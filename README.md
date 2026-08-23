# Valencia Luz Core ⚡🤖  
> **Enterprise Architecture for Real-Time Geospatial AI & Telecommunications Gateway**

Repositorio central del ecosistema distribuido diseñado para la captura, procesamiento cognitivo y mapeo probabilístico de contingencias eléctricas. El sistema unifica canales conversacionales de telefonía móvil con backends geoespaciales mediante una arquitectura de microservicios contenerizada en la nube.

---

## 🗺️ Visión de la Arquitectura Distribuida
El pipeline de datos opera de forma asíncrona a través de cuatro capas independientes:

1. **Gateway de Telecomunicaciones (WAHA API):** Actúa como aduana perimetral corriendo bajo el motor `WEBJS/Chromium`, capturando reportes en caliente desde redes móviles (Claro Colombia).
2. **Orquestador de Eventos (n8n Core):** Captura los webhooks encriptados bajo HTTPS, aplicando filtros de exclusión mutua para derivar flujos según el tipo de datos (Location nativo vs. Texto libre).
3. **Procesamiento de Lenguaje Natural (OpenAI Agent):** Extrae entidades geoespaciales mediante modelos lingüísticos avanzados para calcular ubicaciones basadas en texto abierto de la calle.
4. **Core Backend & Cartografía (FastAPI + Leaflet):** Motor en Python que asimila las variables geoespaciales, calcula zonas de riesgo y renderiza manchas de racionamiento translúcidas sobre mapas interactivos.

---

## 🛠️ Stack Tecnológico & Infraestructura
* **Cloud Provider:** Hetzner Cloud (VPS Ubuntu Dedicated CPU Alemania).
* **Reverse Proxy & SSL:** Nginx Server + Let's Encrypt Multidominio.
* **Containerization:** Docker & Docker Compose Framework.
* **Backend Engines:** FastAPI (Python), Node.js, n8n Automation Engine.
* **AI Core:** OpenAI Large Language Models API.

---

## 📦 Planos de Despliegue (Docker Compose)
El ecosistema se despliega en caliente mediante un único plano unificado que blinda la persistencia de datos:

```yaml
version: '3.8'

services:
  # Capa de Automatización & Orquestación
  automatizacion-n8n:
    image: docker.n8n.io/n8nio/n8n:latest
    container_name: luz_plataforma_n8n
    restart: always
    ports:
      - "5678:5678"
    volumes:
      - n8n_data_storage:/home/node/.n8n

  # Capa de Telecomunicaciones (WhatsApp HTTP API)
  puente-whatsapp-waha:
    image: devlikeapro/waha:latest
    container_name: luz_puente_whatsapp_waha
    restart: always
    ports:
      - "3000:3000"
    env_file:
      - .env
    volumes:
      - waha_sessions:/app/.sessions

  # Capa de Análisis de Datos Geoespaciales
  backend-geoprocesamiento:
    image: python:3.11-slim
    container_name: luz_backend_python
    restart: always
    ports:
      - "8000:8000"
```

---

## 🔗 Configuración Segura de Red (Nginx Reverse Proxy)
El balanceo de tráfico internacional se administra en el puerto seguro `443` aplicando reglas de redirección asíncrona hacia los sockets internos de los microservicios:

* **Tráfico de Orquestación:** `https://tu-dominio.com` ➔ Puerto `5678`
* **Tráfico Conversacional:** `https://tu-dominio.com` ➔ Puerto `3000`
* **Tráfico Cartográfico:** `https://tu-dominio.com` ➔ Puerto `8000`

---

## 🎯 Capacidades de Ingeniería Demostradas
* **Infraestructura Híbrida:** Despliegue distribuido de microservicios contenerizados de alta disponibilidad.
* **Seguridad Perimetral:** Cifrado simétrico de credenciales y túneles SSL multidominio administrados a nivel de Kernel de red.
* **DevOps Senior:** Gestión asíncrona de Webhooks, purga automatizada de memoria y control total sobre el ciclo de vida de las APIs.

---
Developed by **Daniel** — CTO Portfolio.
