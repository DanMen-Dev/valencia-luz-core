#!/bin/bash
# Respaldo diario de la base de Valencia Luz (cron 0 0 * * *). Guarda 7 dias.
set -u
RESPALDO_DIR="/root/ValenciaLuz/backups"
FECHA=$(date +"%Y-%m-%d_%H%M%S")
DB_ORIGEN="/root/ValenciaLuz/datos/valencia_luz_persistente.db"

mkdir -p "$RESPALDO_DIR"

if [ ! -s "$DB_ORIGEN" ]; then
    echo "ERROR $FECHA: no existe la base en $DB_ORIGEN; no se respaldo nada"
    exit 1
fi

# Copia consistente con la API de respaldo de SQLite (dentro del contenedor, que tiene Python)
if docker exec luz_backend_python python -c "import sqlite3; s=sqlite3.connect('/app/datos/valencia_luz_persistente.db'); d=sqlite3.connect('/app/datos/respaldo_tmp.db'); s.backup(d); d.close(); s.close()"; then
    mv "/root/ValenciaLuz/datos/respaldo_tmp.db" "$RESPALDO_DIR/valencia_luz_backup_$FECHA.db"
else
    cp "$DB_ORIGEN" "$RESPALDO_DIR/valencia_luz_backup_$FECHA.db"   # respaldo simple si el contenedor no responde
fi

find "$RESPALDO_DIR" -type f -name "*.db" -mtime +7 -delete
echo "OK $FECHA: respaldo en $RESPALDO_DIR/valencia_luz_backup_$FECHA.db ($(du -h "$RESPALDO_DIR/valencia_luz_backup_$FECHA.db" | cut -f1))"
