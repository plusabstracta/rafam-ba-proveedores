"""error_formatting.py — Formateo detallado de excepciones para diagnóstico.

Módulo compartido por todo el pipeline (check_integrity, notifier, main) para
producir descripciones de errores ricas en contexto: clase de excepción,
mensaje, archivo/línea/función de origen y traceback completo.

Se usa a menudo en reportes destinados al equipo de soporte y desarrollo, por
eso vive en ``src/`` y no en ``scripts/``.
"""

from __future__ import annotations

import traceback
from pathlib import Path


def exception_origin(exc: BaseException) -> tuple[str, str, str]:
    """Devuelve (archivo, línea, función) del último frame del traceback.

    Si la excepción no tiene traceback asociado devuelve marcadores
    ``"Desconocido"`` para cada campo.
    """
    origin_file = "Desconocido"
    origin_line = "Desconocido"
    origin_func = "Desconocido"

    tb = exc.__traceback__
    if tb:
        while tb.tb_next:
            tb = tb.tb_next
        frame = tb.tb_frame
        code = frame.f_code
        origin_file = Path(code.co_filename).name
        origin_line = str(tb.tb_lineno)
        origin_func = code.co_name

    return origin_file, origin_line, origin_func


def describe_exception(exc: BaseException) -> dict:
    """Extrae los campos de diagnóstico de una excepción en un dict.

    Returns:
        dict con las claves:
            - ``error_type``      : nombre de la clase de excepción.
            - ``error_message``   : ``str(exc)``.
            - ``error_location``  : "Archivo: X, Línea: N, Función: F".
            - ``error_trace``     : traceback completo como texto.
    """
    origin_file, origin_line, origin_func = exception_origin(exc)
    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return {
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "error_location": f"Archivo: {origin_file}, Línea: {origin_line}, Función: {origin_func}",
        "error_trace": tb_text,
    }


def format_exception_context(
    exc: Exception,
    entity: str,
    source_key: str | None,
    context: str,
) -> str:
    """Formatea detalladamente una excepción con traceback completo y contexto.

    Bloque multilinea autoexplicativo (entidad, source_key, operación, ubicación
    del error, clase, mensaje y traceback) apto para logs y para el cuerpo de
    los emails de soporte.
    """
    info = describe_exception(exc)
    return (
        f"======================================================================\n"
        f"ERROR DETECTADO EN ENTIDAD: '{entity}' (source_key: '{source_key}')\n"
        f"Contexto de la operación: {context}\n"
        f"Ubicación del error: {info['error_location']}\n"
        f"Clase de excepción: {info['error_type']}\n"
        f"Mensaje de error: {info['error_message']}\n"
        f"----------------------------------------------------------------------\n"
        f"Traceback completo:\n"
        f"{info['error_trace']}"
        f"======================================================================"
    )
