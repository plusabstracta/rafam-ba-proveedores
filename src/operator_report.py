"""operator_report.py — Lista para el operador de RAFAM en el resumen diario.

El resumen diario arma, desde la cola de reintentos en vivo:

* PARA REVISAR EN RAFAM: todo registro que no llego a Paxapos y necesita que
  alguien lo mire (rechazos de Paxapos, datos invalidos, batches caidos,
  'permanent' y esperas que superaron RAFAM_WAIT_ALERT_DAYS), con que paso,
  desde cuando y el error. Hasta RAFAM_MAIL_RETRY_DETAIL_LIMIT por entidad; el
  resto, con `main.py retry-queue --entity X`.
* DESTRABADOS HOY: lo que salio de la cola en el dia (se migro, quedo fuera de
  alcance, se descarto a mano), para verificar que una correccion funciono.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from .notifier import _CLI, _REASON_HEADLINE, _WAIT_REASONS, describe_queue_state
from .record_ledger import with_paxapos_ids
from .retry_labels import describe_retry_key
from .retry_store import RESOLVED_MIGRATED
from .utils import days_since_utc_sql, utc_sql_to_local


def local_day_bounds_utc(day: date) -> tuple[str, str]:
    """[inicio, fin) del dia local ``day`` como timestamps UTC de SQLite."""
    start_local = datetime.combine(day, time.min).astimezone()
    end_local = datetime.combine(day + timedelta(days=1), time.min).astimezone()
    fmt = "%Y-%m-%d %H:%M:%S"
    return (
        start_local.astimezone(timezone.utc).strftime(fmt),
        end_local.astimezone(timezone.utc).strftime(fmt),
    )


def _row(item, *, max_attempts: int) -> dict:
    label = describe_retry_key(item.entity, item.external_id)
    is_wait = item.reason_code in _WAIT_REASONS
    if is_wait:
        que_paso = "espera vencida: depende de otro registro o de un dato de RAFAM"
    else:
        que_paso = _REASON_HEADLINE.get(item.reason_code, item.reason_code)
    if item.status == "permanent" and not getattr(item, "auto_retry", 1):
        next_retry = "no (rechazo terminal)"
    elif item.status == "permanent" and getattr(item, "next_retry_after", None):
        next_retry = utc_sql_to_local(item.next_retry_after)
    else:
        next_retry = "proxima corrida"
    days = days_since_utc_sql(item.first_seen)
    return {
        "entidad": item.entity,
        "registro": label,
        "clave_rafam": item.external_id,
        "id_paxapos": getattr(item, "paxapos_id", None) or "",
        "que_paso": que_paso,
        "motivo": f"{item.reason_code}/{item.reason_detail or 'sin detalle'}",
        "estado": "espera vencida" if is_wait else ("permanent" if item.status == "permanent" else "pendiente"),
        "detalle_estado": describe_queue_state(item, max_attempts=max_attempts),
        "en_cola_desde": utc_sql_to_local(item.first_seen),
        "dias": int(days) if days is not None else "",
        "ultimo_intento": utc_sql_to_local(item.last_attempt),
        "intentos": item.attempts,
        "proximo_reintento": next_retry,
        "error": str(item.error_message or "sin mensaje"),
        "reenviar": f'{_CLI} resend --entity {item.entity} --key "{label}"',
        "_first_seen_utc": item.first_seen or "",
    }


def build_operator_report(retry_store, *, day: date, body_limit: int, link_store=None) -> dict:
    """Foto de la cola para el mail diario (todas las entidades).

    Con ``link_store`` cada registro lleva su ID de Paxapos si ya existe alli.
    """
    day_start, day_end = local_day_bounds_utc(day)
    items = with_paxapos_ids(retry_store.attention_items(), link_store)
    attention = [_row(it, max_attempts=retry_store.max_attempts) for it in items]
    attention.sort(key=lambda r: (r["entidad"], r["_first_seen_utc"], r["registro"]))
    waiting: dict[str, int] = {}
    for item in retry_store.waiting_items():
        waiting[item.entity] = waiting.get(item.entity, 0) + 1
    resolved = [
        r for r in retry_store.resolved_since(day_start)
        if str(r.get("resolved_at") or "") < day_end
    ]
    return {
        "date": day.isoformat(),
        "attention": attention,
        "new_today": sum(1 for r in attention if day_start <= r["_first_seen_utc"] < day_end),
        "waiting": waiting,
        "resolved": resolved,
        "body_limit": max(0, int(body_limit)),
        "retry_hours": retry_store.permanent_retry_hours,
        "wait_days": retry_store.wait_alert_days,
    }


# ─── Render ──────────────────────────────────────────────────────────────────

def render_operator_section(lines: list[str], report: dict, *, sep: str, sub: str) -> None:
    attention = report.get("attention") or []
    waiting = report.get("waiting") or {}
    limit = int(report.get("body_limit") or 0)
    lines.append("PARA REVISAR EN RAFAM — registros que no llegaron a Paxapos")
    lines.append(sep)
    if not attention:
        lines.append("  Ningun registro necesita revision.")
    else:
        lines.append(f"  {len(attention)} registro(s) ({int(report.get('new_today') or 0)} nuevo(s) hoy).")
        lines.append(
            "  Revisar cada uno en RAFAM (numero mal cargado, duplicado, dato faltante...). "
            "Al corregirlo se migra solo:"
        )
        lines.append(
            f"  los 'pendiente' en la proxima corrida y los 'permanent' en su proximo reintento "
            f"(cada {float(report.get('retry_hours') or 0):g} h)."
        )
        lines.append(f'  Para reenviar uno ya: {_CLI} resend --entity <entidad> --key "<registro>"')
        by_entity: dict[str, list[dict]] = {}
        for row in attention:
            by_entity.setdefault(row["entidad"], []).append(row)
        for entity, rows in by_entity.items():
            lines.append("")
            lines.append(f"  [{entity}] — {len(rows)} registro(s)")
            shown = rows if limit == 0 else rows[:limit]
            for row in shown:
                if row["estado"] == "permanent":
                    estado = f"PERMANENT, proximo reintento: {row['proximo_reintento']}"
                elif row["estado"] == "espera vencida":
                    estado = f"en espera hace {row['dias']} dia(s)"
                else:
                    estado = "pendiente (se reintenta en cada corrida)"
                lines.append(f"    · {row['registro']} — {row['que_paso']} — {estado}")
                id_paxapos = f" · ID Paxapos {row['id_paxapos']}" if row.get("id_paxapos") else ""
                lines.append(
                    f"        desde {row['en_cola_desde']} · {row['intentos']} intento(s) · motivo {row['motivo']}"
                    f"{id_paxapos}"
                )
                first = row["error"].splitlines()[0] if row["error"] else ""
                lines.append(f"        error: {first[:300]}")
            if len(rows) > len(shown):
                lines.append(
                    f"    ... y {len(rows) - len(shown)} mas — ver `{_CLI} retry-queue --entity {entity}`"
                )
    if waiting:
        total = sum(waiting.values())
        detail = ", ".join(f"{ent}: {n}" for ent, n in sorted(waiting.items()))
        lines.append("")
        lines.append(
            f"  En espera normal (menos de {float(report.get('wait_days') or 0):g} dia(s), no requieren accion): "
            f"{total} ({detail})"
        )
    lines.append("")

    resolved = report.get("resolved") or []
    lines.append("DESTRABADOS HOY — salieron de la cola")
    lines.append(sub)
    if not resolved:
        lines.append("  Ninguno.")
    else:
        migrated = [r for r in resolved if r.get("how") == RESOLVED_MIGRATED]
        others: dict[str, list[dict]] = {}
        for r in resolved:
            if r.get("how") != RESOLVED_MIGRATED:
                others.setdefault(str(r.get("how") or "?").split(":", 1)[0], []).append(r)
        if migrated:
            lines.append(f"  Se migraron: {len(migrated)}")
            for r in migrated[: (limit or len(migrated))]:
                lines.append(
                    f"    · {describe_retry_key(r['entity'], r['external_id'])} — estaba {r.get('status')} "
                    f"({r.get('reason_code')}/{r.get('reason_detail') or 'sin detalle'}, "
                    f"{r.get('attempts')} intento(s), desde {utc_sql_to_local(r.get('first_seen'))})"
                )
            if limit and len(migrated) > limit:
                lines.append(f"    ... y {len(migrated) - limit} mas")
        labels = {
            "fuera_de_alcance": "Quedaron fuera de alcance (regla de negocio)",
            "sin_envio": "El script ya no los envia (sin cambios o regla de negocio)",
            "descartado": "Descartados a mano (retry-queue --dismiss)",
        }
        for how, rows in sorted(others.items()):
            ejemplos = ", ".join(describe_retry_key(r["entity"], r["external_id"]) for r in rows[:5])
            lines.append(f"  {labels.get(how, how)}: {len(rows)} (ej: {ejemplos}{' ...' if len(rows) > 5 else ''})")
    lines.append("")
