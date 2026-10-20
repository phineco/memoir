#!/bin/bash
# 安全安装入口：仅配置依赖与示例环境，不修改任何数据库。
set -euo pipefail
cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "需要 Python 3.10+")'
if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  .venv/bin/python - <<'CONFIG'
import secrets
from pathlib import Path
with Path(".env").open("a") as output:
    output.write("\nSECRET_KEY=" + secrets.token_hex(32) + "\n")
CONFIG
fi
cat <<'NEXT'
依赖与配置已准备；没有创建或清空数据库。
新项目：核对 .env 后执行 .venv/bin/python create_admin.py 创建账号。
已有部署：先备份，再按 DEPLOY.md 执行增量迁移。
演示 seed.py 会清空业务数据，必须手动选择独立演示库运行。
NEXT
