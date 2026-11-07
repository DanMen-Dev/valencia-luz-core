// Recuerda en este navegador a que grupos ya les dio "Yo tambien", para no ofrecer el boton otra vez.
// Es solo una comodidad: si el almacenamiento falla o esta bloqueado, todo sigue funcionando.
const CLAVE = 'radar.confirmados';
const VIGENCIA_MS = 12 * 3600 * 1000;

function leer(): Record<string, number> {
  try {
    const datos = JSON.parse(localStorage.getItem(CLAVE) ?? '{}') as Record<string, number>;
    const ahora = Date.now();
    return Object.fromEntries(Object.entries(datos).filter(([, t]) => typeof t === 'number' && ahora - t < VIGENCIA_MS));
  } catch {
    return {};
  }
}

export function yaConfirmado(clave: string): boolean {
  return clave in leer();
}

export function marcarConfirmado(clave: string): void {
  try {
    localStorage.setItem(CLAVE, JSON.stringify({ ...leer(), [clave]: Date.now() }));
  } catch {
    // sin almacenamiento: no pasa nada
  }
}
