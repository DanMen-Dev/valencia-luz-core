// Gateway del mapa de Radar: sirve la pagina del mapa y hace de puente hacia el backend de Python.
const express = require('express');
const axios = require('axios');
const path = require('path');

const PORT = Number(process.env.PORT || 5000);
const BACKEND = process.env.VL_BACKEND_URL || 'http://motor-python:8000';
const WHATSAPP = String(process.env.VL_WHATSAPP || '').replace(/\D/g, '');
const REPORTES_WEB_POR_HORA = Number(process.env.VL_REPORTES_WEB_POR_HORA || 10);

const app = express();
app.disable('x-powered-by');
// nginx esta delante (el puerto solo escucha en 127.0.0.1): la IP real del visitante es la que agrega nginx
app.set('trust proxy', 1);
app.use(express.json({ limit: '2kb' }));

app.use((req, res, next) => {
  res.set({
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'X-Frame-Options': 'DENY',
    'Content-Security-Policy': [
      "default-src 'self'",
      "img-src 'self' data: https://*.tile.openstreetmap.org",
      "style-src 'self' 'unsafe-inline'",
      "script-src 'self'",
      "connect-src 'self'",
      "frame-ancestors 'none'",
    ].join('; '),
  });
  next();
});

app.use('/leaflet', express.static(path.join(__dirname, 'node_modules', 'leaflet', 'dist'), { maxAge: '7d' }));
// /static lo toma el nginx de Brecha-Cero (archivos de Django), por eso los del mapa van en /recursos
app.use('/recursos', express.static(path.join(__dirname, 'public'), { maxAge: '5m' }));

app.get('/', (req, res) => res.redirect('/mapa'));
app.get('/mapa', (req, res) => res.sendFile(path.join(__dirname, 'public', 'mapa.html')));
app.get('/salud', (req, res) => res.json({ status: 'online', modulo: 'Gateway del mapa de Radar' }));

app.get('/api/v1/config', (req, res) => res.json({ whatsapp: WHATSAPP }));

app.get('/api/v1/mapa/circuitos', async (req, res) => {
  try {
    const r = await axios.get(`${BACKEND}/api/mapa/activos`, { timeout: 8000 });
    res.set('Cache-Control', 'no-store').json(Array.isArray(r.data) ? r.data : []);
  } catch (error) {
    console.error('[GATEWAY] No se pudo leer el mapa del backend:', error.message);
    res.status(502).json({ error: 'No se pudo conectar con el backend.' });
  }
});

// Tope de reportes web por IP (en memoria; se reinicia con el contenedor, suficiente para frenar abuso simple)
const reportesPorIp = new Map();
function permitido(ip) {
  const ahora = Date.now();
  const recientes = (reportesPorIp.get(ip) || []).filter(t => ahora - t < 3600e3);
  if (recientes.length >= REPORTES_WEB_POR_HORA) { reportesPorIp.set(ip, recientes); return false; }
  recientes.push(ahora);
  reportesPorIp.set(ip, recientes);
  if (reportesPorIp.size > 5000) reportesPorIp.clear();
  return true;
}

app.post('/api/v1/reportar', async (req, res) => {
  const latitud = Number(req.body?.latitud);
  const longitud = Number(req.body?.longitud);
  const tiene_luz = Number(req.body?.tiene_luz);
  if (!Number.isFinite(latitud) || !Number.isFinite(longitud) || ![0, 1].includes(tiene_luz)) {
    return res.status(400).json({ error: 'Datos del reporte incompletos.' });
  }
  if (!permitido(req.ip)) {
    return res.status(429).json({ error: 'Demasiados reportes desde esta conexión. Intenta más tarde.' });
  }
  try {
    const r = await axios.post(`${BACKEND}/api/reportar`, { latitud, longitud, tiene_luz },
      { timeout: 8000, validateStatus: () => true });
    if (r.status === 422) return res.status(422).json({ error: 'Esa ubicación está fuera de Venezuela.' });
    if (r.status >= 400) return res.status(r.status).json({ error: 'El backend rechazó el reporte.' });
    res.json(r.data);
  } catch (error) {
    console.error('[GATEWAY] No se pudo enviar el reporte al backend:', error.message);
    res.status(502).json({ error: 'No se pudo conectar con el backend.' });
  }
});

app.use((req, res) => res.status(404).json({ error: 'Ruta no encontrada' }));

app.listen(PORT, () => console.log(`[GATEWAY] Mapa de Radar en el puerto ${PORT}`));
