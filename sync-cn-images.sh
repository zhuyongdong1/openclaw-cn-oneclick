#!/usr/bin/env bash
set -euo pipefail

# 用法：
#   export CN_REGISTRY=registry.cn-hangzhou.aliyuncs.com
#   export CN_NAMESPACE=zhuyodo/openclaw
#   ./sync-cn-images.sh
#
# 可选：
#   export OPENCLAW_UPSTREAM_IMAGE=ghcr.io/openclaw/openclaw:latest
#   export POSTGRES_UPSTREAM_IMAGE=postgres:16-alpine

CN_REGISTRY="${CN_REGISTRY:-}"
CN_NAMESPACE="${CN_NAMESPACE:-}"
OPENCLAW_UPSTREAM_IMAGE="${OPENCLAW_UPSTREAM_IMAGE:-ghcr.io/openclaw/openclaw:latest}"
POSTGRES_UPSTREAM_IMAGE="${POSTGRES_UPSTREAM_IMAGE:-postgres:16-alpine}"

if [[ -z "$CN_REGISTRY" || -z "$CN_NAMESPACE" ]]; then
  echo "[ERR] 请先设置 CN_REGISTRY 和 CN_NAMESPACE"
  echo "例如:"
  echo "  export CN_REGISTRY=registry.cn-hangzhou.aliyuncs.com"
  echo "  export CN_NAMESPACE=zhuyodo/openclaw"
  exit 1
fi

CN_OPENCLAW_IMAGE="${CN_REGISTRY}/${CN_NAMESPACE}/openclaw:latest"
CN_POSTGRES_IMAGE="${CN_REGISTRY}/${CN_NAMESPACE}/postgres:16-alpine"

echo "[1/6] Pull upstream images"
docker pull "$OPENCLAW_UPSTREAM_IMAGE"
docker pull "$POSTGRES_UPSTREAM_IMAGE"

echo "[2/6] Tag CN images"
docker tag "$OPENCLAW_UPSTREAM_IMAGE" "$CN_OPENCLAW_IMAGE"
docker tag "$POSTGRES_UPSTREAM_IMAGE" "$CN_POSTGRES_IMAGE"

echo "[3/6] Login CN registry"
echo "请按提示登录国内镜像仓库（ACR/TCR）"
docker login "$CN_REGISTRY"

echo "[4/6] Push CN images"
docker push "$CN_OPENCLAW_IMAGE"
docker push "$CN_POSTGRES_IMAGE"

echo "[5/6] Done"
echo "CN_OPENCLAW_IMAGE=$CN_OPENCLAW_IMAGE"
echo "CN_POSTGRES_IMAGE=$CN_POSTGRES_IMAGE"

echo "[6/6] 客户部署示例"
cat <<EOF
export CN_OPENCLAW_IMAGE=$CN_OPENCLAW_IMAGE
export CN_POSTGRES_IMAGE=$CN_POSTGRES_IMAGE
./deploy-cn.sh
EOF
