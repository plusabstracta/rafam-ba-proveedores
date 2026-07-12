from __future__ import annotations

import io
import json
from urllib import error
from unittest.mock import patch

import pytest

from src.exporter import (
    MigratorExporter,
    _build_migrator_url,
    _env_bool,
    _fetch_migrator_json,
    build_exporter,
    fetch_migrator_lookups,
    fetch_migrator_spec,
)


class _FakeHttpResponse:
    def __init__(
        self,
        body=b"{}",
        *,
        status=200,
        url="https://example.test/tenant/rafam/migracion/importar.json",
        content_type="application/json",
    ):
        self._body = body
        self._status = status
        self._url = url
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def getcode(self):
        return self._status

    def geturl(self):
        return self._url

    def read(self):
        return self._body


def _migrator(monkeypatch, tmp_path, *, dry_run=True, lookups=None):
    monkeypatch.setenv("PAXAPOS_URL", "https://example.test")
    monkeypatch.setenv("PAXAPOS_TENANT", "tenant")
    monkeypatch.setenv("PAXAPOS_API_KEY", "key")
    monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(tmp_path / "migrator_links.db"))
    monkeypatch.setenv("PAXAPOS_VERIFY_SSL", "true")
    lookup_payload = lookups or {
        "lookups": {
            "unidades_de_medida": [{"id": "1", "name": "Unidad"}],
            "tipos_factura": [
                {"id": "2", "name": "A", "codename": "factura_a"},
                {"id": "3", "name": "B", "codename": "fab"},
                {"id": "4", "name": "NCB", "codename": "ncb"},
            ],
            "tipos_de_pago": [
                {"id": "4", "name": "Transferencia bancaria"},
                {"id": "5", "name": "Cheque"},
            ],
            "tipos_retencion": [
                {"id": "101", "codigo": "GAN", "name": "Retencion ganancias"},
                {"id": "102", "codename": "iva", "name": "Retencion IVA"},
                {"id": "103", "name": "Ingresos Brutos"},
            ],
            "mercaderias": [{"id": "88", "nombre_compra": "Papel A4"}],
        }
    }
    with patch("src.exporter.fetch_migrator_lookups", return_value=lookup_payload):
        return MigratorExporter(dry_run=dry_run)


def test_build_exporter_returns_migrator():
    with patch("src.exporter.MigratorExporter", return_value="migrator") as migrator:
        assert build_exporter(dry_run=True) == "migrator"
        migrator.assert_called_once_with(dry_run=True)
    with patch("src.exporter.MigratorExporter", return_value="migrator") as migrator:
        assert build_exporter() == "migrator"
        migrator.assert_called_once_with(dry_run=False)


class TestMigratorExporterExtraPaths:
    def test_write_batch_dispatch_empty_and_unknown(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        # solic_gastos con filas vacias es un no-op (lote vacío)
        exporter.write_batch("solic_gastos", [], [])
        # orden_compra ya no es una entidad valida (se migra via oc_items)
        with pytest.raises(ValueError):
            exporter.write_batch("orden_compra", [], [])
        with pytest.raises(ValueError):
            exporter.write_batch("otra", [], [])

    def test_write_batch_proveedores_persists_when_not_dry_run(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path, dry_run=False)
        columns = ["COD_PROV", "FANTASIA", "RAZON_SOCIAL", "CUIT", "COD_IVA", "COD_ESTADO"]
        rows = [("7", "Prov", "Prov SA", "20-12345678-3", "RINS", "A")]

        def fake_post(_url, payload):
            assert payload["proveedores"][0]["external_id"] == {"cod_prov": 7}
            return {
                "stats": {"proveedores": {"ok": 1, "error": 0}},
                "results": {
                    "proveedores": [
                        {"success": True, "external_id": {"cod_prov": 7}, "id": 700}
                    ]
                },
            }

        exporter._post_json = fake_post
        exporter.write_batch("proveedores", columns, rows)

        link = exporter._link_store.get_link("proveedores", "7")
        assert link["remote_id"] == "700"
        assert link["cuit"] == "20123456783"
        assert link["cod_estado"] == "A"
        from src.mappers.proveedores import compute_content_hash
        assert link["content_hash"] == compute_content_hash(dict(zip(columns, rows[0])))

    def test_write_batch_solic_gastos_filters_by_sent_oc_refs(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path, dry_run=False)
        exporter._link_store.save_link("proveedores", "99", "777")
        exporter._link_store.save_link(
            "orden_compra",
            json.dumps({"ejercicio": 2026, "nro_oc": 100, "uni_compra": 1}, sort_keys=True),
            "900",
            gasto_refs="SG-2026-2-300",
        )
        columns = [
            "EJERCICIO",
            "DELEG_SOLIC",
            "NRO_SOLIC",
            "FECH_SOLIC",
            "IMPORTE_TOT",
            "ESTADO_SOLIC",
            "CTA_COMPROB_COUNT",
            "CTA_NRO_COMPROB",
            "CTA_TIPO_COMPROB",
            "CTA_FECH_VENCIM",
            "CTA_IMPORTE_COMPR",
            "CTA_IMPORTE_NETO",
            "OC_COD_PROV",
            "OBSERVACIONES",
        ]

        def row(nro_solic):
            values = {
                "EJERCICIO": "2026",
                "DELEG_SOLIC": "2",
                "NRO_SOLIC": str(nro_solic),
                "FECH_SOLIC": "2026-03-10 00:00:00",
                "IMPORTE_TOT": "1210.50",
                "ESTADO_SOLIC": "C",
                "CTA_COMPROB_COUNT": "1",
                "CTA_NRO_COMPROB": "0001-00012345",
                "CTA_TIPO_COMPROB": "FAB",
                "CTA_FECH_VENCIM": "2026-04-10",
                "CTA_IMPORTE_COMPR": "1210.50",
                "CTA_IMPORTE_NETO": "1000.00",
                "OC_COD_PROV": "99",
                "OBSERVACIONES": "Factura",
            }
            return tuple(values.get(col, "") for col in columns)

        sent = []
        exporter._post_json = lambda _url, payload: sent.append(payload) or {
            "stats": {"gastos": {"ok": 1, "error": 0}},
            "results": {
                "gastos": [
                    {
                        "success": True,
                        "external_id": {"ejercicio": 2026, "deleg_solic": 2, "nro_solic": 300},
                        "id": 123,
                    }
                ]
            },
        }
        exporter._write_batch_solic_gastos(columns, [row(300), row(301)])

        assert len(sent) == 1
        assert len(sent[0]["gastos"]) == 1
        gasto = sent[0]["gastos"][0]["Gasto"]
        assert gasto["proveedor_id"] == 777
        assert gasto["tipo_factura_id"] == 2
        assert gasto["fecha_vencimiento"] == "2026-04-10"
        assert gasto["importe_total"] == 1210.50
        assert gasto["importe_neto"] == 1000.00
        source_key = json.dumps({"ejercicio": 2026, "deleg_solic": 2, "nro_solic": 300}, sort_keys=True)
        assert exporter._link_store.get_remote_id("gasto", source_key) == "123"
        assert exporter._link_store.get_remote_id("gasto", json.dumps({"rafam_ref": "SG-2026-2-300"}, sort_keys=True)) == "123"

    def test_op_helpers_retenciones_refs_and_dump(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path, dry_run=False)
        exporter._link_store.save_link("proveedores", "99", "777")
        oc_key = json.dumps({"ejercicio": 2026, "nro_oc": 100, "uni_compra": 1}, sort_keys=True)
        exporter._link_store.save_link("orden_compra", oc_key, "900", gasto_refs="SG-2026-2-300")

        assert exporter._resolve_gasto_refs_via_oc(2026, "100", "2026") == ["SG-2026-2-300"]
        assert exporter._resolve_gasto_refs_via_oc(2026, None, "2026") == []
        assert exporter._resolve_pedido_id_from_oc_link(
            {"SG_OC_EJERCICIO": "2026", "SG_OC_UNI_COMPRA": "1", "SG_OC_NRO": "100"}
        ) == 900
        assert exporter._pedido_id_from_op_row({"PAXAPOS_PEDIDO_ID": "42"}) == 42
        assert exporter._gasto_external_id_from_ref("SG-2026-2-300") == {
            "ejercicio": 2026,
            "deleg_solic": 2,
            "nro_solic": 300,
        }
        assert exporter._gasto_external_id_from_ref("BAD") is None
        assert exporter._gasto_ref_from_external_id({"rafam_ref": "SG-1-2-3"}) == "SG-1-2-3"
        assert exporter._gasto_ref_from_external_id({"ejercicio": "bad"}) == ""
        assert exporter._split_ref_set(" a, ,b ") == {"a", "b"}

        assert exporter._resolve_tipo_pago_id({"TIPO_CANCE": "CA"}) == 9
        assert exporter._resolve_tipo_pago_id({"TIPO_CANCE": "NO"}) == 1
        assert exporter._resolve_tipo_retencion_id("GAN", "") == 101
        assert exporter._resolve_tipo_retencion_id("iva", "") == 102
        assert exporter._resolve_tipo_retencion_id("", "Ingresos Brutos") == 103
        assert exporter._resolve_tipo_retencion_id_by_alias("iibb") == 103
        assert exporter._retencion_alias("Seguridad social jubilatoria") == "suss"
        assert exporter._map_retencion_dict({"cod_ret": "0", "importe": "0"}, 2026, 1) is None
        assert exporter._map_retencion_dict({"cod_ret": "GAN", "importe": "12.5"}, 2026, 1)[
            "tipo_impuesto_id"
        ] == 101

        dump_path = tmp_path / "payloads.log"
        monkeypatch.setenv("DUMP_PAYLOAD", str(dump_path))
        monkeypatch.setenv("APP_ENV", "dev")
        url = _build_migrator_url("https://example.test", "tenant", "rafam/migracion/importar.json")
        assert _build_migrator_url("https://example.test", "tenant", "https://api.test/importar.json") == "https://api.test/importar.json"
        response = _FakeHttpResponse(json.dumps({"ok": True}).encode(), url=url)
        with patch("src.exporter._http_request_with_retries", return_value=response):
            assert exporter._post_json(url, {"cuit": "20-12345678-3", "token": "secret"}) == {"ok": True}
        dumped = dump_path.read_text(encoding="utf-8")
        assert "20-12345678-3" not in dumped
        assert "secret" not in dumped
        assert "***REDACTED***" in dumped

    def test_persist_links_sections_and_error_cases(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path, dry_run=False)

        op_source = json.dumps({"ejercicio": 2026, "nro_op": 9}, sort_keys=True)
        exporter._persist_links(
            "orden_pago",
            {
                "results": {
                    "ordenes_pago": [
                        {"success": True, "external_id": {"ejercicio": 2026, "nro_op": 9}, "id": 90},
                        {"success": True, "external_id": {"ejercicio": 2026}, "id": 91},
                    ]
                }
            },
            {op_source: {"ESTADO_OP": "C", "CONFIRMADO": "S", "FECH_CONFIRM": "2026-03-10", "IMPORTE_TOTAL": "100"}},
        )
        assert exporter._link_store.get_link("orden_pago", op_source)["remote_id"] == "90"

        assert exporter._lookup_list({"bad": []}, "missing") == []
        assert exporter._build_single_index([{"id": 1, "name": "Á B"}, {"id": 2, "name": ""}], "name") == {"a b": {"id": 1, "name": "Á B"}}
        assert exporter._to_int("bad") is None
        assert exporter._normalize_text(" Á-B  ") == "a b"


class TestMigratorFetchHelpers:
    def test_fetch_migrator_json_success_errors_and_wrappers(self, monkeypatch):
        monkeypatch.setenv("PAXAPOS_URL", "https://example.test")
        monkeypatch.setenv("PAXAPOS_TENANT", "tenant")
        monkeypatch.setenv("PAXAPOS_API_KEY", "key")
        monkeypatch.setenv("PAXAPOS_VERIFY_SSL", "false")
        url = "https://example.test/tenant/rafam/migracion/spec.json"
        response = _FakeHttpResponse(b'{"entities": []}', url=url)

        with patch("src.exporter._http_request_with_retries", return_value=response):
            assert fetch_migrator_spec() == {"entities": []}

        html = _FakeHttpResponse(b"<html></html>", url=url, content_type="text/html")
        with patch("src.exporter._http_request_with_retries", return_value=html):
            with pytest.raises(RuntimeError, match="no JSON"):
                _fetch_migrator_json("PAXAPOS_RAFAM_SPEC_PATH", "rafam/migracion/spec.json")

        http_error = error.HTTPError(url, 401, "unauthorized", {}, io.BytesIO(b"no"))
        with patch("src.exporter._http_request_with_retries", side_effect=http_error):
            with pytest.raises(RuntimeError, match="HTTP 401"):
                _fetch_migrator_json("PAXAPOS_RAFAM_SPEC_PATH", "rafam/migracion/spec.json")

        with patch("src.exporter._http_request_with_retries", side_effect=error.URLError("dns")):
            with pytest.raises(RuntimeError, match="URL error"):
                _fetch_migrator_json("PAXAPOS_RAFAM_SPEC_PATH", "rafam/migracion/spec.json")

        monkeypatch.delenv("PAXAPOS_API_KEY")
        response = _FakeHttpResponse(b'{"spec": {}}', url=url)
        with patch("src.exporter._http_request_with_retries", return_value=response):
            assert fetch_migrator_spec() == {"spec": {}}

        with pytest.raises(ValueError, match="PAXAPOS_API_KEY"):
            _fetch_migrator_json("PAXAPOS_RAFAM_SPEC_PATH", "rafam/migracion/spec.json")

    def test_fetch_migrator_lookups_fallback_merge_and_failure(self):
        with patch("src.exporter._fetch_migrator_json", side_effect=[RuntimeError("full"), {"a": [1]}, {"b": [2]}]):
            merged = fetch_migrator_lookups()
            assert merged["a"] == [1]
            assert merged["b"] == [2]
            assert "_partial_errors" in merged

        with patch("src.exporter._fetch_migrator_json", return_value={"one": [1]}) as fetch:
            assert fetch_migrator_lookups([" one "]) == {"one": [1]}
            assert fetch.call_args.kwargs["query_params"] == {"only": "one"}

        with patch("src.exporter._fetch_migrator_json", side_effect=[RuntimeError("a"), {"b": [2]}]):
            merged = fetch_migrator_lookups(["a", "b"])
            assert merged["b"] == [2]
            assert "a" in merged["_partial_errors"]

        with patch("src.exporter._fetch_migrator_json", side_effect=RuntimeError("down")):
            with pytest.raises(RuntimeError, match="Todas"):
                fetch_migrator_lookups(["a", "b"])

    def test_env_bool(self, monkeypatch):
        monkeypatch.setenv("FLAG", "yes")
        assert _env_bool("FLAG") is True
        monkeypatch.setenv("FLAG", "0")
        assert _env_bool("FLAG") is False
        monkeypatch.delenv("FLAG")
        assert _env_bool("FLAG", default="on") is True