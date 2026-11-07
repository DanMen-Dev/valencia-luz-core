// Contador de vecinos sin datos personales: el navegador genera un numero al azar la primera vez y avisa
// una vez al dia "estoy aqui". No se usan IP, cookies ni nada que identifique a la persona.
const CLAVE_ID = 'radar.visitante';
const CLAVE_DIA = 'radar.visita';
const VALIDO = /^[A-Za-z0-9-]{8,64}$/;

function nuevoId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
}

export function fechaLocal(d = new Date()): string {
  const dos = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}`;
}

export function idVisitante(): string {
  try {
    let id = localStorage.getItem(CLAVE_ID);
    if (!id || !VALIDO.test(id)) {
      id = nuevoId();
      localStorage.setItem(CLAVE_ID, id);
    }
    return id;
  } catch {
    return nuevoId();   // sin almacenamiento: cuenta como visita nueva, no pasa nada
  }
}

// Devuelve true si aviso hoy; false si ya lo habia hecho o no hubo conexion
export async function avisarVisita(hoy = fechaLocal()): Promise<boolean> {
  let ultimo: string | null = null;
  try { ultimo = localStorage.getItem(CLAVE_DIA); } catch { /* sin almacenamiento */ }
  if (ultimo === hoy) return false;
  try {
    await fetch('/api/v1/visita', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ visitante: idVisitante() }), keepalive: true,
    });
    try { localStorage.setItem(CLAVE_DIA, hoy); } catch { /* sin almacenamiento */ }
    return true;
  } catch {
    return false;
  }
}
