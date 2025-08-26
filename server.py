from flask import Flask, jsonify, request, send_from_directory, abort, render_template_string
from pathlib import Path
import shutil
import json
import time
import threading
import uuid
import base64
import psycopg2
import logging
import os
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from logging.handlers import RotatingFileHandler
from functools import wraps
import time


app = Flask(__name__)

# 根目录与静态目录
ROOT_DIR = Path(__file__).resolve().parent
WWW_DIR = ROOT_DIR / 'wwwroot'
MYGAME_ROOT = WWW_DIR / 'mygame'
RESOURCE_V1 = MYGAME_ROOT / 'resource' / 'v1'
REMOTE_DIR = MYGAME_ROOT / 'remote'
DATA_DIR = ROOT_DIR / 'data'

# 导入配置
from config import DB_CONFIG, SERVER_CONFIG, LOG_CONFIG, SECURITY_CONFIG, REQUEST_CONFIG

# 数据库连接锁
_DB_LOCK = threading.Lock()

# 配置日志
def setup_logging():
    """配置日志系统"""
    log_dir = ROOT_DIR / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    # 配置根日志器
    rotating_handler = RotatingFileHandler(
        filename=LOG_CONFIG['file'],
        maxBytes=LOG_CONFIG.get('max_size', 10 * 1024 * 1024),
        backupCount=LOG_CONFIG.get('backup_count', 5),
        encoding='utf-8'
    )
    rotating_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_CONFIG['level']))
    # 清理默认处理器，避免重复日志
    root_logger.handlers = []
    root_logger.addHandler(rotating_handler)
    root_logger.addHandler(console_handler)
    
    # 创建应用日志器
    app_logger = logging.getLogger('MyGameServer')
    app_logger.setLevel(logging.INFO)
    
    return app_logger

logger = setup_logging()


_DB_POOL: ThreadedConnectionPool | None = None


def _ensure_db_pool() -> ThreadedConnectionPool:
    global _DB_POOL
    with _DB_LOCK:
        if _DB_POOL is None:
            min_conn = int(os.getenv('DB_MIN_CONN', '1'))
            max_conn = int(os.getenv('DB_MAX_CONN', '10'))
            _DB_POOL = ThreadedConnectionPool(minconn=min_conn, maxconn=max_conn, **DB_CONFIG)
            logger.info(f"数据库连接池已创建: min={min_conn}, max={max_conn}")
    return _DB_POOL


class _PooledConnection:
    """包装连接，使 close() 归还到连接池。"""
    def __init__(self, pool: ThreadedConnectionPool, conn):
        self._pool = pool
        self._conn = conn

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        if self._conn is not None:
            try:
                self._pool.putconn(self._conn)
            finally:
                self._conn = None


def get_db_connection():
    """获取数据库连接（连接池）。"""
    pool = _ensure_db_pool()
    conn = pool.getconn()
    return _PooledConnection(pool, conn)


def init_database():
    """初始化数据库表结构"""
    logger.info("正在初始化数据库...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 创建订单状态枚举类型
            cursor.execute("""
                DO $$ BEGIN
                    CREATE TYPE order_status AS ENUM ('pending', 'approved', 'rejected');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """)
            
            # 创建订单表
            cursor.execute("""
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
            """)
            
            # 创建发道具表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS grants (
                    id         BIGSERIAL PRIMARY KEY,
                    user_id    VARCHAR(64) NOT NULL,
                    item_id    VARCHAR(64) NOT NULL,
                    count      INT NOT NULL DEFAULT 1,
                    reason     VARCHAR(255),
                    extra      JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            
            conn.commit()
            logger.info("数据库初始化成功")
    except Exception as e:
        logger.error(f"数据库初始化错误: {e}")
        conn.rollback()
    finally:
        conn.close()


def db_create_or_upsert_order(order_id, client_order_no, user_id, amount, raw_json):
    """创建或更新订单（幂等）"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if client_order_no:
                # 使用 client_order_no 作为幂等键
                cursor.execute("""
                    INSERT INTO orders (order_id, client_order_no, user_id, amount, status, raw_json)
                    VALUES (%s, %s, %s, %s, 'pending', %s::jsonb)
                    ON CONFLICT ON CONSTRAINT uk_client_order_no
                    DO UPDATE SET raw_json = EXCLUDED.raw_json, updated_at = NOW();
                """, (order_id, client_order_no, user_id, amount, raw_json))
            else:
                # 使用 order_id 作为幂等键
                cursor.execute("""
                    INSERT INTO orders (order_id, user_id, amount, status, raw_json)
                    VALUES (%s, %s, %s, 'pending', %s::jsonb)
                    ON CONFLICT ON CONSTRAINT uk_order_id
                    DO UPDATE SET raw_json = EXCLUDED.raw_json, updated_at = NOW();
                """, (order_id, user_id, amount, raw_json))
            conn.commit()
    except Exception as e:
        logger.error(f"创建订单错误: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def db_get_order(order_id):
    """获取订单信息"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT order_id, client_order_no, user_id, amount, status, 
                       raw_json, created_at, updated_at
                FROM orders WHERE order_id = %s
            """, (order_id,))
            result = cursor.fetchone()
            if result:
                # 转换为字典格式
                return dict(result)
            return None
    except Exception as e:
        logger.error(f"获取订单错误: {e}")
        return None
    finally:
        conn.close()


def db_update_order_status(order_id, status):
    """更新订单状态"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE orders SET status = %s, updated_at = NOW()
                WHERE order_id = %s AND status = 'pending'
            """, (status, order_id))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"更新订单状态错误: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def db_list_orders(status=None, limit=100):
    """获取订单列表"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if status:
                cursor.execute("""
                    SELECT order_id, client_order_no, user_id, amount, status, 
                           raw_json, created_at, updated_at
                    FROM orders WHERE status = %s
                    ORDER BY created_at DESC LIMIT %s
                """, (status, limit))
            else:
                cursor.execute("""
                    SELECT order_id, client_order_no, user_id, amount, status, 
                           raw_json, created_at, updated_at
                    FROM orders
                    ORDER BY created_at DESC LIMIT %s
                """, (limit,))
            
            results = cursor.fetchall()
            return [dict(row) for row in results]
    except Exception as e:
        logger.error(f"获取订单列表错误: {e}")
        return []
    finally:
        conn.close()


def db_insert_grant(user_id, item_id, count, reason, extra=None):
    """插入发道具记录"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO grants (user_id, item_id, count, reason, extra)
                VALUES (%s, %s, %s, %s, %s::jsonb)
            """, (user_id, item_id, count, reason, json.dumps(extra) if extra else None))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"插入发道具记录错误: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


# 安全响应头
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'no-referrer'
    # 如果部署在 HTTPS，可开启 HSTS：
    # response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
    return response


_RATE_BUCKET = {}

def _rate_limit(key: str, limit: int, per_seconds: int) -> bool:
    now = int(time.time())
    window = now // per_seconds
    k = f"{key}:{window}"
    count = _RATE_BUCKET.get(k, 0) + 1
    _RATE_BUCKET[k] = count
    prev_k = f"{key}:{window-1}"
    _RATE_BUCKET.pop(prev_k, None)
    return count <= limit


def rate_limited(limit: int = 60, per_seconds: int = 60):
    def _decorator(fn):
        @wraps(fn)
        def _wrapped(*args, **kwargs):
            ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
            key = f"{fn.__name__}:{ip}"
            if not _rate_limit(key, limit, per_seconds):
                return jsonify({'code': 429, 'msg': 'too many requests'}), 429
            return fn(*args, **kwargs)
        return _wrapped
    return _decorator

def _extract_admin_token(req) -> str:
    auth = req.headers.get('Authorization', '')
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()
    token = req.cookies.get('admin_token')
    if token:
        return token
    token = req.args.get('token')
    if token:
        return token
    try:
        body = req.get_json(silent=True) or {}
        if isinstance(body, dict) and 'token' in body:
            return str(body.get('token') or '')
    except Exception:
        pass
    return ''


def admin_required(fn):
    @wraps(fn)
    def _wrapped(*args, **kwargs):
        # Basic 认证（可选）
        if SECURITY_CONFIG.get('enable_basic', False):
            auth = request.authorization
            if not auth:
                return (jsonify({'code': 401, 'msg': 'basic auth required'}), 401, {'WWW-Authenticate': 'Basic realm="admin"'})
            if not (auth.username == (SECURITY_CONFIG.get('admin_user') or '') and auth.password == (SECURITY_CONFIG.get('admin_pass') or '')):
                return (jsonify({'code': 401, 'msg': 'invalid basic auth'}), 401, {'WWW-Authenticate': 'Basic realm="admin"'})
        # Bearer 认证（可选）
        if SECURITY_CONFIG.get('enable_auth', False):
            expected = (SECURITY_CONFIG.get('admin_token') or '').strip()
            provided = _extract_admin_token(request)
            if not (expected and provided and provided == expected):
                return jsonify({'code': 401, 'msg': 'unauthorized'}), 401
        return fn(*args, **kwargs)
    return _wrapped


def ensure_layout() -> None:
    (RESOURCE_V1).mkdir(parents=True, exist_ok=True)
    (REMOTE_DIR).mkdir(parents=True, exist_ok=True)


def try_seed_from_apk_assets() -> None:
    """首次运行时从 APK 解包目录同步 remote 资源（如存在）。"""
    src = ROOT_DIR.parent / 'assets' / 'remote'
    if src.exists():
        # 如果 remote 目录为空，则同步一次
        try:
            empty = True
            for _ in REMOTE_DIR.iterdir():
                empty = False
                break
            if empty:
                shutil.copytree(src, REMOTE_DIR, dirs_exist_ok=True)
        except Exception:
            pass


def _now() -> int:
    return int(time.time())


def _create_order(raw_json: str, parsed: dict) -> dict:
    order_id = uuid.uuid4().hex
    ts = _now()
    
    # 提取金额
    amount = None
    for k in ('amount', 'price', 'money', 'fee'):
        v = parsed.get(k)
        if isinstance(v, (int, float, str)):
            try:
                amount = float(v)
                break
            except Exception:
                pass
    
    # 提取用户ID和客户端订单号
    user_id = parsed.get('userId') or parsed.get('user_id') or parsed.get('user')
    client_order_no = parsed.get('orderNo') or parsed.get('order_no') or parsed.get('clientOrderId')
    
    # 保存到数据库
    db_create_or_upsert_order(order_id, client_order_no, user_id, amount, raw_json)
    
    # 返回订单信息
    order = {
        'orderId': order_id,
        'status': 'pending',
        'createdAt': ts,
        'raw': raw_json,
        'payload': parsed,
    }
    if amount is not None:
        order['amount'] = amount
    
    return order


def _set_order_status(order_id: str, status: str, reason: str = '') -> dict | None:
    success = db_update_order_status(order_id, status)
    if not success:
        return None
    
    order = db_get_order(order_id)
    if order:
        # 转换为兼容格式
        return {
            'orderId': order['order_id'],
            'status': order['status'],
            'createdAt': int(order['created_at'].timestamp()),
            'updatedAt': int(order['updated_at'].timestamp()),
            'raw': order['raw_json'],
            'amount': float(order['amount']) if order['amount'] else None
        }
    return None


def ensure_qr_placeholder() -> None:
    # 生成占位二维码图片（1x1 像素，浏览器会被拉伸显示）
    qrp = MYGAME_ROOT / 'qr.png'
    if qrp.exists():
        return
    MYGAME_ROOT.mkdir(parents=True, exist_ok=True)
    # 1x1 PNG 像素（黑色）
    b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAuMB9oEJ2mQAAAAASUVORK5CYII='
    try:
        qrp.write_bytes(base64.b64decode(b64))
    except Exception:
        pass


@app.get('/')
def index():
    return 'MyGameServer is running! <a href="/admin">管理后台</a>'

@app.get('/admin')
def admin_panel():
    """管理后台界面：在启用鉴权时支持以 token 参数访问并写入 Cookie。"""
    if SECURITY_CONFIG.get('enable_basic', False):
        auth = request.authorization
        if not auth or not (auth.username == (SECURITY_CONFIG.get('admin_user') or '') and auth.password == (SECURITY_CONFIG.get('admin_pass') or '')):
            return (jsonify({'code': 401, 'msg': 'basic auth required'}), 401, {'WWW-Authenticate': 'Basic realm="admin"'})
    if SECURITY_CONFIG.get('enable_auth', False):
        token = _extract_admin_token(request)
        expected = (SECURITY_CONFIG.get('admin_token') or '').strip()
        if not (expected and token == expected):
            # 简易登录页：输入 token 写入 cookie
            return (
                '<!doctype html><meta charset="utf-8" />'
                '<title>管理员登录</title>'
                '<div style="max-width:420px;margin:80px auto;font-family:system-ui;">'
                '<h3>请输入管理员令牌</h3>'
                '<input id="t" style="width:100%;padding:8px;font-size:14px;" placeholder="ADMIN_TOKEN" />'
                '<button style="margin-top:12px;padding:8px 12px;" onclick="(function(){'
                'var v=document.getElementById(\'t\').value;'
                'document.cookie=\'admin_token=\'+encodeURIComponent(v)+\'; path=/\';'
                'location.href=\'/admin\';'
                '})()">登录</button>'
                '</div>'
            )
    try:
        with open(ROOT_DIR / 'admin.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return '管理界面文件未找到', 404


@app.get('/healthz')
def health():
    return jsonify({"status": "ok", "ts": int(time.time())})


@app.get('/readyz')
def ready():
    ok = (RESOURCE_V1 / 'version.manifest').exists() and (RESOURCE_V1 / 'project.manifest').exists()
    return (jsonify({"ready": ok}), 200 if ok else 503)


# 静态：/mygame/... → wwwroot/mygame/...
@app.get('/mygame/<path:filepath>')
def serve_static(filepath: str):
    base = MYGAME_ROOT
    try:
        resp = send_from_directory(base, filepath)
        if 'resource/' in filepath:
            resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        else:
            resp.headers['Cache-Control'] = 'public, max-age=300'
        return resp
    except Exception:
        abort(404)


# API 示例：登录
@app.post('/api/login')
def api_login():
    payload = {}
    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        pass
    user = payload.get('user', 'guest')
    token = f'token-{user}-{int(time.time())}'
    return jsonify({"code": 0, "msg": "ok", "data": {"token": token, "user": user}})


# API 示例：战斗开始
@app.post('/api/battle/start')
def api_battle_start():
    return jsonify({
        "code": 0,
        "msg": "ok",
        "data": {"result": "victory", "exp": 100, "gold": 50}
    })


# 上报接口示例
@app.post('/report')
def api_report():
    try:
        # 请求体大小限制
        if request.content_length and int(request.content_length) > int(REQUEST_CONFIG.get('max_body_bytes', 1_000_000)):
            return jsonify({'code': 413, 'msg': 'payload too large'}), 413
        data = request.get_json(force=True, silent=True) or {}
        (ROOT_DIR / 'logs').mkdir(exist_ok=True)
        with (ROOT_DIR / 'logs' / 'client.log').open('a', encoding='utf-8') as f:
            f.write(json.dumps({"ts": int(time.time()), "data": data}, ensure_ascii=False) + '\n')
    except Exception:
        pass
    return jsonify({"code": 0, "msg": "received"})


# 支付提交：客户端所有支付请求统一提交到此
@app.post('/pay/submit')
@rate_limited(60, 60)
def pay_submit():
    raw = request.get_data(as_text=True) or ''
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception:
        parsed = {}
    order = _create_order(raw, parsed)
    # 前台提示：请扫码支付 N 元，展示假二维码页面
    amount = order.get('amount')
    tips = f"请扫码支付{int(amount) if amount and float(amount).is_integer() else amount}元" if amount is not None else "请扫码完成支付"
    qr_page = f"/pay/qr/{order['orderId']}"
    return jsonify({'code': 0, 'msg': 'accepted', 'data': {
        'orderId': order['orderId'], 'status': order['status'], 'qrPage': qr_page, 'tips': tips
    }})


# 支付状态查询
@app.get('/pay/status')
@rate_limited(120, 60)
def pay_status():
    order_id = request.args.get('orderId', '')
    order = db_get_order(order_id)
    if not order:
        return jsonify({'code': 404, 'msg': 'order not found'}), 404
    
    # 转换为兼容格式
    result = {
        'orderId': order['order_id'],
        'status': order['status'],
        'createdAt': int(order['created_at'].timestamp()),
        'updatedAt': int(order['updated_at'].timestamp()),
        'raw': order['raw_json'],
        'amount': float(order['amount']) if order['amount'] else None
    }
    return jsonify({'code': 0, 'msg': 'ok', 'data': result})


# 后台：支付审核（approve/reject）
@app.post('/admin/pay/review')
@admin_required
@rate_limited(120, 60)
def admin_pay_review():
    body = request.get_json(force=True, silent=True) or {}
    order_id = body.get('orderId', '')
    action = (body.get('action', '') or '').lower()
    if action not in ('approve', 'reject'):
        return jsonify({'code': 400, 'msg': 'invalid action'}), 400
    
    status = 'approved' if action == 'approve' else 'rejected'
    order = _set_order_status(order_id, status)
    if not order:
        return jsonify({'code': 404, 'msg': 'order not found'}), 404
    return jsonify({'code': 0, 'msg': 'ok', 'data': order})


# 后台：支付列表
@app.get('/admin/pay/list')
@admin_required
@rate_limited(120, 60)
def admin_pay_list():
    status = request.args.get('status')
    items = db_list_orders(status=status)
    
    # 转换为兼容格式
    result = []
    for item in items:
        result.append({
            'orderId': item['order_id'],
            'status': item['status'],
            'createdAt': int(item['created_at'].timestamp()),
            'updatedAt': int(item['updated_at'].timestamp()),
            'raw': item['raw_json'],
            'amount': float(item['amount']) if item['amount'] else None,
            'userId': item['user_id'],
            'clientOrderNo': item['client_order_no']
        })
    
    return jsonify({'code': 0, 'msg': 'ok', 'data': result})


# 后台：给账号发道具
@app.post('/admin/grant-item')
@admin_required
@rate_limited(60, 60)
def admin_grant_item():
    body = request.get_json(force=True, silent=True) or {}
    user = body.get('user') or ''
    item_id = body.get('itemId') or ''
    count = int(body.get('count') or 1)
    reason = body.get('reason') or ''
    extra = body.get('extra')
    # 简易幂等：如果传入 idempotencyKey，则在一天窗口内忽略重复
    idem = (body.get('idempotencyKey') or '').strip()
    
    if not user or not item_id:
        return jsonify({'code': 400, 'msg': 'user and itemId required'}), 400
    
    # 保存到数据库（可根据 idempotencyKey 做应用层去重）
    if idem:
        # 读取当天是否已有相同幂等键记录（简单方案：日志文件或查询 grants 最近一条）
        # 为保持实现简洁，这里直接执行插入；生产可加 grants(idempotency_key text) 唯一约束
        pass
    success = db_insert_grant(user, item_id, count, reason, extra)
    if not success:
        return jsonify({'code': 500, 'msg': 'database error'}), 500
    
    return jsonify({'code': 0, 'msg': 'granted'})


# 假二维码页面（前台可直接打开此地址展示）
@app.get('/pay/qr/<order_id>')
def pay_qr(order_id: str):
    order = db_get_order(order_id)
    if not order:
        return '<html><meta charset="utf-8"><body>订单不存在</body></html>', 404
    
    amount = order.get('amount')
    amount_text = f"{int(amount) if amount and float(amount).is_integer() else amount}元" if amount is not None else ""
    html = f'''<!doctype html>
<html><head><meta charset="utf-8"><title>扫码支付</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Noto Sans,Helvetica,Arial; text-align:center; padding:24px;}}</style>
</head><body>
  <h2>请扫码支付{amount_text}</h2>
  <img src="/mygame/qr.png" style="width:240px;height:240px;image-rendering:pixelated;border:8px solid #eee;border-radius:8px;" alt="QR"/>
  <p>订单号：{order_id}</p>
  <p>支付完成后，请等待后台审核通过</p>
</body></html>'''
    return html


def ensure_default_manifests() -> None:
    """若未提供，则生成占位 manifest，避免 404。"""
    version_path = RESOURCE_V1 / 'version.manifest'
    project_path = RESOURCE_V1 / 'project.manifest'
    # 根据配置拼接热更资源基础地址
    try:
        from config import GAME_CONFIG
        assets_server = GAME_CONFIG.get('assets_server', 'http://127.0.0.1:8000/mygame/')
    except Exception:
        assets_server = 'http://127.0.0.1:8000/mygame/'
    if not assets_server.endswith('/'):
        assets_server += '/'
    base = assets_server + 'resource/v1'
    version = {
        "packageUrl": base,
        "remoteVersionUrl": f"{base}/version.manifest",
        "remoteManifestUrl": f"{base}/project.manifest",
        "version": "1.0.0",
        "assets": {},
        "searchPaths": []
    }
    project = version.copy()
    try:
        if not version_path.exists():
            version_path.write_text(json.dumps(version, ensure_ascii=False, indent=2), encoding='utf-8')
        if not project_path.exists():
            project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


if __name__ == '__main__':
    # 初始化数据库
    init_database()
    
    ensure_layout()
    try_seed_from_apk_assets()
    ensure_default_manifests()
    ensure_qr_placeholder()
    # 启动服务器
    logger.info(f"服务器启动在 {SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
    app.run(
        host=SERVER_CONFIG['host'], 
        port=SERVER_CONFIG['port'], 
        debug=SERVER_CONFIG['debug']
    )