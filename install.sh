#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing dependency: $1" >&2
    exit 1
  }
}

need_cmd docker
need_cmd python3

COMPOSE_CMD=()
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "Docker Compose not available. Install docker compose plugin or docker-compose." >&2
  exit 1
fi

env_has_key() {
  local key="$1"
  [[ -f "$ROOT_DIR/.env" ]] && grep -q "^${key}=" "$ROOT_DIR/.env"
}

append_env_kv() {
  local key="$1"
  local value="$2"
  if ! env_has_key "$key"; then
    printf '%s=%s\n' "$key" "$value" >> "$ROOT_DIR/.env"
  fi
}

OPENCLAW_CONFIG_DIR_DEFAULT="$ROOT_DIR/data/openclaw/config"
OPENCLAW_WORKSPACE_DIR_DEFAULT="$ROOT_DIR/data/openclaw/workspace"

mkdir -p "$OPENCLAW_CONFIG_DIR_DEFAULT" "$OPENCLAW_WORKSPACE_DIR_DEFAULT"

is_tcp_port_in_use() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "Generating .env"
  SECRET_KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
  )"
  POSTGRES_PASSWORD="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
  )"
  ADMIN_PASSWORD="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(16))
PY
  )"

  OPENCLAW_GATEWAY_TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
  )"

  cat > "$ROOT_DIR/.env" <<EOF
APP_NAME=OpenClaw CN OneClick
APP_ENV=local

API_HOST=0.0.0.0
API_PORT=8080
API_BASE_URL=http://localhost:8080

SECRET_KEY=$SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES=43200

ADMIN_EMAIL=admin@local
ADMIN_PASSWORD=$ADMIN_PASSWORD

POSTGRES_DB=openclaw
POSTGRES_USER=openclaw
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
DATABASE_URL=postgresql+psycopg://openclaw:$POSTGRES_PASSWORD@db:5432/openclaw

OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:latest
OPENCLAW_GATEWAY_BIND=lan
OPENCLAW_GATEWAY_PORT=18789
OPENCLAW_BRIDGE_PORT=18790
OPENCLAW_GATEWAY_TOKEN=$OPENCLAW_GATEWAY_TOKEN
OPENCLAW_CONFIG_DIR=$OPENCLAW_CONFIG_DIR_DEFAULT
OPENCLAW_WORKSPACE_DIR=$OPENCLAW_WORKSPACE_DIR_DEFAULT
EOF

  echo "Created $ROOT_DIR/.env"
  echo "Admin credentials: admin@local / $ADMIN_PASSWORD"
else
  echo "Using existing .env"

  # Backfill OpenClaw settings if this repo was created before integration.
  append_env_kv "OPENCLAW_IMAGE" "ghcr.io/openclaw/openclaw:latest"
  append_env_kv "OPENCLAW_GATEWAY_BIND" "lan"
  append_env_kv "OPENCLAW_GATEWAY_PORT" "18789"
  append_env_kv "OPENCLAW_BRIDGE_PORT" "18790"
  if ! env_has_key "OPENCLAW_GATEWAY_TOKEN"; then
    OPENCLAW_GATEWAY_TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
    )"
    append_env_kv "OPENCLAW_GATEWAY_TOKEN" "$OPENCLAW_GATEWAY_TOKEN"
  fi
  append_env_kv "OPENCLAW_CONFIG_DIR" "$OPENCLAW_CONFIG_DIR_DEFAULT"
  append_env_kv "OPENCLAW_WORKSPACE_DIR" "$OPENCLAW_WORKSPACE_DIR_DEFAULT"
fi

echo "Starting containers..."

# Avoid common local port conflicts (e.g. OpenClaw already running on host).
if is_tcp_port_in_use 18789; then
  export OPENCLAW_GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-28789}"
fi
if is_tcp_port_in_use 18790; then
  export OPENCLAW_BRIDGE_PORT="${OPENCLAW_BRIDGE_PORT:-28790}"
fi

# Create a minimal OpenClaw config on first run.
# This is required when binding the Control UI to non-loopback inside Docker.
OPENCLAW_CONFIG_PATH="$OPENCLAW_CONFIG_DIR_DEFAULT/openclaw.json"
if [[ ! -f "$OPENCLAW_CONFIG_PATH" ]]; then
  cat > "$OPENCLAW_CONFIG_PATH" <<'EOF'
{
  "gateway": {
    "mode": "local",
    "controlUi": {
      "allowedOrigins": [
        "http://localhost:18789",
        "http://127.0.0.1:18789",
        "http://localhost:28789",
        "http://127.0.0.1:28789"
      ]
    }
  }
}
EOF
fi

# If the env is still set to a local image but it doesn't exist, fall back to the
# published container image so one-click works without a source build.
OPENCLAW_IMAGE_VALUE="$(grep '^OPENCLAW_IMAGE=' "$ROOT_DIR/.env" | head -n 1 | cut -d= -f2-)"
if [[ "$OPENCLAW_IMAGE_VALUE" == "openclaw:local" ]]; then
  if ! docker image inspect "openclaw:local" >/dev/null 2>&1; then
    export OPENCLAW_IMAGE="ghcr.io/openclaw/openclaw:latest"
  fi
fi

"${COMPOSE_CMD[@]}" -f "$ROOT_DIR/docker-compose.yml" up -d --build

echo
echo "Done. Open:" 
echo "- Admin UI: http://localhost:8080/"
echo "- API docs: http://localhost:8080/docs"
echo "- OpenClaw Gateway: http://localhost:${OPENCLAW_GATEWAY_PORT:-18789}/ (health: /healthz)"
