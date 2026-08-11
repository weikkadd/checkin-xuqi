# 自动续期合集 🎮

多个免费 Minecraft / VPS 面板的 GitHub Actions 自动续期合集。

> 所有方案都基于 GitHub Actions（公开仓库免费），无需 VPS。

---

## 📦 已支持面板

| 面板 | 目录 | 登录方式 | 备注 |
| --- | --- | --- | --- |
| [ACLClouds](https://dash.aclclouds.com/projects) | [`ACLClouds-server/`](ACLClouds-server/) | Cookie 注入 | 支持 Turnstile 浏览器版 |
| [Gaming4Free](https://control.gaming4free.net/) | [`gaming4free-renew/`](gaming4free-renew/) | Cookie 注入 | SeleniumBase UC + Turnstile |

---

## 🚀 快速部署

### 1. Fork 仓库

点击 GitHub 右上角 **Fork** 按钮，将仓库复制到你自己的 GitHub 账号。

### 2. 配置 Secrets

进入 `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

添加以下 Secret（根据你要续期的面板）：

#### ACLClouds

| Secret | 必填 | 格式示例 |
| --- | --- | --- |
| `ACL_COOKIES` | 是 | `__Host-aclclouds_session=xxx; XSRF-TOKEN=yyy` |
| `ACL_ACCOUNTS` | 多账号 | `名称1\|\|\|session=xxx; XSRF-TOKEN=yyy` |
| `PROXY_URL` | 推荐 | `hysteria2://user:pass@server:port` |
| `TG_BOT_TOKEN` | 是 | Telegram Bot Token |
| `TG_CHAT_ID` | 是 | Telegram Chat ID |

**获取 Cookie：**
1. 浏览器登录 https://aclclouds.com
2. F12 → Application → Cookies → https://aclclouds.com
3. 复制所有 Cookie，确保包含 `__Host-aclclouds_session` 和 `XSRF-TOKEN`

---

#### Gaming4Free

| Secret | 必填 | 格式示例 |
| --- | --- | --- |
| `GAME4FREE_COOKIE` | 单账号 | `session=xxx; XSRF-TOKEN=yyy` |
| `GAME4FREE_RENEW_URL` | 单账号 | `https://control.gaming4free.net/server/xxx/console` |
| `GAME4FREE_ACCOUNTS` | 多账号 | `名称\|\|\|https://url\|\|\|session=xxx; XSRF-TOKEN=yyy` |
| `PROXY_URL` | 推荐 | `hysteria2://user:pass@server:port` |
| `TG_BOT_TOKEN` | 是 | Telegram Bot Token |
| `TG_CHAT_ID` | 是 | Telegram Chat ID |

**获取 Cookie：**
1. 浏览器登录 https://control.gaming4free.net
2. 进入服务器控制台页面
3. F12 → Application → Cookies → 复制全部 Cookie

---

### 3. 获取 Telegram Bot Token

1. 在 Telegram 搜索 `@BotFather`
2. 发送 `/newbot`，按提示创建 Bot
3. 复制获得的 Token（格式：`123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`）

### 4. 获取 Telegram Chat ID

1. 在 Telegram 搜索 `@userinfobot`
2. 发送 `/start`，获得你的 Chat ID（纯数字）

---

## 📁 目录结构

```
.
├── .github/workflows/
│   ├── aclclouds-browser.yml    # ACLClouds 浏览器版（推荐）
│   ├── aclclouds-kaka.yml       # ACLClouds 纯 API 版（备用）
│   └── gaming4free.yml          # Gaming4Free 续期
├── ACLClouds-server/            # ACLClouds 脚本
├── gaming4free-renew/           # Gaming4Free 脚本
└── diagnose.py                  # 通用诊断脚本
```

---

## ▶️ 运行 Workflow

### GitHub Actions（推荐）

1. 进入 `Actions` 标签
2. 选择要运行的 workflow
3. 点击 `Run workflow` → `Run workflow`

### 定时任务

- **ACLClouds**: 每 6 小时 (UTC 00,06,12,18)
- **Gaming4Free**: 每 6 小时 (UTC 00,06,12,18)
- **Host2Play**: 每天 5 次 (UTC 00:00, 05:30, 11:00, 16:30, 22:00)

---

## 📱 Telegram 通知示例

```
🎮 ACLClouds 续期通知

✅ 续期成功
👤 账号: main
📊 服务器: prod-01 (ID: 12345)
⏰ 续期后剩余: 72h 30m
```

---

## 🐛 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| Cookie 为空 / 注入失败 | Secret 未设置或格式错误 | 检查 Secret 是否包含完整 Cookie 字符串 |
| 代理连接失败 | sing-box 未启动或节点失效 | 检查 PROXY_URL 格式，确认节点有效 |
| Turnstile 一直加载 | 代理 IP 被 CF 识别 | 更换代理或直连 |
| 续期按钮找不到 | 页面结构变化 / Cookie 过期 | 重新登录获取 Cookie |
| SeleniumBase 导入失败 | Chrome 未安装 | 已在 workflow 中添加安装步骤 |
| Telegram 收不到通知 | TG_BOT_TOKEN / TG_CHAT_ID 未设置 | 检查 Secret 是否配置正确 |

---

## 📄 License

MIT
