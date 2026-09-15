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

DB_PATH = "valencia_luz_persistente.db"

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
        INSERT INTO circuitos (telefono, latitud, longitud, nombre_zona, tiene_luz, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (data.telefono, data.latitud, data.longitud, "pendiente de asignacion", 0, now.strftime('%Y-%m-%d %H:%M:%S')))
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


# 3. Asociar el nombre del sector dado por el usuario al circuito creado (Punto 3)
@app.post("/api/reportar/nombre")
async def asociar_nombre_zona(data: RegistroNombre):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    zona_limpia = data.nombre_zona.strip().lower()
    cursor.execute("""
        UPDATE circuitos 
        SET nombre_zona = ? 
        WHERE telefono = ? AND nombre_zona = 'pendiente de asignacion'
    """, (zona_limpia, data.telefono))
    conn.commit()
    conn.close()
    estado_conversacional_usuarios.pop(data.telefono, None)
    return {"status": "success", "message": f"Circuito geoespacial asociado a: {zona_limpia}"}

# 4. El Frontend consume los circuitos activos de las últimas 6 horas (Filtro dinámico de tiempo - Punto 4)
@app.get("/api/mapa/activos")
async def consultar_circuitos_mapa():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    hace_6_horas = (datetime.now() - timedelta(hours=6)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("SELECT latitud, longitud, nombre_zona, tiene_luz FROM circuitos WHERE timestamp > ?", (hace_6_horas,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# 5. Consultar estado actual por zonas para la herramienta de OpenAI (Versión JSON Estable)
@app.get("/api/analitica/estado-actual")
async def analitica_actual(zona: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    hace_6_horas = (datetime.now() - timedelta(hours=6)).strftime('%Y-%m-%d %H:%M:%S')
    zona_limpia = zona.strip().lower()
    cursor.execute("""
        SELECT COUNT(*) FROM circuitos 
        WHERE nombre_zona = ? AND tiene_luz = 0 AND timestamp > ?
    """, (zona_limpia, hace_6_horas))
    reportes_activos = cursor.fetchone()
    conn.close()
    return {"zona": zona_limpia, "reportes_sin_luz_activos": reportes_activos[0]}


# 6. Calcular la probabilidad matemática predictiva sobre el histórico perpetuo (Versión JSON Estable)
@app.get("/api/analitica/historico")
async def analitica_historica(zona: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    zona_limpia = zona.strip().lower()
    hace_7_dias = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        SELECT COUNT(DISTINCT DATE(timestamp)) FROM circuitos 
        WHERE nombre_zona = ? AND tiene_luz = 0 AND timestamp > ?
    """, (zona_limpia, hace_7_dias))
    dias_con_apagones = cursor.fetchone()
    conn.close()
    return {"zona": zona_limpia, "dias_con_racionamiento_ultimos_7_dias": dias_con_apagones[0], "total_dias_evaluados": 7}

