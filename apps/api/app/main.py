from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Settings(BaseSettings):
    app_name: str = "OpenClaw CN OneClick"
    app_env: str = "local"
    api_base_url: str = "http://localhost:8080"

    secret_key: str
    access_token_expire_minutes: int = 60 * 24 * 30

    admin_email: str
    admin_password: str

    database_url: str

    class Config:
        env_prefix = ""
        case_sensitive = False


settings = Settings()

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_email: Mapped[str] = mapped_column(String(320), index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


engine = create_engine(settings.database_url, pool_pre_ping=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def db_session() -> Session:
    with Session(engine) as s:
        yield s


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(*, subject: str, expires_minutes: int) -> str:
    now = utcnow()
    exp = now + timedelta(minutes=expires_minutes)
    payload = {"sub": subject, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def get_current_user_email(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        sub = payload.get("sub")
        if not sub or not isinstance(sub, str):
            raise ValueError("missing sub")
        return sub
    except (JWTError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e


def bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return auth.removeprefix("Bearer ").strip()


def require_auth(token: str = Depends(bearer_token)) -> str:
    return get_current_user_email(token)


def audit(db: Session, *, actor_email: str, action: str, detail: str) -> None:
    db.add(
        AuditLog(
            actor_email=actor_email,
            action=action,
            detail=detail,
            created_at=utcnow(),
        )
    )
    db.commit()


class LoginIn(BaseModel):
    email: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class MeOut(BaseModel):
    email: str
    app: str
    env: str


class AuditOut(BaseModel):
    id: int
    actor_email: str
    action: str
    detail: str
    created_at: datetime


app = FastAPI(title=settings.app_name)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        existing = db.execute(select(User).where(User.email == settings.admin_email)).scalar_one_or_none()
        if existing is None:
            db.add(
                User(
                    email=settings.admin_email,
                    password_hash=hash_password(settings.admin_password),
                    created_at=utcnow(),
                )
            )
            db.commit()
            audit(db, actor_email=settings.admin_email, action="bootstrap", detail="Initial admin created")


@app.get("/healthz")
def healthz(db: Session = Depends(db_session)) -> dict[str, Any]:
    db.execute(select(1))
    return {"ok": True, "app": settings.app_name, "env": settings.app_env, "time": utcnow().isoformat()}


@app.post("/auth/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(db_session)) -> LoginOut:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(subject=user.email, expires_minutes=settings.access_token_expire_minutes)
    audit(db, actor_email=user.email, action="login", detail="User login")
    return LoginOut(
        access_token=token,
        expires_in_minutes=settings.access_token_expire_minutes,
    )


@app.get("/me", response_model=MeOut)
def me(user_email: str = Depends(require_auth)) -> MeOut:
    return MeOut(email=user_email, app=settings.app_name, env=settings.app_env)


@app.get("/admin/audit", response_model=list[AuditOut])
def list_audit(
    limit: int = 50,
    user_email: str = Depends(require_auth),
    db: Session = Depends(db_session),
) -> list[AuditOut]:
    _ = user_email
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 200)))).scalars().all()
    return [
        AuditOut(
            id=r.id,
            actor_email=r.actor_email,
            action=r.action,
            detail=r.detail,
            created_at=r.created_at,
        )
        for r in rows
    ]


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
