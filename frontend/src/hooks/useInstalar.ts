import { useCallback, useEffect, useState } from 'react';

// Evento que Chrome/Edge (Android y computadora) disparan cuando la app se puede instalar
interface EventoInstalar extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

export type Plataforma = 'ios' | 'android' | 'otro';

export function detectarPlataforma(ua: string, tactil: number): Plataforma {
  if (/iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && tactil > 1)) return 'ios';   // iPad moderno dice "Macintosh"
  if (/Android/i.test(ua)) return 'android';
  return 'otro';
}

function abiertaComoApp(): boolean {
  const iosApp = (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return iosApp || (typeof window.matchMedia === 'function' && window.matchMedia('(display-mode: standalone)').matches);
}

// Chrome/Edge: guardamos su aviso para mostrarlo con nuestro boton. iPhone no tiene aviso: alli se explica
// como agregarla desde Compartir. Si ya esta abierta como app instalada, no se ofrece nada.
export function useInstalar() {
  const [evento, setEvento] = useState<EventoInstalar | null>(null);
  const [instalada, setInstalada] = useState(abiertaComoApp);
  const [plataforma] = useState<Plataforma>(() => detectarPlataforma(navigator.userAgent, navigator.maxTouchPoints ?? 0));

  useEffect(() => {
    const alPoder = (e: Event) => { e.preventDefault(); setEvento(e as EventoInstalar); };
    const alInstalar = () => { setEvento(null); setInstalada(true); };
    window.addEventListener('beforeinstallprompt', alPoder);
    window.addEventListener('appinstalled', alInstalar);
    return () => {
      window.removeEventListener('beforeinstallprompt', alPoder);
      window.removeEventListener('appinstalled', alInstalar);
    };
  }, []);

  const instalar = useCallback(async () => {
    if (!evento) return;
    await evento.prompt();
    await evento.userChoice.catch(() => undefined);
    setEvento(null);
  }, [evento]);

  // Que mostrar: el boton (si el navegador avisa), una ayuda paso a paso, o nada
  const ayuda: 'ios' | 'android' | null =
    instalada || evento ? null : plataforma === 'ios' ? 'ios' : plataforma === 'android' ? 'android' : null;

  return { puedeInstalar: !instalada && evento !== null, instalar, ayuda };
}
