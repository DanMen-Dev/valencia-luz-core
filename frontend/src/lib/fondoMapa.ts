// Fondo del mapa. Principal: OpenFreeMap (mapas vectoriales, gratis, sin clave ni limite de vistas), dibujado
// con MapLibre. Respaldo: las imagenes de OpenStreetMap, si el telefono no tiene WebGL o OpenFreeMap falla.
export const ESTILO_OPENFREEMAP = 'https://tiles.openfreemap.org/styles/positron';
export const ATRIBUCION_OPENFREEMAP =
  '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> © <a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> Datos de <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>';
export const TILES_OSM = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';

export function tieneWebGL(): boolean {
  try {
    const lienzo = document.createElement('canvas');
    return Boolean(lienzo.getContext('webgl2') || lienzo.getContext('webgl'));
  } catch {
    return false;
  }
}
