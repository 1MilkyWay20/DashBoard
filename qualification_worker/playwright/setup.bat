@echo off
REM 依赖上级 qualification_worker\.venv，不再在本目录建虚拟环境
cd /d "%~dp0.."

where python >nul 2>&1
if errorlevel 1 (
  echo 未找到 python，请先安装 Python 3.10+ 并勾选 Add to PATH
  exit /b 1
)

if not exist .venv (
  echo ==^> 创建虚拟环境 qualification_worker\.venv
  python -m venv .venv
  if errorlevel 1 exit /b 1
)

echo ==^> 安装依赖（清华源）
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
if errorlevel 1 exit /b 1

echo.
echo 完成。激活环境并运行：
echo   cd %CD%
echo   .venv\Scripts\activate
echo   python playwright\changeFileMt.py
echo.
echo 说明：
echo   - 虚拟环境在 qualification_worker\.venv（与 worker 共用）
echo   - 脚本默认使用本机已安装的 Google Chrome
