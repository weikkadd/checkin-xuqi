# Dockerfile for checkin-new-panel - 优化版
# 分阶段构建，减少最终镜像大小

# === 阶段 1: 构建 ===
FROM node:22-slim AS builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 复制 package 文件
COPY package*.json ./

# 安装依赖（包括 devDependencies，因为需要 tsc）
RUN npm install

# 复制源代码
COPY . .

# 编译 TypeScript
RUN npx tsc

# === 阶段 2: 运行 ===
FROM node:22-slim

WORKDIR /app

# 安装 Chromium 运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxcb1 libxkbcommon0 libx11-6 libxcomposite1 libxdamage1 \
    libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 \
    libasound2 libatspi2.0-0 libxshmfence1 fonts-liberation \
    fonts-noto-color-emoji wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 复制 package 文件并安装生产依赖
COPY package*.json ./
RUN npm install --production

# 安装 Playwright Chromium
RUN npx playwright install chromium --with-deps

# 复制编译后的代码
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/drizzle ./drizzle
COPY --from=builder /app/client ./client

# 暴露端口
EXPOSE 3000

# 环境变量
ENV NODE_ENV=production
ENV PORT=3000

# 启动命令
CMD ["node", "dist/server/index.js"]
