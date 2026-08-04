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

# Cargar frecuencias desde cron.conf. Solo aceptamos líneas de la forma
#   KEY="valor"   # comentario inline opcional
#   KEY=valor
# El valor entre comillas se toma tal cual; cualquier comentario inline
# posterior a las comillas se ignora (NO debe filtrarse al schedule del cron).
# WHITELIST: solo se aceptan las 3 claves de schedule. Un cron.conf con una
# línea PROJECT_DIR=... o RUN=... (por error o merge) redefiniría variables
# internas del script y corrompería el crontab instalado.
_assign_schedule() {
    case "$1" in
        PIPELINE_SCHEDULE|DAILY_REPORT_SCHEDULE|INTEGRITY_SCHEDULE)
            declare -g "$1=$2"
            ;;
        *)
            echo "⚠️  cron.conf: clave '$1' ignorada (solo se aceptan *_SCHEDULE)" >&2
            ;;
    esac
}
while IFS= read -r line || [[ -n "$line" ]]; do
    # Ignorar líneas vacías y comentarios de línea completa
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    # KEY="valor entre comillas"  (el comentario inline queda fuera de la captura)
    if [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=\"([^\"]*)\" ]]; then
        _assign_schedule "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    # KEY=valor  (sin comillas: se corta en el primer espacio o '#')
    elif [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=([^[:space:]#]+) ]]; then
        _assign_schedule "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    fi
done < "$PROJECT_DIR/cron.conf"

# Defaults de cron.conf:
# - PIPELINE_SCHEDULE: corrida del pipeline completo cada 10 min (sin mail).
# - DAILY_REPORT_SCHEDULE: UN unico mail resumen del dia + purga del historial.
# - INTEGRITY_SCHEDULE: verificacion de integridad diaria.
: "${PIPELINE_SCHEDULE:=*/10 * * * *}"
: "${DAILY_REPORT_SCHEDULE:=55 23 * * *}"
: "${INTEGRITY_SCHEDULE:=0 2 * * *}"

# Quitar entradas previas de este proyecto (por PROJECT_DIR) y registrar.
# IMPORTANTE: distinguir "sin crontab" (OK, se arranca vacío) de un fallo real
# de `crontab -l`. Si el fallo se silenciara, el `crontab "$TMP"` de abajo
# REEMPLAZARÍA el crontab completo del usuario solo con nuestras 3 entradas.
TMP=$(mktemp)
CRON_CURRENT=""
if ! CRON_CURRENT=$(crontab -l 2>&1); then
    if ! grep -qi "no crontab" <<< "$CRON_CURRENT"; then
        echo "❌ Error leyendo el crontab actual (no se toca nada): $CRON_CURRENT" >&2
        rm -f "$TMP"
        exit 1
    fi
    CRON_CURRENT=""
fi
# grep -F: PROJECT_DIR es un path literal, no una regex (los '.' matcheaban
# cualquier caracter y podían borrar líneas de otros proyectos).
( grep -vF -- "$PROJECT_DIR" <<< "$CRON_CURRENT" || true ) > "$TMP"

# ── Pipeline completo cada 10 min: todas las entidades en orden, sin mail ──
# run_entity.sh all -> main.py run (proveedores -> oc_items -> solic_gastos
# -> orden_pago -> retenciones). Registra cada corrida para el resumen diario.
echo "$PIPELINE_SCHEDULE $RUN all" >> "$TMP"

# ── Resumen diario por email (un unico mail con el total del dia) ──
DAILY_LOG="$LOG_DIR/daily_report.log"
echo "$DAILY_REPORT_SCHEDULE flock -n $PROJECT_DIR/state/locks/daily_report.lock bash -c 'cd $PROJECT_DIR && $PY main.py daily-report >> $DAILY_LOG 2>&1'" >> "$TMP"

# ── check_integrity (diario off-hours con lock) ──
# cd al proyecto: el script usa paths relativos (state/checkpoint.db); sin el
# cd, corría contra una DB vacía en $HOME y la verificación era un no-op.
echo "$INTEGRITY_SCHEDULE flock -n $PROJECT_DIR/state/locks/integrity.lock bash -c 'cd $PROJECT_DIR && $PY $INTEGRITY --apply >> $INTEGRITY_LOG 2>&1'" >> "$TMP"

crontab "$TMP"
rm -f "$TMP"

echo "✅ Cron jobs instalados/actualizados para: $PROJECT_DIR"
echo ""
crontab -l | grep "$PROJECT_DIR"
