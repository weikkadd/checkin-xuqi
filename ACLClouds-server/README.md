# ACLClouds 自动续期

为 [https://aclclouds.com/dashboard/projects](https://aclclouds.com/dashboard/projects) 上的免费 Minecraft / VPS 服务器自动续期。

## 📐 方案说明

| Workflow | 脚本 | 原理 |
|----------|------|------|
| **`ACLClouds-浏览器续期`** | `renew_browser.py` | SeleniumBase UC mode 打开真实浏览器，能过 Cloudflare Turnstile |

> 💡 详细部署步骤见 [../DEPLOY-GUIDE.md](../DEPLOY-GUIDE.md)

## 工作原理

- 用 SeleniumBase UC mode 打开浏览器
- 复用 Gaming4Free 的 CF Turnstile 破解方案 (CDP 点击 checkbox)
- 先用 API 获取服务器列表 (快), 再用浏览器续期 (能过验证)

## 部署步骤

### 1. Fork / Clone 本仓库到你的 GitHub

### 2. 获取 Cookie

1. 用浏览器登录 https://aclclouds.com
2. 按 `F12` → `Application` → `Cookies` → `https://aclclouds.com`
3. 复制全部 Cookie 为字符串 (格式: `key1=value1; key2=value2; ...`)

> 必须包含: `XSRF-TOKEN` 和 `__Host-aclclouds_session` (或 `aclclouds_session`)

### 3. 配置 GitHub Secrets

| Secret | 必填 | 说明 |
| --- | --- | --- |
| `ACL_COOKIES` | ✅ | 单账号 Cookie 字符串 |
| `ACL_ACCOUNTS` | 多账号 | 每行 `name\|\|\|cookie` |
| `PROXY_URL` | ✅ | sing-box 节点链接 (hysteria2/tuic/vless) |
| `TG_BOT_TOKEN` | 通知 | Telegram Bot Token |
| `TG_CHAT_ID` | 通知 | Chat ID |

### 4. 触发 Workflow

进入仓库的 `Actions` 标签 → 选择 `ACLClouds-浏览器续期` → `Run workflow`

## 续期规则

| 服务类型 | 可续期阈值 |
| --- | --- |
| 免费服务 (普通) | 到期前 2 天 |
| 免费 Minecraft | 到期前 2 小时 |
| 付费服务 | 4 天前 |

脚本默认 `< 48h` 就尝试续期, 后端会返回 `renewNotAvailableYet` 跳过未到期服务器。

## 浏览器版工作流程

1. 用 API 获取服务器列表 + 到期时间 (快)
2. 筛选剩余 < 48h 的服务器
3. 启动 SeleniumBase UC mode 浏览器
4. 注入 Cookie (自动改名 `aclclouds_session` → `__Host-aclclouds_session`)
5. 对每个服务器:
   - 打开 `/server/{id}` 页面
   - 找续期按钮 (多种选择器 + JS 兜底)
   - 点击后处理 CF Turnstile (CDP 点击 checkbox)
   - 检查续期结果 (toast 通知)
6. TG 通知汇总

## 本地调试

```bash
pip install -r requirements.txt
export ACL_COOKIES="XSRF-TOKEN=...; aclclouds_session=..."
xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24" python renew_browser.py
```

## TG 通知示例

```
🎮 ACLClouds 续期汇总 [main]
✅ 成功: 2 | ❌ 失败: 0
📊 总计: 2 台服务器
```

## 维护

- Cookie 有效期约 7-30 天, 过期后重新登录复制
- 浏览器版需要代理 (PROXY_URL), 否则 CF 验证可能过不去
- 阈值: 修改 `RENEW_THRESHOLD_HOURS` 环境变量 (默认 48h)
