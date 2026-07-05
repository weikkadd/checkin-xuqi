---
title: Checkin New Panel
emoji: 🎮
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Checkin New Panel 🎮

自动化签到续期管理平台 - 支持 gaming4free / host2play / katabump 等多个免费服务器自动续期。

## ✨ 功能特性

- 🔗 **链接签到**：fetch 模式，快速签到（适合 host2play 等）
- 🌐 **浏览器访问**：Playwright 模式，点击按钮续期（适合 gaming4free）
- 🍪 **Cookie 注入**：跳过登录，直接用 Cookie 访问
- 🔐 **账号密码登录**：自动填表 + 提交
- 🔁 **循环点击**：gaming4free +90min 按钮专用，4 分钟冷却循环点击，上限 45h
- 🤖 **Turnstile 验证**：增强反检测 + 真实鼠标点击 + 11 项指纹伪造
- ⏰ **Cron 定时**：每 6 小时自动续期，支持每任务独立 Cron
- 🔒 **任务级锁**：防止同一任务并发执行
- 📱 **TG 通知**：续期结果发到 Telegram 群，带功能按钮
- 🖥️ **Web 面板**：可视化任务管理（Cloudflare Pages 前端）
- 📊 **日志记录**：每次执行结果 + 截图 + 错误信息

## 🏗️ 技术栈

- **后端**：Node.js 22 + Express + tRPC + Drizzle ORM + MySQL/TiDB
- **前端**：React 18 + Tailwind + tRPC client
- **浏览器自动化**：Playwright + playwright-extra + stealth
- **定时任务**：cron 库
- **通知**：Telegram Bot API
- **部署**：Docker / DCDeploy / zo.computer / HuggingFace Spaces

## 📦 部署方式

### 方式 1：Docker 部署（推荐）

```bash
docker build -t checkin-new-panel .
docker run -d --name checkin-api -p 3000:3000 \
  -e DATABASE_URL=mysql://... \
  -e TG_BOT_TOKEN=... \
  -e TG_CHAT_ID=... \
  -e AUTH_TOKEN=simple-token-ok \
  -e PORT=3000 \
  -e GLOBAL_CRON="0 0 */6 * * *" \
  checkin-new-panel
```

### 方式 2：DCDeploy 部署

1. Fork 本仓库
2. 在 DCDeploy 创建环境，选 GitHub 部署
3. 配置环境变量（见下方）
4. 选 DCD-3（1GB）或更高配置
5. 部署

### 方式 3：VPS 部署（最稳定，需 1GB+ 内存）

适合有自己 VPS 的用户，7x24 稳定运行，不休眠。

```bash
# 1. SSH 连接 VPS
ssh root@你的VPS_IP -p 端口

# 2. 安装 Node.js 22
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs git

# 3. 克隆代码
git clone https://github.com/weikkadd/checkin-new-panel.git
cd checkin-new-panel

# 4. 安装依赖
npm install
npx playwright install chromium
npx playwright install-deps chromium

# 5. 配置环境变量
cat > .env << 'EOF'
DATABASE_URL=mysql://user:pass@host:4000/db?ssl=...
TG_BOT_TOKEN=你的TG机器人Token
TG_CHAT_ID=你的TG群ID
AUTH_TOKEN=simple-token-ok
PORT=3000
GLOBAL_CRON=0 0 */6 * * *
EOF

# 6. 编译
npx tsc

# 7. 用 pm2 守护进程（7x24 运行）
npm install -g pm2
pm2 start dist/server/index.js --name checkin-api
pm2 save
pm2 startup  # 设置开机自启
```

### 方式 4：zo.computer 部署（免费）

```bash
git clone https://github.com/weikkadd/checkin-new-panel.git
cd checkin-new-panel
npm install
npx tsc
# 配置 .env
# 用 supervisord 守护进程
# 配合 CF Worker 保活防休眠
```

### 方式 5：HuggingFace Spaces 部署（免费 16GB）

- SDK: Docker
- 端口: 7860
- 内存: 16GB（免费层）
- 基础镜像: Playwright 官方镜像（内置 Chromium）

## ⚙️ 环境变量

### 必需

| 变量 | 说明 | 示例 |
|------|------|------|
| `DATABASE_URL` | TiDB/MySQL 数据库连接串 | `mysql://user:pass@host:4000/db?ssl=...` |
| `AUTH_TOKEN` | API 鉴权 token | `simple-token-ok` |

### 可选

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `TG_BOT_TOKEN` | Telegram Bot Token | - |
| `TG_CHAT_ID` | Telegram Chat ID | - |
| `PORT` | 服务端口 | `3000` |
| `GLOBAL_CRON` | 全局 Cron 表达式 | `0 0 */6 * * *` |
| `TG_API_PROXY` | TG API 代理 | `https://api.telegram.org` |

## 🗄️ 数据库表结构

### tasks 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| name | varchar | 任务名称 |
| url | text | 站点地址 |
| taskType | varchar | 任务类型：link/login/cookie/browser |
| renewButtonText | varchar | 续期按钮文字（如 +90 min）|
| cookies | text | 登录 Cookie |
| customScript | text | 自定义脚本（LOOP_MODE 等）|
| cronExpr | varchar | 独立 Cron 表达式 |
| execMode | int | 执行模式：1=自动+手动, 2=仅手动, 3=仅自动 |
| enabled | boolean | 是否启用 |

### customScript 配置示例

#### gaming4free 循环点击模式

```
LOOP_MODE:1
COOLDOWN_SEC:240
CAP_HOURS:45
MAX_CLICKS:35
```

#### 成功关键词

```
SUCCESS_KEYWORD:续期成功|renewed|已续期|Renew server
```

## 🎯 任务类型说明

### 🔗 link（链接签到）
- 仅访问 URL，用 fetch
- 最快最省资源
- 适合 host2play / hax 等

### 🌐 browser（浏览器访问）
- Playwright 打开页面 + 点击按钮
- 可选循环点击模式
- 适合 gaming4free（+90 min 按钮）

### 🍪 cookie（Cookie 注入）
- Playwright + Cookie 跳过登录
- 适合 Discord/Google OAuth 站点

### 🔐 login（账号密码登录）
- Playwright 自动填表 + 提交
- 适合普通登录站点

## 🔧 管理命令

### supervisord（zo.computer）

```bash
# 重启服务
supervisorctl -c /etc/zo/supervisord-user.conf restart checkin-api

# 看状态
supervisorctl -c /etc/zo/supervisord-user.conf status

# 看日志
tail -f /dev/shm/checkin-api.log
```

### pm2

```bash
pm2 start dist/server/index.js --name checkin-api
pm2 restart checkin-api
pm2 logs checkin-api
```

### API 接口

```bash
# 健康检查
curl http://localhost:3000/ping

# 触发任务
curl -X POST http://localhost:3000/trpc/task.runNow?batch=1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer simple-token-ok" \
  -d '{"0":{"json":{"taskId":1}}}'

# 查看任务日志
curl http://localhost:3000/trpc/task.getLogs?input={"json":{"taskId":1,"limit":5}} \
  -H "Authorization: Bearer simple-token-ok"
```

## 📱 TG 通知功能

- ✅ 续期成功通知（带剩余时间）
- ❌ 续期失败告警
- 🔘 群内按钮：自动续期 / 手动签到 / 测试通知 / 查看日志 / 编辑任务 / 打开面板

## 🔄 防休眠方案

### zo.computer
- 用 CF Worker 每 3 分钟 ping `/ping`
- supervisord 守护进程，崩溃自动重启

### HuggingFace Spaces
- 用 UptimeRobot 每 5 分钟 ping `/ping`
- 48 小时不访问会休眠

### DCDeploy / Railway
- PaaS 平台，不休眠
- 按用量计费

## 📄 License

MIT

## 👤 Author

weikkadd (weimei)
