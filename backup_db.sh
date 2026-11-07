#!/bin/bash
# Ecosistema de Respaldo Inmutable - Valencia Luz Core
RESPALDO_DIR="/root/ValenciaLuz/backups"
FECHA=$(date +"%Y-%m-%d_%H%M%S")
DB_ORIGEN="/root/ValenciaLuz/valencia_luz_persistente.db"

# Crear la carpeta de resguardo si no existe en el disco duro
mkdir -p "$RESPALDO_DIR"

# Ejecutar el clonado en frío del archivo relacional
cp "$DB_ORIGEN" "$RESPALDO_DIR/valencia_luz_backup_$FECHA.db"

# Mantener la casa limpia: eliminar respaldos viejos de más de 7 días
find "$RESPALDO_DIR" -type f -name "*.db" -mtime +7 -delete

echo "🛰️ Base de datos relacional clonada y respaldada con éxito el $FECHA"
