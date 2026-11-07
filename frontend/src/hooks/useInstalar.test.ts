import { describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { detectarPlataforma, useInstalar } from './useInstalar';

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

  it('sin aviso del navegador en computadora no ofrece nada', () => {
    const { result } = renderHook(() => useInstalar());
    expect(result.current.puedeInstalar).toBe(false);
    expect(result.current.ayuda).toBeNull();   // jsdom no es iPhone ni Android
  });

  it('oculta el boton cuando la app ya se instalo', () => {
    const { result } = renderHook(() => useInstalar());
    act(() => { window.dispatchEvent(eventoInstalar('dismissed')); });
    act(() => { window.dispatchEvent(new Event('appinstalled')); });
    expect(result.current.puedeInstalar).toBe(false);
  });
});

describe('detectarPlataforma', () => {
  it('reconoce iPhone, iPad moderno, Android y computadora', () => {
    expect(detectarPlataforma('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)', 5)).toBe('ios');
    expect(detectarPlataforma('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 5)).toBe('ios');
    expect(detectarPlataforma('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 0)).toBe('otro');
    expect(detectarPlataforma('Mozilla/5.0 (Linux; Android 14; SM-A155M)', 5)).toBe('android');
    expect(detectarPlataforma('Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 0)).toBe('otro');
  });
});
