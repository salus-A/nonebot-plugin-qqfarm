"""
Token 管理模块
"""
import secrets
from typing import Optional, Dict, Any
from nonebot.log import logger

async def init_token_table(db_pool):
    """初始化 token 表"""
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_tokens (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        username VARCHAR(50) NOT NULL UNIQUE,
                        token VARCHAR(64) NOT NULL UNIQUE,
                        endpoint VARCHAR(100) NOT NULL UNIQUE,
                        qq BIGINT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used TIMESTAMP NULL,
                        INDEX idx_token (token),
                        INDEX idx_username (username),
                        INDEX idx_qq (qq)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                logger.info("Token表已确认")
    except Exception as e:
        logger.error(f"创建token表失败: {e}")

def generate_token() -> str:
    """生成随机token"""
    return secrets.token_hex(16)

def generate_endpoint(token: str) -> str:
    """根据token生成端点（取前8位）"""
    return token[:8]

async def create_token(db_pool, username: str, qq: int) -> Optional[Dict[str, str]]:
    """为用户创建token"""
    if not db_pool:
        return None
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 检查是否已有token
                await cur.execute(
                    "SELECT token, endpoint FROM user_tokens WHERE username = %s",
                    (username,)
                )
                existing = await cur.fetchone()
                if existing:
                    return {"token": existing[0], "endpoint": existing[1]}
                
                # 生成新token
                token = generate_token()
                endpoint = generate_endpoint(token)
                
                # 确保端点唯一
                while True:
                    await cur.execute(
                        "SELECT 1 FROM user_tokens WHERE endpoint = %s",
                        (endpoint,)
                    )
                    if not await cur.fetchone():
                        break
                    token = generate_token()
                    endpoint = generate_endpoint(token)
                
                # 插入数据库
                await cur.execute("""
                    INSERT INTO user_tokens (username, token, endpoint, qq)
                    VALUES (%s, %s, %s, %s)
                """, (username, token, endpoint, qq))
                
                return {"token": token, "endpoint": endpoint}
    except Exception as e:
        logger.error(f"创建token失败: {e}")
        return None

async def verify_endpoint(db_pool, endpoint: str) -> Optional[Dict[str, Any]]:
    """通过端点验证，返回用户信息"""
    if not db_pool:
        return None
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT username, qq, token, endpoint
                    FROM user_tokens WHERE endpoint = %s
                """, (endpoint,))
                row = await cur.fetchone()
                if row:
                    # 更新最后使用时间
                    await cur.execute("""
                        UPDATE user_tokens SET last_used = NOW()
                        WHERE endpoint = %s
                    """, (endpoint,))
                    return {
                        "username": row[0],
                        "qq": row[1],
                        "token": row[2],
                        "endpoint": row[3]
                    }
                return None
    except Exception as e:
        logger.error(f"验证端点失败: {e}")
        return None

async def delete_token(db_pool, username: str) -> bool:
    """删除用户的token"""
    if not db_pool:
        return False
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM user_tokens WHERE username = %s",
                    (username,)
                )
                return True
    except Exception as e:
        logger.error(f"删除token失败: {e}")
        return False
