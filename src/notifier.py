"""notifier.py — Envío de notificaciones por email para el pipeline RAFAM.

Soporta SMTP con SSL/TLS (puerto 465) y STARTTLS (puerto 587).
Configuración via variables de entorno con prefijo NOTIFY_*.

Variables de entorno:
    NOTIFY_ENABLED          true/false (default: true si NOTIFY_SMTP_HOST está seteado)
    NOTIFY_SMTP_HOST        Servidor SMTP (ej: neon.gnucleo.net)
    NOTIFY_SMTP_PORT        Puerto SMTP (default: 465)
    NOTIFY_SMTP_USER        Usuario/email de autenticación
    NOTIFY_SMTP_PASSWORD    Contraseña SMTP
    NOTIFY_FROM             Dirección remitente (default: NOTIFY_SMTP_USER)
    NOTIFY_TO               Destinatarios separados por coma
    NOTIFY_SUBJECT_PREFIX   Prefijo del asunto (default: [RAFAM])
    NOTIFY_ALERT_TO         Destinatarios de los mails por registro y por incidente (default: NOTIFY_TO)
"""

from __future__ import annotations

import html
import logging
import os
import smtplib
import socket
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Sequence

from .retry_labels import describe_retry_key
from .utils import days_since_utc_sql, utc_sql_to_local

# Motivos de espera (mismo valor que retry_store.WAIT_REASONS; no se importa
# retry_store para no acoplar el notifier a la cola).
_WAIT_REASONS = frozenset({"dependency_missing"})

logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _is_enabled() -> bool:
    explicit = _env("NOTIFY_ENABLED")
    if explicit:
        return explicit.lower() in {"1", "true", "yes", "on"}
    # Auto-habilitar si hay host SMTP configurado
    return bool(_env("NOTIFY_SMTP_HOST"))


def notifications_enabled() -> bool:
    return _is_enabled()


def _split_recipients(raw: str) -> list[str]:
    return [r.strip() for r in raw.split(",") if r.strip()]


def _build_recipients() -> list[str]:
    raw = _env("NOTIFY_TO")
    if not raw:
        return []
    return _split_recipients(raw)


def send_notification(
    subject: str,
    body: str,
    *,
    is_html: bool = False,
    extra_recipients: Sequence[str] = (),
    recipients: Sequence[str] | None = None,
    html_body: str | None = None,
) -> bool:
    """Envía una notificación por email.

    Args:
        subject: Asunto del email.
        body: Cuerpo del mensaje (texto plano o HTML según is_html).
        is_html: Si True, envía como text/html; si False, como text/plain.
        extra_recipients: Destinatarios adicionales a los configurados en NOTIFY_TO.
        recipients: Si se pasa, reemplaza a NOTIFY_TO (ej. NOTIFY_ALERT_TO).
        html_body: Version HTML del mismo mail (p.ej. con una tabla). Va como
            alternativa de ``body``: el cliente de correo muestra la HTML y el
            texto queda para los que no la muestran.

    Returns:
        True si el envío fue exitoso, False en caso contrario.
    """
    if not _is_enabled():
        logger.debug("Notificaciones deshabilitadas (NOTIFY_ENABLED=false o sin NOTIFY_SMTP_HOST)")
        return False

    smtp_host = _env("NOTIFY_SMTP_HOST")
    if not smtp_host:
        logger.warning("notifier: NOTIFY_SMTP_HOST no configurado — no se puede enviar email")
        return False

    try:
        smtp_port = int(_env("NOTIFY_SMTP_PORT", "465"))
    except (TypeError, ValueError):
        logger.warning("notifier: NOTIFY_SMTP_PORT invalido; usando 465")
        smtp_port = 465
    smtp_user = _env("NOTIFY_SMTP_USER")
    smtp_password = _env("NOTIFY_SMTP_PASSWORD")
    from_addr = _env("NOTIFY_FROM") or smtp_user
    subject_prefix = _env("NOTIFY_SUBJECT_PREFIX", "[RAFAM]")

    base_recipients = list(recipients) if recipients else _build_recipients()
    recipients = base_recipients + list(extra_recipients)
    if not recipients:
        logger.warning("notifier: NOTIFY_TO no configurado — no hay destinatarios")
        return False

    if not from_addr:
        logger.warning("notifier: NOTIFY_FROM y NOTIFY_SMTP_USER no configurados")
        return False

    full_subject = f"{subject_prefix} {subject}".strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = full_subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)

    mime_type = "html" if is_html else "plain"
    msg.attach(MIMEText(body, mime_type, "utf-8"))
    if html_body:
        # En multipart/alternative la ultima parte es la preferida.
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        timeout = int(_env("NOTIFY_SMTP_TIMEOUT", "15"))
        # Contexto SSL explicito: el default de smtplib no valida certificado
        # ni hostname, dejando la password SMTP expuesta a un MITM en login().
        tls_context = ssl.create_default_context()
        # Puerto 465 = SSL/TLS directo; otros puertos = STARTTLS
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout, context=tls_context) as server:
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, recipients, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as server:
                server.ehlo()
                server.starttls(context=tls_context)
                server.ehlo()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, recipients, msg.as_string())

        logger.info(
            "notifier: email enviado a %s — asunto: %s",
            ", ".join(recipients),
            full_subject,
        )
        return True

    except smtplib.SMTPAuthenticationError as exc:
        logger.error("notifier: error de autenticación SMTP: %s", exc)
    except smtplib.SMTPException as exc:
        logger.error("notifier: error SMTP: %s", exc)
    except socket.timeout:
        logger.error("notifier: timeout conectando a %s:%s", smtp_host, smtp_port)
    except OSError as exc:
        logger.error("notifier: error de red: %s", exc)

    return False


def notify_integrity_result(
    summary_lines: list[str],
    warnings: list[str],
    *,
    dry_run: bool,
    entity: str | None,
    total_actualizados: int,
    total_anulados: int,
    total_errores: int,
) -> bool:
    """Notifica el resultado de check_integrity por email.

    Solo envía email si hay algo que reportar (actualizados, anulados o errores).
    En dry-run siempre notifica si hay anomalías (para alertar sin aplicar cambios).

    Returns:
        True si se envió el email, False si no había nada relevante o hubo error.
    """
    has_issues = total_actualizados > 0 or total_anulados > 0 or total_errores > 0

    if not has_issues:
        logger.debug("notifier: sin anomalías — no se envía email")
        return False

    mode_label = "DRY-RUN" if dry_run else "APPLY"
    entity_label = entity or "todas las entidades"

    subject = f"Integridad RAFAM [{mode_label}] — {entity_label}"
    if total_errores > 0:
        subject = f"⚠ ERROR {subject}"
    elif total_actualizados > 0 or total_anulados > 0:
        subject = f"⚡ {subject}"

    # Construir cuerpo del mail
    lines: list[str] = [
        f"Resultado de check_integrity — Modo: {mode_label}",
        f"Entidad: {entity_label}",
        "",
        "─" * 60,
        "",
    ]
    lines.extend(summary_lines)

    if warnings:
        lines += [
            "",
            "─" * 60,
            "DETALLE DE ERRORES/ANOMALÍAS:",
            "",
        ]
        for w in warnings:
            if "\n" in w or "===" in w:
                lines.append(w)
            else:
                lines.append(f"  • {w}")

    body = "\n".join(lines)
    return send_notification(subject, body)


def _retry_total(value) -> int:
    """Normaliza el conteo de reintentos a un entero.

    ``retry_store.counts_by_entity`` devuelve ``{entity: {status: count}}``,
    pero versiones/orígenes antiguos podían usar ``{entity: count}``. Se
    soportan ambas formas.
    """
    if isinstance(value, dict):
        return sum(v for v in value.values() if isinstance(v, int))
    if isinstance(value, int):
        return value
    return 0


def _parse_hhmmss(value: str) -> float:
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


def _emit_error_block(lines: list[str], metrics: dict, indent: str = "  ") -> None:
    """Agrega al reporte el bloque de diagnóstico de un fallo de entidad.

    Incluye motivo, clase de excepción, ubicación (archivo/línea/función),
    respuesta cruda del migrator y traceback completo, cada uno multilinea.
    """
    lines.append(f"{indent}DIAGNÓSTICO DE FALLO:")
    if metrics.get("error_kind") == "backend_infra":
        lines.append(
            f"{indent}  ATENCIÓN        : fallo de INFRAESTRUCTURA del servidor Paxapos (SQL/PHP). "
            "Los datos de RAFAM no son el problema; las filas se releen en la próxima corrida."
        )
    if metrics.get("error_msg"):
        lines.append(f"{indent}  Motivo          : {metrics['error_msg']}")
    if metrics.get("error_type"):
        lines.append(f"{indent}  Clase excepción : {metrics['error_type']}")
    if metrics.get("error_location"):
        lines.append(f"{indent}  Ubicación       : {metrics['error_location']}")
    if metrics.get("migrator_error"):
        lines.append(f"{indent}  Error del migrator:")
        for l in str(metrics["migrator_error"]).splitlines():
            lines.append(f"{indent}    {l}")
    if metrics.get("error_trace"):
        lines.append(f"{indent}  Traceback / contexto completo:")
        for l in str(metrics["error_trace"]).splitlines():
            lines.append(f"{indent}    {l}")


def notify_run_report(
    summary_data: dict,
    entity_metrics: list[dict],
    *,
    dry_run: bool = False,
) -> bool:
    """Envía un reporte de diagnóstico DETALLADO en texto plano al finalizar una corrida.

    Pensado para el equipo de soporte/desarrollo: prioriza información útil
    (qué falló, por qué, cómo, archivo, hora, tiempos y velocidad en minutos,
    error devuelto por el migrator y traceback) por sobre la estética.
    """
    if not _is_enabled():
        return False

    mode_label = "DRY-RUN" if dry_run else "APPLY"
    success = summary_data.get("success", False)
    status_label = summary_data.get("status_label") or ("OK" if success else "CON ERRORES")
    if any(
        int(m.get("migrator_errors", 0) or 0) > 0
        or int(m.get("source_invalid", 0) or 0) > 0
        for m in entity_metrics
    ):
        status_label = "CON ERRORES"
    subject = summary_data.get("subject") or f"Reporte Sincronización RAFAM [{mode_label}] — {status_label}"

    SEP = "=" * 70
    SUB = "-" * 70

    # Tiempo total de la corrida (para métricas en minutos)
    duration_fmt = summary_data.get("duration_formatted", "00:00:00")
    run_secs = _parse_hhmmss(duration_fmt)
    run_mins = run_secs / 60.0

    # Agregados globales
    total_entities = len(entity_metrics)
    ok_entities = sum(1 for m in entity_metrics if m.get("success"))
    fail_entities = total_entities - ok_entities
    total_migrator_sent = sum(m.get("migrator_sent", 0) for m in entity_metrics)
    total_migrator_saved = sum(m.get("migrator_saved", 0) for m in entity_metrics)
    total_migrator_errors = sum(m.get("migrator_errors", 0) for m in entity_metrics)
    total_created = sum(m.get("migrator_created", 0) for m in entity_metrics)
    total_updated = sum(m.get("migrator_updated", 0) for m in entity_metrics)
    total_replaced = sum(m.get("migrator_replaced", 0) for m in entity_metrics)
    total_deleted = sum(m.get("migrator_deleted", 0) for m in entity_metrics)
    total_skipped = sum(m.get("migrator_skipped", 0) for m in entity_metrics)
    total_unclassified = sum(m.get("migrator_unclassified", 0) for m in entity_metrics)
    total_invalid = sum(m.get("source_invalid", 0) for m in entity_metrics)
    total_batches_ok = sum(m.get("batches_ok", 0) for m in entity_metrics)
    total_batches_failed = sum(m.get("batches_failed", 0) for m in entity_metrics)
    total_batches_recovered = sum(int(m.get("batches_recovered", 0) or 0) for m in entity_metrics)
    total_records_isolated = sum(int(m.get("records_isolated", 0) or 0) for m in entity_metrics)
    total_bisect_requests = sum(int(m.get("bisect_requests", 0) or 0) for m in entity_metrics)
    runs_count = summary_data.get("runs_count")

    lines: list[str] = []
    lines.append(SEP)
    lines.append("REPORTE DE SINCRONIZACIÓN RAFAM → PAXAPOS")
    lines.append(SEP)
    lines.append(f"Estado global : {status_label}")
    lines.append(f"Modo          : {mode_label}")
    lines.append(f"Servidor      : {summary_data.get('hostname', 'Desconocido')}")
    lines.append(f"Inicio        : {summary_data.get('start_time', '—')}")
    lines.append(f"Fin           : {summary_data.get('end_time', '—')}")
    lines.append(f"Duración total: {duration_fmt}   ({run_mins:.2f} min / {run_secs:.0f} s)")
    lines.append("")

    # Lo primero que tiene que ver el operador: que registros no llegaron.
    operator = summary_data.get("operator")
    if operator:
        from .operator_report import render_operator_section

        render_operator_section(lines, operator, sep=SEP, sub=SUB)

    lines.append("RESUMEN GLOBAL")
    lines.append(SUB)
    if runs_count is not None:
        lines.append(f"  • Corridas agregadas    : {runs_count}")
    lines.append(f"  • Entidades procesadas   : {total_entities}  (OK: {ok_entities}, con error: {fail_entities})")
    lines.append(f"  • Items enviados Paxapos : {total_migrator_sent:,}")
    lines.append(f"  • Confirmados por Paxapos: {total_migrator_saved:,}")
    lines.append(f"      Altas nuevas         : {total_created:,}")
    lines.append(f"      Actualizaciones      : {total_updated:,}")
    lines.append(f"      Reemplazos           : {total_replaced:,}")
    lines.append(f"      Bajas                : {total_deleted:,}")
    lines.append(f"      Omitidos/ya existentes: {total_skipped:,}")
    lines.append(f"      Sin modo clasificable: {total_unclassified:,}")
    lines.append(f"  • Filas inválidas        : {total_invalid:,}")
    lines.append(f"  • Rechazados por Paxapos : {total_migrator_errors:,}")
    lines.append(f"  • Batches OK / con error : {total_batches_ok} / {total_batches_failed}")
    if total_batches_recovered or total_records_isolated:
        lines.append(
            f"  • Batches caidos recuperados: {total_batches_recovered:,}  "
            f"({total_records_isolated:,} registro(s) aislado(s) en la cola, "
            f"{total_bisect_requests:,} request(s) extra)"
        )
    if summary_data.get("record_alerts_sent") is not None:
        lines.append(
            f"  • Alertas por registro enviadas: {int(summary_data.get('record_alerts_sent') or 0):,}"
            "  (un mail por cada registro rechazado u omitido por datos invalidos)"
        )
    if summary_data.get("incident_alerts_sent") is not None:
        lines.append(
            f"  • Avisos de incidente enviados: {int(summary_data.get('incident_alerts_sent') or 0):,}"
            "  (entidad sin sincronizar: Paxapos caido o batch sin aislar)"
        )
    if operator:
        lines.append(
            f"  • Para revisar en RAFAM   : {len(operator.get('attention') or []):,}"
            f"  ({int(operator.get('new_today') or 0):,} nuevo(s) hoy)"
        )
    total_permanent_retried = sum(int(m.get("permanent_retried", 0) or 0) for m in entity_metrics)
    if total_permanent_retried:
        lines.append(
            f"  • 'permanent' reintentados solos: {total_permanent_retried:,}"
            "  (intentos automaticos de registros trabados)"
        )
    lines.append("")

    # Error general de la corrida
    if not success and summary_data.get("error_msg"):
        lines.append("ERROR GENERAL DE LA CORRIDA")
        lines.append(SUB)
        for l in str(summary_data["error_msg"]).splitlines():
            lines.append(f"  {l}")
        lines.append("")

    # Detalle por entidad
    lines.append("DETALLE POR ENTIDAD")
    lines.append(SEP)
    for m in entity_metrics:
        ent = m.get("entity", "?")
        ent_ok = (
            m.get("success", False)
            and int(m.get("migrator_errors", 0) or 0) == 0
            and int(m.get("source_invalid", 0) or 0) == 0
        )
        ent_status = "OK" if ent_ok else "ERROR"
        # En el resumen diario duration_secs es la suma de todas las corridas
        # del dia: se muestra el promedio de UNA corrida de la entidad.
        entity_runs = max(1, int(m.get("runs", 1) or 1))
        duration = (m.get("duration_secs", 0.0) or 0.0) / entity_runs
        dur_min = duration / 60.0
        migrator_sent = m.get("migrator_sent", 0)
        migrator_saved = m.get("migrator_saved", 0)
        migrator_errors = m.get("migrator_errors", 0)

        lines.append(f"[{ent}]  ({m.get('mode', '—')})  →  {ent_status}")
        lines.append(f"  Items enviados Paxapos  : {migrator_sent:,}")
        lines.append(f"  Confirmados por Paxapos : {migrator_saved:,}")
        lines.append(f"    Altas / updates       : {m.get('migrator_created', 0):,} / {m.get('migrator_updated', 0):,}")
        lines.append(f"    Reemplazos / bajas    : {m.get('migrator_replaced', 0):,} / {m.get('migrator_deleted', 0):,}")
        lines.append(f"    Omitidos / sin modo   : {m.get('migrator_skipped', 0):,} / {m.get('migrator_unclassified', 0):,}")
        lines.append(f"  Filas inválidas         : {m.get('source_invalid', 0):,}")
        lines.append(f"  Rechazados por Paxapos  : {migrator_errors:,}")
        lines.append(f"  Batches OK / con error  : {m.get('batches_ok', 0)} / {m.get('batches_failed', 0)}")
        if int(m.get("batches_recovered", 0) or 0) or int(m.get("records_isolated", 0) or 0):
            lines.append(
                f"  Batches recuperados     : {int(m.get('batches_recovered', 0) or 0):,}  "
                f"(registros aislados: {int(m.get('records_isolated', 0) or 0):,}, "
                f"requests extra: {int(m.get('bisect_requests', 0) or 0):,})"
            )
        ledger_new = m.get("ledger_new") or {}
        if any(ledger_new.values()):
            lines.append(
                "  Sin ID de Paxapos (nuevos a la cola): "
                f"{int(ledger_new.get('queued_fallo', 0) or 0):,} fallo(s), "
                f"{int(ledger_new.get('queued_espera', 0) or 0):,} espera(s), "
                f"{int(ledger_new.get('unexplained', 0) or 0):,} sin motivo"
            )
        if int(m.get("permanent_retried", 0) or 0):
            lines.append(f"  'permanent' reintentados: {int(m.get('permanent_retried', 0) or 0):,}")
        if entity_runs > 1:
            lines.append(
                f"  Duración prom. corrida  : {duration:.2f} s   ({dur_min:.2f} min, promedio de {entity_runs} corridas)"
            )
        else:
            lines.append(f"  Duración                : {duration:.2f} s   ({dur_min:.2f} min)")
        if not ent_ok:
            lines.append(f"  {SUB}")
            _emit_error_block(lines, m, indent="  ")
        lines.append("")

    # Fuera de alcance: foto de la ultima corrida (sumar 144 corridas no dice nada).
    fuera_rows = [
        (m.get("entity", "?"), (m.get("ledger_last") or {}).get("fuera_detail") or {})
        for m in entity_metrics
    ]
    if any(detail for _, detail in fuera_rows):
        lines.append("NO SE MIGRAN POR REGLA (fuera de alcance, ultima corrida)")
        lines.append(SUB)
        for ent, detail in fuera_rows:
            for info in sorted(detail.values(), key=lambda d: -int(d.get("count", 0) or 0)):
                ejemplos = ", ".join(info.get("examples") or [])
                lines.append(
                    f"  • [{ent}] {info.get('label', '?')}: {int(info.get('count', 0) or 0):,}"
                    + (f"  (ej: {ejemplos})" if ejemplos else "")
                )
        lines.append("")

    # Cola de reintentos
    lines.append("COLA DE REINTENTOS (errores F1 pendientes)")
    lines.append(SEP)
    start_retries = summary_data.get("retry_counts_start") or {}
    end_retries = summary_data.get("retry_counts_end") or {}
    all_ents = sorted(set(start_retries) | set(end_retries))
    if all_ents:
        for ent in all_ents:
            s = _retry_total(start_retries.get(ent, 0))
            e = _retry_total(end_retries.get(ent, 0))
            diff = e - s
            diff_str = f"{diff:+d}" if diff != 0 else "sin cambios"
            lines.append(f"  • {ent:<24} inicio: {s:>4}  →  fin: {e:>4}   ({diff_str})")
    else:
        lines.append("  Sin registros pendientes de reintento.")
    retry_summary = summary_data.get("retry_summary_end") or []
    if retry_summary:
        lines.append("")
        lines.append("  Agrupado por causa al cierre:")
        for row in retry_summary:
            detail = row.get("reason_detail") or "legacy_unspecified"
            lines.append(
                f"    - {row.get('entity', '?')} | {row.get('status', '?')} | "
                f"{row.get('reason_code', '?')}/{detail}: {int(row.get('count', 0) or 0):,} "
                f"(desde {utc_sql_to_local(row.get('oldest_first_seen'))}, último intento "
                f"{utc_sql_to_local(row.get('last_attempt'))}, máx. intentos {int(row.get('max_attempts', 0) or 0)})"
            )
    retry_detail = summary_data.get("retry_detail_end") or {}
    if retry_detail:
        lines.append("")
        lines.append("  Detalle individual (mas viejos primero — quien necesita atencion):")
        for ent in sorted(retry_detail):
            info = retry_detail[ent]
            rows = info.get("items") or []
            total = int(info.get("total", len(rows)) or 0)
            if not rows:
                continue
            lines.append(f"    [{ent}] — {total} registro(s) en cola")
            for row in rows:
                detail = row.get("reason_detail") or "legacy_unspecified"
                lines.append(
                    f"      · {row.get('label', '?')} — {row.get('status', '?')} "
                    f"({row.get('reason_code', '?')}/{detail}, intento {row.get('attempts', 0)}, "
                    f"desde {utc_sql_to_local(row.get('first_seen'))}, "
                    f"ultimo intento {utc_sql_to_local(row.get('last_attempt'))})"
                )
                error_message = row.get("error_message")
                if error_message:
                    lines.append(f"          error: {str(error_message)[:300]}")
            if total > len(rows):
                lines.append(
                    f"      ... y {total - len(rows)} mas — ver "
                    f"`main.py retry-queue --entity {ent}` (detalle completo) o el README "
                    "seccion 'Fiabilidad: cola de reintentos' (como forzar el reenvio)."
                )
        lines.append("")
    if retry_summary:
        lines.append("  Inspección: .venv/bin/python main.py retry-queue --entity <entidad>")
    lines.append("")
    lines.append(SEP)
    lines.append("Email generado automáticamente por el pipeline de sincronización RAFAM (Madariaga).")

    body = "\n".join(lines)
    return send_notification(subject, body, is_html=False)


# ─── Alertas por registro (un mail por registro que no llego a Paxapos) ──────

_REASON_HEADLINE = {
    "backend_rejected": "Paxapos lo rechazo",
    "validation_client": "no se envio (datos invalidos)",
    "batch_failed": "fallo el envio (aislado de un batch caido)",
    "dependency_missing": "sigue sin migrarse (espera vencida)",
}

# Contexto extra en el mail por registro, segun el motivo.
_REASON_NOTE = {
    "batch_failed": (
        "El batch donde iba fallo entero; se partio hasta encontrar que este registro falla\n"
        "SOLO (los demas se enviaron bien). Suele ser un dato que hace fallar a Paxapos:\n"
        "revisar el log de Paxapos a la hora del ultimo intento."
    ),
    "dependency_missing": (
        "El registro no tiene errores propios, pero depende de otro que todavia no esta en\n"
        "Paxapos (o de un estado de RAFAM que no cambia: OC sin confirmar, OP sin imputacion).\n"
        "Una espera normal se resuelve en horas; esta ya supero el plazo. Revisar en RAFAM\n"
        "el motivo de arriba. Cuando se resuelva, se migra solo en la proxima corrida."
    ),
}


def _wait_days_label(first_seen) -> str:
    days = days_since_utc_sql(first_seen)
    if days is None:
        return "varios dias"
    return f"{int(days)} dia(s)" if days >= 1 else "menos de 1 dia"


def _paxapos_id_text(item) -> str:
    paxapos_id = getattr(item, "paxapos_id", None)
    if paxapos_id:
        return f"{paxapos_id} (ya existe en Paxapos: fallo la actualizacion)"
    return "— (todavia no existe en Paxapos)"


def describe_queue_state(item, *, max_attempts: int) -> str:
    """Estado de la fila en la cola en palabras (mail por registro y lista del operador)."""
    if item.reason_code in _WAIT_REASONS:
        return (
            f"en espera hace {_wait_days_label(item.first_seen)} — se reintenta solo en cada "
            "corrida y se migra apenas se resuelva lo que espera"
        )
    if item.status == "permanent":
        base = f"PERMANENT — agoto {item.attempts} intento(s) seguidos"
        if not getattr(item, "auto_retry", 1):
            return f"{base}; NO se reintenta solo (rechazo terminal): reenviar a mano si corresponde"
        next_retry = getattr(item, "next_retry_after", None)
        if next_retry:
            return (
                f"{base}; ya no se reintenta en cada corrida pero se vuelve a intentar solo: "
                f"proximo intento {utc_sql_to_local(next_retry)} (hora local)"
            )
        return f"{base}; no se reintenta solo (RAFAM_PERMANENT_RETRY_HOURS=0): reenviar a mano"
    return f"pendiente — se reintenta solo en cada corrida (intento {item.attempts} de {max_attempts})"

_CLI = ".venv/bin/python main.py"


def _alert_recipients() -> list[str] | None:
    raw = _env("NOTIFY_ALERT_TO")
    return _split_recipients(raw) if raw else None


def notify_record_failure(item, *, max_attempts: int) -> bool:
    """Mail SOLO de este registro (rechazado por Paxapos, omitido por datos
    invalidos o en espera hace mas de RAFAM_WAIT_ALERT_DAYS dias).

    ``item`` es un `retry_store.RetryItem`. Se manda al entrar a la cola, otra
    vez si pasa a 'permanent', y una vez cuando una espera se vence (ver
    RetryStore.pending_alerts).
    """
    label = describe_retry_key(item.entity, item.external_id)
    headline = _REASON_HEADLINE.get(item.reason_code, item.reason_code)
    permanent = item.status == "permanent"
    if item.reason_code in _WAIT_REASONS:
        subject = f"{label}: hace {_wait_days_label(item.first_seen)} que no se puede migrar (espera vencida)"
    elif permanent:
        subject = f"{label}: PASO A PERMANENT ({headline})"
    else:
        subject = f"{label}: {headline}"
    estado = describe_queue_state(item, max_attempts=max_attempts)

    SEP = "=" * 70
    SUB = "-" * 70
    external_id = str(item.external_id).replace("'", "'\\''")
    lines = [
        SEP,
        "REGISTRO QUE NO LLEGO A PAXAPOS",
        SEP,
        f"Registro       : {label}",
        f"Clave RAFAM    : {item.external_id}",
        f"ID Paxapos     : {_paxapos_id_text(item)}",
        f"Entidad        : {item.entity}",
        f"Que paso       : {headline}",
        f"Motivo         : {item.reason_code} / {item.reason_detail or 'sin detalle'}",
        f"Estado         : {estado}",
        f"En la cola desde: {utc_sql_to_local(item.first_seen)} (hora local)",
        f"Ultimo intento : {utc_sql_to_local(item.last_attempt)} (hora local)",
        f"Servidor       : {socket.gethostname()}",
        "",
        "ERROR",
        SUB,
    ]
    lines.extend(f"  {line}" for line in str(item.error_message or "sin mensaje").splitlines())
    note = _REASON_NOTE.get(item.reason_code)
    if note:
        lines.append("")
        lines.extend(f"  {line}" for line in note.splitlines())
    if item.reason_code in _WAIT_REASONS:
        first_step = "  1. Revisar en RAFAM lo que espera este registro (ver ERROR) y destrabarlo."
        second_step = "  2. Se migra solo en la proxima corrida; para no esperar (probar con --dry-run):"
    else:
        first_step = "  1. Corregir la causa (el dato en RAFAM o la configuracion en Paxapos)."
        second_step = "  2. Se reintenta solo; para reenviarlo ya (probar antes agregando --dry-run):"
    lines += [
        "",
        "QUE HACER",
        SUB,
        first_step,
        second_step,
        f'       {_CLI} resend --entity {item.entity} --key "{label}"',
        "",
        "  Ver el detalle en la cola:",
        f"       {_CLI} retry-queue --entity {item.entity} --external-id '{external_id}'",
        "  Si no corresponde migrarlo:",
        f"       {_CLI} retry-queue --dismiss --entity {item.entity} "
        f"--external-id '{external_id}' --note 'motivo'",
        "",
        SEP,
        "Se avisa una vez por registro (y otra si pasa a permanent). Mientras no se migre,",
        "figura todos los dias en la lista PARA REVISAR del resumen diario.",
    ]
    return send_notification(subject, "\n".join(lines), recipients=_alert_recipients())


def _short_queue_state(item, *, max_attempts: int) -> str:
    """Estado en pocas palabras (columna Estado del mail agrupado)."""
    if item.reason_code in _WAIT_REASONS:
        return f"en espera hace {_wait_days_label(item.first_seen)}"
    if item.status == "permanent":
        if not getattr(item, "auto_retry", 1):
            return "PERMANENT, sin reintento automatico (rechazo terminal)"
        next_retry = getattr(item, "next_retry_after", None)
        if next_retry:
            return f"PERMANENT, proximo intento {utc_sql_to_local(next_retry)}"
        return "PERMANENT, reenviar a mano"
    return f"pendiente, se reintenta cada corrida (intento {item.attempts} de {max_attempts})"


def _record_row(item, *, max_attempts: int) -> dict:
    label = describe_retry_key(item.entity, item.external_id)
    return {
        "registro": label,
        "entidad": item.entity,
        "id_paxapos": getattr(item, "paxapos_id", None) or "—",
        "que_paso": _REASON_HEADLINE.get(item.reason_code, item.reason_code),
        "motivo": f"{item.reason_code}/{item.reason_detail or 'sin detalle'}",
        "error": str(item.error_message or "sin mensaje"),
        "estado": _short_queue_state(item, max_attempts=max_attempts),
        "desde": utc_sql_to_local(item.first_seen),
        "reenviar": f'{_CLI} resend --entity {item.entity} --key "{label}"',
    }


# (titulo, clave de _record_row) en el orden de la tabla.
_TABLE_COLUMNS = (
    ("Registro RAFAM", "registro"),
    ("Entidad", "entidad"),
    ("ID Paxapos", "id_paxapos"),
    ("Que paso", "que_paso"),
    ("Error", "error"),
    ("Estado", "estado"),
    ("En la cola desde", "desde"),
    ("Reenviar", "reenviar"),
)
_ERROR_MAX_CHARS = 1000
_DEFAULT_MAX_ROWS = 500


def _record_alert_max_rows() -> int:
    raw = _env("NOTIFY_RECORD_ALERT_MAX_ROWS", str(_DEFAULT_MAX_ROWS))
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("NOTIFY_RECORD_ALERT_MAX_ROWS=%r no es valido; se usa %d", raw, _DEFAULT_MAX_ROWS)
        return _DEFAULT_MAX_ROWS


def notify_record_failures_table(items, *, max_attempts: int) -> bool:
    """UN mail con todos los registros que no llegaron a Paxapos en la corrida.

    Si en una corrida falla mas de un registro, en vez de un mail por cada uno
    va este: una tabla (HTML, con version en texto) con una fila por registro
    y una columna por dato. Mas de NOTIFY_RECORD_ALERT_MAX_ROWS filas (default
    500; 0 = sin tope) se resumen por causa al pie, en el mismo mail.
    """
    items = list(items)
    cap = _record_alert_max_rows()
    shown = items if cap == 0 else items[:cap]
    rest = items[len(shown):]
    rows = [_record_row(item, max_attempts=max_attempts) for item in shown]

    by_entity: dict[str, int] = {}
    for item in items:
        by_entity[item.entity] = by_entity.get(item.entity, 0) + 1
    entities_txt = ", ".join(f"{ent}: {n}" for ent, n in sorted(by_entity.items()))
    subject = f"{len(items)} registros no llegaron a Paxapos ({entities_txt})"

    rest_by_cause: dict[tuple[str, str], int] = {}
    for item in rest:
        cause = (item.entity, f"{item.reason_code}/{item.reason_detail or 'sin detalle'}")
        rest_by_cause[cause] = rest_by_cause.get(cause, 0) + 1
    rest_lines = [
        f"{count} x {entity} — {cause}"
        for (entity, cause), count in sorted(rest_by_cause.items(), key=lambda kv: -kv[1])
    ]
    intro = (
        f"En esta corrida {len(items)} registro(s) no llegaron a Paxapos ({entities_txt}). "
        "Se reintentan solos; revisar en RAFAM el dato de cada uno."
    )
    footer = [
        "Ver el detalle en la cola: " + f"{_CLI} retry-queue --entity <entidad>",
        "Si no corresponde migrar uno: "
        + f"{_CLI} retry-queue --dismiss --entity <entidad> --external-id '<clave>' --note 'motivo'",
        "Se avisa una vez por registro (y otra si pasa a permanent). Mientras no se migre, figura "
        "todos los dias en la lista PARA REVISAR del resumen diario.",
    ]

    # Texto (para clientes que no muestran HTML).
    SEP = "=" * 70
    text = [SEP, f"{len(items)} REGISTROS NO LLEGARON A PAXAPOS", SEP, intro, ""]
    for row in rows:
        text.append(
            f"· {row['registro']} | {row['entidad']} | ID Paxapos {row['id_paxapos']} | "
            f"{row['que_paso']} | {row['estado']} | desde {row['desde']}"
        )
        text.extend(f"    error: {line}" for line in row["error"][:_ERROR_MAX_CHARS].splitlines())
        text.append(f"    reenviar: {row['reenviar']}")
    if rest_lines:
        text += ["", f"... y {len(rest)} mas (NOTIFY_RECORD_ALERT_MAX_ROWS), por causa:"]
        text += [f"  {line}" for line in rest_lines]
    text += [""] + footer

    # HTML: una fila por registro, una columna por dato.
    cell = 'style="border:1px solid #c8c8c8;padding:4px 8px;vertical-align:top;text-align:left"'
    head = "".join(
        f'<th {cell[:-1]};background:#eeeeee">{html.escape(title)}</th>' for title, _key in _TABLE_COLUMNS
    )
    body_rows = []
    for row in rows:
        cells = []
        for _title, key in _TABLE_COLUMNS:
            value = row[key]
            if key == "error":
                value = value[:_ERROR_MAX_CHARS]
                cells.append(f'<td {cell[:-1]};white-space:pre-wrap">{html.escape(value)}</td>')
            elif key == "reenviar":
                cells.append(f"<td {cell}><code>{html.escape(value)}</code></td>")
            else:
                cells.append(f"<td {cell}>{html.escape(value)}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    rest_html = ""
    if rest_lines:
        rest_html = (
            f"<p>... y {len(rest)} mas (NOTIFY_RECORD_ALERT_MAX_ROWS), por causa:</p><ul>"
            + "".join(f"<li>{html.escape(line)}</li>" for line in rest_lines)
            + "</ul>"
        )
    html_body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px">'
        f"<h3>{len(items)} registros no llegaron a Paxapos</h3>"
        f"<p>{html.escape(intro)}</p>"
        '<table style="border-collapse:collapse">'
        f"<tr>{head}</tr>{''.join(body_rows)}</table>"
        f"{rest_html}"
        + "".join(f"<p>{html.escape(line)}</p>" for line in footer)
        + "</div>"
    )
    return send_notification(
        subject, "\n".join(text), html_body=html_body, recipients=_alert_recipients(),
    )


# ─── Alertas por incidente (una entidad entera no se sincroniza) ─────────────

_INCIDENT_HEADLINE = {
    "backend": "Paxapos (o la red) falla: no son los datos",
    "batch": "un batch se cae y no se pudo aislar el registro",
    "error": "falla antes de enviar a Paxapos",
}

_INCIDENT_WHAT_TO_DO = {
    "backend": [
        "1. Revisar que Paxapos responda (y su log a esa hora).",
        "2. En RAFAM no hay nada que corregir: cuando Paxapos vuelva, la proxima corrida",
        "   reenvia sola lo atrasado. Los registros NO gastan intentos por esto.",
    ],
    "batch": [
        "1. Ver en el log de la corrida el batch que falla (buscar 'FALLO').",
        "2. Probar de a uno, con --dry-run, los registros que quedaron sin aislar (si figuran arriba).",
        "3. Si es un dato puntual, corregirlo en RAFAM o descartarlo; el batch se destraba solo.",
    ],
    "error": [
        "1. Ver el log de la corrida: la entidad no llego a enviar (conexion a RAFAM,",
        "   estado local en state/, configuracion).",
    ],
}


def _incident_label(entity: str) -> str:
    return "La corrida" if entity == "corrida" else entity


def notify_incident(entity: str, incident: dict) -> bool:
    """Mail al abrir un incidente (ver src/incident_alerts.py). Uno por incidente."""
    kind = str(incident.get("kind") or "error")
    headline = _INCIDENT_HEADLINE.get(kind, kind)
    since = utc_sql_to_local(incident.get("since"))
    label = _incident_label(entity)
    subject = f"{label}: NO SE ESTA SINCRONIZANDO — {headline}"

    SEP = "=" * 70
    SUB = "-" * 70
    lines = [
        SEP,
        f"{label.upper()} NO SE ESTA SINCRONIZANDO CON PAXAPOS",
        SEP,
        f"Entidad        : {entity}",
        f"Que pasa       : {headline}",
        f"Desde          : {since} (hora local)",
        f"Corridas       : {int(incident.get('runs') or 0)} seguida(s) con el mismo problema",
        f"Servidor       : {socket.gethostname()}",
        "",
        "ULTIMO ERROR",
        SUB,
    ]
    lines.extend(f"  {line}" for line in str(incident.get("detail") or "sin detalle").splitlines()[:40])
    keys = incident.get("keys") or []
    if keys:
        lines += ["", "REGISTROS DEL BATCH QUE QUEDARON SIN AISLAR", SUB]
        for key_label in keys:
            lines.append(f'  {_CLI} resend --entity {entity} --key "{key_label}" --dry-run')
    lines += [
        "",
        "QUE SIGNIFICA",
        SUB,
        "  No se pierde nada: el cursor de la entidad queda congelado y las filas se",
        "  vuelven a leer en cada corrida hasta que pasen.",
        "",
        "QUE HACER",
        SUB,
    ]
    lines.extend(f"  {line}" for line in _INCIDENT_WHAT_TO_DO.get(kind, _INCIDENT_WHAT_TO_DO["error"]))
    if entity != "corrida":
        lines += ["", "  Forzar una corrida ahora:", f"       {_CLI} run --entity {entity}"]
    lines += [
        "",
        SEP,
        "Se avisa una vez por incidente; cuando se normalice llega otro mail.",
    ]
    return send_notification(subject, "\n".join(lines), recipients=_alert_recipients())


def notify_incident_resolved(entity: str, incident: dict, *, resolved_at: str) -> bool:
    """Mail al cerrarse un incidente que ya se habia avisado."""
    kind = str(incident.get("kind") or "error")
    label = _incident_label(entity)
    since = utc_sql_to_local(incident.get("since"))
    subject = f"{label}: normalizado (con fallas desde {since})"
    SEP = "=" * 70
    lines = [
        SEP,
        f"{label.upper()} VOLVIO A SINCRONIZAR",
        SEP,
        f"Entidad        : {entity}",
        f"Problema       : {_INCIDENT_HEADLINE.get(kind, kind)}",
        f"Desde          : {since} (hora local)",
        f"Hasta          : {utc_sql_to_local(resolved_at)} (hora local)",
        f"Corridas       : {int(incident.get('runs') or 0)} con fallas",
        "",
        "La ultima corrida termino sin batches caidos: lo atrasado ya se envio.",
        "Si quedo algun registro rechazado, llega (o llego) su propio mail.",
        SEP,
    ]
    return send_notification(subject, "\n".join(lines), recipients=_alert_recipients())
