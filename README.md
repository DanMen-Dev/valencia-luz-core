# Enterprise Architecture for Real-Time Geospatial AI & Telecommunications Gateway 💡🛰️📱
### Valencia Luz Core v1.0.0 — Distributed Infrastructure for Racionamiento Predicitivo & Crowdsourcing

Repositorio central del ecosistema distribuido global diseñado para la captura, procesamiento cognitivo, persistencia inmutable y mapeo probabilístico de contingencias eléctricas. El sistema unifica canales conversacionales de telefonía móvil (WhatsApp API) con backends geoespaciales mediante una arquitectura robusta de microservicios contenerizada en la nube de alta disponibilidad.

---

## 🗺️ Visión de la Arquitectura Distribuida y Pipeline de Datos

El pipeline de datos opera de forma asíncrona y síncrona a través de cuatro capas independientes y tolerantes a fallos, comunicando dos clústeres de automatización internacionales (**Bogotá - Alemania**):

```text
[Ciudadano WhatsApp] 
         │
         ▼
 🇨🇴 [Gateway de Telecomunicaciones (WAHA API + n8n Puente)] ➔ Aduana perimetral anti-bucles infinitos (Puerto 3000/5050)
         │
   (Puente HTTP Sincronizado Transatlántico en Puerto Seguro 443)
         │
         ▼
 🇩🇪 [Orquestador de Eventos (n8n Core - Hetzner Alemania)] ➔ Filtro de exclusión mutua por tipado de datos (Puerto 5678)
         │
         ├─── CASO A (Ubicación Satelital Nativa) ➔ Ingesta Inmutable ➔ [FastAPI /api/reportar/gps]
         │
         ├─── CASO B (Texto de Crowdsourcing) ➔ Validación de Sesión ➔ [FastAPI /api/reportar/nombre]
         │
         └─── CASO C (Consulta Libre Escrita) ➔ OpenAI Extractor ➔ [FastAPI /api/analitica/historico] ➔ OpenAI Redactor UX
```

1. **Capa de Telecomunicaciones (WAHA Engine):** Actúa como aduana perimetral corriendo bajo el motor WEBJS/Chromium, capturando reportes en caliente desde redes móviles a nivel de usuario de forma ininterrumpida.
2. **Orquestación Perimetral Anti-Bucles (n8n Bogotá):** Filtra los paquetes entrantes discriminando mensajes escritos de metadatos automáticos del sistema (`incoming` vs `outgoing`), mitigando ráfagas recursivas de red y asegurando la estabilidad del canal móvil.
3. **Capa Cognitiva de Inteligencia Mixta (OpenAI API + n8n Core Alemania):** Para evitar la inestabilidad de las herramientas de llamada de funciones (*Function Calling*) de las interfaces visuales, se implementa una arquitectura lineal dual: El primer LLM (`gpt-4o-mini`) actúa como extractor semántico para normalizar zonas. Posteriormente, un nodo de red estándar HTTP interroga al backend inyectándole el parámetro dinámico `?zona={{ $json.zona }}`. Finalmente, un segundo LLM redacta el informe probabilístico con empatía y claridad institucional.
4. **Core Backend & Cartografía (FastAPI + SQLite3):** Motor síncrono en Python que asimila las variables geoespaciales, gestiona los hilos de memoria conversacional para el crowdsourcing asíncrono, calcula zonas de riesgo y renderiza manchas de racionamiento translúcidas sobre mapas interactivos mediante Leaflet.

---

## 🛠️ Stack Tecnológico & Infraestructura

- **Cloud Provider:** Hetzner Cloud (VPS Dedicated CPU Ubuntu Linux, Datacenter Alemania).
- **Reverse Proxy & SSL:** Nginx Server + Let's Encrypt Multidominio administrado a nivel de Kernel de red (Puerto seguro 443).
- **Backend Engines:** FastAPI (Python 3.11 Asynchronous Framework), Node.js, n8n Automation Engine.
- **Database Layer:** SQLite3 (Persistencia relacional local inmutable de alto rendimiento para escrituras masivas).
- **AI Core:** OpenAI Large Language Models API (`gpt-4o-mini`).

---

## 🛡️ Capacidades de Ingeniería Demostradas (DevOps Senior)

### 1. Saneamiento Sintáctico en la Capa de Transporte
Implementación de lógica nativa en JavaScript para la deserialización de objetos JSON crudos encapsulados como cadenas de texto plano (`String`). El flujo puente implementa un blindaje inmutable contra caracteres de control y saltos de línea físicos de teclado mediante metaprogramación de Node.js:
```json
"content": {{ JSON.stringify(\$json.mensaje_confirmacion) }}
```
Esto garantiza la integridad estructural de las peticiones HTTP reduciendo a 0% los errores sintácticos de red tipo `Bad control character` o `Unexpected token ','`.

### 2. Control de Estado Conversacional Asíncrono (Crowdsourcing Dinámico)
El sistema gestiona de forma determinista hilos conversacionales persistentes de corta duración en el backend. Si el usuario envía un PIN GPS, el enrutador lógico lo almacena temporalmente como `pendiente de asignacion`. Al responder el usuario con el texto de la urbanización, el motor del pipeline evalúa la propiedad de estado directo en la raíz de la RAM del orquestador:
```javascript
{{ \$json.estado }} == "esperando"
```
Desviando el flujo por la compuerta lógica `TRUE` para ejecutar un `UPDATE` masivo relacional en caliente, vinculando de forma permanente las coordenadas con el sector real del ciudadano y dibujando la mancha de contingencia en la cartografía web.

### 3. Lógica de Matemática Predictiva No-Bloqueante
El Agente cognitivo asimila los datos numéricos crudos aplanados directamente de la base de datos de Hetzner y ejecuta la ecuación probabilística de contingencia en caliente:
$$\text{Probabilidad de Racionamiento} = \left( \frac{\text{Días con Cortes}}{\text{Total Días Evaluados}} \right) \times 100$$
Ofreciendo una respuesta institucional, transparente y altamente humana al ciudadano sobre el riesgo de sufrir una suspensión de energía en su circuito en las próximas horas.

---

## 📦 Planos de Despliegue Unificados (Docker Compose)

El ecosistema se despliega en caliente mediante un único plano unificado que blinda la persistencia de datos y elimina las imágenes en caché del pasado mediante compilación forzada de código (`build: .`):

```yaml
version: '3.8'

services:
  # Capa de Análisis de Datos Geoespaciales & API Relacional
  motor-python:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: luz_backend_python
    expose:
      - "8000"
    restart: always

  # Gateway de Orquestación de Telecomunicaciones (Bogotá)
  orquestador-node:
    build:
      context: ./GatewayNode
      dockerfile: Dockerfile
    container_name: luz_gateway_node
    ports:
      - "5050:5000"
    environment:
      - PORT=5000
    restart: always
    depends_on:
      - motor-python

  # Capa de Automatización & Pipelines Cognitivos (Alemania)
  automatizacion-n8n:
    image: docker.n8n.io/n8nio/n8n:latest
    container_name: luz_plataforma_n8n
    restart: always
    ports:
      - "5678:5678"
    environment:
      - N8N_HOST=://brecha-cero.com
      - N8N_PORT=5678
      - N8N_PROTOCOL=http
      - WEBHOOK_URL=http://://brecha-cero.com/
    volumes:
      - n8n_data_storage:/home/node/.n8n

  # Capa de Telecomunicaciones (WhatsApp HTTP API Gateway)
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

volumes:
  n8n_data_storage:
    name: luz_n8n_data_volume
  waha_sessions:
    name: luz_waha_sessions_volume
```

---

## 🚀 Instrucciones de Despliegue en Servidor Limpio

Para romper la caché física del procesador de Linux e inyectar las nuevas reglas relacionales en caliente, clone el repositorio en su VPS y ejecute la re-creación destructiva perimetral:

```bash
cd ~/ValenciaLuz
docker compose down && docker compose up -d --build
```

---
Developed by Daniel Mendoza — CTO Portfolio.
