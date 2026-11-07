import type { Reporte } from '../types';

export function reporte(parcial: Partial<Reporte> = {}): Reporte {
  return {
    id: 1,
    nombre_zona: 'prebo',
    lat: 10.21,
    lon: -68.0,
    tiene_luz: 0,
    capa_color: 'gris',
    hora_inicio: '9:42 AM',
    hora_estimada: '1:20 PM',
    actualizado: '2026-11-07 09:42:10',
    ...parcial,
  };
}

export function respuesta(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}
