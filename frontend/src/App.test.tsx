import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { respuesta } from './test/datos';

// Leaflet necesita un navegador real; aqui se prueba el flujo de la app, no el dibujo del mapa
vi.mock('./components/MapaReportes', () => ({
  MapaReportes: () => <div data-testid="mapa" />,
}));

function rutas(reportar: Response) {
  return vi.fn((url: string) => {
    if (url === '/api/v1/config') return Promise.resolve(respuesta({ whatsapp: '' }));
    if (url === '/api/v1/mapa/circuitos') return Promise.resolve(respuesta([]));
    if (url === '/api/v1/reportar') return Promise.resolve(reportar);
    return Promise.reject(new Error('ruta inesperada ' + url));
  });
}

function ubicacion(lat: number, lon: number) {
  Object.defineProperty(navigator, 'geolocation', {
    configurable: true,
    value: { getCurrentPosition: (ok: PositionCallback) => ok({ coords: { latitude: lat, longitude: lon } } as GeolocationPosition) },
  });
}

describe('App', () => {
  beforeEach(() => ubicacion(10.2, -68.01));

  it('confirma el reporte y recarga el mapa', async () => {
    const fetchMock = rutas(respuesta({ status: 'success', circuito_asignado: 'PREBO', tiene_luz: 0 }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    await screen.findByText(/Sin reportes en las últimas 12 horas/);
    await userEvent.click(screen.getByRole('button', { name: /No hay luz/ }));
    expect(await screen.findByText('Gracias: tu reporte de corte en PREBO ya está en el mapa.')).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([u]) => u === '/api/v1/mapa/circuitos').length).toBeGreaterThanOrEqual(2));
  });

  it('muestra el error cuando la ubicacion esta fuera de Venezuela', async () => {
    ubicacion(4.71, -74.07);
    vi.stubGlobal('fetch', rutas(respuesta({ error: 'Esa ubicación está fuera de Venezuela.' }, 422)));
    render(<App />);
    await userEvent.click(screen.getByRole('button', { name: /No hay luz/ }));
    expect(await screen.findByText('Esa ubicación está fuera de Venezuela.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /No hay luz/ })).toBeEnabled();
  });

  it('avisa si el navegador no da la ubicacion', async () => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition: (_ok: PositionCallback, err: PositionErrorCallback) => err({} as GeolocationPositionError) },
    });
    vi.stubGlobal('fetch', rutas(respuesta({})));
    render(<App />);
    await userEvent.click(screen.getByRole('button', { name: /Ya volvió la luz/ }));
    expect(await screen.findByText(/No pudimos leer tu ubicación/)).toBeInTheDocument();
  });
});
