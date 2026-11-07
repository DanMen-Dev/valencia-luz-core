"""Pruebas del backend: reportes por WhatsApp y web, conversacion, mapa y estadisticas sin datos inventados."""
import importlib
from contextlib import closing
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


def test_el_mapa_dice_de_donde_sale_el_retorno(app_mod, cliente):
    insertar(app_mod, "prebo", 0, app_mod.ahora() - timedelta(hours=1))
    estimado = cliente.get("/api/mapa/activos").json()[0]["hora_estimada"]
    assert estimado.endswith(f"(aprox., promedio general de {app_mod.HORAS_CORTE} h)")


def test_un_corte_sin_noticias_vence_y_sale_del_mapa(app_mod, cliente):
    insertar(app_mod, "prebo", 0, app_mod.ahora() - timedelta(hours=app_mod.HORAS_CORTE, minutes=10))
    assert cliente.get("/api/mapa/activos").json() == []


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


def test_sin_cortes_medidos_usa_el_promedio_general_y_lo_dice(app_mod):
    import sqlite3 as s
    base = app_mod.ahora().replace(hour=12, minute=0, second=0, microsecond=0)
    insertar(app_mod, "guaparo", 0, base)
    conn = s.connect(app_mod.DB_PATH)
    conn.row_factory = s.Row
    r = app_mod.resumen_zona(conn, "guaparo", momento=base + timedelta(hours=1))
    assert r["retorno_fuente"] == "promedio_general"
    assert r["retorno_estimado"] == app_mod.hora_legible(base + timedelta(hours=app_mod.HORAS_CORTE))
    assert "promedio general" in app_mod.mensaje_zona(r)
    vencido = app_mod.resumen_zona(conn, "guaparo", momento=base + timedelta(hours=app_mod.HORAS_CORTE + 1))
    assert vencido["estado"] == "sin_reportes" and vencido["retorno_estimado"] is None


def test_volvio_la_luz_cierra_el_corte_y_un_nuevo_corte_reinicia_el_ciclo(app_mod):
    import sqlite3 as s
    base = app_mod.ahora().replace(hour=8, minute=0, second=0, microsecond=0)
    insertar(app_mod, "prebo", 0, base, tel="58414001")
    insertar(app_mod, "prebo", 1, base + timedelta(hours=3), tel="58414001")
    insertar(app_mod, "prebo", 0, base + timedelta(hours=5), tel="58414002")
    conn = s.connect(app_mod.DB_PATH)
    conn.row_factory = s.Row
    r = app_mod.resumen_zona(conn, "prebo", momento=base + timedelta(hours=6))
    assert r["cortes_hoy"] == 2 and r["duracion_promedio_horas"] == 3.0
    assert r["inicio_corte_hoy"] == app_mod.hora_legible(base + timedelta(hours=5))
    assert r["retorno_fuente"] == "promedio_sector"


@pytest.mark.parametrize("serie, tipos", [
    ([(0, 0), (7, 0)], ["vencido", "abierto"]),     # 7 h sin noticias: el primero vencio
    ([(0, 0), (4, 0), (9, 0)], ["abierto"]),        # un 'sin luz' a las 4 h renueva el plazo
    ([(0, 0), (7, 1)], ["medido"]),                 # 'volvio' algo tarde: todavia mide
    ([(0, 0), (13, 1)], ["vencido"]),               # 'volvio' muy tarde: no mide nada
])
def test_episodios_con_vencimiento(app_mod, serie, tipos):
    base = app_mod.ahora().replace(hour=6, minute=0, second=0, microsecond=0)
    filas = [{"timestamp": app_mod.texto_hora(base + timedelta(hours=h)), "tiene_luz": luz} for h, luz in serie]
    cortes = app_mod.episodios(filas, momento=base + timedelta(hours=serie[-1][0] + 1), horas_corte=6)
    assert [c[2] for c in cortes] == tipos


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


def test_la_migracion_calcula_celdas_y_votos(tmp_path, monkeypatch):
    ruta = tmp_path / "vieja.db"
    with sqlite3.connect(ruta) as c:
        c.execute("""CREATE TABLE circuitos (id INTEGER PRIMARY KEY AUTOINCREMENT, telefono TEXT, latitud REAL,
                     longitud REAL, nombre_zona TEXT, tiene_luz INTEGER, timestamp DATETIME)""")
        c.execute("INSERT INTO circuitos (telefono, latitud, longitud, nombre_zona, tiene_luz, timestamp) "
                  "VALUES ('58414', 10.2134, -68.0125, 'prebo-Lat:10.2-Lon:-68.0', 0, '2026-09-18 10:00:00')")
        c.execute("INSERT INTO circuitos (telefono, latitud, longitud, nombre_zona, tiene_luz, timestamp) "
                  "VALUES ('web', 10.2134, -68.0125, 'guaparo', 0, '2026-09-18 11:00:00')")   # web: no vota
    monkeypatch.setenv("VL_DB_PATH", str(ruta))
    import main
    importlib.reload(main)
    main.init_db()   # dos veces: no debe duplicar votos
    with sqlite3.connect(ruta) as c:
        assert {f[0] for f in c.execute("SELECT celda FROM circuitos")} == {"10.21_-68.02"}
        assert c.execute("SELECT nombre, celda, votos FROM alias").fetchall() == [("prebo", "10.21_-68.02", 1)]


# ---------- Celdas y nombres populares

def nombrar(cliente, tel, texto, lat=10.2134, lon=-68.0125):
    assert gps(cliente, tel=tel, lat=lat, lon=lon).status_code == 200
    return cliente.post("/api/reportar/nombre", json={"telefono": tel, "nombre_zona": texto})


def test_celdas_fijas_y_vecinas(app_mod):
    assert app_mod.celda_de(10.21, -68.0125) == "10.21_-68.02"     # 10.21 no cae en 10.20 por coma flotante
    assert app_mod.celda_de(10.2199, -68.0001) == "10.21_-68.01"
    assert app_mod.centro_celda("10.21_-68.02") == (10.215, -68.015)
    vecinas = app_mod.celdas_vecinas("10.21_-68.02")
    assert len(set(vecinas)) == 9 and "10.22_-68.01" in vecinas and "10.20_-68.03" in vecinas


@pytest.mark.parametrize("texto, esperado", [
    ("Urb. La Prebo", "prebo"), ("Sector Prebo", "prebo"), ("  PREBO ", "prebo"),
    ("Zona Industrial", "industrial"), ("Sector", "sector"),
])
def test_limpiar_alias(app_mod, texto, esperado):
    assert app_mod.limpiar_alias(texto) == esperado


def test_el_nombre_que_escribe_el_vecino_vota_en_su_celda(app_mod, cliente):
    nombrar(cliente, "58414001", "Prebo")
    nombrar(cliente, "58414002", "Urb. Prebo")
    nombrar(cliente, "58414003", "Prevo")
    with sqlite3.connect(app_mod.DB_PATH) as c:
        votos = dict(((n, cel), v) for n, cel, v in c.execute("SELECT nombre, celda, votos FROM alias"))
    assert votos == {("prebo", "10.21_-68.02"): 2, ("prevo", "10.21_-68.02"): 1}


def test_una_variante_minoritaria_se_ve_con_el_nombre_mas_votado(cliente):
    for i, texto in enumerate(["Prebo", "prebo", "Sector Prebo"]):
        nombrar(cliente, f"5841400{i}", texto)
    nombrar(cliente, "58414009", "Prevo")
    assert {m["nombre_zona"] for m in cliente.get("/api/mapa/activos").json()} == {"prebo"}


def test_un_sector_de_borde_conserva_su_nombre(cliente):
    for i in range(2):
        nombrar(cliente, f"5841400{i}", "Prebo")
    nombrar(cliente, "58414009", "Kerdell")      # 1 de 3 votos (33 %): tiene peso propio
    assert {m["nombre_zona"] for m in cliente.get("/api/mapa/activos").json()} == {"prebo", "kerdell"}


def test_el_reporte_web_toma_el_nombre_de_su_celda_o_de_sus_vecinas(cliente):
    nombrar(cliente, "58414001", "Prebo")
    misma = cliente.post("/api/reportar", json={"latitud": 10.2180, "longitud": -68.0110, "tiene_luz": 0}).json()
    vecina = cliente.post("/api/reportar", json={"latitud": 10.2250, "longitud": -68.0125, "tiene_luz": 0}).json()
    lejos = cliente.post("/api/reportar", json={"latitud": 10.4000, "longitud": -68.0125, "tiene_luz": 0}).json()
    assert (misma["circuito_asignado"], vecina["circuito_asignado"], lejos["circuito_asignado"]) == \
        ("PREBO", "PREBO", "SIN ZONA")


def test_el_resumen_del_sector_suma_todas_sus_variantes(app_mod, cliente):
    for i, texto in enumerate(["Prebo", "prebo", "Urb Prebo"]):
        nombrar(cliente, f"5841400{i}", texto)
    nombrar(cliente, "58414009", "Prevo")
    r = cliente.get("/api/analitica/historico", params={"zona": "Sector Prebo"}).json()
    assert r["estado"] == "sin_luz" and r["reportes_7_dias"] == 4


def test_consultar_un_nombre_popular_y_sus_celdas(cliente):
    nombrar(cliente, "58414001", "Prebo")
    r = cliente.get("/api/sectores", params={"nombre": "Urb. Prebo"}).json()
    assert r["nombre"] == "prebo" and r["conocido"] is True
    assert r["celdas"][0]["id"] == "10.21_-68.02" and r["celdas"][0]["cubre"] is True
    assert cliente.get("/api/sectores", params={"nombre": "Guaparo"}).json()["conocido"] is False


# ---------- Busqueda tolerante

@pytest.mark.parametrize("a, b, d", [
    ("prebo", "prebo", 0), ("prevo", "prebo", 1), ("perbo", "prebo", 1),    # cambio e intercambio de vecinas
    ("tocuyto", "tocuyito", 1), ("prebos", "prebo", 1), ("guaparo", "prebo", 6),
])
def test_distancia_letras(app_mod, a, b, d):
    assert app_mod.distancia_letras(a, b) == d


@pytest.fixture
def sectores(cliente):
    """Prebo (3 votos + 1 'Prevo'), Tocuyito, San Diego, Prado (2) y Pardo (1), en celdas distintas."""
    datos = [("Prebo", 10.2134, -68.0125)] * 3 + [("Prevo", 10.2134, -68.0125)] + \
        [("Tocuyito", 10.10, -68.08)] * 2 + [("San Diego", 10.25, -67.95)] + \
        [("Prado", 10.30, -68.10)] * 2 + [("Pardo", 10.35, -68.15)]
    for i, (texto, lat, lon) in enumerate(datos):
        nombrar(cliente, f"584140{i:03d}", texto, lat=lat, lon=lon)
    return cliente


@pytest.mark.parametrize("escrito, metodo, nombre", [
    ("Urb Prebo", "exacto", "prebo"),
    ("prevo", "exacto", "prebo"),          # variante amarrada a la celda de Prebo
    ("Perbo", "aproximado", "prebo"),
    ("Tocuyto", "aproximado", "tocuyito"),
    ("sandiego", "aproximado", "san diego"),
    ("Prdo", "desconocido", "prdo"),       # nombres cortos: un cambio ya puede ser otro sector
    ("Guaparo", "desconocido", "guaparo"),
])
def test_resolver_sector(app_mod, sectores, escrito, metodo, nombre):
    with closing(app_mod.conectar()) as conn:
        r = app_mod.resolver_sector(conn, escrito)
    assert (r["metodo"], r["nombre"]) == (metodo, nombre)


def test_dos_sectores_igual_de_parecidos_se_pregunta(app_mod, sectores):
    with closing(app_mod.conectar()) as conn:
        r = app_mod.resolver_sector(conn, "Paado")
    assert r["metodo"] == "ambiguo" and set(r["candidatos"]) == {"prado", "pardo"}
    msg = sectores.get("/api/analitica/historico", params={"zona": "Paado"}).json()["mensaje"]
    assert "¿te refieres a" in msg and "PRADO" in msg and "PARDO" in msg


def test_el_bot_dice_que_sector_entendio(sectores):
    r = sectores.get("/api/analitica/historico", params={"zona": "Tocuyto"}).json()
    assert r["sector"]["metodo"] == "aproximado"
    assert "Entendí TOCUYITO" in r["mensaje"] and "*Radar · TOCUYITO*" in r["mensaje"]
    exacto = sectores.get("/api/analitica/historico", params={"zona": "Prebo"}).json()["mensaje"]
    assert "Entendí" not in exacto


def test_salud(cliente):
    assert cliente.get("/api/salud").json()["status"] == "ok"
