import { describe, expect, it } from 'vitest';
import { agrupar, distanciaKm, normalizarZona, radioGrupo } from './agrupar';
import { reporte } from '../test/datos';

// ~0.01 grados de latitud ≈ 1,1 km
describe('agrupar', () => {
  it('junta reportes del mismo sector que estan cerca y promedia su centro', () => {
    const g = agrupar([
      reporte({ id: 1, lat: 10.20, lon: -68.00 }),
      reporte({ id: 2, lat: 10.21, lon: -68.00, nombre_zona: 'Prebo ' }),
    ]);
    expect(g).toHaveLength(1);
    expect(g[0].total).toBe(2);
    expect(g[0].lat).toBeCloseTo(10.205, 5);
  });

  it('separa sectores distintos aunque esten cerca', () => {
    const g = agrupar([reporte({ id: 1 }), reporte({ id: 2, nombre_zona: 'guaparo' })]);
    expect(g.map(x => x.zona).sort()).toEqual(['guaparo', 'prebo']);
  });

  it('separa el mismo nombre en dos focos lejanos', () => {
    const g = agrupar([reporte({ id: 1, lat: 10.20 }), reporte({ id: 2, lat: 10.30 })]);
    expect(g).toHaveLength(2);
  });

  it('reportes sin sector solo se juntan si estan muy cerca', () => {
    const sinNombre = { nombre_zona: 'sector sin nombre' };
    const g = agrupar([
      reporte({ id: 1, ...sinNombre, lat: 10.200 }),
      reporte({ id: 2, ...sinNombre, lat: 10.203 }),   // ~330 m: mismo grupo
      reporte({ id: 3, ...sinNombre, lat: 10.215 }),   // ~1,7 km: otro grupo
    ]);
    expect(g.map(x => x.total)).toEqual([2, 1]);
    expect(g[0].zona).toBe('');
  });

  it('el estado lo decide la mayoria y, si empatan, el reporte mas reciente', () => {
    const [mayoria] = agrupar([
      reporte({ id: 1, actualizado: '2026-11-07 08:00:00' }),
      reporte({ id: 2, actualizado: '2026-11-07 08:10:00' }),
      reporte({ id: 3, tiene_luz: 1, actualizado: '2026-11-07 09:00:00' }),
    ]);
    expect(mayoria.estado).toBe('sin_luz');
    expect([mayoria.sinLuz, mayoria.conLuz]).toEqual([2, 1]);

    const [empate] = agrupar([
      reporte({ id: 1, actualizado: '2026-11-07 08:00:00' }),
      reporte({ id: 2, tiene_luz: 1, actualizado: '2026-11-07 09:00:00' }),
    ]);
    expect(empate.estado).toBe('con_luz');
    expect(empate.ultimoReporte).toBe('2026-11-07 09:00:00');
  });

  it('toma el primer corte y un retorno estimado real (no el texto de "sin estimacion")', () => {
    const [g] = agrupar([
      reporte({ id: 2, hora_inicio: '9:42 AM', actualizado: '2026-11-07 09:42:00', hora_estimada: 'Sin estimación (faltan datos)' }),
      reporte({ id: 1, hora_inicio: '7:10 AM', actualizado: '2026-11-07 07:10:00', hora_estimada: '1:20 PM' }),
    ]);
    expect(g.primerCorte).toBe('7:10 AM');
    expect(g.retornoEstimado).toBe('1:20 PM');
  });

  it('da la misma clave al grupo entre recargas aunque cambie el orden', () => {
    const a = reporte({ id: 1, actualizado: '2026-11-07 07:00:00' });
    const b = reporte({ id: 2, actualizado: '2026-11-07 08:00:00' });
    expect(agrupar([a, b])[0].clave).toBe(agrupar([b, a])[0].clave);
  });
});

describe('ayudas', () => {
  it('normaliza nombres y trata "sin zona" como sin sector', () => {
    expect(normalizarZona('  San   Diego ')).toBe('san diego');
    expect(normalizarZona('SIN ZONA')).toBe('');
  });

  it('mide distancias razonables', () => {
    expect(distanciaKm(10.16, -68.02, 10.17, -68.02)).toBeCloseTo(1.11, 1);
  });

  it('el radio crece con los reportes y tiene tope', () => {
    expect(radioGrupo(1)).toBe(400);
    expect(radioGrupo(5)).toBeGreaterThan(radioGrupo(2));
    expect(radioGrupo(500)).toBe(1200);
  });
});
