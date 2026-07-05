FROM mcr.microsoft.com/playwright:v1.45.0-jammy

# 使用 Playwright 镜像自带的非 root 用户 pwuser
USER pwuser
WORKDIR /app

COPY --chown=pwuser package*.json ./
RUN npm install

COPY --chown=pwuser . .
RUN npx tsc

EXPOSE 7860
ENV NODE_ENV=production
ENV PORT=7860
ENV HOME=/home/pwuser

CMD ["node", "dist/server/index.js"]
