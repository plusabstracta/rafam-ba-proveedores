#!/usr/bin/env bash
# install_crons.sh — instala/actualiza los cron jobs de rafam-ba-proveedores.
# Idempotente: elimina entradas anteriores del proyecto y reinstala desde cron.conf.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$PROJECT_DIR/scripts/run_entity.sh"
PY="$PROJECT_DIR/.venv/bin/python"
INTEGRITY="$PROJECT_DIR/scripts/check_integrity.py"
LOG_DIR="$PROJECT_DIR/logs"
INTEGRITY_LOG="$LOG_DIR/check_integrity.log"
mkdir -p "$LOG_DIR" "$PROJECT_DIR/state/locks"

# Verificar si cron.conf existe
if [[ ! -f "$PROJECT_DIR/cron.conf" ]]; then
    echo "❌ Error: No se encontró cron.conf en $PROJECT_DIR"
    exit 1
fi

# Cargar frecuencias. Usamos un parser simple ya que bash no soporta 'source' directo
# con comentarios e igualdades de manera segura sin evaluar. Pero como es formato simple,
# podemos filtrar las líneas vacías o comentarios y hacer export/eval.
while IFS= read -r line || [[ -n "$line" ]]; do
    # Limpiar espacios
    line=$(echo "$line" | xargs)
    # Ignorar vacíos y comentarios
    if [[ -z "$line" || "$line" =~ ^# ]]; then
        continue
    fi
    # Extraer clave y valor
    if [[ "$line" =~ ^([^=]+)=(.*)$ ]]; then
        key="${BASH_REMATCH[1]}"
        value="${BASH_REMATCH[2]}"
        # Quitar comillas del valor
        value=$(echo "$value" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
        declare "$key=$value"
    fi
done < "$PROJECT_DIR/cron.conf"

# Defaults de cron.conf (una sola corrida del pipeline completo):
# PIPELINE_SCHEDULE ejecuta TODAS las entidades en orden de FK en un mismo
# proceso (proveedores -> oc_items -> solic_gastos -> orden_pago -> retenciones)
# y al terminar envia UN unico mail con la duracion total y, si hubo errores,
# el detalle por entidad y la respuesta del migrator.
: "${PIPELINE_SCHEDULE:=*/10 * * * *}"
: "${INTEGRITY_SCHEDULE:=0 2 * * *}"

# Quitar entradas previas de este proyecto (por PROJECT_DIR) y registrar
TMP=$(mktemp)
( crontab -l 2>/dev/null | grep -v "$PROJECT_DIR" || true ) > "$TMP"

# ── Pipeline completo: todas las entidades en orden, un unico mail final ──
# run_entity.sh all -> main.py run (proveedores -> oc_items -> solic_gastos
# -> orden_pago -> retenciones) con NOTIFY_RUN_REPORT=true.
echo "$PIPELINE_SCHEDULE $RUN all" >> "$TMP"

# ── check_integrity (diario off-hours con lock) ──
echo "$INTEGRITY_SCHEDULE flock -n $PROJECT_DIR/state/locks/integrity.lock $PY $INTEGRITY --apply >> $INTEGRITY_LOG 2>&1" >> "$TMP"

crontab "$TMP"
rm -f "$TMP"

echo "✅ Cron jobs instalados/actualizados para: $PROJECT_DIR"
echo ""
crontab -l | grep "$PROJECT_DIR"
