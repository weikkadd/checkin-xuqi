# AclClouds 卡卡项目 自动续期

> GitHub Actions + Playwright + Google OAuth 登录 + 自动续期 + TG 通知。

## 📁 文件结构

```
checkin-gaming4/
├── .github/workflows/aclclouds-kaka.yml
├── aclclouds-kaka-renew/
│   ├── renew.py
│   └── README.md
```

## 🔧 工作原理

1. Playwright 打开 Chrome，导航到 `dash.aclclouds.com/login`
2. 点击 Google 登录按钮，进入 Google OAuth 流程
3. 自动填写邮箱和密码
4. 回到项目列表，找到"卡卡"项目
5. 检查续期按钮（到期前 2 天出现），点击续期
6. TG 推送执行结果

## 🚀 部署步骤

### 1. 配置 Secrets

进入仓库 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

| Secret 名 | 必填 | 说明 |
|---|---|---|
| `KAKA_GOOGLE_EMAIL` | ✅ | Google 账号邮箱 |
| `KAKA_GOOGLE_PASSWORD` | ✅ | Google 账号密码 |
| `TG_BOT_TOKEN` | ❌ | Telegram Bot Token |
| `TG_CHAT_ID` | ❌ | Telegram Chat ID |

> ⚠️ 如果 Google 账号开了两步验证，需要使用应用专用密码。

### 2. 手动触发测试

Actions → `AclClouds-Kaka-Renew` → `Run workflow`

### 3. 自动续期

默认每天 UTC 01:00 自动运行。可在 `.github/workflows/aclclouds-kaka.yml` 中修改 cron 表达式。

## 📱 TG 通知示例

```
🎮 AclClouds 续期通知
🖥️项目: 卡卡
📊续期结果: ✅续期成功！
⏰耗时: 15.3s
```
