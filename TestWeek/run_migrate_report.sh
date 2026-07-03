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
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/rafam_migrate_report.XXXXXX")"
REPORT_DUMP_PAYLOAD_FORCE="${REPORT_DUMP_PAYLOAD_FORCE:-1}"

mkdir -p "$LOG_DIR"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

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
    OUTPUT_FILE="$TMP_DIR/${entity}.out"
    DUMP_FILE="$TMP_DIR/${entity}.payload.dump"
    : > "$DUMP_FILE"

    set +e
    OUTPUT=$(env \
        DUMP_PAYLOAD="$DUMP_FILE" \
        DUMP_PAYLOAD_FORCE="$REPORT_DUMP_PAYLOAD_FORCE" \
        make "$target" 2>&1)
    EXIT_CODE=$?
    set -e
    printf '%s\n' "$OUTPUT" > "$OUTPUT_FILE"

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

# --- Payloads generados/enviados y respuesta Paxapos -------------------------
set +e
PAYLOAD_REPORT=$(.venv/bin/python - "$TMP_DIR" "${ENTITIES[@]}" <<'PY'
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

tmp_dir = Path(sys.argv[1])
entities = list(sys.argv[2:])

official_entity = {
    "proveedores": "proveedores",
    "oc": "oc_items",
    "facturas": "solic_gastos",
    "op": "orden_pago",
    "retenciones": "retenciones",
}

section_labels = {
    "proveedores": "proveedores",
    "ordenes_compra": "ordenes de compra",
    "gastos": "gastos/facturas",
    "ordenes_pago": "ordenes de pago",
    "retenciones": "retenciones",
    "pedidos": "pedidos",
}
payload_sections = tuple(section_labels.keys())
dash = "—"


def parse_json_blocks(path: Path):
    requests = []
    responses = []
    if not path.exists() or path.stat().st_size == 0:
        return requests, responses

    current_kind = None
    current_lines = []

    def flush_kind(kind, lines):
        raw = "\n".join(lines).strip()
        if not kind or not raw:
            return
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return
        if kind == "request":
            requests.append(parsed)
        elif kind == "response":
            responses.append(parsed)

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("=== POST "):
            flush_kind(current_kind, current_lines)
            current_kind = "request"
            current_lines = []
            continue
        if line.startswith("--- RESPONSE"):
            flush_kind(current_kind, current_lines)
            current_kind = "response"
            current_lines = []
            continue
        if current_kind:
            current_lines.append(line)
    flush_kind(current_kind, current_lines)
    return requests, responses


def parse_run_output(path: Path, label: str):
    if not path.exists():
        return {"mode": None, "records": None, "lines": []}
    text = path.read_text(encoding="utf-8", errors="replace")
    official = official_entity.get(label, label)
    pattern = re.compile(
        r"\[(DRY RUN|FULL LOAD|INCREMENTAL)\s*\]\s+([A-Za-z_]+)\s+" + dash + r"\s+(\d+)\s+registros"
    )
    found = None
    for match in pattern.finditer(text):
        if match.group(2) == official:
            found = {"mode": match.group(1), "records": int(match.group(3))}
    interesting = []
    for line in text.splitlines():
        lower = line.lower()
        if any(token in lower for token in ("paxapos", "mismo_estado", "skip", "cola de reintentos", "error", "warning", "payload")):
            interesting.append(line)
    return {
        "mode": found["mode"] if found else None,
        "records": found["records"] if found else None,
        "lines": interesting[-8:],
    }


def list_counts(counter):
    if not counter:
        return "sin resultados"
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items()))


def _compact(value, max_len=160):
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _json_compact(value, max_len=220):
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        text = str(value)
    return _compact(text, max_len=max_len)


def _extract_record_summary(section, item):
    if not isinstance(item, dict):
        return _json_compact(item)

    if section == "proveedores":
        ext = item.get("external_id") or {}
        prov = item.get("Proveedor") or {}
        return (
            f"cod_prov={ext.get('cod_prov', dash)}; "
            f"razon_social={_compact(prov.get('razon_social') or prov.get('name') or dash, 120)}; "
            f"cuit={prov.get('cuit', dash)}; "
            f"mail={_compact(prov.get('mail') or dash, 80)}"
        )

    if section == "ordenes_compra":
        ext = item.get("external_id") or {}
        pedido = item.get("Pedido") or {}
        items = item.get("items") or []
        return (
            f"oc={ext.get('ejercicio', dash)}-{ext.get('uni_compra', dash)}-{ext.get('nro_oc', dash)}; "
            f"internal_id={pedido.get('internal_id', dash)}; "
            f"proveedor_id={pedido.get('proveedor_id', dash)}; "
            f"deleted={pedido.get('deleted', 0)}; "
            f"items={len(items)}"
        )

    if section == "gastos":
        ext = item.get("external_id") or {}
        gasto = item.get("Gasto") or {}
        return (
            f"sg={ext.get('ejercicio', dash)}-{ext.get('deleg_solic', dash)}-{ext.get('nro_solic', dash)}; "
            f"proveedor_id={gasto.get('proveedor_id', dash)}; "
            f"factura={_compact(gasto.get('factura_nro') or dash, 80)}; "
            f"pv={_compact(gasto.get('punto_de_venta') or dash, 20)}; "
            f"importe_total={gasto.get('importe_total', dash)}; "
            f"fecha={gasto.get('fecha', dash)}"
        )

    if section == "ordenes_pago":
        ext = item.get("external_id") or {}
        egreso = item.get("Egreso") or {}
        retenciones = item.get("retenciones") or []
        return (
            f"op={ext.get('ejercicio', dash)}-{ext.get('nro_op', dash)}; "
            f"identificador={_compact(egreso.get('identificador_pago') or dash, 80)}; "
            f"total={egreso.get('total', dash)}; "
            f"fecha={egreso.get('fecha', dash)}; "
            f"pedido_id={item.get('pedido_id', dash)}; "
            f"comprobante={_compact(item.get('gasto_nro_comprobante') or dash, 80)}; "
            f"retenciones={len(retenciones)}"
        )

    if section == "retenciones":
        ext = item.get("external_id") or {}
        retenciones = item.get("retenciones") or []
        detail = []
        for ret in retenciones:
            if not isinstance(ret, dict):
                continue
            rid = ret.get("external_id") or {}
            detail.append(
                f"cod={rid.get('codigo_deduc', dash)} monto={ret.get('monto_retenido', dash)}"
            )
        detail_text = "; ".join(detail) if detail else dash
        return (
            f"op={ext.get('ejercicio', dash)}-{ext.get('nro_op', dash)}; "
            f"retenciones_count={len(retenciones)}; "
            f"detalle={_compact(detail_text, 200)}"
        )

    return _json_compact(item)


def stats_text(stats):
    chunks = []
    for section in payload_sections:
        values = stats.get(section)
        if not values:
            continue
        total = values.get("total", 0)
        ok = values.get("ok", 0)
        error = values.get("error", 0)
        chunks.append(f"{section_labels.get(section, section)}: total={total}, ok={ok}, error={error}")
    return "; ".join(chunks) if chunks else "sin stats de backend"


summaries = {}
global_payloads = 0
global_requests = 0
global_responses = 0
global_backend_errors = 0
global_modes = Counter()

for entity in entities:
    requests, responses = parse_json_blocks(tmp_dir / f"{entity}.payload.dump")
    output = parse_run_output(tmp_dir / f"{entity}.out", entity)

    request_counts = Counter()
    record_details = []
    for request_index, request in enumerate(requests, start=1):
        if not isinstance(request, dict):
            continue
        for section in payload_sections:
            items = request.get(section)
            if isinstance(items, list):
                request_counts[section] += len(items)
                for item_index, item in enumerate(items, start=1):
                    summary = _extract_record_summary(section, item)
                    record_details.append(
                        {
                            "request_index": request_index,
                            "item_index": item_index,
                            "section": section,
                            "summary": summary,
                        }
                    )

    stats = defaultdict(lambda: {"total": 0, "ok": 0, "error": 0})
    modes = Counter()
    errors = []
    for response in responses:
        if not isinstance(response, dict):
            continue
        response_stats = response.get("stats") or {}
        if isinstance(response_stats, dict):
            for section, values in response_stats.items():
                if not isinstance(values, dict):
                    continue
                stats[section]["total"] += int(values.get("total") or 0)
                stats[section]["ok"] += int(values.get("ok") or 0)
                stats[section]["error"] += int(values.get("error") or 0)
        results = response.get("results") or {}
        if isinstance(results, dict):
            for section, rows in results.items():
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if isinstance(row, dict) and row.get("mode"):
                        modes[f"{section}:{row['mode']}"] += 1
        response_errors = response.get("errors") or []
        if isinstance(response_errors, list):
            errors.extend(response_errors)

    payload_count = sum(request_counts.values())
    backend_error_count = max(len(errors), sum(values.get("error", 0) for values in stats.values()))

    global_payloads += payload_count
    global_requests += len(requests)
    global_responses += len(responses)
    global_backend_errors += backend_error_count
    global_modes.update(modes)

    created_count = sum(value for key, value in modes.items() if key.endswith(":create"))
    update_count = sum(value for key, value in modes.items() if key.endswith(":update"))
    replace_count = sum(value for key, value in modes.items() if key.endswith(":replace"))

    if payload_count == 0:
        conclusion = "No se genero ni envio payload hacia Paxapos. No hay altas nuevas por esta entidad."
    elif created_count > 0:
        conclusion = f"Se envio payload y Paxapos informo {created_count} alta(s) nueva(s) con mode=create."
    elif update_count or replace_count:
        conclusion = (
            "Se envio payload, pero Paxapos no informo altas nuevas; "
            f"respondio update={update_count}, replace={replace_count}."
        )
    else:
        conclusion = "Se envio payload, pero la respuesta no trajo mode=create/update/replace para confirmar altas."

    summaries[entity] = {
        "output": output,
        "requests": len(requests),
        "responses": len(responses),
        "request_counts": request_counts,
        "payload_count": payload_count,
        "record_details": record_details,
        "stats": dict(stats),
        "modes": modes,
        "errors": errors,
        "backend_error_count": backend_error_count,
        "conclusion": conclusion,
    }

global_created = sum(value for key, value in global_modes.items() if key.endswith(":create"))
global_updated = sum(value for key, value in global_modes.items() if key.endswith(":update"))
global_replaced = sum(value for key, value in global_modes.items() if key.endswith(":replace"))

lines = []
lines.append("─── PAYLOADS Y ALTAS EN PAXAPOS ───")
lines.append(f"  Payloads generados/enviados: {'SI' if global_payloads else 'NO'} ({global_payloads} item(s) en {global_requests} request(s))")
lines.append(f"  Respuestas recibidas: {global_responses}")
lines.append(f"  Registros nuevos confirmados por Paxapos (mode=create): {global_created}")
lines.append(f"  Actualizaciones confirmadas (mode=update): {global_updated}")
lines.append(f"  Reemplazos/idempotencia confirmados (mode=replace): {global_replaced}")
lines.append(f"  Errores reportados por backend: {global_backend_errors}")
lines.append("  Nota: payload enviado significa actividad hacia Paxapos; alta nueva se confirma solo con mode=create.")
lines.append("")
lines.append("  Detalle por entidad:")

for entity in entities:
    summary = summaries[entity]
    output = summary["output"]
    records = output["records"]
    mode = output["mode"] or "sin modo detectado"
    records_text = str(records) if records is not None else "no detectado"

    lines.append(f"    - {entity}")
    lines.append(f"        Filas procesadas por el migrador: {records_text} ({mode})")
    lines.append(f"        Payloads enviados: {summary['payload_count']} item(s)")
    lines.append(f"        Respuestas: {summary['responses']}")
    lines.append(f"        Backend stats: {stats_text(summary['stats'])}")
    lines.append(f"        Modes: {list_counts(summary['modes'])}")
    lines.append(f"        Lectura: {summary['conclusion']}")
    if summary["record_details"]:
        lines.append(f"        Registros enviados (detalle completo): {len(summary['record_details'])}")
        for detail in summary["record_details"]:
            lines.append(
                "          "
                f"[req#{detail['request_index']} item#{detail['item_index']} {detail['section']}] "
                f"{detail['summary']}"
            )
    if summary["errors"]:
        sample = summary["errors"][:3]
        lines.append(f"        Errores muestra: {json.dumps(sample, ensure_ascii=False)}")
    if output["lines"]:
        lines.append("        Lineas relevantes del log:")
        for log_line in output["lines"]:
            lines.append(f"          {log_line}")

print("\n".join(lines))
PY
)
PAYLOAD_REPORT_EXIT=$?
set -e

if [[ $PAYLOAD_REPORT_EXIT -ne 0 ]]; then
    PAYLOAD_REPORT="─── PAYLOADS Y ALTAS EN PAXAPOS ───
  No se pudo generar el resumen de payloads.
  Error del parser:
$PAYLOAD_REPORT"
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

$PAYLOAD_REPORT

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
