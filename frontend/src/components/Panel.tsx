import type { Aviso, Reporte } from '../types';

interface Props {
  reportes: Reporte[];
  cargando: boolean;
  error: boolean;
  actualizado: Date | null;
  whatsapp: string;
  horas: number;
  aviso: Aviso;
  enviando: boolean;
  onReportar: (tieneLuz: 0 | 1) => void;
}

function resumen({ reportes, cargando, error, actualizado, horas }: Pick<Props, 'reportes' | 'cargando' | 'error' | 'actualizado' | 'horas'>) {
  if (cargando) return 'Cargando reportes…';
  if (error) return 'No se pudieron cargar los reportes. Reintentando…';
  const hora = actualizado?.toLocaleTimeString('es-VE', { hour: 'numeric', minute: '2-digit' }) ?? '';
  const sin = reportes.filter(r => r.tiene_luz === 0).length;
  const con = reportes.length - sin;
  return reportes.length === 0
    ? `Sin reportes en las últimas ${horas} horas · actualizado ${hora}`
    : `${sin} sin luz · ${con} con luz (últimas ${horas} h) · actualizado ${hora}`;
}

export function Panel(props: Props) {
  const { whatsapp, aviso, enviando, onReportar } = props;
  return (
    <aside className="panel">
      <header>
        <h1>Radar <span aria-hidden="true">📡</span></h1>
        <p className="sub">Cortes de luz reportados por los vecinos, en vivo. No es información oficial de Corpoelec.</p>
      </header>

      <section className="acciones" aria-label="Reportar">
        <button type="button" className="btn btn-corte" disabled={enviando} onClick={() => onReportar(0)}>
          📍 No hay luz donde estoy
        </button>
        <button type="button" className="btn btn-volvio" disabled={enviando} onClick={() => onReportar(1)}>
          💡 Ya volvió la luz donde estoy
        </button>
        {whatsapp && (
          <a className="btn btn-wa" href={`https://wa.me/${whatsapp}?text=${encodeURIComponent('Hola')}`}
             target="_blank" rel="noopener noreferrer">
            💬 Reportar por WhatsApp
          </a>
        )}
        <p className={`aviso ${aviso?.tipo ?? ''}`} role="status" aria-live="polite">{aviso?.texto ?? ''}</p>
      </section>

      <section className="leyenda" aria-label="Leyenda">
        <div className="item"><span className="punto gris" /> Sin luz (reporte de un vecino)</div>
        <div className="item"><span className="punto amarillo" /> Volvió la luz</div>
        <p className="nota">Un corte sin noticias sale del mapa a las {props.horas} h: se asume que volvió.</p>
        <p className="estado">{resumen(props)}</p>
      </section>
    </aside>
  );
}
