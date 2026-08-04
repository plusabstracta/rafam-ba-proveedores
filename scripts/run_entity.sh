#!/usr/bin/env bash
# scripts/run_entity.sh <entity|all>
# Wrapper seguro con flock: evita que dos corridas se pisen.
#   <entity>  corre una sola entidad:     main.py run --entity <entity>
#   all       corre el pipeline completo:  main.py run  (todas en orden de FK)
#             y registra la corrida para el resumen diario (sin mail por corrida).
set -euo pipefail

ENTITY="${1:?Falta entidad (usa 'all' para el pipeline completo)}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOCK_DIR="$PROJECT_DIR/state/locks"

if [[ "$ENTITY" == "all" ]]; then
    LOG_FILE="$PROJECT_DIR/logs/rafam-pipeline-cron.log"
    LOCK_FILE="$LOCK_DIR/pipeline.lock"
else
    RUN_ARGS="run --entity $ENTITY"
    LOG_FILE="$PROJECT_DIR/logs/rafam-${ENTITY}-cron.log"
    LOCK_FILE="$LOCK_DIR/${ENTITY}.lock"
fi

mkdir -p "$LOCK_DIR" "$PROJECT_DIR/logs"

TS_START=$(date '+%Y-%m-%d %H:%M:%S')

# Lock no bloqueante sobre descriptor para cubrir toda la ejecución del script.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "[$TS_START] [SKIP] ${ENTITY}: corrida anterior aun en curso (lock activo)" | tee -a "$LOG_FILE"
    exit 0
fi

if [[ "$ENTITY" == "all" ]]; then
    echo "[$TS_START] [START] all" | tee -a "$LOG_FILE"
    T0=$(date +%s)
    cd "$PROJECT_DIR"

    ENTITIES=(proveedores oc_items solic_gastos orden_pago retenciones)
    TOTAL=${#ENTITIES[@]}
    FAIL_COUNT=0

    for IDX in "${!ENTITIES[@]}"; do
        E="${ENTITIES[$IDX]}"
        POS=$((IDX + 1))
        ET0=$(date +%s)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [PROGRESS] [$POS/$TOTAL] START entidad=$E" | tee -a "$LOG_FILE"

        if .venv/bin/python main.py run --entity "$E" >> "$LOG_FILE" 2>&1; then
            ERC=0
        else
            ERC=$?
        fi
        EELAPSED=$(( $(date +%s) - ET0 ))

        if [[ $ERC -eq 0 ]]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] [PROGRESS] [$POS/$TOTAL] OK entidad=$E rc=$ERC duracion=${EELAPSED}s" | tee -a "$LOG_FILE"
        elif [[ $ERC -eq 75 ]]; then
            # 75 = EX_TEMPFAIL: otro proceso tiene el lock global de main.py.
            # No es un fallo; la proxima corrida del cron lo retoma.
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] [PROGRESS] [$POS/$TOTAL] SKIP entidad=$E rc=$ERC (lock ocupado) duracion=${EELAPSED}s" | tee -a "$LOG_FILE"
        else
            FAIL_COUNT=$((FAIL_COUNT + 1))
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] [PROGRESS] [$POS/$TOTAL] FAIL entidad=$E rc=$ERC duracion=${EELAPSED}s" | tee -a "$LOG_FILE"
        fi
    done

    ELAPSED=$(( $(date +%s) - T0 ))
    if [[ $FAIL_COUNT -eq 0 ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [END] all: rc=0 duracion=${ELAPSED}s" | tee -a "$LOG_FILE"
        exit 0
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [END] all: rc=1 duracion=${ELAPSED}s fallas=$FAIL_COUNT" | tee -a "$LOG_FILE"
    exit 1
fi

echo "[$TS_START] [START] ${ENTITY}" | tee -a "$LOG_FILE"
T0=$(date +%s)
cd "$PROJECT_DIR"
if .venv/bin/python main.py ${RUN_ARGS} >> "$LOG_FILE" 2>&1; then
    RC=0
else
    RC=$?
fi
ELAPSED=$(( $(date +%s) - T0 ))
if [[ $RC -eq 75 ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [END] ${ENTITY}: SKIP rc=$RC (lock ocupado) duracion=${ELAPSED}s" | tee -a "$LOG_FILE"
    exit 0
fi
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [END] ${ENTITY}: rc=$RC duracion=${ELAPSED}s" | tee -a "$LOG_FILE"
exit $RC
