import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PopupReporte } from './PopupReporte';
import { reporte } from '../test/datos';

describe('PopupReporte', () => {
  it('muestra el sector en mayusculas y el retorno estimado cuando no hay luz', () => {
    render(<PopupReporte r={reporte()} />);
    expect(screen.getByText(/PREBO/)).toBeInTheDocument();
    expect(screen.getByText('SIN LUZ')).toBeInTheDocument();
    expect(screen.getByText(/Retorno estimado: 1:20 PM/)).toBeInTheDocument();
  });

  it('no muestra retorno estimado cuando volvio la luz', () => {
    render(<PopupReporte r={reporte({ tiene_luz: 1, capa_color: 'amarillo' })} />);
    expect(screen.getByText('VOLVIÓ LA LUZ')).toBeInTheDocument();
    expect(screen.queryByText(/Retorno estimado/)).not.toBeInTheDocument();
  });

  it('trata el nombre del sector como texto, nunca como HTML', () => {
    const { container } = render(<PopupReporte r={reporte({ nombre_zona: 'prebo <img src=x onerror=alert(1)>' })} />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText(/<IMG SRC=X ONERROR=ALERT\(1\)>/)).toBeInTheDocument();
  });

  it('usa un nombre por defecto si el sector viene vacio', () => {
    render(<PopupReporte r={reporte({ nombre_zona: '' })} />);
    expect(screen.getByText(/SECTOR SIN NOMBRE/)).toBeInTheDocument();
  });
});
