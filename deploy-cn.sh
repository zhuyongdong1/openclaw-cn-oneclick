#!/usr/bin/env bash
set -euo pipefail

echo "[CN] openclaw-cn-oneclick deploy"

configure_linux_docker_mirror() {
  # 可通过 SKIP_DOCKER_MIRROR=1 跳过
  if [[ "${SKIP_DOCKER_MIRROR:-0}" == "1" ]]; then
    echo "[CN] skip docker mirror config (SKIP_DOCKER_MIRROR=1)"
    return 0
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "[CN] docker not found, skip mirror setup"
    return 0
  fi

  local daemon_json="/etc/docker/daemon.json"
  local tmp_file
  tmp_file="$(mktemp)"

  cat > "$tmp_file" <<'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://mirror.ccs.tencentyun.com",
    "https://docker.1ms.run"
  ]
}
EOF

  if [[ "$(id -u)" -eq 0 ]]; then
    mkdir -p /etc/docker
    cp "$tmp_file" "$daemon_json"
    if command -v systemctl >/dev/null 2>&1; then
      systemctl daemon-reload || true
      systemctl restart docker
    else
      service docker restart || true
    fi
  else
    if ! command -v sudo >/dev/null 2>&1; then
      echo "[CN] sudo not found, skip mirror setup"
      rm -f "$tmp_file"
      return 0
    fi
    sudo mkdir -p /etc/docker
    sudo cp "$tmp_file" "$daemon_json"
    if command -v systemctl >/dev/null 2>&1; then
      sudo systemctl daemon-reload || true
      sudo systemctl restart docker
    else
      sudo service docker restart || true
    fi
  fi

  rm -f "$tmp_file"
  echo "[CN] docker mirror configured: $daemon_json"
  docker info 2>/dev/null | sed -n '/Registry Mirrors/,+6p' || true
}

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
  configure_linux_docker_mirror
else
  echo "[CN] Desktop system detected ($OSTYPE)."
  echo "[CN] 请在 Docker Desktop > Settings > Docker Engine 手动配置 registry-mirrors。"
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

# 你可以在执行前导出下面两个变量，或直接改成你的固定国内镜像地址
# export CN_POSTGRES_IMAGE=registry.cn-hangzhou.aliyuncs.com/<ns>/postgres:16-alpine
# export CN_OPENCLAW_IMAGE=registry.cn-hangzhou.aliyuncs.com/<ns>/openclaw:latest
CN_POSTGRES_IMAGE="${CN_POSTGRES_IMAGE:-}"
CN_OPENCLAW_IMAGE="${CN_OPENCLAW_IMAGE:-}"

if [[ -n "$CN_POSTGRES_IMAGE" ]]; then
  if grep -q '^POSTGRES_IMAGE=' .env; then
    sed -i.bak "s#^POSTGRES_IMAGE=.*#POSTGRES_IMAGE=${CN_POSTGRES_IMAGE}#" .env
  else
    echo "POSTGRES_IMAGE=${CN_POSTGRES_IMAGE}" >> .env
  fi
else
  echo "[CN] CN_POSTGRES_IMAGE is empty; keep current POSTGRES_IMAGE in .env"
fi

if [[ -n "$CN_OPENCLAW_IMAGE" ]]; then
  if grep -q '^OPENCLAW_IMAGE=' .env; then
    sed -i.bak "s#^OPENCLAW_IMAGE=.*#OPENCLAW_IMAGE=${CN_OPENCLAW_IMAGE}#" .env
  else
    echo "OPENCLAW_IMAGE=${CN_OPENCLAW_IMAGE}" >> .env
  fi
else
  echo "[CN] CN_OPENCLAW_IMAGE is empty; keep current OPENCLAW_IMAGE in .env"
fi

./install.sh

echo "[CN] done"
