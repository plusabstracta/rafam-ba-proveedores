import os
from unittest.mock import patch, MagicMock
import pytest
from src.notifier import notify_run_report, notify_entity_detailed_report

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
        html_body = args[1]
        is_html = kwargs.get("is_html")
        
        assert "Reporte Sincronización RAFAM [APPLY] — OK" in subject
        assert is_html is True
        assert "test-server" in html_body
        assert "proveedores" in html_body
        assert "FULL LOAD" in html_body
        assert "00:05:00" in html_body

@patch("src.notifier._is_enabled", return_value=True)
@patch("src.notifier.send_notification")
def test_notify_entity_detailed_report(mock_send, mock_is_enabled, clean_env):
    with patch.dict(os.environ, {"NOTIFY_RUN_REPORT": "true", "NOTIFY_SMTP_HOST": "localhost"}):
        metrics = {
            "entity": "proveedores",
            "mode": "FULL LOAD",
            "success": True,
            "records_ok": 500,
            "batches_ok": 5,
            "batches_failed": 0,
            "duration_secs": 25.0,
            "query_duration_secs": 5.0,
            "batch_times": [3.0, 4.0, 3.0, 5.0, 5.0],
            "error_msg": None,
        }
        
        mock_send.return_value = True
        
        res = notify_entity_detailed_report("proveedores", metrics, dry_run=True)
        
        assert res is True
        mock_send.assert_called_once()
        
        args, kwargs = mock_send.call_args
        subject = args[0]
        html_body = args[1]
        is_html = kwargs.get("is_html")
        
        assert "FULL LOAD Detalle: proveedores [DRY-RUN]" in subject
        assert is_html is True
        # Verificar cálculos de overhead en HTML
        assert "Overhead SQL" in html_body
        assert "5.00s" in html_body  # tiempo query
        assert "20.00s" in html_body  # tiempo de red (25.0 - 5.0)
        assert "5.000s" in html_body  # max batch latency
        assert "3.000s" in html_body  # min batch latency
