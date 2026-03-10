#!/usr/bin/env bash
set -euo pipefail

echo "[GLOBAL] openclaw-cn-oneclick deploy"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

# Ensure global default images
if grep -q '^POSTGRES_IMAGE=' .env; then
  sed -i.bak 's#^POSTGRES_IMAGE=.*#POSTGRES_IMAGE=postgres:16-alpine#' .env
else
  echo 'POSTGRES_IMAGE=postgres:16-alpine' >> .env
fi

if grep -q '^OPENCLAW_IMAGE=' .env; then
  sed -i.bak 's#^OPENCLAW_IMAGE=.*#OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:latest#' .env
else
  echo 'OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:latest' >> .env
fi

./install.sh

echo "[GLOBAL] done"
