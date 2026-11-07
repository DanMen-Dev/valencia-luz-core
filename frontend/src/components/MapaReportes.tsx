import { useEffect, useMemo } from 'react';
import { Circle, MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import iconoUrl from 'leaflet/dist/images/marker-icon.png';
import iconoRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import sombraUrl from 'leaflet/dist/images/marker-shadow.png';
import { PopupGrupo, type Confirmar } from './PopupGrupo';
import { agrupar, radioGrupo, type Grupo } from '../lib/agrupar';
import type { Reporte } from '../types';

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
  return (
    <MapContainer
      center={foco ? [foco.lat, foco.lon] : CENTRO_VALENCIA}
      zoom={foco?.zoom ?? 13}
      className="mapa"
    >
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} attribution="© OpenStreetMap" />
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
