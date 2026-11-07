import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Panel, textoCompartir } from './Panel';
import { reporte } from '../test/datos';

const base = {
  reportes: [],
  cargando: false,
  error: false,
  actualizado: new Date(2026, 10, 7, 9, 43),
  whatsapp: '',
  horas: 6,
  aviso: null,
  enviando: false,
  onReportar: () => {},
};

describe('Panel', () => {
  it('cuenta los reportes con y sin luz', () => {
    render(<Panel {...base} reportes={[reporte({ id: 1 }), reporte({ id: 2 }), reporte({ id: 3, tiene_luz: 1 })]} />);
    expect(screen.getByText(/2 sin luz · 1 con luz/)).toBeInTheDocument();
  });

  it('avisa cuando no hay reportes, cuando carga y cuando falla', () => {
    const { rerender } = render(<Panel {...base} />);
    expect(screen.getByText(/Sin reportes en las últimas 6 horas/)).toBeInTheDocument();
    rerender(<Panel {...base} cargando />);
    expect(screen.getByText('Cargando reportes…')).toBeInTheDocument();
    rerender(<Panel {...base} error />);
    expect(screen.getByText(/No se pudieron cargar los reportes/)).toBeInTheDocument();
  });

  it('oculta el boton de WhatsApp sin numero y lo enlaza cuando hay uno', () => {
    const { rerender } = render(<Panel {...base} />);
    expect(screen.queryByRole('link', { name: /Reportar por WhatsApp/ })).not.toBeInTheDocument();
    rerender(<Panel {...base} whatsapp="584141234567" />);
    expect(screen.getByRole('link', { name: /Reportar por WhatsApp/ })).toHaveAttribute('href', 'https://wa.me/584141234567?text=Hola');
  });

  it('cada boton reporta su estado y se bloquean mientras se envia', async () => {
    const onReportar = vi.fn();
    const { rerender } = render(<Panel {...base} onReportar={onReportar} />);
    await userEvent.click(screen.getByRole('button', { name: /No hay luz/ }));
    await userEvent.click(screen.getByRole('button', { name: /Ya volvió la luz/ }));
    expect(onReportar.mock.calls).toEqual([[0], [1]]);
    rerender(<Panel {...base} enviando onReportar={onReportar} />);
    expect(screen.getByRole('button', { name: /No hay luz/ })).toBeDisabled();
  });

  it('avisa cuando muestra reportes guardados sin conexion', () => {
    render(<Panel {...base} guardadoEn={new Date(2026, 10, 7, 9, 40)} />);
    expect(screen.getByText(/Sin conexión: mostrando los reportes guardados/)).toBeInTheDocument();
  });

  it('ofrece instalar la app solo cuando el navegador lo permite', async () => {
    const onInstalar = vi.fn();
    const { rerender } = render(<Panel {...base} onInstalar={onInstalar} />);
    expect(screen.queryByRole('button', { name: /Instalar Radar/ })).not.toBeInTheDocument();
    rerender(<Panel {...base} puedeInstalar onInstalar={onInstalar} />);
    await userEvent.click(screen.getByRole('button', { name: /Instalar Radar/ }));
    expect(onInstalar).toHaveBeenCalledOnce();
  });

  it('en iPhone explica como agregar la app desde Compartir', () => {
    render(<Panel {...base} ayudaInstalar="ios" />);
    expect(screen.getByText(/Instalar Radar en tu iPhone/)).toBeInTheDocument();
    expect(screen.getByText('Agregar a inicio')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Instalar Radar/ })).not.toBeInTheDocument();
  });

  it('enlaza el bot de Telegram cuando esta configurado', () => {
    const { rerender } = render(<Panel {...base} />);
    expect(screen.queryByRole('link', { name: /Telegram/ })).not.toBeInTheDocument();
    rerender(<Panel {...base} telegram="RadarCortesBot" />);
    expect(screen.getByRole('link', { name: /Reportar por Telegram/ })).toHaveAttribute('href', 'https://t.me/RadarCortesBot');
  });

  it('siempre ofrece compartir el mapa por WhatsApp, sin numero de bot', () => {
    render(<Panel {...base} />);
    const enlace = screen.getByRole('link', { name: /Compartir el mapa por WhatsApp/ });
    expect(enlace.getAttribute('href')).toBe(`https://wa.me/?text=${encodeURIComponent(textoCompartir())}`);
    expect(textoCompartir('https://radar.brecha-cero.com')).toContain('https://radar.brecha-cero.com/mapa');
  });
});
