import { useState } from 'react';
import type { Grupo } from '../lib/agrupar';
import { marcarConfirmado, yaConfirmado } from '../lib/memoria';

export type Confirmar = (g: Grupo, tieneLuz: 0 | 1) => Promise<void>;

function vecinos(n: number) { return n === 1 ? '1 vecino' : `${n} vecinos`; }

type Estado = { tipo: 'listo' } | { tipo: 'enviando' } | { tipo: 'hecho'; tieneLuz: 0 | 1 } | { tipo: 'error'; texto: string };

// React escapa el texto: el nombre del sector que escribe un vecino nunca se interpreta como HTML
export function PopupGrupo({ g, onConfirmar }: { g: Grupo; onConfirmar?: Confirmar }) {
  const sinLuz = g.estado === 'sin_luz';
  const [estado, setEstado] = useState<Estado>(() => (yaConfirmado(g.clave) ? { tipo: 'hecho', tieneLuz: sinLuz ? 0 : 1 } : { tipo: 'listo' }));
  const puedeConfirmar = Boolean(onConfirmar && g.zona);

  async function confirmar(tieneLuz: 0 | 1) {
    if (!onConfirmar) return;
    setEstado({ tipo: 'enviando' });
    try {
      await onConfirmar(g, tieneLuz);
      marcarConfirmado(g.clave);
      setEstado({ tipo: 'hecho', tieneLuz });
    } catch (e) {
      setEstado({ tipo: 'error', texto: (e as Error).message });
    }
  }

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

      {puedeConfirmar && (
        <div className="confirmar">
          {estado.tipo === 'hecho' ? (
            <span className="gracias">✅ ¡Gracias! Tu {estado.tieneLuz ? 'aviso de que hay luz' : 'reporte de corte'} ya cuenta.</span>
          ) : (
            <>
              <span className="pregunta">¿Estás en {g.zona.toUpperCase()}?</span>
              <button type="button" className="btn-pop principal" disabled={estado.tipo === 'enviando'}
                      onClick={() => confirmar(sinLuz ? 0 : 1)}>
                🙋 {sinLuz ? 'Yo también estoy sin luz' : 'A mí también me volvió'}
              </button>
              <button type="button" className="btn-pop" disabled={estado.tipo === 'enviando'}
                      onClick={() => confirmar(sinLuz ? 1 : 0)}>
                {sinLuz ? '💡 Aquí ya volvió' : '📍 Yo sigo sin luz'}
              </button>
              {estado.tipo === 'error' && <span className="error-pop" role="alert">{estado.texto}</span>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
