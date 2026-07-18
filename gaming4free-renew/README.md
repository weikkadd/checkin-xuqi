# Gaming4Free 自动续期（GHA + sing-box + SeleniumBase UC mode）
https://control.gaming4free.net/

## 📁 文件结构

```
checkin-xuqi/
├── .github/workflows/gaming4free.yml
└── gaming4free-renew/
    ├── renew.py
    ├── requirements.txt
    └── README.md
```

## 🚀 部署步骤

### 1. 配置 Secrets

进入仓库 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

| Secret 名 | 必填 | 说明 |
| --- | --- | --- |
| `GAME4FREE_ACCOUNT` | ✅ | 格式：`服务器名,续期URL`（英文逗号分隔），多账号每行一个 |
| `GAME4FREE_COOKIE` | ✅ | 浏览器登录 control.gaming4free.net 后复制的完整 Cookie 字符串 |
| `PROXY_URL` | ✅ | sing-box 节点链接（tuic/vless/vmess/trojan/hysteria2/socks5） |
| `TG_BOT_TOKEN` | ❌ | Telegram Bot Token（不填则不发通知） |
| `TG_CHAT_ID` | ❌ | 接收通知的 Telegram Chat ID |

#### `GAME4FREE_ACCOUNT` 示例

单账号：
```
我的服务器,https://control.gaming4free.net/server/247d3700/console
```

多账号（每行一个）：
```
服务器1,https://control.gaming4free.net/server/abc123/console
服务器2,https://control.gaming4free.net/server/def456/console
```

#### `GAME4FREE_COOKIE` 示例

浏览器登录 <https://control.gaming4free.net> → F12 → Application → Cookies → 复制全部 Cookie 为一个字符串：

```
_ga=GA1.1.883012624.1783430975; remember_web_592f0a8b...; XSRF-TOKEN=eyJpdiI6...; gaming4free_session=eyJpdiI6...
```

推荐用 **EditThisCookie** / **Cookie-Editor** 扩展 → "Export as Header String" 一键导出。

#### `PROXY_URL` 示例

```
tuic://uuid:password@host:port?insecure=1
vless://uuid@host:port?type=ws&security=tls&path=/
vmess://eyJ2Ijoi...
```

复用其他续期仓库（aida/katabump/hidencloud 等）的同一个节点即可。

### 2. 手动触发测试

Actions → `Game4Free-Renew` → `Run workflow`

### 3. 自动续期

默认每天 UTC 01:00 自动运行。

## 📱 TG 通知示例

```
🎮 Gaming4Free Pro
🖥服务器: 我的服务器
⏰时间: 2026-07-18 14:45:25
📊状态: ✅ Pro续期成功
⏱剩余: 01:44:55
⚙️模式: Renew-Pro v10
```

## 🔧 工作原理

1. sing-box 启动代理（出口为住宅 IP，避免 Cloudflare 黑名单）
2. SeleniumBase UC mode 启动 Chrome（绕过 navigator.webdriver 检测）
3. 注入 Cookie 登录（无需密码 / OAuth）
4. 点击 `+ 90 min` 按钮，处理 Turnstile 验证
5. 等待按钮冷却结束，重复点击直到 48h cap
