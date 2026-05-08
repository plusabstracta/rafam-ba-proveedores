"""
Regression tests para los mappings de IDs de Paxapos.

Estos tests bloquean el contrato de mapeo entre RAFAM y Paxapos:

- RAFAM CTA_COMPROB.TIPO  -> tipo_factura.id (1=A, 2=B, 5=C, 4=M, 7=Otros, 8..14 NC/ND)
- RAFAM ORDEN_PAGO.TIPO_CANCE -> tipo_de_pago.id (1=Transferencia, 9=Cheque)
- Default UM = 5 (Unidad)
- pedido_internal_id se envia en OP cuando hay HDR_OC_* y no se resuelve por link_store

Si estos valores cambian, el lado servidor (CakePHP) tambien debe actualizarse.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.exporter import MigratorExporter
from src.gateway_mapper import (
    RAFAM_TIPO_CANCE_DEFAULT_PAGO_ID,
    RAFAM_TIPO_CANCE_TO_PAXAPOS_PAGO_ID,
    RAFAM_TIPO_COMPROB_DEFAULT_ID,
    RAFAM_TIPO_COMPROB_TO_PAXAPOS_ID,
    _UM_DEFAULT,
)


# ─── Constantes ───────────────────────────────────────────────────────────────


class TestGatewayMapperConstants:
    """Asegura que los IDs canonicos de Paxapos no se rompan por descuido."""

    def test_um_default_es_unidad_id_5(self):
        assert _UM_DEFAULT == 5

    def test_tipo_comprob_default_es_otros_id_7(self):
        assert RAFAM_TIPO_COMPROB_DEFAULT_ID == 7

    def test_tipo_cance_default_es_transferencia_id_1(self):
        assert RAFAM_TIPO_CANCE_DEFAULT_PAGO_ID == 1

    @pytest.mark.parametrize(
        "rafam_code,paxapos_id",
        [
            # Facturas
            ("FAA", 1),  # Factura A
            ("FAS", 1),
            ("FAB", 2),  # Factura B
            ("FAC", 5),  # Factura C
            ("FAM", 4),  # Factura M
            ("REA", 1),  # Recibo A
            ("REB", 2),  # Recibo B
            ("EXB", 2),  # Exento B
            # Notas de credito
            ("NCA", 10),
            ("NCB", 8),
            ("NCC", 9),
            ("NCM", 14),
            # Notas de debito
            ("NDA", 13),
            ("NDB", 11),
            ("NDC", 12),
            # Otros
            ("TKT", 7),
            ("LIQ", 7),
            ("REC", 7),
        ],
    )
    def test_tipo_comprob_id_mapping(self, rafam_code, paxapos_id):
        assert RAFAM_TIPO_COMPROB_TO_PAXAPOS_ID[rafam_code] == paxapos_id

    @pytest.mark.parametrize(
        "tipo_cance,paxapos_id",
        [
            ("CA", 9),  # Cheque al dia
            ("CM", 9),  # Cheque diferido
            ("NO", 1),  # Transferencia bancaria
        ],
    )
    def test_tipo_cance_id_mapping(self, tipo_cance, paxapos_id):
        assert RAFAM_TIPO_CANCE_TO_PAXAPOS_PAGO_ID[tipo_cance] == paxapos_id


# ─── Resolvers en el exporter ─────────────────────────────────────────────────


@pytest.fixture
def exporter():
    """MigratorExporter con catalogo NO matcheante para verificar fallback a IDs."""
    with patch("src.exporter.fetch_migrator_lookups") as mock_lookups:
        mock_lookups.return_value = {
            "unidades_de_medida": [],   # vacio: forzar default UM
            "tipos_factura": [],         # vacio: forzar default por ID map
            "tipos_de_pago": [],         # vacio: forzar default por ID map
            "tipos_retencion": [],
        }
        with patch.dict(
            "os.environ",
            {
                "PAXAPOS_URL": "https://example.com",
                "PAXAPOS_TENANT": "test",
                "PAXAPOS_API_KEY": "key",
                "LOCAL_STATE_DB_PATH": ":memory:",
            },
            clear=False,
        ):
            return MigratorExporter(dry_run=True)


class TestResolveTipoFacturaIdMappings:
    """_resolve_tipo_factura_id usa el mapping ID-first como fuente de verdad."""

    @pytest.mark.parametrize(
        "rafam_code,paxapos_id",
        [
            ("FAA", 1), ("FAB", 2), ("FAC", 5), ("FAM", 4),
            ("NCA", 10), ("NCB", 8), ("NCC", 9), ("NCM", 14),
            ("NDA", 13), ("NDB", 11), ("NDC", 12),
            ("TKT", 7), ("LIQ", 7),
        ],
    )
    def test_resuelve_codigo_rafam_a_id_paxapos(self, exporter, rafam_code, paxapos_id):
        assert exporter._resolve_tipo_factura_id(rafam_code) == paxapos_id

    def test_codigo_desconocido_cae_a_otros_id_7(self, exporter):
        assert exporter._resolve_tipo_factura_id("ZZZ") == 7

    def test_codigo_lowercase_se_normaliza(self, exporter):
        assert exporter._resolve_tipo_factura_id("ncc") == 9

    def test_none_no_devuelve_default(self, exporter):
        # Sin tipo_doc no hay nada que mapear; el caller decide.
        assert exporter._resolve_tipo_factura_id(None) is None


class TestResolveTipoPagoIdMappings:
    """_resolve_tipo_pago_id mapea TIPO_CANCE a tipo_de_pago.id."""

    def test_cheque_al_dia_es_id_9(self, exporter):
        assert exporter._resolve_tipo_pago_id({"TIPO_CANCE": "CA"}) == 9

    def test_cheque_diferido_es_id_9(self, exporter):
        assert exporter._resolve_tipo_pago_id({"TIPO_CANCE": "CM"}) == 9

    def test_no_es_transferencia_id_1(self, exporter):
        assert exporter._resolve_tipo_pago_id({"TIPO_CANCE": "NO"}) == 1

    def test_tipo_desconocido_cae_a_transferencia_id_1(self, exporter):
        assert exporter._resolve_tipo_pago_id({"TIPO_CANCE": "XX"}) == 1

    def test_lowercase_se_normaliza(self, exporter):
        assert exporter._resolve_tipo_pago_id({"tipo_cance": "ca"}) == 9 or \
               exporter._resolve_tipo_pago_id({"TIPO_CANCE": "ca"}) == 9


class TestResolveUnidadMedidaDefault:
    """_resolve_unidad_medida_id retorna 5 (Unidad) cuando link_store esta vacio."""

    def test_link_store_vacio_devuelve_id_5(self, exporter):
        assert exporter._resolve_unidad_medida_id({"UNI_MED": "UNIDAD"}) == 5

    def test_uni_med_none_devuelve_id_5(self, exporter):
        assert exporter._resolve_unidad_medida_id({}) == 5

    def test_uni_med_resuelta_via_link_store(self, exporter):
        exporter._link_store.save_link("unidad_medida", "KILOGRAMO", "3")
        assert exporter._resolve_unidad_medida_id({"UNI_MED": "KILOGRAMO"}) == 3


# ─── pedido_internal_id en payload de OP ─────────────────────────────────────


class TestPedidoInternalIdEnOrdenPago:
    """Verifica que el script envia pedido_internal_id como fallback robusto."""

    def _make_exporter(self):
        with patch("src.exporter.fetch_migrator_lookups") as mock_lookups:
            mock_lookups.return_value = {
                "unidades_de_medida": [],
                "tipos_factura": [],
                "tipos_de_pago": [],
                "tipos_retencion": [],
            }
            with patch.dict(
                "os.environ",
                {
                    "PAXAPOS_URL": "https://example.com",
                    "PAXAPOS_TENANT": "test",
                    "PAXAPOS_API_KEY": "key",
                    "LOCAL_STATE_DB_PATH": ":memory:",
                },
                clear=False,
            ):
                return MigratorExporter(dry_run=True)

    @staticmethod
    def _columns():
        return [
            "EJERCICIO", "NRO_OP", "FECH_OP", "ESTADO_OP",
            "IMPORTE_TOTAL", "CONCEPTO", "NRO_CANCE",
            "SG_DELEG_SOLIC", "SG_NRO_SOLIC",
            "HDR_CC_NRO",
            "HDR_OC_EJERCICIO", "HDR_OC_UNI_COMPRA", "HDR_OC_NRO",
            "FECH_CONFIRM", "CONFIRMADO", "TIPO_CANCE",
        ]

    @staticmethod
    def _row(cols, **overrides):
        defaults = {
            "EJERCICIO": "2026", "NRO_OP": "5001",
            "FECH_OP": "2026-04-10 00:00:00",
            "ESTADO_OP": "C", "IMPORTE_TOTAL": "1000.00",
            "CONCEPTO": "Pago", "NRO_CANCE": "9000",
            "SG_DELEG_SOLIC": "1", "SG_NRO_SOLIC": "200",
            "HDR_CC_NRO": "0001-00012345",
            "HDR_OC_EJERCICIO": "2026", "HDR_OC_UNI_COMPRA": "1", "HDR_OC_NRO": "777",
            "FECH_CONFIRM": "2026-04-15 00:00:00", "CONFIRMADO": "S",
            "TIPO_CANCE": "NO",
        }
        defaults.update(overrides)
        return tuple(defaults.get(c, "") for c in cols)

    def _send_and_capture(self, exp, rows):
        cols = self._columns()
        sent = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_pago": {"ok": 1, "error": 0}}}
        )
        exp.write_batch("orden_pago", cols, rows)
        return sent

    def test_envia_pedido_internal_id_cuando_link_store_vacio(self):
        """OC nunca migrada por este script -> link_store vacio -> manda internal_id."""
        exp = self._make_exporter()
        rows = [self._row(self._columns())]

        sent = self._send_and_capture(exp, rows)
        assert len(sent) == 1
        ops = sent[0]["ordenes_pago"]
        assert len(ops) == 1
        op = ops[0]
        # Sin link_store -> no hay pedido_id, pero SI pedido_internal_id
        assert "pedido_id" not in op
        assert op["pedido_internal_id"] == "rafam-oc-2026-1-777"

    def test_no_envia_pedido_internal_id_si_pedido_id_resuelto(self):
        """OC ya migrada por este script -> link_store devuelve pedido_id."""
        exp = self._make_exporter()
        # Pre-vincular OC en el link_store local
        oc_key = json.dumps(
            {"ejercicio": 2026, "nro_oc": 777, "uni_compra": 1}, sort_keys=True,
        )
        exp._link_store.save_link("orden_compra", oc_key, "12345")

        rows = [self._row(self._columns())]
        sent = self._send_and_capture(exp, rows)

        op = sent[0]["ordenes_pago"][0]
        assert op["pedido_id"] == 12345
        # Cuando ya hay pedido_id resuelto, no se envia internal_id (evita ambiguedad)
        assert "pedido_internal_id" not in op

    def test_omite_pedido_internal_id_si_falta_alguna_columna_oc(self):
        """Sin HDR_OC_* completo no se puede construir el internal_id."""
        exp = self._make_exporter()
        rows = [self._row(self._columns(), HDR_OC_NRO="")]
        sent = self._send_and_capture(exp, rows)
        op = sent[0]["ordenes_pago"][0]
        assert "pedido_id" not in op
        assert "pedido_internal_id" not in op

    def test_internal_id_es_lowercase_y_formato_canonico(self):
        """El formato debe coincidir con lo que el OC migra: rafam-oc-{ej}-{uni}-{nro}."""
        exp = self._make_exporter()
        rows = [self._row(
            self._columns(),
            HDR_OC_EJERCICIO="2025", HDR_OC_UNI_COMPRA="3", HDR_OC_NRO="42",
        )]
        sent = self._send_and_capture(exp, rows)
        op = sent[0]["ordenes_pago"][0]
        assert op["pedido_internal_id"] == "rafam-oc-2025-3-42"

    def test_tipo_pago_se_setea_desde_tipo_cance(self):
        """TIPO_CANCE='CA' -> tipo_de_pago_id=9 (Cheque)."""
        exp = self._make_exporter()
        rows = [self._row(self._columns(), TIPO_CANCE="CA")]
        sent = self._send_and_capture(exp, rows)
        op = sent[0]["ordenes_pago"][0]
        assert op["Egreso"]["tipo_de_pago_id"] == 9

    def test_tipo_pago_default_para_tipo_cance_no(self):
        """TIPO_CANCE='NO' -> tipo_de_pago_id=1 (Transferencia bancaria)."""
        exp = self._make_exporter()
        rows = [self._row(self._columns(), TIPO_CANCE="NO")]
        sent = self._send_and_capture(exp, rows)
        op = sent[0]["ordenes_pago"][0]
        assert op["Egreso"]["tipo_de_pago_id"] == 1
