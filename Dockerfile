FROM python:3.13-slim

WORKDIR /app

# Dependencias fijadas en requirements.txt (antes se instalaban sin version)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# La base de datos vive en /app/datos, montada como volumen: sobrevive a un rebuild del contenedor
ENV VL_DB_PATH=/app/datos/valencia_luz_persistente.db
RUN mkdir -p /app/datos

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
