import os
from unittest.mock import patch, MagicMock
import pytest
from src.notifier import notify_run_report

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
        assert "Filas leídas de RAFAM" in body
        assert "Registros migrados" not in body
        assert "filas leídas no equivale a altas nuevas" in body
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
    assert "2026-07-01 08:00:00" in body
    assert "external_id" not in body
