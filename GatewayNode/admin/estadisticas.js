// Panel privado de Radar: pide la clave, la guarda solo en esta pestana y la manda en una cabecera.
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const fmt = n => Number(n || 0).toLocaleString('es-VE');

  function celda(texto, clase) {
    const td = document.createElement('td');
    td.textContent = texto;
    if (clase) td.className = clase;
    return td;
  }

  function tarjeta(titulo, numero, detalle) {
    const div = document.createElement('div');
    div.className = 'tarjeta';
    for (const [clase, texto] of [['titulo', titulo], ['numero', numero], ['detalle', detalle]]) {
      const el = document.createElement('div');
      el.className = clase;
      el.textContent = texto;
      div.append(el);
    }
    return div;
  }

  function pintar(e) {
    $('generado').textContent = `Actualizado: ${e.generado} (hora de Venezuela)`;
    $('tarjetas').replaceChildren(
      tarjeta('Vecinos hoy', fmt(e.hoy.total), `${fmt(e.hoy.mapa)} en el mapa · ${fmt(e.hoy.bot)} en el bot`),
      tarjeta('Últimos 7 días', fmt(e.semana.total), `${fmt(e.semana.mapa)} mapa · ${fmt(e.semana.bot)} bot`),
      tarjeta('Últimos 30 días', fmt(e.mes.total), `${fmt(e.mes.mapa)} mapa · ${fmt(e.mes.bot)} bot`),
      tarjeta('Vuelven', fmt(e.vuelven_30_dias), 'usaron Radar 2 días o más (30 días)'),
    );

    const maximo = Math.max(1, ...e.por_dia.map(d => d.mapa + d.bot));
    $('barras').replaceChildren(...e.por_dia.map(d => {
      const barra = document.createElement('div');
      barra.className = 'barra';
      barra.title = `${d.dia}: ${d.mapa} mapa, ${d.bot} bot`;
      for (const [clase, n] of [['m', d.mapa], ['b', d.bot]]) {
        const parte = document.createElement('div');
        parte.className = clase;
        parte.style.height = `${(n / maximo) * 96}px`;
        barra.append(parte);
      }
      return barra;
    }));

    const filas = [
      ['Vecinos en el mapa', 'mapa'], ['Vecinos en el bot', 'bot'],
      ['Vecinos que reportaron', 'vecinos_que_reportaron'], ['Reportes', 'reportes'],
    ];
    $('detalle').replaceChildren(...filas.map(([nombre, campo]) => {
      const tr = document.createElement('tr');
      tr.append(celda(nombre), celda(fmt(e.hoy[campo]), 'n'), celda(fmt(e.semana[campo]), 'n'), celda(fmt(e.mes[campo]), 'n'));
      return tr;
    }));

    $('sectores').replaceChildren(...(e.sectores_mas_activos.length ? e.sectores_mas_activos : [{ sector: 'Sin reportes todavía', reportes: '' }])
      .map(s => {
        const tr = document.createElement('tr');
        tr.append(celda(String(s.sector).toUpperCase()), celda(s.reportes === '' ? '' : fmt(s.reportes), 'n'));
        return tr;
      }));
  }

  async function cargar(clave) {
    $('error').textContent = '';
    try {
      const r = await fetch('/api/v1/estadisticas', { headers: { 'X-Radar-Clave': clave }, cache: 'no-store' });
      if (r.status === 403) throw new Error('Clave incorrecta.');
      if (r.status === 404) throw new Error('El panel está desactivado (falta VL_CLAVE_ESTADISTICAS en el .env).');
      if (!r.ok) throw new Error('No se pudieron cargar las estadísticas.');
      pintar(await r.json());
      try { sessionStorage.setItem('radar.clave', clave); } catch { /* sin almacenamiento: se pide cada vez */ }
      $('acceso').hidden = true;
      $('panel').hidden = false;
    } catch (err) {
      $('error').textContent = err.message;
      try { sessionStorage.removeItem('radar.clave'); } catch { /* nada */ }
    }
  }

  $('acceso').addEventListener('submit', ev => { ev.preventDefault(); cargar($('clave').value); });
  let guardada = null;
  try { guardada = sessionStorage.getItem('radar.clave'); } catch { /* nada */ }
  if (guardada) cargar(guardada);
})();
