import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type ComponentType } from 'react';
import { Circle, MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import iconoUrl from 'leaflet/dist/images/marker-icon.png';
import iconoRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import sombraUrl from 'leaflet/dist/images/marker-shadow.png';
import { PopupGrupo, type Confirmar } from './PopupGrupo';
import { TILES_OSM, tieneWebGL } from '../lib/fondoMapa';
import { agrupar, radioGrupo, type Grupo } from '../lib/agrupar';
import type { Reporte } from '../types';

type PropsFondo = { onFalla: () => void; onListo: () => void };

// Si el archivo del fondo vectorial no llega (sin conexion la primera vez), se queda el respaldo
function SinFondo({ onFalla }: PropsFondo) {
  useEffect(() => { onFalla(); }, [onFalla]);
  return null;
}

// MapLibre pesa ~300 KB comprimido: se carga aparte, despues de la app y los circulos.
// Mientras tanto (y si falla) se ve el mapa de OpenStreetMap en imagenes.
const FondoVectorial = lazy(() =>
  import('./FondoVectorial')
    .then(m => ({ default: m.FondoVectorial as ComponentType<PropsFondo> }))
    .catch(() => ({ default: SinFondo })));

// Con un empaquetador, Leaflet no encuentra solo las imagenes del marcador
L.Icon.Default.mergeOptions({ iconUrl: iconoUrl, iconRetinaUrl: iconoRetinaUrl, shadowUrl: sombraUrl });

const COLORES = { sin_luz: '#9e9e9e', con_luz: '#ffd54f' } as const;

// Numero de reportes en el centro del circulo (solo si hay mas de uno). No intercepta clics: el popup es del circulo.
function etiqueta(g: Grupo) {
  return L.divIcon({ className: `conteo-grupo ${g.estado}`, html: String(g.total), iconSize: [28, 28], iconAnchor: [14, 14] });
}
export const CENTRO_VALENCIA: [number, number] = [10.165, -68.021];

export interface Foco { lat: number; lon: number; zoom: number; marcador?: string }

function Enfocar({ foco }: { foco: Foco | null }) {
  const map = useMap();
  useEffect(() => {
    if (foco) map.setView([foco.lat, foco.lon], foco.zoom);
  }, [foco, map]);
  return null;
}

export function MapaReportes({ reportes, foco, onConfirmar }: { reportes: Reporte[]; foco: Foco | null; onConfirmar?: Confirmar }) {
  const grupos = useMemo(() => agrupar(reportes), [reportes]);
  const [vectorial, setVectorial] = useState(tieneWebGL);
  const [vectorialListo, setVectorialListo] = useState(false);
  const alFallar = useCallback(() => { setVectorial(false); setVectorialListo(false); }, []);
  const alEstarListo = useCallback(() => setVectorialListo(true), []);
  return (
    <MapContainer
      center={foco ? [foco.lat, foco.lon] : CENTRO_VALENCIA}
      zoom={foco?.zoom ?? 13}
      className="mapa"
    >
      {/* Las imagenes de OpenStreetMap se ven hasta que el fondo vectorial termina de dibujarse */}
      {!(vectorial && vectorialListo) && <TileLayer url={TILES_OSM} maxZoom={19} attribution="© OpenStreetMap" />}
      {vectorial && (
        <Suspense fallback={null}>
          <FondoVectorial onFalla={alFallar} onListo={alEstarListo} />
        </Suspense>
      )}
      <Enfocar foco={foco} />
      {grupos.map(g => (
        <Circle
          key={g.clave}
          center={[g.lat, g.lon]}
          radius={radioGrupo(g.total)}
          pathOptions={{ color: COLORES[g.estado], fillColor: COLORES[g.estado], fillOpacity: 0.4, weight: 1.5 }}
        >
          <Popup><PopupGrupo g={g} onConfirmar={onConfirmar} /></Popup>
        </Circle>
      ))}
      {grupos.filter(g => g.total > 1).map(g => (
        <Marker key={`n-${g.clave}`} position={[g.lat, g.lon]} icon={etiqueta(g)} interactive={false} keyboard={false} />
      ))}
      {foco?.marcador && (
        <Marker position={[foco.lat, foco.lon]}>
          <Popup>{foco.marcador}</Popup>
        </Marker>
      )}
    </MapContainer>
  );
}
