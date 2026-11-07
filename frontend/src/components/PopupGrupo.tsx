import type { Grupo } from '../lib/agrupar';

function vecinos(n: number) { return n === 1 ? '1 vecino' : `${n} vecinos`; }

// React escapa el texto: el nombre del sector que escribe un vecino nunca se interpreta como HTML
export function PopupGrupo({ g }: { g: Grupo }) {
  const sinLuz = g.estado === 'sin_luz';
  return (
    <div className="pop">
      <strong className="zona">📍 {(g.zona || 'Sector sin nombre').toUpperCase()}</strong>
      <span className={`badge ${sinLuz ? 'sin' : 'con'}`}>{sinLuz ? 'SIN LUZ' : 'VOLVIÓ LA LUZ'}</span>
      {g.total > 1 && (
        <span className="linea conteo">
          {g.sinLuz > 0 && `${vecinos(g.sinLuz)} sin luz`}
          {g.sinLuz > 0 && g.conLuz > 0 && ' · '}
          {g.conLuz > 0 && `${vecinos(g.conLuz)} con luz`}
        </span>
      )}
      {g.primerCorte && <span className="linea">⏳ {g.total > 1 ? 'Primer reporte de corte' : 'Reportado'} a las {g.primerCorte}</span>}
      {!g.primerCorte && <span className="linea">💡 Reportado a las {g.reportes[0].hora_inicio || '—'}</span>}
      {sinLuz && <span className="linea">🚀 Retorno estimado: {g.retornoEstimado ?? 'sin datos suficientes'}</span>}
      <small>Último reporte · {g.ultimoReporte} (hora de Venezuela)</small>
    </div>
  );
}
