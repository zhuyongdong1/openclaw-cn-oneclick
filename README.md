# openclaw-cn-oneclick

Local, one-click deployable stack:

- Web admin UI + API (FastAPI)
- Postgres
- OpenClaw gateway (Docker image)

## Quickstart (macOS/Linux)

Prereq: Docker Desktop (or Docker Engine) with **either** `docker compose` or `docker-compose`.

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

## 网页配置 .env（给不会命令行的客户）

项目内置了网页配置器：

- `tools/env-web-config.html`

使用方式：

1. 双击打开这个 HTML 文件（Mac/Windows 浏览器都可）
2. 按表单填写密钥和参数
3. 点击“下载 .env”
4. 把下载的文件放到项目根目录（与 `docker-compose.yml` 同级）
5. 执行 `./install.sh`

> 注意：`.env` 包含敏感信息，不要上传到 GitHub。

## Ubuntu 常见问题（云服务器）

如果你是通过 Ubuntu 仓库安装的 Docker，可能出现：

- 有 `docker`，但没有 `docker compose`
- `docker-compose-plugin` 包找不到

可直接安装 v1：

```bash
sudo apt update
sudo apt install -y docker-compose
```

本项目 `install.sh` 已兼容 `docker compose` / `docker-compose` 两种命令。

## Dev

```bash
docker compose logs -f api || docker-compose logs -f api
docker compose down || docker-compose down
```
