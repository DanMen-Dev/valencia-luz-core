// Lo que devuelve GET /api/v1/mapa/circuitos (el gateway lo toma de /api/mapa/activos del backend)
export interface Reporte {
  id: number;
  nombre_zona: string;
  lat: number;
  lon: number;
  tiene_luz: 0 | 1;
  capa_color: 'gris' | 'amarillo';
  hora_inicio: string;
  hora_estimada: string;
  actualizado: string;
}

export interface Config {
  whatsapp: string;
  horas: number;   // un corte sin noticias vence a estas horas (VL_HORAS_CORTE)
}

export interface RespuestaReporte {
  status: string;
  circuito_asignado: string;
  tiene_luz: 0 | 1;
}

export type Aviso = { texto: string; tipo: 'ok' | 'error' | 'info' } | null;

export interface RespuestaConfirmacion {
  status: string;
  zona: string;
  tiene_luz: 0 | 1;
}
