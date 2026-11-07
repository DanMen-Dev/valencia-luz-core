import type { Config, Reporte, RespuestaReporte } from '../types';

// Limites aproximados de Venezuela: el backend aplica los mismos al guardar
const VENEZUELA = { latMin: 0.5, latMax: 12.6, lonMin: -73.5, lonMax: -59.5 };

export function enVenezuela(lat: number, lon: number): boolean {
  return Number.isFinite(lat) && Number.isFinite(lon) &&
    lat >= VENEZUELA.latMin && lat <= VENEZUELA.latMax &&
    lon >= VENEZUELA.lonMin && lon <= VENEZUELA.lonMax;
}

export async function obtenerReportes(senal?: AbortSignal): Promise<Reporte[]> {
  const r = await fetch('/api/v1/mapa/circuitos', { cache: 'no-store', signal: senal });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const datos: unknown = await r.json();
  if (!Array.isArray(datos)) return [];
  return (datos as Reporte[]).filter(d => enVenezuela(Number(d.lat), Number(d.lon)));
}

export async function obtenerConfig(): Promise<Config> {
  const r = await fetch('/api/v1/config');
  if (!r.ok) return { whatsapp: '' };
  return (await r.json()) as Config;
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
