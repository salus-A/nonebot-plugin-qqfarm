
from pydantic import BaseModel, Field
from typing import Optional

class Config(BaseModel):
    """插件配置"""
    qqfarm_base_url: str = Field(..., description="QQFarm 后端 API 基础 URL")
    qqfarm_admin_password: str = Field(..., description="管理员密码")
    qqfarm_api_key: str = Field("", description="API 密钥（可选）")
    qqfarm_timeout: int = Field(30, description="HTTP 请求超时（秒）")
    qqfarm_offline_check_interval: int = Field(60, description="离线检查间隔（秒）")
    qqfarm_admin_qq: list[int] = Field([], description="初始管理员 QQ 号列表")
    qqfarm_database: dict = Field(
        {
            "host": "localhost",
            "port": 3306,
            "user": "qq_farm_user",
            "password": "",
            "database": "qq_farm_bot",
            "charset": "utf8mb4"
        },
        description="数据库配置"
    )