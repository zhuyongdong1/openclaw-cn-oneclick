#!/usr/bin/env bash
set -euo pipefail

echo "[CN] openclaw-cn-oneclick deploy"

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
