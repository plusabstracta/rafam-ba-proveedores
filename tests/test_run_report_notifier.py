import os
from unittest.mock import patch, MagicMock
import pytest
from src.notifier import notify_run_report
from src.utils import utc_sql_to_local

@pytest.fixture
def clean_env():
    with patch.dict(os.environ, {}, clear=True):
        yield

def test_notify_run_report_disabled_by_default(clean_env):
    # Por defecto NOTIFY_RUN_REPORT no está seteado o es false
    assert not notify_run_report({}, [])

@patch("src.notifier._is_enabled", return_value=True)
@patch("src.notifier.send_notification")
def test_notify_run_report_enabled(mock_send, mock_is_enabled, clean_env):
    with patch.dict(os.environ, {"NOTIFY_RUN_REPORT": "true", "NOTIFY_SMTP_HOST": "localhost"}):
        summary_data = {
            "hostname": "test-server",
            "start_time": "2026-07-01 10:00:00",
            "end_time": "2026-07-01 10:05:00",
            "duration_formatted": "00:05:00",
            "runs_count": 144,
            "success": True,
            "error_msg": None,
            "retry_counts_start": {"proveedores": 1},
            "retry_counts_end": {"proveedores": 0},
        }
        
        entity_metrics = [
            {
                "entity": "proveedores",
                "mode": "FULL LOAD",
                "success": True,
                "records_ok": 100,
                "migrator_sent": 80,
                "migrator_saved": 78,
                "migrator_errors": 2,
                "migrator_created": 10,
                "migrator_updated": 68,
                "batches_ok": 2,
                "batches_failed": 0,
                "duration_secs": 10.0,
                "batch_times": [4.0, 6.0],
            }
        ]
        
        mock_send.return_value = True
        
        res = notify_run_report(summary_data, entity_metrics, dry_run=False)
        
        assert res is True
        mock_send.assert_called_once()
        
        # Obtener los argumentos pasados a send_notification
        args, kwargs = mock_send.call_args
        subject = args[0]
        body = args[1]
        is_html = kwargs.get("is_html")
        
        assert "Reporte Sincronización RAFAM [APPLY] — CON ERRORES" in subject
        assert is_html is False
        assert "test-server" in body
        assert "proveedores" in body
        assert "FULL LOAD" in body
        assert "00:05:00" in body
        assert "Corridas agregadas" in body
        assert "144" in body
        assert "Registros migrados" not in body
        # Metricas sacadas del mail (no aportaban al operador).
        for removed in (
            "Filas leídas de RAFAM",
            "Sin cambios, no enviados",
            "Excluidos por configuración",
            "Diferidos",
            "Velocidad",
            "filas leídas no equivale a altas nuevas",
            "Query origen",
            "Latencia batch",
        ):
            assert removed not in body
        assert "Filas inválidas" in body
        assert "Items enviados Paxapos" in body
        assert "Confirmados por Paxapos" in body
        assert "Altas nuevas" in body
        assert "Actualizaciones" in body
        assert "Rechazados por Paxapos" in body
        assert "80" in body
        assert "78" in body

@patch("src.notifier._is_enabled", return_value=True)
@patch("src.notifier.send_notification")
def test_notify_run_report_nested_retry_counts(mock_send, mock_is_enabled, clean_env):
    """Regresión: retry_store.counts_by_entity devuelve {entity: {status: count}}.

    El reporte debe sumar los estados a un entero y no romper con dict - int.
    """
    with patch.dict(os.environ, {"NOTIFY_RUN_REPORT": "true", "NOTIFY_SMTP_HOST": "localhost"}):
        summary_data = {
            "hostname": "test-server",
            "start_time": "2026-07-01 10:00:00",
            "end_time": "2026-07-01 10:05:00",
            "duration_formatted": "00:05:00",
            "success": False,
            "error_msg": "fallo",
            "retry_counts_start": {},
            "retry_counts_end": {"proveedores": {"pending": 3}},
        }
        entity_metrics = [
            {
                "entity": "proveedores",
                "mode": "FULL LOAD",
                "success": False,
                "records_ok": 10,
                "migrator_sent": 5,
                "migrator_saved": 0,
                "migrator_errors": 5,
                "batches_ok": 1,
                "batches_failed": 1,
                "duration_secs": 2.0,
                "batch_times": [2.0],
            }
        ]
        mock_send.return_value = True

        res = notify_run_report(summary_data, entity_metrics, dry_run=False)

        assert res is True
        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        body = args[1]
        # El conteo pendiente (3) debe aparecer como entero, no como dict.
        assert "{'pending'" not in body
        assert "(+3)" in body


@patch("src.notifier._is_enabled", return_value=True)
@patch("src.notifier.send_notification")
def test_notify_run_report_groups_retry_causes_without_ids(mock_send, mock_is_enabled, clean_env):
    summary_data = {
        "hostname": "test-server",
        "start_time": "2026-07-01 10:00:00",
        "end_time": "2026-07-01 10:05:00",
        "duration_formatted": "00:05:00",
        "success": True,
        "status_label": "CON ADVERTENCIAS",
        "retry_counts_start": {},
        "retry_counts_end": {"retenciones": {"pending": 2}},
        "retry_summary_end": [
            {
                "entity": "retenciones",
                "status": "pending",
                "reason_code": "dependency_missing",
                "reason_detail": "payment_not_migrated",
                "count": 2,
                "oldest_first_seen": "2026-07-01 08:00:00",
                "last_attempt": "2026-07-01 10:04:00",
                "max_attempts": 1,
            }
        ],
    }
    mock_send.return_value = True

    notify_run_report(summary_data, [], dry_run=False)

    subject, body = mock_send.call_args.args[:2]
    assert "CON ADVERTENCIAS" in subject
    assert "dependency_missing/payment_not_migrated: 2" in body
    # Los timestamps de la cola son UTC y el mail los muestra en hora local.
    assert utc_sql_to_local("2026-07-01 08:00:00") in body
    assert "external_id" not in body


@patch("src.notifier._is_enabled", return_value=True)
@patch("src.notifier.send_notification")
def test_notify_run_report_lista_detalle_individual_con_label_legible(mock_send, mock_is_enabled, clean_env):
    """Pedido explicito del operador: el mail tiene que decir CON QUE OC/OP/
    retencion se corresponde cada pendiente, no solo un conteo agrupado."""
    with patch.dict(os.environ, {"NOTIFY_RUN_REPORT": "true", "NOTIFY_SMTP_HOST": "localhost"}):
        summary_data = {
            "hostname": "test-server",
            "start_time": "2026-07-01 10:00:00",
            "end_time": "2026-07-01 10:05:00",
            "duration_formatted": "00:05:00",
            "success": True,
            "status_label": "CON ADVERTENCIAS",
            "retry_counts_start": {},
            "retry_counts_end": {"orden_pago": {"pending": 1}},
            "retry_summary_end": [],
            "retry_detail_end": {
                "orden_pago": {
                    "items": [
                        {
                            "label": "OP 2026-1023",
                            "reason_code": "backend_rejected",
                            "reason_detail": "validation_error",
                            "attempts": 3,
                            "status": "pending",
                            "first_seen": "2026-06-30 09:00:00",
                            "last_attempt": "2026-07-01 09:50:00",
                            "error_message": "importe negativo",
                        },
                    ],
                    "total": 5,
                },
            },
        }
    mock_send.return_value = True

    notify_run_report(summary_data, [], dry_run=False)

    _, body = mock_send.call_args.args[:2]
    assert "OP 2026-1023" in body
    assert "importe negativo" in body
    assert "backend_rejected" in body
    # total=5 pero solo 1 item mostrado -> tiene que avisar que faltan 4 y donde verlos.
    assert "4 mas" in body
    assert "retry-queue --entity orden_pago" in body


@patch("src.notifier._is_enabled", return_value=True)
@patch("src.notifier.send_notification")
def test_notify_run_report_sin_retry_detail_no_rompe(mock_send, mock_is_enabled, clean_env):
    """Compatibilidad hacia atras: summary_data sin `retry_detail_end` (ej. un
    run_history.jsonl viejo agregado antes de este cambio) no debe romper."""
    with patch.dict(os.environ, {"NOTIFY_RUN_REPORT": "true", "NOTIFY_SMTP_HOST": "localhost"}):
        summary_data = {
            "hostname": "test-server",
            "start_time": "2026-07-01 10:00:00",
            "end_time": "2026-07-01 10:05:00",
            "duration_formatted": "00:05:00",
            "success": True,
            "retry_counts_start": {},
            "retry_counts_end": {},
        }
    mock_send.return_value = True

    assert notify_run_report(summary_data, [], dry_run=False) is True


@patch("src.notifier._is_enabled", return_value=True)
@patch("src.notifier.send_notification")
def test_notify_run_report_duracion_es_promedio_por_corrida(mock_send, mock_is_enabled, clean_env):
    """En el resumen diario la duracion por entidad es la de UNA corrida, no la suma del dia."""
    summary_data = {"duration_formatted": "00:30:00", "runs_count": 3, "success": True}
    entity_metrics = [
        {"entity": "oc_items", "mode": "DIARIO", "success": True, "runs": 3, "duration_secs": 300.0},
        {"entity": "proveedores", "mode": "INCREMENTAL", "success": True, "duration_secs": 12.0},
    ]
    mock_send.return_value = True

    assert notify_run_report(summary_data, entity_metrics) is True
    body = mock_send.call_args[0][1]

    assert "Duración prom. corrida  : 100.00 s   (1.67 min, promedio de 3 corridas)" in body
    assert "300.00 s" not in body
    # Corrida individual (sin `runs`): la duracion se muestra tal cual.
    assert "Duración                : 12.00 s   (0.20 min)" in body
