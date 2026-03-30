"""
QQ农场Webhook模块 - 支持多群版本
"""
import re
import asyncio
from nonebot import get_driver, get_bot, on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment
from nonebot.log import logger
from fastapi import APIRouter, Request

from .token_manager import init_token_table, create_token, verify_endpoint, delete_token

# 获取配置
global_config = get_driver().config

# 支持多个默认群：可以是单个群号，也可以是群号列表
default_group_config = getattr(global_config, "qqfarm_default_group", "1060330308")
if isinstance(default_group_config, str):
    if ',' in default_group_config:
        DEFAULT_GROUPS = [int(g.strip()) for g in default_group_config.split(',') if g.strip().isdigit()]
    else:
        DEFAULT_GROUPS = [int(default_group_config)] if default_group_config.isdigit() else []
elif isinstance(default_group_config, int):
    DEFAULT_GROUPS = [default_group_config]
elif isinstance(default_group_config, list):
    DEFAULT_GROUPS = [int(g) for g in default_group_config if str(g).isdigit()]
else:
    DEFAULT_GROUPS = []

if not DEFAULT_GROUPS:
    DEFAULT_GROUPS = [1060330308]

WEBHOOK_URL = getattr(global_config, "qqfarm_webhook_url", "http://localhost:6399")

logger.info(f"配置的默认群列表: {DEFAULT_GROUPS}")

try:
    from . import db_pool, get_current_username
except ImportError:
    db_pool = None
    async def get_current_username(qq):
        return None

async def get_qq_by_account_id(account_id: int):
    if not db_pool:
        return None
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT ub.qq FROM accounts a
                    JOIN user_bindings ub ON a.username = ub.username
                    WHERE a.id = %s
                """, (account_id,))
                row = await cur.fetchone()
                return row[0] if row else None
    except Exception as e:
        logger.error(f"查询账号绑定失败: {e}")
        return None

def extract_account_id(content: str) -> str:
    match = re.search(r'账号:\s*(\d+)', content)
    return match.group(1) if match else None

class WebhookHandler:
    def __init__(self):
        asyncio.create_task(init_token_table(db_pool))
        self._setup_routes()
        logger.info(f"Webhook地址配置: {WEBHOOK_URL}")
        logger.info(f"默认群列表: {DEFAULT_GROUPS}")

    def _setup_routes(self):
        driver = get_driver()
        router = APIRouter()

        @router.post("/report")
        async def report_webhook(request: Request):
            data = await request.json()
            title = data.get('title', '')
            content = data.get('content', '')
            account_id = extract_account_id(content)
            if not account_id:
                return {"code": 400, "message": "无法提取账号ID"}
            target_qq = await get_qq_by_account_id(int(account_id))
            if not target_qq:
                return {"code": 404, "message": f"账号 {account_id} 未绑定QQ"}
            message = f"{title}\n\n{content}"
            bot = get_bot()
            try:
                await bot.send_private_msg(user_id=target_qq, message=message)
                results = ["private"]
                group_success = []
                for group_id in DEFAULT_GROUPS:
                    try:
                        group_msg = MessageSegment.at(target_qq) + MessageSegment.text(f"\n{message}")
                        await bot.send_group_msg(group_id=group_id, message=group_msg)
                        group_success.append(str(group_id))
                        logger.info(f"已发送群消息到 {group_id}，艾特 {target_qq}")
                    except Exception as e:
                        logger.error(f"发送到群 {group_id} 失败: {e}")
                if group_success:
                    results.append(f"groups:{','.join(group_success)}")
                return {"code": 200, "message": f"已发送到 {results}"}
            except Exception as e:
                logger.error(f"发送失败: {e}")
                return {"code": 500, "message": str(e)}

        @router.post("/{endpoint}/send")
        async def send_with_endpoint(endpoint: str, request: Request):
            user_info = await verify_endpoint(db_pool, endpoint)
            if not user_info:
                return {"code": 403, "message": "无效的端点"}
            data = await request.json()
            title = data.get('title', '')
            content = data.get('content', '')
            account_id = extract_account_id(content)
            target_qq = await get_qq_by_account_id(int(account_id)) if account_id else None
            message = f"{title}\n\n{content}"
            bot = get_bot()
            results = []
            if target_qq:
                await bot.send_private_msg(user_id=target_qq, message=message)
                results.append("private")
            group_success = []
            for group_id in DEFAULT_GROUPS:
                try:
                    if target_qq:
                        group_msg = MessageSegment.at(target_qq) + MessageSegment.text(f"\n{message}")
                    else:
                        group_msg = message
                    await bot.send_group_msg(group_id=group_id, message=group_msg)
                    group_success.append(str(group_id))
                    logger.info(f"已发送群消息到 {group_id}" + (f"，艾特 {target_qq}" if target_qq else ""))
                except Exception as e:
                    logger.error(f"发送到群 {group_id} 失败: {e}")
            if group_success:
                results.append(f"groups:{','.join(group_success)}")
            return {"code": 200, "message": f"已发送到 {results}"}

        if hasattr(driver, 'server_app') and driver.server_app:
            driver.server_app.include_router(router, prefix="")
            logger.info("动态端点已注册: /{endpoint}/send, 统一端点: /report")
        else:
            logger.warning("未找到FastAPI应用")

# ========== QQ命令 ==========
async def check_private(event: MessageEvent):
    if event.message_type != "private":
        await get_bot().send_private_msg(user_id=int(event.user_id), message="此命令仅支持私聊")
        return False
    return True

apply_cmd = on_command("申请端点", priority=10, block=True)

@apply_cmd.handle()
async def handle_apply(event: MessageEvent):
    if not await check_private(event):
        return
    user_qq = int(event.user_id)
    username = await get_current_username(user_qq)
    if not username:
        await get_bot().send_private_msg(user_id=user_qq, message="请先绑定农场账号\n使用: 绑定农场账号 <用户名>")
        return
    token_info = await create_token(db_pool, username, user_qq)
    if token_info:
        endpoint = token_info['endpoint']
        token = token_info['token']
        group_list = "\n".join([f"  • {g}" for g in DEFAULT_GROUPS])
        await get_bot().send_private_msg(
            user_id=user_qq,
            message=(
                f"✅ 申请成功！\n\n"
                f"端点: {endpoint}\n"
                f"Token: {token}\n\n"
                f"使用地址:\n"
                f"POST {WEBHOOK_URL}/{endpoint}/send\n\n"
                f"统一地址:\n"
                f"POST {WEBHOOK_URL}/report\n\n"
                f"通知将发送到以下群:\n{group_list}"
            )
        )
        logger.info(f"用户 {user_qq} 申请端点成功，endpoint={endpoint}")
    else:
        await get_bot().send_private_msg(user_id=user_qq, message="申请失败，请稍后重试")

my_cmd = on_command("我的端点", priority=10, block=True)

@my_cmd.handle()
async def handle_my(event: MessageEvent):
    if not await check_private(event):
        return
    user_qq = int(event.user_id)
    username = await get_current_username(user_qq)
    if not username:
        await get_bot().send_private_msg(user_id=user_qq, message="请先绑定农场账号")
        return
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT token, endpoint, created_at, last_used FROM user_tokens WHERE username=%s", (username,))
            row = await cur.fetchone()
            if row:
                token, endpoint, created_at, last_used = row
                last_used_str = last_used.strftime("%Y-%m-%d %H:%M:%S") if last_used else "从未使用"
                group_list = "\n".join([f"  • {g}" for g in DEFAULT_GROUPS])
                await get_bot().send_private_msg(
                    user_id=user_qq,
                    message=(
                        f"📋 你的端点信息\n\n"
                        f"端点: {endpoint}\n"
                        f"Token: {token}\n"
                        f"创建时间: {created_at}\n"
                        f"最后使用: {last_used_str}\n\n"
                        f"通知将发送到以下群:\n{group_list}"
                    )
                )
            else:
                await get_bot().send_private_msg(user_id=user_qq, message="未申请端点\n使用: 申请端点")

reset_cmd = on_command("重置端点", priority=10, block=True)

@reset_cmd.handle()
async def handle_reset(event: MessageEvent):
    if not await check_private(event):
        return
    user_qq = int(event.user_id)
    username = await get_current_username(user_qq)
    if not username:
        await get_bot().send_private_msg(user_id=user_qq, message="请先绑定农场账号")
        return
    await delete_token(db_pool, username)
    token_info = await create_token(db_pool, username, user_qq)
    if token_info:
        group_list = "\n".join([f"  • {g}" for g in DEFAULT_GROUPS])
        await get_bot().send_private_msg(
            user_id=user_qq,
            message=(
                f"✅ 重置成功！\n\n"
                f"新端点: {token_info['endpoint']}\n"
                f"新Token: {token_info['token']}\n\n"
                f"通知将发送到以下群:\n{group_list}"
            )
        )
    else:
        await get_bot().send_private_msg(user_id=user_qq, message="重置失败")

test_cmd = on_command("测试", priority=1, block=True)

@test_cmd.handle()
async def handle_test(event: MessageEvent):
    await get_bot().send_private_msg(user_id=int(event.user_id), message="测试成功")

def init_webhook():
    try:
        handler = WebhookHandler()
        logger.info("Webhook初始化完成")
    except Exception as e:
        logger.error(f"Webhook初始化失败: {e}")