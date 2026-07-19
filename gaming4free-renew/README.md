# Gaming4Free 自动续期

> GitHub Actions + sing-box 代理 + SeleniumBase UC mode + Cloudflare Turnstile 验证。
>
> 面板地址：<https://control.gaming4free.net/>

## 📁 文件结构

```
checkin-xuqi/
├── .github/workflows/gaming4free.yml
└── gaming4free-renew/
    ├── renew.py
    └── README.md
```

## 🚀 部署步骤

### 1. 配置 Secrets

进入仓库 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

支持 **单账号** 或 **多账号** 两种配置方式：

#### 方式 A：单账号（URL + Cookie 分开，简单）

| Secret 名 | 必填 | 说明 |
|---|---|---|
| `GAME4FREE_RENEW_URL` | ✅ | 续期页面 URL，如 `https://control.gaming4free.net/server/247d3700/console` |
| `GAME4FREE_COOKIE` | ✅ | gaming4free 的 Cookie 字符串 |
| `PROXY_URL` | ✅ | sing-box 节点链接（tuic/vless/vmess/trojan/hysteria2/socks5） |
| `TG_BOT_TOKEN` | ❌ | Telegram Bot Token（要通知才填） |
| `TG_CHAT_ID` | ❌ | Telegram Chat ID |

#### 方式 B：多账号（合并到一个 Secret）

| Secret 名 | 必填 | 说明 |
|---|---|---|
| `GAME4FREE_ACCOUNTS` | ✅ | 多账号配置，每行一个：`名称\|\|\|URL\|\|\|Cookie` |
| `PROXY_URL` | ✅ | sing-box 节点链接 |
| `TG_BOT_TOKEN` | ❌ | Telegram Bot Token |
| `TG_CHAT_ID` | ❌ | Telegram Chat ID |

**`GAME4FREE_ACCOUNTS` 格式示例**：

```
我的服务器1|||https://control.gaming4free.net/server/abc123/console|||_ga=GA1.1.xxx; XSRF-TOKEN=xxx; gaming4free_session=xxx
我的服务器2|||https://control.gaming4free.net/server/def456/console|||_ga=GA1.1.xxx; XSRF-TOKEN=xxx; gaming4free_session=xxx
```

> 字段用 `|||`（三个竖线）分隔，因为 Cookie 里常含 `;` 和 `=`，用逗号会冲突。
>
> 也可以省略名称，只写 `URL|||Cookie`，脚本会自动用 `server-1` / `server-2` 命名。

### 2. 获取 Cookie

1. 浏览器登录 <https://control.gaming4free.net>
2. 按 `F12` → `Application` → `Cookies` → `https://control.gaming4free.net`
3. 复制全部 Cookie 为一个字符串（格式：`name1=value1; name2=value2; ...`）

> 必须包含这两个关键 Cookie：`XSRF-TOKEN` 和 `gaming4free_session`
>
> 推荐用 **Cookie-Editor** / **EditThisCookie** 扩展一键导出 → "Export as Header String"

#### Cookie 字符串示例

```
_ga=GA1.1.883012624.1783430975; remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d=eyJpdiI6...; XSRF-TOKEN=eyJpdiI6...; gaming4free_session=eyJpdiI6...
```

### 3. 获取 PROXY_URL

sing-box 节点链接，复用其他续期仓库（aida/katabump/hidencloud 等）的同一个节点即可：

```
tuic://uuid:password@host:port?insecure=1
vless://uuid@host:port?type=ws&security=tls&path=/
vmess://eyJ2Ijoi...
hysteria2://uuid@host:port?sni=xxx
```

### 4. 手动触发测试

Actions → `Game4Free 自动续期` → `Run workflow`

### 5. 自动续期

默认每天 UTC 01:00 自动运行（北京时间 09:00）。

## 🔧 工作原理

1. sing-box 启动代理（出口为住宅 IP，避免 Cloudflare 黑名单）
2. SeleniumBase UC mode 启动 Chrome（绕过 navigator.webdriver 检测）
3. 注入完整 Cookie 字符串登录（无需密码 / OAuth）
4. JS 查找 +90 min 按钮，用原生 `element.click()` 触发 Livewire 事件
5. `uc_gui_click_captcha` + `xdotool` 系统级点击处理 Cloudflare Turnstile
6. 重新加载页面比对剩余时间判断成功

## 📱 TG 通知示例

```
🎮 Game4Free 续期通知
⏰ 2026-07-19 09:00:00
🖥️ 服务器: 我的服务器
🔢 剩余时间: 02:13:22
📊 续期结果: ✅ 续期成功
```

## ⚠️ 注意事项

1. **Cookie 有效期**：约 7-30 天，过期需重新复制
2. **Turnstile 通过率**：依赖代理 IP 信誉，住宅 IP > WARP > 机房 IP
3. **必须用公开仓库**：私有仓库 GHA 分钟数不够
4. **48h 上限**：gaming4free 免费服务器 48 小时封顶，超过自动跳过

## 🐛 故障排查

| 问题 | 解决 |
|---|---|
| `❌ 未配置账号信息` | 检查 `GAME4FREE_RENEW_URL` + `GAME4FREE_COOKIE` 是否都配置了 |
| Cookie 失效 | 重新登录复制 Cookie 更新 `GAME4FREE_COOKIE` |
| Turnstile 未通过 | 换代理节点（住宅 IP 最佳），或多次重试 |
| 按钮找不到 | 检查 `GAME4FREE_RENEW_URL` 是否正确（必须含 server slug） |

## 📄 License

MIT
