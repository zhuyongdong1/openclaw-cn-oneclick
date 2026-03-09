# openclaw-cn-oneclick

Local, one-click deployable stack:

- Web admin UI + API (FastAPI)
- Postgres
- OpenClaw gateway (Docker image)

## Quickstart (macOS/Linux)

Prereq: Docker Desktop (or Docker Engine) with `docker compose`.

```bash
./install.sh
```

Then open:

- Admin UI: http://localhost:8080/
- API docs (Swagger): http://localhost:8080/docs
- OpenClaw Gateway: http://localhost:18789/ (health: /healthz)

If `18789` is already in use on your machine, `install.sh` will fall back to `28789`.

## What you get

- FastAPI service with JWT login
- Postgres database
- Minimal admin UI (status, token login, view audit logs)
- OpenClaw gateway container (pulled via `OPENCLAW_IMAGE`)

By default we use `OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:latest`.

## Dev

```bash
docker compose logs -f api
docker compose down
```
