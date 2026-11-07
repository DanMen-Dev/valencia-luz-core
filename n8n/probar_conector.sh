#!/usr/bin/env bash
# Prueba el flujo Conector de n8n sin WhatsApp: le manda eventos falsos de Chatwoot y muestra la respuesta.
# Uso (en el VPS): bash n8n/probar_conector.sh
# Al final borra los reportes del telefono de prueba.
set -u
URL="${URL:-http://127.0.0.1:5678/webhook/reporte-comunitario-luz}"
TEL="580000000001"

enviar() {
  local titulo="$1" evento="$2"
  echo "== $titulo"
  python3 -c 'import json,sys; print(json.dumps({"data": sys.argv[1]}))' "$evento" |
    curl -s -m 60 -X POST "$URL" -H 'Content-Type: application/json' -d @- |
    python3 -c 'import json,sys; t=sys.stdin.read(); 
try: print(json.loads(t).get("mensaje_confirmacion","(vacio)"))
except Exception: print("RESPUESTA NO JSON:", t[:300])'
  echo
}
base='"event":"message_created","message_type":"incoming","conversation":{"id":0,"meta":{"sender":{"phone_number":"+'$TEL'"}}}'

enviar "1. Saludo"            '{'"$base"',"content":"Hola"}'
enviar "2. Ubicacion"         '{'"$base"',"content":"","attachments":[{"file_type":"location","coordinates_lat":10.2155,"coordinates_long":-68.0059}]}'
# Sector de prueba con nombre unico: al final se borra sin tocar sectores reales
enviar "3. Sector (volvio)"   '{'"$base"',"content":"Si, Radarprueba"}'
enviar "4. Consulta (modelo)" '{'"$base"',"content":"buenas, como esta la luz en radarprueba?"}'
enviar "5. Sin sector"        '{'"$base"',"content":"a que hora vuelve la luz?"}'
enviar "6. Saliente (nada)"   '{"event":"message_created","message_type":"outgoing","content":"x"}'
enviar "7. Reporte escrito"   '{'"$base"',"content":"mira se fue la luz en Radarprueva"}'
enviar "8. Sector desconocido" '{'"$base"',"content":"se fue la luz en Sectorinventadox"}'

docker exec luz_backend_python python -c "
import sqlite3; c=sqlite3.connect('/app/datos/valencia_luz_persistente.db')
n=c.execute(\"delete from circuitos where telefono='$TEL'\").rowcount
c.execute(\"delete from conversaciones where telefono='$TEL'\")
c.execute(\"delete from alias where nombre='radarprueba'\")
c.execute(\"delete from celdas where id not in (select celda from alias)\"); c.commit(); print('reportes de prueba borrados:', n)"
