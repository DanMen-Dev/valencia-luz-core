import { useEffect, useState } from 'react';
import { MapaReportes, type Foco } from './components/MapaReportes';
import { Panel } from './components/Panel';
import { useReportes } from './hooks/useReportes';
import { useInstalar } from './hooks/useInstalar';
import { HORAS_POR_DEFECTO, confirmarSector, enVenezuela, enviarReporte, obtenerConfig, obtenerContador, ubicacionActual } from './lib/api';
import { avisarVisita } from './lib/visita';
import type { Grupo } from './lib/agrupar';
import type { Aviso } from './types';

// ?lat=..&lon=.. (enlace desde WhatsApp): el mapa abre centrado en esa ubicacion
function focoInicial(): Foco | null {
  const q = new URLSearchParams(window.location.search);
  const lat = parseFloat(q.get('lat') ?? ''), lon = parseFloat(q.get('lon') ?? '');
  return enVenezuela(lat, lon) ? { lat, lon, zoom: 16, marcador: 'Tu reporte está aquí' } : null;
}

export default function App() {
  const estado = useReportes();
  const { puedeInstalar, instalar, ayuda } = useInstalar();
  const [whatsapp, setWhatsapp] = useState('');
  const [telegram, setTelegram] = useState('');
  const [horas, setHoras] = useState(HORAS_POR_DEFECTO);
  const [contador, setContador] = useState<number | null>(null);
  const [aviso, setAviso] = useState<Aviso>(null);
  const [enviando, setEnviando] = useState(false);
  const [foco, setFoco] = useState<Foco | null>(focoInicial);

  useEffect(() => {
    obtenerConfig().then(c => { setWhatsapp(c.whatsapp); setTelegram(c.telegram); setHoras(c.horas); }).catch(() => {});
    void avisarVisita();
    obtenerContador().then(setContador).catch(() => {});
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
      const sinRed = !navigator.onLine || e instanceof TypeError;
      setAviso({ tipo: 'error', texto: sinRed ? 'Sin conexión: tu reporte no se envió. Intenta de nuevo cuando vuelva la señal.' : (e as Error).message });
    } finally {
      setEnviando(false);
    }
  }

  // "Yo tambien" desde el popup de un grupo: no pide ubicacion, usa el centro del grupo
  async function confirmar(g: Grupo, tieneLuz: 0 | 1) {
    await confirmarSector(g.zona, g.lat, g.lon, tieneLuz);
    void estado.recargar();
  }

  return (
    <div className="app">
      <Panel {...estado} contador={contador} whatsapp={whatsapp} telegram={telegram} horas={horas} puedeInstalar={puedeInstalar} ayudaInstalar={ayuda} onInstalar={() => void instalar()} aviso={aviso} enviando={enviando} onReportar={reportar} />
      <main className="contenedor-mapa">
        <MapaReportes reportes={estado.reportes} foco={foco} onConfirmar={confirmar} />
      </main>
    </div>
  );
}
