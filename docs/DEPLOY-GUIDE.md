# 部署指南

---

## 目录

- [方式 1：VPS 部署（最稳定，推荐）](#方式-1vps-部署最稳定推荐)
- [方式 2：Docker 部署](#方式-2docker-部署)
- [方式 3：zo.computer 部署（免费）](#方式-3zocomputer-部署免费)
- [方式 4：DCDeploy 部署（付费，按量计费）](#方式-4dcdeploy-部署付费按量计费)
- [方式 5：HuggingFace Spaces 部署（免费 16GB）](#方式-5huggingface-spaces-部署免费-16gb)
- [方式 6：Cloudflare Pages 前端部署](#方式-6cloudflare-pages-前端部署)
- [方式 7：CF Worker 保活服务](#方式-7cf-worker-保活服务)
- [环境变量说明](#环境变量说明)
- [常用管理命令](#常用管理命令)

---

## 方式 1：VPS 部署（最稳定，推荐）

适合有自己 VPS 的用户，7x24 稳定运行，不休眠。

### 要求
- VPS 内存 ≥ 1GB（推荐 2GB+）
- 系统：Ubuntu 22.04 / Debian 12

### 1.1 SSH 连接 VPS

```bash
ssh root@你的VPS_IP -p 端口号
```

### 1.2 安装 Node.js 22 和 Git

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs git
```

验证：
```bash
node -v   # 应显示 v22.x.x
npm -v    # 应显示 10.x.x
```

### 1.3 克隆代码

```bash
cd /home
git clone https://github.com/weikkadd/checkin-new-panel.git
cd checkin-new-panel
```

### 1.4 安装依赖

```bash
npm install
```

### 1.5 安装 Playwright + Chromium

```bash
npx playwright install chromium
npx playwright install-deps chromium
```

> 这会下载 Chromium（约 150MB）和系统依赖库。

### 1.6 配置环境变量

```bash
cat > .env << 'EOF'
DATABASE_URL=mysql://用户名:密码@主机:4000/数据库名?ssl=%7B%22rejectUnauthorized%22%3Atrue%7D
TG_BOT_TOKEN=你的TG机器人Token
TG_CHAT_ID=你的TG群ID
AUTH_TOKEN=simple-token-ok
PORT=3000
GLOBAL_CRON=0 0 */6 * * *
EOF
```

### 1.7 编译 TypeScript

```bash
npx tsc
```

### 1.8 测试运行

```bash
node dist/server/index.js
```

应该看到：
```
[DB] ✅ 数据库连接测试成功
全局签到定时任务已启动
服务运行在端口: 3000
```

按 `Ctrl+C` 停止。

### 1.9 安装 pm2 守护进程

```bash
npm install -g pm2
```

### 1.10 启动服务

```bash
cd /home/checkin-new-panel
pm2 start dist/server/index.js --name checkin-api
```

验证：
```bash
pm2 list          # 应看到 checkin-api 状态 online
curl -s http://localhost:3000/ping   # 应返回 ok
```

### 1.11 设置开机自启

```bash
pm2 save
pm2 startup
```

> `pm2 startup` 会输出一条命令，复制并执行那条命令。

### 1.12（可选）Nginx 反向代理 + HTTPS

```bash
apt install -y nginx certbot python3-certbot-nginx

cat > /etc/nginx/sites-available/checkin-api << 'EOF'
server {
    listen 80;
    server_name your-domain.com;
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

ln -s /etc/nginx/sites-available/checkin-api /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# 配置 HTTPS（需要域名）
certbot --nginx -d your-domain.com
```

---

## 方式 2：Docker 部署

适合有 Docker 环境的用户。

### 2.1 克隆代码

```bash
git clone https://github.com/weikkadd/checkin-new-panel.git
cd checkin-new-panel
```

### 2.2 构建镜像

```bash
docker build -t checkin-new-panel .
```

### 2.3 启动容器

```bash
docker run -d --name checkin-api -p 3000:3000 \
  -e DATABASE_URL="mysql://用户名:密码@主机:4000/数据库名?ssl=%7B%22rejectUnauthorized%22%3Atrue%7D" \
  -e TG_BOT_TOKEN="你的TG机器人Token" \
  -e TG_CHAT_ID="你的TG群ID" \
  -e AUTH_TOKEN="simple-token-ok" \
  -e PORT=3000 \
  -e GLOBAL_CRON="0 0 */6 * * *" \
  checkin-new-panel
```

### 2.4 验证

```bash
docker logs checkin-api
curl -s http://localhost:3000/ping
```

### 2.5 Docker Compose（可选）

创建 `docker-compose.yml`：
```yaml
version: '3'
services:
  checkin-api:
    build: .
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=mysql://用户名:密码@主机:4000/数据库名?ssl=%7B%22rejectUnauthorized%22%3Atrue%7D
      - TG_BOT_TOKEN=你的TG机器人Token
      - TG_CHAT_ID=你的TG群ID
      - AUTH_TOKEN=simple-token-ok
      - PORT=3000
      - GLOBAL_CRON=0 0 */6 * * *
    restart: unless-stopped
```

启动：
```bash
docker-compose up -d
```

---

## 方式 3：zo.computer 部署（免费）

适合没有 VPS 的用户，免费 4GB 内存，但会休眠（需配合 CF Worker 保活）。

### 3.1 注册 zo.computer

打开 https://zo.computer 注册账号。

### 3.2 打开终端

登录后打开 Terminal（终端）。

### 3.3 克隆代码

```bash
cd /home/workspace
git clone https://github.com/weikkadd/checkin-new-panel.git
cd checkin-new-panel
```

### 3.4 安装依赖

```bash
npm install
npx playwright install chromium
npx playwright install-deps chromium
```

### 3.5 配置环境变量

```bash
cat > .env << 'EOF'
DATABASE_URL=mysql://用户名:密码@主机:4000/数据库名?ssl=%7B%22rejectUnauthorized%22%3Atrue%7D
TG_BOT_TOKEN=你的TG机器人Token
TG_CHAT_ID=你的TG群ID
AUTH_TOKEN=simple-token-ok
PORT=3000
GLOBAL_CRON=0 0 */6 * * *
EOF
```

### 3.6 编译并启动

```bash
npx tsc
node dist/server/index.js
```

### 3.7 用 supervisord 守护进程

zo.computer 自带 supervisord，配置文件在 `/etc/zo/supervisord-user.conf`。

添加 checkin-api 服务：
```ini
[program:checkin-api]
command=node dist/server/index.js
directory=/home/workspace/checkin-new-panel
environment=NODE_ENV="production",PORT="3000"
autostart=true
autorestart=true
```

重启：
```bash
supervisorctl -c /etc/zo/supervisord-user.conf restart checkin-api
```

### 3.8 配置 CF Worker 保活（必须！）

zo.computer 免费版会休眠，需要 CF Worker 每 3 分钟 ping 一次防止休眠。

详见 [方式 7：CF Worker 保活服务](#方式-7cf-worker-保活服务)。

---

## 方式 4：DCDeploy 部署（付费，按量计费）

印度 PaaS 平台，不休眠，按量计费。

### 4.1 注册 DCDeploy

打开 https://dash.dcdeploy.com 注册账号。

### 4.2 开通「优点」套餐

免费版只有 256MB 内存（不够跑 Playwright），需要开通「优点」套餐选 DCD-3（1GB）或更高。

### 4.3 创建环境

1. 点「创造环境」
2. 配置：
   - 名称：`checkin-api`
   - 来源：GitHub
   - 存储库：`https://github.com/weikkadd/checkin-new-panel`
   - 参考资料（ref）：`main`
   - 背景（Context）：`./`
   - Dockerfile Name：`./Dockerfile`
   - 端口：`3000`
   - 协议：`https`
   - 地区：Germany
   - 机器类型：DCD-3（1GB）或 DCD-4（2GB）
3. 添加环境变量（见下方）
4. 点 CONTINUE 部署

### 4.4 环境变量

| Name | Value |
|------|-------|
| `DATABASE_URL` | `mysql://...` |
| `TG_BOT_TOKEN` | `你的Token` |
| `TG_CHAT_ID` | `你的群ID` |
| `AUTH_TOKEN` | `simple-token-ok` |
| `PORT` | `3000` |
| `GLOBAL_CRON` | `0 0 */6 * * *` |

### 4.5 费用

| 机器 | 内存 | 月费 |
|------|------|------|
| DCD-3 | 1GB | ~$4/月 |
| DCD-4 | 2GB | ~$7/月 |

---

## 方式 5：HuggingFace Spaces 部署（免费 16GB）

免费 16GB 内存，48 小时不访问才休眠。

### 5.1 注册 HuggingFace

打开 https://huggingface.co 注册账号。

### 5.2 创建 Space

1. 打开 https://huggingface.co/new-space
2. 配置：
   - Space name：`checkin-api`
   - License：MIT
   - SDK：**Docker**
   - Hardware：**CPU basic (16GB RAM) - Free**
   - 可见性：**Public**
3. 点 Create Space

### 5.3 推送代码

```bash
git clone https://github.com/weikkadd/checkin-new-panel.git
cd checkin-new-panel

# 添加 HuggingFace 远程仓库
git remote add hf https://用户名:Token@huggingface.co/spaces/用户名/checkin-api

# 推送
git push hf main --force
```

### 5.4 配置环境变量

在 Space Settings → Variables and secrets 里添加：

| Name | Value | Type |
|------|-------|------|
| `DATABASE_URL` | `mysql://...` | Variable |
| `TG_BOT_TOKEN` | `你的Token` | Secret |
| `TG_CHAT_ID` | `你的群ID` | Variable |
| `AUTH_TOKEN` | `simple-token-ok` | Secret |
| `PORT` | `7860` | Variable |
| `GLOBAL_CRON` | `0 0 */6 * * *` | Variable |

> 注意：HuggingFace Spaces 端口必须是 `7860`。

### 5.5 配置 UptimeRobot 保活

- URL：`https://用户名-checkin-api.hf.space/ping`
- Interval：5 minutes

### 5.6 注意事项

- HuggingFace 可能检测到 Playwright 自动化并暂停 Space
- 如果被暂停，尝试更换账号或使用其他部署方式
- Dockerfile 必须使用非 root 用户（Playwright 镜像自带的 `pwuser`）

---

## 方式 6：Cloudflare Pages 前端部署

前端面板部署在 Cloudflare Pages，连接后端 API。

### 6.1 注册 Cloudflare

打开 https://dash.cloudflare.com 注册账号。

### 6.2 创建 Pages 项目

1. 进入 Workers & Pages
2. 点 Create application → Create Pages → Connect to Git
3. 选择 GitHub 仓库 `weikkadd/checkin-new-panel`
4. 配置：
   - Framework preset：None
   - Build command：`cd client && npm install && npm run build`
   - Build output directory：`client/dist`
5. 部署

### 6.3 配置环境变量

在 Settings → Environment variables 里添加：

| Name | Value |
|------|-------|
| `VITE_API_URL` | `https://你的后端地址/trpc` |

> Production 和 Preview 都要配置。改完后需要重新部署。

### 6.4 访问

部署成功后，访问：
```
https://checkin-new-panel.pages.dev
```

---

## 方式 7：CF Worker 保活服务

防止 zo.computer / HuggingFace Spaces 休眠。

### 7.1 创建 CF Worker

1. Cloudflare Dashboard → Workers & Pages → Create Worker
2. 名称：`checkin-keepalive`
3. 部署

### 7.2 编辑代码

粘贴以下代码：

```javascript
let failCount = 0;
let lastAlertTime = 0;

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(pingAndAlert(env));
  },
  async fetch(request, env) {
    const result = await pingAndAlert(env, true);
    return new Response(result, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
  }
}

async function pingAndAlert(env, isManual = false) {
  const url = env.PING_URL || "http://localhost:3000/ping";
  const timestamp = new Date().toISOString();
  try {
    const resp = await fetch(url, {
      method: "GET",
      signal: AbortSignal.timeout(10000),
      headers: { "User-Agent": "CF-KeepAlive/2.0", "Authorization": "Bearer simple-token-ok" }
    });
    if (resp.status === 200) {
      failCount = 0;
      return isManual ? `✅ [${timestamp}] ping OK` : "ok";
    } else {
      failCount++;
      if (failCount < 3) return isManual ? `⚠️ 失败 ${failCount}/3 次` : "retrying";
      const now = Date.now();
      if (now - lastAlertTime < 30 * 60 * 1000) return "throttled";
      lastAlertTime = now;
      await sendTgAlert(env, `🚨 checkin-api 异常: HTTP ${resp.status}`);
      return "alert sent";
    }
  } catch (e) {
    failCount++;
    if (failCount < 3) return isManual ? `⚠️ 连接失败 ${failCount}/3 次` : "retrying";
    const now = Date.now();
    if (now - lastAlertTime < 30 * 60 * 1000) return "throttled";
    lastAlertTime = now;
    await sendTgAlert(env, `🚨 checkin-api 挂了: ${e.message}`);
    return "alert sent";
  }
}

async function sendTgAlert(env, msg) {
  if (!env.TG_BOT_TOKEN || !env.TG_CHAT_ID) return;
  try {
    await fetch(`https://api.telegram.org/bot${env.TG_BOT_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: env.TG_CHAT_ID, text: msg, disable_web_page_preview: true }),
    });
  } catch {}
}
```

### 7.3 配置环境变量

在 Worker Settings → Variables 里添加：

| Name | Value |
|------|-------|
| `PING_URL` | `https://你的后端地址/trpc/task.getAll?batch=1&input=%7B%220%22%3A%7B%22json%22%3Anull%7D%7D` |
| `TG_BOT_TOKEN` | `你的TG机器人Token` |
| `TG_CHAT_ID` | `你的TG群ID` |

### 7.4 添加 Cron Trigger

在 Worker Triggers → Cron Triggers 里添加：
```
*/3 * * * *
```

每 3 分钟执行一次。

---

## 环境变量说明

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
| `PORT` | 服务端口 | `3000`（HuggingFace 用 `7860`） |
| `GLOBAL_CRON` | 全局 Cron 表达式 | `0 0 */6 * * *` |
| `TG_API_PROXY` | TG API 代理 | `https://api.telegram.org` |

---

## 常用管理命令

### pm2（VPS）

```bash
pm2 start dist/server/index.js --name checkin-api   # 启动
pm2 restart checkin-api                               # 重启
pm2 stop checkin-api                                  # 停止
pm2 logs checkin-api                                  # 看日志
pm2 list                                              # 看状态
```

### supervisord（zo.computer）

```bash
supervisorctl -c /etc/zo/supervisord-user.conf restart checkin-api   # 重启
supervisorctl -c /etc/zo/supervisord-user.conf status                # 看状态
tail -f /dev/shm/checkin-api.log                                     # 看日志
```

### Docker

```bash
docker logs checkin-api          # 看日志
docker restart checkin-api       # 重启
docker stop checkin-api          # 停止
```

### 更新代码

```bash
cd /项目目录
git pull origin main
npm install
npx tsc
# 然后重启服务（pm2 restart / supervisorctl restart / docker restart）
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
curl "http://localhost:3000/trpc/task.getLogs?input=%7B%22json%22%3A%7B%22taskId%22%3A1%2C%22limit%22%3A5%7D%7D" \
  -H "Authorization: Bearer simple-token-ok"
```

---

## 注意事项

1. **内存要求**：Playwright + Chromium 至少需要 500MB 内存，建议 ≥ 1GB
2. **防火墙**：确保服务端口（3000/7860）已开放
3. **Cookie 更新**：gaming4free 的 Cookie 一般 7-14 天过期，过期后需要重新提取并更新
4. **更新代码**：每次 `git pull` 后需要重新 `npx tsc` 编译 + 重启服务
5. **HuggingFace 端口**：HuggingFace Spaces 端口必须是 `7860`
6. **zo.computer 休眠**：免费版会休眠，必须配合 CF Worker 保活
