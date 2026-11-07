import { describe, expect, it, vi } from 'vitest';
import { avisarVisita, fechaLocal, idVisitante } from './visita';

describe('contador de visitas', () => {
  it('genera un numero al azar y lo reutiliza', () => {
    const id = idVisitante();
    expect(id).toMatch(/^[A-Za-z0-9-]{8,64}$/);
    expect(idVisitante()).toBe(id);
  });

  it('avisa una sola vez por dia y sin datos personales', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    expect(await avisarVisita('2026-11-07')).toBe(true);
    expect(await avisarVisita('2026-11-07')).toBe(false);
    expect(await avisarVisita('2026-11-08')).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const cuerpo = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(Object.keys(cuerpo)).toEqual(['visitante']);
  });

  it('sin conexion no marca el dia, para intentar de nuevo', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('sin red')));
    expect(await avisarVisita('2026-11-07')).toBe(false);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    expect(await avisarVisita('2026-11-07')).toBe(true);
  });

  it('funciona aunque el almacenamiento falle', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('bloqueado'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('bloqueado'); });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    expect(idVisitante()).toMatch(/^[A-Za-z0-9-]{8,64}$/);
    expect(await avisarVisita()).toBe(true);
  });

  it('formatea la fecha local', () => {
    expect(fechaLocal(new Date(2026, 0, 5))).toBe('2026-01-05');
  });
});
