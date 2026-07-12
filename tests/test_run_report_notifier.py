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
        
        assert "Reporte Sincronización RAFAM [APPLY] — OK" in subject
        assert is_html is False
        assert "test-server" in body
        assert "proveedores" in body
        assert "FULL LOAD" in body
        assert "00:05:00" in body
        assert "Corridas agregadas" in body
        assert "144" in body
        assert "Registros procesados" in body
        assert "Registros migrados" not in body
        assert "no equivale a altas nuevas" in body
        assert "Enviados al migrator" in body
        assert "Guardados por migrator" in body
        assert "Errores del migrator" in body
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
