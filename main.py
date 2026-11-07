from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
import sqlite3
import os

app = FastAPI(
    title="Valencia Luz Core - Motor Geoespacial y Predictivo",
    description="Backend relacional inmutable para la ingesta de telemetría GPS y analítica predictiva de OpenAI"
)

DB_PATH = "/app/valencia_luz_persistente.db"

def obtener_tiempo_vzla(restar_horas=0):
    # Base inmutable: calculamos la hora actual de Venezuela (UTC-4)
    hora_actual_vzla = datetime.utcnow() - timedelta(hours=4)
    # Si el filtro nos pide ir al pasado, le restamos las horas dinámicamente
    return (hora_actual_vzla - timedelta(hours=restar_horas)).strftime('%Y-%m-%d %H:%M:%S')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS circuitos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telefono TEXT,
            latitud REAL,
            longitud REAL,
            nombre_zona TEXT,
            tiene_luz INTEGER,
            timestamp DATETIME
        )
    """)
    conn.commit()
    conn.close()

init_db()

estado_conversacional_usuarios: Dict[str, Dict] = {}

class RegistroGPS(BaseModel):
    telefono: str
    latitud: float
    longitud: float

class RegistroNombre(BaseModel):
    telefono: str
    nombre_zona: str


# 1. Tragar el PIN GPS métrico del satélite (Punto 2 y 3)
@app.post("/api/reportar/gps")
async def reportar_gps(data: RegistroGPS):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute("""
        INSERT INTO circuitos (nombre_zona, latitud, longitud, tiene_luz, telefono, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("pendiente de asignacion", data.latitud, data.longitud, 0, data.telefono, obtener_tiempo_vzla()))
    conn.commit()
    conn.close()

    estado_conversacional_usuarios[data.telefono] = {
        "estado": "esperando",
        "timestamp_gps": now
    }
    return {"status": "success", "message": "Coordenadas métricas inyectadas de forma inmutable."}


# 2. Validar el estado del contexto conversacional para el IF 3 de n8n
@app.get("/api/usuario/esperando-nombre")
async def verificar_estado_usuario(telefono: str = ""):
    # Si por error de codificación llega vacío, evitamos el 404 devolviendo un estado neutro
    if not telefono:
        return {"estado": "libre"}

    tel_limpio = telefono.strip()
    user_state = estado_conversacional_usuarios.get(tel_limpio)

    if not user_state:
        return {"estado": "libre"}

    if datetime.now() - user_state["timestamp_gps"] > timedelta(minutes=3):
        estado_conversacional_usuarios.pop(tel_limpio, None)
        return {"estado": "libre"}

    return {"estado": "esperando"}

# 3. Registrar el nombre de la zona combinándolo dinámicamente con su firma satelital (Paso 3 UX)
@app.post("/api/reportar/nombre")
async def reportar_nombre(data: dict):
    telefono = data.get("telefono")
    zona_usuario = data.get("zona", "").strip().lower()

    # Capturar la intención real de la telemetría (1 = Con Luz, 0 = Sin Luz)
    # Si por alguna razón no viene, aplicamos 0 por defecto (Apagón)
    estado_luz = int(data.get("estado_luz", 0))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 3.1. Recuperar el PIN GPS latente guardado en la memoria por el satélite
    cursor.execute("""
        SELECT latitud, longitud FROM circuitos
        WHERE telefono = ? AND nombre_zona = 'pendiente de asignacion'
        ORDER BY timestamp DESC LIMIT 1
    """, (telefono,))
    fila_gps = cursor.fetchone()

    if not fila_gps:
        conn.close()
        raise HTTPException(status_code=404, detail="No se encontró telemetría GPS activa en espera.")

    lat, lon = fila_gps[0], fila_gps[1]

    # 3.2. Ensamblar la Nomenclatura Relacional Inmutable de Daniel Mendoza
    nombre_combinado_enterprise = f"{zona_usuario}-Lat:{round(lat, 4)}-Lon:{round(lon, 4)}"

    # 3.3 Guardar el estado real reportado. Leaflet omitirá pintar en gris si es 1.
    cursor.execute("""
        UPDATE circuitos
        SET nombre_zona = ?, tiene_luz = ?
        WHERE telefono = ? AND nombre_zona = 'pendiente de asignacion'
    """, (nombre_combinado_enterprise, estado_luz, telefono))

    conn.commit()
    conn.close()
    
    return {
        "status": "success",
        "circuito_registrado": nombre_combinado_enterprise,
        "tiene_luz_registrado": estado_luz
    }


#4 Generacion de Mapa
@app.get("/api/mapa/activos")
async def mapa_activos():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Filtrar por los cortes de las últimas 24 horas (Reloj Venezuela)
    hace_24_h = obtener_tiempo_vzla(restar_horas=24)

    cursor.execute("""
        SELECT id, nombre_zona, latitud, longitud, tiene_luz, timestamp
        FROM circuitos
        WHERE tiene_luz = 0 AND timestamp >= ?
    """, (hace_24_h,))
    filas = cursor.fetchall()
    conn.close()

    resultado_mapa=[]
    for f in filas:
        id_db, zona, latitud, longitud, tiene_luz, timestamp = f

        # Lógica Predictiva de Bloque Corto/Largo:
        # Si la zona ya tiene reportes o si se calcula la base de 6 horas
        dt_corte = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        hora_inicio_str = dt_corte.strftime('%I:%M %p')

        # Duración estándar base de 6 horas ante contingencia nacional
        dt_retorno = dt_corte + timedelta(hours=6)
        hora_retorno_str = dt_retorno.strftime('%I:%M %p')

        # 🔌 SANEAMIENTO LOGICO FRONTEND: Si se quedó congelado en la aduana de Docker
        zona_limpia = zona.strip()
        if zona_limpia.lower() == "pendiente de asignacion":
            zona_limpia = "CIRCUITO BAJO INVESTIGACIÓN"

        resultado_mapa.append({
            "id": id_db,
            "nombre_zona": zona_limpia,
            "lat": latitud,
            "lon": longitud,
            "capa_color": "gris",
            "hora_inicio": hora_inicio_str,
            "hora_estimada": hora_retorno_str,
            "actualizado": timestamp
        })
    return resultado_mapa





# 5. Consultar estado actual por zonas para la herramienta de OpenAI (Versión JSON Estable)
@app.get("/api/analitica/estado-actual")
async def analitica_actual(zona: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    hace_6_horas = obtener_tiempo_vzla(restar_horas=6)
    zona_limpia = zona.strip().lower()
    cursor.execute("""
        SELECT COUNT(*) FROM circuitos 
        WHERE nombre_zona = ? AND tiene_luz = 0 AND timestamp > ?
    """, (zona_limpia, hace_6_horas))
    reportes_activos = cursor.fetchone()
    conn.close()
    return {"zona": zona_limpia, "reportes_sin_luz_activos": reportes_activos[0]}


# 6. Calcular analítica horaria predictiva en caliente (La compuerta UX de Daniel)
@app.get("/api/analitica/historico")
async def analitica_historica(zona: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    zona_limpia = zona.strip().lower()

    # 1. Buscar el reporte más reciente de hoy en este sector para calcular la hora de inicio
    hoy_inicio = datetime.now().strftime('%Y-%m-%d 00:00:00')
    cursor.execute("""
        SELECT timestamp FROM circuitos
        WHERE nombre_zona LIKE ? AND tiene_luz = 0 AND timestamp >= ?
        ORDER BY timestamp ASC LIMIT 1
    """, (f"%{zona_limpia}%", hoy_inicio))
    primer_corte = cursor.fetchone()

    # 2. Contar si hay múltiples reportes hoy en la misma zona para evaluar reincidencia
    cursor.execute("""
        SELECT COUNT(*) FROM circuitos
        WHERE nombre_zona LIKE ? AND tiene_luz = 0 AND timestamp >= ?
    """, (f"%{zona_limpia}%", hoy_inicio))
    conteo_cortes_hoy = cursor.fetchone()[0]
    conn.close()

    # 3. Lógica determinista de proyección horaria
    hora_corte_str = "11:00 AM aprox."
    hora_retorno_str = "5:00 PM aprox."
    duracion_base = 6

    if primer_corte:
        dt_corte = datetime.strptime(primer_corte[0], '%Y-%m-%d %H:%M:%S')
        # Ajustar formato estético legible humano
        hora_corte_str = dt_corte.strftime('%I:%M %p')

        # Aplicar penalización si hay reincidencia del segundo corte del día (+2 horas)
        if conteo_cortes_hoy > 1:
            duracion_base += 2

        dt_retorno = dt_corte + timedelta(hours=duracion_base)
        hora_retorno_str = dt_retorno.strftime('%I:%M %p')

    return {
        "zona": zona_limpia,
        "hora_corte": hora_corte_str,
        "hora_retorno": hora_retorno_str,
        "duracion_promedio": duracion_base,
        "reincidencia_detectada": "Sí (+2h castigo)" if conteo_cortes_hoy > 1 else "No"
    }


