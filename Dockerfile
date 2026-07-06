FROM mcr.microsoft.com/playwright:v1.45.0-jammy

# 安装 Xvfb 虚拟显示器（用于 headless: false 模式过 Turnstile）
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    xauth \
    && rm -rf /var/lib/apt/lists/*

# 创建工作目录并赋权给 pwuser
WORKDIR /app
RUN chown -R pwuser:pwuser /app

# 切换到非 root 用户
USER pwuser

COPY --chown=pwuser:pwuser package*.json ./
RUN npm install

COPY --chown=pwuser:pwuser . .
RUN npx tsc

EXPOSE 7860
ENV NODE_ENV=production
ENV PORT=7860
ENV HOME=/home/pwuser
ENV DISPLAY=:99

# 启动 Xvfb 虚拟显示器 + Node.js 服务
CMD Xvfb :99 -screen 0 1920x1080x24 -ac &> /dev/null & sleep 1 && node dist/server/index.js
