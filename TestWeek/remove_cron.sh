#!/usr/bin/env bash
# ============================================================================
# TestWeek/remove_cron.sh
# Elimina el cron job de TestWeek y opcionalmente borra la carpeta completa.
# ============================================================================
set -euo pipefail

CRON_TAG="TESTWEEK_MIGRATE_ALL"

echo "Buscando cron con tag: $CRON_TAG"

EXISTING=$(crontab -l 2>/dev/null | grep "$CRON_TAG" || true)

if [[ -z "$EXISTING" ]]; then
    echo "⚠ No se encontró cron job con tag '$CRON_TAG'. Nada que remover."
else
    crontab -l 2>/dev/null | grep -v "$CRON_TAG" | crontab -
    echo "✔ Cron job eliminado:"
    echo "  $EXISTING"
fi

echo ""
echo "Para eliminar la carpeta TestWeek completa:"
echo "  rm -rf $(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
