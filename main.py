"""
Radar: backend de reportes comunitarios de cortes de luz.

Recibe reportes por WhatsApp (via n8n) y por la web (via el gateway del mapa), los guarda en SQLite
y responde solo con datos reales: si no hay reportes suficientes, lo dice en vez de inventar horas.

Hora: todo se guarda y se muestra en hora de Venezuela (America/Caracas).
"""
import hashlib
import hmac
import os
import secrets
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import datetime, timedelta
from math import asin, cos, floor, radians, sin, sqrt
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, field_validator

app = FastAPI(
    title="Radar - cortes de luz",
    description="Reportes comunitarios de cortes de luz: registro, mapa y estadisticas por zona.",
)

DB_PATH = os.environ.get("VL_DB_PATH", "/app/datos/valencia_luz_persistente.db")
TZ = ZoneInfo("America/Caracas")
FORMATO = "%Y-%m-%d %H:%M:%S"
PENDIENTE = "pendiente de asignacion"

MINUTOS_ESPERA_NOMBRE = int(os.environ.get("VL_MINUTOS_ESPERA_NOMBRE", "10"))  # con mala señal, 3 era poco
# Un corte sin noticias se da por terminado a las HORAS_CORTE horas (promedio general de un corte). Un "volvio la
# luz" antes lo cierra; un "sin luz" nuevo despues abre otro ciclo. Tambien es lo que dura un reporte en el mapa.
HORAS_CORTE = int(os.environ.get("VL_HORAS_CORTE", "6"))
HORAS_MAPA = int(os.environ.get("VL_HORAS_MAPA", str(HORAS_CORTE)))
REPORTES_POR_HORA = int(os.environ.get("VL_REPORTES_POR_HORA", "6"))  # tope por telefono (frena el spam)
KM_ZONA_CERCANA = 1.5                                               # reporte web sin zona: toma la mas cercana
# Celdas: cuadros fijos del mapa de 0,01 grados (~1,1 km x 1,1 km en Venezuela, el tamano de un sector).
# El id sale de las coordenadas redondeadas hacia abajo ('10.21_-68.01'): el mismo lugar da siempre la misma celda.
PASO_CELDA = 0.01
PESO_MINIMO_ALIAS = 0.3     # un nombre "cubre" una celda si tiene al menos el 30 % de sus votos
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


# Reporte escrito ("se fue la luz en Tocuyito"): reglas para la intencion. Mandan sobre lo que sugiere el
# modelo; una pregunta ("¿se fue la luz en Prebo?") siempre es consulta, nunca reporte.
RE_VOLVIO = re.compile(r"\b(volvio|regreso|llego|vino|ya (hay|tengo|tenemos)|prendio|restablec\w*)\b.{0,25}"
                       r"\b(luz|electricidad|corriente)\b|\bya hay luz\b", re.IGNORECASE)
RE_SE_FUE = re.compile(r"\b(se (nos )?fue|se va|no hay|sin|quitaron|cortaron|corte de|apagon|bajon)\b.{0,15}"
                       r"\b(la )?(luz|electricidad|corriente)\b|\bapagon\b|\ba oscuras\b", re.IGNORECASE)
RE_PREGUNTA = re.compile(r"^(cuant\w*|cuando|a que hora|como|donde|que tal|sabe\w*|alguien sabe|hay|y la luz)\b")
INTENCIONES = ("consulta", "sin_luz", "volvio")


def intencion_de(texto, sugerida=""):
    """'consulta', 'sin_luz' o 'volvio'. Las reglas sobre el texto mandan; si no deciden, lo que sugiere el modelo."""
    crudo = str(texto or "")
    t = normalizar_zona(crudo)
    if "?" in crudo or "¿" in crudo or RE_PREGUNTA.match(t):
        return "consulta"
    if RE_VOLVIO.search(t):
        return "volvio"
    if RE_SE_FUE.search(t):
        return "sin_luz"
    return sugerida if sugerida in INTENCIONES else "consulta"


def zona_de(nombre_zona):
    """Compatibilidad con reportes viejos guardados como 'prebo-Lat:10.2-Lon:-68.0'."""
    base = str(nombre_zona or "").split("-Lat:")[0]
    return normalizar_zona(base)


def celda_de(lat, lon):
    """Id de la celda de un punto. round() antes de floor(): 10.21 * 100 da 1020.9999... en coma flotante."""
    fila = floor(round(lat / PASO_CELDA, 6))
    columna = floor(round(lon / PASO_CELDA, 6))
    return f"{fila * PASO_CELDA:.2f}_{columna * PASO_CELDA:.2f}"


def centro_celda(celda):
    lat, lon = (float(x) for x in celda.split("_"))
    return round(lat + PASO_CELDA / 2, 6), round(lon + PASO_CELDA / 2, 6)


def celdas_vecinas(celda):
    """La celda y sus 8 vecinas: dos casas a 50 m pueden caer a cada lado de una linea de la cuadricula."""
    lat, lon = centro_celda(celda)
    return [celda_de(lat + d_lat * PASO_CELDA, lon + d_lon * PASO_CELDA)
            for d_lat in (-1, 0, 1) for d_lon in (-1, 0, 1)]


# Palabras que no distinguen un sector: "Urb. Prebo", "Sector Prebo" y "Prebo" son el mismo nombre popular
RELLENO = {"urb", "urbanizacion", "sector", "barrio", "bo", "res", "residencias", "conjunto", "parroquia",
           "zona", "la", "el", "los", "las", "de", "del", "en"}


def limpiar_alias(valor):
    """'Urb. La Prebo' -> 'prebo'. Si solo quedan palabras de relleno, se deja el nombre normalizado."""
    normal = normalizar_zona(valor)
    util = " ".join(p for p in normal.split() if p not in RELLENO)
    return util or normal


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
        if "celda" not in columnas:
            conn.execute("ALTER TABLE circuitos ADD COLUMN celda TEXT")
        # Reportes que todavia no tienen celda (los de antes de esta version): se calcula de sus coordenadas
        for fila in conn.execute("SELECT id, latitud, longitud FROM circuitos WHERE celda IS NULL").fetchall():
            if fila["latitud"] is not None and fila["longitud"] is not None:
                conn.execute("UPDATE circuitos SET celda = ? WHERE id = ?",
                             (celda_de(fila["latitud"], fila["longitud"]), fila["id"]))
        conn.execute("CREATE INDEX IF NOT EXISTS ix_circuitos_zona_tiempo ON circuitos (zona, timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_circuitos_celda_tiempo ON circuitos (celda, timestamp)")
        # Celdas y nombres populares: cada vez que un vecino manda su ubicacion y escribe su sector, ese nombre
        # suma un voto en esa celda. Asi "Prebo", "Prevo" y "Urb Prebo" quedan amarrados al mismo lugar.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS celdas (
                id TEXT PRIMARY KEY,
                lat_centro REAL NOT NULL,
                lon_centro REAL NOT NULL,
                creada DATETIME NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alias (
                nombre TEXT NOT NULL,
                celda TEXT NOT NULL REFERENCES celdas(id),
                votos INTEGER NOT NULL DEFAULT 0,
                ultimo DATETIME NOT NULL,
                PRIMARY KEY (nombre, celda)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_alias_celda ON alias (celda)")
        # Primera vez: los votos se reconstruyen con los reportes que ya hay
        if conn.execute("SELECT COUNT(*) FROM alias").fetchone()[0] == 0:
            for f in conn.execute(f"""
                SELECT zona, celda, timestamp FROM circuitos
                WHERE {SQL_NOMBRE_DEL_VECINO} AND celda IS NOT NULL ORDER BY timestamp
            """).fetchall():
                votar_alias(conn, f["zona"], f["celda"], f["timestamp"])
        conn.execute("CREATE INDEX IF NOT EXISTS ix_circuitos_tel_tiempo ON circuitos (telefono, timestamp)")
        # La conversacion ("esperando el nombre del sector") vive en la base: sobrevive a un reinicio
        # Cortes ya calculados por celda (inicio, fin, duracion, tipo): la base para analizar y predecir.
        # Se recalculan cada noche (python main.py recalcular-cortes) a partir de los reportes.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cortes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                celda TEXT NOT NULL,
                inicio DATETIME NOT NULL,
                fin DATETIME,
                duracion_horas REAL,
                tipo TEXT NOT NULL,          -- medido | vencido | abierto
                calculado DATETIME NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_cortes_celda_inicio ON cortes (celda, inicio)")
        # Contador de usuarios: un registro por dia, canal y persona, guardando solo una huella (HMAC) del id.
        # Mapa: un numero al azar que genera el navegador. Bot: el telefono o id de Telegram, nunca en claro.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS actividad (
                dia TEXT NOT NULL,
                canal TEXT NOT NULL,          -- mapa | bot
                quien TEXT NOT NULL,
                PRIMARY KEY (dia, canal, quien)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversaciones (
                telefono TEXT PRIMARY KEY,
                estado TEXT NOT NULL,
                actualizado DATETIME NOT NULL
            )
        """)


# Solo cuentan como voto los nombres que escribio un vecino junto con su ubicacion (WhatsApp/Telegram).
# Los reportes web y los "yo tambien" toman el nombre de la zona, no lo aportan.
SQL_NOMBRE_DEL_VECINO = ("telefono != 'web' AND zona IS NOT NULL AND zona != '' "
                         f"AND nombre_zona != '{PENDIENTE}'")


def registrar_celda(conn, celda, cuando=None):
    lat, lon = centro_celda(celda)
    conn.execute("INSERT OR IGNORE INTO celdas (id, lat_centro, lon_centro, creada) VALUES (?, ?, ?, ?)",
                 (celda, lat, lon, cuando or texto_hora()))


def votar_alias(conn, nombre, celda, cuando=None):
    """Un voto para el nombre popular 'nombre' en 'celda'."""
    nombre = limpiar_alias(nombre)
    if not nombre or not celda:
        return
    cuando = cuando or texto_hora()
    registrar_celda(conn, celda, cuando)
    conn.execute("""
        INSERT INTO alias (nombre, celda, votos, ultimo) VALUES (?, ?, 1, ?)
        ON CONFLICT (nombre, celda) DO UPDATE SET votos = votos + 1, ultimo = excluded.ultimo
    """, (nombre, celda, cuando))


def nombre_de_celda(conn, celda, mirar_vecinas=True):
    """Nombre popular mas votado de la celda; si no tiene, el de sus vecinas. '' si nadie la ha nombrado."""
    fila = conn.execute("SELECT nombre FROM alias WHERE celda = ? ORDER BY votos DESC, ultimo DESC LIMIT 1",
                        (celda,)).fetchone()
    if fila or not mirar_vecinas:
        return fila["nombre"] if fila else ""
    vecinas = celdas_vecinas(celda)
    fila = conn.execute(f"""
        SELECT nombre, SUM(votos) AS v FROM alias WHERE celda IN ({",".join("?" * len(vecinas))})
        GROUP BY nombre ORDER BY v DESC LIMIT 1
    """, vecinas).fetchone()
    return fila["nombre"] if fila else ""


def peso_alias(conn, nombre, celda):
    """Que parte de los votos de la celda tiene este nombre (0 a 1)."""
    fila = conn.execute("""
        SELECT COALESCE(SUM(CASE WHEN nombre = ? THEN votos END), 0) AS mios, SUM(votos) AS total
        FROM alias WHERE celda = ?
    """, (limpiar_alias(nombre), celda)).fetchone()
    return (fila["mios"] / fila["total"]) if fila and fila["total"] else 0.0


def nombre_para_mostrar(conn, zona, celda):
    """El nombre con que se ve un reporte: el suyo si tiene peso en su celda; si es una variante minoritaria
    ('prevo' donde casi todos dicen 'prebo'), el nombre mas votado de la celda. Asi el mapa no parte un
    sector en dos por una letra."""
    propio = "" if normalizar_zona(zona) in ("", "sin zona", "sector sin nombre") else limpiar_alias(zona)
    if not celda:
        return propio
    if propio and peso_alias(conn, propio, celda) >= PESO_MINIMO_ALIAS:
        return propio
    return nombre_de_celda(conn, celda, mirar_vecinas=not propio) or propio


# ---------- Busqueda tolerante: "Prevo", "Tocuyto" o "sandiego" encuentran su sector ----------

def distancia_letras(a, b):
    """Cuantas letras hay que cambiar, quitar, poner o intercambiar (vecinas) para pasar de a a b
    (distancia de Damerau-Levenshtein restringida)."""
    if a == b:
        return 0
    filas = [list(range(len(b) + 1))]
    for i, ca in enumerate(a, 1):
        fila = [i]
        for j, cb in enumerate(b, 1):
            costo = 0 if ca == cb else 1
            fila.append(min(filas[-1][j] + 1, fila[j - 1] + 1, filas[-1][j - 1] + costo))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                fila[j] = min(fila[j], filas[-2][j - 2] + 1)
        filas.append(fila)
    return filas[-1][-1]


def tolerancia(nombre):
    """Errores de letra que se aceptan segun el largo: en nombres cortos un cambio ya es otro sector."""
    largo = len(nombre.replace(" ", ""))
    return 0 if largo <= 4 else 1 if largo <= 8 else 2


def resolver_sector(conn, texto):
    """De lo que escribio el vecino al nombre de un sector conocido.
    Devuelve {'nombre', 'metodo', 'escrito', 'candidatos'} con metodo:
      'exacto'      nombre conocido (o variante amarrada a un sector: 'prevo' -> 'prebo')
      'aproximado'  un solo sector a 1-2 letras de distancia
      'ambiguo'     dos o mas igual de parecidos: hay que preguntar
      'desconocido' ninguno (se responde con lo que haya bajo ese texto)"""
    escrito = limpiar_alias(texto)
    salida = {"nombre": escrito, "metodo": "desconocido", "escrito": escrito, "candidatos": []}
    if not escrito:
        return salida
    votos = {f["nombre"]: f["v"] for f in conn.execute("SELECT nombre, SUM(votos) AS v FROM alias GROUP BY nombre")}

    def canonico(nombre):
        # Una variante minoritaria ('prevo') se resuelve al nombre mas votado de su celda principal
        if celdas_de_alias(conn, nombre):
            return nombre
        fila = conn.execute("SELECT celda FROM alias WHERE nombre = ? ORDER BY votos DESC LIMIT 1", (nombre,)).fetchone()
        return (nombre_de_celda(conn, fila["celda"], mirar_vecinas=False) or nombre) if fila else nombre

    if escrito in votos:
        return {**salida, "nombre": canonico(escrito), "metodo": "exacto"}
    if not votos:   # sin alias todavia: se busca por el texto tal cual (reportes de antes de las celdas)
        conocido = conn.execute("SELECT 1 FROM circuitos WHERE zona = ? LIMIT 1", (escrito,)).fetchone()
        return {**salida, "metodo": "exacto" if conocido else "desconocido"}

    limite = tolerancia(escrito)
    junto = escrito.replace(" ", "")
    parecidos = {}
    for nombre in votos:
        d = min(distancia_letras(escrito, nombre), distancia_letras(junto, nombre.replace(" ", "")))
        if d <= min(limite, tolerancia(nombre)) or junto == nombre.replace(" ", ""):
            destino = canonico(nombre)
            parecidos[destino] = min(d, parecidos.get(destino, d))
    if not parecidos:
        return salida
    orden = sorted(parecidos, key=lambda n: (parecidos[n], -votos.get(n, 0)))
    mejor = orden[0]
    empatados = [n for n in orden if parecidos[n] == parecidos[mejor]]
    # Empate de distancia: solo se elige solo si uno tiene 5 veces mas votos que el siguiente
    if len(empatados) == 1 or votos.get(empatados[0], 0) >= 5 * max(1, votos.get(empatados[1], 0)):
        return {**salida, "nombre": mejor, "metodo": "aproximado", "candidatos": orden[:3]}
    return {**salida, "nombre": "", "metodo": "ambiguo", "candidatos": empatados[:3]}


def celdas_de_alias(conn, nombre):
    """Celdas que cubre un nombre popular: donde tiene al menos PESO_MINIMO_ALIAS de los votos de la celda.
    Una celda de borde (media Prebo, media Kerdell) cuenta para los dos si ambos tienen peso."""
    nombre = limpiar_alias(nombre)
    if not nombre:
        return []
    filas = conn.execute("""
        SELECT a.celda, a.votos, (SELECT SUM(votos) FROM alias b WHERE b.celda = a.celda) AS total
        FROM alias a WHERE a.nombre = ? ORDER BY a.votos DESC
    """, (nombre,)).fetchall()
    return [f["celda"] for f in filas if f["total"] and f["votos"] / f["total"] >= PESO_MINIMO_ALIAS]


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


class ReporteTexto(BaseModel):
    telefono: str
    texto: str = ""
    zona: str = ""          # el sector que extrajo el modelo
    intencion: str = ""     # lo que sugiere el modelo: consulta | sin_luz | volvio


class Confirmacion(Coordenadas):
    zona: str
    tiene_luz: int


# ---------- Reportes -----------------------------------------------------------------

# ---------- Contador de usuarios (sin datos personales) ----------
CLAVE_ESTADISTICAS = os.environ.get("VL_CLAVE_ESTADISTICAS", "")      # vacia: el panel privado no existe
CONTADOR_MINIMO = int(os.environ.get("VL_CONTADOR_MINIMO", "50"))     # el contador publico aparece desde aqui
RE_VISITANTE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def secreto_contador():
    """Llave de las huellas: VL_SECRETO_CONTADOR o, si no esta, una al azar guardada junto a la base."""
    if os.environ.get("VL_SECRETO_CONTADOR"):
        return os.environ["VL_SECRETO_CONTADOR"].encode()
    ruta = os.path.join(os.path.dirname(DB_PATH) or ".", "secreto_contador")
    if not os.path.exists(ruta):
        with open(ruta, "w") as f:
            f.write(secrets.token_hex(32))
    with open(ruta) as f:
        return f.read().strip().encode()


def huella(valor):
    return hmac.new(secreto_contador(), str(valor).encode(), hashlib.sha256).hexdigest()[:20]


def registrar_actividad(conn, canal, quien):
    if quien:
        conn.execute("INSERT OR IGNORE INTO actividad (dia, canal, quien) VALUES (?, ?, ?)",
                     (ahora().strftime("%Y-%m-%d"), canal, huella(quien)))


def estadisticas(conn, momento=None):
    momento = momento or ahora()
    def desde(dias):
        return (momento - timedelta(days=dias - 1)).strftime("%Y-%m-%d")

    def unicos(canal, dias):
        return conn.execute("SELECT COUNT(DISTINCT quien) FROM actividad WHERE canal = ? AND dia >= ?",
                            (canal, desde(dias))).fetchone()[0]

    def reportes(dias, distintos=False):
        campo = "COUNT(DISTINCT telefono)" if distintos else "COUNT(*)"
        return conn.execute(f"""SELECT {campo} FROM circuitos WHERE nombre_zona != ? AND timestamp >= ?
                                {"AND telefono != 'web'" if distintos else ""}""",
                            (PENDIENTE, desde(dias) + " 00:00:00")).fetchone()[0]

    periodos = {}
    for nombre, dias in (("hoy", 1), ("semana", 7), ("mes", 30)):
        periodos[nombre] = {"mapa": unicos("mapa", dias), "bot": unicos("bot", dias),
                            "vecinos_que_reportaron": reportes(dias, distintos=True), "reportes": reportes(dias)}
        periodos[nombre]["total"] = periodos[nombre]["mapa"] + periodos[nombre]["bot"]
    vuelven = conn.execute("""SELECT COUNT(*) FROM (SELECT quien FROM actividad WHERE dia >= ?
                              GROUP BY canal, quien HAVING COUNT(DISTINCT dia) >= 2)""", (desde(30),)).fetchone()[0]
    serie = [{"dia": f["dia"], "mapa": f["mapa"], "bot": f["bot"]} for f in conn.execute("""
        SELECT dia, SUM(canal = 'mapa') AS mapa, SUM(canal = 'bot') AS bot FROM actividad
        WHERE dia >= ? GROUP BY dia ORDER BY dia""", (desde(30),))]
    sectores = [{"sector": f["zona"], "reportes": f["n"]} for f in conn.execute("""
        SELECT zona, COUNT(*) AS n FROM circuitos WHERE zona != '' AND zona IS NOT NULL AND timestamp >= ?
        GROUP BY zona ORDER BY n DESC LIMIT 10""", (desde(30) + " 00:00:00",))]
    return {"generado": texto_hora(momento), **periodos, "vuelven_30_dias": vuelven,
            "por_dia": serie, "sectores_mas_activos": sectores}


# 1. Ubicacion enviada por WhatsApp: queda pendiente hasta que el usuario diga su sector
@app.post("/api/reportar/gps")
async def reportar_gps(data: RegistroGPS):
    telefono = normalizar_telefono(data.telefono)
    if not telefono:
        raise HTTPException(status_code=422, detail="Falta el telefono.")
    with closing(conectar()) as conn, conn:
        registrar_actividad(conn, "bot", telefono)
        controlar_frecuencia(conn, telefono)
        # Un pendiente anterior sin respuesta se descarta: cuenta el ultimo PIN
        conn.execute("DELETE FROM circuitos WHERE telefono = ? AND nombre_zona = ?", (telefono, PENDIENTE))
        conn.execute("""
            INSERT INTO circuitos (telefono, latitud, longitud, nombre_zona, zona, tiene_luz, timestamp, origen, celda)
            VALUES (?, ?, ?, ?, '', 0, ?, 'whatsapp', ?)
        """, (telefono, data.latitud, data.longitud, PENDIENTE, texto_hora(), celda_de(data.latitud, data.longitud)))
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
        registrar_actividad(conn, "bot", tel)   # el Conector pregunta esto con cada mensaje escrito
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
        celda = celda_de(fila["latitud"], fila["longitud"])
        conn.execute("UPDATE circuitos SET nombre_zona = ?, zona = ?, tiene_luz = ?, celda = ? WHERE id = ?",
                     (zona, zona, tiene_luz, celda, fila["id"]))
        votar_alias(conn, zona, celda)   # el nombre que escribio el vecino queda amarrado a su celda
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
        celda = celda_de(data.latitud, data.longitud)
        # El nombre sale de la celda (o sus vecinas); si nadie la ha nombrado, del sector reportado mas cerca
        zona = (normalizar_zona(data.zona) or nombre_de_celda(conn, celda)
                or zona_cercana(conn, data.latitud, data.longitud))
        tiene_luz = 1 if data.tiene_luz == 1 else 0
        conn.execute("""
            INSERT INTO circuitos (telefono, latitud, longitud, nombre_zona, zona, tiene_luz, timestamp, origen, celda)
            VALUES ('web', ?, ?, ?, ?, ?, ?, 'web', ?)
        """, (data.latitud, data.longitud, zona or "sin zona", zona, tiene_luz, texto_hora(), celda))
    return {"status": "success", "circuito_asignado": (zona or "sin zona").upper(), "tiene_luz": tiene_luz}


# 4. "Yo tambien" desde el mapa: suma un reporte a un sector que YA tiene reportes activos cerca.
#    No crea sectores nuevos: solo confirma (o contradice) lo que otros vecinos reportaron.
KM_CONFIRMACION = 2.0


@app.post("/api/confirmar")
async def confirmar(data: Confirmacion):
    zona = normalizar_zona(data.zona)
    if not zona:
        raise HTTPException(status_code=422, detail="Falta el sector.")
    tiene_luz = 1 if data.tiene_luz == 1 else 0
    with closing(conectar()) as conn, conn:
        celdas = celdas_de_alias(conn, zona)
        filtro = f"(zona = ? OR celda IN ({','.join('?' * len(celdas))}))" if celdas else "zona = ?"
        filas = conn.execute(
            f"SELECT latitud, longitud FROM circuitos WHERE {filtro} AND timestamp >= ? AND nombre_zona != ?",
            (zona, *celdas, texto_hora(restar_horas=HORAS_MAPA), PENDIENTE)).fetchall()
        if not any(distancia_km(data.latitud, data.longitud, f["latitud"], f["longitud"]) <= KM_CONFIRMACION
                   for f in filas):
            raise HTTPException(status_code=404, detail="Ese sector no tiene reportes activos cerca.")
        conn.execute("""
            INSERT INTO circuitos (telefono, latitud, longitud, nombre_zona, zona, tiene_luz, timestamp, origen, celda)
            VALUES ('web', ?, ?, ?, ?, ?, ?, 'confirmacion', ?)
        """, (data.latitud, data.longitud, zona, zona, tiene_luz, texto_hora(), celda_de(data.latitud, data.longitud)))
    return {"status": "success", "zona": zona.upper(), "tiene_luz": tiene_luz}


# ---------- Estadisticas por zona ----------------------------------------------------

def episodios(filas, momento=None, horas_corte=None):
    """De una serie de reportes ordenados (timestamp, tiene_luz) saca los cortes: [(inicio, fin, tipo)].

    - 'medido': empezo con un 'sin luz' y lo cerro un 'con luz' (fin = hora de ese reporte).
    - 'vencido': paso mas de horas_corte sin noticias (ningun 'sin luz' nuevo ni 'con luz'); se asume que
      volvio la luz, pero no sabemos cuando: fin = None y no entra en los promedios.
    - 'abierto': sigue sin luz y todavia no vence.
    Un 'con luz' que llega mucho despues (mas de 2 x horas_corte sin noticias) no mide nada: el corte ya habia
    vencido y esa duracion no seria confiable."""
    horas_corte = horas_corte or HORAS_CORTE
    vence = timedelta(hours=horas_corte)
    cortes, inicio, ultima = [], None, None
    for f in filas:
        t = datetime.strptime(f["timestamp"], FORMATO)
        if inicio is not None and f["tiene_luz"] == 1:
            cortes.append((inicio, t, "medido") if t - ultima <= 2 * vence else (inicio, None, "vencido"))
            inicio = ultima = None
        elif f["tiene_luz"] == 0:
            if inicio is not None and t - ultima > vence:
                cortes.append((inicio, None, "vencido"))
                inicio = None
            if inicio is None:
                inicio = t
            ultima = t
    if inicio is not None:
        vencido = momento is not None and momento - ultima > vence
        cortes.append((inicio, None, "vencido" if vencido else "abierto"))
    return cortes


def filas_sector(conn, zona, desde, hasta):
    """Reportes (timestamp, tiene_luz) de un sector entre dos momentos. Un sector son las celdas que cubre su
    nombre popular (todas sus variantes cuentan); sin celdas todavia, se busca por el texto tal cual."""
    celdas = celdas_de_alias(conn, zona)
    if celdas:
        filtro, valores = f"(celda IN ({','.join('?' * len(celdas))}) OR zona = ?)", [*celdas, zona]
    else:
        filtro, valores = "zona = ?", [zona]
    return conn.execute(f"""
        SELECT timestamp, tiene_luz FROM circuitos
        WHERE {filtro} AND nombre_zona != ? AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp
    """, (*valores, PENDIENTE, desde.strftime(FORMATO), hasta.strftime(FORMATO))).fetchall()


def resumen_zona(conn, zona, momento=None):
    momento = momento or ahora()
    hoy = momento.replace(hour=0, minute=0, second=0, microsecond=0)
    hace_7 = momento - timedelta(days=7)
    filas = filas_sector(conn, zona, hace_7, momento)
    cortes = episodios(filas, momento)
    duraciones = [(f - i).total_seconds() / 3600 for i, f, tipo in cortes if tipo == "medido"]
    promedio = round(sum(duraciones) / len(duraciones), 1) if duraciones else None
    dias_con_corte = len({i.date() for i, _, _ in cortes})
    de_hoy = [c for c in cortes if c[0] >= hoy]
    ultimo = filas[-1] if filas else None
    if ultimo is None or datetime.strptime(ultimo["timestamp"], FORMATO) < momento - timedelta(hours=HORAS_MAPA):
        estado = "sin_reportes"
    else:
        estado = "con_luz" if ultimo["tiene_luz"] == 1 else "sin_luz"

    corte_hoy = de_hoy[-1] if de_hoy else None
    # Retorno estimado solo para un corte abierto: con el promedio del sector si hay cortes medidos; si no, con
    # el promedio general (HORAS_CORTE), y se dice cual se uso. Nunca una hora sin explicar de donde sale.
    retorno_estimado, retorno_fuente = None, None
    if corte_hoy and corte_hoy[2] == "abierto":
        if promedio:
            retorno_estimado, retorno_fuente = corte_hoy[0] + timedelta(hours=promedio), "promedio_sector"
        else:
            retorno_estimado, retorno_fuente = corte_hoy[0] + timedelta(hours=HORAS_CORTE), "promedio_general"
    return {
        "zona": zona,
        "estado": estado,
        "reportes_7_dias": len(filas),
        "cortes_hoy": len(de_hoy),
        "inicio_corte_hoy": hora_legible(corte_hoy[0]) if corte_hoy else None,
        "fin_corte_hoy": hora_legible(corte_hoy[1]) if corte_hoy and corte_hoy[1] else None,
        "retorno_estimado": hora_legible(retorno_estimado) if retorno_estimado else None,
        "retorno_fuente": retorno_fuente,
        "horas_corte": HORAS_CORTE,
        "duracion_promedio_horas": promedio,
        "cortes_medidos_7_dias": len(duraciones),
        "dias_con_corte_7_dias": dias_con_corte,
        "probabilidad_corte_pct": round(dias_con_corte / 7 * 100),
    }


# ---------- Prediccion, etapa 1: patrones por hora y dia ----------
# Estadistica simple y explicable sobre las ultimas 8 semanas: a que hora suelen empezar los cortes, que dias
# se repiten, cuanto duran y con que frecuencia hubo corte en la franja horaria de ahora. Solo se muestra
# cuando hay datos suficientes; nunca un patron inventado con dos reportes.
DIAS_PATRON = 56
MIN_CORTES_PATRON = 4
MIN_SEMANAS_PATRON = 2
MIN_DIAS_PROBABILIDAD = 14
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def franja_de(hora):
    """Franjas de 3 horas: 0 = 12-3 AM, 1 = 3-6 AM, ... 7 = 9 PM-12 AM."""
    return hora // 3


def texto_franja(franja):
    def h(x):
        x %= 24
        return f"{12 if x % 12 == 0 else x % 12} {'AM' if x < 12 else 'PM'}"
    return f"{h(franja * 3)} y {h(franja * 3 + 3)}"


def patrones_zona(conn, zona, momento=None, dias=DIAS_PATRON):
    momento = momento or ahora()
    filas = filas_sector(conn, zona, momento - timedelta(days=dias), momento)
    cortes = episodios(filas, momento)
    semanas = {i.isocalendar()[:2] for i, _, _ in cortes}
    salida = {"zona": zona, "cortes_analizados": len(cortes), "semanas_con_cortes": len(semanas),
              "suficiente": len(cortes) >= MIN_CORTES_PATRON and len(semanas) >= MIN_SEMANAS_PATRON,
              "franja_habitual": None, "dias_habituales": [], "duracion_tipica_horas": None,
              "probabilidad_franja_actual_pct": None, "dias_observados": 0}
    if not salida["suficiente"]:
        return salida

    por_franja = {}
    for i, _, _ in cortes:
        por_franja[franja_de(i.hour)] = por_franja.get(franja_de(i.hour), 0) + 1
    franja, n = max(por_franja.items(), key=lambda kv: (kv[1], -kv[0]))
    if n >= 3 and n / len(cortes) >= 0.4:
        salida["franja_habitual"] = {"franja": franja, "texto": texto_franja(franja), "cortes": n}

    por_dia = {}
    for i, _, _ in cortes:
        por_dia[i.weekday()] = por_dia.get(i.weekday(), 0) + 1
    promedio = len(cortes) / 7
    habituales = sorted((d for d, k in por_dia.items() if k >= 2 and k >= 1.5 * promedio),
                        key=lambda d: (-por_dia[d], d))[:2]
    salida["dias_habituales"] = [DIAS_SEMANA[d] for d in sorted(habituales)]

    medidos = sorted((f - i).total_seconds() / 3600 for i, f, t in cortes if t == "medido")
    if len(medidos) >= 3:
        mitad = len(medidos) // 2
        salida["duracion_tipica_horas"] = round(medidos[mitad] if len(medidos) % 2
                                                else (medidos[mitad - 1] + medidos[mitad]) / 2, 1)

    primero = datetime.strptime(filas[0]["timestamp"], FORMATO).date()
    observados = min(dias, (momento.date() - primero).days + 1)
    salida["dias_observados"] = observados
    if observados >= MIN_DIAS_PROBABILIDAD:
        ahora_franja = franja_de(momento.hour)
        # Un dia cuenta si algun corte toco esa franja (no solo si empezo en ella): un corte de 2 a 6 PM
        # tambien es "corte entre 3 y 6 PM". Vencido: se asume que duro HORAS_CORTE; abierto: hasta ahora.
        dias_con = set()
        for i, f, tipo in cortes:
            fin = f or (i + timedelta(hours=HORAS_CORTE) if tipo == "vencido" else momento)
            dia = i.date()
            while dia <= fin.date():
                ventana = datetime.combine(dia, datetime.min.time(), i.tzinfo) + timedelta(hours=ahora_franja * 3)
                if i < ventana + timedelta(hours=3) and fin > ventana:
                    dias_con.add(dia)
                dia += timedelta(days=1)
        salida["probabilidad_franja_actual_pct"] = round(len(dias_con) / observados * 100)
        salida["franja_actual"] = texto_franja(ahora_franja)
    return salida


def lineas_patron(p):
    """Lineas para el bot; vacio si no hay datos suficientes."""
    if not p["suficiente"]:
        return []
    partes = []
    if p["franja_habitual"]:
        dias = f" ({' y '.join(p['dias_habituales'])})" if p["dias_habituales"] else ""
        partes.append(f"los cortes suelen empezar entre las {p['franja_habitual']['texto']}{dias}")
    elif p["dias_habituales"]:
        partes.append(f"los cortes se repiten más los {' y '.join(p['dias_habituales'])}")
    if p["duracion_tipica_horas"]:
        partes.append(f"duran unas {p['duracion_tipica_horas']:g} h")
    evidencia = f"{p['cortes_analizados']} cortes en {p['semanas_con_cortes']} semanas"
    lineas = [f"• Patrón ({evidencia}): {', '.join(partes)}."] if partes else []
    if p["probabilidad_franja_actual_pct"] is not None:
        lineas.append(f"• Entre las {p['franja_actual']} hubo corte {p['probabilidad_franja_actual_pct']} % "
                      f"de los días ({p['dias_observados']} días con datos).")
    return lineas


def recalcular_cortes(conn, dias=60, momento=None):
    """Rehace la tabla cortes de los ultimos 'dias', celda por celda. Idempotente."""
    momento = momento or ahora()
    desde = momento - timedelta(days=dias)
    conn.execute("DELETE FROM cortes WHERE inicio >= ?", (desde.strftime(FORMATO),))
    celdas = [f["celda"] for f in conn.execute(
        "SELECT DISTINCT celda FROM circuitos WHERE celda IS NOT NULL AND timestamp >= ?", (desde.strftime(FORMATO),))]
    total = 0
    for celda in celdas:
        filas = conn.execute("""
            SELECT timestamp, tiene_luz FROM circuitos
            WHERE celda = ? AND nombre_zona != ? AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp
        """, (celda, PENDIENTE, desde.strftime(FORMATO), momento.strftime(FORMATO))).fetchall()
        for inicio, fin, tipo in episodios(filas, momento):
            conn.execute("""
                INSERT INTO cortes (celda, inicio, fin, duracion_horas, tipo, calculado) VALUES (?, ?, ?, ?, ?, ?)
            """, (celda, inicio.strftime(FORMATO), fin.strftime(FORMATO) if fin else None,
                  round((fin - inicio).total_seconds() / 3600, 2) if fin else None, tipo, texto_hora(momento)))
            total += 1
    return total


def mensaje_zona(r):
    """El texto para WhatsApp, armado solo con datos reales."""
    nombre = r["zona"].upper()
    if r["reportes_7_dias"] == 0:
        return (f"📡 *Radar*: todavía no hay reportes de *{nombre}* en los últimos 7 días.\n"
                "Si estás ahí, envía tu ubicación 📍 para que tu sector aparezca en el mapa: "
                "https://radar.brecha-cero.com/mapa")
    lineas = [f"📡 *Radar · {nombre}*"]
    if r["estado"] == "sin_luz":
        lineas.append(f"• Ahora: *sin luz* según los reportes (desde las {r['inicio_corte_hoy']})."
                      if r["inicio_corte_hoy"] else "• Ahora: *sin luz* según los reportes.")
        if r["retorno_estimado"] and r["retorno_fuente"] == "promedio_sector":
            lineas.append(f"• Retorno estimado: {r['retorno_estimado']} "
                          f"(promedio de {r['duracion_promedio_horas']} h en {r['cortes_medidos_7_dias']} "
                          f"cortes medidos esta semana).")
        elif r["retorno_estimado"]:
            lineas.append(f"• Retorno estimado: aprox. {r['retorno_estimado']} (promedio general de "
                          f"{r['horas_corte']} h; este sector aún no tiene cortes medidos).")
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
    lineas.append("Mapa en vivo: https://radar.brecha-cero.com/mapa")
    return "\n".join(lineas)


# 5. Reportes activos de una zona (ultimas horas)
@app.get("/api/analitica/estado-actual")
async def analitica_actual(zona: str):
    z = normalizar_zona(zona)
    with closing(conectar()) as conn:
        n = conn.execute("""
            SELECT COUNT(*) FROM circuitos WHERE zona = ? AND tiene_luz = 0 AND timestamp > ?
        """, (z, texto_hora(restar_horas=HORAS_CORTE))).fetchone()[0]
    return {"zona": z, "reportes_sin_luz_activos": n}


# 6. Resumen de una zona para el bot. Mantiene los nombres que lee el flujo de n8n (hora_corte, hora_retorno,
#    duracion_promedio, reincidencia_detectada) pero con datos reales o un texto que dice que no los hay,
#    nunca horas inventadas. 'mensaje' trae el texto listo para enviar.
def nota_entendido(sector):
    """'(Entendí PREBO; escribiste «perbo».)' cuando el sector no es exactamente lo que se escribio."""
    if sector["metodo"] == "aproximado" or (sector["metodo"] == "exacto" and sector["nombre"] != sector["escrito"]):
        return f"_(Entendí {sector['nombre'].upper()}; escribiste «{sector['escrito']}».)_"
    return ""


def pregunta_ambigua(sector):
    opciones = " o ".join(f"*{c.upper()}*" for c in sector["candidatos"])
    return f"📡 *Radar*: ¿te refieres a {opciones}? Escribe el nombre del sector como lo conoces y te digo cómo está."


def consulta_sector(conn, zona):
    """Resumen de un sector para el bot. Mantiene los campos que leia el flujo de n8n."""
    sector = resolver_sector(conn, zona)
    if sector["metodo"] == "ambiguo":
        return {"zona": sector["escrito"], "sector": sector, "mensaje": pregunta_ambigua(sector),
                "hora_corte": "por confirmar el sector", "hora_retorno": "por confirmar el sector",
                "duracion_promedio": "sin datos", "reincidencia_detectada": "No"}
    nombre = sector["nombre"] or normalizar_zona(zona)
    r = resumen_zona(conn, nombre)
    mensaje = mensaje_zona(r)
    patron = lineas_patron(patrones_zona(conn, nombre))
    if patron:   # antes del enlace al mapa
        mensaje = mensaje.replace("\nMapa en vivo:", "\n" + "\n".join(patron) + "\nMapa en vivo:", 1)
    nota = nota_entendido(sector)
    if nota:   # el vecino ve si el sector es el que queria
        mensaje = mensaje.replace("\n", f"\n{nota}\n", 1)
    return {
        "sector": sector,
        **r,
        "hora_corte": r["inicio_corte_hoy"] or "sin reportes de corte hoy",
        "hora_retorno": r["fin_corte_hoy"] or (
            (r["retorno_estimado"] if r["retorno_fuente"] == "promedio_sector" else f"aprox. {r['retorno_estimado']}")
            if r["retorno_estimado"] else "sin datos suficientes para estimarlo"),
        "duracion_promedio": r["duracion_promedio_horas"] if r["duracion_promedio_horas"] is not None
        else "sin datos",
        "reincidencia_detectada": "Sí" if r["cortes_hoy"] > 1 else "No",
        "mensaje": mensaje,
    }


@app.get("/api/analitica/historico")
async def analitica_historica(zona: str):
    with closing(conectar()) as conn:
        return consulta_sector(conn, zona)


# 8. Mensaje escrito al bot (lo que no es saludo, ubicacion ni respuesta de sector). El modelo extrae el sector
#    y sugiere la intencion; aqui se decide: consulta -> resumen; "se fue la luz en X" / "volvio la luz en X" ->
#    reporte en el centro de la celda mas votada de X, si X ya es un sector conocido. Si no, se pide la ubicacion.
@app.post("/api/reportar/texto")
async def reportar_texto(data: ReporteTexto):
    intencion = intencion_de(data.texto, data.intencion)
    telefono = normalizar_telefono(data.telefono)
    with closing(conectar()) as conn, conn:
        if intencion == "consulta" or not telefono:
            return {"tipo": "consulta", **consulta_sector(conn, data.zona or data.texto)}
        sector = resolver_sector(conn, data.zona)
        if sector["metodo"] == "ambiguo":
            return {"tipo": "pregunta", "sector": sector, "mensaje": pregunta_ambigua(sector)}
        fila = conn.execute("SELECT celda FROM alias WHERE nombre = ? ORDER BY votos DESC LIMIT 1",
                            (sector["nombre"],)).fetchone() if sector["metodo"] != "desconocido" else None
        if not fila:
            nombre = (sector["escrito"] or "tu sector").upper()
            return {"tipo": "falta_ubicacion", "sector": sector, "mensaje": (
                f"📍 Todavía no tengo *{nombre}* en el mapa. Envía tu ubicación con el botón 📍 y luego escribe "
                f"el nombre de tu sector: así queda tu reporte y el sector aprende dónde está.")}
        controlar_frecuencia(conn, telefono)
        tiene_luz = 1 if intencion == "volvio" else 0
        lat, lon = centro_celda(fila["celda"])
        # origen 'texto': ubicacion aproximada (centro de la celda); no vota como nombre popular
        conn.execute("""
            INSERT INTO circuitos (telefono, latitud, longitud, nombre_zona, zona, tiene_luz, timestamp, origen, celda)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'texto', ?)
        """, (telefono, lat, lon, sector["nombre"], sector["nombre"], tiene_luz, texto_hora(), fila["celda"]))
    nombre = sector["nombre"].upper()
    lineas = [f"✅ Anotado: *volvió la luz* en *{nombre}*. ¡Gracias por avisar!" if tiene_luz
              else f"✅ Anotado: *sin luz* en *{nombre}*."]
    nota = nota_entendido(sector)
    if nota:
        lineas.append(nota)
    if not tiene_luz:
        lineas.append("Para más precisión en el mapa, envía tu ubicación con el botón 📍.")
    lineas.append("Mapa en vivo: https://radar.brecha-cero.com/mapa")
    return {"tipo": "reporte", "sector": sector, "tiene_luz": tiene_luz, "mensaje": "\n".join(lineas)}


# ---------- Mapa ---------------------------------------------------------------------

@app.get("/api/mapa/activos")
async def mapa_activos():
    """Reportes de las ultimas HORAS_MAPA horas (por defecto HORAS_CORTE: un corte sin noticias vence y sale del
    mapa). Por telefono cuenta solo el ultimo reporte: si alguien reporto 'sin luz' y despues 'volvio la luz',
    se ve solo lo segundo."""
    with closing(conectar()) as conn:
        filas = conn.execute("""
            SELECT id, telefono, zona, nombre_zona, latitud, longitud, tiene_luz, timestamp, celda FROM circuitos
            WHERE timestamp >= ? AND nombre_zona != ? ORDER BY timestamp DESC
        """, (texto_hora(restar_horas=HORAS_MAPA), PENDIENTE)).fetchall()
        vistos, salida, resumenes = set(), [], {}
        for f in filas:
            if f["telefono"] != "web":
                if f["telefono"] in vistos:
                    continue
                vistos.add(f["telefono"])
            zona = nombre_para_mostrar(conn, f["zona"] or zona_de(f["nombre_zona"]), f["celda"])
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
                "hora_estimada": hora_estimada_mapa(r, inicio) if f["tiene_luz"] == 0 else "—",
                "actualizado": f["timestamp"],
            })
    return salida


def hora_estimada_mapa(r, inicio_reporte):
    """Texto del retorno para el mapa: promedio del sector si lo hay; si no, promedio general, dicho como tal."""
    if r and r["retorno_estimado"] and r["retorno_fuente"] == "promedio_sector":
        return r["retorno_estimado"]
    if r and r["retorno_estimado"]:
        base = r["retorno_estimado"]
    else:   # reporte sin sector (o sin corte abierto en su sector): desde la hora del propio reporte
        base = hora_legible(inicio_reporte + timedelta(hours=HORAS_CORTE))
    return f"{base} (aprox., promedio general de {HORAS_CORTE} h)"


# 7. Un nombre popular y las celdas que cubre (lo usaran la busqueda tolerante y el reporte por texto)
@app.get("/api/sectores")
async def sector(nombre: str):
    limpio = limpiar_alias(nombre)
    with closing(conectar()) as conn:
        filas = conn.execute("SELECT celda, votos FROM alias WHERE nombre = ? ORDER BY votos DESC",
                             (limpio,)).fetchall()
        cubre = set(celdas_de_alias(conn, limpio))
        resolucion = resolver_sector(conn, nombre)
        celdas = []
        for f in filas:
            lat, lon = centro_celda(f["celda"])
            celdas.append({"id": f["celda"], "lat": lat, "lon": lon, "votos": f["votos"],
                           "cubre": f["celda"] in cubre, "nombre_mas_votado": nombre_de_celda(conn, f["celda"], False)})
    return {"nombre": limpio, "conocido": bool(celdas), "celdas": celdas, "resolucion": resolucion}


# 9. Patrones de un sector (prediccion, etapa 1)
@app.get("/api/analitica/patrones")
async def analitica_patrones(zona: str):
    with closing(conectar()) as conn:
        sector = resolver_sector(conn, zona)
        nombre = sector["nombre"] or normalizar_zona(zona)
        p = patrones_zona(conn, nombre)
    return {**p, "sector": sector, "lineas": lineas_patron(p)}


# 10. Contador de usuarios
class Visita(BaseModel):
    visitante: str


@app.post("/api/visita")
async def visita(data: Visita):
    """El mapa avisa una vez al dia con un numero al azar que genero el navegador (no identifica a nadie)."""
    if not RE_VISITANTE.match(data.visitante or ""):
        raise HTTPException(status_code=422, detail="Visitante invalido.")
    with closing(conectar()) as conn, conn:
        registrar_actividad(conn, "mapa", data.visitante)
    return {"status": "ok"}


@app.get("/api/contador")
async def contador():
    """Vecinos que usaron Radar en los ultimos 30 dias (mapa + bot). None hasta llegar a CONTADOR_MINIMO."""
    with closing(conectar()) as conn:
        e = estadisticas(conn)
    return {"mes": e["mes"]["total"] if e["mes"]["total"] >= CONTADOR_MINIMO else None}


@app.get("/api/estadisticas")
async def ver_estadisticas(request: Request):
    """Panel privado: requiere VL_CLAVE_ESTADISTICAS en la cabecera X-Radar-Clave."""
    if not CLAVE_ESTADISTICAS:
        raise HTTPException(status_code=404, detail="Panel desactivado.")
    if not hmac.compare_digest(request.headers.get("x-radar-clave", ""), CLAVE_ESTADISTICAS):
        raise HTTPException(status_code=403, detail="Clave incorrecta.")
    with closing(conectar()) as conn:
        return estadisticas(conn)


@app.get("/api/salud")
async def salud():
    with closing(conectar()) as conn:
        n = conn.execute("SELECT COUNT(*) FROM circuitos").fetchone()[0]
    return {"status": "ok", "reportes": n, "hora_venezuela": texto_hora(), "horas_corte": HORAS_CORTE}


if __name__ == "__main__":
    # Tarea nocturna (cron): docker exec luz_backend_python python main.py recalcular-cortes
    import sys
    if sys.argv[1:] == ["recalcular-cortes"]:
        with closing(conectar()) as conn, conn:
            print(f"{texto_hora()} cortes recalculados: {recalcular_cortes(conn)}")
    else:
        print("uso: python main.py recalcular-cortes")
