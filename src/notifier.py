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


def notify_run_report(
    summary_data: dict,
    entity_metrics: list[dict],
    *,
    dry_run: bool = False,
) -> bool:
    """Envía un reporte resumen en formato HTML al finalizar una corrida (run)."""
    if not _is_enabled() or not _env("NOTIFY_RUN_REPORT", "false").lower() == "true":
        return False

    mode_label = "DRY-RUN" if dry_run else "APPLY"
    status_icon = "✅" if summary_data["success"] else "❌"
    status_label = "OK" if summary_data["success"] else "CON ERRORES"
    subject = f"{status_icon} Reporte Sincronización RAFAM [{mode_label}] — {status_label}"

    # Construir filas de la tabla de entidades
    table_rows = []
    for m in entity_metrics:
        # Calcular velocidad de carga (registros / segundo)
        duration = m["duration_secs"]
        speed = m["records_ok"] / duration if duration > 0 else 0
        speed_str = f"{speed:.1f} reg/s" if speed > 0 else "—"
        
        status_badge_color = "#10b981" if m["success"] else "#ef4444"
        status_badge_text = "OK" if m["success"] else "ERROR"
        
        mode_badge_color = "#3b82f6" if m["mode"] == "FULL LOAD" else "#6b7280"

        table_rows.append(f"""
        <tr style="border-bottom: 1px solid #e5e7eb;">
            <td style="padding: 12px; font-weight: bold; color: #1f2937;">{m['entity']}</td>
            <td style="padding: 12px;">
                <span style="background-color: {mode_badge_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">
                    {m['mode']}
                </span>
            </td>
            <td style="padding: 12px;">
                <span style="background-color: {status_badge_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">
                    {status_badge_text}
                </span>
            </td>
            <td style="padding: 12px; text-align: right;">{m['records_ok']:,}</td>
            <td style="padding: 12px; text-align: right; color: #10b981;">{m['batches_ok']}</td>
            <td style="padding: 12px; text-align: right; color: { '#ef4444' if m['batches_failed'] > 0 else '#6b7280' }; font-weight: { 'bold' if m['batches_failed'] > 0 else 'normal' };">{m['batches_failed']}</td>
            <td style="padding: 12px; text-align: right;">{duration:.2f}s</td>
            <td style="padding: 12px; text-align: right; font-weight: 500;">{speed_str}</td>
        </tr>
        """)

    # Construir filas de la tabla de reintentos
    retry_rows = []
    start_retries = summary_data.get("retry_counts_start") or {}
    end_retries = summary_data.get("retry_counts_end") or {}
    all_entities_set = set(start_retries.keys()) | set(end_retries.keys())
    
    if all_entities_set:
        for ent in sorted(all_entities_set):
            start_count = start_retries.get(ent, 0)
            end_count = end_retries.get(ent, 0)
            diff = end_count - start_count
            diff_color = "#ef4444" if diff > 0 else ("#10b981" if diff < 0 else "#6b7280")
            diff_sign = "+" if diff > 0 else ""
            diff_str = f"({diff_sign}{diff})" if diff != 0 else "—"
            
            retry_rows.append(f"""
            <tr style="border-bottom: 1px solid #e5e7eb;">
                <td style="padding: 10px; color: #374151; font-weight: 500;">{ent}</td>
                <td style="padding: 10px; text-align: right; color: #4b5563;">{start_count}</td>
                <td style="padding: 10px; text-align: right; color: #1f2937; font-weight: bold;">{end_count}</td>
                <td style="padding: 10px; text-align: right; color: {diff_color}; font-weight: 500;">{diff_str}</td>
            </tr>
            """)
    else:
        retry_rows.append("""
        <tr>
            <td colspan="4" style="padding: 15px; text-align: center; color: #9ca3af; font-style: italic;">
                Sin registros pendientes de reintento.
            </td>
        </tr>
        """)

    # Si hay errores generales, mostrarlos arriba
    error_box = ""
    if not summary_data["success"] and summary_data.get("error_msg"):
        error_box = f"""
        <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 16px; margin-bottom: 24px; border-radius: 4px;">
            <h3 style="margin-top: 0; color: #991b1b; font-size: 16px;">Detalle de error general:</h3>
            <pre style="white-space: pre-wrap; font-family: monospace; font-size: 13px; color: #7f1d1d; margin: 0; background: #fff5f5; padding: 10px; border-radius: 4px; border: 1px solid #fee2e2;">{summary_data['error_msg']}</pre>
        </div>
        """

    # Estructura del cuerpo HTML
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Reporte Sincronización</title>
    </head>
    <body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f3f4f6; color: #374151;">
        <div style="max-width: 800px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); overflow: hidden; border: 1px solid #e5e7eb;">
            <!-- Header con Gradiente -->
            <div style="background: linear-gradient(135deg, {'#059669, #10b981' if summary_data['success'] else '#dc2626, #f87171'}); padding: 30px 24px; color: #ffffff; text-align: center;">
                <h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.025em; text-transform: uppercase;">
                    RAFAM &rarr; Paxapos Sync
                </h1>
                <p style="margin: 5px 0 0 0; font-size: 15px; opacity: 0.9;">
                    Reporte de Corrida en modo <b>{mode_label}</b>
                </p>
            </div>
            
            <div style="padding: 24px;">
                {error_box}
                
                <!-- Metadata Grid -->
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; background-color: #f9fafb; padding: 16px; border-radius: 8px; border: 1px solid #f3f4f6;">
                    <div style="padding: 5px;">
                        <span style="font-size: 11px; text-transform: uppercase; color: #6b7280; font-weight: bold; display: block; margin-bottom: 2px;">Servidor</span>
                        <strong style="font-size: 14px; color: #1f2937;">{summary_data['hostname']}</strong>
                    </div>
                    <div style="padding: 5px;">
                        <span style="font-size: 11px; text-transform: uppercase; color: #6b7280; font-weight: bold; display: block; margin-bottom: 2px;">Inicio</span>
                        <strong style="font-size: 14px; color: #1f2937;">{summary_data['start_time']}</strong>
                    </div>
                    <div style="padding: 5px;">
                        <span style="font-size: 11px; text-transform: uppercase; color: #6b7280; font-weight: bold; display: block; margin-bottom: 2px;">Fin</span>
                        <strong style="font-size: 14px; color: #1f2937;">{summary_data['end_time']}</strong>
                    </div>
                    <div style="padding: 5px;">
                        <span style="font-size: 11px; text-transform: uppercase; color: #6b7280; font-weight: bold; display: block; margin-bottom: 2px;">Duración Total</span>
                        <strong style="font-size: 14px; color: {'#10b981' if summary_data['success'] else '#ef4444'};">{summary_data['duration_formatted']}</strong>
                    </div>
                </div>

                <!-- Tabla de Entidades -->
                <h2 style="font-size: 18px; color: #111827; margin: 0 0 12px 0; border-bottom: 2px solid #f3f4f6; padding-bottom: 6px;">Métricas por Entidad</h2>
                <div style="overflow-x: auto; margin-bottom: 28px;">
                    <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;">
                        <thead>
                            <tr style="background-color: #f9fafb; border-bottom: 2px solid #e5e7eb; color: #4b5563; font-weight: bold;">
                                <th style="padding: 10px 12px;">Entidad</th>
                                <th style="padding: 10px 12px;">Modo</th>
                                <th style="padding: 10px 12px;">Estado</th>
                                <th style="padding: 10px 12px; text-align: right;">Registros</th>
                                <th style="padding: 10px 12px; text-align: right;">Batches OK</th>
                                <th style="padding: 10px 12px; text-align: right;">Batches Error</th>
                                <th style="padding: 10px 12px; text-align: right;">Tiempo</th>
                                <th style="padding: 10px 12px; text-align: right;">Velocidad</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join(table_rows)}
                        </tbody>
                    </table>
                </div>

                <!-- Tabla de Reintentos -->
                <h2 style="font-size: 18px; color: #111827; margin: 0 0 12px 0; border-bottom: 2px solid #f3f4f6; padding-bottom: 6px;">Cola de Reintentos (Errores F1)</h2>
                <div style="overflow-x: auto; max-width: 500px; margin-bottom: 12px;">
                    <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;">
                        <thead>
                            <tr style="background-color: #f9fafb; border-bottom: 2px solid #e5e7eb; color: #4b5563; font-weight: bold;">
                                <th style="padding: 8px 10px;">Entidad</th>
                                <th style="padding: 8px 10px; text-align: right;">Al Inicio</th>
                                <th style="padding: 8px 10px; text-align: right;">Al Final</th>
                                <th style="padding: 8px 10px; text-align: right;">Variación</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join(retry_rows)}
                        </tbody>
                    </table>
                </div>
            </div>
            
            <div style="background-color: #f9fafb; padding: 16px 24px; text-align: center; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af;">
                Este email fue generado automáticamente por el sistema de sincronización de Madariaga.
            </div>
        </div>
    </body>
    </html>
    """

    return send_notification(subject, html_body, is_html=True)


def notify_entity_detailed_report(
    entity: str,
    metrics: dict,
    *,
    dry_run: bool = False,
) -> bool:
    """Envía un reporte detallado e individual de performance para una corrida FULL LOAD."""
    if not _is_enabled() or not _env("NOTIFY_RUN_REPORT", "false").lower() == "true":
        return False

    mode_label = "DRY-RUN" if dry_run else "APPLY"
    status_icon = "🚀" if metrics["success"] else "⚠️"
    subject = f"{status_icon} FULL LOAD Detalle: {entity} [{mode_label}]"

    # Procesar tiempos de batch
    batch_times = metrics.get("batch_times") or []
    num_batches = len(batch_times)
    
    if num_batches > 0:
        avg_batch = sum(batch_times) / num_batches
        max_batch = max(batch_times)
        min_batch = min(batch_times)
    else:
        avg_batch = max_batch = min_batch = 0.0

    # Calcular overheads
    total_duration = metrics["duration_secs"]
    query_duration = metrics.get("query_duration_secs", 0.0)
    net_duration = total_duration - query_duration

    query_pct = (query_duration / total_duration * 100) if total_duration > 0 else 0
    net_pct = (net_duration / total_duration * 100) if total_duration > 0 else 0

    # Si hay errores de validacion/migracion parciales
    error_section = ""
    if metrics.get("error_msg"):
        error_section = f"""
        <div style="background-color: #fff5f5; border-left: 4px solid #f87171; padding: 16px; border-radius: 4px; margin-bottom: 24px;">
            <strong style="color: #991b1b; display: block; margin-bottom: 8px;">Detalle de Error / Fallo:</strong>
            <pre style="margin: 0; background: #ffffff; padding: 10px; border-radius: 4px; border: 1px solid #fee2e2; font-family: monospace; font-size: 12px; color: #7f1d1d; white-space: pre-wrap;">{metrics['error_msg']}</pre>
        </div>
        """

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Performance Full Load: {entity}</title>
    </head>
    <body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f3f4f6; color: #374151;">
        <div style="max-width: 700px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); overflow: hidden; border: 1px solid #e5e7eb;">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #1e3a8a, #3b82f6); padding: 24px; color: #ffffff; text-align: center;">
                <h1 style="margin: 0; font-size: 20px; font-weight: 800; letter-spacing: -0.025em; text-transform: uppercase;">
                    Performance Full Load: {entity}
                </h1>
                <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.9;">
                    Análisis de Overhead de Red y Base de Datos &bull; {mode_label}
                </p>
            </div>

            <div style="padding: 24px;">
                {error_section}

                <!-- Tabla Resumen Metricas -->
                <h2 style="font-size: 16px; color: #111827; margin: 0 0 12px 0; border-bottom: 2px solid #f3f4f6; padding-bottom: 6px;">Métricas Generales</h2>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 24px;">
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 10px 0; color: #6b7280; font-weight: bold;">Registros Procesados</td>
                        <td style="padding: 10px 0; text-align: right; font-weight: bold; color: #111827;">{metrics['records_ok']:,}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 10px 0; color: #6b7280;">Batches OK</td>
                        <td style="padding: 10px 0; text-align: right; color: #10b981; font-weight: bold;">{metrics['batches_ok']}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 10px 0; color: #6b7280;">Batches Fallidos</td>
                        <td style="padding: 10px 0; text-align: right; color: {'#ef4444' if metrics['batches_failed'] > 0 else '#6b7280'}; font-weight: bold;">{metrics['batches_failed']}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 10px 0; color: #6b7280; font-weight: bold;">Tiempo Total de Carga</td>
                        <td style="padding: 10px 0; text-align: right; font-weight: bold; color: #1e3a8a;">{total_duration:.2f} segundos</td>
                    </tr>
                </table>

                <!-- Distribucion de Overhead -->
                <h2 style="font-size: 16px; color: #111827; margin: 0 0 12px 0; border-bottom: 2px solid #f3f4f6; padding-bottom: 6px;">Distribución de Overhead</h2>
                <div style="margin-bottom: 24px; padding: 16px; background-color: #f9fafb; border-radius: 8px; border: 1px solid #f3f4f6;">
                    <div style="height: 24px; display: flex; border-radius: 12px; overflow: hidden; margin-bottom: 12px;">
                        <div style="width: {query_pct}%; background-color: #f59e0b; color: white; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold;" title="Query SQL">
                            {query_pct:.0f}%
                        </div>
                        <div style="width: {net_pct}%; background-color: #3b82f6; color: white; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold;" title="Network POST">
                            {net_pct:.0f}%
                        </div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 12px;">
                        <div>
                            <span style="display: inline-block; width: 12px; height: 12px; background-color: #f59e0b; border-radius: 50%; margin-right: 4px;"></span>
                            Overhead SQL (Query Origen): <b>{query_duration:.2f}s</b> ({query_pct:.1f}%)
                        </div>
                        <div>
                            <span style="display: inline-block; width: 12px; height: 12px; background-color: #3b82f6; border-radius: 50%; margin-right: 4px;"></span>
                            Envío HTTP &amp; Red (Paxapos): <b>{net_duration:.2f}s</b> ({net_pct:.1f}%)
                        </div>
                    </div>
                </div>

                <!-- Detalles de Latencia de Red por Batch -->
                <h2 style="font-size: 16px; color: #111827; margin: 0 0 12px 0; border-bottom: 2px solid #f3f4f6; padding-bottom: 6px;">Detalle de Latencia por Batch (POST)</h2>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 8px 0; color: #6b7280;">Lotes Totales</td>
                        <td style="padding: 8px 0; text-align: right; font-weight: bold; color: #111827;">{num_batches}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 8px 0; color: #6b7280;">Latencia Mínima</td>
                        <td style="padding: 8px 0; text-align: right; color: #10b981;">{min_batch:.3f}s</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 8px 0; color: #6b7280;">Latencia Promedio</td>
                        <td style="padding: 8px 0; text-align: right; color: #3b82f6; font-weight: bold;">{avg_batch:.3f}s</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f3f4f6;">
                        <td style="padding: 8px 0; color: #6b7280;">Latencia Máxima (Lote más lento)</td>
                        <td style="padding: 8px 0; text-align: right; color: #ef4444; font-weight: bold;">{max_batch:.3f}s</td>
                    </tr>
                </table>
            </div>

            <div style="background-color: #f9fafb; padding: 16px; text-align: center; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af;">
                Reporte de performance individual &bull; Madariaga RAFAM Pipeline
            </div>
        </div>
    </body>
    </html>
    """

    return send_notification(subject, html_body, is_html=True)
