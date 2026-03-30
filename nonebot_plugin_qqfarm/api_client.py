#!/usr/bin/env python3
"""
QQ Farm Bot UI API client (async)
支持所有可用的 API 路由
"""

from typing import Optional, Dict, Any, List
import httpx
import logging
import time

logger = logging.getLogger(__name__)


class QQFarmAPI:
    """QQ Farm Bot UI API client"""

    def __init__(
        self,
        base_url: str,
        admin_password: str = "",
        timeout: int = 30,
        api_key: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.admin_password = admin_password
        self.timeout = timeout
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def ainit(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        use_external: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if self._client is None:
            await self.ainit()
        assert self._client is not None

        req_headers = headers or {}
        if use_external and self.api_key:
            req_headers["X-API-Key"] = self.api_key

        url = f"{self.base_url}{path}"
        try:
            response = await self._client.request(
                method,
                url,
                headers=req_headers,
                json=json_data,
            )
        except httpx.RequestError as e:
            logger.error(f"HTTP request failed: {e}")
            return None

        if response.status_code != 200:
            logger.warning(f"Unexpected status code {response.status_code} from {url}")
            return None

        try:
            return response.json()
        except ValueError:
            logger.error("Invalid JSON response")
            return None

    # ========== 认证相关 ==========
    async def login(self) -> bool:
        """使用管理员密码登录"""
        result = await self._request(
            "POST",
            "/api/login",
            json_data={"username": "admin", "password": self.admin_password},
        )
        if result and result.get("ok"):
            logger.info("QQFarm API login successful")
            return True
        logger.warning("QQFarm API login failed")
        return False

    async def logout(self) -> bool:
        """登出"""
        result = await self._request("POST", "/api/logout")
        return bool(result and result.get("ok"))

    async def validate_token(self) -> bool:
        """验证 token 是否有效"""
        result = await self._request("GET", "/api/auth/validate")
        return bool(result and result.get("ok"))

    # ========== 账号管理（内部 API）==========
    async def get_accounts(self) -> List[Dict[str, Any]]:
        """获取所有账号列表（包含 uptime、running、connected 等完整信息）"""
        result = await self._request("GET", "/api/accounts")
        if not result or not result.get("ok"):
            return []
        data = result.get("data", {})
        accounts = data.get("accounts", [])
        return accounts if isinstance(accounts, list) else []

    async def add_account(self, uin: str, code: str, nickname: str = None) -> Optional[Dict[str, Any]]:
        """添加新农场账号，返回包含 id 的账号信息"""
        data = {"uin": uin, "code": code}
        if nickname:
            data["nick"] = nickname
        result = await self._request("POST", "/api/accounts", json_data=data)

        if result and result.get("ok"):
            resp_data = result.get("data", {})
            new_id = resp_data.get("touchedAccountId")
            if new_id:
                logger.info(f"添加账号成功，后端返回 touchedAccountId: {new_id}")
                return {"id": str(new_id), "uin": uin, "nick": nickname or "", "code": code}
            if isinstance(resp_data, dict):
                if "id" in resp_data:
                    return {"id": str(resp_data["id"]), "uin": uin, "nick": nickname or "", "code": code}
                if "accounts" in resp_data and isinstance(resp_data["accounts"], list) and resp_data["accounts"]:
                    last = resp_data["accounts"][-1]
                    if "id" in last:
                        return {"id": str(last["id"]), "uin": uin, "nick": nickname or "", "code": code}
            return {"id": str(int(time.time())), "uin": uin, "nick": nickname or "", "code": code}
        logger.warning(f"add_account failed: {result}")
        return None

    async def delete_account(self, account_id: str) -> bool:
        """删除农场账号"""
        result = await self._request("DELETE", f"/api/accounts/{account_id}")
        if result:
            if result.get("ok") is True:
                return True
            if "data" in result:
                return True
        return False

    async def start_account(self, account_id: str) -> bool:
        """启动账号"""
        result = await self._request(
            "POST",
            f"/api/accounts/{account_id}/start",
            json_data={}
        )
        return bool(result and result.get("ok"))

    async def stop_account(self, account_id: str) -> bool:
        """停止账号"""
        result = await self._request(
            "POST",
            f"/api/accounts/{account_id}/stop",
            json_data={}
        )
        return bool(result and result.get("ok"))

    async def restart_account(self, account_id: str) -> bool:
        """重启账号"""
        result = await self._request(
            "POST",
            f"/api/accounts/{account_id}/restart",
            json_data={}
        )
        return bool(result and result.get("ok"))

    async def update_account_code(self, account_id: str, code: str) -> bool:
        """更新账号 Code"""
        result = await self._request(
            "POST",
            "/api/accounts",
            json_data={"id": account_id, "code": code}
        )
        return bool(result and result.get("ok"))

    async def assign_account(self, account_id: str, username: str) -> bool:
        """将账号分配给指定用户名（通过更新账号的 username 字段）"""
        result = await self._request(
            "POST",
            "/api/accounts",
            json_data={"id": account_id, "username": username}
        )
        return bool(result and result.get("ok"))

    async def set_account_remark(self, account_id: str, remark: str) -> bool:
        """设置账号备注"""
        result = await self._request(
            "POST",
            "/api/account/remark",
            headers={"x-account-id": account_id},
            json_data={"remark": remark}
        )
        return bool(result and result.get("ok"))

    # ========== 状态相关 ==========
    async def get_status(self, account_id: str) -> Optional[Dict[str, Any]]:
        """获取账号运行状态"""
        result = await self._request(
            "GET",
            "/api/status",
            headers={"x-account-id": account_id}
        )
        if result and result.get("ok"):
            return result.get("data")
        return None

    async def get_scheduler_status(self) -> Optional[Dict[str, Any]]:
        """获取调度器状态"""
        result = await self._request("GET", "/api/scheduler")
        if result and result.get("ok"):
            return result.get("data")
        return None

    # ========== 日志相关 ==========
    async def get_account_logs(self, account_id: str, limit: int = 50) -> List:
        """获取账号日志"""
        result = await self._request(
            "GET",
            f"/api/account-logs?accountId={account_id}&limit={limit}"
        )
        if not result:
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            if result.get("ok") is True:
                data = result.get("data", [])
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    logs = data.get("logs", [])
                    return logs if isinstance(logs, list) else []
            if "logs" in result:
                return result["logs"] if isinstance(result["logs"], list) else []
            return result
        return []

    async def get_global_logs(self, limit: int = 50) -> List:
        """获取全局日志"""
        result = await self._request("GET", f"/api/logs?limit={limit}")
        if not result or not result.get("ok"):
            return []
        data = result.get("data", [])
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            logs = data.get("logs", [])
            return logs if isinstance(logs, list) else []
        return []

    # ========== 设置相关 ==========
    async def get_settings(self, account_id: str) -> Optional[Dict[str, Any]]:
        """获取账号设置"""
        result = await self._request(
            "GET",
            "/api/settings",
            headers={"x-account-id": account_id}
        )
        if result and result.get("ok"):
            return result.get("data")
        return None

    async def save_settings(self, account_id: str, settings: Dict[str, Any]) -> bool:
        """保存账号设置"""
        result = await self._request(
            "POST",
            "/api/settings/save",
            headers={"x-account-id": account_id},
            json_data=settings
        )
        return bool(result and result.get("ok"))

    async def set_automation(self, account_id: str, automation: Dict[str, Any]) -> bool:
        """设置自动化配置"""
        result = await self._request(
            "POST",
            "/api/automation",
            headers={"x-account-id": account_id},
            json_data=automation
        )
        return bool(result and result.get("ok"))

    # ========== 用户相关 ==========
    async def get_users(self) -> List[Dict[str, Any]]:
        """获取用户列表"""
        result = await self._request("GET", "/api/users")
        if result and result.get("ok"):
            return result.get("users", [])
        return []

    async def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """获取用户详情"""
        result = await self._request("GET", f"/api/users/{username}")
        if result and result.get("ok"):
            return result.get("user")
        return None

    async def change_password(self, old_password: str, new_password: str) -> bool:
        """修改密码"""
        result = await self._request(
            "POST",
            "/api/auth/change-password",
            json_data={"old_password": old_password, "new_password": new_password}
        )
        return bool(result and result.get("ok"))

    # ========== 统计相关 ==========
    async def get_analytics(self) -> Optional[Dict[str, Any]]:
        """获取统计信息"""
        result = await self._request("GET", "/api/analytics")
        if result and result.get("ok"):
            return result.get("data")
        return None

    # ========== 通知相关 ==========
    async def get_notifications(self) -> List[Dict[str, Any]]:
        """获取通知列表"""
        result = await self._request("GET", "/api/notifications")
        if result and result.get("ok"):
            return result.get("data", [])
        return []

    # ========== 健康检查 ==========
    async def ping(self) -> bool:
        """Ping 测试"""
        result = await self._request("GET", "/api/ping")
        return bool(result and result.get("ok"))

    async def health_basic(self) -> Optional[Dict[str, Any]]:
        """基础健康检查"""
        result = await self._request("GET", "/api/health/basic")
        if result and result.get("ok"):
            return result.get("data")
        return None

    async def health_dependencies(self) -> Optional[Dict[str, Any]]:
        """依赖健康检查"""
        result = await self._request("GET", "/api/health/dependencies")
        if result and result.get("ok"):
            return result.get("data")
        return None

    async def health_runtime(self) -> Optional[Dict[str, Any]]:
        """运行时健康检查"""
        result = await self._request("GET", "/api/health/runtime")
        if result and result.get("ok"):
            return result.get("data")
        return None

    async def get_service_profile(self) -> Optional[Dict[str, Any]]:
        """获取服务配置"""
        result = await self._request("GET", "/api/system/service-profile")
        if result and result.get("ok"):
            return result.get("data")
        return None

    # ========== 外部 API ==========
    async def get_external_accounts(self) -> List[Dict[str, Any]]:
        """获取所有账号列表（外部 API，简化版）"""
        result = await self._request("GET", "/api/external/accounts", use_external=True)
        if not result or not result.get("ok"):
            return []
        data = result.get("data", {})
        items = data.get("items", [])
        return items if isinstance(items, list) else []

    async def get_external_health(self) -> Optional[Dict[str, Any]]:
        """获取系统健康状态（外部 API）"""
        result = await self._request("GET", "/api/external/health", use_external=True)
        if result and result.get("ok"):
            return result.get("data")
        return None

    async def get_external_stats(self) -> Optional[Dict[str, Any]]:
        """获取统计摘要（外部 API）"""
        result = await self._request("GET", "/api/external/stats/summary", use_external=True)
        if result and result.get("ok"):
            return result.get("data")
        return None

    async def get_external_ping(self) -> Optional[Dict[str, Any]]:
        """获取外部 Ping 信息"""
        result = await self._request("GET", "/api/external/ping", use_external=True)
        if result and result.get("ok"):
            return result.get("data")
        return None

    # ========== 农场操作 ==========
    async def get_lands(self, account_id: str) -> Optional[Dict[str, Any]]:
        """获取土地信息"""
        result = await self._request(
            "GET",
            "/api/lands",
            headers={"x-account-id": account_id}
        )
        if result and result.get("ok"):
            return result.get("data")
        return None

    async def get_friends(self, account_id: str) -> List[Dict[str, Any]]:
        """获取好友列表"""
        result = await self._request(
            "GET",
            "/api/friends",
            headers={"x-account-id": account_id}
        )
        if result and result.get("ok"):
            data = result.get("data", [])
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                friends = data.get("friends", [])
                return friends if isinstance(friends, list) else []
        return []

    async def get_bag(self, account_id: str) -> List[Dict[str, Any]]:
        """获取背包"""
        result = await self._request(
            "GET",
            "/api/bag",
            headers={"x-account-id": account_id}
        )
        if result and result.get("ok"):
            data = result.get("data", [])
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                items = data.get("items", [])
                return items if isinstance(items, list) else []
        return []

    async def get_seeds(self, account_id: str) -> List[Dict[str, Any]]:
        """获取种子列表"""
        result = await self._request(
            "GET",
            "/api/seeds",
            headers={"x-account-id": account_id}
        )
        if result and result.get("ok"):
            data = result.get("data", [])
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                seeds = data.get("seeds", [])
                return seeds if isinstance(seeds, list) else []
        return []

    async def do_farm_operation(self, account_id: str, op: str, params: Dict[str, Any] = None) -> bool:
        """执行农场操作"""
        json_data = {"op": op}
        if params:
            json_data.update(params)
        result = await self._request(
            "POST",
            "/api/farm/operate",
            headers={"x-account-id": account_id},
            json_data=json_data
        )
        return bool(result and result.get("ok"))

    async def do_friend_operation(self, account_id: str, friend_gid: str, op: str, amount: int = 1) -> bool:
        """执行好友操作"""
        result = await self._request(
            "POST",
            f"/api/friend/{friend_gid}/op",
            headers={"x-account-id": account_id},
            json_data={"op": op, "amount": amount}
        )
        return bool(result and result.get("ok"))