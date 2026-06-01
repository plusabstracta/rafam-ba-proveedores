from __future__ import annotations

import io
import json
from urllib import error
from unittest.mock import patch

import pytest

from src.exporter import (
    AlreadyExistsError,
    CsvExporter,
    GatewayExporter,
    MigratorExporter,
    NoopExporter,
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


def _gateway(monkeypatch, tmp_path, *, force_update=False):
    monkeypatch.setenv("PAXAPOS_URL", "https://example.test")
    monkeypatch.setenv("PAXAPOS_TENANT", "tenant")
    monkeypatch.setenv("PAXAPOS_JWT", "jwt")
    monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(tmp_path / "gateway_links.db"))
    monkeypatch.setenv("PAXAPOS_VERIFY_SSL", "true")
    return GatewayExporter(force_update=force_update)


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


def test_csv_exporter_writes_and_closes(tmp_path):
    exporter = CsvExporter(tmp_path)
    exporter.write_batch("proveedores", ["id", "name"], [(1, "Uno"), (2, "Dos")])
    exporter.write_batch("proveedores", ["id", "name"], [(3, "Tres")])
    exporter.close()

    [path] = tmp_path.glob("proveedores_*.csv")
    assert path.read_text(encoding="utf-8").splitlines() == [
        "id,name",
        "1,Uno",
        "2,Dos",
        "3,Tres",
    ]
    assert exporter._files == {}
    assert exporter._writers == {}


def test_noop_and_factory_branches(monkeypatch, tmp_path):
    NoopExporter().write_batch("x", ["a"], [(1,)])
    assert isinstance(build_exporter("noop"), NoopExporter)

    with patch("src.exporter.CsvExporter", return_value="csv"):
        assert build_exporter("csv") == "csv"
    with patch("src.exporter.GatewayExporter", return_value="gateway") as gateway:
        assert build_exporter("gateway", force_update=True) == "gateway"
        gateway.assert_called_once_with(force_update=True)
    with patch("src.exporter.MigratorExporter", return_value="migrator") as migrator:
        assert build_exporter("migrator", dry_run=True) == "migrator"
        migrator.assert_called_once_with(dry_run=True)
    with pytest.raises(ValueError):
        build_exporter("desconocido")


class TestGatewayExporter:
    def test_helpers_and_extractors(self, monkeypatch, tmp_path):
        exporter = _gateway(monkeypatch, tmp_path)

        assert exporter._headers()["Authorization"] == "Bearer jwt"
        assert exporter._build_update_url("proveedores", "9") == "https://example.test/account/proveedores/edit/9.json"
        assert exporter._normalize_cuit("20-12345678-3") == "20123456783"
        assert exporter._normalize_cuit("123") is None
        assert exporter._source_key("proveedores", {"COD_PROV": 7}) == "7"
        assert exporter._source_key("otra", {"COD_PROV": 7}) is None
        assert "id=4" in exporter._summarize_gateway_payload({"Proveedor": {"id": 4, "cuit": "x"}})
        assert "validationErrors" in exporter._summarize_gateway_payload({"validationErrors": {"x": []}})
        assert exporter._summarize_gateway_payload(["x"]) == "payload no-objeto"
        assert exporter._is_duplicate_cuit_error(
            {"validationErrors": {"cuit": ["El CUIT ya existe"]}}
        )
        assert not exporter._is_duplicate_cuit_error({"validationErrors": {"name": ["bad"]}})

        assert exporter._extract_provider_id_from_index_payload(
            [{"id": 10, "value": "Proveedor (20-12345678-3)"}],
            "20123456783",
        ) == "10"
        assert exporter._extract_provider_id_from_index_payload({"bad": []}, "20123456783") is None
        assert exporter._extract_provider_id_from_search_payload(
            {"proveedores": [{"id": 11, "cuit": "20-12345678-3"}]},
            "20123456783",
        ) == "11"
        assert exporter._extract_provider_id_from_search_payload({"proveedores": "bad"}, "x") is None

    def test_post_json_success_and_gateway_response_errors(self, monkeypatch, tmp_path):
        exporter = _gateway(monkeypatch, tmp_path)
        url = "https://example.test/account/proveedores.json"
        response = _FakeHttpResponse(
            json.dumps({"Proveedor": {"id": 8}}).encode(),
            url=url,
        )
        with patch("src.exporter._http_request_with_retries", return_value=response):
            assert exporter._post_json(url, {"Proveedor": {"name": "Acme"}}) == {"Proveedor": {"id": 8}}

        duplicate = _FakeHttpResponse(
            json.dumps({"validationErrors": {"cuit": ["CUIT ya existe"]}}).encode(),
            url=url,
        )
        with patch("src.exporter._http_request_with_retries", return_value=duplicate):
            with pytest.raises(AlreadyExistsError):
                exporter._post_json(url, {"Proveedor": {"name": "Acme"}})

        validation = _FakeHttpResponse(
            json.dumps({"validationErrors": {"name": ["required"]}}).encode(),
            url=url,
        )
        with patch("src.exporter._http_request_with_retries", return_value=validation):
            with pytest.raises(RuntimeError, match="validacion"):
                exporter._post_json(url, {"Proveedor": {"name": ""}})

    def test_post_json_rejects_redirect_html_http_and_url_errors(self, monkeypatch, tmp_path):
        exporter = _gateway(monkeypatch, tmp_path)
        url = "https://example.test/account/proveedores.json"

        redirect = _FakeHttpResponse(b"{}", url="https://example.test/login")
        with patch("src.exporter._http_request_with_retries", return_value=redirect):
            with pytest.raises(RuntimeError, match="Redirect"):
                exporter._post_json(url, {"Proveedor": {"name": "Acme"}})

        html = _FakeHttpResponse(b"<html></html>", url=url, content_type="text/html")
        with patch("src.exporter._http_request_with_retries", return_value=html):
            with pytest.raises(RuntimeError, match="no JSON"):
                exporter._post_json(url, {"Proveedor": {"name": "Acme"}})

        http_error = error.HTTPError(url, 500, "boom", {}, io.BytesIO(b"server"))
        with patch("src.exporter._http_request_with_retries", side_effect=http_error):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                exporter._post_json(url, {"Proveedor": {"name": "Acme"}})

        with patch("src.exporter._http_request_with_retries", side_effect=error.URLError("dns")):
            with pytest.raises(RuntimeError, match="URL error"):
                exporter._post_json(url, {"Proveedor": {"name": "Acme"}})

    def test_get_json_and_lookup_fallbacks(self, monkeypatch, tmp_path):
        exporter = _gateway(monkeypatch, tmp_path)
        url = "https://example.test/account/proveedores/index.json?cuit=20123456783"
        response = _FakeHttpResponse(b'[{"id": 6, "value": "Acme (20-12345678-3)"}]', url=url)
        with patch("src.exporter._http_request_with_retries", return_value=response):
            assert exporter._get_json(url) == [{"id": 6, "value": "Acme (20-12345678-3)"}]

        with patch.object(exporter, "_get_json", return_value=[{"id": 6, "value": "Acme (20-12345678-3)"}]):
            assert exporter._lookup_proveedor_id_by_cuit("20123456783") == "6"

        def fallback(url):
            if "index" in url:
                raise RuntimeError("index unavailable")
            return {"proveedores": [{"id": 7, "cuit": "20-12345678-3"}]}

        with patch.object(exporter, "_get_json", side_effect=fallback):
            assert exporter._lookup_proveedor_id_by_cuit("20123456783") == "7"

        with patch.object(exporter, "_get_json", side_effect=RuntimeError("down")):
            assert exporter._lookup_proveedor_id_by_cuit("20123456783") is None
            assert exporter._lookup_proveedores_enabled is False

    def test_write_batch_create_skip_update_duplicate_and_errors(self, monkeypatch, tmp_path):
        columns = ["COD_PROV", "FANTASIA", "RAZON_SOCIAL", "CUIT", "COD_IVA"]
        row = ("1", "Acme", "Acme SA", "20-12345678-3", "RINS")

        exporter = _gateway(monkeypatch, tmp_path)
        with patch.object(exporter, "_post_json", return_value={"Proveedor": {"id": 50}}) as post:
            exporter.write_batch("proveedores", columns, [row])
        assert post.call_count == 1
        assert exporter._link_store.get_remote_id("proveedores", "1") == "50"

        with patch.object(exporter, "_post_json") as post:
            exporter.write_batch("proveedores", columns, [row])
        post.assert_not_called()

        updater = _gateway(monkeypatch, tmp_path, force_update=True)
        updater._link_store.save_link("proveedores", "2", "77", cuit="20123456783")
        update_row = ("2", "Acme", "Acme SA", "20-12345678-3", "RINS")
        with patch.object(updater, "_post_json", return_value={}) as post:
            updater.write_batch("proveedores", columns, [update_row])
        assert "edit/77.json" in post.call_args.args[0]

        duplicate = _gateway(monkeypatch, tmp_path)
        duplicate_error = AlreadyExistsError(
            "ya existe",
            parsed={"validationErrors": {"cuit": ["CUIT ya existe"]}},
        )
        with patch.object(duplicate, "_post_json", side_effect=duplicate_error), patch.object(
            duplicate, "_lookup_proveedor_id_by_cuit", return_value="88"
        ):
            duplicate.write_batch("proveedores", columns, [("3", "Otro", "Otro SA", "20-12345678-3", "RINS")])
        assert duplicate._link_store.get_remote_id("proveedores", "3") == "88"

        failing = _gateway(monkeypatch, tmp_path)
        with patch.object(failing, "_post_json", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="envíos fallidos"):
                failing.write_batch("proveedores", columns, [("4", "Fail", "Fail SA", "20-12345678-3", "RINS")])

        with pytest.raises(ValueError):
            exporter.write_batch("orden_pago", columns, [row])


PED_COLUMNS = [
    "EJERCICIO",
    "NUM_PED",
    "ORDEN",
    "CLASE",
    "TIPO",
    "INCISO",
    "PAR_PRIN",
    "PAR_PARC",
    "CANTIDAD",
    "COSTO_UNI",
    "DESCRIP_BIE",
    "UNI_MED",
    "JURISDICCION",
    "PED_COSTO_TOT",
]


def _ped_row(**overrides):
    data = {
        "EJERCICIO": "2026",
        "NUM_PED": "10",
        "ORDEN": "1",
        "CLASE": "1",
        "TIPO": "2",
        "INCISO": "3",
        "PAR_PRIN": "4",
        "PAR_PARC": "5",
        "CANTIDAD": "2",
        "COSTO_UNI": "15.50",
        "DESCRIP_BIE": "Resma A4",
        "UNI_MED": "UN",
        "JURISDICCION": "1110104000",
        "PED_COSTO_TOT": "31",
    }
    data.update(overrides)
    return tuple(data.get(col, "") for col in PED_COLUMNS)


ORDEN_COMPRA_COLUMNS = [
    "EJERCICIO",
    "UNI_COMPRA",
    "NRO_OC",
    "ITEM_OC",
    "DELEG_SOLIC",
    "NRO_SOLIC",
    "ITEM_REAL",
    "DESCRIPCION",
    "CANTIDAD",
    "IMP_UNITARIO",
    "CANT_RECIB",
    "COD_PROV",
    "OC_FECH_OC",
    "OC_OBSERVACIONES",
    "OC_ESTADO_OC",
    "OC_FECH_CONFIRM",
    "OC_IMPORTE_TOT",
    "SG_JURISDICCION",
    "OC_CC_NRO",
]


def _orden_compra_row(**overrides):
    data = {
        "EJERCICIO": "2026",
        "UNI_COMPRA": "1",
        "NRO_OC": "100",
        "ITEM_OC": "1",
        "DELEG_SOLIC": "2",
        "NRO_SOLIC": "300",
        "ITEM_REAL": "4",
        "DESCRIPCION": "Toner negro",
        "CANTIDAD": "3",
        "IMP_UNITARIO": "100.25",
        "CANT_RECIB": "1",
        "COD_PROV": "99",
        "OC_FECH_OC": "2026-03-10 00:00:00",
        "OC_OBSERVACIONES": "Compra urgente",
        "OC_ESTADO_OC": "R",
        "OC_FECH_CONFIRM": "2026-03-11 00:00:00",
        "OC_IMPORTE_TOT": "300.75",
        "SG_JURISDICCION": "1110104000",
        "OC_CC_NRO": "0001-00000001",
    }
    data.update(overrides)
    return tuple(data.get(col, "") for col in ORDEN_COMPRA_COLUMNS)


class TestMigratorExporterExtraPaths:
    def test_write_batch_dispatch_disabled_and_unknown(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        for entity in ("ped_items", "orden_compra", "solic_gastos", "pedidos"):
            exporter.write_batch(entity, [], [])
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

    def test_write_batch_ped_items_builds_grouped_payload(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        exporter._link_store.save_link("unidad_medida", "UN", "9")
        exporter._link_store.save_link("mercaderia", "name:resma a4", "188")
        exporter._link_store.save_link("mercaderia", "name:lapicera", "189")
        sent = []
        exporter._post_json = lambda _url, payload: sent.append(payload) or {
            "stats": {"pedidos": {"ok": 1, "error": 0}}
        }

        exporter._write_batch_ped_items(
            PED_COLUMNS,
            [_ped_row(ORDEN="1"), _ped_row(ORDEN="2", DESCRIP_BIE="Lapicera")],
        )

        assert len(sent) == 1
        pedido = sent[0]["pedidos"][0]
        assert pedido["external_id"] == {"ejercicio": 2026, "num_ped": 10}
        assert pedido["Pedido"]["monto_presupuestado"] == 31.0
        assert pedido["centro_costo_id"] == 1
        assert len(pedido["items"]) == 2
        assert pedido["items"][0]["unidad_de_medida_id"] == 9
        assert pedido["items"][0]["mercaderia_id"] == 188
        assert "name" not in pedido["items"][0]
        assert "mercaderia_external_ref" not in pedido["items"][0]

    def test_write_batch_ped_items_raises_without_resolvable_items(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path, dry_run=False)
        with pytest.raises(RuntimeError, match="sin items resolubles"):
            exporter._write_batch_ped_items(PED_COLUMNS, [_ped_row(ORDEN="", DESCRIP_BIE="")])

    def test_write_batch_orden_compra_create_anular_skip_and_register(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path, dry_run=False)
        exporter._link_store.save_link("proveedores", "99", "777")
        exporter._link_store.save_link("mercaderia", "name:toner negro", "188")

        anular_key = json.dumps({"ejercicio": 2026, "nro_oc": 200, "uni_compra": 1}, sort_keys=True)
        exporter._link_store.save_link(
            "orden_compra",
            anular_key,
            "880",
            estado_oc="R",
            gasto_linked_refs="",
        )
        same_state_key = json.dumps({"ejercicio": 2026, "nro_oc": 300, "uni_compra": 1}, sort_keys=True)
        exporter._link_store.save_link(
            "orden_compra",
            same_state_key,
            "990",
            estado_oc="R",
            gasto_linked_refs="0001-00000001",
        )

        sent = []

        def fake_post(_url, payload):
            sent.append(payload)
            return {
                "stats": {"ordenes_compra": {"ok": len(payload["ordenes_compra"]), "error": 0}},
                "results": {
                    "ordenes_compra": [
                        {
                            "success": True,
                            "external_id": oc["external_id"],
                            "id": 10000 + oc["external_id"]["nro_oc"],
                            "gasto_ids": [1, 2],
                        }
                        for oc in payload["ordenes_compra"]
                    ]
                },
            }

        exporter._post_json = fake_post
        rows = [
            _orden_compra_row(NRO_OC="100", ITEM_OC="1", OC_ESTADO_OC="R"),
            _orden_compra_row(NRO_OC="100", ITEM_OC="1", NRO_SOLIC="301", OC_ESTADO_OC="R"),
            _orden_compra_row(NRO_OC="100", ITEM_OC="2", OC_ESTADO_OC="R"),
            _orden_compra_row(NRO_OC="200", OC_ESTADO_OC="A"),
            _orden_compra_row(NRO_OC="300", OC_ESTADO_OC="R"),
            _orden_compra_row(NRO_OC="400", OC_ESTADO_OC="N"),
            _orden_compra_row(NRO_OC="500", COD_PROV="404", OC_ESTADO_OC="R"),
        ]
        exporter._write_batch_orden_compra(ORDEN_COMPRA_COLUMNS, rows)

        assert len(sent) == 1
        ordenes = sent[0]["ordenes_compra"]
        assert [oc["external_id"]["nro_oc"] for oc in ordenes] == [100, 200]
        created = ordenes[0]
        assert created["Pedido"]["proveedor_id"] == 777
        assert created["Pedido"]["observacion"] == "Compra urgente"
        assert created["Pedido"]["created"] == "2026-03-10 00:00:00"
        assert len(created["items"]) == 2
        assert "gasto_nro_comprobante" not in created
        assert ordenes[1]["Pedido"]["deleted"] == 1
        assert exporter._link_store.get_link("orden_compra", same_state_key)["remote_id"] == "990"
        skip_key = json.dumps({"ejercicio": 2026, "nro_oc": 400, "uni_compra": 1}, sort_keys=True)
        assert exporter._link_store.get_link("orden_compra", skip_key)["estado_oc"] == "N"

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
        response = _FakeHttpResponse(json.dumps({"ok": True}).encode(), url=url)
        with patch("src.exporter._http_request_with_retries", return_value=response):
            assert exporter._post_json(url, {"cuit": "20-12345678-3", "token": "secret"}) == {"ok": True}
        dumped = dump_path.read_text(encoding="utf-8")
        assert "20-12345678-3" not in dumped
        assert "secret" not in dumped
        assert "***REDACTED***" in dumped

    def test_persist_links_sections_and_error_cases(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path, dry_run=False)
        exporter._persist_links(
            "ped_items",
            {
                "results": {
                    "pedidos": [
                        {"success": True, "external_id": {"ejercicio": 2026, "num_ped": 10}, "id": 1},
                        {"success": True, "external_id": {"ejercicio": 2026}, "id": 2},
                        {"success": False, "external_id": {"ejercicio": 2026, "num_ped": 11}, "id": 3},
                    ]
                }
            },
            {},
        )
        assert exporter._link_store.get_remote_id("pedido", json.dumps({"ejercicio": 2026, "num_ped": 10}, sort_keys=True)) == "1"

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