FROM node:24-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY server.js .
COPY public ./public

EXPOSE 5000
USER node

CMD ["node", "server.js"]
