#!/usr/bin/env bash
# scripts/run_entity.sh <entity>
# Wrapper seguro con flock: evita que dos corridas de la misma entidad se pisen.
set -euo pipefail

ENTITY="${1:?Falta entidad}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOCK_DIR="$PROJECT_DIR/state/locks"
LOG_FILE="$PROJECT_DIR/logs/rafam-${ENTITY}-cron.log"
LOCK_FILE="$LOCK_DIR/${ENTITY}.lock"

mkdir -p "$LOCK_DIR" "$PROJECT_DIR/logs"

TS_START=$(date '+%Y-%m-%d %H:%M:%S')

# -n: non-blocking. Si el lock ya está tomado, sale con código 1.
if ! flock -n "$LOCK_FILE" true; then
    echo "[$TS_START] [SKIP] ${ENTITY}: corrida anterior aun en curso (lock activo)" >> "$LOG_FILE"
    exit 0
fi

# Ejecutar dentro del lock (flock mantiene el fd abierto durante el subproceso)
exec flock -n "$LOCK_FILE" bash -c "
    echo '[$TS_START] [START] ${ENTITY}' >> '$LOG_FILE'
    T0=\$(date +%s)
    cd '$PROJECT_DIR'
    .venv/bin/python main.py run --entity '${ENTITY}' >> '$LOG_FILE' 2>&1
    RC=\$?
    ELAPSED=\$(( \$(date +%s) - T0 ))
    echo \"[\$(date '+%Y-%m-%d %H:%M:%S')] [END] ${ENTITY}: rc=\$RC duracion=\${ELAPSED}s\" >> '$LOG_FILE'
"
