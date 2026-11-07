# Se construye desde la raiz del repo (ver docker-compose.yml): necesita frontend/ y GatewayNode/

# 1. Compilar la app de React
FROM node:24-slim AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2. Gateway: sirve la app compilada y hace de puente hacia el backend
FROM node:24-slim
WORKDIR /app
COPY GatewayNode/package*.json ./
RUN npm ci --omit=dev
COPY GatewayNode/server.js .
COPY --from=frontend /frontend/dist ./public

EXPOSE 5000
USER node
CMD ["node", "server.js"]
