import { useCallback, useEffect, useState } from 'react';

// Evento que Chrome/Edge (Android y escritorio) disparan cuando la app se puede instalar
interface EventoInstalar extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

// Guarda el aviso de instalacion para mostrarlo con nuestro propio boton. En iPhone no existe:
// alli se instala desde Compartir -> Agregar a inicio.
export function useInstalar() {
  const [evento, setEvento] = useState<EventoInstalar | null>(null);

  useEffect(() => {
    const alPoder = (e: Event) => { e.preventDefault(); setEvento(e as EventoInstalar); };
    const alInstalar = () => setEvento(null);
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

  return { puedeInstalar: evento !== null, instalar };
}
