const express = require('express');
const axios = require('axios');
const path = require('path');
const app = express();
const PORT = 5000;

// Version GITHUB

app.use(express.json());

// Servimos Leaflet localmente para evitar bloqueos del navegador
app.use('/leaflet', express.static(path.join(__dirname, 'node_modules', 'leaflet', 'dist')));

// Red interna de Docker hacia Python FastAPI (Puerto 8000)
const PYTHON_API_URL = 'http://localhost:8000/api/circuitos/datos_vivos';
const PYTHON_REPORTAR_URL = 'http://localhost:8000/api/reportar';

app.get('/', (req, res) => {
    res.json({ status: "online", modulo: "Gateway Orquestador Node.js - Modo Autónomo" });
});

app.get('/api/v1/mapa/circuitos', async (req, res) => {
    try {
        const respuestaPython = await axios.get(PYTHON_API_URL);
        res.json(respuestaPython.data);
    } catch (error) {
        console.error("[NODE ERROR] Falla al pedir JSON a Python:", error.message);
        res.json([]);
    }
});

app.post('/api/v1/reportar', async (req, res) => {
    try {
        const respuestaPython = await axios.post(PYTHON_REPORTAR_URL, {
            latitud: parseFloat(req.body.latitud),
            longitud: parseFloat(req.body.longitud),
            tiene_luz: parseInt(req.body.tiene_luz)
        });
        res.json(respuestaPython.data);
    } catch (error) {
        console.error("[NODE ERROR] Falló la comunicación con Python:", error.message);
        res.status(500).json({ status: "error", mensaje: "No se pudo conectar con el motor." });
    }
});

app.get('/mapa', (req, res) => {
    res.send(`
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Valencia Luz - Monitoreo Dinámico</title>
            <link rel="stylesheet" href="/leaflet/leaflet.css" />
            <script src="/leaflet/leaflet.js"></script>
            <style>
                html, body { margin: 0; padding: 0; width: 100%; height: 100%; background-color: #121212; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; overflow: hidden; }
                #app-container { display: flex; width: 100%; height: 100%; }
                #panel-control { width: 320px; background-color: #1a1a1a; border-right: 3px solid #ff9800; padding: 20px; box-sizing: border-box; display: flex; flex-direction: column; justify-content: space-between; z-index: 1000; }
                #mapa { flex-grow: 1; height: 100%; background: #1a1a1a; }
                h1 { margin: 0; font-size: 22px; color: #ff9800; font-weight: 800; letter-spacing: 0.5px; }
                p.sub { margin: 5px 0 20px 0; font-size: 11px; color: #aaaaaa; line-height: 1.4; }
                .btn-accion { width: 100%; padding: 12px; border: none; border-radius: 6px; font-weight: bold; font-size: 13px; cursor: pointer; margin-bottom: 12px; transition: all 0.2s ease; display: flex; align-items: center; justify-content: center; gap: 8px; }
                .btn-gps { background-color: #ff9800; color: #121212; }
                .btn-gps:hover { background-color: #e68a00; transform: translateY(-1px); }
                .btn-wa { background-color: #25d366; color: #ffffff; text-decoration: none; }
                .btn-wa:hover { background-color: #20ba5a; transform: translateY(-1px); }
                .leyenda-box { background-color: #222; padding: 12px; border-radius: 6px; font-size: 11px; color: #ccc; }
                .leyenda-item { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
                .legend-color { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
                .leaflet-popup-content-wrapper { background: #1a1a1a !important; color: #fff !important; border: 1px solid #ff9800; border-radius: 8px; }
                .leaflet-popup-tip { background: #ff9800 !important; }
                .badge-status { padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 10px; display: inline-block; margin-top: 5px; }
                @media (max-width: 768px) {
                    #app-container { flex-direction: column; }
                    #panel-control { width: 100%; height: auto; border-right: none; border-bottom: 3px solid #ff9800; padding: 15px; }
                    #mapa { height: calc(100vh - 200px); }
                }
            </style>
        </head>
        <body>
            <div id="app-container">
                <div id="panel-control">
                    <div>
                        <h1>VALENCIA LUZ ⚡</h1>
                        <p class="sub">Sistema comunitario y probabilístico de monitoreo eléctrico. Reporta para ver los datos vivos.</p>
                        <button class="btn-accion btn-gps" onclick="reportarConGpsWeb()">📍 Reportar Apagón en mi Ubicación</button>
                        <a href="https://wa.me" target="_blank" class="btn-accion btn-wa">💬 Reportar Vía WhatsApp (IA)</a>
                    </div>
                    <div class="leyenda-box">
                        <strong style="color: #ff9800; display:block; margin-bottom:8px;">Código de Colores:</strong>
                        <div class="leyenda-item"><span class="legend-color" style="background:#9e9e9e;"></span> Sin Electricidad (Reportado)</div>
                        <div class="leyenda-item"><span class="legend-color" style="background:#f44336;"></span> Riesgo Crítico (Corte Inminente)</div>
                        <div class="leyenda-item"><span class="legend-color" style="background:#ff9800;"></span> Riesgo Alto (Vigilancia)</div>
                        <div class="leyenda-item"><span class="legend-color" style="background:#ffeb3b;"></span> Servicio Estable (Con Luz)</div>
                    </div>
                </div>
                <div id="mapa"></div>
            </div>

            <script>
                console.log("--> Levantando mapa dinámico de producción...");
                const map = L.map('mapa').setView([10.162, -68.007], 13);

                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    maxZoom: 19,
                    attribution: '© OpenStreetMap'
                }).addTo(map);

                function cargarCircuitosDinamicos() {
                    fetch('/api/v1/mapa/circuitos')
                        .then(res => res.json())
                        .then(circuitos => {
                            circuitos.forEach(c => {
                                let colorHex = "#ffeb3b";
                                let textoLegible = "CON ELECTRICIDAD";
                                let colorBadge = "#198754";

                                if (c.capa_color === "gris") {
                                    colorHex = "#9e9e9e";
                                    textoLegible = "SIN ELECTRICIDAD ❌";
                                    colorBadge = "#dc3545";
                                } else if (c.capa_color === "rojo") {
                                    colorHex = "#f44336";
                                    textoLegible = "RIESGO CRÍTICO ⚠️";
                                    colorBadge = "#ffc107";
                                } else if (c.capa_color === "naranja") {
                                    colorHex = "#ff9800";
                                    textoLegible = "RIESGO ALTO ⌛";
                                    colorBadge = "#fd7e14";
                                }

                                const circle = L.circle([c.lat, c.lon], {
                                    color: colorHex,
                                    fillColor: colorHex,
                                    fillOpacity: 0.4,
                                    radius: 500,
                                    weight: 1.5
                                }).addTo(map);

                                circle.bindPopup(\`
                                    <div style="font-family: sans-serif; min-width: 160px;">
                                        <strong style="color: #ff9800; font-size: 13px;">ID: \${c.id}</strong><br>
                                        <span class="badge-status" style="background-color: \${colorBadge}; color: #fff;">\${textoLegible}</span><br><br>
                                        <b>Estabilidad actual:</b> \${c.horas_estables} hrs con luz<br>
                                        <b>Riesgo de corte:</b> \${c.probabilidad_corte}%<br>
                                        <small style="color: #888; display:block; margin-top:5px;">Actualizado: \${c.actualizado}</small>
                                    </div>
                                \`);
                            });
                        }).catch(err => console.error(err));
                }

                function reportarConGpsWeb() {
                    if (!navigator.geolocation) {
                        alert("Tu navegador no soporta geolocalización directa.");
                        return;
                    }
                    navigator.geolocation.getCurrentPosition(position => {
                        const { latitude, longitude } = position.coords;
                        fetch('/api/v1/reportar', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ latitud: latitude, longitud: longitude, tiene_luz: 0 })
                        })
                        .then(res => res.json())
                        .then(data => {
                            alert("⚡ Reporte registrado con éxito. Circuito asignado: " + data.circuito_asignado);
                            location.reload();
                        })
                        .catch(err => alert("Error al reportar: " + err.message));
                    }, () => {
                        alert("No pudimos acceder a tu GPS. Por favor activa los permisos de ubicación.");
                    });
                }

                cargarCircuitosDinamicos();
            </script>
        </body>
        </html>
    `);
});

app.use((req, res) => {
    res.status(404).json({ error: "Ruta no encontrada" });
});

app.listen(PORT, () => {
    console.log(`[NODE] Orquestador UI/UX en puerto ${PORT}`);
});

