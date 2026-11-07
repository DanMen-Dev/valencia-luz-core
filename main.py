"""
Valencia Luz Core: backend de reportes comunitarios de cortes de luz.

Recibe reportes por WhatsApp (via n8n) y por la web (via el gateway del mapa), los guarda en SQLite
y responde solo con datos reales: si no hay reportes suficientes, lo dice en vez de inventar horas.

Hora: todo se guarda y se muestra en hora de Venezuela (America/Caracas).
"""
import os
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, field_validator

app = FastAPI(
    title="Valencia Luz Core",
    description="Reportes comunitarios de cortes de luz: registro, mapa y estadisticas por zona.",
)

DB_PATH = os.environ.get("VL_DB_PATH", "/app/datos/valencia_luz_persistente.db")
TZ = ZoneInfo("America/Caracas")
FORMATO = "%Y-%m-%d %H:%M:%S"
PENDIENTE = "pendiente de asignacion"

MINUTOS_ESPERA_NOMBRE = int(os.environ.get("VL_MINUTOS_ESPERA_NOMBRE", "10"))  # con mala señal, 3 era poco
HORAS_MAPA = int(os.environ.get("VL_HORAS_MAPA", "12"))            # cuanto tiempo se ve un reporte en el mapa
REPORTES_POR_HORA = int(os.environ.get("VL_REPORTES_POR_HORA", "6"))  # tope por telefono (frena el spam)
KM_ZONA_CERCANA = 1.5                                               # reporte web sin zona: toma la mas cercana
# Venezuela, aprox.: se rechazan coordenadas que no pueden ser un reporte real
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = 0.5, 12.6, -73.5, -59.5


# ---------- Utilidades ---------------------------------------------------------------

def ahora():
    return datetime.now(TZ).replace(tzinfo=None)


def texto_hora(dt=None, restar_horas=0):
    return ((dt or ahora()) - timedelta(hours=restar_horas)).strftime(FORMATO)


def hora_legible(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def normalizar_telefono(valor):
    """'+58 414-425 3799' -> '584144253799'. Un '+' en la URL llega como espacio: tambien se limpia."""
    return re.sub(r"\D", "", str(valor or ""))


def normalizar_zona(valor):
    """'  San Diégo ' -> 'san diego'. Minusculas, sin acentos, sin signos, espacios simples."""
    t = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9 ]+", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


RE_YA_HAY_LUZ = re.compile(r"^\s*(si|sí|1|ya|volvio|regreso|llego)\b[\s,.:;-]*", re.IGNORECASE)
RE_SIN_LUZ = re.compile(r"^\s*(no|0)\b[\s,.:;-]*", re.IGNORECASE)


def interpretar_respuesta(texto):
    """La respuesta al '¿cual es tu sector?': 'Si, Prebo' = volvio la luz en Prebo; 'Prebo' = sin luz.
    Devuelve (zona_normalizada, tiene_luz)."""
    t = str(texto or "")
    if RE_YA_HAY_LUZ.match(t):
        return normalizar_zona(RE_YA_HAY_LUZ.sub("", t, count=1)), 1
    if RE_SIN_LUZ.match(t):
        return normalizar_zona(RE_SIN_LUZ.sub("", t, count=1)), 0
    return normalizar_zona(t), 0


def zona_de(nombre_zona):
    """Compatibilidad con reportes viejos guardados como 'prebo-Lat:10.2-Lon:-68.0'."""
    base = str(nombre_zona or "").split("-Lat:")[0]
    return normalizar_zona(base)


def distancia_km(lat1, lon1, lat2, lon2):
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


# ---------- Base de datos ------------------------------------------------------------

def conectar():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    carpeta = os.path.dirname(DB_PATH)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    with closing(conectar()) as conn, conn:
        conn.execute("""
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
        columnas = {r["name"] for r in conn.execute("PRAGMA table_info(circuitos)")}
        if "zona" not in columnas:
            # Zona normalizada en su propia columna (antes iba mezclada con las coordenadas en nombre_zona)
            conn.execute("ALTER TABLE circuitos ADD COLUMN zona TEXT")
            conn.execute("ALTER TABLE circuitos ADD COLUMN origen TEXT DEFAULT 'whatsapp'")
            for fila in conn.execute("SELECT id, nombre_zona FROM circuitos").fetchall():
                z = "" if fila["nombre_zona"] == PENDIENTE else zona_de(fila["nombre_zona"])
                conn.execute("UPDATE circuitos SET zona = ? WHERE id = ?", (z, fila["id"]))
        conn.execute("CREATE INDEX IF NOT EXISTS ix_circuitos_zona_tiempo ON circuitos (zona, timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_circuitos_tel_tiempo ON circuitos (telefono, timestamp)")
        # La conversacion ("esperando el nombre del sector") vive en la base: sobrevive a un reinicio
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversaciones (
                telefono TEXT PRIMARY KEY,
                estado TEXT NOT NULL,
                actualizado DATETIME NOT NULL
            )
        """)


init_db()


def zona_cercana(conn, lat, lon):
    """La zona mas reportada a menos de KM_ZONA_CERCANA en los ultimos 30 dias (para reportes sin zona)."""
    desde = texto_hora(restar_horas=24 * 30)
    filas = conn.execute(
        "SELECT zona, latitud, longitud FROM circuitos WHERE zona != '' AND zona IS NOT NULL AND timestamp >= ?",
        (desde,)).fetchall()
    conteo = {}
    for f in filas:
        if distancia_km(lat, lon, f["latitud"], f["longitud"]) <= KM_ZONA_CERCANA:
            conteo[f["zona"]] = conteo.get(f["zona"], 0) + 1
    return max(conteo, key=conteo.get) if conteo else ""


def controlar_frecuencia(conn, telefono):
    if not telefono or telefono == "web":
        return
    n = conn.execute("SELECT COUNT(*) FROM circuitos WHERE telefono = ? AND timestamp >= ?",
                     (telefono, texto_hora(restar_horas=1))).fetchone()[0]
    if n >= REPORTES_POR_HORA:
        raise HTTPException(status_code=429, detail="Demasiados reportes desde este telefono en la ultima hora.")


# ---------- Modelos ------------------------------------------------------------------

class Coordenadas(BaseModel):
    latitud: float
    longitud: float

    @field_validator("latitud")
    @classmethod
    def _lat(cls, v):
        if not LAT_MIN <= v <= LAT_MAX:
            raise ValueError("latitud fuera de Venezuela")
        return v

    @field_validator("longitud")
    @classmethod
    def _lon(cls, v):
        if not LON_MIN <= v <= LON_MAX:
            raise ValueError("longitud fuera de Venezuela")
        return v


class RegistroGPS(Coordenadas):
    telefono: str


class ReporteWeb(Coordenadas):
    tiene_luz: int = 0
    zona: str = ""


# ---------- Reportes -----------------------------------------------------------------

# 1. Ubicacion enviada por WhatsApp: queda pendiente hasta que el usuario diga su sector
@app.post("/api/reportar/gps")
async def reportar_gps(data: RegistroGPS):
    telefono = normalizar_telefono(data.telefono)
    if not telefono:
        raise HTTPException(status_code=422, detail="Falta el telefono.")
    with closing(conectar()) as conn, conn:
        controlar_frecuencia(conn, telefono)
        # Un pendiente anterior sin respuesta se descarta: cuenta el ultimo PIN
        conn.execute("DELETE FROM circuitos WHERE telefono = ? AND nombre_zona = ?", (telefono, PENDIENTE))
        conn.execute("""
            INSERT INTO circuitos (telefono, latitud, longitud, nombre_zona, zona, tiene_luz, timestamp, origen)
            VALUES (?, ?, ?, ?, '', 0, ?, 'whatsapp')
        """, (telefono, data.latitud, data.longitud, PENDIENTE, texto_hora()))
        conn.execute("REPLACE INTO conversaciones (telefono, estado, actualizado) VALUES (?, 'esperando', ?)",
                     (telefono, texto_hora()))
    return {"status": "success", "message": "Ubicacion recibida. Falta el nombre del sector."}


# 2. ¿Este telefono esta respondiendo con el nombre de su sector? (IF del flujo de n8n)
@app.get("/api/usuario/esperando-nombre")
async def verificar_estado_usuario(telefono: str = ""):
    tel = normalizar_telefono(telefono)
    if not tel:
        return {"estado": "libre"}
    with closing(conectar()) as conn, conn:
        fila = conn.execute("SELECT estado, actualizado FROM conversaciones WHERE telefono = ?", (tel,)).fetchone()
        if not fila:
            return {"estado": "libre"}
        if datetime.strptime(fila["actualizado"], FORMATO) < ahora() - timedelta(minutes=MINUTOS_ESPERA_NOMBRE):
            conn.execute("DELETE FROM conversaciones WHERE telefono = ?", (tel,))
            return {"estado": "libre"}
        return {"estado": fila["estado"]}


# 3. Nombre del sector: completa el reporte pendiente. Acepta los nombres de campo viejos y nuevos:
#    n8n manda {telefono, nombre_zona, tiene_luz}; una version anterior usaba {zona, estado_luz}.
@app.post("/api/reportar/nombre")
async def reportar_nombre(request: Request):
    data = await request.json()
    telefono = normalizar_telefono(data.get("telefono"))
    texto = data.get("nombre_zona", data.get("zona", ""))
    zona, tiene_luz = interpretar_respuesta(texto)
    # El estado sale del texto ("Si, Prebo" = volvio la luz). El tiene_luz que calcula n8n busca "si" en
    # cualquier parte ("Casiano" daba 1), asi que no se usa; estado_luz explicito (version anterior) si.
    if str(data.get("estado_luz", "")).strip() in ("0", "1"):
        tiene_luz = int(data["estado_luz"])
    if not telefono or not zona:
        raise HTTPException(status_code=422, detail="Faltan el telefono o el nombre del sector.")

    with closing(conectar()) as conn, conn:
        fila = conn.execute("""
            SELECT id, latitud, longitud FROM circuitos
            WHERE telefono = ? AND nombre_zona = ? ORDER BY timestamp DESC LIMIT 1
        """, (telefono, PENDIENTE)).fetchone()
        if not fila:
            raise HTTPException(status_code=404, detail="No hay una ubicacion pendiente para este telefono.")
        conn.execute("UPDATE circuitos SET nombre_zona = ?, zona = ?, tiene_luz = ? WHERE id = ?",
                     (zona, zona, tiene_luz, fila["id"]))
        conn.execute("DELETE FROM conversaciones WHERE telefono = ?", (telefono,))

    return {
        "status": "success",
        "zona": zona,
        "tiene_luz": tiene_luz,
        "circuito_registrado": zona,              # compatibilidad con la respuesta anterior
        "tiene_luz_registrado": tiene_luz,
    }


# 3b. Reporte desde el boton del mapa web (sin telefono): toma la zona mas cercana conocida
@app.post("/api/reportar")
async def reportar_web(data: ReporteWeb):
    with closing(conectar()) as conn, conn:
        zona = normalizar_zona(data.zona) or zona_cercana(conn, data.latitud, data.longitud)
        tiene_luz = 1 if data.tiene_luz == 1 else 0
        conn.execute("""
            INSERT INTO circuitos (telefono, latitud, longitud, nombre_zona, zona, tiene_luz, timestamp, origen)
            VALUES ('web', ?, ?, ?, ?, ?, ?, 'web')
        """, (data.latitud, data.longitud, zona or "sin zona", zona, tiene_luz, texto_hora()))
    return {"status": "success", "circuito_asignado": (zona or "sin zona").upper(), "tiene_luz": tiene_luz}


# ---------- Estadisticas por zona ----------------------------------------------------

def episodios(filas):
    """De una serie de reportes ordenados (timestamp, tiene_luz) saca los cortes: [(inicio, fin|None)].
    Un corte empieza con el primer 'sin luz' y termina con el primer 'con luz' posterior."""
    cortes, inicio = [], None
    for f in filas:
        t = datetime.strptime(f["timestamp"], FORMATO)
        if f["tiene_luz"] == 0 and inicio is None:
            inicio = t
        elif f["tiene_luz"] == 1 and inicio is not None:
            cortes.append((inicio, t))
            inicio = None
    if inicio is not None:
        cortes.append((inicio, None))
    return cortes


def resumen_zona(conn, zona, momento=None):
    momento = momento or ahora()
    hoy = momento.replace(hour=0, minute=0, second=0, microsecond=0)
    hace_7 = momento - timedelta(days=7)
    filas = conn.execute("""
        SELECT timestamp, tiene_luz FROM circuitos
        WHERE zona = ? AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp
    """, (zona, hace_7.strftime(FORMATO), momento.strftime(FORMATO))).fetchall()
    cortes = episodios(filas)
    terminados = [(i, f) for i, f in cortes if f is not None]
    duraciones = [(f - i).total_seconds() / 3600 for i, f in terminados]
    promedio = round(sum(duraciones) / len(duraciones), 1) if duraciones else None
    dias_con_corte = len({i.date() for i, _ in cortes})
    de_hoy = [(i, f) for i, f in cortes if i >= hoy]
    ultimo = filas[-1] if filas else None
    if ultimo is None or datetime.strptime(ultimo["timestamp"], FORMATO) < momento - timedelta(hours=HORAS_MAPA):
        estado = "sin_reportes"
    else:
        estado = "con_luz" if ultimo["tiene_luz"] == 1 else "sin_luz"

    corte_hoy = de_hoy[-1] if de_hoy else None
    retorno_estimado = None
    if corte_hoy and corte_hoy[1] is None and promedio:
        retorno_estimado = corte_hoy[0] + timedelta(hours=promedio)
    return {
        "zona": zona,
        "estado": estado,
        "reportes_7_dias": len(filas),
        "cortes_hoy": len(de_hoy),
        "inicio_corte_hoy": hora_legible(corte_hoy[0]) if corte_hoy else None,
        "fin_corte_hoy": hora_legible(corte_hoy[1]) if corte_hoy and corte_hoy[1] else None,
        "retorno_estimado": hora_legible(retorno_estimado) if retorno_estimado else None,
        "duracion_promedio_horas": promedio,
        "cortes_medidos_7_dias": len(duraciones),
        "dias_con_corte_7_dias": dias_con_corte,
        "probabilidad_corte_pct": round(dias_con_corte / 7 * 100),
    }


def mensaje_zona(r):
    """El texto para WhatsApp, armado solo con datos reales."""
    nombre = r["zona"].upper()
    if r["reportes_7_dias"] == 0:
        return (f"💡 *Valencia Luz*: todavía no hay reportes de *{nombre}* en los últimos 7 días.\n"
                "Si estás ahí, envía tu ubicación 📍 para que tu sector aparezca en el mapa: "
                "https://luz.brecha-cero.com/mapa")
    lineas = [f"💡 *Valencia Luz · {nombre}*"]
    if r["estado"] == "sin_luz":
        lineas.append(f"• Ahora: *sin luz* según los reportes (desde las {r['inicio_corte_hoy']})."
                      if r["inicio_corte_hoy"] else "• Ahora: *sin luz* según los reportes.")
        if r["retorno_estimado"]:
            lineas.append(f"• Retorno estimado: {r['retorno_estimado']} "
                          f"(promedio de {r['duracion_promedio_horas']} h en {r['cortes_medidos_7_dias']} "
                          f"cortes medidos esta semana).")
        else:
            lineas.append("• Retorno estimado: aún no hay datos suficientes para estimarlo.")
    elif r["estado"] == "con_luz":
        if r["fin_corte_hoy"]:
            lineas.append(f"• Ahora: *con luz* (volvió a las {r['fin_corte_hoy']}).")
        else:
            lineas.append("• Ahora: *con luz* según el último reporte.")
    else:
        lineas.append("• No hay reportes recientes de este sector.")
    lineas.append(f"• Esta semana: cortes en {r['dias_con_corte_7_dias']} de 7 días "
                  f"({r['probabilidad_corte_pct']} %).")
    lineas.append("Mapa en vivo: https://luz.brecha-cero.com/mapa")
    return "\n".join(lineas)


# 5. Reportes activos de una zona (ultimas horas)
@app.get("/api/analitica/estado-actual")
async def analitica_actual(zona: str):
    z = normalizar_zona(zona)
    with closing(conectar()) as conn:
        n = conn.execute("""
            SELECT COUNT(*) FROM circuitos WHERE zona = ? AND tiene_luz = 0 AND timestamp > ?
        """, (z, texto_hora(restar_horas=6))).fetchone()[0]
    return {"zona": z, "reportes_sin_luz_activos": n}


# 6. Resumen de una zona para el bot. Mantiene los nombres que lee el flujo de n8n (hora_corte, hora_retorno,
#    duracion_promedio, reincidencia_detectada) pero con datos reales o un texto que dice que no los hay,
#    nunca horas inventadas. 'mensaje' trae el texto listo para enviar.
@app.get("/api/analitica/historico")
async def analitica_historica(zona: str):
    z = normalizar_zona(zona)
    with closing(conectar()) as conn:
        r = resumen_zona(conn, z)
    return {
        **r,
        "hora_corte": r["inicio_corte_hoy"] or "sin reportes de corte hoy",
        "hora_retorno": r["fin_corte_hoy"] or r["retorno_estimado"] or "sin datos suficientes para estimarlo",
        "duracion_promedio": r["duracion_promedio_horas"] if r["duracion_promedio_horas"] is not None
        else "sin datos",
        "reincidencia_detectada": "Sí" if r["cortes_hoy"] > 1 else "No",
        "mensaje": mensaje_zona(r),
    }


# ---------- Mapa ---------------------------------------------------------------------

@app.get("/api/mapa/activos")
async def mapa_activos():
    """Reportes de las ultimas HORAS_MAPA horas. Por telefono cuenta solo el ultimo reporte: si alguien
    reporto 'sin luz' y despues 'volvio la luz', se ve solo lo segundo."""
    with closing(conectar()) as conn:
        filas = conn.execute("""
            SELECT id, telefono, zona, nombre_zona, latitud, longitud, tiene_luz, timestamp FROM circuitos
            WHERE timestamp >= ? AND nombre_zona != ? ORDER BY timestamp DESC
        """, (texto_hora(restar_horas=HORAS_MAPA), PENDIENTE)).fetchall()
        vistos, salida, resumenes = set(), [], {}
        for f in filas:
            if f["telefono"] != "web":
                if f["telefono"] in vistos:
                    continue
                vistos.add(f["telefono"])
            zona = f["zona"] or zona_de(f["nombre_zona"])
            if zona and zona not in resumenes:
                resumenes[zona] = resumen_zona(conn, zona)
            r = resumenes.get(zona)
            inicio = datetime.strptime(f["timestamp"], FORMATO)
            salida.append({
                "id": f["id"],
                "nombre_zona": zona or "sector sin nombre",   # sin guiones: el mapa usa el texto tal cual
                "lat": f["latitud"],
                "lon": f["longitud"],
                "tiene_luz": f["tiene_luz"],
                "capa_color": "gris" if f["tiene_luz"] == 0 else "amarillo",
                "hora_inicio": hora_legible(inicio),
                "hora_estimada": (r["retorno_estimado"] if r and r["retorno_estimado"] and f["tiene_luz"] == 0
                                  else "Sin estimación (faltan datos)" if f["tiene_luz"] == 0 else "—"),
                "actualizado": f["timestamp"],
            })
    return salida


@app.get("/api/salud")
async def salud():
    with closing(conectar()) as conn:
        n = conn.execute("SELECT COUNT(*) FROM circuitos").fetchone()[0]
    return {"status": "ok", "reportes": n, "hora_venezuela": texto_hora()}
