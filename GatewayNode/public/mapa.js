// Mapa de Valencia Luz: dibuja los reportes recientes y permite reportar desde el navegador.
(function () {
  'use strict';
  const CENTRO = [10.165, -68.021];
  const REFRESCO_MS = 60 * 1000;
  const VENEZUELA = { latMin: 0.5, latMax: 12.6, lonMin: -73.5, lonMax: -59.5 };

  const map = L.map('mapa', { zoomControl: true });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '© OpenStreetMap',
  }).addTo(map);
  const capa = L.layerGroup().addTo(map);

  const $aviso = document.getElementById('aviso');
  const $estado = document.getElementById('estado');

  function enVenezuela(lat, lon) {
    return Number.isFinite(lat) && Number.isFinite(lon) &&
      lat >= VENEZUELA.latMin && lat <= VENEZUELA.latMax && lon >= VENEZUELA.lonMin && lon <= VENEZUELA.lonMax;
  }

  function avisar(texto, tipo) {
    $aviso.textContent = texto;
    $aviso.className = 'aviso' + (tipo ? ' ' + tipo : '');
  }

  // El popup se arma con nodos de texto: el nombre del sector lo escribe un vecino y nunca se interpreta como HTML
  function el(tag, clase, texto) {
    const n = document.createElement(tag);
    if (clase) n.className = clase;
    if (texto !== undefined) n.textContent = texto;
    return n;
  }
  function popup(c) {
    const sinLuz = c.tiene_luz === 0;
    const caja = el('div', 'pop');
    caja.append(el('strong', 'zona', '📍 ' + String(c.nombre_zona || 'Sector sin nombre').toUpperCase()));
    caja.append(el('span', 'badge ' + (sinLuz ? 'sin' : 'con'), sinLuz ? 'SIN LUZ' : 'VOLVIÓ LA LUZ'));
    caja.append(el('span', 'linea', (sinLuz ? '⏳ Reportado a las ' : '💡 Reportado a las ') + (c.hora_inicio || '—')));
    if (sinLuz) caja.append(el('span', 'linea', '🚀 Retorno estimado: ' + (c.hora_estimada || 'sin datos')));
    caja.append(el('small', '', 'Hora de Venezuela · ' + (c.actualizado || '')));
    return caja;
  }

  async function cargar() {
    try {
      const r = await fetch('/api/v1/mapa/circuitos', { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const datos = await r.json();
      capa.clearLayers();
      let sin = 0, con = 0;
      for (const c of datos) {
        if (!enVenezuela(Number(c.lat), Number(c.lon))) continue;
        const color = c.tiene_luz === 0 ? '#9e9e9e' : '#ffd54f';
        c.tiene_luz === 0 ? sin++ : con++;
        L.circle([c.lat, c.lon], { color, fillColor: color, fillOpacity: 0.4, radius: 400, weight: 1.5 })
          .bindPopup(popup(c)).addTo(capa);
      }
      const hora = new Date().toLocaleTimeString('es-VE', { hour: 'numeric', minute: '2-digit' });
      $estado.textContent = (sin + con === 0)
        ? `Sin reportes en las últimas 12 horas · actualizado ${hora}`
        : `${sin} sin luz · ${con} con luz (últimas 12 h) · actualizado ${hora}`;
    } catch (e) {
      $estado.textContent = 'No se pudieron cargar los reportes. Reintentando…';
    }
  }

  function reportar(tieneLuz, boton) {
    if (!navigator.geolocation) return avisar('Tu navegador no permite compartir la ubicación.', 'error');
    const botones = document.querySelectorAll('.btn[data-luz]');
    botones.forEach(b => { b.disabled = true; });
    avisar('Buscando tu ubicación…');
    const listo = () => botones.forEach(b => { b.disabled = false; });
    navigator.geolocation.getCurrentPosition(async pos => {
      const { latitude, longitude } = pos.coords;
      try {
        const r = await fetch('/api/v1/reportar', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ latitud: latitude, longitud: longitude, tiene_luz: tieneLuz }),
        });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(d.error || 'No se pudo registrar el reporte.');
        const zona = d.circuito_asignado && d.circuito_asignado !== 'SIN ZONA' ? ' en ' + d.circuito_asignado : '';
        avisar(tieneLuz ? `Gracias: registramos que volvió la luz${zona}.` : `Gracias: tu reporte de corte${zona} ya está en el mapa.`, 'ok');
        map.setView([latitude, longitude], 15);
        await cargar();
      } catch (e) {
        avisar(e.message, 'error');
      } finally { listo(); }
    }, () => {
      avisar('No pudimos leer tu ubicación. Activa el permiso de ubicación del navegador e intenta de nuevo.', 'error');
      listo();
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
  }

  document.querySelectorAll('.btn[data-luz]').forEach(b =>
    b.addEventListener('click', () => reportar(Number(b.dataset.luz), b)));

  // Enlace de WhatsApp: solo aparece si el servidor tiene un numero configurado (VL_WHATSAPP)
  fetch('/api/v1/config').then(r => r.json()).then(cfg => {
    if (!cfg.whatsapp) return;
    const wa = document.getElementById('btn-wa');
    wa.href = 'https://wa.me/' + cfg.whatsapp + '?text=' + encodeURIComponent('Hola');
    wa.hidden = false;
  }).catch(() => {});

  // ?lat=..&lon=.. (enlace desde WhatsApp): centra el mapa en esa ubicacion
  const q = new URLSearchParams(location.search);
  const lat = parseFloat(q.get('lat')), lon = parseFloat(q.get('lon'));
  if (enVenezuela(lat, lon)) {
    map.setView([lat, lon], 16);
    L.marker([lat, lon]).addTo(map).bindPopup('Tu reporte está aquí').openPopup();
  } else {
    map.setView(CENTRO, 13);
  }

  cargar();
  setInterval(() => { if (!document.hidden) cargar(); }, REFRESCO_MS);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) cargar(); });
})();
