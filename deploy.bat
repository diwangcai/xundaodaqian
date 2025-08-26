@echo off
chcp 65001 >nul
echo === MyGameServer 部署脚本 ===

REM 检查 Python 版本
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

echo ✓ Python 已安装

REM 检查 PostgreSQL
psql --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 PostgreSQL，请先安装 PostgreSQL
    pause
    exit /b 1
)

echo ✓ PostgreSQL 已安装

REM 创建虚拟环境
if not exist "venv" (
    echo 创建虚拟环境...
    python -m venv venv
)

echo ✓ 虚拟环境已准备

REM 激活虚拟环境
echo 激活虚拟环境...
call venv\Scripts\activate.bat

REM 安装依赖
echo 安装 Python 依赖...
python -m pip install --upgrade pip
pip install -r requirements-minimal.txt

echo ✓ 依赖安装完成

REM 创建必要的目录
echo 创建目录结构...
if not exist "wwwroot\mygame\resource\v1" mkdir wwwroot\mygame\resource\v1
if not exist "logs" mkdir logs

echo ✓ 目录结构创建完成

REM 检查环境变量文件
if not exist ".env" (
    echo 创建环境变量文件...
    copy env.example .env
    echo ⚠️  请编辑 .env 文件，设置数据库密码等配置
    echo    特别是 DB_PASSWORD 字段
)

echo ✓ 环境变量文件已准备

echo.
echo === 下一步操作 ===
echo 1. 编辑 .env 文件，设置数据库密码
echo 2. 创建数据库: psql -U postgres -f init_db.sql
echo 3. 启动服务器: python start.py
echo.
echo 管理后台地址: http://127.0.0.1:8000/admin
echo ==================
pause
