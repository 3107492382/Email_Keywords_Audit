@echo off
chcp 65001 >nul
echo ============================================
echo   邮件关键词审计系统 — 运行脚本 (Conda)
echo ============================================
echo.

REM 检查 conda
where conda >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 conda
    pause
    exit /b 1
)

set ENV_NAME=email_audit

REM 创建环境（首次）
conda env list | findstr /C:"%ENV_NAME%" >nul
if errorlevel 1 (
    echo [1/3] 创建 conda 环境 %ENV_NAME%...
    conda create -n %ENV_NAME% python=3.10 -y
)

call conda activate %ENV_NAME%

echo [2/3] 检查依赖...
pip install -r requirements.txt --quiet -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [3/3] 启动应用...
python main.py
pause
