from nonebot import get_driver, on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.log import logger
from nonebot.exception import FinishedException
from typing import Optional, Set, List, Tuple, Dict, Any

import asyncio
import time
import json
import os

import asyncmy
from asyncmy import Pool

from .api_client import QQFarmAPI

# 插件元数据
__plugin_meta__ = PluginMetadata(
    name="QQ农场助手",
    description="QQ农场助手插件，支持账号管理、好友操作、农场操作，并自动通知离线状态",
    usage="""
    基础指令：
    绑定农场账号 <用户名> - 绑定当前 QQ 与农场用户名
    我的农场账号 [用户名] - 查看指定用户名下的农场账号
    农场状态 - 查看自己绑定的农场账号状态
    农场详情 <账号ID> - 查看指定账号详情
    启动农场 <账号ID> - 启动农场账号
    停止农场 <账号ID> - 停止农场账号
    更新农场Code <账号ID> <Code> - 更新账号Code并自动启动
    农场备注 <账号ID> <备注内容> - 设置账号备注
    农场日志 <账号ID> [数量] - 查看账号日志
    添加农场账号 <uin> <code> [昵称] - 添加新农场账号并自动启动
    删除农场账号 <账号ID> - 删除自己的农场账号

    管理员指令：
    管理账号列表 - 查看所有农场账号
    添加管理员 <QQ号> - 添加管理员
    删除管理员 <QQ号> - 删除管理员
    绑定用户 <QQ号> <用户名> - 为指定QQ绑定用户名
    解绑用户 <QQ号> - 解绑指定QQ的用户
    管理员启动农场 <账号ID> - 启动任意账号
    管理员停止农场 <账号ID> - 停止任意账号
    管理员更新农场Code <账号ID> <Code> - 更新任意账号Code并自动启动
    管理员农场备注 <账号ID> <备注> - 设置任意账号备注
    管理员农场日志 <账号ID> [数量] - 查看任意账号日志
    分配账号 <账号ID> <用户名> - 将账号分配给指定用户
    解绑QQ <QQ号> - 强制解除QQ与用户名的绑定
    农场统计 - 查看农场统计摘要

    全局指令：
    全局日志 [数量] - 查看全局日志
    农场帮助 [类别] - 显示帮助信息
    """,
    type="application",
    homepage="https://github.com/salus-A/nonebot-plugin-qqfarm",
    supported_adapters={"~onebot.v11"},
)

# ========== 配置读取（使用 NoneBot 全局配置）==========
global_config = get_driver().config

base_url = getattr(global_config, "nonebot_plugin_qqfarm_base_url", "") or ""
admin_password = getattr(global_config, "nonebot_plugin_qqfarm_admin_password", "") or ""
timeout = getattr(global_config, "nonebot_plugin_qqfarm_timeout", 30)
api_key = getattr(global_config, "nonebot_plugin_qqfarm_api_key", "") or ""
offline_check_interval = getattr(global_config, "nonebot_plugin_qqfarm_offline_check_interval", 60)

admin_qq = getattr(global_config, "nonebot_plugin_qqfarm_admin_qq", [])
initial_admins = admin_qq if isinstance(admin_qq, list) else []

db_config = getattr(global_config, "nonebot_plugin_qqfarm_database", {})
if not db_config:
    logger.warning("QQ农场插件：数据库配置缺失")

# ========== 全局变量 ==========
api: Optional[QQFarmAPI] = None
db_pool: Optional[Pool] = None
_offline_notify_task: Optional[asyncio.Task] = None
_offline_notified: Set[int] = set()
_admin_cache: Set[int] = set()


# ========== 初始化函数 ==========
async def init_api() -> bool:
    global api
    if not base_url:
        logger.warning("QQ农场插件：base_url 未配置")
        return False
    api = QQFarmAPI(base_url, admin_password, timeout, api_key)
    await api.ainit()
    if admin_password:
        ok = await api.login()
        if ok:
            logger.info("QQ农场插件：API 登录成功")
            return True
        else:
            logger.warning("QQ农场插件：API 登录失败")
            return False
    else:
        logger.warning("QQ农场插件：admin_password 未设置，无法登录")
        return False


async def init_db_pool() -> bool:
    global db_pool
    if not db_config:
        logger.warning("QQ农场插件：数据库配置缺失")
        return False
    try:
        db_pool = await asyncmy.create_pool(
            host=db_config.get("host", "localhost"),
            port=db_config.get("port", 3306),
            user=db_config.get("user", "qq_farm_user"),
            password=db_config.get("password", ""),
            db=db_config.get("database", "qq_farm_bot"),
            charset=db_config.get("charset", "utf8mb4"),
            autocommit=True,
            minsize=1,
            maxsize=5,
        )
        logger.info("QQ农场插件：数据库连接池初始化成功")
        return True
    except Exception as e:
        logger.error(f"QQ农场插件：数据库连接池初始化失败: {e}")
        return False


async def ensure_tables():
    """创建插件所需的新表，不修改现有表结构"""
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 管理员表
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS admins (
                        qq BIGINT PRIMARY KEY,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # 用户绑定表（QQ ↔ username）
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_bindings (
                        qq BIGINT PRIMARY KEY,
                        username VARCHAR(50) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY idx_username (username)
                    )
                """)
                # 账号备注表
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS account_remarks (
                        account_id INT PRIMARY KEY,
                        remark TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """)
                # 兼容旧版的 users 表结构（确保存在，但不依赖其 qq 字段）
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        username VARCHAR(50) NOT NULL UNIQUE,
                        password_hash VARCHAR(255) NOT NULL,
                        role VARCHAR(20) DEFAULT 'user',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                logger.info("插件专用表结构已确认")
    except Exception as e:
        logger.error(f"创建插件专用表失败: {e}")


async def sync_initial_admins():
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                for qq in initial_admins:
                    await cur.execute(
                        "INSERT IGNORE INTO admins (qq) VALUES (%s)",
                        (qq,)
                    )
                    _admin_cache.add(qq)
        logger.info(f"已同步初始管理员: {initial_admins}")
    except Exception as e:
        logger.error(f"同步初始管理员失败: {e}")


# ========== 数据库辅助函数 ==========
async def is_admin(qq: int) -> bool:
    if not db_pool:
        return False
    if qq in _admin_cache:
        return True
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1 FROM admins WHERE qq = %s", (qq,))
                row = await cur.fetchone()
                if row:
                    _admin_cache.add(qq)
                    return True
        return False
    except Exception as e:
        logger.error(f"检查管理员权限失败: {e}")
        return False


async def get_current_username(qq: int) -> Optional[str]:
    """根据QQ号从 user_bindings 表获取绑定的用户名"""
    if not db_pool:
        return None
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT username FROM user_bindings WHERE qq = %s", (qq,))
                row = await cur.fetchone()
                return row[0] if row else None
    except Exception as e:
        logger.error(f"根据QQ查询用户名失败: {e}")
        return None


async def get_qq_by_username(username: str) -> Optional[int]:
    """根据用户名从 user_bindings 表获取绑定的QQ号"""
    if not db_pool:
        return None
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT qq FROM user_bindings WHERE username = %s", (username,))
                row = await cur.fetchone()
                if row and row[0]:
                    return row[0]
    except Exception as e:
        logger.error(f"根据用户名查询QQ失败: {e}")
    return None


async def check_account_ownership(qq: int, account_id: int) -> bool:
    if await is_admin(qq):
        return True
    username = await get_current_username(qq)
    if not username:
        return False
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id FROM accounts WHERE id = %s AND username = %s",
                    (account_id, username)
                )
                return await cur.fetchone() is not None
    except Exception as e:
        logger.error(f"检查账号所有权失败: {e}")
        return False


async def update_account_code(account_id: int, code: str):
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE accounts SET code = %s WHERE id = %s",
                    (code, account_id)
                )
    except Exception as e:
        logger.error(f"更新账号Code失败: {e}")


async def update_account_remark(account_id: int, remark: str):
    """将备注存入 account_remarks 表"""
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO account_remarks (account_id, remark) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE remark = %s",
                    (account_id, remark, remark)
                )
    except Exception as e:
        logger.error(f"更新账号备注失败: {e}")


async def get_account_remark(account_id: int) -> str:
    """从 account_remarks 表获取备注"""
    if not db_pool:
        return ""
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT remark FROM account_remarks WHERE account_id = %s", (account_id,))
                row = await cur.fetchone()
                return row[0] if row else ""
    except Exception as e:
        logger.error(f"获取账号备注失败: {e}")
        return ""


# ========== 在线状态判断 ==========
def is_account_online_from_data(acc: dict, current_time: int) -> bool:
    running = acc.get("running", False)
    uptime = acc.get("uptime", 0)
    last_status_at = acc.get("lastStatusAt", 0)
    is_recent = (current_time - last_status_at) < 60000
    return running and uptime > 10 and is_recent


async def get_accounts_with_online_status(accounts: List[dict]) -> List[Tuple[bool, dict]]:
    current_time = int(time.time() * 1000)
    result = []
    for acc in accounts:
        is_online = is_account_online_from_data(acc, current_time)
        result.append((is_online, acc))
    return result


# ========== 后台离线通知 ==========
async def offline_notify_loop():
    if not db_pool or not api:
        logger.warning("离线通知功能已禁用：数据库或API未就绪")
        return

    while True:
        try:
            await asyncio.sleep(offline_check_interval)

            accounts = await api.get_accounts()
            if not accounts:
                continue

            current_time = int(time.time() * 1000)
            for acc in accounts:
                acc_id = acc.get("id")
                username = acc.get("username", "")
                nick = acc.get("name", "")

                is_online = is_account_online_from_data(acc, current_time)

                user_qq = await get_qq_by_username(username)

                if not is_online and acc_id not in _offline_notified:
                    if not user_qq:
                        continue
                    msg = f"⚠️ 农场账号 {acc_id}（{nick or '无昵称'}）已离线，请检查。"
                    await send_private_message(user_qq, msg)
                    _offline_notified.add(acc_id)
                    logger.info(f"已向QQ {user_qq} 发送账号 {acc_id} 离线通知")

                elif is_online and acc_id in _offline_notified:
                    _offline_notified.discard(acc_id)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"离线通知循环错误: {e}")


async def send_private_message(user_qq: int, message: str):
    from nonebot import get_bot
    try:
        bot = get_bot()
        await bot.send_private_msg(user_id=user_qq, message=message)
        logger.info(f"私聊消息已发送给 {user_qq}: {message[:50]}...")
    except Exception as e:
        logger.error(f"发送私聊消息给 {user_qq} 失败: {e}")


# ========== 日志格式化 ==========
def format_log_line(log) -> str:
    try:
        if isinstance(log, dict):
            time_str = log.get("time", "")
            msg = log.get("msg", "")
            if not msg:
                msg = log.get("message", "")
            if not msg:
                msg = log.get("action", "")
            if not msg:
                msg = str(log)
        elif isinstance(log, (list, tuple)):
            time_str = log[0] if len(log) > 0 else ""
            msg = log[1] if len(log) > 1 else ""
        else:
            time_str = ""
            msg = str(log)
        return f"[{time_str}] {msg}"
    except Exception as e:
        logger.error(f"日志解析失败: {e}, 数据: {log}")
        return f"[解析失败] {str(log)}"


def format_uptime(seconds: int) -> str:
    if seconds <= 0:
        return "0秒"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}时{minutes}分{secs}秒"
    elif minutes > 0:
        return f"{minutes}分{secs}秒"
    else:
        return f"{secs}秒"


def format_timestamp(ts: int) -> str:
    """将毫秒时间戳格式化为本地时间字符串，若为空或0则返回'无'"""
    if not ts or ts <= 0:
        return "无"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts / 1000))
    except Exception:
        return "无效"


# ========== 指令处理 ==========
# 绑定农场账号
bind_account_cmd = on_command("绑定农场账号", aliases={"绑定农场"}, priority=10, block=True)


@bind_account_cmd.handle()
async def handle_bind_account(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("绑定农场账号"):
        plain_text = plain_text[len("绑定农场账号"):].strip()
    elif plain_text.startswith("绑定农场"):
        plain_text = plain_text[len("绑定农场"):].strip()
    username = plain_text
    if not username:
        await bind_account_cmd.finish("❌ 请提供要绑定的用户名，例如：绑定农场账号 jiongba")

    user_qq = int(event.user_id)

    if not db_pool:
        await bind_account_cmd.finish("❌ 数据库未连接")

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 确保 users 表中有该用户记录（不绑定QQ）
                await cur.execute("SELECT id FROM users WHERE username = %s", (username,))
                row = await cur.fetchone()
                if not row:
                    await cur.execute(
                        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                        (username, "", "user")
                    )
                # 存储绑定关系到 user_bindings 表
                await cur.execute(
                    "INSERT INTO user_bindings (qq, username) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE username = %s",
                    (user_qq, username, username)
                )
                await bind_account_cmd.finish(f"✅ 已绑定当前 QQ 与用户名：{username}")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"绑定用户失败: {e}")
        await bind_account_cmd.finish(f"❌ 绑定失败，请检查数据库连接或用户名是否正确")


# 我的农场账号
my_accounts_cmd = on_command("我的农场账号", aliases={"我的账号"}, priority=10, block=True)


@my_accounts_cmd.handle()
async def handle_my_accounts(event: MessageEvent):
    user_qq = int(event.user_id)
    is_admin_flag = await is_admin(user_qq)
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("我的农场账号"):
        plain_text = plain_text[len("我的农场账号"):].strip()
    elif plain_text.startswith("我的账号"):
        plain_text = plain_text[len("我的账号"):].strip()
    username_arg = plain_text

    if username_arg:
        if not is_admin_flag:
            await my_accounts_cmd.finish("❌ 权限不足，非管理员不能查看他人账号。")
        target_username = username_arg
    else:
        target_username = await get_current_username(user_qq)
        if not target_username:
            await my_accounts_cmd.finish("❌ 您尚未绑定农场账号，请先使用 /绑定农场账号 <用户名> 绑定，或直接输入用户名：我的农场账号 <用户名>")

    if not api:
        await my_accounts_cmd.finish("❌ API 未初始化")

    all_accounts = await api.get_accounts()
    if not all_accounts:
        await my_accounts_cmd.finish("❌ 未获取到账号列表")

    my_accounts = [acc for acc in all_accounts if acc.get("username") == target_username]
    if not my_accounts:
        await my_accounts_cmd.finish(f"📭 用户名 {target_username} 下没有农场账号")

    current_time = int(time.time() * 1000)
    online_status = {}
    for acc in all_accounts:
        online_status[str(acc.get("id"))] = is_account_online_from_data(acc, current_time)

    my_accounts.sort(key=lambda acc: online_status.get(str(acc.get("id")), False), reverse=True)

    lines = [f"📋 用户名 {target_username} 的农场账号", "----------------------------------------"]
    for idx, acc in enumerate(my_accounts, start=1):
        acc_id = acc.get("id")
        nick = acc.get("name", "无昵称")
        level = acc.get("level", 0)
        is_online = online_status.get(str(acc_id), False)
        status_icon = "🟢 运行中" if is_online else "🔴 已停止"
        remark = await get_account_remark(acc_id)
        uptime = acc.get("uptime", 0)
        uptime_str = format_uptime(uptime)
        lines.append(f"{idx}. ID: {acc_id} | 昵称: {nick} | 等级: {level} | 状态: {status_icon} | 运行: {uptime_str} | 备注: {remark}")
    lines.append("----------------------------------------")
    await my_accounts_cmd.finish("\n".join(lines))


# 农场状态
farm_status_cmd = on_command("农场状态", priority=10, block=True)


@farm_status_cmd.handle()
async def handle_farm_status(event: MessageEvent):
    user_qq = int(event.user_id)
    username = await get_current_username(user_qq)
    if not username:
        await farm_status_cmd.finish("❌ 您尚未绑定农场账号，请先使用 /绑定农场账号 <用户名> 绑定。")

    if not api:
        await farm_status_cmd.finish("❌ API 未初始化")

    all_accounts = await api.get_accounts()
    if not all_accounts:
        await farm_status_cmd.finish("❌ 未获取到账号列表")

    my_accounts = [acc for acc in all_accounts if acc.get("username") == username]
    if not my_accounts:
        await farm_status_cmd.finish(f"📭 用户名 {username} 下没有农场账号")

    current_time = int(time.time() * 1000)
    lines = ["🍀 我的农场账号状态", "----------------------------------------"]
    for acc in my_accounts:
        acc_id = acc.get("id")
        nick = acc.get("name", "无")
        level = acc.get("level", 0)
        is_online = is_account_online_from_data(acc, current_time)
        status_icon = "🟢 运行中" if is_online else "🔴 已停止"
        lines.append(f"ID: {acc_id} | 昵称: {nick} | 等级: {level} | 状态: {status_icon}")
    lines.append("----------------------------------------")
    await farm_status_cmd.finish("\n".join(lines))


# 农场详情
farm_detail_cmd = on_command("农场详情", priority=10, block=True)


@farm_detail_cmd.handle()
async def handle_farm_detail(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("农场详情"):
        plain_text = plain_text[len("农场详情"):].strip()
    if not plain_text.isdigit():
        await farm_detail_cmd.finish("账号ID必须为数字")
    account_id = int(plain_text)

    user_qq = int(event.user_id)

    if not api:
        await farm_detail_cmd.finish("❌ API 未初始化")

    accounts = await api.get_accounts()
    target = None
    for acc in accounts:
        if str(acc.get("id")) == str(account_id):
            target = acc
            break
    if not target:
        await farm_detail_cmd.finish(f"❌ 无法获取账号 {account_id} 详情")

    current_time = int(time.time() * 1000)
    is_online = is_account_online_from_data(target, current_time)

    gold = target.get("gold", 0)
    exp = target.get("exp", 0)
    friend_count = target.get("friendCount", 0)
    land_count = target.get("landCount", 0)
    uptime = target.get("uptime", 0)
    uptime_str = format_uptime(uptime)

    uin = target.get("uin", "无")
    qq = target.get("qq", "无")
    platform = target.get("platform", "无")
    coupon = target.get("coupon", 0)
    account_zone = target.get("accountZone", "无")
    last_online_at = format_timestamp(target.get("lastOnlineAt", 0))
    last_login_at = format_timestamp(target.get("lastLoginAt", 0))

    msg = [
        f"🍀 账号 {account_id} 详情",
        "----------------------------------------",
        f"昵称: {target.get('name', '未知')}",
        f"等级: {target.get('level', 0)}",
        f"金币: {gold}",
        f"经验: {exp}",
        f"券: {coupon}",
        f"好友数: {friend_count}",
        f"土地数: {land_count}",
        f"运行时间: {uptime_str}",
        f"状态: {'🟢 运行中' if is_online else '🔴 已停止'}",
        f"需要重新登录: {'是' if target.get('needsRelogin') else '否'}",
        f"是否禁用: {'是' if target.get('banned') else '否'}",
        "----------------------------------------",
        f"QQ号: {uin}",
        f"关联QQ: {qq}",
        f"平台: {platform}",
        f"区服: {account_zone}",
        f"最后在线: {last_online_at}",
        f"最后登录: {last_login_at}",
        "----------------------------------------",
    ]
    await farm_detail_cmd.finish("\n".join(msg))


# 启动农场
farm_start_cmd = on_command("启动农场", priority=10, block=True)


@farm_start_cmd.handle()
async def handle_farm_start(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("启动农场"):
        plain_text = plain_text[len("启动农场"):].strip()
    if not plain_text.isdigit():
        await farm_start_cmd.finish("账号ID必须为数字")
    account_id = int(plain_text)

    user_qq = int(event.user_id)
    if not await check_account_ownership(user_qq, account_id):
        await farm_start_cmd.finish(f"❌ 账号 {account_id} 不存在或不属于您。")

    if not api:
        await farm_start_cmd.finish("❌ API 未初始化")

    ok = await api.start_account(str(account_id))
    if ok:
        await farm_start_cmd.finish(f"✅ 账号 {account_id} 已启动")
    else:
        await farm_start_cmd.finish(f"❌ 启动账号 {account_id} 失败")


# 停止农场
farm_stop_cmd = on_command("停止农场", priority=10, block=True)


@farm_stop_cmd.handle()
async def handle_farm_stop(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("停止农场"):
        plain_text = plain_text[len("停止农场"):].strip()
    if not plain_text.isdigit():
        await farm_stop_cmd.finish("账号ID必须为数字")
    account_id = int(plain_text)

    user_qq = int(event.user_id)
    if not await check_account_ownership(user_qq, account_id):
        await farm_stop_cmd.finish(f"❌ 账号 {account_id} 不存在或不属于您。")

    if not api:
        await farm_stop_cmd.finish("❌ API 未初始化")

    ok = await api.stop_account(str(account_id))
    if ok:
        await farm_stop_cmd.finish(f"✅ 账号 {account_id} 已停止")
    else:
        await farm_stop_cmd.finish(f"❌ 停止账号 {account_id} 失败")


# 更新农场Code
update_code_cmd = on_command("更新农场Code", priority=10, block=True)


@update_code_cmd.handle()
async def handle_update_code(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("更新农场Code"):
        plain_text = plain_text[len("更新农场Code"):].strip()
    parts = plain_text.split()
    if len(parts) < 2:
        await update_code_cmd.finish("❌ 请提供账号ID和Code，例如：更新农场Code 123456 abcdef")
    account_id_str = parts[0]
    code = parts[1]
    if not account_id_str.isdigit():
        await update_code_cmd.finish("账号ID必须为数字")
    account_id = int(account_id_str)

    user_qq = int(event.user_id)
    if not await check_account_ownership(user_qq, account_id):
        await update_code_cmd.finish(f"❌ 账号 {account_id} 不存在或不属于您。")

    if not api:
        await update_code_cmd.finish("❌ API 未初始化")

    try:
        ok = await api.update_account_code(str(account_id), code)
        if not ok:
            await update_code_cmd.finish(f"❌ 更新账号 {account_id} Code 失败")

        await update_account_code(account_id, code)

        start_ok = await api.start_account(str(account_id))
        default_automation = {
    "farm": True,                     # 农场自动化总开关
    "farm_manage": True,              # 农场管理
    "farm_water": True,               # 浇水
    "farm_weed": True,                # 除草
    "farm_bug": True,                 # 除虫
    "farm_push": False,               # 推送（手动）
    "land_upgrade": False,            # 土地升级（手动）
    "friend": True,                   # 好友操作总开关
    "friend_help_exp_limit": True,    # 帮助经验限制（开启）
    "friend_steal": True,             # 偷菜
    "friend_help": True,              # 帮助（开启）
    "friend_bad": True,               # 不良好友（开启）
    "friend_auto_accept": False,      # 自动接受好友（手动）
    "task": True,                     # 任务（开启）
    "email": False,                   # 邮件（手动）
    "fertilizer_gift": False,         # 肥料礼物（手动）
    "fertilizer_buy": False,          # 购买肥料（手动）
    "sell": True,                     # 出售
    "free_gifts": True,               # 免费礼物（开启）
    "share_reward": True,             # 分享奖励（开启）
    "vip_gift": True,                 # VIP礼物（开启）
    "month_card": True,               # 月卡（开启）
    "open_server_gift": True,         # 开服礼物（开启）
    "fertilizer": "both",             # 肥料类型保持默认
}
        set_auto_ok = await api.set_automation(str(account_id), default_automation)
        if not set_auto_ok:
            logger.warning(f"更新 Code 后设置账号 {account_id} 默认自动化开关失败")

        if start_ok:
            await update_code_cmd.finish(f"✅ 账号 {account_id} Code 已更新，并已启动，自动化开关已应用。")
        else:
            await update_code_cmd.finish(f"✅ 账号 {account_id} Code 已更新，但启动失败，请手动启动，自动化开关已应用。")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"更新Code失败: {e}")
        await update_code_cmd.finish(f"❌ 更新失败：{str(e)}")


# 农场备注
set_remark_cmd = on_command("农场备注", priority=10, block=True)


@set_remark_cmd.handle()
async def handle_set_remark(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("农场备注"):
        plain_text = plain_text[len("农场备注"):].strip()
    parts = plain_text.split(maxsplit=1)
    if len(parts) < 2:
        await set_remark_cmd.finish("❌ 请提供账号ID和备注内容，例如：农场备注 123456 我的备注")
    account_id_str = parts[0]
    remark = parts[1].strip()
    if not account_id_str.isdigit():
        await set_remark_cmd.finish("账号ID必须为数字")
    account_id = int(account_id_str)

    user_qq = int(event.user_id)
    if not await check_account_ownership(user_qq, account_id):
        await set_remark_cmd.finish(f"❌ 账号 {account_id} 不存在或不属于您。")

    if not api:
        await set_remark_cmd.finish("❌ API 未初始化")

    ok = await api.set_account_remark(str(account_id), remark)
    if ok:
        await update_account_remark(account_id, remark)
        await set_remark_cmd.finish(f"✅ 账号 {account_id} 备注已更新为：{remark}")
    else:
        await set_remark_cmd.finish(f"❌ 更新备注失败")


# 农场日志
farm_logs_cmd = on_command("农场日志", priority=10, block=True)


@farm_logs_cmd.handle()
async def handle_farm_logs(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("农场日志"):
        plain_text = plain_text[len("农场日志"):].strip()
    parts = plain_text.split()
    if len(parts) < 1:
        await farm_logs_cmd.finish("❌ 请提供账号ID，例如：农场日志 123456 [数量]")
    account_id_str = parts[0]
    limit = 10
    if len(parts) >= 2 and parts[1].isdigit():
        limit = int(parts[1])
    if not account_id_str.isdigit():
        await farm_logs_cmd.finish("账号ID必须为数字")
    account_id = int(account_id_str)

    user_qq = int(event.user_id)
    if not await check_account_ownership(user_qq, account_id):
        await farm_logs_cmd.finish(f"❌ 账号 {account_id} 不存在或不属于您。")

    if not api:
        await farm_logs_cmd.finish("❌ API 未初始化")

    logs = await api.get_account_logs(str(account_id), limit * 3)
    if not logs:
        await farm_logs_cmd.finish(f"📭 账号 {account_id} 暂无日志")

    if isinstance(logs, dict):
        logs = logs.get("logs", [])
        if not isinstance(logs, list):
            logs = []

    filtered_logs = []
    for log in logs:
        try:
            if isinstance(log, dict):
                log_account_id = str(log.get("accountId", ""))
                msg = log.get("msg", "")
                if not msg:
                    msg = log.get("message", "")
                is_match = False
                if log_account_id == str(account_id):
                    is_match = True
                elif f"账号 {account_id}" in msg or f"账号{account_id}" in msg:
                    is_match = True
                elif str(account_id) in msg:
                    is_match = True
                if is_match:
                    filtered_logs.append(log)
            elif isinstance(log, (list, tuple)) and len(log) >= 3:
                if len(log) > 3 and str(log[3]) == str(account_id):
                    filtered_logs.append(log)
                elif str(account_id) in str(log[2]):
                    filtered_logs.append(log)
            else:
                filtered_logs.append(log)
        except Exception as e:
            logger.error(f"日志过滤失败: {e}, 数据: {log}")
            continue

    if not filtered_logs:
        await farm_logs_cmd.finish(f"📭 账号 {account_id} 暂无相关日志")

    lines = [f"📋 账号 {account_id} 最近日志", "----------------------------------------"]
    for log in filtered_logs[:limit]:
        lines.append(format_log_line(log))
    lines.append("----------------------------------------")
    await farm_logs_cmd.finish("\n".join(lines))


# 全局日志
global_logs_cmd = on_command("全局日志", priority=10, block=True)


@global_logs_cmd.handle()
async def handle_global_logs(event: MessageEvent):
    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await global_logs_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("全局日志"):
        plain_text = plain_text[len("全局日志"):].strip()
    limit = 20
    if plain_text.isdigit():
        limit = int(plain_text)

    if not api:
        await global_logs_cmd.finish("❌ API 未初始化")

    logs = await api.get_global_logs(limit)
    if not logs:
        await global_logs_cmd.finish("📭 暂无全局日志")

    lines = ["📋 全局最近日志", "----------------------------------------"]
    for log in logs[:limit]:
        lines.append(format_log_line(log))
    lines.append("----------------------------------------")
    await global_logs_cmd.finish("\n".join(lines))


# 农场统计
farm_stats_cmd = on_command("农场统计", priority=10, block=True)


@farm_stats_cmd.handle()
async def handle_farm_stats(bot: Bot, event: MessageEvent):
    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await farm_stats_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")
        return

    if not api:
        await farm_stats_cmd.finish("❌ API 未初始化")
        return

    try:
        stats = await api.get_analytics()
        if not stats:
            await farm_stats_cmd.finish("❌ 获取统计失败：后端返回空数据")
            return

        # 检查 stats 是否为字典，如果不是则尝试兼容或报错
        if not isinstance(stats, dict):
            logger.error(f"get_analytics 返回了非字典类型: {type(stats)}")
            await farm_stats_cmd.finish(f"❌ 统计接口返回了异常数据格式（{type(stats).__name__}），请联系管理员检查后端接口。")
            return

        lines = ["📊 农场统计摘要", "----------------------------------------"]

        accounts = stats.get("accounts", {})
        if isinstance(accounts, dict):
            total = accounts.get("total", 0)
            relogin = accounts.get("reloginRequired", 0)
            banned = accounts.get("banned", 0)
            lines.append(f"📁 账号统计:")
            lines.append(f"   总账号: {total}")
            lines.append(f"   需重新登录: {relogin}")
            lines.append(f"   已禁用: {banned}")
            lines.append("")
        else:
            lines.append("📁 账号统计: 数据格式异常")

        buckets = stats.get("buckets", {})
        if isinstance(buckets, dict):
            lines.append("📈 收益统计:")
            for period, data in buckets.items():
                if isinstance(data, dict):
                    label = data.get("label", period)
                    exp = data.get("exp", 0)
                    gold = data.get("gold", 0)
                    steal = data.get("steal", 0)
                    help_count = data.get("help", 0)
                    lines.append(f"   {label}: 经验:{exp} 金币:{gold} 偷菜:{steal} 帮助:{help_count}")
                else:
                    lines.append(f"   {period}: 数据格式异常")
        else:
            lines.append("📈 收益统计: 数据格式异常")

        lines.append("----------------------------------------")
        await farm_stats_cmd.finish("\n".join(lines))
    except Exception as e:
        logger.error(f"农场统计错误: {e}")
        await farm_stats_cmd.finish(f"❌ 获取统计失败：{str(e)}")


# 农场帮助
farm_help_cmd = on_command("农场帮助", priority=10, block=True)


@farm_help_cmd.handle()
async def handle_farm_help(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("农场帮助"):
        plain_text = plain_text[len("农场帮助"):].strip()
    category = plain_text.lower()

    if not category:
        help_text = (
            "🍀 **QQ农场助手 - 帮助菜单**\n"
            "----------------------------------------\n"
            "请选择查看类别：\n"
            "📌 `农场帮助 基础`  - 基础指令（账号绑定、查看、操作）\n"
            "🔧 `农场帮助 管理`  - 管理员专用指令\n"
            "📁 `农场帮助 账号`  - 账号管理指令（添加/删除账号）\n"
            "🔑 `农场帮助 端点`  - Webhook端点管理指令（仅私聊）\n"
            "📊 `农场帮助 统计`  - 统计指令\n"
            "🌐 `农场帮助 全局`  - 全局日志、帮助等\n"
            "----------------------------------------\n"
            "💡 提示：输入 `农场帮助 <类别>` 查看具体指令。"
        )
        await farm_help_cmd.finish(help_text)
        return

    if category == "基础":
        help_text = (
            "🔗 **基础指令**\n"
            "----------------------------------------\n"
            "`绑定农场账号 <用户名>` - 绑定当前 QQ 与农场用户名\n"
            "`我的农场账号 [用户名]` - 查看指定用户名下的农场账号\n"
            "`农场状态` - 查看自己绑定的农场账号状态\n"
            "`农场详情 <账号ID>` - 查看指定账号详情\n"
            "`启动农场 <账号ID>` - 启动农场账号\n"
            "`停止农场 <账号ID>` - 停止农场账号\n"
            "`更新农场Code <账号ID> <Code>` - 更新账号Code并自动启动\n"
            "`农场备注 <账号ID> <备注内容>` - 设置账号备注\n"
            "`农场日志 <账号ID> [数量]` - 查看账号日志\n"
            "----------------------------------------"
        )
    elif category == "管理":
        help_text = (
            "🔧 **管理员专用指令**\n"
            "----------------------------------------\n"
            "`管理账号列表` - 查看所有农场账号\n"
            "`添加管理员 <QQ号>` - 添加管理员\n"
            "`删除管理员 <QQ号>` - 删除管理员\n"
            "`绑定用户 <QQ号> <用户名>` - 为指定QQ绑定用户名\n"
            "`解绑用户 <QQ号>` - 解绑指定QQ的用户\n"
            "`管理员启动农场 <账号ID>` - 启动任意账号\n"
            "`管理员停止农场 <账号ID>` - 停止任意账号\n"
            "`管理员更新农场Code <账号ID> <Code>` - 更新任意账号Code并自动启动\n"
            "`管理员农场备注 <账号ID> <备注>` - 设置任意账号备注\n"
            "`管理员农场日志 <账号ID> [数量]` - 查看任意账号日志\n"
            "`分配账号 <账号ID> <用户名>` - 将账号分配给指定用户\n"
            "`解绑QQ <QQ号>` - 强制解除QQ与用户名的绑定\n"
            "`端点列表` - 查看所有申请的端点（管理员）\n"
            "`农场统计` - 查看农场统计摘要\n"
            "----------------------------------------"
        )
    elif category == "账号":
        help_text = (
            "📁 **账号管理指令**\n"
            "----------------------------------------\n"
            "`添加农场账号 <uin> <code> [昵称]` - 添加新农场账号并自动启动\n"
            "`删除农场账号 <账号ID>` - 删除自己的农场账号\n"
            "----------------------------------------"
        )
    elif category == "端点":
        help_text = (
            "🔑 **端点管理指令（仅私聊）**\n"
            "----------------------------------------\n"
            "`申请端点` - 申请专属Webhook端点\n"
            "`我的端点` - 查看自己的端点信息\n"
            "`重置端点` - 重置端点Token（旧端点失效）\n"
            "----------------------------------------\n"
            "📡 **Webhook地址**:\n"
            "• 统一端点: POST /report\n"
            "• 专属端点: POST /{endpoint}/send\n"
            "----------------------------------------\n"
            "📝 **请求格式**:\n"
            "{\n"
            '  "title": "标题",\n'
            '  "content": "账号: xxx\\n内容..."\n'
            "}\n"
            "----------------------------------------\n"
            "💡 统一端点会根据内容中的账号ID自动通知对应QQ\n"
            "💡 专属端点需先申请，每个用户独立"
        )
    elif category == "统计":
        help_text = (
            "📊 **统计指令**\n"
            "----------------------------------------\n"
            "`农场统计` - 查看农场统计摘要（管理员）\n"
            "----------------------------------------"
        )
    elif category == "全局":
        help_text = (
            "🌐 **全局指令**\n"
            "----------------------------------------\n"
            "`全局日志 [数量]` - 查看全局日志\n"
            "`农场帮助 [类别]` - 显示帮助信息\n"
            "----------------------------------------"
        )
    else:
        await farm_help_cmd.finish(f"❌ 未知类别 `{category}`，可用类别：基础、管理、账号、端点、统计、全局")
        return

    await farm_help_cmd.finish(help_text)


# 添加农场账号
add_account_cmd = on_command("添加农场账号", priority=10, block=True)


@add_account_cmd.handle()
async def handle_add_account(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("添加农场账号"):
        plain_text = plain_text[len("添加农场账号"):].strip()
    parts = plain_text.split(maxsplit=2)
    if len(parts) < 2:
        await add_account_cmd.finish("❌ 请提供 uin 和 code，例如：添加农场账号 123456 abcdef [昵称]")
    uin = parts[0]
    code = parts[1]
    nickname = parts[2] if len(parts) >= 3 else None

    user_qq = int(event.user_id)
    username = await get_current_username(user_qq)
    if not username:
        await add_account_cmd.finish("❌ 您尚未绑定农场账号，请先使用 /绑定农场账号 <用户名> 绑定。")

    if not api:
        await add_account_cmd.finish("❌ API 未初始化")

    if not db_pool:
        await add_account_cmd.finish("❌ 数据库未连接")

    try:
        result = await api.add_account(uin, code, nickname)
        if not result:
            await add_account_cmd.finish("❌ 添加账号失败，后端返回无效数据。")

        account_id = result.get('id')
        if not account_id:
            await add_account_cmd.finish("❌ 添加账号失败，未获得账号ID。")

        accounts = await api.get_accounts()
        account_exists = any(str(acc.get("id")) == str(account_id) for acc in accounts)
        if not account_exists:
            await add_account_cmd.finish(f"❌ 添加账号失败，后端未实际创建账号 {account_id}。")

        default_automation = {
    "farm": True,                     # 农场自动化总开关
    "farm_manage": True,              # 农场管理
    "farm_water": True,               # 浇水
    "farm_weed": True,                # 除草
    "farm_bug": True,                 # 除虫
    "farm_push": False,               # 推送（手动）
    "land_upgrade": False,            # 土地升级（手动）
    "friend": True,                   # 好友操作总开关
    "friend_help_exp_limit": True,    # 帮助经验限制（开启）
    "friend_steal": True,             # 偷菜
    "friend_help": True,              # 帮助（开启）
    "friend_bad": True,               # 不良好友（开启）
    "friend_auto_accept": False,      # 自动接受好友（手动）
    "task": True,                     # 任务（开启）
    "email": False,                   # 邮件（手动）
    "fertilizer_gift": False,         # 肥料礼物（手动）
    "fertilizer_buy": False,          # 购买肥料（手动）
    "sell": True,                     # 出售
    "free_gifts": True,               # 免费礼物（开启）
    "share_reward": True,             # 分享奖励（开启）
    "vip_gift": True,                 # VIP礼物（开启）
    "month_card": True,               # 月卡（开启）
    "open_server_gift": True,         # 开服礼物（开启）
    "fertilizer": "both",             # 肥料类型保持默认
}
        set_auto_ok = await api.set_automation(str(account_id), default_automation)
        if not set_auto_ok:
            logger.warning(f"设置账号 {account_id} 默认自动化开关失败")

        assign_ok = await api.assign_account(str(account_id), username)
        if not assign_ok:
            logger.warning(f"添加账号 {account_id} 后分配失败")

        # 插入本地数据库
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM accounts WHERE id = %s", (account_id,))
                await cur.execute("""
                    INSERT INTO accounts (id, uin, nick, username, code, running)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (account_id, uin, nickname or '', username, code, 1 if result.get('running') else 0))

        if assign_ok and set_auto_ok:
            await add_account_cmd.finish(f"✅ 成功添加农场账号 {account_id}（{nickname or '无昵称'}）并已分配给用户 {username}，自动化开关已设置。")
        elif assign_ok:
            await add_account_cmd.finish(f"✅ 成功添加农场账号 {account_id}（{nickname or '无昵称'}）并已分配给用户 {username}，但自动化开关设置失败。")
        else:
            await add_account_cmd.finish(f"⚠️ 农场账号 {account_id} 已添加，但分配失败，请管理员手动分配。")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"添加账号失败: {e}")
        await add_account_cmd.finish(f"❌ 添加账号失败：{str(e)}")


# 删除农场账号
delete_account_cmd = on_command("删除农场账号", priority=10, block=True)


@delete_account_cmd.handle()
async def handle_delete_account(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("删除农场账号"):
        plain_text = plain_text[len("删除农场账号"):].strip()
    account_id_str = plain_text
    if not account_id_str.isdigit():
        await delete_account_cmd.finish("账号ID必须为数字")
    account_id = int(account_id_str)

    user_qq = int(event.user_id)
    if not await check_account_ownership(user_qq, account_id):
        await delete_account_cmd.finish(f"❌ 账号 {account_id} 不存在或不属于您。")

    if not api:
        await delete_account_cmd.finish("❌ API 未初始化")

    if not db_pool:
        await delete_account_cmd.finish("❌ 数据库未连接")

    try:
        await api.stop_account(str(account_id))
        del_ok = await api.delete_account(str(account_id))
        if not del_ok:
            await delete_account_cmd.finish(f"❌ 后端删除账号 {account_id} 失败，请稍后重试。")

        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM accounts WHERE id = %s", (account_id,))
                await cur.execute("DELETE FROM account_remarks WHERE account_id = %s", (account_id,))

        await delete_account_cmd.finish(f"✅ 成功删除农场账号 {account_id}（已从后端和本地删除）。")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"删除账号失败: {e}")
        await delete_account_cmd.finish(f"❌ 删除账号失败：{str(e)}")


# 管理账号列表
admin_account_list_cmd = on_command("管理账号列表", priority=10, block=True)


@admin_account_list_cmd.handle()
async def handle_admin_account_list(event: MessageEvent):
    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await admin_account_list_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    if not api:
        await admin_account_list_cmd.finish("❌ API 未初始化")

    try:
        accounts = await api.get_accounts()
        if not accounts:
            await admin_account_list_cmd.finish("📭 没有任何农场账号")

        accounts_with_status = await get_accounts_with_online_status(accounts)
        accounts_with_status.sort(key=lambda x: x[0], reverse=True)

        lines = ["📋 所有农场账号（实时状态）", "----------------------------------------"]
        for is_online, acc in accounts_with_status:
            acc_id = acc.get("id")
            nick = acc.get("name", "无")
            username = acc.get("username", "未绑定")
            level = acc.get("level", 0)
            gold = acc.get("gold", 0)
            uptime = acc.get("uptime", 0)
            status_icon = "🟢 运行中" if is_online else "🔴 已停止"
            lines.append(f"ID: {acc_id} | 昵称: {nick} | 用户名: {username} | 等级: {level} | 金币: {gold} | 运行时间: {format_uptime(uptime)} | 状态: {status_icon}")
        lines.append("----------------------------------------")
        await admin_account_list_cmd.finish("\n".join(lines))
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"管理员账号列表错误: {e}")
        await admin_account_list_cmd.finish(f"❌ 查询失败：{str(e)}")


# 分配账号
assign_account_cmd = on_command("分配账号", priority=10, block=True)


@assign_account_cmd.handle()
async def handle_assign_account(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("分配账号"):
        plain_text = plain_text[len("分配账号"):].strip()
    parts = plain_text.split()
    if len(parts) < 2:
        await assign_account_cmd.finish("❌ 请提供账号ID和用户名，例如：分配账号 123456 jiongba")
    account_id_str = parts[0]
    username = parts[1]
    if not account_id_str.isdigit():
        await assign_account_cmd.finish("账号ID必须为数字")
    account_id = int(account_id_str)

    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await assign_account_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    if not db_pool:
        await assign_account_cmd.finish("❌ 数据库未连接")

    if not api:
        await assign_account_cmd.finish("❌ API 未初始化")

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 确保用户名存在于 users 表
                await cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
                if not await cur.fetchone():
                    await cur.execute(
                        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                        (username, "", "user")
                    )
                # 更新 accounts 表
                await cur.execute("UPDATE accounts SET username = %s WHERE id = %s", (username, account_id))

                try:
                    assign_ok = await api.assign_account(str(account_id), username)
                    if not assign_ok:
                        logger.warning(f"分配账号同步到后端失败: {account_id}")
                except Exception as e:
                    logger.error(f"后端分配同步失败: {e}")

                await assign_account_cmd.finish(f"✅ 已将账号 {account_id} 分配给用户 {username}。")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"分配账号失败: {e}")
        await assign_account_cmd.finish(f"❌ 分配失败：{str(e)}")


# 解绑QQ
unbind_qq_cmd = on_command("解绑QQ", priority=10, block=True)


@unbind_qq_cmd.handle()
async def handle_unbind_qq(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("解绑QQ"):
        plain_text = plain_text[len("解绑QQ"):].strip()
    qq_str = plain_text
    if not qq_str.isdigit():
        await unbind_qq_cmd.finish("❌ QQ号必须为数字")
    target_qq = int(qq_str)

    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await unbind_qq_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    if not db_pool:
        await unbind_qq_cmd.finish("❌ 数据库未连接")

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT username FROM user_bindings WHERE qq = %s", (target_qq,))
                row = await cur.fetchone()
                if not row:
                    await unbind_qq_cmd.finish(f"❌ 未找到 QQ {target_qq} 绑定的用户。")
                username = row[0]
                await cur.execute("DELETE FROM user_bindings WHERE qq = %s", (target_qq,))
                if target_qq in _admin_cache:
                    _admin_cache.discard(target_qq)
                await unbind_qq_cmd.finish(f"✅ 已解绑 QQ {target_qq}（原用户名 {username}）。")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"解绑QQ失败: {e}")
        await unbind_qq_cmd.finish(f"❌ 解绑失败：{str(e)}")


# 添加管理员
admin_add_cmd = on_command("添加管理员", priority=10, block=True)


@admin_add_cmd.handle()
async def handle_admin_add(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("添加管理员"):
        plain_text = plain_text[len("添加管理员"):].strip()
    qq_str = plain_text
    if not qq_str.isdigit():
        await admin_add_cmd.finish("❌ QQ号必须为数字")
    target_qq = int(qq_str)

    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await admin_add_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    if not db_pool:
        await admin_add_cmd.finish("❌ 数据库未连接")

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("INSERT IGNORE INTO admins (qq) VALUES (%s)", (target_qq,))
                _admin_cache.add(target_qq)
                await admin_add_cmd.finish(f"✅ 已添加 QQ {target_qq} 为管理员")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"添加管理员失败: {e}")
        await admin_add_cmd.finish("❌ 添加失败")


# 删除管理员
admin_remove_cmd = on_command("删除管理员", priority=10, block=True)


@admin_remove_cmd.handle()
async def handle_admin_remove(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("删除管理员"):
        plain_text = plain_text[len("删除管理员"):].strip()
    qq_str = plain_text
    if not qq_str.isdigit():
        await admin_remove_cmd.finish("❌ QQ号必须为数字")
    target_qq = int(qq_str)

    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await admin_remove_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    if not db_pool:
        await admin_remove_cmd.finish("❌ 数据库未连接")

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM admins WHERE qq = %s", (target_qq,))
                _admin_cache.discard(target_qq)
                await admin_remove_cmd.finish(f"✅ 已删除 QQ {target_qq} 的管理员权限")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"删除管理员失败: {e}")
        await admin_remove_cmd.finish("❌ 删除失败")


# 绑定用户
bind_user_cmd = on_command("绑定用户", priority=10, block=True)


@bind_user_cmd.handle()
async def handle_bind_user(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("绑定用户"):
        plain_text = plain_text[len("绑定用户"):].strip()
    parts = plain_text.split()
    if len(parts) < 2:
        await bind_user_cmd.finish("❌ 请提供QQ号和用户名，例如：绑定用户 123456 jiongba")
    qq_str = parts[0]
    username = parts[1]
    if not qq_str.isdigit():
        await bind_user_cmd.finish("❌ QQ号必须为数字")
    target_qq = int(qq_str)

    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await bind_user_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    if not db_pool:
        await bind_user_cmd.finish("❌ 数据库未连接")

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 确保 users 表存在该用户
                await cur.execute("SELECT id FROM users WHERE username = %s", (username,))
                row = await cur.fetchone()
                if not row:
                    await cur.execute(
                        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                        (username, "", "user")
                    )
                # 插入绑定关系
                await cur.execute(
                    "INSERT INTO user_bindings (qq, username) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE username = %s",
                    (target_qq, username, username)
                )
                await bind_user_cmd.finish(f"✅ 已将 QQ {target_qq} 绑定到用户名 {username}")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"管理员绑定用户失败: {e}")
        await bind_user_cmd.finish("❌ 绑定失败，请检查数据库连接或用户名是否正确")


# 解绑用户
unbind_user_cmd = on_command("解绑用户", priority=10, block=True)


@unbind_user_cmd.handle()
async def handle_unbind_user(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("解绑用户"):
        plain_text = plain_text[len("解绑用户"):].strip()
    qq_str = plain_text
    if not qq_str.isdigit():
        await unbind_user_cmd.finish("❌ QQ号必须为数字")
    target_qq = int(qq_str)

    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await unbind_user_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    if not db_pool:
        await unbind_user_cmd.finish("❌ 数据库未连接")

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT username FROM user_bindings WHERE qq = %s", (target_qq,))
                row = await cur.fetchone()
                if not row:
                    await unbind_user_cmd.finish(f"❌ 未找到 QQ {target_qq} 绑定的用户")
                username = row[0]
                await cur.execute("DELETE FROM user_bindings WHERE qq = %s", (target_qq,))
                await unbind_user_cmd.finish(f"✅ 已解绑 QQ {target_qq}（用户名 {username}）")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"管理员解绑用户失败: {e}")
        await unbind_user_cmd.finish("❌ 解绑失败")


# 管理员启动农场
admin_farm_start_cmd = on_command("管理员启动农场", priority=10, block=True)


@admin_farm_start_cmd.handle()
async def handle_admin_farm_start(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("管理员启动农场"):
        plain_text = plain_text[len("管理员启动农场"):].strip()
    if not plain_text.isdigit():
        await admin_farm_start_cmd.finish("账号ID必须为数字")
    account_id = int(plain_text)

    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await admin_farm_start_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    if not api:
        await admin_farm_start_cmd.finish("❌ API 未初始化")

    ok = await api.start_account(str(account_id))
    if ok:
        await admin_farm_start_cmd.finish(f"✅ 账号 {account_id} 已启动（管理员操作）")
    else:
        await admin_farm_start_cmd.finish(f"❌ 启动账号 {account_id} 失败")


# 管理员停止农场
admin_farm_stop_cmd = on_command("管理员停止农场", priority=10, block=True)


@admin_farm_stop_cmd.handle()
async def handle_admin_farm_stop(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("管理员停止农场"):
        plain_text = plain_text[len("管理员停止农场"):].strip()
    if not plain_text.isdigit():
        await admin_farm_stop_cmd.finish("账号ID必须为数字")
    account_id = int(plain_text)

    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await admin_farm_stop_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    if not api:
        await admin_farm_stop_cmd.finish("❌ API 未初始化")

    ok = await api.stop_account(str(account_id))
    if ok:
        await admin_farm_stop_cmd.finish(f"✅ 账号 {account_id} 已停止（管理员操作）")
    else:
        await admin_farm_stop_cmd.finish(f"❌ 停止账号 {account_id} 失败")


# 管理员更新农场Code
admin_update_code_cmd = on_command("管理员更新农场Code", priority=10, block=True)


@admin_update_code_cmd.handle()
async def handle_admin_update_code(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("管理员更新农场Code"):
        plain_text = plain_text[len("管理员更新农场Code"):].strip()
    parts = plain_text.split()
    if len(parts) < 2:
        await admin_update_code_cmd.finish("❌ 请提供账号ID和Code，例如：管理员更新农场Code 123456 abcdef")
    account_id_str = parts[0]
    code = parts[1]
    if not account_id_str.isdigit():
        await admin_update_code_cmd.finish("账号ID必须为数字")
    account_id = int(account_id_str)

    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await admin_update_code_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    if not api:
        await admin_update_code_cmd.finish("❌ API 未初始化")

    try:
        ok = await api.update_account_code(str(account_id), code)
        if not ok:
            await admin_update_code_cmd.finish(f"❌ 更新账号 {account_id} Code 失败")

        await update_account_code(account_id, code)

        start_ok = await api.start_account(str(account_id))
        default_automation = {
    "farm": True,                     # 农场自动化总开关
    "farm_manage": True,              # 农场管理
    "farm_water": True,               # 浇水
    "farm_weed": True,                # 除草
    "farm_bug": True,                 # 除虫
    "farm_push": False,               # 推送（手动）
    "land_upgrade": False,            # 土地升级（手动）
    "friend": True,                   # 好友操作总开关
    "friend_help_exp_limit": True,    # 帮助经验限制（开启）
    "friend_steal": True,             # 偷菜
    "friend_help": True,              # 帮助（开启）
    "friend_bad": True,               # 不良好友（开启）
    "friend_auto_accept": False,      # 自动接受好友（手动）
    "task": True,                     # 任务（开启）
    "email": False,                   # 邮件（手动）
    "fertilizer_gift": False,         # 肥料礼物（手动）
    "fertilizer_buy": False,          # 购买肥料（手动）
    "sell": True,                     # 出售
    "free_gifts": True,               # 免费礼物（开启）
    "share_reward": True,             # 分享奖励（开启）
    "vip_gift": True,                 # VIP礼物（开启）
    "month_card": True,               # 月卡（开启）
    "open_server_gift": True,         # 开服礼物（开启）
    "fertilizer": "both",             # 肥料类型保持默认
}
        set_auto_ok = await api.set_automation(str(account_id), default_automation)
        if not set_auto_ok:
            logger.warning(f"管理员更新 Code 后设置账号 {account_id} 默认自动化开关失败")

        if start_ok:
            await admin_update_code_cmd.finish(f"✅ 账号 {account_id} Code 已更新，并已启动，自动化开关已应用（管理员操作）")
        else:
            await admin_update_code_cmd.finish(f"✅ 账号 {account_id} Code 已更新，但启动失败，请手动启动，自动化开关已应用（管理员操作）")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"管理员更新Code失败: {e}")
        await admin_update_code_cmd.finish(f"❌ 更新失败：{str(e)}")


# 管理员农场备注
admin_set_remark_cmd = on_command("管理员农场备注", priority=10, block=True)


@admin_set_remark_cmd.handle()
async def handle_admin_set_remark(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("管理员农场备注"):
        plain_text = plain_text[len("管理员农场备注"):].strip()
    parts = plain_text.split(maxsplit=1)
    if len(parts) < 2:
        await admin_set_remark_cmd.finish("❌ 请提供账号ID和备注内容，例如：管理员农场备注 123456 我的备注")
    account_id_str = parts[0]
    remark = parts[1].strip()
    if not account_id_str.isdigit():
        await admin_set_remark_cmd.finish("账号ID必须为数字")
    account_id = int(account_id_str)

    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await admin_set_remark_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    if not api:
        await admin_set_remark_cmd.finish("❌ API 未初始化")

    ok = await api.set_account_remark(str(account_id), remark)
    if ok:
        await update_account_remark(account_id, remark)
        await admin_set_remark_cmd.finish(f"✅ 账号 {account_id} 备注已更新为：{remark}（管理员操作）")
    else:
        await admin_set_remark_cmd.finish(f"❌ 更新备注失败")


# 管理员农场日志
admin_farm_logs_cmd = on_command("管理员农场日志", priority=10, block=True)


@admin_farm_logs_cmd.handle()
async def handle_admin_farm_logs(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    if plain_text.startswith("管理员农场日志"):
        plain_text = plain_text[len("管理员农场日志"):].strip()
    parts = plain_text.split()
    if len(parts) < 1:
        await admin_farm_logs_cmd.finish("❌ 请提供账号ID，例如：管理员农场日志 123456 [数量]")
    account_id_str = parts[0]
    limit = 10
    if len(parts) >= 2 and parts[1].isdigit():
        limit = int(parts[1])
    if not account_id_str.isdigit():
        await admin_farm_logs_cmd.finish("账号ID必须为数字")
    account_id = int(account_id_str)

    user_qq = int(event.user_id)
    if not await is_admin(user_qq):
        await admin_farm_logs_cmd.finish("❌ 权限不足，仅管理员可使用此命令。")

    if not api:
        await admin_farm_logs_cmd.finish("❌ API 未初始化")

    logs = await api.get_account_logs(str(account_id), limit)
    if not logs:
        await admin_farm_logs_cmd.finish(f"📭 账号 {account_id} 暂无日志")

    lines = [f"📋 账号 {account_id} 最近日志", "----------------------------------------"]
    for log in logs[:limit]:
        lines.append(format_log_line(log))
    lines.append("----------------------------------------")
    await admin_farm_logs_cmd.finish("\n".join(lines))


# ========== 启动和关闭 ==========
driver = get_driver()


@driver.on_startup
async def startup():
    global _offline_notify_task
    await init_db_pool()
    await init_api()
    if db_pool:
        await ensure_tables()
        await sync_initial_admins()
    # ========== 初始化 Webhook ==========

    try:

        from .webhook import init_webhook

        init_webhook()

        logger.info("Webhook模块已加载")

    except Exception as e:

        logger.error(f"Webhook初始化失败: {e}")

    # ========== Webhook初始化结束 ==========
    if db_pool and api:
        _offline_notify_task = asyncio.create_task(offline_notify_loop())
        logger.info(f"离线通知任务已启动（间隔 {offline_check_interval} 秒）")
    else:
        logger.warning("离线通知功能已禁用（数据库或API未就绪）")


@driver.on_shutdown
async def shutdown():
    global _offline_notify_task
    if _offline_notify_task:
        _offline_notify_task.cancel()
        try:
            await _offline_notify_task
        except asyncio.CancelledError:
            pass
    if db_pool:
        db_pool.close()
        await db_pool.wait_closed()
    if api:
        await api.close()
    logger.info("QQ农场插件已关闭")