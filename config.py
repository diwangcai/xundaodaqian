import os
from pathlib import Path

# 基础配置
BASE_DIR = Path(__file__).resolve().parent

# 数据库配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'dbname': os.getenv('DB_NAME', 'mygamedb'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'your_password'),  # 请设置环境变量
}

# 服务器配置
SERVER_CONFIG = {
    'host': os.getenv('SERVER_HOST', '0.0.0.0'),
    'port': int(os.getenv('SERVER_PORT', 8000)),
    'debug': os.getenv('SERVER_DEBUG', 'false').lower() == 'true',
}

# 日志配置
LOG_CONFIG = {
    'level': os.getenv('LOG_LEVEL', 'INFO'),
    'file': BASE_DIR / 'logs' / 'server.log',
    'max_size': int(os.getenv('LOG_MAX_SIZE', 10 * 1024 * 1024)),  # 10MB
    'backup_count': int(os.getenv('LOG_BACKUP_COUNT', 5)),
}

# 安全配置
SECURITY_CONFIG = {
    'admin_token': os.getenv('ADMIN_TOKEN', ''),  # 管理后台访问令牌
    'enable_auth': os.getenv('ENABLE_AUTH', 'false').lower() == 'true',
    'enable_basic': os.getenv('ENABLE_BASIC_AUTH', 'false').lower() == 'true',
    'admin_user': os.getenv('ADMIN_USER', ''),
    'admin_pass': os.getenv('ADMIN_PASS', ''),
}

# 游戏配置
GAME_CONFIG = {
    'assets_server': os.getenv('ASSETS_SERVER', 'http://127.0.0.1:8000/mygame/'),
    'hot_update_enabled': os.getenv('HOT_UPDATE_ENABLED', 'true').lower() == 'true',
}

# 请求限制配置
REQUEST_CONFIG = {
    'max_body_bytes': int(os.getenv('MAX_BODY_BYTES', 1_000_000)),  # 1MB
}
