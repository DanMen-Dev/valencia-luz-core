/* Service worker de Radar: la app abre sin conexion y muestra el ultimo mapa guardado.
 *  - /mapa y los archivos de la app: guardados al instalar y al usarse (los de assets/ llevan hash: no cambian).
 *  - Reportes: siempre de la red; si no hay conexion, la ultima respuesta guardada, marcada con X-Radar-Guardado.
 *  - Calles (OpenFreeMap): se guardan las que ya se vieron, con tope, para que el fondo cargue con mala senal.
 * Al publicar cambios en este archivo, subir VERSION para que se borren los guardados viejos. */
const VERSION = 'radar-v1';
const APP = `${VERSION}-app`;
const DATOS = `${VERSION}-datos`;
const CALLES = `${VERSION}-calles`;
const MAX_CALLES = 600;

self.addEventListener('install', evento => {
  evento.waitUntil(caches.open(APP).then(c => c.addAll(['/mapa'])).then(() => self.skipWaiting()));
});

self.addEventListener('activate', evento => {
  evento.waitUntil((async () => {
    for (const nombre of await caches.keys()) if (!nombre.startsWith(VERSION)) await caches.delete(nombre);
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', evento => {
  const pedido = evento.request;
  if (pedido.method !== 'GET') return;            // los reportes (POST) van siempre directo a la red
  const url = new URL(pedido.url);

  if (url.origin === self.location.origin) {
    if (pedido.mode === 'navigate' && (url.pathname === '/mapa' || url.pathname === '/')) {
      evento.respondWith(redPrimero(pedido, APP, '/mapa'));
    } else if (url.pathname.startsWith('/recursos/')) {
      evento.respondWith(guardadoPrimero(pedido, APP));
    } else if (url.pathname === '/api/v1/mapa/circuitos') {
      evento.respondWith(reportesConRespaldo(pedido));
    } else if (url.pathname === '/api/v1/config') {
      evento.respondWith(redPrimero(pedido, DATOS));
    }
    return;
  }
  if (url.hostname === 'tiles.openfreemap.org') evento.respondWith(calles(pedido));
});

async function redPrimero(pedido, nombre, clave) {
  const cache = await caches.open(nombre);
  try {
    const respuesta = await fetch(pedido);
    if (respuesta.ok) await cache.put(clave || pedido, respuesta.clone());
    return respuesta;
  } catch (e) {
    const guardada = await cache.match(clave || pedido, { ignoreSearch: true });
    if (guardada) return guardada;
    throw e;
  }
}

async function guardadoPrimero(pedido, nombre) {
  const cache = await caches.open(nombre);
  const guardada = await cache.match(pedido);
  if (guardada) return guardada;
  const respuesta = await fetch(pedido);
  if (respuesta.ok) await cache.put(pedido, respuesta.clone());
  return respuesta;
}

async function reportesConRespaldo(pedido) {
  const cache = await caches.open(DATOS);
  try {
    const respuesta = await fetch(pedido);
    if (respuesta.ok) {
      const cuerpo = await respuesta.clone().text();
      const encabezados = new Headers(respuesta.headers);
      encabezados.set('X-Radar-Guardado', new Date().toISOString());
      await cache.put('/api/v1/mapa/circuitos', new Response(cuerpo, { status: 200, headers: encabezados }));
    }
    return respuesta;
  } catch (e) {
    const guardada = await cache.match('/api/v1/mapa/circuitos');
    if (guardada) return guardada;
    throw e;
  }
}

async function calles(pedido) {
  const cache = await caches.open(CALLES);
  const guardada = await cache.match(pedido);
  const deLaRed = fetch(pedido).then(async respuesta => {
    if (respuesta.ok) {
      await cache.put(pedido, respuesta.clone());
      const claves = await cache.keys();
      for (const vieja of claves.slice(0, Math.max(0, claves.length - MAX_CALLES))) await cache.delete(vieja);
    }
    return respuesta;
  });
  if (guardada) { deLaRed.catch(() => {}); return guardada; }
  return deLaRed;
}
