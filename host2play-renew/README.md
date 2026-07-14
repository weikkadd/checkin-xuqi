# host2play 自动续期（GHA + WARP + reCAPTCHA 音频识别）

> 利用 GitHub Actions + Cloudflare WARP + DrissionPage + reCAPTCHA 音频识别自动续期 host2play 服务器。

## 🎯 原理

- **WARP 代理** — Cloudflare 自家 IP
- **DrissionPage** — 真实浏览器，反检测
- **Cookie 注入** — 跳过登录
- **reCAPTCHA 音频识别** — 用 SpeechRecognition 识别音频验证码

## 📁 文件结构

```
host2play-renew/
├── main.py              # 续期主脚本
├── requirements.txt     # Python 依赖
└── output/screenshots/  # 截图输出目录
```

## 🚀 部署步骤

### 1. 配置 Secrets

进入仓库 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

| Secret 名 | 必填 | 说明 |
|---|---|---|
| `H2P_RENEW_URL` | ✅ | 续期页面 URL，如 `https://host2play.gratis/server/renew?i=xxx` |
| `H2P_COOKIE` | ✅ | host2play 的 cookie 字符串 |
| `TG_BOT_TOKEN` | ❌ | Telegram Bot Token（要通知才填） |
| `TG_CHAT_ID` | ❌ | Telegram Chat ID |

### 2. 获取 Cookie

1. 浏览器登录 `https://host2play.gratis`
2. 按 F12 → Application → Cookies → `https://host2play.gratis`
3. 把所有 cookie 按 `Name=Value; ` 格式拼接

或者用 Cookie-Editor 插件一键导出（Header String 格式）。

### 3. 手动触发测试

`Actions` → `host2play 续期` → `Run workflow`

### 4. 自动续期

默认 cron：
- UTC `00:00, 11:00, 22:00` = 北京 `08:00, 19:00, 06:00`
- UTC `05:30, 16:30` = 北京 `13:30, 00:30`

每天 5 次，足够维持续期。

## 🔧 reCAPTCHA 音频识别流程

```
1. 点击 Renew server 按钮
2. 弹出 reCAPTCHA checkbox
3. 点击 checkbox
4. 如果直接通过 → 点 Renew
5. 如果弹图片选择 → 切音频模式
6. 下载音频 → SpeechRecognition 识别
7. 输入结果 → 验证
8. 失败重试（最多 5 次）
```

## 📱 TG 通知示例

```
🎮 host2play
🚀 续期启动
⏰ 2026-07-07 16:00:00 (北京时间)

🎮 host2play
📊 当前剩余时间
⏳ 7h 57m

🎮 host2play
✅ 续期成功
⏰ 16:05:00 (北京)
⏳ 剩余: 7h 57m → 31h 57m
➕ 增加: 24h 0m
```

## ⚠️ 注意事项

1. **reCAPTCHA 音频识别成功率约 60%**，失败会自动重试
2. **Cookie 有效期**：一般 7-30 天，过期需重新复制
3. **WARP 代理**：Cloudflare 自家 IP，reCAPTCHA 有时直接通过
4. **必须用公开仓库**：私有仓库 GHA 分钟数不够

## 🐛 故障排查

| 问题 | 解决 |
|---|---|
| Cookie 失效 | 重新复制 cookie 更新 `H2P_COOKIE` |
| reCAPTCHA 未通过 | 音频识别失败，多重跑几次 |
| 找不到 Renew 按钮 | 检查 `H2P_RENEW_URL` 是否正确 |

## 📄 License

MIT
