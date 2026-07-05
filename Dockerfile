FROM mcr.microsoft.com/playwright:v1.45.0-jammy

RUN useradd -m -u 1000 user
WORKDIR /app

COPY --chown=user package*.json ./
RUN npm install

COPY --chown=user . .
RUN npx tsc

RUN chown -R user:user /app
USER user

EXPOSE 7860
ENV NODE_ENV=production
ENV PORT=7860
ENV HOME=/home/user
ENV PATH=/home/user/.local/bin:$PATH

CMD ["node", "dist/server/index.js"]
