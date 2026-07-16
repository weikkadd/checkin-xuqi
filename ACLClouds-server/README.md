# AclClouds 卡卡项目 自动续期

> GitHub Actions + Playwright + Google OAuth + 自动续期 + TG 通知

## 📁 文件结构

```
checkin-gaming4/
├── .github/workflows/aclclouds-kaka.yml
├── ACLClouds-server/
│   ├── renew.py
│   └── README.md
```

## 🔧 工作原理

1. Playwright 打开 Chrome → `dash.aclclouds.com/login`
2. 点击 Google 登录 → 自动填写邮箱和密码
3. OAuth 回调 → 项目列表 → 找"卡卡"
4. 续期按钮（到期前 2 天出现）→ 点击续期
5. TG 推送结果

## 🚀 部署

### 1. 配置 Secrets

`Settings` → `Secrets and variables` → `Actions`

| Secret | 必填 | 说明 |
|---|---|---|
| `KAKA_GOOGLE_EMAIL` | ✅ | Google 邮箱 |
| `KAKA_GOOGLE_PASSWORD` | ✅ | Google 密码 / 应用专用密码 |
| `TG_BOT_TOKEN` | ❌ | Telegram Bot Token |
| `TG_CHAT_ID` | ❌ | Telegram Chat ID |

> ⚠️ 两步验证 → 使用[应用专用密码](https://myaccount.google.com/apppasswords)

### 2. 测试

Actions → `AclClouds-Kaka-Renew` → `Run workflow`

### 3. 自动运行

每天 UTC 01:00（北京时间 09:00）

## 📱 TG 通知示例

```
🎮 AclClouds 续期通知
🖥️项目: 卡卡
📊续期结果: ✅续期成功！
⏰耗时: 15.3s
```
