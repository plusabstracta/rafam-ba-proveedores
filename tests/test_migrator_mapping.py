"""
Tests de mapeo para MigratorExporter — sin llamadas HTTP reales.

Validan que _map_oc_item y _write_batch_orden_pago construyen los payloads correctos.
"""
import json
from unittest.mock import patch

import pytest

from src.exporter import MigratorExporter, _build_migrator_url, _migrator_endpoint, _paxapos_url
from src.gateway_mapper import map_proveedor_migrator_row


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
            "tipos_retencion": [
                {"id": "102", "name": "Retención de IVA"},
                {"id": "103", "name": "Retención de Ganancias"},
                {"id": "104", "name": "Retención de IIBB"},
                {"id": "105", "name": "Retención SUSS"},
            ],
            "mercaderias": [{"id": "88", "nombre_compra": "Papel A4"}],
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


def test_proveedor_rnis_mapea_iva_condicion():
    result = map_proveedor_migrator_row({
        "COD_PROV": "7",
        "FANTASIA": "Proveedor RNIS",
        "RAZON_SOCIAL": "Proveedor RNIS SA",
        "CUIT": "30-12345678-9",
        "COD_IVA": "RNIS",
    })

    assert result is not None
    # RNIS (Resp. No Inscripto, derogado) -> No Categorizado (id 5)
    assert result["Proveedor"]["iva_condicion_id"] == 5


def test_proveedor_normaliza_espacios_multiples():
    result = map_proveedor_migrator_row({
        "COD_PROV": "15",
        "FANTASIA": "  GARCIA   ALE  \n  S.R.L. ",
        "RAZON_SOCIAL": "GARCIA   ALE   S.R.L.",
        "CUIT": "30-12345678-9",
    })

    assert result is not None
    assert result["Proveedor"]["name"] == "GARCIA ALE S.R.L."
    assert result["Proveedor"]["razon_social"] == "GARCIA ALE S.R.L."


def test_proveedor_monot_mapea_a_monotributo():
    result = map_proveedor_migrator_row({
        "COD_PROV": "8",
        "FANTASIA": "Mono Prov",
        "CUIT": "20-12345678-3",
        "COD_IVA": "MONOT",
    })
    assert result is not None
    assert result["Proveedor"]["iva_condicion_id"] == 6


def test_proveedor_rins_mapea_a_responsable_inscripto():
    result = map_proveedor_migrator_row({
        "COD_PROV": "9",
        "FANTASIA": "RI Prov",
        "CUIT": "30-12345678-9",
        "COD_IVA": "RINS",
    })
    assert result is not None
    assert result["Proveedor"]["iva_condicion_id"] == 1


def test_proveedor_exen_mapea_a_exento():
    result = map_proveedor_migrator_row({
        "COD_PROV": "10",
        "FANTASIA": "Exento Prov",
        "CUIT": "30-12345678-9",
        "COD_IVA": "EXEN",
    })
    assert result is not None
    assert result["Proveedor"]["iva_condicion_id"] == 2


def test_proveedor_excluido_no_se_mapea():
    """Los COD_PROV de la blocklist no deben generar payload (no migran)."""
    from src.config import EXCLUDED_COD_PROV

    # Un puñado representativo de la blocklist (telefonia, caja chica, banco).
    for cod in (50001, 50012, 50087, 50925, 51096):
        assert cod in EXCLUDED_COD_PROV
        result = map_proveedor_migrator_row({
            "COD_PROV": str(cod),
            "FANTASIA": "Excluido",
            "RAZON_SOCIAL": "Proveedor Excluido SA",
            "CUIT": "30-12345678-9",
            "COD_IVA": "RINS",
        })
        assert result is None, f"COD_PROV {cod} deberia estar excluido de la migracion"


def test_proveedor_no_excluido_si_se_mapea():
    """Un COD_PROV fuera de la blocklist sigue migrando normalmente."""
    from src.config import is_cod_prov_excluded

    assert not is_cod_prov_excluded("12345")
    result = map_proveedor_migrator_row({
        "COD_PROV": "12345",
        "FANTASIA": "Proveedor Real",
        "RAZON_SOCIAL": "Proveedor Real SA",
        "CUIT": "30-12345678-9",
        "COD_IVA": "RINS",
    })
    assert result is not None
    assert result["external_id"]["cod_prov"] == 12345


def test_is_cod_prov_excluded_tolera_tipos():
    """El helper acepta int, str, con espacios, y None sin romper."""
    from src.config import is_cod_prov_excluded

    assert is_cod_prov_excluded(50001) is True
    assert is_cod_prov_excluded("50001") is True
    assert is_cod_prov_excluded(" 50001 ") is True
    assert is_cod_prov_excluded(None) is False
    assert is_cod_prov_excluded("no-numerico") is False


class TestMapSolicGasto:

    def test_mapea_campos_basicos(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "500",
            "FECH_SOLIC": "2026-03-10 00:00:00",
            "IMPORTE_TOT": "1210.50",
            "ESTADO_SOLIC": "C",
            "TIPO_DOC": "doc_legacy_ignorado",
            "NRO_DOC": "42",
            "CTA_COMPROB_COUNT": "1",
            "CTA_TIPO_COMPROB": "factura_a",
            "CTA_NRO_COMPROB": "0001-00000042",
            "CTA_IMPORTE_COMPR": "1210.50",
            "CTA_IMPORTE_SIN_IVA": "1000.00",
            "OBSERVACIONES": "Factura de papelería",
        }
        result = exporter._map_solic_gasto(raw)
        assert result is not None
        assert result["external_id"] == {"ejercicio": 2026, "deleg_solic": 1, "nro_solic": 500}
        assert result["Gasto"]["fecha"] == "2026-03-10"
        assert result["Gasto"]["importe_total"] == 1210.50
        assert result["Gasto"]["importe_neto"] == 1000.00
        assert result["Gasto"]["tipo_factura_id"] == 2
        assert result["Gasto"]["punto_de_venta"] == "0001"
        assert result["Gasto"]["factura_nro"] == "00000042"
        assert result["Gasto"]["observacion"] == "Factura de papelería"

    def test_mapea_importes_crudos_cta_con_fallback_legacy(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "510",
            "FECH_SOLIC": "2026-03-10",
            "IMPORTE_TOT": "9999.99",
            "ESTADO_SOLIC": "C",
            "CTA_COMPROB_COUNT": "1",
            "CTA_TIPO_COMPROB": "factura_b",
            "CTA_NRO_COMPROB": "0001-00000051",
            "CTA_IMPORTE_COMPR": "2420.00",
            "CTA_IMPORTE_NETO": "2000.00",
            "CTA_IMPORTE_SIN_IVA": "1900.00",
        }

        result = exporter._map_solic_gasto(raw)

        assert result is not None
        assert result["Gasto"]["importe_total"] == 2420.00
        assert result["Gasto"]["importe_neto"] == 2000.00

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
            "CTA_COMPROB_COUNT": "1", "CTA_NRO_COMPROB": "0001-00000050",
            "CTA_TIPO_COMPROB": "DESCONOCIDO",
        }
        result = exporter._map_solic_gasto(raw)
        # Default RAFAM_TIPO_COMPROB_DEFAULT_ID = 7 (Otros) cuando no matchea
        assert result is not None
        assert result["Gasto"].get("tipo_factura_id") == 7

    def test_sin_cta_comprob_no_mapea(self, exporter):
        raw = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "505",
            "FECH_SOLIC": "2026-03-10", "IMPORTE_TOT": "50",
            "ESTADO_SOLIC": "C", "NRO_DOC": "42",
        }
        assert exporter._map_solic_gasto(raw) is None


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

        columns = [
            "EJERCICIO", "NRO_OP", "FECH_OP", "ESTADO_OP",
            "IMPORTE_TOTAL", "CONCEPTO", "NRO_CANCE",
            "SG_DELEG_SOLIC", "SG_NRO_SOLIC",
            "OPI_NRO_COMPROB", "pedido_id",
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

        def row(nro_op, sg_deleg, sg_nro, estado="N", importe="500", confirmado="S", fech_confirm="2026-03-11 00:00:00", cc_nro="0001-00000042"):
            vals = {
                "EJERCICIO": "2026", "NRO_OP": str(nro_op),
                "FECH_OP": "2026-03-10 00:00:00",
                "ESTADO_OP": estado, "IMPORTE_TOTAL": importe,
                "CONCEPTO": "Pago servicios", "NRO_CANCE": str(sg_nro),
                "SG_DELEG_SOLIC": str(sg_deleg), "SG_NRO_SOLIC": str(sg_nro),
                "OPI_NRO_COMPROB": cc_nro,
                "pedido_id": "789",
                "CONFIRMADO": confirmado, "FECH_CONFIRM": fech_confirm,
            }
            return tuple(vals.get(c, "") for c in columns)

        rows = [
            row(1001, 1, 100, estado="C", cc_nro="0001-00000100"),
            row(1002, 1, 200, estado="C", cc_nro="0001-00000200"),
            row(1003, None, None, estado="C", cc_nro=""),  # sin CC_NRO -> omitida
            row(1004, 1, 100, estado="A"),  # anulada -> omitida por estado
            row(1005, 1, 100, estado="C", confirmado="N"),  # no confirmada -> omitida
            row(1006, 1, 100, estado="C", fech_confirm=""),  # sin FECH_CONFIRM -> omitida
            row(1007, 1, 100, estado="N", cc_nro="0001-00000107"),  # normal confirmada -> omitida por estado
        ]

        sent_payloads = []

        def fake_post(url, payload):
            sent_payloads.append(payload)
            return {"stats": {"ordenes_pago": {"ok": 2, "error": 0}}}

        exp._post_json = fake_post
        exp.write_batch("orden_pago", columns, rows)

        assert len(sent_payloads) == 1
        ops = sent_payloads[0]["ordenes_pago"]
        assert len(ops) == 2
        ids = {op["external_id"]["nro_op"] for op in ops}
        assert ids == {1001, 1002}
        # verificar que gasto_nro_comprobante se asignó desde OPI_NRO_COMPROB
        assert ops[0]["gasto_nro_comprobante"] == "0001-00000100"
        assert ops[1]["gasto_nro_comprobante"] == "0001-00000200"
        for op in ops:
            assert op["Egreso"]["estado"] == 3
            assert op["Egreso"]["fecha"] == "2026-03-11"
        assert sent_payloads[0]["options"]["auto_create_gasto"] is True

    def test_op_reenvia_pedido_id_sin_resolverlo(self):
        exp = self._make_exporter()

        columns = [
            "EJERCICIO", "NRO_OP", "FECH_OP", "ESTADO_OP",
            "IMPORTE_TOTAL", "CONCEPTO", "NRO_CANCE",
            "SG_DELEG_SOLIC", "SG_NRO_SOLIC",
            "OPI_NRO_COMPROB", "pedido_id", "FECH_CONFIRM", "CONFIRMADO", "COD_PROV",
        ]
        vals = {
            "EJERCICIO": "2026", "NRO_OP": "1001",
            "FECH_OP": "2026-03-10 00:00:00", "ESTADO_OP": "C",
            "IMPORTE_TOTAL": "500", "CONCEPTO": "Pago servicios", "NRO_CANCE": "100",
            "SG_DELEG_SOLIC": "1", "SG_NRO_SOLIC": "100",
            "OPI_NRO_COMPROB": "0001-00000100",
            "pedido_id": "789",
            "CONFIRMADO": "S", "FECH_CONFIRM": "2026-03-11 00:00:00",
        }
        rows = [tuple(vals.get(c, "") for c in columns)]

        sent = []
        exp._post_json = lambda url, p: sent.append(p) or {"stats": {"ordenes_pago": {"ok": 1, "error": 0}}}
        exp.write_batch("orden_pago", columns, rows)

        assert len(sent) == 1
        op = sent[0]["ordenes_pago"][0]
        assert op["gasto_nro_comprobante"] == "0001-00000100"
        assert op["pedido_id"] == 789

    def test_op_sin_oc_en_regcomp_imputado_no_se_envia(self):
        exp = self._make_exporter()
        exp._link_store.save_link("proveedores", "100", remote_id="1000")

        columns = [
            "EJERCICIO", "NRO_OP", "ESTADO_OP", "CONFIRMADO", "FECH_CONFIRM",
            "IMPORTE_TOTAL", "CONCEPTO", "NRO_CANCE", "COD_PROV",
            "OPI_NRO_REG_COMP", "OPI_NRO_COMPROB", "OPI_TIPO_COMPROB", "OPI_COD_PROV",
            "CTA_IMPORTE_COMPR", "CTA_IMPORTE_SIN_IVA", "CTA_FECH_COMPROB", "CTA_FECH_VENCIM",
        ]
        vals = {
            "EJERCICIO": "2026", "NRO_OP": "245",
            "ESTADO_OP": "C", "CONFIRMADO": "S",
            "FECH_CONFIRM": "2026-01-22 00:00:00",
            "IMPORTE_TOTAL": "1750", "CONCEPTO": "Reg.Comp. 236",
            "NRO_CANCE": "372", "COD_PROV": "100",
            "OPI_NRO_REG_COMP": "236",
            "OPI_NRO_COMPROB": "0021-00100640",
            "OPI_TIPO_COMPROB": "TKT",
            "OPI_COD_PROV": "100",
            "CTA_IMPORTE_COMPR": "1750.00",
            "CTA_IMPORTE_SIN_IVA": "1750.00",
            "CTA_FECH_COMPROB": "2026-01-22 00:00:00",
            "CTA_FECH_VENCIM": "2026-01-22 00:00:00",
        }
        rows = [tuple(vals.get(c, "") for c in columns)]

        sent = []
        exp._post_json = lambda url, p: sent.append(p) or {
            "stats": {"ordenes_pago": {"ok": 1, "error": 0}, "gastos": {"ok": 1, "error": 0}}
        }
        exp.write_batch("orden_pago", columns, rows)

        assert sent == []

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

    def test_op_cancelada_no_se_envia(self):
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
            "FECH_OP": "2026-03-10", "ESTADO_OP": "C",
            "IMPORTE_TOTAL": "100", "NRO_CANCE": "50",
            "SG_DELEG_SOLIC": "1", "SG_NRO_SOLIC": "50",
            "CONFIRMADO": "S", "FECH_CONFIRM": "2026-03-11",
        }
        rows = [tuple(vals.get(c, "") for c in columns)]

        sent = []
        exp._post_json = lambda url, p: sent.append(p) or {"stats": {"ordenes_pago": {"ok": 0}}}
        exp.write_batch("orden_pago", columns, rows)
        assert sent == []

    def test_op_emite_gasto_completo_desde_cta_comprob(self):
        """Cuando la OP trae datos de CTA_COMPROB, el payload incluye un Gasto
        completo en la coleccion gastos[] para que Paxapos lo cree con todos
        los campos (no solo el stub de auto_create_gasto)."""
        exp = self._make_exporter()
        # Pre-popular link_proveedores para que el helper resuelva el id remoto
        exp._link_store.save_link("proveedores", "555", remote_id="42")

        columns = [
            "EJERCICIO", "NRO_OP", "ESTADO_OP", "CONFIRMADO", "FECH_CONFIRM",
            "IMPORTE_TOTAL", "IMPORTE_LIQUIDO", "CONCEPTO", "NRO_CANCE", "COD_PROV",
            "SG_DELEG_SOLIC", "SG_NRO_SOLIC",
            "OPI_NRO_COMPROB", "OPI_TIPO_COMPROB", "OPI_COD_PROV",
            "SG_OC_COD_PROV", "pedido_id",
            "CTA_IMPORTE_COMPR", "CTA_IMPORTE_NETO", "CTA_IMPORTE_SIN_IVA",
            "CTA_FECH_COMPROB", "CTA_FECH_VENCIM",
        ]
        vals = {
            "EJERCICIO": "2026", "NRO_OP": "8001",
            "ESTADO_OP": "C", "CONFIRMADO": "S",
            "FECH_CONFIRM": "2026-04-15 00:00:00",
            "IMPORTE_TOTAL": "12100", "IMPORTE_LIQUIDO": "315814.05", "CONCEPTO": "Pago factura",
            "NRO_CANCE": "300", "COD_PROV": "555",
            "SG_DELEG_SOLIC": "1", "SG_NRO_SOLIC": "300",
            "OPI_NRO_COMPROB": "0001-00012345",
            "OPI_TIPO_COMPROB": "FAB",
            "OPI_COD_PROV": "555",
            "SG_OC_COD_PROV": "555",
            "pedido_id": "789",
            "CTA_IMPORTE_COMPR": "12100.00",
            "CTA_IMPORTE_NETO": "10000.00",
            "CTA_IMPORTE_SIN_IVA": "9999.00",
            "CTA_FECH_COMPROB": "2026-04-10 00:00:00",
            "CTA_FECH_VENCIM": "2026-05-10 00:00:00",
        }
        rows = [tuple(vals.get(c, "") for c in columns)]

        sent = []
        exp._post_json = lambda url, p: sent.append(p) or {
            "stats": {"ordenes_pago": {"ok": 1, "error": 0}, "gastos": {"ok": 1, "error": 0}}
        }
        exp.write_batch("orden_pago", columns, rows)

        assert len(sent) == 1
        payload = sent[0]
        # OP enviada con gasto_nro_comprobante
        assert len(payload["ordenes_pago"]) == 1
        op = payload["ordenes_pago"][0]
        assert op["gasto_nro_comprobante"] == "0001-00012345"
        assert op["pedido_id"] == 789
        assert op["importe_total"] == 12100.00
        assert op["importe_neto"] == 315814.05
        assert "neto_transferido" not in op["Egreso"]
        # Gasto enviado con todos los datos fiscales reales
        assert len(payload["gastos"]) == 1
        gasto = payload["gastos"][0]["Gasto"]
        assert gasto["pedido_id"] == 789
        assert gasto["proveedor_id"] == 42
        assert gasto["importe_total"] == 12100.00
        assert gasto["importe_neto"] == 10000.00
        assert gasto["fecha"] == "2026-04-10"
        assert gasto["fecha_vencimiento"] == "2026-05-10"
        assert gasto["punto_de_venta"] == "0001"
        assert gasto["factura_nro"] == "00012345"
        # external_id basado en SG cuando esta disponible
        assert payload["gastos"][0]["external_id"] == {
            "ejercicio": 2026, "deleg_solic": 1, "nro_solic": 300
        }

    def test_op_omite_gasto_si_falta_importe_o_fecha(self):
        """Sin CTA_COMPROB.IMPORTE_COMPR o FECH_COMPROB el gasto no se emite,
        pero la OP igual se envia con gasto_nro_comprobante (Paxapos hara stub)."""
        exp = self._make_exporter()
        exp._link_store.save_link("proveedores", "555", remote_id="42")

        columns = [
            "EJERCICIO", "NRO_OP", "ESTADO_OP", "CONFIRMADO", "FECH_CONFIRM",
            "IMPORTE_TOTAL", "NRO_CANCE", "COD_PROV",
            "SG_DELEG_SOLIC", "SG_NRO_SOLIC",
            "OPI_NRO_COMPROB", "OPI_TIPO_COMPROB", "OPI_COD_PROV", "pedido_id",
        ]
        vals = {
            "EJERCICIO": "2026", "NRO_OP": "8002",
            "ESTADO_OP": "C", "CONFIRMADO": "S",
            "FECH_CONFIRM": "2026-04-15", "IMPORTE_TOTAL": "100",
            "NRO_CANCE": "301", "COD_PROV": "555",
            "SG_DELEG_SOLIC": "1", "SG_NRO_SOLIC": "301",
            "OPI_NRO_COMPROB": "0001-00099999", "OPI_TIPO_COMPROB": "FAB",
            "OPI_COD_PROV": "555",
            "pedido_id": "789",
        }
        rows = [tuple(vals.get(c, "") for c in columns)]

        sent = []
        exp._post_json = lambda url, p: sent.append(p) or {
            "stats": {"ordenes_pago": {"ok": 1, "error": 0}}
        }
        exp.write_batch("orden_pago", columns, rows)

        assert len(sent) == 1
        assert sent[0]["gastos"] == []
        assert sent[0]["ordenes_pago"][0]["gasto_nro_comprobante"] == "0001-00099999"

    def test_op_dedup_gasto_por_proveedor_factura(self):
        """Dos OPs distintas que pagan el mismo comprobante emiten un solo Gasto."""
        exp = self._make_exporter()
        exp._link_store.save_link("proveedores", "555", remote_id="42")

        columns = [
            "EJERCICIO", "NRO_OP", "ESTADO_OP", "CONFIRMADO", "FECH_CONFIRM",
            "IMPORTE_TOTAL", "NRO_CANCE", "COD_PROV",
            "SG_DELEG_SOLIC", "SG_NRO_SOLIC",
            "OPI_NRO_COMPROB", "OPI_TIPO_COMPROB", "OPI_COD_PROV",
            "CTA_IMPORTE_COMPR", "CTA_FECH_COMPROB", "pedido_id",
        ]

        def row(nro_op):
            vals = {
                "EJERCICIO": "2026", "NRO_OP": str(nro_op),
                "ESTADO_OP": "C", "CONFIRMADO": "S",
                "FECH_CONFIRM": "2026-04-15", "IMPORTE_TOTAL": "100",
                "NRO_CANCE": "400", "COD_PROV": "555",
                "SG_DELEG_SOLIC": "1", "SG_NRO_SOLIC": "400",
                "OPI_NRO_COMPROB": "0001-00077777", "OPI_TIPO_COMPROB": "FAB",
                "OPI_COD_PROV": "555",
                "CTA_IMPORTE_COMPR": "200.00", "CTA_FECH_COMPROB": "2026-04-10",
                "pedido_id": "789",
            }
            return tuple(vals.get(c, "") for c in columns)

        rows = [row(9001), row(9002)]
        sent = []
        exp._post_json = lambda url, p: sent.append(p) or {
            "stats": {"ordenes_pago": {"ok": 2, "error": 0}}
        }
        exp.write_batch("orden_pago", columns, rows)

        assert len(sent[0]["gastos"]) == 1, "El comprobante repetido se deduplica"
        assert len(sent[0]["ordenes_pago"]) == 2

    def test_op_con_proveedor_distinto_a_oc_y_a_cc_resuelve_links(self):
        """Caso UTE / cesion de credito: el proveedor de la OP (a quien se
        paga), el de la factura (CTA_COMPROB) y el de la OC original difieren.

        Regla canonica:
          - Egreso.proveedor_id  = ORDEN_PAGO.COD_PROV (cesionario)
          - Gasto.proveedor_id   = OPI_COD_PROV       (emisor de factura)
          - Pedido.proveedor_id  = ORDEN_COMPRA.COD_PROV (vendedor original)
        """
        exp = self._make_exporter()
        # Tres proveedores distintos linkeados en Paxapos.
        exp._link_store.save_link("proveedores", "100", remote_id="1000")  # OP (cesionario)
        exp._link_store.save_link("proveedores", "200", remote_id="2000")  # CC (emisor)
        exp._link_store.save_link("proveedores", "300", remote_id="3000")  # OC (vendedor)
        oc_key = json.dumps(
            {"ejercicio": 2026, "nro_oc": 55, "uni_compra": 1},
            sort_keys=True,
        )
        exp._link_store.save_link("orden_compra", oc_key, remote_id="12345")

        columns = [
            "EJERCICIO", "NRO_OP", "ESTADO_OP", "CONFIRMADO", "FECH_CONFIRM",
            "IMPORTE_TOTAL", "NRO_CANCE", "COD_PROV",
            "SG_DELEG_SOLIC", "SG_NRO_SOLIC",
            "OPI_NRO_COMPROB", "OPI_TIPO_COMPROB", "OPI_COD_PROV",
            "SG_OC_EJERCICIO", "SG_OC_UNI_COMPRA", "SG_OC_NRO", "SG_OC_COD_PROV",
            "CTA_IMPORTE_COMPR", "CTA_FECH_COMPROB",
        ]
        vals = {
            "EJERCICIO": "2026", "NRO_OP": "9100",
            "ESTADO_OP": "C", "CONFIRMADO": "S",
            "FECH_CONFIRM": "2026-04-15 00:00:00",
            "IMPORTE_TOTAL": "5000", "NRO_CANCE": "777",
            "COD_PROV": "100",  # cesionario (a quien pagamos)
            "SG_DELEG_SOLIC": "1", "SG_NRO_SOLIC": "777",
            "OPI_NRO_COMPROB": "0001-00055555", "OPI_TIPO_COMPROB": "FAB",
            "OPI_COD_PROV": "200",  # emisor del comprobante
            "SG_OC_EJERCICIO": "2026", "SG_OC_UNI_COMPRA": "1", "SG_OC_NRO": "55",
            "SG_OC_COD_PROV": "300",  # vendedor original
            "CTA_IMPORTE_COMPR": "5000.00", "CTA_FECH_COMPROB": "2026-04-10",
        }
        rows = [tuple(vals.get(c, "") for c in columns)]

        sent = []
        exp._post_json = lambda url, p: sent.append(p) or {
            "stats": {"ordenes_pago": {"ok": 1, "error": 0}, "gastos": {"ok": 1, "error": 0}}
        }
        exp.write_batch("orden_pago", columns, rows)

        assert len(sent) == 1
        payload = sent[0]
        op = payload["ordenes_pago"][0]
        # Egreso → proveedor de la OP (cesionario). En el payload de Paxapos
        # el proveedor_id va al nivel del row (sibling de "Egreso"), porque
        # representa el destinatario del pago, no un atributo del Egreso.
        assert op.get("proveedor_id") == 1000, (
            f"row.proveedor_id debe ser 1000 (OP.COD_PROV=100), "
            f"got {op.get('proveedor_id')}"
        )
        assert op["pedido_id"] == 12345
        # Gasto → proveedor del CC (emisor de factura)
        assert len(payload["gastos"]) == 1
        assert payload["gastos"][0]["Gasto"]["proveedor_id"] == 2000, (
            f"Gasto.proveedor_id debe ser 2000 (OPI_COD_PROV=200), "
            f"got {payload['gastos'][0]['Gasto']['proveedor_id']}"
        )


# ─── tipo_factura lookup ──────────────────────────────────────────────────────

class TestResolveTipoFacturaId:

    def test_match_por_codename(self, exporter):
        assert exporter._resolve_tipo_factura_id("factura_a") == 2

    def test_match_por_name(self, exporter):
        assert exporter._resolve_tipo_factura_id("Factura B") == 3

    def test_sin_match_retorna_default(self, exporter):
        # Default RAFAM_TIPO_COMPROB_DEFAULT_ID = 7 (Otros)
        assert exporter._resolve_tipo_factura_id("ORDSE") == 7

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

    def test_stats_con_error_parcial_no_falla_por_defecto(self):
        """Comportamiento default: warning si hay filas OK en la misma seccion."""
        MigratorExporter._raise_on_migrator_errors({"stats": {"proveedores": {"ok": 1, "error": 1}}})

    def test_stats_con_error_total_falla_por_defecto(self):
        """Si una seccion tiene 0 OK y errores, el batch no debe avanzar checkpoint."""
        with pytest.raises(RuntimeError, match="todas las filas"):
            MigratorExporter._raise_on_migrator_errors({"stats": {"ordenes_compra": {"ok": 0, "error": 100}}})

    def test_errors_array_no_falla_por_defecto(self):
        """Comportamiento default: log warning, NO raise."""
        MigratorExporter._raise_on_migrator_errors({"errors": [{"message": "fallo"}]})

    def test_stats_con_error_falla_en_modo_estricto(self, monkeypatch):
        """Modo estricto opt-in via RAFAM_STRICT_PARTIAL_ERRORS=true."""
        monkeypatch.setenv("RAFAM_STRICT_PARTIAL_ERRORS", "true")
        with pytest.raises(RuntimeError):
            MigratorExporter._raise_on_migrator_errors({"stats": {"proveedores": {"error": 1}}})

    def test_errors_array_falla_en_modo_estricto(self, monkeypatch):
        monkeypatch.setenv("RAFAM_STRICT_PARTIAL_ERRORS", "true")
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

    def test_endpoint_acepta_url_completa(self):
        with patch.dict("os.environ", {"PAXAPOS_RAFAM_SPEC_PATH": "https://example.com/spec.json"}):
            assert (
                _migrator_endpoint("PAXAPOS_RAFAM_SPEC_PATH", "rafam/migracion/spec.json")
                == "https://example.com/spec.json"
            )

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
    """Tests para _write_batch_oc_items."""

    def _make_exporter_with_prov(self, cod_prov="99", remote_prov_id="777", *, dry_run=True, mercaderias=None):
        """Crea MigratorExporter con un proveedor pre-linkeado."""
        with patch("src.exporter.fetch_migrator_lookups") as mock_lookups:
            mock_lookups.return_value = {
                "unidades_de_medida": [{"id": "1", "name": "Unidad"}],
                "tipos_factura": [],
                "tipos_de_pago": [],
                "mercaderias": mercaderias if mercaderias is not None else [{"id": "88", "nombre_compra": "Papel A4"}],
            }
            with patch.dict("os.environ", {
                "PAXAPOS_URL": "https://example.com",
                "PAXAPOS_TENANT": "test",
                "PAXAPOS_API_KEY": "key",
                "PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID": "1",
                "PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID": "4",
                "LOCAL_STATE_DB_PATH": ":memory:",
            }):
                exp = MigratorExporter(dry_run=dry_run)
        if cod_prov and remote_prov_id:
            exp._link_store.save_link(
                entity="proveedores",
                source_key=cod_prov,
                remote_id=remote_prov_id,
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
        with patch.object(logging.getLogger("src.mappers.oc_items"), "warning") as mock_warn:
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

    # ── Items: se envían con mercaderia_id resuelto; nunca con mercaderia_external_ref ──

    def test_item_no_envia_descripcion(self):
        exp = self._make_exporter_with_prov()
        exp._link_store.save_link("mercaderia", "name:papel a4 resma 500 hojas", "188")
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

    def test_item_resuelve_por_api_y_guarda_link_sin_external_ref(self):
        exp = self._make_exporter_with_prov(dry_run=False, mercaderias=[])
        rows = [_oc_row(descripcion="Papel A4 resma 500 hojas")]

        sent = []
        resolver_calls = []

        def fake_post(url, payload):
            if url == exp._resolver_url:
                resolver_calls.append(payload)
                return {
                    "resolver": {
                        "success": True,
                        "mercaderia_id": 188,
                        "mode": "create_from_name",
                        "barcode": "RAFAM-NAME:abc",
                        "nombre_compra": "Papel A4 resma 500 hojas",
                    }
                }
            sent.append(payload)
            return {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}

        exp._post_json = fake_post
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        item = sent[0]["ordenes_compra"][0]["items"][0]
        assert item["mercaderia_id"] == 188
        assert "name" not in item
        assert "mercaderia_external_ref" not in item
        assert "mercaderia_external_ref" not in resolver_calls[0]
        assert resolver_calls[0]["item"]["name"] == "Papel A4 resma 500 hojas"
        assert resolver_calls[0]["item"]["descripcion"] == "Papel A4 resma 500 hojas"
        assert resolver_calls[0]["item"]["nombre_compra"] == "Papel A4 resma 500 hojas"
        assert resolver_calls[0]["item"]["producto_nombre"] == "Papel A4 resma 500 hojas"
        assert "barcode" not in resolver_calls[0]["item"]
        link = exp._link_store.get_link("mercaderia", "name:papel a4 resma 500 hojas")
        assert link["remote_id"] == "188"
        assert link["barcode"] == "RAFAM-NAME:abc"
        assert link["nombre_compra"] == "Papel A4 resma 500 hojas"

        exp._mercaderia_resolved.clear()

        def fail_if_called(url, payload):
            raise RuntimeError("no debe llamar resolver")

        exp._post_json = fail_if_called
        remapped = exp._map_oc_item(dict(zip(OC_COLUMNS, _oc_row(descripcion="Papel A4 resma 500 hojas"))))
        assert remapped is not None
        assert remapped["mercaderia_id"] == 188

    def test_mercaderia_rafam_autocreada_se_resuelve_por_api_sin_fallback(self):
        with patch("src.exporter.fetch_migrator_lookups") as mock_lookups:
            mock_lookups.return_value = {
                "unidades_de_medida": [{"id": "1", "name": "Unidad"}],
                "tipos_factura": [],
                "tipos_de_pago": [],
                "mercaderias": [
                    {"id": "99", "nombre_compra": "Papel A4 [RAFAM-316ca8e3e0]", "barcode": "RAFAM:abc"},
                ],
            }
            with patch.dict("os.environ", {
                "PAXAPOS_URL": "https://example.com",
                "PAXAPOS_TENANT": "test",
                "PAXAPOS_API_KEY": "key",
                "PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID": "1",
                "PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID": "4",
                "LOCAL_STATE_DB_PATH": ":memory:",
            }, clear=True):
                exp = MigratorExporter(dry_run=False)

        resolver_calls = []

        def fake_post(url, payload):
            resolver_calls.append(payload)
            return {
                "resolver": {
                    "success": True,
                    "mercaderia_id": 123,
                    "mode": "create_from_name",
                    "barcode": "RAFAM-NAME:def",
                    "nombre_compra": "Papel A4",
                }
            }

        exp._post_json = fake_post

        item = exp._map_oc_item(dict(zip(OC_COLUMNS, _oc_row(descripcion="Papel A4"))))
        assert item is not None
        assert item["mercaderia_id"] == 123
        assert "name" not in item
        assert "mercaderia_external_ref" not in item
        assert "mercaderia_external_ref" not in resolver_calls[0]
        assert resolver_calls[0]["item"]["name"] == "Papel A4"
        assert "barcode" not in resolver_calls[0]["item"]

    def test_mercaderia_con_barcode_rafam_y_nombre_limpio_se_reutiliza(self):
        exp = self._make_exporter_with_prov(
            dry_run=False,
            mercaderias=[{"id": "99", "nombre_compra": "Papel A4", "barcode": "RAFAM:abc"}],
        )

        def fail_if_called(url, payload):
            raise RuntimeError("no debe llamar resolver")

        exp._post_json = fail_if_called

        item = exp._map_oc_item(dict(zip(OC_COLUMNS, _oc_row(descripcion="Papel A4"))))

        assert item is not None
        assert item["mercaderia_id"] == 99
        link = exp._link_store.get_link("mercaderia", "name:papel a4")
        assert link["barcode"] == "RAFAM:abc"
        assert link["nombre_compra"] == "Papel A4"

    def test_resolver_rechaza_nombre_generado_con_hash_rafam(self):
        exp = self._make_exporter_with_prov(dry_run=False, mercaderias=[])
        exp._post_json = lambda url, payload: {
            "resolver": {
                "success": True,
                "mercaderia_id": 123,
                "mode": "create_deterministic",
                "barcode": "RAFAM:def",
                "nombre_compra": "Papel A4 [RAFAM-def]",
            }
        }

        with pytest.raises(RuntimeError, match="nombre generado"):
            exp._map_oc_item(dict(zip(OC_COLUMNS, _oc_row(descripcion="Papel A4"))))

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
        assert item["precio_unitario"] == 50.5
        assert item["recibida_cantidad"] == 3.0
        assert "name" in item
        assert "mercaderia_external_ref" not in item
        assert item["unidad_de_medida_id"] == 5  # fallback Unidad (id 5, link_store vacio)

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

    def test_items_se_deduplican_por_item_oc(self):
        """Si el LEFT JOIN a SOLIC_GASTOS o oc_to_cc duplica filas, los
        items no deben duplicarse en el payload (sino los totales se inflan)."""
        exp = self._make_exporter_with_prov()
        # Misma OC con item_oc=1 repetido 3 veces (simulando multi-match SG/CC)
        rows = [
            _oc_row(item_oc="1", cantidad="10", imp_unitario="100", nro_solic="500"),
            _oc_row(item_oc="1", cantidad="10", imp_unitario="100", nro_solic="501"),
            _oc_row(item_oc="1", cantidad="10", imp_unitario="100", nro_solic="502"),
            _oc_row(item_oc="2", cantidad="5", imp_unitario="200", nro_solic="500"),
            _oc_row(item_oc="2", cantidad="5", imp_unitario="200", nro_solic="501"),
        ]

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        items = sent[0]["ordenes_compra"][0]["items"]
        assert len(items) == 2, "Solo 2 items distintos (item_oc 1 y 2), sin duplicados"

    # ── Anulación: R→A sin OP → soft-delete ──

    def test_oc_anulada_sin_op_envia_deleted(self):
        """OC previamente migrada con R, ahora A y sin OP → Pedido.deleted=1."""
        exp = self._make_exporter_with_prov()
        source_key = json.dumps({"ejercicio": 2026, "nro_oc": 100, "uni_compra": 1}, sort_keys=True)
        exp._link_store.save_link(
            "orden_compra", source_key, "880",
            estado_oc="R", gasto_linked_refs="",
        )

        rows = [_oc_row(estado_oc="A")]

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        assert len(sent) == 1
        oc = sent[0]["ordenes_compra"][0]
        assert oc["Pedido"]["deleted"] == 1
        assert "estado_aprobacion" not in oc["Pedido"] or oc["Pedido"]["estado_aprobacion"] != 4
        assert "motivo_rechazo" not in oc["Pedido"]

    # ── Anulación: R→A con OP → NO se envía ──

    def test_oc_anulada_con_op_no_se_envia(self):
        """OC previamente migrada con R, ahora A pero con has_op=1 → no se envía."""
        exp = self._make_exporter_with_prov()
        source_key = json.dumps({"ejercicio": 2026, "nro_oc": 100, "uni_compra": 1}, sort_keys=True)
        exp._link_store.save_link(
            "orden_compra", source_key, "880",
            estado_oc="R", gasto_linked_refs="", has_op="1",
        )

        rows = [_oc_row(estado_oc="A")]

        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_compra": {"ok": 0, "error": 0}}}
        )
        exp.write_batch("oc_items", OC_COLUMNS, rows)

        # No se envía nada a Paxapos
        assert sent == []
        # Pero se registra localmente con estado A
        link = exp._link_store.get_link("orden_compra", source_key)
        assert link is not None
        assert link["estado_oc"] == "A"
        assert link["remote_id"] == "880"  # se preserva

    # ── mark_oc_has_op ──

    def test_mark_oc_has_op(self):
        """mark_oc_has_op actualiza el campo has_op en la tabla de links."""
        exp = self._make_exporter_with_prov()
        source_key = json.dumps({"ejercicio": 2026, "nro_oc": 100, "uni_compra": 1}, sort_keys=True)
        exp._link_store.save_link("orden_compra", source_key, "880", estado_oc="R")

        link_before = exp._link_store.get_link("orden_compra", source_key)
        assert not link_before.get("has_op")

        exp._link_store.mark_oc_has_op(source_key)

        link_after = exp._link_store.get_link("orden_compra", source_key)
        assert link_after["has_op"] == "1"


# ─── Tests para deducciones por OP (ORDEN_PAGO_DEDUC) ─────────────────────


class TestFetchDeduccionesForOps:
    """Valida que fetch_deducciones_for_ops usa ORDEN_PAGO_DEDUC por NRO_OP."""

    def _make_sqlite_with_deducciones(self, tmp_path):
        from sqlalchemy import create_engine, text as sa_text
        db_path = tmp_path / "test_deduc.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        with engine.begin() as conn:
            conn.execute(sa_text("""
                CREATE TABLE ORDEN_PAGO_DEDUC (
                    EJERCICIO TEXT, NRO_OP TEXT, CODIGO_DEDUC TEXT,
                    IMPORTE_RETEN TEXT, ALICUOTA TEXT, COMPROB_DEDUC TEXT,
                    TIPO_GENERAC TEXT, CUENTA TEXT, COEF_CONV_MULTI TEXT,
                    ACTIVIDAD TEXT, TIPO_ALICUOTA TEXT
                )
            """))
            conn.execute(sa_text("""
                CREATE TABLE DEDUCCIONES (
                    CODIGO TEXT, DESCRIPCION TEXT, TIPO_DEDUC TEXT,
                    PORCENTAJE TEXT, SALDO TEXT, DECRIPCION_AB TEXT,
                    CODIGO_AXT TEXT, EJERCICIO TEXT
                )
            """))
            # OP 1392 tiene 1 deducción de 3400
            conn.execute(sa_text(
                "INSERT INTO ORDEN_PAGO_DEDUC VALUES ('2026','1392','5','3400','10.5','7001','A','123',NULL,NULL,NULL)"
            ))
            # OP 1393 tiene 1 deducción de 10000
            conn.execute(sa_text(
                "INSERT INTO ORDEN_PAGO_DEDUC VALUES ('2026','1393','5','10000','10.5','7002','A','124',NULL,NULL,NULL)"
            ))
            # OP 1394 tiene 1 deducción de 800
            conn.execute(sa_text(
                "INSERT INTO ORDEN_PAGO_DEDUC VALUES ('2026','1394','3','800','3','7003','M',NULL,NULL,NULL,NULL)"
            ))
            # Lookup de deducciones
            conn.execute(sa_text(
                "INSERT INTO DEDUCCIONES VALUES ('5','RET. GANANCIAS','R',NULL,NULL,NULL,NULL,'2026')"
            ))
            conn.execute(sa_text(
                "INSERT INTO DEDUCCIONES VALUES ('3','RET. IIBB','R',NULL,NULL,NULL,NULL,'2026')"
            ))
        return engine

    def test_returns_deducciones_keyed_by_nro_op(self, tmp_path):
        from src.source_repository import SourceRepository
        engine = self._make_sqlite_with_deducciones(tmp_path)
        with engine.connect() as conn:
            repo = SourceRepository(conn, schema=None)
            result = repo.fetch_deducciones_for_ops([(2026, 1392), (2026, 1393), (2026, 1394)])

        assert (2026, 1392) in result
        assert (2026, 1393) in result
        assert (2026, 1394) in result
        # Cada OP tiene solo SU deducción, no la de las demás
        assert len(result[(2026, 1392)]) == 1
        assert float(result[(2026, 1392)][0]["importe_reten"]) == 3400
        assert float(result[(2026, 1393)][0]["importe_reten"]) == 10000
        assert float(result[(2026, 1394)][0]["importe_reten"]) == 800
        # Descripción viene del JOIN con DEDUCCIONES
        assert result[(2026, 1392)][0]["descripcion"] == "RET. GANANCIAS"
        assert result[(2026, 1394)][0]["descripcion"] == "RET. IIBB"

    def test_empty_keys_returns_empty(self, tmp_path):
        from src.source_repository import SourceRepository
        engine = self._make_sqlite_with_deducciones(tmp_path)
        with engine.connect() as conn:
            repo = SourceRepository(conn, schema=None)
            assert repo.fetch_deducciones_for_ops([]) == {}

    def test_missing_table_returns_none(self, tmp_path):
        from sqlalchemy import create_engine
        db_path = tmp_path / "empty.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        with engine.begin() as conn:
            pass  # DB vacía
        from src.source_repository import SourceRepository
        with engine.connect() as conn:
            repo = SourceRepository(conn, schema=None)
            assert repo.fetch_deducciones_for_ops([(2026, 1)]) is None

class TestMapDeduccionDict:
    """Valida _map_deduccion_dict del exporter."""

    @pytest.fixture
    def exporter(self):
        with patch("src.exporter.fetch_migrator_lookups") as mock_lookups:
            mock_lookups.return_value = {
                "unidades_de_medida": [],
                "tipos_factura": [],
                "tipos_de_pago": [{"id": "4", "name": "Transferencia"}],
                "tipos_retencion": [
                    {"id": "102", "name": "Retención de IVA"},
                    {"id": "103", "name": "Retención de Ganancias"},
                    {"id": "104", "name": "Retención de IIBB"},
                    {"id": "105", "name": "Retención SUSS"},
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

    def test_maps_deduccion_with_alicuota(self, exporter):
        ded = {
            "codigo_deduc": "5",
            "importe_reten": "3400.00",
            "alicuota": "10.5",
            "comprob_deduc": "7001",
            "cuenta": "123",
            "descripcion": "RET. GANANCIAS",
        }
        result = exporter._map_deduccion_dict(ded, 2026, 1392)
        assert result is not None
        assert result["monto_retenido"] == 3400.00
        assert result["tipo_impuesto_id"] == 103  # Ganancias
        assert result["alicuota"] == 10.5
        assert result["numero_certificado"] == "7001"
        assert result["external_id"]["codigo_deduc"] == "5"

    def test_zero_importe_returns_none(self, exporter):
        ded = {"codigo_deduc": "5", "importe_reten": "0", "descripcion": "GANANCIAS"}
        assert exporter._map_deduccion_dict(ded, 2026, 1) is None

    def test_no_catalog_match_returns_none(self, exporter):
        ded = {"codigo_deduc": "999", "importe_reten": "100", "descripcion": "DESCONOCIDO XYZ"}
        result = exporter._map_deduccion_dict(ded, 2026, 1)
        assert result is None
