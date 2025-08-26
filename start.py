#!/usr/bin/env python3
"""
MyGameServer 启动脚本
支持环境变量配置和命令行参数
"""

import os
import sys
import argparse
from pathlib import Path

def load_env_file(env_file):
    """加载环境变量文件"""
    if not env_file.exists():
        print(f"警告: 环境变量文件 {env_file} 不存在")
        return
    
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

def main():
    parser = argparse.ArgumentParser(description='MyGameServer 启动脚本')
    parser.add_argument('--env', default='.env', help='环境变量文件路径')
    parser.add_argument('--port', type=int, help='服务器端口')
    parser.add_argument('--host', help='服务器主机')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    
    args = parser.parse_args()
    
    # 加载环境变量文件
    env_file = Path(args.env)
    load_env_file(env_file)
    
    # 命令行参数覆盖环境变量
    if args.port:
        os.environ['SERVER_PORT'] = str(args.port)
    if args.host:
        os.environ['SERVER_HOST'] = args.host
    if args.debug:
        os.environ['SERVER_DEBUG'] = 'true'
    
    # 检查必要的环境变量
    if os.environ.get('DB_PASSWORD') == 'your_password_here':
        print("警告: 请设置 DB_PASSWORD 环境变量")
        print("可以复制 env.example 为 .env 并修改配置")
        sys.exit(1)
    
    # 启动服务器
    print("正在启动 MyGameServer...")
    from server import app, logger
    
    try:
        from config import SERVER_CONFIG
        logger.info(f"服务器配置: {SERVER_CONFIG}")
        app.run(
            host=SERVER_CONFIG['host'],
            port=SERVER_CONFIG['port'],
            debug=SERVER_CONFIG['debug']
        )
    except KeyboardInterrupt:
        logger.info("服务器已停止")
    except Exception as e:
        logger.error(f"服务器启动失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
