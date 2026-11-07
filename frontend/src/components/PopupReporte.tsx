import type { Reporte } from '../types';

// React escapa el texto: el nombre del sector que escribe un vecino nunca se interpreta como HTML
export function PopupReporte({ r }: { r: Reporte }) {
  const sinLuz = r.tiene_luz === 0;
  return (
    <div className="pop">
      <strong className="zona">📍 {(r.nombre_zona || 'Sector sin nombre').toUpperCase()}</strong>
      <span className={`badge ${sinLuz ? 'sin' : 'con'}`}>{sinLuz ? 'SIN LUZ' : 'VOLVIÓ LA LUZ'}</span>
      <span className="linea">{sinLuz ? '⏳' : '💡'} Reportado a las {r.hora_inicio || '—'}</span>
      {sinLuz && <span className="linea">🚀 Retorno estimado: {r.hora_estimada || 'sin datos'}</span>}
      <small>Hora de Venezuela · {r.actualizado}</small>
    </div>
  );
}
