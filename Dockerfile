FROM mcr.microsoft.com/playwright:v1.45.0-jammy

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

CMD ["node", "dist/server/index.js"]
