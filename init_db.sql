-- 创建数据库（如果不存在）
SELECT 'CREATE DATABASE mygamedb'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mygamedb')\gexec

-- 连接到数据库
\c mygamedb

-- 创建订单状态枚举类型
DO $$ BEGIN
    CREATE TYPE order_status AS ENUM ('pending', 'approved', 'rejected');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 创建订单表
CREATE TABLE IF NOT EXISTS orders (
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
CREATE TABLE IF NOT EXISTS grants (
    id         BIGSERIAL PRIMARY KEY,
    user_id    VARCHAR(64) NOT NULL,
    item_id    VARCHAR(64) NOT NULL,
    count      INT NOT NULL DEFAULT 1,
    reason     VARCHAR(255),
    extra      JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- 幂等：可选唯一约束（按业务自定）。以下示例：同一用户在同一天、同一 reason+item 仅记录一次
-- 需要应用层传入幂等键或日期戳。此处示例为 (user_id, item_id, reason, date)
-- 先创建计算列日期（物化简版：generated column 需 PostgreSQL 12+，这里使用 expression index 替代）
CREATE INDEX IF NOT EXISTS idx_grants_user_reason_date ON grants (user_id, item_id, (date_trunc('day', created_at)));

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_grants_user_id ON grants(user_id);
CREATE INDEX IF NOT EXISTS idx_grants_created_at ON grants(created_at DESC);

-- 显示表结构
\d orders
\d grants
