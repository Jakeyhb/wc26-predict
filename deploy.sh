#!/usr/bin/env bash
set -euo pipefail

echo "=== WC26 Predict 部署脚本 ==="
git pull origin main

echo "构建前端..."
pushd apps/web >/dev/null
npm install
npm run build
popd >/dev/null

echo "复制前端到 nginx..."
rm -rf nginx/html
mkdir -p nginx/html
cp -r apps/web/dist/* nginx/html

echo "构建 Docker 镜像..."
docker-compose -f docker-compose.prod.yml build backend celery nginx

echo "滚动重启服务..."
docker-compose -f docker-compose.prod.yml up -d

echo "执行数据库迁移..."
docker-compose -f docker-compose.prod.yml exec -T backend alembic upgrade head

echo "部署完成 $(date)"
