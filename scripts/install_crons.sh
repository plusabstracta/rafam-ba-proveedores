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
SYNC_LOG="$LOG_DIR/sync_changes.log"
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

# Verificar que las variables necesarias existan
for var in PROV_LABORAL PROV_FUERA OC_LABORAL OC_FUERA SG_LABORAL SG_FUERA OP_LABORAL OP_FUERA RET_LABORAL RET_FUERA INTEGRITY_SCHEDULE SYNC_PROVEEDORES_SCHEDULE SYNC_OC_SCHEDULE; do
    if [[ -z "${!var:-}" ]]; then
        echo "❌ Error: Variable $var no definida en cron.conf"
        exit 1
    fi
done

# Función helper para soportar intervalos de 30s usando sleep
append_cron_entry() {
    local schedule="$1"
    local entity="$2"
    if [[ "$schedule" == "30s" ]]; then
        echo "* * * * * $RUN $entity" >> "$TMP"
        echo "* * * * * sleep 30 && $RUN $entity" >> "$TMP"
    else
        echo "$schedule $RUN $entity" >> "$TMP"
    fi
}

# Quitar entradas previas de este proyecto (por PROJECT_DIR) y registrar
TMP=$(mktemp)
( crontab -l 2>/dev/null | grep -v "$PROJECT_DIR" || true ) > "$TMP"

# ── proveedores ──
append_cron_entry "$PROV_LABORAL" proveedores
append_cron_entry "$PROV_FUERA" proveedores

# ── oc_items ──
append_cron_entry "$OC_LABORAL" oc_items
append_cron_entry "$OC_FUERA" oc_items

# ── solic_gastos ──
append_cron_entry "$SG_LABORAL" solic_gastos
append_cron_entry "$SG_FUERA" solic_gastos

# ── orden_pago ──
append_cron_entry "$OP_LABORAL" orden_pago
append_cron_entry "$OP_FUERA" orden_pago

# ── retenciones ──
append_cron_entry "$RET_LABORAL" retenciones
append_cron_entry "$RET_FUERA" retenciones

# ── check_integrity (diario off-hours con lock) ──
if [[ "$INTEGRITY_SCHEDULE" == "30s" ]]; then
    echo "* * * * * flock -n $PROJECT_DIR/state/locks/integrity.lock $PY $INTEGRITY --apply >> $INTEGRITY_LOG 2>&1" >> "$TMP"
    echo "* * * * * sleep 30 && flock -n $PROJECT_DIR/state/locks/integrity.lock $PY $INTEGRITY --apply >> $INTEGRITY_LOG 2>&1" >> "$TMP"
else
    echo "$INTEGRITY_SCHEDULE  flock -n $PROJECT_DIR/state/locks/integrity.lock $PY $INTEGRITY --apply >> $INTEGRITY_LOG 2>&1" >> "$TMP"
fi

# ── sync-changes (updates semanales de registros ya migrados, con lock) ──
echo "$SYNC_PROVEEDORES_SCHEDULE  cd $PROJECT_DIR && flock -n $PROJECT_DIR/state/locks/sync_changes_prov.lock $PY main.py sync-changes --entity proveedores >> $SYNC_LOG 2>&1" >> "$TMP"
echo "$SYNC_OC_SCHEDULE  cd $PROJECT_DIR && flock -n $PROJECT_DIR/state/locks/sync_changes_oc.lock $PY main.py sync-changes --entity oc_items >> $SYNC_LOG 2>&1" >> "$TMP"

crontab "$TMP"
rm -f "$TMP"

echo "✅ Cron jobs instalados/actualizados para: $PROJECT_DIR"
echo ""
crontab -l | grep "$PROJECT_DIR"
