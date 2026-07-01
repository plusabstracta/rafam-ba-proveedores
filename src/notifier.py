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
"""

from __future__ import annotations

import logging
import os
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Sequence

logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _is_enabled() -> bool:
    explicit = _env("NOTIFY_ENABLED")
    if explicit:
        return explicit.lower() in {"1", "true", "yes", "on"}
    # Auto-habilitar si hay host SMTP configurado
    return bool(_env("NOTIFY_SMTP_HOST"))


def _build_recipients() -> list[str]:
    raw = _env("NOTIFY_TO")
    if not raw:
        return []
    return [r.strip() for r in raw.split(",") if r.strip()]


def send_notification(
    subject: str,
    body: str,
    *,
    is_html: bool = False,
    extra_recipients: Sequence[str] = (),
) -> bool:
    """Envía una notificación por email.

    Args:
        subject: Asunto del email.
        body: Cuerpo del mensaje (texto plano o HTML según is_html).
        is_html: Si True, envía como text/html; si False, como text/plain.
        extra_recipients: Destinatarios adicionales a los configurados en NOTIFY_TO.

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

    smtp_port = int(_env("NOTIFY_SMTP_PORT", "465"))
    smtp_user = _env("NOTIFY_SMTP_USER")
    smtp_password = _env("NOTIFY_SMTP_PASSWORD")
    from_addr = _env("NOTIFY_FROM") or smtp_user
    subject_prefix = _env("NOTIFY_SUBJECT_PREFIX", "[RAFAM]")

    recipients = _build_recipients() + list(extra_recipients)
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

    try:
        timeout = int(_env("NOTIFY_SMTP_TIMEOUT", "15"))
        # Puerto 465 = SSL/TLS directo; otros puertos = STARTTLS
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout) as server:
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, recipients, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as server:
                server.ehlo()
                server.starttls()
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


def notify_sync_error(
    errors: dict[str, str] | str,
    *,
    dry_run: bool = False,
) -> bool:
    """Notifica un error crítico o fallo de sincronización de entidades por email.

    Args:
        errors: Diccionario de {entidad: error} o un string con el error general.
        dry_run: Si se estaba ejecutando en modo de prueba (dry-run).

    Returns:
        True si se envió el email, False en caso contrario.
    """
    mode_label = "DRY-RUN" if dry_run else "APPLY"
    subject = f"❌ ERROR de Sincronización RAFAM [{mode_label}]"

    lines = [
        f"Se detectaron errores durante la ejecución de la sincronización ({mode_label}).",
        "",
        "─" * 60,
        "",
    ]

    if isinstance(errors, dict):
        lines.append("Detalle de errores por entidad:")
        for entity, err in errors.items():
            lines.append(f"  • {entity}: {err}")
    else:
        lines.append("Detalle del error general / excepción:")
        lines.append(f"  {errors}")

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
    if not _is_enabled() or not _env("NOTIFY_RUN_REPORT", "false").lower() == "true":
        return False

    mode_label = "DRY-RUN" if dry_run else "APPLY"
    success = summary_data.get("success", False)
    status_label = "OK" if success else "CON ERRORES"
    subject = f"Reporte Sincronización RAFAM [{mode_label}] — {status_label}"

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
    total_records = sum(m.get("records_ok", 0) for m in entity_metrics)
    total_batches_ok = sum(m.get("batches_ok", 0) for m in entity_metrics)
    total_batches_failed = sum(m.get("batches_failed", 0) for m in entity_metrics)
    global_speed_min = (total_records / run_mins) if run_mins > 0 else 0.0
    global_speed_sec = (total_records / run_secs) if run_secs > 0 else 0.0

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

    lines.append("RESUMEN GLOBAL")
    lines.append(SUB)
    lines.append(f"  • Entidades procesadas   : {total_entities}  (OK: {ok_entities}, con error: {fail_entities})")
    lines.append(f"  • Registros migrados     : {total_records:,}")
    lines.append(f"  • Batches OK / con error : {total_batches_ok} / {total_batches_failed}")
    lines.append(f"  • Velocidad global       : {global_speed_min:,.1f} reg/min   ({global_speed_sec:,.1f} reg/s)")
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
        ent_ok = m.get("success", False)
        ent_status = "OK" if ent_ok else "ERROR"
        duration = m.get("duration_secs", 0.0) or 0.0
        dur_min = duration / 60.0
        records = m.get("records_ok", 0)
        speed_min = (records / dur_min) if dur_min > 0 else 0.0
        speed_sec = (records / duration) if duration > 0 else 0.0
        query_dur = m.get("query_duration_secs", 0.0) or 0.0
        batch_times = m.get("batch_times") or []
        if batch_times:
            b_min = min(batch_times)
            b_max = max(batch_times)
            b_avg = sum(batch_times) / len(batch_times)
        else:
            b_min = b_max = b_avg = 0.0

        lines.append(f"[{ent}]  ({m.get('mode', '—')})  →  {ent_status}")
        lines.append(f"  Registros migrados      : {records:,}")
        lines.append(f"  Batches OK / con error  : {m.get('batches_ok', 0)} / {m.get('batches_failed', 0)}")
        lines.append(f"  Duración                : {duration:.2f} s   ({dur_min:.2f} min)")
        lines.append(f"  Query origen (SQL)      : {query_dur:.2f} s")
        lines.append(f"  Velocidad               : {speed_min:,.1f} reg/min   ({speed_sec:,.1f} reg/s)")
        lines.append(f"  Latencia batch (POST)   : min {b_min:.3f}s | prom {b_avg:.3f}s | max {b_max:.3f}s")
        if not ent_ok:
            lines.append(f"  {SUB}")
            _emit_error_block(lines, m, indent="  ")
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
    lines.append("")
    lines.append(SEP)
    lines.append("Email generado automáticamente por el pipeline de sincronización RAFAM (Madariaga).")

    body = "\n".join(lines)
    return send_notification(subject, body, is_html=False)


def notify_entity_detailed_report(
    entity: str,
    metrics: dict,
    *,
    dry_run: bool = False,
) -> bool:
    """Envía un reporte detallado (texto plano) de performance/diagnóstico de una entidad FULL LOAD."""
    if not _is_enabled() or not _env("NOTIFY_RUN_REPORT", "false").lower() == "true":
        return False

    mode_label = "DRY-RUN" if dry_run else "APPLY"
    status_label = "OK" if metrics.get("success") else "CON ERRORES"
    subject = f"FULL LOAD Detalle: {entity} [{mode_label}]"

    SEP = "=" * 70
    SUB = "-" * 70

    batch_times = metrics.get("batch_times") or []
    num_batches = len(batch_times)
    if num_batches > 0:
        avg_batch = sum(batch_times) / num_batches
        max_batch = max(batch_times)
        min_batch = min(batch_times)
    else:
        avg_batch = max_batch = min_batch = 0.0

    total_duration = metrics.get("duration_secs", 0.0) or 0.0
    query_duration = metrics.get("query_duration_secs", 0.0) or 0.0
    net_duration = total_duration - query_duration
    query_pct = (query_duration / total_duration * 100) if total_duration > 0 else 0.0
    net_pct = (net_duration / total_duration * 100) if total_duration > 0 else 0.0
    records = metrics.get("records_ok", 0)
    dur_min = total_duration / 60.0
    speed_min = (records / dur_min) if dur_min > 0 else 0.0
    speed_sec = (records / total_duration) if total_duration > 0 else 0.0

    lines: list[str] = []
    lines.append(SEP)
    lines.append(f"DETALLE FULL LOAD — {entity}")
    lines.append(SEP)
    lines.append(f"Estado : {status_label}")
    lines.append(f"Modo   : {mode_label}")
    lines.append("")

    lines.append("MÉTRICAS GENERALES")
    lines.append(SUB)
    lines.append(f"  • Registros procesados  : {records:,}")
    lines.append(f"  • Batches OK            : {metrics.get('batches_ok', 0)}")
    lines.append(f"  • Batches fallidos      : {metrics.get('batches_failed', 0)}")
    lines.append(f"  • Tiempo total de carga : {total_duration:.2f} s   ({dur_min:.2f} min)")
    lines.append(f"  • Velocidad             : {speed_min:,.1f} reg/min   ({speed_sec:,.1f} reg/s)")
    lines.append("")

    lines.append("DISTRIBUCIÓN DE OVERHEAD")
    lines.append(SUB)
    lines.append(f"  • Overhead SQL (query origen) : {query_duration:.2f}s   ({query_pct:.1f}%)")
    lines.append(f"  • Envío HTTP & red (Paxapos)  : {net_duration:.2f}s   ({net_pct:.1f}%)")
    lines.append("")

    lines.append("LATENCIA POR BATCH (POST)")
    lines.append(SUB)
    lines.append(f"  • Lotes totales   : {num_batches}")
    lines.append(f"  • Latencia mínima : {min_batch:.3f}s")
    lines.append(f"  • Latencia prom.  : {avg_batch:.3f}s")
    lines.append(f"  • Latencia máxima : {max_batch:.3f}s")

    if metrics.get("error_msg") or metrics.get("error_trace"):
        lines.append("")
        lines.append("DIAGNÓSTICO DE ERROR")
        lines.append(SUB)
        _emit_error_block(lines, metrics, indent="")

    lines.append("")
    lines.append(SEP)
    lines.append("Reporte individual de entidad — Pipeline RAFAM (Madariaga).")

    body = "\n".join(lines)
    return send_notification(subject, body, is_html=False)
