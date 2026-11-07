import { useCallback, useEffect, useRef, useState } from 'react';
import { obtenerReportes } from '../lib/api';
import type { Reporte } from '../types';

const REFRESCO_MS = 60_000;

export interface EstadoReportes {
  reportes: Reporte[];
  cargando: boolean;
  error: boolean;
  actualizado: Date | null;
  recargar: () => Promise<void>;
}

// Trae los reportes al montar, cada minuto mientras la pestana esta visible y al volver a ella.
export function useReportes(): EstadoReportes {
  const [reportes, setReportes] = useState<Reporte[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(false);
  const [actualizado, setActualizado] = useState<Date | null>(null);
  const enCurso = useRef<AbortController | null>(null);

  const recargar = useCallback(async () => {
    enCurso.current?.abort();
    const control = new AbortController();
    enCurso.current = control;
    try {
      const datos = await obtenerReportes(control.signal);
      setReportes(datos);
      setError(false);
      setActualizado(new Date());
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError(true);
    } finally {
      if (enCurso.current === control) setCargando(false);
    }
  }, []);

  useEffect(() => {
    void recargar();
    const intervalo = window.setInterval(() => { if (!document.hidden) void recargar(); }, REFRESCO_MS);
    const alVolver = () => { if (!document.hidden) void recargar(); };
    document.addEventListener('visibilitychange', alVolver);
    return () => {
      window.clearInterval(intervalo);
      document.removeEventListener('visibilitychange', alVolver);
      enCurso.current?.abort();
    };
  }, [recargar]);

  return { reportes, cargando, error, actualizado, recargar };
}
