import { useEffect } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import { Map as MapaGL } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { ATRIBUCION_OPENFREEMAP, ESTILO_OPENFREEMAP } from '../lib/fondoMapa';

// Fondo vectorial: un mapa de MapLibre debajo de las capas de Leaflet, que lo sigue en cada movimiento.
// Leaflet sigue manejando los gestos, los circulos y los popups; MapLibre solo dibuja las calles.
// MapLibre usa cuadros de 512 px y Leaflet de 256: el mismo nivel de detalle es zoom - 1.
export function FondoVectorial({ onFalla }: { onFalla: () => void }) {
  const map = useMap();

  useEffect(() => {
    const lienzo = L.DomUtil.create('div', 'fondo-vectorial', map.getContainer());
    const centro = () => { const c = map.getCenter(); return [c.lng, c.lat] as [number, number]; };
    let gl: MapaGL;
    try {
      gl = new MapaGL({
        container: lienzo, style: ESTILO_OPENFREEMAP, center: centro(), zoom: map.getZoom() - 1,
        interactive: false, attributionControl: false,
      });
    } catch {
      lienzo.remove();
      onFalla();
      return;
    }

    const seguir = () => gl.jumpTo({ center: centro(), zoom: map.getZoom() - 1 });
    // Durante la animacion de zoom de Leaflet (250 ms), MapLibre anima igual para no despegarse
    const animarZoom = (e: L.LeafletEvent) => {
      const { center, zoom } = e as L.ZoomAnimEvent;
      gl.easeTo({ center: [center.lng, center.lat], zoom: zoom - 1, duration: 250, easing: t => 1 - (1 - t) ** 3 });
    };
    const redimensionar = () => { gl.resize(); seguir(); };
    map.on('move zoom', seguir);
    map.on('zoomanim', animarZoom);
    map.on('resize', redimensionar);
    map.attributionControl?.addAttribution(ATRIBUCION_OPENFREEMAP);

    // Un cuadro suelto que falla no importa; si falla el estilo o fallan muchos seguidos, al respaldo
    let fallas = 0;
    gl.on('error', e => {
      fallas += 1;
      if (/style/i.test(e.error?.message ?? '') || fallas >= 8) onFalla();
    });

    return () => {
      map.off('move zoom', seguir);
      map.off('zoomanim', animarZoom);
      map.off('resize', redimensionar);
      map.attributionControl?.removeAttribution(ATRIBUCION_OPENFREEMAP);
      gl.remove();
      lienzo.remove();
    };
  }, [map, onFalla]);

  return null;
}
