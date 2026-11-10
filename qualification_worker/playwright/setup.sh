#!/usr/bin/env bash
# 依赖上级 qualification_worker/.venv，不再在本目录建虚拟环境
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3，请先安装 Python 3.10+"
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "==> 创建虚拟环境 qualification_worker/.venv"
  python3 -m venv .venv
fi

echo "==> 安装依赖（清华源）"
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

echo ""
echo "完成。激活环境并运行："
echo "  cd $(pwd)"
echo "  source .venv/bin/activate"
echo "  python playwright/changeFileMt.py"
echo ""
echo "说明："
echo "  - 虚拟环境在 qualification_worker/.venv（与 worker 共用）"
echo "  - 脚本默认使用本机已安装的 Google Chrome"
