import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PopupGrupo } from './PopupGrupo';
import { agrupar } from '../lib/agrupar';
import { reporte } from '../test/datos';
import type { Reporte } from '../types';

const grupo = (...rs: Reporte[]) => agrupar(rs)[0];

describe('PopupGrupo', () => {
  it('un solo reporte sin luz: sector, estado y retorno, sin conteo de vecinos', () => {
    render(<PopupGrupo g={grupo(reporte())} />);
    expect(screen.getByText(/PREBO/)).toBeInTheDocument();
    expect(screen.getByText('SIN LUZ')).toBeInTheDocument();
    expect(screen.getByText(/Reportado a las 9:42 AM/)).toBeInTheDocument();
    expect(screen.getByText(/Retorno estimado: 1:20 PM/)).toBeInTheDocument();
    expect(screen.queryByText(/vecino/)).not.toBeInTheDocument();
  });

  it('varios reportes: cuenta vecinos con y sin luz y muestra el primer corte', () => {
    render(<PopupGrupo g={grupo(
      reporte({ id: 1, hora_inicio: '7:10 AM', actualizado: '2026-11-07 07:10:00' }),
      reporte({ id: 2, actualizado: '2026-11-07 08:00:00' }),
      reporte({ id: 3, tiene_luz: 1, actualizado: '2026-11-07 09:00:00' }),
    )} />);
    expect(screen.getByText('2 vecinos sin luz · 1 vecino con luz')).toBeInTheDocument();
    expect(screen.getByText(/Primer reporte de corte a las 7:10 AM/)).toBeInTheDocument();
  });

  it('volvio la luz: sin retorno estimado', () => {
    render(<PopupGrupo g={grupo(reporte({ tiene_luz: 1, capa_color: 'amarillo', hora_inicio: '8:02 AM' }))} />);
    expect(screen.getByText('VOLVIÓ LA LUZ')).toBeInTheDocument();
    expect(screen.getByText(/Reportado a las 8:02 AM/)).toBeInTheDocument();
    expect(screen.queryByText(/Retorno estimado/)).not.toBeInTheDocument();
  });

  it('trata el nombre del sector como texto, nunca como HTML', () => {
    const { container } = render(<PopupGrupo g={grupo(reporte({ nombre_zona: 'prebo <img src=x onerror=alert(1)>' }))} />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText(/<IMG SRC=X ONERROR=ALERT\(1\)>/)).toBeInTheDocument();
  });

  it('sin sector muestra un nombre por defecto', () => {
    render(<PopupGrupo g={grupo(reporte({ nombre_zona: 'sector sin nombre' }))} />);
    expect(screen.getByText(/SECTOR SIN NOMBRE/)).toBeInTheDocument();
  });
});
