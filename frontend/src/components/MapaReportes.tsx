import { useEffect } from 'react';
import { Circle, MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import iconoUrl from 'leaflet/dist/images/marker-icon.png';
import iconoRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import sombraUrl from 'leaflet/dist/images/marker-shadow.png';
import { PopupReporte } from './PopupReporte';
import type { Reporte } from '../types';

// Con un empaquetador, Leaflet no encuentra solo las imagenes del marcador
L.Icon.Default.mergeOptions({ iconUrl: iconoUrl, iconRetinaUrl: iconoRetinaUrl, shadowUrl: sombraUrl });

const COLORES = { 0: '#9e9e9e', 1: '#ffd54f' } as const;
export const CENTRO_VALENCIA: [number, number] = [10.165, -68.021];

export interface Foco { lat: number; lon: number; zoom: number; marcador?: string }

function Enfocar({ foco }: { foco: Foco | null }) {
  const map = useMap();
  useEffect(() => {
    if (foco) map.setView([foco.lat, foco.lon], foco.zoom);
  }, [foco, map]);
  return null;
}

export function MapaReportes({ reportes, foco }: { reportes: Reporte[]; foco: Foco | null }) {
  return (
    <MapContainer
      center={foco ? [foco.lat, foco.lon] : CENTRO_VALENCIA}
      zoom={foco?.zoom ?? 13}
      className="mapa"
    >
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} attribution="© OpenStreetMap" />
      <Enfocar foco={foco} />
      {reportes.map(r => (
        <Circle
          key={r.id}
          center={[r.lat, r.lon]}
          radius={400}
          pathOptions={{ color: COLORES[r.tiene_luz], fillColor: COLORES[r.tiene_luz], fillOpacity: 0.4, weight: 1.5 }}
        >
          <Popup><PopupReporte r={r} /></Popup>
        </Circle>
      ))}
      {foco?.marcador && (
        <Marker position={[foco.lat, foco.lon]}>
          <Popup>{foco.marcador}</Popup>
        </Marker>
      )}
    </MapContainer>
  );
}
