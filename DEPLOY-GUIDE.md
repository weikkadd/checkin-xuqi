# ACLClouds 自动续期部署说明

## 📐 方案说明

| Workflow | 脚本 | 原理 | 推荐度 |
|----------|------|------|--------|
| **`ACLClouds-浏览器续期`** | `renew_browser.py` | SeleniumBase UC mode 打开真实浏览器，能过 Cloudflare Turnstile | ⭐⭐⭐⭐⭐ |

仓库只保留这一个 ACLClouds 续期 workflow。原来还有一个纯 API 版（`ACLClouds-卡卡续期`）已删除，因为它过不了 Cloudflare Turnstile 验证。

> 💡 详细技术文档见 [`ACLClouds-server/README.md`](ACLClouds-server/README.md)

---

## 🚀 部署步骤（推荐：浏览器版）

### 1. Fork 仓库

点 GitHub 右上角 **Fork** 把仓库 fork 到你的账户。

### 2. 获取 Cookie

1. 浏览器登录 https://aclclouds.com
2. 按 `F12` → **Application** 标签 → **Cookies** → `https://aclclouds.com`
3. 复制全部 Cookie 为字符串（格式：`key1=value1; key2=value2; ...`）

⚠️ **必须包含**：
- `XSRF-TOKEN`
- `aclclouds_session` 或 `__Host-aclclouds_session`

### 3. 获取代理（浏览器版必需）

ACLClouds 用 Cloudflare Turnstile 验证，GitHub Actions 的 Azure IP 会被 CF 风控。需要一个代理节点（推荐住宅 IP）：

支持的协议：
- `hysteria2://` 或 `hy2://`（推荐）
- `tuic://`
- `vless://`（需要 REALITY 或 TLS）
- `vmess://`
- `trojan://`
- `ss://`

### 4. 配置 GitHub Secrets

进入仓库 → **Settings → Secrets and variables → Actions → New repository secret**

| Secret 名 | 必填 | 示例 | 说明 |
|-----------|------|------|------|
| `ACL_COOKIES` | ✅ | `XSRF-TOKEN=xxx; aclclouds_session=yyy; ...` | 单账号 Cookie 字符串 |
| `ACL_ACCOUNTS` | 多账号 | `名称1\|\|\|cookie1\n名称2\|\|\|cookie2` | 多账号时每行一个 |
| `PROXY_URL` | ✅ 浏览器版 | `hysteria2://user:pass@server:port` | 代理节点链接 |
| `TG_BOT_TOKEN` | 推荐 | `123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` | Telegram Bot Token |
| `TG_CHAT_ID` | 推荐 | `123456789` | Telegram Chat ID |
| `RENEW_THRESHOLD_HOURS` | 可选 | `48`（默认） | 续期阈值（小时） |

### 5. 触发 Workflow

1. 进入仓库的 **Actions** 标签
2. 左侧选择 **`ACLClouds-浏览器续期`**
3. 右上角点 **`Run workflow`** → `Run workflow`

### 6. 查看结果

- 等运行完成（约 2-5 分钟）
- 看 workflow 日志确认续期成功
- Telegram 会收到通知：

```
🎮 ACLClouds 续期通知

✅ 续期成功
👤 服务器: main (329ae281)
📅 当前剩余: 47h 30m
```

---

## 📅 自动触发时间

| Workflow | 定时（UTC） | 北京时间 |
|----------|-------------|---------|
| `ACLClouds-浏览器续期` | 每 6 小时（00, 06, 12, 18 点） | 08:00, 14:00, 20:00, 02:00 |

---

## ❓ 常见问题

### Q1: Cookie 返回 401 Unauthorized？

检查：
1. Cookie 是否包含 `XSRF-TOKEN` 和 `aclclouds_session` / `__Host-aclclouds_session`
2. Cookie 是否过期（有效期约 7-30 天）
3. 浏览器版会自动把 `aclclouds_session` 重命名为 `__Host-aclclouds_session`

### Q2: 浏览器版日志显示 "Cloudflare 验证未通过"？

这是 CF 风控了你的代理 IP：
- ❌ AWS / GCP / Azure / DigitalOcean 等 IDC IP → 大概率被风控
- ✅ 日本 / 韩国 / 香港 / 台湾的住宅宽带 IP → 推荐选择
- 重新获取 `cf_clearance` Cookie 并配置到 `CF_CLEARANCE` Secret（可选，但能提高成功率）

### Q3: 续期失败，提示 "renewNotAvailableYet"？

ACLClouds 限制：到期前 2 天（48 小时）才能续期。脚本默认阈值 `< 48h` 触发续期，后端会返回 `renewNotAvailableYet` 跳过未到期服务器。这是**正常行为**，不是错误。

### Q4: 如何立即测试续期流程？

把 `RENEW_THRESHOLD_HOURS` 改成 `200`（或更大的值），强制让脚本认为剩余时间不够，触发完整流程。

### Q5: 续期成功后多久会再次运行？

workflow 每 6 小时自动跑一次。但 ACLClouds 续期后会进入 **5 分钟冷却**（cooldown），冷却期内再次续期不会增加时间。所以多次跑只是确认状态，不会扣费。

---

## 📁 项目结构

```
ACLClouds-server/
├── renew_browser.py      # 浏览器版续期脚本
├── requirements.txt
└── README.md             # 详细技术文档

.github/workflows/
└── aclclouds-browser.yml  # 唯一的 ACLClouds workflow
```

---

## 🔗 相关链接

- ACLClouds 控制台：https://aclclouds.com/dashboard/projects
- Telegram BotFather：https://t.me/BotFather
- Telegram User Info Bot：https://t.me/userinfobot
