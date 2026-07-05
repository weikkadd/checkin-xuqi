FROM mcr.microsoft.com/playwright:v1.45.0-jammy

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npx tsc

EXPOSE 7860
ENV NODE_ENV=production
ENV PORT=7860

CMD ["node", "dist/server/index.js"]
