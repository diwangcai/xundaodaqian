#!/bin/bash

# MyGameServer 部署脚本

set -e

echo "=== MyGameServer 部署脚本 ==="

# 检查 Python 版本
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "错误: 需要 Python 3.8 或更高版本，当前版本: $python_version"
    exit 1
fi

echo "✓ Python 版本检查通过: $python_version"

# 检查 PostgreSQL
if ! command -v psql &> /dev/null; then
    echo "错误: 未找到 PostgreSQL，请先安装 PostgreSQL"
    exit 1
fi

echo "✓ PostgreSQL 已安装"

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

echo "✓ 虚拟环境已准备"

# 激活虚拟环境
echo "激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "安装 Python 依赖..."
pip install --upgrade pip
pip install -r requirements-minimal.txt

echo "✓ 依赖安装完成"

# 创建必要的目录
echo "创建目录结构..."
mkdir -p wwwroot/mygame/resource/v1
mkdir -p logs

echo "✓ 目录结构创建完成"

# 检查环境变量文件
if [ ! -f ".env" ]; then
    echo "创建环境变量文件..."
    cp env.example .env
    echo "⚠️  请编辑 .env 文件，设置数据库密码等配置"
    echo "   特别是 DB_PASSWORD 字段"
fi

echo "✓ 环境变量文件已准备"

# 数据库初始化提示
echo ""
echo "=== 下一步操作 ==="
echo "1. 编辑 .env 文件，设置数据库密码"
echo "2. 创建数据库: psql -U postgres -f init_db.sql"
echo "3. 启动服务器: python start.py"
echo ""
echo "管理后台地址: http://127.0.0.1:8000/admin"
echo "=================="
