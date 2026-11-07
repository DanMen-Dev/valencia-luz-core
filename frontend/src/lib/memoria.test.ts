import { describe, expect, it, vi } from 'vitest';
import { marcarConfirmado, yaConfirmado } from './memoria';

describe('memoria de confirmaciones', () => {
  it('recuerda un grupo confirmado', () => {
    expect(yaConfirmado('prebo:1')).toBe(false);
    marcarConfirmado('prebo:1');
    expect(yaConfirmado('prebo:1')).toBe(true);
  });

  it('olvida las confirmaciones de hace mas de 12 horas', () => {
    localStorage.setItem('radar.confirmados', JSON.stringify({ 'prebo:1': Date.now() - 13 * 3600 * 1000 }));
    expect(yaConfirmado('prebo:1')).toBe(false);
  });

  it('sigue funcionando si el almacenamiento falla', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('bloqueado'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('bloqueado'); });
    expect(() => marcarConfirmado('prebo:1')).not.toThrow();
    expect(yaConfirmado('prebo:1')).toBe(false);
  });
});
