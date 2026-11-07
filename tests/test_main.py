"""Pruebas del backend: reportes por WhatsApp y web, conversacion, mapa y estadisticas sin datos inventados."""
import importlib
import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

TEL = "584144253799"


@pytest.fixture
def app_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("VL_DB_PATH", str(tmp_path / "datos" / "prueba.db"))
    import main
    return importlib.reload(main)


@pytest.fixture
def cliente(app_mod):
    return TestClient(app_mod.app)


def gps(cliente, tel=TEL, lat=10.2134, lon=-68.0125):
    return cliente.post("/api/reportar/gps", json={"telefono": tel, "latitud": lat, "longitud": lon})


def insertar(app_mod, zona, tiene_luz, cuando, tel="584140000001", lat=10.2134, lon=-68.0125):
    with sqlite3.connect(app_mod.DB_PATH) as c:
        c.execute("""INSERT INTO circuitos (telefono, latitud, longitud, nombre_zona, zona, tiene_luz, timestamp)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""", (tel, lat, lon, zona, zona, tiene_luz, app_mod.texto_hora(cuando)))


# ---------- Utilidades

def test_normalizar_telefono_y_zona(app_mod):
    assert app_mod.normalizar_telefono("+58 414-425 3799") == TEL
    assert app_mod.normalizar_telefono(" 584144253799") == TEL          # el '+' de la URL llega como espacio
    assert app_mod.normalizar_zona("  San Diégo ") == "san diego"
    assert app_mod.normalizar_zona("La-Isabelica!!") == "la isabelica"


@pytest.mark.parametrize("texto, esperado", [
    ("Prebo", ("prebo", 0)),
    ("Si, Prebo", ("prebo", 1)),
    ("sí prebo", ("prebo", 1)),
    ("1 Tocuyito", ("tocuyito", 1)),
    ("No, San Diego", ("san diego", 0)),
    ("Sinai", ("sinai", 0)),                 # empieza con "si" pero es un nombre
])
def test_interpretar_respuesta(app_mod, texto, esperado):
    assert app_mod.interpretar_respuesta(texto) == esperado


def test_zona_de_reportes_viejos(app_mod):
    assert app_mod.zona_de("prebo-Lat:10.2134-Lon:-68.0125") == "prebo"
    assert app_mod.zona_de("-Lat:10.2-Lon:-68.0") == ""


# ---------- Flujo de WhatsApp

def test_flujo_completo_por_whatsapp(cliente):
    assert gps(cliente).status_code == 200
    # n8n consulta con el '+' (que en la URL llega como espacio)
    assert cliente.get("/api/usuario/esperando-nombre", params={"telefono": "+" + TEL}).json() == {"estado": "esperando"}
    r = cliente.post("/api/reportar/nombre", json={"telefono": TEL, "nombre_zona": "Prebo", "tiene_luz": 0})
    assert r.status_code == 200
    assert r.json()["zona"] == "prebo"
    assert cliente.get("/api/usuario/esperando-nombre", params={"telefono": TEL}).json() == {"estado": "libre"}
    mapa = cliente.get("/api/mapa/activos").json()
    assert len(mapa) == 1
    assert mapa[0]["nombre_zona"] == "prebo"
    assert "-" not in mapa[0]["nombre_zona"]
    assert mapa[0]["capa_color"] == "gris"


def test_volvio_la_luz_con_los_campos_que_manda_n8n(cliente):
    gps(cliente)
    # n8n manda tiene_luz calculado por includes('si'): aqui llega 1 y el texto "Si, Prebo"
    r = cliente.post("/api/reportar/nombre", json={"telefono": TEL, "nombre_zona": "Si, Prebo", "tiene_luz": 1})
    assert r.json()["zona"] == "prebo" and r.json()["tiene_luz"] == 1
    assert cliente.get("/api/mapa/activos").json()[0]["capa_color"] == "amarillo"


def test_no_confunde_un_sector_que_contiene_si(cliente):
    gps(cliente)
    # n8n calcula tiene_luz=1 porque "Casiano" contiene "si": manda el texto
    r = cliente.post("/api/reportar/nombre", json={"telefono": TEL, "nombre_zona": "Casiano", "tiene_luz": 1})
    assert r.json()["zona"] == "casiano" and r.json()["tiene_luz"] == 0


def test_acepta_los_nombres_de_campo_anteriores(cliente):
    gps(cliente)
    r = cliente.post("/api/reportar/nombre", json={"telefono": TEL, "zona": "Guaparo", "estado_luz": 1})
    assert r.json()["zona"] == "guaparo" and r.json()["tiene_luz"] == 1


def test_sin_ubicacion_pendiente_da_404(cliente):
    r = cliente.post("/api/reportar/nombre", json={"telefono": TEL, "nombre_zona": "Prebo"})
    assert r.status_code == 404


def test_la_espera_del_nombre_vence(app_mod, cliente, monkeypatch):
    gps(cliente)
    futuro = app_mod.ahora() + timedelta(minutes=app_mod.MINUTOS_ESPERA_NOMBRE + 1)
    monkeypatch.setattr(app_mod, "ahora", lambda: futuro)
    assert cliente.get("/api/usuario/esperando-nombre", params={"telefono": TEL}).json() == {"estado": "libre"}


def test_la_conversacion_sobrevive_a_un_reinicio(app_mod, cliente):
    gps(cliente)
    reiniciado = TestClient(importlib.reload(app_mod).app)
    assert reiniciado.get("/api/usuario/esperando-nombre", params={"telefono": TEL}).json() == {"estado": "esperando"}


def test_un_nuevo_pin_reemplaza_al_pendiente(app_mod, cliente):
    gps(cliente, lat=10.1)
    gps(cliente, lat=10.3)
    with sqlite3.connect(app_mod.DB_PATH) as c:
        filas = c.execute("SELECT latitud FROM circuitos WHERE nombre_zona = ?", (app_mod.PENDIENTE,)).fetchall()
    assert filas == [(10.3,)]


def test_tope_de_reportes_por_hora(app_mod, cliente):
    for _ in range(app_mod.REPORTES_POR_HORA):
        assert gps(cliente).status_code == 200
        cliente.post("/api/reportar/nombre", json={"telefono": TEL, "nombre_zona": "Prebo"})
    assert gps(cliente).status_code == 429


def test_coordenadas_fuera_de_venezuela(cliente):
    assert gps(cliente, lat=40.4, lon=-3.7).status_code == 422


# ---------- Mapa y web

def test_reporte_web_toma_la_zona_cercana(app_mod, cliente):
    insertar(app_mod, "prebo", 0, app_mod.ahora() - timedelta(hours=1))
    r = cliente.post("/api/reportar", json={"latitud": 10.2140, "longitud": -68.0120, "tiene_luz": 0})
    assert r.status_code == 200
    assert r.json()["circuito_asignado"] == "PREBO"


def test_en_el_mapa_cuenta_el_ultimo_reporte_de_cada_telefono(app_mod, cliente):
    insertar(app_mod, "prebo", 0, app_mod.ahora() - timedelta(hours=3))
    insertar(app_mod, "prebo", 1, app_mod.ahora() - timedelta(hours=1))
    mapa = cliente.get("/api/mapa/activos").json()
    assert len(mapa) == 1 and mapa[0]["capa_color"] == "amarillo"


def test_el_mapa_no_inventa_el_retorno(app_mod, cliente):
    insertar(app_mod, "prebo", 0, app_mod.ahora() - timedelta(hours=1))
    assert cliente.get("/api/mapa/activos").json()[0]["hora_estimada"] == "Sin estimación (faltan datos)"


def test_yo_tambien_suma_un_reporte_al_sector(app_mod, cliente):
    insertar(app_mod, "prebo", 0, app_mod.ahora() - timedelta(hours=1))
    r = cliente.post("/api/confirmar", json={"zona": "Prebo", "latitud": 10.2150, "longitud": -68.0110, "tiene_luz": 0})
    assert r.status_code == 200 and r.json()["zona"] == "PREBO"
    mapa = cliente.get("/api/mapa/activos").json()
    assert len(mapa) == 2 and {m["nombre_zona"] for m in mapa} == {"prebo"}
    with sqlite3.connect(app_mod.DB_PATH) as c:
        assert c.execute("SELECT origen FROM circuitos WHERE telefono = 'web'").fetchone()[0] == "confirmacion"


def test_yo_tambien_puede_decir_que_volvio(app_mod, cliente):
    insertar(app_mod, "prebo", 0, app_mod.ahora() - timedelta(hours=1))
    r = cliente.post("/api/confirmar", json={"zona": "prebo", "latitud": 10.2134, "longitud": -68.0125, "tiene_luz": 1})
    assert r.json()["tiene_luz"] == 1


@pytest.mark.parametrize("cuerpo, codigo", [
    ({"zona": "guaparo", "latitud": 10.2134, "longitud": -68.0125, "tiene_luz": 0}, 404),   # sector sin reportes
    ({"zona": "prebo", "latitud": 10.40, "longitud": -68.0125, "tiene_luz": 0}, 404),      # lejos del sector
    ({"zona": "  ", "latitud": 10.2134, "longitud": -68.0125, "tiene_luz": 0}, 422),       # sin sector
    ({"zona": "prebo", "latitud": 4.71, "longitud": -74.07, "tiene_luz": 0}, 422),         # fuera de Venezuela
])
def test_yo_tambien_no_inventa_sectores(app_mod, cliente, cuerpo, codigo):
    insertar(app_mod, "prebo", 0, app_mod.ahora() - timedelta(hours=1))
    assert cliente.post("/api/confirmar", json=cuerpo).status_code == codigo


def test_yo_tambien_ignora_reportes_viejos(app_mod, cliente):
    insertar(app_mod, "prebo", 0, app_mod.ahora() - timedelta(hours=app_mod.HORAS_MAPA + 1))
    r = cliente.post("/api/confirmar", json={"zona": "prebo", "latitud": 10.2134, "longitud": -68.0125, "tiene_luz": 0})
    assert r.status_code == 404


def test_los_pendientes_no_salen_en_el_mapa(cliente):
    gps(cliente)
    assert cliente.get("/api/mapa/activos").json() == []


# ---------- Estadisticas

def test_zona_sin_reportes_no_inventa_horas(cliente):
    r = cliente.get("/api/analitica/historico", params={"zona": "Prebo"}).json()
    assert r["hora_corte"] == "sin reportes de corte hoy"
    assert "11:00" not in r["mensaje"] and "5:00" not in r["mensaje"]
    assert "todavía no hay reportes" in r["mensaje"]


def test_resumen_zona(app_mod):
    import sqlite3 as s
    base = app_mod.ahora().replace(hour=12, minute=0, second=0, microsecond=0)
    for dias, horas in ((2, 4), (3, 6)):
        inicio = base - timedelta(days=dias)
        insertar(app_mod, "prebo", 0, inicio, tel="58414001")
        insertar(app_mod, "prebo", 1, inicio + timedelta(hours=horas), tel="58414001")
    insertar(app_mod, "prebo", 0, base, tel="58414002")
    conn = s.connect(app_mod.DB_PATH)
    conn.row_factory = s.Row
    r = app_mod.resumen_zona(conn, "prebo", momento=base + timedelta(hours=1))
    assert r["estado"] == "sin_luz"
    assert r["duracion_promedio_horas"] == 5.0
    assert r["cortes_medidos_7_dias"] == 2
    assert r["inicio_corte_hoy"] == "12:00 PM"
    assert r["retorno_estimado"] == "5:00 PM"
    assert r["dias_con_corte_7_dias"] == 3
    msg = app_mod.mensaje_zona(r)
    assert "sin luz" in msg and "5:00 PM" in msg and "2 cortes medidos" in msg


def test_historico_conserva_los_campos_que_lee_n8n(cliente):
    r = cliente.get("/api/analitica/historico", params={"zona": "prebo"}).json()
    for campo in ("zona", "hora_corte", "hora_retorno", "duracion_promedio", "reincidencia_detectada", "mensaje"):
        assert r[campo] not in (None, "")


def test_migra_reportes_viejos(tmp_path, monkeypatch):
    ruta = tmp_path / "vieja.db"
    with sqlite3.connect(ruta) as c:
        c.execute("""CREATE TABLE circuitos (id INTEGER PRIMARY KEY AUTOINCREMENT, telefono TEXT, latitud REAL,
                     longitud REAL, nombre_zona TEXT, tiene_luz INTEGER, timestamp DATETIME)""")
        c.execute("INSERT INTO circuitos (telefono, latitud, longitud, nombre_zona, tiene_luz, timestamp) "
                  "VALUES ('58414', 10.2, -68.0, 'prebo-Lat:10.2-Lon:-68.0', 0, '2026-09-18 10:00:00')")
    monkeypatch.setenv("VL_DB_PATH", str(ruta))
    import main
    importlib.reload(main)
    with sqlite3.connect(ruta) as c:
        assert c.execute("SELECT zona, origen FROM circuitos").fetchone() == ("prebo", "whatsapp")


def test_salud(cliente):
    assert cliente.get("/api/salud").json()["status"] == "ok"
