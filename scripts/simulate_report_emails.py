#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Script para simular y visualizar cómo se verían los correos de reporte de sincronización

con errores, diagnósticos detallados, tracebacks, respuestas del migrator y
full load.
"""

import os
import sys
from unittest.mock import patch
from pathlib import Path

# Agregar el directorio raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.notifier import notify_run_report, notify_entity_detailed_report


def print_email_mock(subject, body, is_html=False):
    """Mock para imprimir el contenido del mail en terminal."""
    print("=" * 80)
    print(f"ASUNTO: {subject}")
    print("=" * 80)
    print(body)
    print("=" * 80)
    print()
    return True


# Forzar a True la habilitación del reporte en el mock/env
os.environ["NOTIFY_RUN_REPORT"] = "true"
os.environ["NOTIFY_SMTP_HOST"] = "localhost"


def simular_reporte_corrida_con_errores_y_full_load():
    print("\nPROBANDO REPORTE DE CORRIDA COMPLETO (Sincronización con Errores y Cola de Reintentos)")
    
    summary_data = {
        "hostname": "rafam-madariaga-prod-01",
        "start_time": "2026-07-01 03:00:01",
        "end_time": "2026-07-01 03:14:45",
        "duration_formatted": "00:14:44",
        "success": False,
        "error_msg": "Se encontraron fallos en 1 de las 4 entidades sincronizadas.",
        "retry_counts_start": {
            "proveedores": 4,
            "oc_items": {"pending": 10},
            "orden_pago": 1
        },
        "retry_counts_end": {
            "proveedores": 4,
            "oc_items": {"pending": 12},  # +2 incrementados
            "orden_pago": 0  # Resuelto
        },
    }

    # Traceback simulado
    mock_traceback = """Traceback (most recent call last):
  File "src/exporter.py", line 124, in export_entity
    self.process_batch(batch, mapper)
  File "src/exporter.py", line 198, in process_batch
    raise RuntimeError(f"HTTP {status}: {body[:500]}")
RuntimeError: HTTP 422: {"error": "Semántica inválida", "details": {"referencia_externa": "proveedor no encontrado o inactivo"}}"""

    entity_metrics = [
        {
            "entity": "proveedores",
            "mode": "INCREMENTAL",
            "success": True,
            "records_ok": 1500,
            "batches_ok": 15,
            "batches_failed": 0,
            "duration_secs": 185.0,
            "query_duration_secs": 15.0,
            "batch_times": [10.5, 12.0, 11.2, 9.8, 14.1, 11.0, 11.5, 10.1, 11.9, 11.3, 12.0, 11.5, 10.8, 11.1, 10.9],
        },
        {
            "entity": "oc_items",
            "mode": "FULL LOAD",
            "success": False,
            "records_ok": 850,
            "batches_ok": 8,
            "batches_failed": 1,
            "duration_secs": 122.5,
            "query_duration_secs": 42.1,
            "batch_times": [8.1, 9.5, 7.8, 8.4, 15.0, 9.2, 8.9, 7.6],
            "error_msg": "Error en la validación HTTP 422 devuelta por el migrator de Paxapos al subir el batch #9.",
            "error_type": "RuntimeError",
            "error_location": "Archivo: src/exporter.py, Línea: 198, Función: process_batch",
            "migrator_error": 'HTTP 422 Unprocessable Entity\n{"error": "Semántica inválida", "details": {"referencia_externa": "proveedor no encontrado o inactivo", "item_codigo_rafam": "M045-8"}}',
            "error_trace": mock_traceback,
        },
        {
            "entity": "orden_pago",
            "mode": "INCREMENTAL",
            "success": True,
            "records_ok": 320,
            "batches_ok": 4,
            "batches_failed": 0,
            "duration_secs": 45.2,
            "query_duration_secs": 4.1,
            "batch_times": [10.0, 11.1, 9.9, 10.1],
        }
    ]

    with patch("src.notifier._is_enabled", return_value=True), \
         patch("src.notifier.send_notification", side_effect=print_email_mock):
        notify_run_report(summary_data, entity_metrics, dry_run=False)


def simular_reporte_detailed_full_load():
    print("\nPROBANDO REPORTE DETALLADO (FULL LOAD Exitoso Especial - Performance)")
    
    metrics = {
        "entity": "orden_compra",
        "mode": "FULL LOAD",
        "success": True,
        "records_ok": 12500,
        "batches_ok": 125,
        "batches_failed": 0,
        "duration_secs": 642.50,
        "query_duration_secs": 158.30,  # El query de Oracle tardó bastante en traer 12500 reg
        "batch_times": [3.5, 4.2, 3.8, 5.1, 4.9, 3.2, 4.0, 3.9, 4.5, 3.7], # Submuestra de tiempos
        "error_msg": None,
    }

    with patch("src.notifier._is_enabled", return_value=True), \
         patch("src.notifier.send_notification", side_effect=print_email_mock):
        notify_entity_detailed_report("orden_compra", metrics, dry_run=False)


if __name__ == "__main__":
    simular_reporte_corrida_con_errores_y_full_load()
    simular_reporte_detailed_full_load()
