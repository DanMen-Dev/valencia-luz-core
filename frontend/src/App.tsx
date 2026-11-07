import { useEffect, useState } from 'react';
import { MapaReportes, type Foco } from './components/MapaReportes';
import { Panel } from './components/Panel';
import { useReportes } from './hooks/useReportes';
import { enVenezuela, enviarReporte, obtenerConfig, ubicacionActual } from './lib/api';
import type { Aviso } from './types';

// ?lat=..&lon=.. (enlace desde WhatsApp): el mapa abre centrado en esa ubicacion
function focoInicial(): Foco | null {
  const q = new URLSearchParams(window.location.search);
  const lat = parseFloat(q.get('lat') ?? ''), lon = parseFloat(q.get('lon') ?? '');
  return enVenezuela(lat, lon) ? { lat, lon, zoom: 16, marcador: 'Tu reporte está aquí' } : null;
}

export default function App() {
  const estado = useReportes();
  const [whatsapp, setWhatsapp] = useState('');
  const [aviso, setAviso] = useState<Aviso>(null);
  const [enviando, setEnviando] = useState(false);
  const [foco, setFoco] = useState<Foco | null>(focoInicial);

  useEffect(() => {
    obtenerConfig().then(c => setWhatsapp(c.whatsapp || '')).catch(() => {});
  }, []);

  async function reportar(tieneLuz: 0 | 1) {
    setEnviando(true);
    setAviso({ texto: 'Buscando tu ubicación…', tipo: 'info' });
    try {
      const pos = await ubicacionActual();
      const { latitude: lat, longitude: lon } = pos.coords;
      const r = await enviarReporte(lat, lon, tieneLuz);
      const zona = r.circuito_asignado && r.circuito_asignado !== 'SIN ZONA' ? ` en ${r.circuito_asignado}` : '';
      setAviso({
        tipo: 'ok',
        texto: tieneLuz ? `Gracias: registramos que volvió la luz${zona}.` : `Gracias: tu reporte de corte${zona} ya está en el mapa.`,
      });
      setFoco({ lat, lon, zoom: 15 });
      await estado.recargar();
    } catch (e) {
      setAviso({ tipo: 'error', texto: (e as Error).message });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="app">
      <Panel {...estado} whatsapp={whatsapp} aviso={aviso} enviando={enviando} onReportar={reportar} />
      <main className="contenedor-mapa">
        <MapaReportes reportes={estado.reportes} foco={foco} />
      </main>
    </div>
  );
}
