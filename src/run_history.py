"""run_history.py — Registro compacto de corridas para el resumen diario.

Cada corrida del pipeline agrega una linea JSON con sus metricas. El comando
``main.py daily-report`` lee las corridas del dia, arma UN unico mail resumen
(tiempo total del dia y, si hubo errores, que entidad fallo y que devolvio el
migrator) y purga del historial las corridas ya reportadas.

El pipeline corre cada 10 minutos: enviar un mail por corrida seria inviable,
por eso el mail se agrega y se manda una sola vez por dia.
"""

from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = "state/run_history.jsonl"


def _path() -> Path:
    return Path(os.getenv("RAFAM_RUN_HISTORY_PATH", _DEFAULT_PATH))


def _hhmmss_to_secs(value: str) -> float:
    """Convierte 'HH:MM:SS' (o 'MM:SS' / 'SS') a segundos. 0.0 si no parsea."""
    try:
        parts = [int(p) for p in str(value).split(":")]
    except (ValueError, AttributeError):
        return 0.0
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0, parts[0], parts[1]
    elif len(parts) == 1:
        h, m, s = 0, 0, parts[0]
    else:
        return 0.0
    return h * 3600 + m * 60 + s


def _record_date(rec: dict) -> str | None:
    ts = rec.get("start_time") or rec.get("end_time")
    if not ts:
        return None
    return str(ts)[:10]  # YYYY-MM-DD


def record_run(summary_data: dict, entity_metrics: list[dict]) -> None:
    """Agrega una linea JSON con el resultado de la corrida al historial."""
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "hostname": summary_data.get("hostname"),
        "start_time": summary_data.get("start_time"),
        "end_time": summary_data.get("end_time"),
        "duration_formatted": summary_data.get("duration_formatted"),
        "success": summary_data.get("success", False),
        "error_msg": summary_data.get("error_msg"),
        "entities": [
            {
                "entity": m.get("entity"),
                "mode": m.get("mode"),
                "success": m.get("success", False),
                "records_ok": m.get("records_ok", 0),
                "migrator_sent": m.get("migrator_sent", 0),
                "migrator_saved": m.get("migrator_saved", 0),
                "migrator_errors": m.get("migrator_errors", 0),
                "batches_ok": m.get("batches_ok", 0),
                "batches_failed": m.get("batches_failed", 0),
                "duration_secs": m.get("duration_secs", 0.0),
                "query_duration_secs": m.get("query_duration_secs", 0.0),
                "error_msg": m.get("error_msg"),
                "error_type": m.get("error_type"),
                "error_location": m.get("error_location"),
                "migrator_error": m.get("migrator_error"),
                "error_trace": m.get("error_trace"),
            }
            for m in entity_metrics
        ],
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_runs(date_str: str | None = None) -> list[dict]:
    """Devuelve las corridas del historial; si date_str, solo las de ese dia."""
    path = _path()
    if not path.exists():
        return []
    runs: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if date_str is None or _record_date(rec) == date_str:
            runs.append(rec)
    return runs


def prune_reported(date_str: str) -> int:
    """Elimina las corridas con fecha <= date_str. Devuelve cuantas quedan."""
    path = _path()
    if not path.exists():
        return 0
    kept: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        d = _record_date(rec)
        if d is not None and d <= date_str:
            continue
        kept.append(line)
    path.write_text(("\n".join(kept) + "\n") if kept else "", encoding="utf-8")
    return len(kept)


def aggregate_runs(runs: list[dict], date_str: str) -> tuple[dict, list[dict]]:
    """Agrega las corridas del dia en (summary_data, entity_metrics).

    El resultado se pasa a ``notifier.notify_run_report`` para armar el mail
    unico del dia. Suma registros/batches por entidad y conserva el ultimo
    error (incluida la respuesta del migrator) para el detalle.
    """
    ent: "OrderedDict[str, dict]" = OrderedDict()
    total_secs = 0.0
    any_fail = False

    for r in runs:
        total_secs += _hhmmss_to_secs(r.get("duration_formatted", "0"))
        if not r.get("success", False):
            any_fail = True
        for m in r.get("entities", []) or []:
            name = m.get("entity", "?")
            agg = ent.setdefault(
                name,
                {
                    "entity": name,
                    "mode": "DIARIO",
                    "records_ok": 0,
                    "migrator_sent": 0,
                    "migrator_saved": 0,
                    "migrator_errors": 0,
                    "batches_ok": 0,
                    "batches_failed": 0,
                    "duration_secs": 0.0,
                    "query_duration_secs": 0.0,
                    "batch_times": [],
                    "success": True,
                    "error_msg": None,
                    "error_type": None,
                    "error_location": None,
                    "migrator_error": None,
                    "error_trace": None,
                },
            )
            agg["records_ok"] += int(m.get("records_ok", 0) or 0)
            agg["migrator_sent"] += int(m.get("migrator_sent", 0) or 0)
            agg["migrator_saved"] += int(m.get("migrator_saved", 0) or 0)
            agg["migrator_errors"] += int(m.get("migrator_errors", 0) or 0)
            agg["batches_ok"] += int(m.get("batches_ok", 0) or 0)
            agg["batches_failed"] += int(m.get("batches_failed", 0) or 0)
            agg["duration_secs"] += float(m.get("duration_secs", 0.0) or 0.0)
            agg["query_duration_secs"] += float(m.get("query_duration_secs", 0.0) or 0.0)
            if not m.get("success", False):
                agg["success"] = False
                for k in ("error_msg", "error_type", "error_location", "migrator_error", "error_trace"):
                    if m.get(k):
                        agg[k] = m.get(k)

    entity_metrics = list(ent.values())
    failed = [name for name, a in ent.items() if not a["success"]]
    status_label = "OK" if not any_fail else "CON ERRORES"

    h, rem = divmod(int(total_secs), 3600)
    mm, ss = divmod(rem, 60)
    duration_formatted = f"{h:02d}:{mm:02d}:{ss:02d}"

    summary_data = {
        "subject": f"Resumen diario RAFAM {date_str} — {status_label}",
        "hostname": (runs[-1].get("hostname") if runs else None) or "—",
        "start_time": (runs[0].get("start_time") if runs else "—"),
        "end_time": (runs[-1].get("end_time") if runs else "—"),
        "duration_formatted": duration_formatted,
        "success": not any_fail,
        "error_msg": (f"Entidades con error en el día: {', '.join(failed)}" if failed else None),
        "runs_count": len(runs),
        "retry_counts_start": {},
        "retry_counts_end": {},
    }
    return summary_data, entity_metrics
