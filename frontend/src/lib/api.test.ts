import { describe, expect, it, vi } from 'vitest';
import { confirmarSector, enVenezuela, enviarReporte, obtenerConfig, obtenerReportes } from './api';
import { reporte, respuesta } from '../test/datos';

describe('enVenezuela', () => {
  it('acepta Valencia y rechaza Bogota, Madrid y valores invalidos', () => {
    expect(enVenezuela(10.16, -68.02)).toBe(true);
    expect(enVenezuela(4.71, -74.07)).toBe(false);
    expect(enVenezuela(40.4, -3.7)).toBe(false);
    expect(enVenezuela(NaN, -68)).toBe(false);
  });
});

describe('obtenerReportes', () => {
  it('descarta reportes con coordenadas fuera de Venezuela', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta([reporte({ id: 1 }), reporte({ id: 2, lat: 40, lon: 3 })])));
    const datos = await obtenerReportes();
    expect(datos.map(d => d.id)).toEqual([1]);
  });

  it('falla si el gateway responde con error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta({ error: 'x' }, 502)));
    await expect(obtenerReportes()).rejects.toThrow('HTTP 502');
  });
});

describe('enviarReporte', () => {
  it('manda latitud, longitud y estado al gateway', async () => {
    const fetchMock = vi.fn().mockResolvedValue(respuesta({ status: 'success', circuito_asignado: 'PREBO', tiene_luz: 1 }));
    vi.stubGlobal('fetch', fetchMock);
    const r = await enviarReporte(10.2, -68.01, 1);
    expect(r.circuito_asignado).toBe('PREBO');
    const [url, opciones] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/reportar');
    expect(JSON.parse(opciones.body)).toEqual({ latitud: 10.2, longitud: -68.01, tiene_luz: 1 });
  });

  it('muestra el mensaje de error que devuelve el gateway', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta({ error: 'Esa ubicación está fuera de Venezuela.' }, 422)));
    await expect(enviarReporte(4.7, -74.0, 0)).rejects.toThrow('Esa ubicación está fuera de Venezuela.');
  });
});

describe('confirmarSector', () => {
  it('manda el sector, el centro del grupo y el estado', async () => {
    const fetchMock = vi.fn().mockResolvedValue(respuesta({ status: 'success', zona: 'PREBO', tiene_luz: 0 }));
    vi.stubGlobal('fetch', fetchMock);
    await confirmarSector('prebo', 10.21, -68.0, 0);
    const [url, opciones] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/confirmar');
    expect(JSON.parse(opciones.body)).toEqual({ zona: 'prebo', latitud: 10.21, longitud: -68.0, tiene_luz: 0 });
  });

  it('pasa el mensaje de error del gateway', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta({ error: 'Ese sector ya no tiene reportes activos.' }, 404)));
    await expect(confirmarSector('prebo', 10.21, -68.0, 0)).rejects.toThrow('Ese sector ya no tiene reportes activos.');
  });
});

describe('obtenerConfig', () => {
  it('lee el numero de WhatsApp y las horas de vencimiento', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta({ whatsapp: '584141234567', horas: 4 })));
    expect(await obtenerConfig()).toEqual({ whatsapp: '584141234567', horas: 4 });
  });

  it('usa 6 horas si el gateway no las manda o falla', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta({ whatsapp: '' })));
    expect((await obtenerConfig()).horas).toBe(6);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta({}, 502)));
    expect(await obtenerConfig()).toEqual({ whatsapp: '', horas: 6 });
  });
});
