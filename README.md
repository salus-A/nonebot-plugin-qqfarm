<div align="center">
  <a href="https://github.com/salus-A/nonebot-plugin-qqfarm">
    <img src="https://github.com/user-attachments/assets/8f2b8c4a-3c1d-4e6f-9b7c-1a2b3c4d5e6f" width="200" alt="QQFarm Logo">
  </a>
  <h1>nonebot-plugin-qqfarm</h1>
  <h3>本项目基于qq-farm-ui-pro-max编写</h3>
  <h4><a href="https://github.com/smdk000/qq-farm-ui-pro-max">点击前往项目</a></h4>

  <p>
    <a href="https://pypi.org/project/nonebot-plugin-qqfarm/">
      <img src="https://img.shields.io/pypi/v/nonebot-plugin-qqfarm?color=green&style=flat-square" alt="PyPI Version">
    </a>
    <a href="https://www.python.org/">
      <img src="https://img.shields.io/badge/python-3.9+-blue?logo=python&style=flat-square" alt="Python Version">
    </a>
    <a href="https://nonebot.dev/">
      <img src="https://img.shields.io/badge/nonebot2-2.0.0+-blue?style=flat-square" alt="NoneBot Version">
    </a>
    <a href="LICENSE">
      <img src="https://img.shields.io/github/license/salus-A/nonebot-plugin-qqfarm?style=flat-square" alt="License">
    </a>
  </p>
</div>
1.核心功能
## ✨ 特性一览

### 🚀 核心功能

- ✅ 多账号绑定与管理
- ✅ 一键启动/停止农场账号
- ✅ 自动更新账号 Code 并启动
- ✅ 实时查看账号状态（在线/离线、等级、金币等）
- ✅ 离线自动检测并私聊通知
- ✅ 账号操作日志查询
- ✅ Webhook 推送（统一端点 + 专属端点）
- ✅ 多群消息广播

### 🧩 扩展体系

- 🔌 支持自定义 Webhook 接收端
- 🧠 智能账号归属识别
- 📦 管理员权限体系
- 🧰 完全基于 NoneBot 标准接口，易于集成

### 🛠️ 高级功能

- 🤖 离线自动通知
- ♻️ 账号备注管理
- 🚨 管理员全局管理账号
- ⏱️ 定时离线检查
- 🔐 API 密钥安全存储
- 🦺 支持外部 API 认证

📦安装

提供两种安装方式：

· 方法一（目前不支持）：
  ```bash
  nb plugin install nonebot-plugin-qqfarm
  ```
· 方法二（手动安装）：
  ```bash
  pip install nonebot-plugin-qqfarm
  ```
  若使用方法二，还需在 pyproject.toml 中手动添加插件名：
  ```toml
  [tool.nonebot.plugins]
  plugins = ["nonebot_plugin_qqfarm"]
  ```
  
---

## ⚙️ 配置示例

在 NoneBot 项目的 `.env` 文件中添加以下配置（使用 `NONEBOT_PLUGIN_QQFARM_` 前缀）：

```env
# ========== 必填配置 ==========
# 后端 API 基础地址
NONEBOT_PLUGIN_QQFARM_BASE_URL=https://your-backend.com
# 管理员认证密码
NONEBOT_PLUGIN_QQFARM_ADMIN_PASSWORD=your_password

# 数据库主机地址
NONEBOT_PLUGIN_QQFARM_DATABASE__HOST=localhost
# 数据库端口
NONEBOT_PLUGIN_QQFARM_DATABASE__PORT=3306
# 数据库用户名
NONEBOT_PLUGIN_QQFARM_DATABASE__USER=root
# 数据库密码
NONEBOT_PLUGIN_QQFARM_DATABASE__PASSWORD=your_db_password
# 数据库名称
NONEBOT_PLUGIN_QQFARM_DATABASE__DATABASE=qq_farm_bot
# 管理员 QQ 号列表（JSON 数组格式）
NONEBOT_PLUGIN_QQFARM_ADMIN_QQ=[123456789]
# 默认推送群组，多个用英文逗号分隔
NONEBOT_PLUGIN_QQFARM_DEFAULT_GROUP=1060330308,1084498190
# 全局 Webhook 接收地址
NONEBOT_PLUGIN_QQFARM_WEBHOOK_URL=https://webhook.your-domain.com
```
注意:如果需要使用域名作为webhook接收地址需要设置反代
---

**4. 使用命令**

```markdown
## 🎮 使用命令

| 命令 | 说明 |
|------|------|
| 绑定农场账号 <用户名> | 绑定当前 QQ 与农场用户名 |
| 我的农场账号 | 查看自己的账号列表 |
| 农场状态 | 查看账号运行状态 |
| 启动农场 <账号ID> | 启动账号 |
| 停止农场 <账号ID> | 停止账号 |
| 更新农场Code <账号ID> <Code> | 更新 Code 并启动 |
| 农场日志 <账号ID> | 查看账号日志 |
| 添加农场账号 <uin> <code> | 添加新账号 |
| 删除农场账号 <账号ID> | 删除账号 |
| 申请端点 | 获取专属 Webhook 端点 |
| 农场帮助 | 查看帮助菜单 |

> 管理员额外命令：`管理账号列表`、`添加管理员`、`分配账号` 等。
```
## 🌐 Webhook 推送

### 统一端点

```http
POST /report
Content-Type: application/json

{
  "title": "标题",
  "content": "账号: 123456\n消息内容"
}
```
### 专属端点
```
POST /{endpoint}/send
Content-Type: application/json

{
  "title": "标题",
  "content": "账号: 123456\n消息内容"
}
```

---

**5. 相关链接 + 社区支持 + 开源协议**

```markdown
## 🔗 相关链接

- PyPI：https://pypi.org/project/nonebot-plugin-qqfarm/
- GitHub：https://github.com/salus-A/nonebot-plugin-qqfarm
- 后端项目：https://github.com/smdk000/qq-farm-ui-pro-max
- 问题反馈：https://github.com/salus-A/nonebot-plugin-qqfarm/issues
```

## 💬 社区支持

如有问题或建议，欢迎提交 GitHub Issue 或加入交流群（QQ 群：227916149）。

## 📄 开源协议

MIT License © 2025 salus-A