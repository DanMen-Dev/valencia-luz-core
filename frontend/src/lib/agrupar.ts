import type { Reporte } from '../types';

// Un grupo = reportes del mismo sector que estan cerca entre si. En el mapa se dibuja como un solo circulo.
export interface Grupo {
  clave: string;
  zona: string;               // '' si los reportes no tienen sector
  lat: number;                // centro: promedio de los reportes
  lon: number;
  sinLuz: number;
  conLuz: number;
  total: number;
  estado: 'sin_luz' | 'con_luz';
  primerCorte: string | null; // hora del reporte de corte mas antiguo
  retornoEstimado: string | null;
  ultimoReporte: string;      // 'YYYY-MM-DD HH:MM:SS' del mas reciente
  reportes: Reporte[];
}

export const KM_MISMO_SECTOR = 2;   // reportes con el mismo nombre a mas de esto son otro foco
export const KM_SIN_NOMBRE = 0.5;   // reportes sin sector: solo se juntan si estan muy cerca
const SIN_NOMBRE = new Set(['', 'sector sin nombre', 'sin zona']);

export function distanciaKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad, dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(a));
}

export function normalizarZona(nombre: string | null | undefined): string {
  const z = (nombre ?? '').trim().toLowerCase().replace(/\s+/g, ' ');
  return SIN_NOMBRE.has(z) ? '' : z;
}

interface Borrador { zona: string; reportes: Reporte[]; lat: number; lon: number }

export function agrupar(reportes: Reporte[]): Grupo[] {
  const borradores: Borrador[] = [];
  // Del mas antiguo al mas nuevo: los grupos quedan estables entre una recarga y otra
  const ordenados = [...reportes].sort((a, b) => a.actualizado.localeCompare(b.actualizado) || a.id - b.id);
  for (const r of ordenados) {
    const zona = normalizarZona(r.nombre_zona);
    const limite = zona ? KM_MISMO_SECTOR : KM_SIN_NOMBRE;
    const destino = borradores.find(b => b.zona === zona && distanciaKm(b.lat, b.lon, r.lat, r.lon) <= limite);
    if (destino) {
      destino.reportes.push(r);
      const n = destino.reportes.length;
      destino.lat += (r.lat - destino.lat) / n;
      destino.lon += (r.lon - destino.lon) / n;
    } else {
      borradores.push({ zona, reportes: [r], lat: r.lat, lon: r.lon });
    }
  }
  return borradores.map(cerrar);
}

function cerrar(b: Borrador): Grupo {
  const sin = b.reportes.filter(r => r.tiene_luz === 0);
  const sinLuz = sin.length, conLuz = b.reportes.length - sinLuz;
  const ultimo = b.reportes[b.reportes.length - 1];
  // Manda la mayoria; si hay empate, el reporte mas reciente
  const estado = sinLuz > conLuz ? 'sin_luz' : conLuz > sinLuz ? 'con_luz' : ultimo.tiene_luz === 0 ? 'sin_luz' : 'con_luz';
  const conEstimado = [...sin].reverse().find(r => r.hora_estimada && !/sin estimaci/i.test(r.hora_estimada));
  return {
    clave: `${b.zona || 'sin-nombre'}:${b.reportes[0].id}`,
    zona: b.zona,
    lat: b.lat,
    lon: b.lon,
    sinLuz,
    conLuz,
    total: b.reportes.length,
    estado,
    primerCorte: sin[0]?.hora_inicio ?? null,
    retornoEstimado: conEstimado?.hora_estimada ?? null,
    ultimoReporte: ultimo.actualizado,
    reportes: b.reportes,
  };
}

// Radio del circulo en metros: crece con la raiz del numero de reportes, con tope
export function radioGrupo(total: number): number {
  return Math.min(1200, Math.round(400 + 150 * Math.sqrt(Math.max(0, total - 1))));
}
