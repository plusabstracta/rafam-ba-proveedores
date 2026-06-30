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
