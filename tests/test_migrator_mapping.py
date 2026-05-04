"""
Tests de mapeo para MigratorExporter — sin llamadas HTTP reales.

Validan que _map_solic_gasto, _map_ped_item, _map_oc_item y
_write_batch_orden_pago construyen los payloads correctos.
"""
import json
from unittest.mock import patch

import pytest

from src.exporter import MigratorExporter, _build_migrator_url, _migrator_endpoint, _paxapos_url


# ─── Fixture: MigratorExporter sin HTTP ──────────────────────────────────────

@pytest.fixture
def exporter():
    """MigratorExporter con lookups mockeados para tests unitarios."""
    with patch("src.exporter.fetch_migrator_lookups") as mock_lookups:
        mock_lookups.return_value = {
            "unidades_de_medida": [{"id": "1", "name": "Unidad"}],
            "tipos_factura": [
                {"id": "2", "name": "Factura A", "codename": "factura_a"},
                {"id": "3", "name": "Factura B", "codename": "factura_b"},
            ],
            "tipos_de_pago": [
                {"id": "4", "name": "Transferencia"}
            ],
        }
        with patch.dict("os.environ", {
            "PAXAPOS_URL": "https://example.com",
            "PAXAPOS_TENANT": "test",
            "PAXAPOS_API_KEY": "key",
            "PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID": "1",
            "PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID": "4",
            "LOCAL_STATE_DB_PATH": ":memory:",
        }):
            exp = MigratorExporter(dry_run=True)
    return exp


# ─── solic_gastos ─────────────────────────────────────────────────────────────

class TestMapSolicGasto:

    def test_mapea_campos_basicos(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "500",
            "FECH_SOLIC": "2026-03-10 00:00:00",
            "IMPORTE_TOT": "1210.50",
            "ESTADO_SOLIC": "C",
            "TIPO_DOC": "factura_a",
            "NRO_DOC": "42",
            "OBSERVACIONES": "Factura de papelería",
        }
        result = exporter._map_solic_gasto(raw)
        assert result is not None
        assert result["external_id"] == {"ejercicio": 2026, "deleg_solic": 1, "nro_solic": 500}
        assert result["Gasto"]["fecha"] == "2026-03-10"
        assert result["Gasto"]["importe_total"] == 1210.50
        assert result["Gasto"]["tipo_factura_id"] == 2
        assert result["Gasto"]["factura_nro"] == "00000042"
        assert result["Gasto"]["observacion"] == "Factura de papelería"

    def test_excluye_anuladas(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "501",
            "FECH_SOLIC": "2026-03-10", "IMPORTE_TOT": "100",
            "ESTADO_SOLIC": "A",
        }
        assert exporter._map_solic_gasto(raw) is None

    def test_sin_fecha_retorna_none(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "502",
            "FECH_SOLIC": "", "IMPORTE_TOT": "100", "ESTADO_SOLIC": "C",
        }
        assert exporter._map_solic_gasto(raw) is None

    def test_sin_importe_retorna_none(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "503",
            "FECH_SOLIC": "2026-03-10", "IMPORTE_TOT": None, "ESTADO_SOLIC": "C",
        }
        assert exporter._map_solic_gasto(raw) is None

    def test_tipo_doc_sin_match_usa_default(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "504",
            "FECH_SOLIC": "2026-03-10", "IMPORTE_TOT": "50",
            "ESTADO_SOLIC": "C", "TIPO_DOC": "DESCONOCIDO",
        }
        result = exporter._map_solic_gasto(raw)
        # default es None cuando PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID no está seteado
        assert result is not None
        assert "tipo_factura_id" not in result["Gasto"]

    def test_nro_doc_cero_no_se_incluye(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "505",
            "FECH_SOLIC": "2026-03-10", "IMPORTE_TOT": "50",
            "ESTADO_SOLIC": "C", "NRO_DOC": "0",
        }
        result = exporter._map_solic_gasto(raw)
        assert result is not None
        assert "factura_nro" not in result["Gasto"]


# ─── _format_date_only ────────────────────────────────────────────────────────

class TestFormatDateOnly:

    def test_datetime_string_recorta_hora(self, exporter):
        assert exporter._format_date_only("2026-03-10 14:30:00") == "2026-03-10"

    def test_solo_fecha(self, exporter):
        assert exporter._format_date_only("2026-03-10") == "2026-03-10"

    def test_vacio_devuelve_string_vacio(self, exporter):
        assert exporter._format_date_only("") == ""
        assert exporter._format_date_only(None) == ""


# ─── orden_pago grouping ──────────────────────────────────────────────────────

class TestWriteBatchOrdenPago:

    def _make_exporter(self):
        with patch("src.exporter.fetch_migrator_lookups") as mock_lookups:
            mock_lookups.return_value = {
                "unidades_de_medida": [],
                "tipos_factura": [],
                "tipos_de_pago": [{"id": "4", "name": "Transferencia"}],
            }
            with patch.dict("os.environ", {
                "PAXAPOS_URL": "https://example.com",
                "PAXAPOS_TENANT": "test",
                "PAXAPOS_API_KEY": "key",
                "PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID": "4",
                "LOCAL_STATE_DB_PATH": ":memory:",
            }):
                return MigratorExporter(dry_run=True)

    def test_agrupa_por_nro_op(self):
        exp = self._make_exporter()

        # Pre-poblar link_store con gastos (simula sync previo de solic_gastos)
        import json
        exp._link_store.save_link(
            entity="gasto",
            source_key=json.dumps({"rafam_ref": "SG-2026-1-100"}, sort_keys=True),
            remote_id="501",
        )
        exp._link_store.save_link(
            entity="gasto",
            source_key=json.dumps({"rafam_ref": "SG-2026-1-200"}, sort_keys=True),
            remote_id="502",
        )

        columns = [
            "EJERCICIO", "NRO_OP", "FECH_OP", "ESTADO_OP",
            "IMPORTE_TOTAL", "CONCEPTO", "NRO_CANCE",
            "SG_DELEG_SOLIC", "SG_NRO_SOLIC",
            "FECH_CONFIRM", "LUG_EMI", "CODIGO_FF", "JURISDICCION",
            "CODIGO_UE", "COD_PROV", "TIPO_OP", "TIPO_DOC", "NRO_DOC",
            "ANIO_DOC", "CONFIRMADO", "CANT_IMPRES", "FECH_ANUL",
            "MOTIVO_ANUL", "OBSERVACIONES", "COD_EMP",
            "IMPORTE_BONIFICACION", "IMPORTE_DEDUCCIONES", "ASIENTO",
            "ASIENTO_ANUL", "MONTO_SIN_IVA", "DEUDA", "BLOQUEADA",
            "RECURSO", "PERCIBIDO", "NO_PAGADO", "PAGADO",
            "RECO_DEU_ORDEN", "RECO_DEU_EJERCICIO", "RECO_DEU_COMPRA",
            "RECO_DEU_COMPRA_EJER", "F931", "SICORE",
        ]

        def row(nro_op, sg_deleg, sg_nro, estado="C", importe="500"):
            vals = {
                "EJERCICIO": "2026", "NRO_OP": str(nro_op),
                "FECH_OP": "2026-03-10 00:00:00",
                "ESTADO_OP": estado, "IMPORTE_TOTAL": importe,
                "CONCEPTO": "Pago servicios", "NRO_CANCE": str(sg_nro),
                "SG_DELEG_SOLIC": str(sg_deleg), "SG_NRO_SOLIC": str(sg_nro),
                "FECH_CONFIRM": "2026-03-11 00:00:00",
            }
            return tuple(vals.get(c, "") for c in columns)

        rows = [
            row(1001, 1, 100),
            row(1002, 1, 200),
            row(1003, None, None, estado="N"),  # sin gasto → omitida
        ]

        sent_payloads = []

        def fake_post(url, payload):
            sent_payloads.append(payload)
            return {"stats": {"ordenes_pago": {"ok": 2, "error": 0}}}

        exp._post_json = fake_post
        exp.write_batch("orden_pago", columns, rows)

        assert len(sent_payloads) == 1
        ops = sent_payloads[0]["ordenes_pago"]
        # 1001 y 1002 tienen gasto; 1003 no tiene (SG_DELEG_SOLIC=None)
        assert len(ops) == 2
        ids = {op["external_id"]["nro_op"] for op in ops}
        assert ids == {1001, 1002}
        # verificar que gasto_ids se resolvió a IDs numéricos de Paxapos
        for op in ops:
            assert len(op["gasto_ids"]) == 1
            assert isinstance(op["gasto_ids"][0], int)

    def test_op_anulada_no_se_envia(self):
        exp = self._make_exporter()
        columns = [
            "EJERCICIO", "NRO_OP", "FECH_OP", "ESTADO_OP",
            "IMPORTE_TOTAL", "CONCEPTO", "NRO_CANCE",
            "SG_DELEG_SOLIC", "SG_NRO_SOLIC",
            "FECH_CONFIRM", "LUG_EMI", "CODIGO_FF", "JURISDICCION",
            "CODIGO_UE", "COD_PROV", "TIPO_OP", "TIPO_DOC", "NRO_DOC",
            "ANIO_DOC", "CONFIRMADO", "CANT_IMPRES", "FECH_ANUL",
            "MOTIVO_ANUL", "OBSERVACIONES", "COD_EMP",
            "IMPORTE_BONIFICACION", "IMPORTE_DEDUCCIONES", "ASIENTO",
            "ASIENTO_ANUL", "MONTO_SIN_IVA", "DEUDA", "BLOQUEADA",
            "RECURSO", "PERCIBIDO", "NO_PAGADO", "PAGADO",
            "RECO_DEU_ORDEN", "RECO_DEU_EJERCICIO", "RECO_DEU_COMPRA",
            "RECO_DEU_COMPRA_EJER", "F931", "SICORE",
        ]
        vals = {
            "EJERCICIO": "2026", "NRO_OP": "999",
            "FECH_OP": "2026-03-10", "ESTADO_OP": "A",
            "IMPORTE_TOTAL": "100", "NRO_CANCE": "50",
            "SG_DELEG_SOLIC": "1", "SG_NRO_SOLIC": "50",
            "FECH_CONFIRM": "",
        }
        rows = [tuple(vals.get(c, "") for c in columns)]

        sent = []
        exp._post_json = lambda url, p: sent.append(p) or {"stats": {"ordenes_pago": {"ok": 0}}}
        exp.write_batch("orden_pago", columns, rows)
        assert sent == []  # no se envió nada


# ─── tipo_factura lookup ──────────────────────────────────────────────────────

class TestResolveTipoFacturaId:

    def test_match_por_codename(self, exporter):
        assert exporter._resolve_tipo_factura_id("factura_a") == 2

    def test_match_por_name(self, exporter):
        assert exporter._resolve_tipo_factura_id("Factura B") == 3

    def test_sin_match_retorna_default(self, exporter):
        # default es None cuando PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID no está seteado
        assert exporter._resolve_tipo_factura_id("ORDSE") is None

    def test_none_retorna_default(self, exporter):
        assert exporter._resolve_tipo_factura_id(None) is None


class TestMapRetencion:

    def test_mapea_retencion_con_alias(self, exporter):
        raw = {
            "RET_COD_RET": "GAN",
            "RET_IMPORTE": "50.25",
            "RET_DESCRIPCION": "Retencion Ganancias",
        }
        result = exporter._map_retencion(raw, 2026, 8001)

        assert result is not None
        assert result["external_id"] == {"ejercicio": 2026, "nro_op": 8001, "cod_ret": "GAN"}
        assert result["monto_retenido"] == 50.25
        assert result["tipo"] == "ganancias"
        assert result["numero_certificado"] == "RAFAM-RET-2026-8001-GAN"

    def test_sin_importe_no_mapea(self, exporter):
        assert exporter._map_retencion({"RET_COD_RET": "GAN"}, 2026, 8001) is None


class TestMigratorErrors:

    def test_stats_con_error_falla(self):
        with pytest.raises(RuntimeError):
            MigratorExporter._raise_on_migrator_errors({"stats": {"proveedores": {"error": 1}}})

    def test_errors_array_falla(self):
        with pytest.raises(RuntimeError):
            MigratorExporter._raise_on_migrator_errors({"errors": [{"message": "fallo"}]})


class TestMigratorUrl:

    def test_arma_url_con_paxapos_tenant_y_path(self):
        url = _build_migrator_url(
            "https://proveedores.madariaga.gob.ar/",
            "madariaga",
            "/rafam/migracion/spec.json",
        )

        assert url == "https://proveedores.madariaga.gob.ar/madariaga/rafam/migracion/spec.json"

    def test_endpoint_rechaza_url_completa(self):
        with patch.dict("os.environ", {"PAXAPOS_RAFAM_SPEC_PATH": "https://example.com/spec.json"}):
            with pytest.raises(ValueError):
                _migrator_endpoint("PAXAPOS_RAFAM_SPEC_PATH", "rafam/migracion/spec.json")

    def test_no_acepta_gateway_url_como_alias(self):
        with patch.dict("os.environ", {"GATEWAY_URL": "https://legacy.example.com"}, clear=True):
            with pytest.raises(ValueError):
                _paxapos_url()


# ─── OC items (orden de compra con items) ─────────────────────────────────────

OC_COLUMNS = [
    "EJERCICIO", "UNI_COMPRA", "NRO_OC", "ITEM_OC",
    "DELEG_SOLIC", "NRO_SOLIC", "ITEM_REAL",
    "DESCRIPCION", "CANTIDAD", "IMP_UNITARIO", "CANT_RECIB", "IMPORTE_EJER",
    "COD_PROV",
    "OC_FECH_OC", "OC_OBSERVACIONES", "OC_ESTADO_OC", "OC_FECH_CONFIRM",
    "OC_IMPORTE_TOT", "SG_JURISDICCION",
]


def _oc_row(
    *,
    ejercicio="2026", uni_compra="1", nro_oc="100", item_oc="1",
    deleg_solic="1", nro_solic="500", item_real="1",
    descripcion="Papel A4", cantidad="10", imp_unitario="50.0",
    cant_recib="0", importe_ejer="500",
    cod_prov="99",
    fech_oc="2026-03-15 00:00:00", observaciones="", estado_oc="R",
    fech_confirm="2026-03-16 00:00:00", importe_tot="500.00",
    sg_jurisdiccion="",
):
    vals = {
        "EJERCICIO": ejercicio, "UNI_COMPRA": uni_compra,
        "NRO_OC": nro_oc, "ITEM_OC": item_oc,
        "DELEG_SOLIC": deleg_solic, "NRO_SOLIC": nro_solic,
        "ITEM_REAL": item_real,
        "DESCRIPCION": descripcion, "CANTIDAD": cantidad,
        "IMP_UNITARIO": imp_unitario, "CANT_RECIB": cant_recib,
        "IMPORTE_EJER": importe_ejer,
        "COD_PROV": cod_prov,
        "OC_FECH_OC": fech_oc, "OC_OBSERVACIONES": observaciones,
        "OC_ESTADO_OC": estado_oc, "OC_FECH_CONFIRM": fech_confirm,
        "OC_IMPORTE_TOT": importe_tot, "SG_JURISDICCION": sg_jurisdiccion,
    }
    return tuple(vals.get(c, "") for c in OC_COLUMNS)


class TestWriteBatchOcItems:
    """Tests para _write_batch_oc_items / _write_batch_orden_compra."""

    def _make_exporter_with_prov(self, cod_prov="99", remote_prov_id="777"):
        """Crea MigratorExporter con un proveedor pre-linkeado."""
        with patch("src.exporter.fetch_migrator_lookups") as mock_lookups:
            mock_lookups.return_value = {
                "unidades_de_medida": [{"id": "1", "name": "Unidad"}],
                "tipos_factura": [],
                "tipos_de_pago": [],
            }
            with patch.dict("os.environ", {
                "PAXAPOS_URL": "https://example.com",
                "PAXAPOS_TENANT": "test",
                "PAXAPOS_API_KEY": "key",
                "PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID": "1",
                "PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID": "4",
                "LOCAL_STATE_DB_PATH": ":memory:",
            }):
                exp = MigratorExporter(dry_run=True)
        if cod_prov and remote_prov_id:
            exp._link_store.save_link(
                entity="proveedores",
                source_key=cod_prov,
                remote_id=remote_prov_id,
            )
        exp._link_store.save_link(
            entity="centro_costo",
            source_key=json.dumps({"jurisdiccion": "1110104000"}, sort_keys=True),
            remote_id="1",
        )
        return exp

    # ── OC con proveedor válido: se envía correctamente ──

    def test_oc_con_proveedor_se_envia(self):
        exp = self._make_exporter_with_prov()
        rows = [
            _oc_row(item_oc="1", cantidad="10", imp_unitario="50"),
            _oc_row(item_oc="2", cantidad="5", imp_unitario="100"),
        ]
        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        assert len(sent) == 1
        ocs = sent[0]["ordenes_compra"]
        assert len(ocs) == 1
        assert ocs[0]["Pedido"]["proveedor_id"] == 777
        assert ocs[0]["Pedido"]["tipo"] == "orden_compra"
        assert len(ocs[0]["items"]) == 2

    # ── OC sin proveedor: se omite ──

    def test_oc_sin_proveedor_no_se_envia(self):
        exp = self._make_exporter_with_prov(cod_prov=None, remote_prov_id=None)
        rows = [_oc_row(cod_prov="999")]  # proveedor 999 no existe en links

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 0, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)
        assert sent == []

    def test_oc_sin_proveedor_no_loguea_duplicado(self):
        """Una OC con 3 items y sin proveedor loguea solo 1 warning."""
        exp = self._make_exporter_with_prov(cod_prov=None, remote_prov_id=None)
        rows = [
            _oc_row(item_oc="1", cod_prov="999"),
            _oc_row(item_oc="2", cod_prov="999"),
            _oc_row(item_oc="3", cod_prov="999"),
        ]
        import logging
        with patch.object(logging.getLogger("src.exporter"), "warning") as mock_warn:
            exp.write_batch("oc_items", OC_COLUMNS, rows)
        # Solo 1 warning para la OC, no 3
        oc_skip_calls = [
            c for c in mock_warn.call_args_list
            if "omitida" in str(c)
        ]
        assert len(oc_skip_calls) == 1

    # ── Fecha created: se envía la FECH_OC real ──

    def test_fecha_created_se_envia(self):
        exp = self._make_exporter_with_prov()
        rows = [_oc_row(fech_oc="2026-03-15 00:00:00")]

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        pedido = sent[0]["ordenes_compra"][0]["Pedido"]
        assert pedido["created"] == "2026-03-15 00:00:00"

    def test_fecha_created_vacia_no_se_incluye(self):
        exp = self._make_exporter_with_prov()
        rows = [_oc_row(fech_oc="")]

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        pedido = sent[0]["ordenes_compra"][0]["Pedido"]
        assert "created" not in pedido

    # ── Observación: solo la real, no traza ──

    def test_observacion_real_se_incluye(self):
        exp = self._make_exporter_with_prov()
        rows = [_oc_row(observaciones="Entregar en depósito central")]

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        pedido = sent[0]["ordenes_compra"][0]["Pedido"]
        assert pedido["observacion"] == "Entregar en depósito central"

    def test_observacion_vacia_no_se_incluye(self):
        exp = self._make_exporter_with_prov()
        rows = [_oc_row(observaciones="")]

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        pedido = sent[0]["ordenes_compra"][0]["Pedido"]
        assert "observacion" not in pedido
        # Asegurar que NO aparece "Migrado RAFAM OC ..."
        assert "Migrado" not in str(pedido)

    # ── Items: envían name, no descripcion ──

    def test_item_no_envia_descripcion(self):
        exp = self._make_exporter_with_prov()
        rows = [_oc_row(descripcion="Papel A4 resma 500 hojas")]

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        item = sent[0]["ordenes_compra"][0]["items"][0]
        assert "descripcion" not in item
        assert "observacion" not in item

    def test_item_envia_name_para_mercaderia(self):
        exp = self._make_exporter_with_prov()
        rows = [_oc_row(descripcion="Papel A4 resma 500 hojas")]

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        item = sent[0]["ordenes_compra"][0]["items"][0]
        assert item["name"] == "Papel A4 resma 500 hojas"

    def test_item_tiene_campos_basicos(self):
        exp = self._make_exporter_with_prov()
        rows = [_oc_row(cantidad="10", imp_unitario="50.5", cant_recib="3")]

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        item = sent[0]["ordenes_compra"][0]["items"][0]
        assert item["cantidad"] == 10.0
        assert item["precio"] == 50.5
        assert item["recibida_cantidad"] == 3.0
        assert "mercaderia_external_ref" in item
        assert item["mercaderia_external_ref"]["entity"] == "oc_items"
        assert item["unidad_de_medida_id"] == 5  # Unidad

    # ── Varias OCs en un batch ──

    def test_multiples_ocs_se_agrupan_correctamente(self):
        exp = self._make_exporter_with_prov()
        rows = [
            _oc_row(nro_oc="100", item_oc="1"),
            _oc_row(nro_oc="100", item_oc="2"),
            _oc_row(nro_oc="200", item_oc="1"),
        ]

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 2, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        ocs = sent[0]["ordenes_compra"]
        assert len(ocs) == 2
        oc_100 = next(o for o in ocs if o["external_id"]["nro_oc"] == 100)
        oc_200 = next(o for o in ocs if o["external_id"]["nro_oc"] == 200)
        assert len(oc_100["items"]) == 2
        assert len(oc_200["items"]) == 1

    # ── Centro de costo ──

    def test_centro_costo_id_se_incluye(self):
        exp = self._make_exporter_with_prov()
        rows = [_oc_row(sg_jurisdiccion="1110104000")]  # Secretaria de Salud = CC 1

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        oc = sent[0]["ordenes_compra"][0]
        assert oc["centro_costo_id"] == 1  # Salud

    def test_centro_costo_id_sin_jurisdiccion_no_se_incluye(self):
        exp = self._make_exporter_with_prov()
        rows = [_oc_row(sg_jurisdiccion="")]

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        oc = sent[0]["ordenes_compra"][0]
        assert "centro_costo_id" not in oc
