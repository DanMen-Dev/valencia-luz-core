import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "/app/valencia_luz_persistente.db"

SECTORES = [
    {"nombre": "tocuyito", "lat_base": 10.1653, "lon_base": -68.0211},
    {"nombre": "prebo", "lat_base": 10.2134, "lon_base": -68.0125},
    {"nombre": "san diego", "lat_base": 10.2458, "lon_base": -67.9624},
    {"nombre": "mañongo", "lat_base": 10.2285, "lon_base": -68.0012},
    {"nombre": "guaparo", "lat_base": 10.2198, "lon_base": -68.0084}
]

def sembrar_ecosistema():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("🛰️ Iniciando siembra masiva de telemetría geoespacial mixta para la entrevista...")
    
    # Hora base actual de Venezuela hoy viernes (UTC-4)
    hora_actual_vzla = datetime.utcnow() - timedelta(hours=4)
    
    for i in range(40):
        sector = random.choice(SECTORES)
        lat_random = sector["lat_base"] + random.uniform(-0.008, 0.008)
        lon_random = sector["lon_base"] + random.uniform(-0.008, 0.008)
        telefono_falso = f"58414{random.randint(1000000, 9999999)}"
        nombre_combinado = f"{sector['nombre']}-Lat:{round(lat_random, 4)}-Lon:{round(lon_random, 4)}"
        
        # Simular cortes frescos dentro de las últimas 3 horas para que no caduquen en el mapa
        minutos_atras = random.randint(10, 180)
        timestamp_fake = (hora_actual_vzla - timedelta(minutes=minutos_atras)).strftime('%Y-%m-%d %H:%M:%S')
        
        # 💡 Distribución mixta: 80% sin luz (0 - gris) y 20% con luz (1 - amarillo)
        tiene_luz = 1 if random.random() < 0.2 else 0
        
        cursor.execute("""
            INSERT INTO circuitos (nombre_zona, latitud, longitud, tiene_luz, telefono, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nombre_combinado, lat_random, lon_random, tiene_luz, telefono_falso, timestamp_fake))
        
    conn.commit()
    
    cursor.execute("SELECT COUNT(*) FROM circuitos WHERE tiene_luz = 0;")
    sin_luz = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM circuitos WHERE tiene_luz = 1;")
    con_luz = cursor.fetchone()[0]
    conn.close()
    
    print(f"🔥 Siembra completada. En el mapa: {sin_luz} Apagones (Gris) y {con_luz} Con Luz (Amarillo).")

if __name__ == "__main__":
    sembrar_ecosistema()

