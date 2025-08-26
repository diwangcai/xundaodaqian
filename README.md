# MyGameServer - 游戏服务器

这是一个基于 Flask 的游戏服务器，支持支付处理、道具发放等功能。

## 功能特性

- 静态文件服务（游戏资源）
- 支付订单管理（PostgreSQL）
- 道具发放记录
- 假二维码支付页面
- 后台管理接口

## 数据库设置

### 1. 安装 PostgreSQL

确保已安装 PostgreSQL 并启动服务。

### 2. 创建数据库

```bash
# 连接到 PostgreSQL
psql -U postgres

# 执行初始化脚本
\i init_db.sql
```

或者手动执行：

```sql
-- 创建数据库
CREATE DATABASE mygamedb;

-- 连接到数据库
\c mygamedb

-- 创建枚举类型
DO $$ BEGIN
    CREATE TYPE order_status AS ENUM ('pending', 'approved', 'rejected');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 创建订单表
CREATE TABLE orders (
    id               BIGSERIAL PRIMARY KEY,
    order_id         VARCHAR(64) NOT NULL,
    client_order_no  VARCHAR(64),
    user_id          VARCHAR(64),
    amount           NUMERIC(10,2),
    status           order_status NOT NULL DEFAULT 'pending',
    raw_json         JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uk_order_id         UNIQUE (order_id),
    CONSTRAINT uk_client_order_no  UNIQUE (client_order_no)
);

-- 创建发道具表
CREATE TABLE grants (
    id         BIGSERIAL PRIMARY KEY,
    user_id    VARCHAR(64) NOT NULL,
    item_id    VARCHAR(64) NOT NULL,
    count      INT NOT NULL DEFAULT 1,
    reason     VARCHAR(255),
    extra      JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## 安装依赖

### 完整依赖（包含所有包）

```bash
pip install -r requirements.txt
```

### 最小依赖（推荐）

```bash
pip install -r requirements-minimal.txt
```

## 配置

### 方法1: 环境变量文件（推荐）

复制环境变量示例文件并修改：

```bash
cp env.example .env
# 编辑 .env 文件，设置数据库密码等配置
```

### 方法2: 环境变量

直接设置环境变量：

```bash
export DB_PASSWORD=your_password_here
export SERVER_PORT=8000
```

### 方法3: 修改配置文件

编辑 `config.py` 中的默认配置。

## 运行服务器

### 方法1: 使用启动脚本（推荐）

```bash
# 使用环境变量文件
python start.py

# 指定端口
python start.py --port 8080

# 调试模式
python start.py --debug
```

### 方法2: 直接运行

```bash
python server.py
```

服务器将在 `http://127.0.0.1:8000` 启动。

### 管理员鉴权（可选）

设置环境变量启用后台鉴权：

```bash
export ENABLE_AUTH=true
export ADMIN_TOKEN=your_strong_token
```

启用后，访问管理后台需提供令牌（支持三种方式）：
- 请求头：`Authorization: Bearer your_strong_token`
- URL 参数：`/admin?token=your_strong_token`
- Cookie：浏览器会在登录页写入 `admin_token`

### 管理后台

启动后访问 `http://127.0.0.1:8000/admin` 进入管理后台。

## API 接口

### 健康检查

- `GET /healthz` - 健康状态
- `GET /readyz` - 就绪状态

### 游戏资源

- `GET /mygame/*` - 静态文件服务

### 支付相关

- `POST /pay/submit` - 提交支付订单
- `GET /pay/status?orderId=xxx` - 查询订单状态
- `GET /pay/qr/<order_id>` - 假二维码支付页面

### 后台管理

- `POST /admin/pay/review` - 审核支付订单
- `GET /admin/pay/list` - 获取订单列表
- `POST /admin/grant-item` - 发放道具

### 游戏 API

- `POST /api/login` - 登录
- `POST /api/battle/start` - 战斗开始
- `POST /report` - 数据上报

## 目录结构

```
MyGameServer/
├── server.py              # 主服务器文件
├── start.py               # 启动脚本
├── config.py              # 配置文件
├── admin.html             # 管理后台界面
├── requirements.txt       # 完整依赖
├── requirements-minimal.txt # 最小依赖
├── init_db.sql           # 数据库初始化脚本
├── env.example           # 环境变量示例
├── README.md             # 说明文档
├── wwwroot/              # 静态文件根目录
│   └── mygame/           # 游戏资源目录
│       ├── resource/     # 热更新资源
│       └── qr.png        # 假二维码图片
├── logs/                 # 日志目录
│   └── server.log        # 服务器日志
└── data/                 # 数据目录（已废弃，改用数据库）
```

## 注意事项

1. 确保 PostgreSQL 服务正在运行
2. 设置数据库密码（通过环境变量或配置文件）
3. 首次运行会自动创建数据库表
4. 支付订单需要手动审核，不会自动通过
5. 所有支付都会显示假二维码页面
6. 管理后台访问地址：`http://127.0.0.1:8000/admin`
7. 日志文件保存在 `logs/server.log`

## 功能特性

- ✅ PostgreSQL 数据库存储
- ✅ 订单幂等性支持
- ✅ 管理后台界面
- ✅ 完整的日志系统
- ✅ 环境变量配置
- ✅ 静态文件服务
- ✅ 支付订单管理
- ✅ 道具发放功能
- ✅ 系统状态监控
