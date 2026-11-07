import type { Config, Reporte, RespuestaConfirmacion, RespuestaReporte } from '../types';

export const HORAS_POR_DEFECTO = 6;

// Limites aproximados de Venezuela: el backend aplica los mismos al guardar
const VENEZUELA = { latMin: 0.5, latMax: 12.6, lonMin: -73.5, lonMax: -59.5 };

export function enVenezuela(lat: number, lon: number): boolean {
  return Number.isFinite(lat) && Number.isFinite(lon) &&
    lat >= VENEZUELA.latMin && lat <= VENEZUELA.latMax &&
    lon >= VENEZUELA.lonMin && lon <= VENEZUELA.lonMax;
}

export interface Lectura {
  reportes: Reporte[];
  guardadoEn: Date | null;   // con valor: sin conexion, es la copia que guardo el service worker a esa hora
}

export async function obtenerReportes(senal?: AbortSignal): Promise<Lectura> {
  const r = await fetch('/api/v1/mapa/circuitos', { cache: 'no-store', signal: senal });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const datos: unknown = await r.json();
  const marca = r.headers.get('X-Radar-Guardado');
  const guardadoEn = marca && !Number.isNaN(Date.parse(marca)) ? new Date(marca) : null;
  const reportes = Array.isArray(datos) ? (datos as Reporte[]).filter(d => enVenezuela(Number(d.lat), Number(d.lon))) : [];
  return { reportes, guardadoEn };
}

export async function obtenerConfig(): Promise<Config> {
  const r = await fetch('/api/v1/config');
  if (!r.ok) return { whatsapp: '', horas: HORAS_POR_DEFECTO };
  const c = (await r.json()) as Partial<Config>;
  return { whatsapp: c.whatsapp || '', horas: Number(c.horas) > 0 ? Number(c.horas) : HORAS_POR_DEFECTO };
}

export async function enviarReporte(latitud: number, longitud: number, tieneLuz: 0 | 1): Promise<RespuestaReporte> {
  const r = await fetch('/api/v1/reportar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ latitud, longitud, tiene_luz: tieneLuz }),
  });
  const cuerpo = (await r.json().catch(() => ({}))) as Partial<RespuestaReporte> & { error?: string };
  if (!r.ok) throw new Error(cuerpo.error || 'No se pudo registrar el reporte.');
  return cuerpo as RespuestaReporte;
}

// "Yo tambien": suma un reporte al sector de un grupo que ya existe (no pide la ubicacion del vecino)
export async function confirmarSector(zona: string, latitud: number, longitud: number, tieneLuz: 0 | 1): Promise<RespuestaConfirmacion> {
  const r = await fetch('/api/v1/confirmar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ zona, latitud, longitud, tiene_luz: tieneLuz }),
  });
  const cuerpo = (await r.json().catch(() => ({}))) as Partial<RespuestaConfirmacion> & { error?: string };
  if (!r.ok) throw new Error(cuerpo.error || 'No se pudo registrar tu confirmación.');
  return cuerpo as RespuestaConfirmacion;
}

export function ubicacionActual(): Promise<GeolocationPosition> {
  return new Promise((resolver, rechazar) => {
    if (!navigator.geolocation) {
      rechazar(new Error('Tu navegador no permite compartir la ubicación.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolver, () =>
      rechazar(new Error('No pudimos leer tu ubicación. Activa el permiso de ubicación del navegador e intenta de nuevo.')),
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
  });
}
