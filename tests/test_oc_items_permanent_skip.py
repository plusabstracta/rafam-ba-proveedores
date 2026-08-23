"""paxapos#489 — oc_items es full_load: una OC que el receptor rechaza para
siempre (ej. el Pedido destino esta soft-deleted) se reenviaba en TODAS las
corridas, generando el mismo error cada ~10 minutos sin cortar nunca.

A diferencia de orden_pago/retenciones (incrementales: alcanza con no
reinyectar un 'permanent'), oc_items escanea toda la tabla en cada corrida, asi
que necesita una exclusion explicita contra `RetryStore.permanent_external_ids`.
"""

from __future__ import annotations

from unittest.mock import patch

from src.exporter import MigratorExporter
from src.retry_store import RetryStore

_COLUMNS = [
    "EJERCICIO", "UNI_COMPRA", "NRO_OC", "COD_PROV",
    "OC_FECH_OC", "OC_OBSERVACIONES", "OC_ESTADO_OC", "OC_FECH_CONFIRM", "OC_IMPORTE_TOT",
    "SG_JURISDICCION",
    "ITEM_OC", "DELEG_SOLIC", "NRO_SOLIC", "DESCRIPCION", "CANTIDAD", "IMP_UNITARIO", "CANT_RECIB",
]

# La OC "envenenada": su Pedido destino esta soft-deleted en Paxapos y el
# receptor la rechaza siempre con el mismo error (paxapos-core#489).
_ROW_POISON = (
    2026, 1, 3130, 5,
    "2026-08-01", "OC municipio", "R", "2026-08-02", 1000.0,
    None,
    1, 10, 20, "Item test", 2.0, 500.0, 2.0,
)


def _ok_row(nro_oc: int) -> tuple:
    """OC siempre aceptada por el receptor, con una clave nueva en cada llamada.

    Sin esto el batch de la corrida #2 en adelante quedaria compuesto SOLO por
    la OC envenenada (la OC "ok" de la corrida anterior ya quedo linkeada y se
    saltea por `mismo_estado`), volviendo a caer en el caso "seccion 100%
    fallida" que corta con RuntimeError antes de llegar a
    `_record_batch_outcomes` — no es el escenario real del issue (ahi el resto
    de un batch de 500 filas SI se procesaba bien).
    """
    return (
        2026, 1, nro_oc, 5,
        "2026-08-01", "OC ok", "R", "2026-08-02", 500.0,
        None,
        1, 10, 30 + nro_oc, "Item ok", 1.0, 500.0, 1.0,
    )


def _migrator(monkeypatch, tmp_path):
    monkeypatch.setenv("PAXAPOS_URL", "https://example.test")
    monkeypatch.setenv("PAXAPOS_TENANT", "tenant")
    monkeypatch.setenv("PAXAPOS_API_KEY", "key")
    monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(tmp_path / "migrator_links.db"))
    monkeypatch.setenv("PAXAPOS_VERIFY_SSL", "true")
    lookup_payload = {
        "lookups": {
            "unidades_de_medida": [{"id": "1", "name": "Unidad"}],
            "tipos_factura": [{"id": "2", "name": "A", "codename": "factura_a"}],
            "tipos_de_pago": [{"id": "4", "name": "Transferencia bancaria"}],
        }
    }
    with patch("src.exporter.fetch_migrator_lookups", return_value=lookup_payload):
        exporter = MigratorExporter(dry_run=False)
    exporter._link_store.save_link("proveedores", "5", "9001")
    return exporter


def _fake_post(post_calls: list) -> callable:
    """POST fake: la OC 3130 siempre rebota (soft-delete), el resto se acepta.

    Refleja la forma real de la respuesta del RafamMigracionesController: un
    207 con `errors` (por fila) y `stats`/`results` con lo que SI se guardo.
    """

    def _post(url, payload):
        post_calls.append(payload)
        ordenes_compra = payload.get("ordenes_compra", [])
        results = []
        errors = []
        ok = 0
        for oc in ordenes_compra:
            ext = oc["external_id"]
            if ext["nro_oc"] == 3130:
                errors.append({
                    "section": "ordenes_compra",
                    "external_id": ext,
                    "message": (
                        "No se puede guardar Pedido #3030 porque ese registro esta "
                        "borrado. Probablemente estes reenviando un formulario viejo."
                    ),
                })
            else:
                ok += 1
                results.append({"success": True, "external_id": ext, "id": 9000 + ext["nro_oc"]})
        return {
            "success": not errors,
            "stats": {"ordenes_compra": {"ok": ok, "error": len(errors)}},
            "results": {"ordenes_compra": results},
            "errors": errors,
        }

    return _post


class TestOcItemsPermanentSkip:
    def test_oc_permanentemente_rechazada_deja_de_reenviarse(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"), max_attempts=2)
        exporter.attach_retry_store(retry)

        post_calls = []
        with patch.object(exporter, "_post_json", side_effect=_fake_post(post_calls)):
            # Dos corridas consecutivas: agotan max_attempts=2 y la fila pasa a
            # 'permanent' (mismo comportamiento que ya protege a orden_pago).
            exporter.write_batch("oc_items", _COLUMNS, [_ROW_POISON, _ok_row(4001)])
            exporter.write_batch("oc_items", _COLUMNS, [_ROW_POISON, _ok_row(4002)])

        assert len(post_calls) == 2, "las primeras corridas SI deben reintentar"

        items = retry.list_items("oc_items")
        assert len(items) == 1
        assert items[0].status == "permanent"
        assert items[0].attempts == 2

        # Corrida #3: la OC sigue full_load (misma fila de origen), pero ya esta
        # 'permanent' — el mapper debe excluirla y NO volver a pegarle al
        # receptor por ella (antes de este fix, se reenviaba para siempre).
        with patch.object(exporter, "_post_json", side_effect=_fake_post(post_calls)):
            exporter.write_batch("oc_items", _COLUMNS, [_ROW_POISON, _ok_row(4003)])

        assert len(post_calls) == 3, "la OC ok de la corrida #3 SI debe enviarse"
        sent_ocs = [oc["external_id"]["nro_oc"] for oc in post_calls[-1]["ordenes_compra"]]
        assert 3130 not in sent_ocs, "una OC 'permanent' no debe reenviarse nunca mas"
        assert 4003 in sent_ocs

        retry.close()

    def test_requeue_reactiva_el_reintento(self, monkeypatch, tmp_path):
        """Via de recuperacion manual una vez resuelta la causa (ej. se
        recreo el Pedido): RetryStore.requeue() ya existia para esto."""
        exporter = _migrator(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"), max_attempts=1)
        exporter.attach_retry_store(retry)

        post_calls = []
        with patch.object(exporter, "_post_json", side_effect=_fake_post(post_calls)):
            # La transicion a 'permanent' recien queda registrada DESPUES de
            # que el batch se envio y el receptor la volvio a rechazar, asi
            # que hacen falta 2 corridas fallidas para llegar a permanent
            # (aunque max_attempts=1) y una 3ra para verificar la exclusion.
            exporter.write_batch("oc_items", _COLUMNS, [_ROW_POISON, _ok_row(4001)])
            exporter.write_batch("oc_items", _COLUMNS, [_ROW_POISON, _ok_row(4002)])

        assert retry.list_items("oc_items")[0].status == "permanent"

        with patch.object(exporter, "_post_json", side_effect=_fake_post(post_calls)):
            exporter.write_batch("oc_items", _COLUMNS, [_ROW_POISON, _ok_row(4003)])

        sent_ocs_call3 = [oc["external_id"]["nro_oc"] for oc in post_calls[-1]["ordenes_compra"]]
        assert 3130 not in sent_ocs_call3

        requeued = retry.requeue(entity="oc_items")
        assert requeued == 1

        with patch.object(exporter, "_post_json", side_effect=_fake_post(post_calls)):
            exporter.write_batch("oc_items", _COLUMNS, [_ROW_POISON, _ok_row(4004)])

        sent_ocs_call4 = [oc["external_id"]["nro_oc"] for oc in post_calls[-1]["ordenes_compra"]]
        assert 3130 in sent_ocs_call4, "tras requeue() la OC debe volver a intentarse"

        retry.close()
