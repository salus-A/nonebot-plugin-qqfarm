```markdown
<div align="center">
<a href="https://v2.nonebot.dev/store">
  <img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/nbp_logo.png" width="180" height="180" alt="NoneBotPluginLogo">
</a>
<br>
  <p><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/NoneBotPlugin.svg" width="240" alt="NoneBotPluginText"></p>
</div>

<div align="center">

# nonebot-plugin-qqfarm

_✨ QQ农场自动化助手 —— 账号管理、自动操作、离线通知、Webhook推送 ✨_

<a href="https://github.com/salus-A/nonebot-plugin-qqfarm/blob/main/LICENSE">
  <img src="https://img.shields.io/github/license/salus-A/nonebot-plugin-qqfarm.svg" alt="license">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-qqfarm">
  <img src="https://img.shields.io/pypi/v/nonebot-plugin-qqfarm.svg" alt="pypi">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-qqfarm">
  <img src="https://img.shields.io/pypi/pyversions/nonebot-plugin-qqfarm.svg" alt="python">
</a>
<img src="https://img.shields.io/badge/nonebot-2.0+-red.svg" alt="nonebot">

</div>

---

## 📖 介绍

本插件基于 [NoneBot2](https://nonebot.dev/) 和 OneBot V11 协议，对接 [qq-farm-ui-pro-max](https://github.com/smdk000/qq-farm-ui-pro-max) 后端 API，实现农场账号的远程管理、自动化执行和状态通知。

### 主要功能

| 功能 | 说明 |
|------|------|
| 🔐 账号绑定 | QQ 与农场用户名绑定，多账号归属清晰 |
| 🚀 自动化控制 | 一键启动/停止，更新 Code 后自动应用默认自动化配置 |
| 📊 状态监控 | 实时查看账号在线状态、运行时长、金币、等级等 |
| 📝 日志查询 | 查看指定账号或全局运行日志 |
| 🛎️ 离线通知 | 后台定时检测离线账号，私聊提醒绑定用户 |
| 👥 管理员系统 | 支持添加/删除管理员，管理所有账号和用户 |
| 🌐 Webhook 推送 | 支持统一端点和用户专属端点，可推送至多个默认群并 @ 目标用户 |
| 📡 多群支持 | 可配置多个默认群组，消息自动广播 |

---

## 💿 安装

<details open>
<summary>使用 nb-cli 安装</summary>

```bash
nb plugin install nonebot-plugin-qqfarm
```

</details>

<details>
<summary>使用 pip 安装</summary>

```bash
pip install nonebot-plugin-qqfarm
```

</details>

<details>
<summary>从 GitHub 安装</summary>

```bash
pip install git+https://github.com/salus-A/nonebot-plugin-qqfarm.git
```

</details>

---

⚙️ 配置

在 NoneBot 项目的 .env 或 env.* 文件中添加以下配置：

必填配置

配置项 类型 说明
QQFARM_BASE_URL str QQ农场后端 API 基础 URL
QQFARM_ADMIN_PASSWORD str 后端管理员密码
QQFARM_DATABASE dict 数据库连接配置

可选配置

配置项 类型 默认值 说明
QQFARM_API_KEY str "" 外部 API 密钥
QQFARM_TIMEOUT int 30 HTTP 请求超时（秒）
QQFARM_OFFLINE_CHECK_INTERVAL int 60 离线检查间隔（秒）
QQFARM_ADMIN_QQ list[int] [] 初始管理员 QQ 号列表
QQFARM_DEFAULT_GROUP str/int/list "1060330308" 默认推送的群号
QQFARM_WEBHOOK_URL str "http://localhost:6399" Webhook 服务公网地址

配置示例

```env
# 后端 API 配置
QQFARM_BASE_URL=http://127.0.0.1:8080
QQFARM_ADMIN_PASSWORD=your_admin_password

# 数据库配置
QQFARM_DATABASE={
    "host": "localhost",
    "port": 3306,
    "user": "qq_farm_user",
    "password": "your_password",
    "database": "qq_farm_bot",
    "charset": "utf8mb4"
}

# 管理员配置
QQFARM_ADMIN_QQ=[123456789]

# Webhook 多群配置（逗号分隔）
QQFARM_DEFAULT_GROUP="1060330308,1060330309"

# Webhook 公网地址
QQFARM_WEBHOOK_URL=http://your-domain:6399
```

---

🗄️ 数据库

插件启动时会自动创建以下表：

表名 说明
admins 管理员列表
user_bindings QQ ↔ 用户名绑定
account_remarks 账号备注
user_tokens Webhook 端点 Token
users 用户表

要求 MySQL 5.7+ 或 MariaDB 10.2+，用户需有建表权限。

---

🎮 命令列表

基础指令（普通用户）

命令 说明
绑定农场账号 <用户名> 绑定当前 QQ 与农场用户名
我的农场账号 [用户名] 查看自己（或指定用户）的账号列表
农场状态 查看自己所有账号的简略状态
农场详情 <账号ID> 查看指定账号的详细信息
启动农场 <账号ID> 启动自己的农场账号
停止农场 <账号ID> 停止自己的农场账号
更新农场Code <账号ID> <Code> 更新账号 Code 并自动启动
农场备注 <账号ID> <备注> 为自己的账号添加备注
农场日志 <账号ID> [数量] 查看账号操作日志
添加农场账号 <uin> <code> [昵称] 添加新农场账号
删除农场账号 <账号ID> 删除自己的账号
申请端点 申请专属 Webhook 端点（私聊）
我的端点 查看自己的端点信息（私聊）
重置端点 重置端点 Token（私聊）
农场帮助 [类别] 查看帮助信息

管理员指令

命令 说明
管理账号列表 查看所有账号及实时状态
添加管理员 <QQ号> 添加管理员
删除管理员 <QQ号> 删除管理员
绑定用户 <QQ号> <用户名> 为指定 QQ 绑定用户名
解绑用户 <QQ号> 解绑指定 QQ 的用户名
管理员启动农场 <账号ID> 启动任意账号
管理员停止农场 <账号ID> 停止任意账号
管理员更新农场Code <账号ID> <Code> 更新任意账号 Code
管理员农场备注 <账号ID> <备注> 为任意账号添加备注
管理员农场日志 <账号ID> [数量] 查看任意账号日志
分配账号 <账号ID> <用户名> 将账号分配给指定用户
解绑QQ <QQ号> 强制解除 QQ 与用户名的绑定
农场统计 查看全局统计摘要
全局日志 [数量] 查看全局运行日志

---

🌐 Webhook 使用

统一端点

· 地址：POST /report
· 请求体：
  ```json
  {
    "title": "标题",
    "content": "账号: 123456\n其余内容..."
  }
  ```
· 行为：提取账号 ID，私聊通知绑定用户，并向默认群推送消息并 @ 该用户。

专属端点（需先私聊发送 申请端点）

· 地址：POST /{endpoint}/send
· 请求体：同上
· 行为：验证 endpoint 有效性后，同样提取账号 ID 并推送私聊 + 群消息。

---

⚙️ 默认自动化配置

当通过 更新农场Code 或 添加农场账号 时，插件会自动应用以下配置：

```json
{
  "farm": true, "farm_manage": true, "farm_water": true,
  "farm_weed": true, "farm_bug": true, "friend": true,
  "friend_steal": true, "friend_help": true, "friend_bad": true,
  "task": true, "sell": true, "free_gifts": true,
  "share_reward": true, "vip_gift": true, "month_card": true,
  "open_server_gift": true, "fertilizer": "both"
}
```

其余开关（如 farm_push、land_upgrade、friend_auto_accept、email 等）默认关闭。

---

🛠️ 测试 Webhook

```bash
curl -X POST http://localhost:6399/report \
  -H "Content-Type: application/json" \
  -d '{"title":"测试","content":"账号: 123456 测试消息"}'
```

---

⚠️ 注意事项

1. 后端依赖：需要配合 QQFarm-Bot-UI 后端使用
2. 数据库：必须使用 MySQL/MariaDB，用户需有建表权限
3. 管理员初始化：QQFARM_ADMIN_QQ 配置的 QQ 号会在启动时自动加入管理员表
4. 私聊命令：申请端点、我的端点、重置端点 仅支持私聊
5. 安全建议：Webhook 端点建议配置 HTTPS，token 请妥善保管

---

📄 开源协议

MIT License © 2025 salus-A

---

🔗 相关链接

链接 地址
PyPI https://pypi.org/project/nonebot-plugin-qqfarm/
GitHub https://github.com/salus-A/nonebot-plugin-qqfarm
Issues https://github.com/salus-A/nonebot-plugin-qqfarm/issues
后端项目 https://github.com/smdk000/qq-farm-ui-pro-max

```