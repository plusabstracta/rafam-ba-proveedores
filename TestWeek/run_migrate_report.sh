#!/usr/bin/env bash
# ============================================================================
# TestWeek/run_migrate_report.sh
# Ejecuta make migrate-all, captura métricas por entidad y envía reporte email.
# Tiempo de vida: 1 semana. Luego usar remove_cron.sh para limpiar.
#
# Uso manual:  ./TestWeek/run_migrate_report.sh
# Auto-setup:  ./TestWeek/run_migrate_report.sh --install-cron
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
CRON_TAG="TESTWEEK_MIGRATE_ALL"
TODAY_YYYYMMDD="$(date +%Y%m%d)"
MORNING_STATUS_FILE="$LOG_DIR/${TODAY_YYYYMMDD}_morning.status"

mkdir -p "$LOG_DIR"

# --- Parseo de argumentos -----------------------------------------------------
INSTALL_CRON=false
RETRY_IF_NEEDED=false
SLOT="manual"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-cron)
            INSTALL_CRON=true
            ;;
        --retry-if-needed)
            RETRY_IF_NEEDED=true
            ;;
        --slot)
            SLOT="${2:-manual}"
            shift
            ;;
    esac
    shift
done

# --- Instalar cron si se pide ------------------------------------------------
if [[ "$INSTALL_CRON" == "true" ]]; then
    CRON_SCHEDULE_MORNING="0 7 * * 1-5"  # Lunes a Viernes a las 07:00
    CRON_SCHEDULE_RETRY="0 20 * * 1-5"   # Lunes a Viernes a las 20:00
    CRON_CMD_MORNING="cd $PROJECT_DIR && $SCRIPT_DIR/run_migrate_report.sh --slot morning >> $LOG_DIR/cron_morning.log 2>&1 # $CRON_TAG"
    CRON_CMD_RETRY="cd $PROJECT_DIR && $SCRIPT_DIR/run_migrate_report.sh --retry-if-needed --slot retry_20 >> $LOG_DIR/cron_retry_20.log 2>&1 # $CRON_TAG"

    # Evitar duplicados
    (crontab -l 2>/dev/null | grep -v "$CRON_TAG") | {
        cat
        echo "$CRON_SCHEDULE_MORNING $CRON_CMD_MORNING"
        echo "$CRON_SCHEDULE_RETRY $CRON_CMD_RETRY"
    } | crontab -
    echo "✔ Cron instalado:"
    echo "  - $CRON_SCHEDULE_MORNING (corrida principal)"
    echo "  - $CRON_SCHEDULE_RETRY (reintento condicional)"
    echo "  Tag: $CRON_TAG"
    echo "  Para remover: ./TestWeek/remove_cron.sh"
    exit 0
fi

# --- Modo reintento: ejecutar solo si 07:00 no corrió o falló ----------------
if [[ "$RETRY_IF_NEEDED" == "true" ]]; then
    if [[ ! -f "$MORNING_STATUS_FILE" ]]; then
        echo ">>> [retry_20] No existe estado de la corrida de las 07:00 para hoy. Se ejecuta reintento."
    else
        MORNING_STATUS="$(cat "$MORNING_STATUS_FILE" 2>/dev/null || echo "ERROR")"
        if [[ "$MORNING_STATUS" == "SUCCESS" ]]; then
            echo ">>> [retry_20] La corrida de las 07:00 fue exitosa. No se ejecuta reintento."
            exit 0
        fi
        echo ">>> [retry_20] La corrida de las 07:00 quedó con error. Se ejecuta reintento."
    fi
fi

# --- Preparar entorno ---------------------------------------------------------
cd "$PROJECT_DIR"

# Cargar .env si existe (para NOTIFY_* vars)
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# Activar venv
if [[ -f .venv/bin/activate ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

# --- Entidades en orden de migración ------------------------------------------
ENTITIES=("proveedores" "oc" "facturas" "op" "retenciones")
MAKE_TARGETS=("migrate-proveedores" "migrate-oc" "migrate-facturas" "migrate-op" "migrate-retenciones")

declare -A ENTITY_TIME
declare -A ENTITY_EXIT
declare -A ENTITY_OUTPUT

TOTAL_START=$(date +%s)
OVERALL_EXIT=0
RUN_DATE=$(date '+%Y-%m-%d %H:%M:%S')

# --- Capturar overhead del servidor antes -------------------------------------
LOAD_BEFORE=$(cat /proc/loadavg 2>/dev/null || echo "N/A")
MEM_BEFORE=$(free -m 2>/dev/null | awk '/^Mem:/{printf "%s/%sMB (%.0f%%)", $3, $2, $3/$2*100}' || echo "N/A")

# --- Ejecutar cada entidad ----------------------------------------------------
for i in "${!ENTITIES[@]}"; do
    entity="${ENTITIES[$i]}"
    target="${MAKE_TARGETS[$i]}"

    echo ">>> [$entity] Iniciando: make $target"
    ENT_START=$(date +%s)

    set +e
    OUTPUT=$(make "$target" 2>&1)
    EXIT_CODE=$?
    set -e

    ENT_END=$(date +%s)
    ENT_ELAPSED=$(( ENT_END - ENT_START ))

    ENTITY_TIME["$entity"]=$ENT_ELAPSED
    ENTITY_EXIT["$entity"]=$EXIT_CODE
    ENTITY_OUTPUT["$entity"]="$OUTPUT"

    if [[ $EXIT_CODE -ne 0 ]]; then
        OVERALL_EXIT=1
    fi

    echo ">>> [$entity] Terminado en ${ENT_ELAPSED}s (exit: $EXIT_CODE)"
done

TOTAL_END=$(date +%s)
TOTAL_ELAPSED=$(( TOTAL_END - TOTAL_START ))
TOTAL_MINUTES=$(awk "BEGIN {printf \"%.2f\", $TOTAL_ELAPSED/60}")

# --- Capturar overhead del servidor después -----------------------------------
LOAD_AFTER=$(cat /proc/loadavg 2>/dev/null || echo "N/A")
MEM_AFTER=$(free -m 2>/dev/null | awk '/^Mem:/{printf "%s/%sMB (%.0f%%)", $3, $2, $3/$2*100}' || echo "N/A")

# --- Cola de reintentos -------------------------------------------------------
RETRY_QUEUE=""
if [[ -f "$PROJECT_DIR/state/retry_queue.db" ]] || [[ -f "$PROJECT_DIR/state/rafam_sync.db" ]]; then
    RETRY_QUEUE=$(.venv/bin/python -c "
import sys, os
sys.path.insert(0, '.')
from src.retry_store import RetryStore
store = RetryStore()
items = store.list_items()
if not items:
    print('Cola vacía (0 registros)')
else:
    print(f'Total en cola: {len(items)}')
    by_entity = {}
    for it in items:
        by_entity.setdefault(it.entity, []).append(it)
    for ent, ent_items in sorted(by_entity.items()):
        print(f'  - {ent}: {len(ent_items)} registros')
        for item in ent_items[:5]:
            print(f'      pk={item.source_pk} reason={item.reason} attempts={item.attempt_count}')
        if len(ent_items) > 5:
            print(f'      ... y {len(ent_items)-5} más')
" 2>&1 || echo "No se pudo leer la cola de reintentos")
fi

# --- Construir reporte --------------------------------------------------------
REPORT="═══════════════════════════════════════════════════════════
 REPORTE DIARIO - make migrate-all
 Fecha: $RUN_DATE
 Estado: $(if [[ $OVERALL_EXIT -eq 0 ]]; then echo '✅ OK'; else echo '❌ CON ERRORES'; fi)
═══════════════════════════════════════════════════════════

─── TIEMPO TOTAL ───
  Duración: ${TOTAL_ELAPSED}s (${TOTAL_MINUTES} min)

─── DETALLE POR ENTIDAD ───"

for entity in "${ENTITIES[@]}"; do
    elapsed="${ENTITY_TIME[$entity]}"
    exit_code="${ENTITY_EXIT[$entity]}"
    minutes=$(awk "BEGIN {printf \"%.2f\", $elapsed/60}")
    status_icon=$(if [[ $exit_code -eq 0 ]]; then echo '✅'; else echo '❌'; fi)

    REPORT+="
  $status_icon $entity
     Tiempo: ${elapsed}s (${minutes} min)
     Exit code: $exit_code"

    if [[ $exit_code -ne 0 ]]; then
        # Incluir últimas 30 líneas del output de error
        ERROR_TAIL=$(echo "${ENTITY_OUTPUT[$entity]}" | tail -30)
        REPORT+="
     --- Output (últimas 30 líneas) ---
$ERROR_TAIL
     -----------------------------------"
    fi
done

REPORT+="

─── COLA DE REINTENTOS ───
$RETRY_QUEUE

─── OVERHEAD DEL SERVIDOR ───
  Load Average ANTES:  $LOAD_BEFORE
  Load Average DESPUÉS: $LOAD_AFTER
  Memoria ANTES:  $MEM_BEFORE
  Memoria DESPUÉS: $MEM_AFTER

═══════════════════════════════════════════════════════════
"

# --- Guardar reporte local ----------------------------------------------------
REPORT_FILE="$LOG_DIR/report_$(date +%Y%m%d_%H%M%S).txt"
echo "$REPORT" > "$REPORT_FILE"
echo ">>> Reporte guardado en: $REPORT_FILE"

# Persistir estado de la corrida de mañana para la validación de las 20:00.
if [[ "$SLOT" == "morning" ]]; then
    if [[ $OVERALL_EXIT -eq 0 ]]; then
        echo "SUCCESS" > "$MORNING_STATUS_FILE"
    else
        echo "ERROR" > "$MORNING_STATUS_FILE"
    fi
fi

# --- Enviar email via notifier.py ---------------------------------------------
SUBJECT="migrate-all $(date +%Y-%m-%d) — $(if [[ $OVERALL_EXIT -eq 0 ]]; then echo 'OK'; else echo 'ERRORES'; fi) (${TOTAL_MINUTES} min)"

.venv/bin/python -c "
import sys, os
sys.path.insert(0, '.')
from src.notifier import send_notification

subject = '''$SUBJECT'''
body = '''$REPORT'''

ok = send_notification(subject, body.replace(\"'''\", ''))
if ok:
    print('✔ Email enviado')
else:
    print('⚠ No se pudo enviar email (verificar NOTIFY_* en .env)')
    sys.exit(1)
" 2>&1 || echo "⚠ Falló el envío de email"

echo ">>> Ejecución completa."
exit $OVERALL_EXIT
