from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime, timedelta

app = FastAPI(title="Valencia Luz - Motor Probabilístico Histórico")

# Base de datos simulada en memoria
# Ahora guarda: estado_actual (1 o 0), inicio_ultimo_corte, historial_cortes_horas
CIRCUITOS_DB = {}

class ReporteLuz(BaseModel):
    latitud: float
    longitud: float
    tiene_luz: int

@app.get("/")
def inicio():
    return {
        "status": "online",
        "circuitos_monitoreados": len(CIRCUITOS_DB)
    }

@app.post("/api/reportar")
def registrar_reporte(reporte: ReporteLuz):
    global CIRCUITOS_DB
    
    # Redondeo a 3 decimales (aproximadamente una cuadra de 110 metros)
    lat_key = round(reporte.latitud, 3)
    lon_key = round(reporte.longitud, 3)
    circuito_id = f"cir-lat{str(lat_key).replace('.', '')}-lon{str(lon_key).replace('.', '')}"
    
    ahora = datetime.now()
    
    # Si el circuito es completamente nuevo en el sistema
    if circuito_id not in CIRCUITOS_DB:
        CIRCUITOS_DB[circuito_id] = {
            "id": circuito_id,
            "lat": lat_key,
            "lon": lon_key,
            "estado_actual": reporte.tiene_luz,
            "horas_con_energia": 4.0 if reporte.tiene_luz == 1 else 0.0,
            "promedio_corte_historico": 4.0, # Asumimos 4 horas estándar de corte inicial
            "inicio_ultimo_corte": ahora if reporte.tiene_luz == 0 else None,
            "ultimo_cambio_estado": ahora,
            "historial_cortes_horas": []
        }
        return {"status": "success", "mensaje": "Circuito fundado", "circuito_asignado": circuito_id}

    # Si el circuito ya existía, evaluamos el cambio de estado (Transición temporal)
    circuito = CIRCUITOS_DB[circuito_id]
    estado_anterior = circuito["estado_actual"]
    
    # REGLA 1: SE FUE LA LUZ (Pasa de 1 a 0)
    if estado_anterior == 1 and reporte.tiene_luz == 0:
        circuito["estado_actual"] = 0
        circuito["inicio_ultimo_corte"] = ahora
        circuito["ultimo_cambio_estado"] = ahora
        circuito["horas_con_energia"] = 0.0

    # REGLA 2: LLEGÓ LA LUZ (Pasa de 0 a 1 - El caso que planteaste en Suba)
    elif estado_anterior == 0 and reporte.tiene_luz == 1:
        circuito["estado_actual"] = 1
        circuito["ultimo_cambio_estado"] = ahora
        circuito["horas_con_energia"] = 1.0 # Arranca con 1 hora de estabilidad
        
        # CALCULAMOS LA MEMORIA HISTÓRICA: ¿Cuánto duró el apagón?
        if circuito["inicio_ultimo_corte"]:
            duracion_corte = (ahora - circuito["inicio_ultimo_corte"]).total_seconds() / 3600.0
            circuito["historial_cortes_horas"].append(round(duracion_corte, 2))
            
            # Recalculamos el promedio histórico de cortes de esa cuadra (Promedio Móvil)
            historial = circuito["historial_cortes_horas"]
            circuito["promedio_corte_historico"] = sum(historial) / len(historial)
            circuito["inicio_ultimo_corte"] = None # Reseteamos el marcador del corte

    # REGLA 3: REPORTES HOMOGÉNEOS CONTINUOS (Sigue en el mismo estado)
    else:
        # Si sigue habiendo luz, calculamos de forma realista cuántas horas lleva estable
        if reporte.tiene_luz == 1:
            horas_transcurridas = (ahora - circuito["ultimo_cambio_estado"]).total_seconds() / 3600.0
            circuito["horas_con_energia"] = min(horas_transcurridas + 1.0, 24.0)
        else:
            circuito["horas_con_energia"] = 0.0

    return {"status": "success", "circuito_asignado": circuito_id, "estado_actual": circuito["estado_actual"]}





