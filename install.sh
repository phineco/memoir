#!/bin/bash
# 家音回忆录 · 一键安装（本地 / 云服务器通用）
# 用法：解压后 cd 进目录，执行 bash install.sh
set -e
cd "$(dirname "$0")"

echo "== 1/4 检查 Python =="
python3 --version || { echo "请先安装 Python 3.9+"; exit 1; }

echo "== 2/4 安装依赖 =="
python3 -m pip install --break-system-packages -r requirements.txt

echo "== 3/4 生成配置 =="
if [ ! -f .env ]; then
  cp .env.example .env
  echo "已从 .env.example 生成 .env"
  echo "云端请修改：DATABASE_URL（MySQL）、APP_ENV=cloud、OSS_*、DEEPSEEK_API_KEY"
else
  echo ".env 已存在，跳过"
fi

echo "== 4/4 初始化演示数据 =="
if [ ! -f memoir.db ]; then
  python3 seed.py
  echo "演示数据已灌入（王家样本；演示账号 13800000000 / demo123）"
else
  echo "memoir.db 已存在，跳过（生产环境请用 create_admin.py 建管理员，不要跑 seed.py）"
fi

echo ""
echo "安装完成！"
echo "  本地试运行：python3 app.py   →  http://服务器IP:5000"
echo "  生产部署（gunicorn + MySQL + OSS + HTTPS）：见 DEPLOY.md"
