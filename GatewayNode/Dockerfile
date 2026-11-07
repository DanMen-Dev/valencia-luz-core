FROM node:24-slim

WORKDIR /app

COPY package*.json ./

# Cambiamos a la instalación estándar para que descargue Leaflet en el contenedor
RUN npm install

COPY server.js .

EXPOSE 5000

CMD ["node", "server.js"]
