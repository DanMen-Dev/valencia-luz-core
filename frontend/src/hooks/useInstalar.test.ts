import { describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useInstalar } from './useInstalar';

function eventoInstalar(resultado: 'accepted' | 'dismissed') {
  const e = new Event('beforeinstallprompt', { cancelable: true }) as Event & { prompt: () => Promise<void>; userChoice: Promise<unknown> };
  e.prompt = vi.fn().mockResolvedValue(undefined);
  e.userChoice = Promise.resolve({ outcome: resultado });
  return e;
}

describe('useInstalar', () => {
  it('guarda el aviso del navegador y lo muestra al pedirlo', async () => {
    const { result } = renderHook(() => useInstalar());
    expect(result.current.puedeInstalar).toBe(false);
    const e = eventoInstalar('accepted');
    act(() => { window.dispatchEvent(e); });
    expect(e.defaultPrevented).toBe(true);
    expect(result.current.puedeInstalar).toBe(true);
    await act(() => result.current.instalar());
    expect(e.prompt).toHaveBeenCalledOnce();
    expect(result.current.puedeInstalar).toBe(false);
  });

  it('oculta el boton cuando la app ya se instalo', () => {
    const { result } = renderHook(() => useInstalar());
    act(() => { window.dispatchEvent(eventoInstalar('dismissed')); });
    act(() => { window.dispatchEvent(new Event('appinstalled')); });
    expect(result.current.puedeInstalar).toBe(false);
  });
});
