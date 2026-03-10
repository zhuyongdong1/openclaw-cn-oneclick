from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
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

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", "/stack"))
ENV_FILE = Path(os.getenv("ENV_FILE", str(PROJECT_ROOT / ".env")))
OPENCLAW_CONFIG_PATH = Path(os.getenv("OPENCLAW_CONFIG_PATH", str(PROJECT_ROOT / "data/openclaw/config/openclaw.json")))
COMPOSE_FILE = Path(os.getenv("COMPOSE_FILE", str(PROJECT_ROOT / "docker-compose.yml")))

MANAGED_ENV_KEYS = [
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_WEBHOOK",
    "OPENCLAW_GATEWAY_TOKEN",
    "OPENCLAW_GATEWAY_PORT",
    "OPENCLAW_BRIDGE_PORT",
]


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
    db.add(AuditLog(actor_email=actor_email, action=action, detail=detail, created_at=utcnow()))
    db.commit()


def parse_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def update_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(updates)
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#") or "=" not in line:
            out.append(line)
            continue
        k, _ = line.split("=", 1)
        key = k.strip()
        if key in pending:
            out.append(f"{key}={pending.pop(key)}")
        else:
            out.append(line)
    if pending:
        if out and out[-1].strip() != "":
            out.append("")
        for k, v in pending.items():
            out.append(f"{k}={v}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def ensure_openclaw_config(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "gateway": {
            "mode": "local",
            "controlUi": {
                "allowedOrigins": [
                    "http://localhost:18789",
                    "http://127.0.0.1:18789",
                    "http://localhost:28789",
                    "http://127.0.0.1:28789",
                ]
            },
        }
    }


def compose_cmd() -> list[str] | None:
    checks = [["docker", "compose", "version"], ["docker-compose", "version"]]
    for check in checks:
        try:
            subprocess.run(check, check=True, cwd=PROJECT_ROOT, capture_output=True, text=True)
            return check[:-1]
        except Exception:
            continue
    return None


def restart_gateway() -> tuple[bool, str]:
    cmd = compose_cmd()
    if cmd is None:
        return False, "compose command not found (docker compose / docker-compose)"
    full = cmd + ["-f", str(COMPOSE_FILE), "up", "-d", "openclaw-gateway"]
    try:
        out = subprocess.run(full, check=True, cwd=PROJECT_ROOT, capture_output=True, text=True)
        text = (out.stdout + "\n" + out.stderr).strip()
        return True, text or "gateway applied"
    except subprocess.CalledProcessError as e:
        err = (e.stdout or "") + "\n" + (e.stderr or "")
        return False, err.strip() or "failed to apply"


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


class ConfigOut(BaseModel):
    deepseek_base_url: str = ""
    deepseek_api_key_masked: str = ""
    feishu_app_id: str = ""
    feishu_app_secret_masked: str = ""
    feishu_webhook_masked: str = ""
    openclaw_gateway_token_masked: str = ""
    openclaw_gateway_port: str = "18789"
    openclaw_bridge_port: str = "18790"


class ConfigIn(BaseModel):
    deepseek_api_key: str = ""
    deepseek_base_url: str = ""
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_webhook: str = ""
    openclaw_gateway_token: str = ""
    openclaw_gateway_port: str = "18789"
    openclaw_bridge_port: str = "18790"


class ApplyOut(BaseModel):
    ok: bool
    message: str


app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        existing = db.execute(select(User).where(User.email == settings.admin_email)).scalar_one_or_none()
        if existing is None:
            db.add(User(email=settings.admin_email, password_hash=hash_password(settings.admin_password), created_at=utcnow()))
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
    return LoginOut(access_token=token, expires_in_minutes=settings.access_token_expire_minutes)


@app.get("/me", response_model=MeOut)
def me(user_email: str = Depends(require_auth)) -> MeOut:
    return MeOut(email=user_email, app=settings.app_name, env=settings.app_env)


@app.get("/admin/audit", response_model=list[AuditOut])
def list_audit(limit: int = 50, user_email: str = Depends(require_auth), db: Session = Depends(db_session)) -> list[AuditOut]:
    _ = user_email
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 200)))).scalars().all()
    return [AuditOut(id=r.id, actor_email=r.actor_email, action=r.action, detail=r.detail, created_at=r.created_at) for r in rows]


@app.get("/admin/config", response_model=ConfigOut)
def get_config(user_email: str = Depends(require_auth)) -> ConfigOut:
    _ = user_email
    envs = parse_env(ENV_FILE)

    def mask(v: str) -> str:
        if not v:
            return ""
        if len(v) <= 8:
            return "*" * len(v)
        return f"{v[:4]}***{v[-4:]}"

    return ConfigOut(
        deepseek_base_url=envs.get("DEEPSEEK_BASE_URL", ""),
        deepseek_api_key_masked=mask(envs.get("DEEPSEEK_API_KEY", "")),
        feishu_app_id=envs.get("FEISHU_APP_ID", ""),
        feishu_app_secret_masked=mask(envs.get("FEISHU_APP_SECRET", "")),
        feishu_webhook_masked=mask(envs.get("FEISHU_WEBHOOK", "")),
        openclaw_gateway_token_masked=mask(envs.get("OPENCLAW_GATEWAY_TOKEN", "")),
        openclaw_gateway_port=envs.get("OPENCLAW_GATEWAY_PORT", "18789"),
        openclaw_bridge_port=envs.get("OPENCLAW_BRIDGE_PORT", "18790"),
    )


@app.post("/admin/config")
def save_config(payload: ConfigIn, user_email: str = Depends(require_auth), db: Session = Depends(db_session)) -> dict[str, Any]:
    updates = {
        "DEEPSEEK_API_KEY": payload.deepseek_api_key.strip(),
        "DEEPSEEK_BASE_URL": payload.deepseek_base_url.strip(),
        "FEISHU_APP_ID": payload.feishu_app_id.strip(),
        "FEISHU_APP_SECRET": payload.feishu_app_secret.strip(),
        "FEISHU_WEBHOOK": payload.feishu_webhook.strip(),
        "OPENCLAW_GATEWAY_TOKEN": payload.openclaw_gateway_token.strip(),
        "OPENCLAW_GATEWAY_PORT": payload.openclaw_gateway_port.strip() or "18789",
        "OPENCLAW_BRIDGE_PORT": payload.openclaw_bridge_port.strip() or "18790",
    }
    # only write non-empty keys to avoid accidental erasing
    updates = {k: v for k, v in updates.items() if v != ""}
    if not updates:
        raise HTTPException(status_code=400, detail="No values to save")

    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.write_text("", encoding="utf-8")
    update_env(ENV_FILE, updates)

    OPENCLAW_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg = ensure_openclaw_config(OPENCLAW_CONFIG_PATH)
    OPENCLAW_CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    audit(db, actor_email=user_email, action="config_save", detail=f"Saved keys: {', '.join(sorted(updates.keys()))}")
    return {"ok": True, "saved": sorted(updates.keys())}


@app.post("/admin/config/apply", response_model=ApplyOut)
def apply_config(user_email: str = Depends(require_auth), db: Session = Depends(db_session)) -> ApplyOut:
    ok, msg = restart_gateway()
    audit(db, actor_email=user_email, action="config_apply", detail=("ok: " if ok else "failed: ") + msg[:500])
    return ApplyOut(ok=ok, message=msg)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
