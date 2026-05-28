"""
Regression tests para los mappings de IDs de Paxapos.

Estos tests bloquean el contrato de mapeo entre RAFAM y Paxapos:

- RAFAM CTA_COMPROB.TIPO  -> tipo_factura.id (1=A, 2=B, 5=C, 4=M, 7=Otros, 8..14 NC/ND)
- RAFAM ORDEN_PAGO.TIPO_CANCE -> tipo_de_pago.id (1=Transferencia, 9=Cheque)
- Default UM = 5 (Unidad)
- orden_pago solo se envia cuando la OC ya resuelve a pedido_id local

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


# ─── pedido_id obligatorio en payload de OP ──────────────────────────────────


class TestPedidoInternalIdEnOrdenPago:
    """Verifica que el script no crea OP/gastos sin OC linkeada."""

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
            "OPI_NRO_COMPROB",
            "SG_OC_EJERCICIO", "SG_OC_UNI_COMPRA", "SG_OC_NRO",
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
            "OPI_NRO_COMPROB": "0001-00012345",
            "SG_OC_EJERCICIO": "2026", "SG_OC_UNI_COMPRA": "1", "SG_OC_NRO": "777",
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

    @staticmethod
    def _link_oc(exp, *, ejercicio=2026, uni_compra=1, nro_oc=777, remote_id="12345"):
        oc_key = json.dumps(
            {"ejercicio": ejercicio, "nro_oc": nro_oc, "uni_compra": uni_compra},
            sort_keys=True,
        )
        exp._link_store.save_link("orden_compra", oc_key, remote_id=remote_id)

    def test_omite_op_cuando_link_store_vacio(self):
        """OC nunca migrada por este script -> no se envia la OP."""
        exp = self._make_exporter()
        rows = [self._row(self._columns())]

        sent = self._send_and_capture(exp, rows)
        assert sent == []

    def test_no_envia_pedido_internal_id_si_pedido_id_resuelto(self):
        """OC ya migrada por este script -> link_store devuelve pedido_id."""
        exp = self._make_exporter()
        self._link_oc(exp)

        rows = [self._row(self._columns())]
        sent = self._send_and_capture(exp, rows)

        op = sent[0]["ordenes_pago"][0]
        assert op["pedido_id"] == 12345
        # Cuando ya hay pedido_id resuelto, no se envia internal_id (evita ambiguedad)
        assert "pedido_internal_id" not in op

    def test_omite_pedido_internal_id_si_falta_alguna_columna_oc(self):
        """Sin SG_OC_* completo no se puede resolver OC, entonces se omite."""
        exp = self._make_exporter()
        rows = [self._row(self._columns(), SG_OC_NRO="")]
        sent = self._send_and_capture(exp, rows)
        assert sent == []

    def test_op_con_oc_vieja_linkeada_envia_pedido_id(self):
        """Una OC vieja incluida por dependencia se vincula por pedido_id local."""
        exp = self._make_exporter()
        self._link_oc(exp, ejercicio=2025, uni_compra=3, nro_oc=42, remote_id="4242")
        rows = [self._row(
            self._columns(),
            SG_OC_EJERCICIO="2025", SG_OC_UNI_COMPRA="3", SG_OC_NRO="42",
        )]
        sent = self._send_and_capture(exp, rows)
        op = sent[0]["ordenes_pago"][0]
        assert op["pedido_id"] == 4242
        assert "pedido_internal_id" not in op

    def test_tipo_pago_se_setea_desde_tipo_cance(self):
        """TIPO_CANCE='CA' -> tipo_de_pago_id=9 (Cheque)."""
        exp = self._make_exporter()
        self._link_oc(exp)
        rows = [self._row(self._columns(), TIPO_CANCE="CA")]
        sent = self._send_and_capture(exp, rows)
        op = sent[0]["ordenes_pago"][0]
        assert op["Egreso"]["tipo_de_pago_id"] == 9

    def test_tipo_pago_default_para_tipo_cance_no(self):
        """TIPO_CANCE='NO' -> tipo_de_pago_id=1 (Transferencia bancaria)."""
        exp = self._make_exporter()
        self._link_oc(exp)
        rows = [self._row(self._columns(), TIPO_CANCE="NO")]
        sent = self._send_and_capture(exp, rows)
        op = sent[0]["ordenes_pago"][0]
        assert op["Egreso"]["tipo_de_pago_id"] == 1


# ─── Bug "varios pagos en cero para un mismo comprobante" ────────────────────


class TestNoCrearPagosEnCero:
    """
    Bug reportado: para un mismo comprobante se generaban varios Egresos en
    Paxapos, uno con importe correcto y otros en $0.

    Causa raiz: cuando una OP RAFAM tenia IMPORTE_TOTAL NULL, no parseable o
    igual a 0 (tipico en OPs de ajuste contable / anulacion), el script
    silenciosamente la enviaba con total=0. Como cada OP tiene
    identificador_pago unico, el upsert no las une y se acumulan Egresos en $0
    vinculados al mismo Gasto via gasto_nro_comprobante.

    Estos tests garantizan que el script NUNCA exporta una OP con total <= 0.
    """

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
            "OPI_NRO_COMPROB",
            "pedido_id", "FECH_CONFIRM", "CONFIRMADO", "TIPO_CANCE",
        ]

    def _row(self, cols, **overrides):
        defaults = {
            "EJERCICIO": "2026", "NRO_OP": "9001",
            "FECH_OP": "2026-04-10 00:00:00",
            "ESTADO_OP": "C", "IMPORTE_TOTAL": "1500.00",
            "CONCEPTO": "Pago", "NRO_CANCE": "9100",
            "SG_DELEG_SOLIC": "1", "SG_NRO_SOLIC": "300",
            "OPI_NRO_COMPROB": "0001-00099999",
            "pedido_id": "12345",
            "FECH_CONFIRM": "2026-04-15 00:00:00", "CONFIRMADO": "S",
            "TIPO_CANCE": "NO",
        }
        defaults.update(overrides)
        return tuple(defaults.get(c, "") for c in cols)

    def _capture(self, exp, rows):
        cols = self._columns()
        sent: list[dict] = []
        exp._post_json = lambda url, p: (
            sent.append(p)
            or {"stats": {"ordenes_pago": {"ok": len(p.get("ordenes_pago", [])), "error": 0}}}
        )
        exp.write_batch("orden_pago", cols, rows)
        return sent

    def test_op_con_importe_total_null_no_se_exporta(self):
        """IMPORTE_TOTAL = NULL -> OP omitida (no se crea Egreso en $0)."""
        exp = self._make_exporter()
        rows = [self._row(self._columns(), NRO_OP="9001", IMPORTE_TOTAL=None)]
        sent = self._capture(exp, rows)
        # No se envia payload alguno (lote vacio)
        assert sent == [], "OP con IMPORTE_TOTAL=NULL no debe exportarse"

    def test_op_con_importe_total_cero_no_se_exporta(self):
        """IMPORTE_TOTAL = 0 -> OP omitida (ajuste contable / anulacion RAFAM)."""
        exp = self._make_exporter()
        rows = [self._row(self._columns(), NRO_OP="9002", IMPORTE_TOTAL="0.00")]
        sent = self._capture(exp, rows)
        assert sent == [], "OP con IMPORTE_TOTAL=0 no debe exportarse"

    def test_op_con_importe_total_negativo_no_se_exporta(self):
        """IMPORTE_TOTAL negativo es un caso defensivo: no se exporta."""
        exp = self._make_exporter()
        rows = [self._row(self._columns(), NRO_OP="9003", IMPORTE_TOTAL="-100.00")]
        sent = self._capture(exp, rows)
        assert sent == [], "OP con IMPORTE_TOTAL<0 no debe exportarse"

    def test_op_con_importe_total_no_parseable_no_se_exporta(self):
        """Strings basura en IMPORTE_TOTAL -> OP omitida con warning, no Egreso en $0."""
        exp = self._make_exporter()
        rows = [self._row(self._columns(), NRO_OP="9004", IMPORTE_TOTAL="N/D")]
        sent = self._capture(exp, rows)
        assert sent == [], "OP con IMPORTE_TOTAL no parseable no debe exportarse"

    def test_op_con_importe_valido_si_se_exporta(self):
        """Sanity check: la OP con importe positivo si se exporta."""
        exp = self._make_exporter()
        rows = [self._row(self._columns(), NRO_OP="9005", IMPORTE_TOTAL="1500.00")]
        sent = self._capture(exp, rows)
        assert len(sent) == 1
        ops = sent[0]["ordenes_pago"]
        assert len(ops) == 1
        assert ops[0]["Egreso"]["total"] == 1500.00
        assert ops[0]["importe_total"] == 1500.00

    def test_lote_mixto_solo_exporta_op_con_importe_valido(self):
        """
        Escenario realista del bug: 4 OPs RAFAM apuntando al mismo comprobante.
        Solo una tiene importe; las otras son ajustes contables (0/null/error).
        Esperado: se exporta UN solo Egreso (no 4).
        """
        exp = self._make_exporter()
        cc = "0001-00099999"
        rows = [
            self._row(self._columns(), NRO_OP="8001", IMPORTE_TOTAL="2500.00", OPI_NRO_COMPROB=cc),
            self._row(self._columns(), NRO_OP="8002", IMPORTE_TOTAL="0.00", OPI_NRO_COMPROB=cc),
            self._row(self._columns(), NRO_OP="8003", IMPORTE_TOTAL=None, OPI_NRO_COMPROB=cc),
            self._row(self._columns(), NRO_OP="8004", IMPORTE_TOTAL="ERROR", OPI_NRO_COMPROB=cc),
        ]
        sent = self._capture(exp, rows)
        assert len(sent) == 1
        ops = sent[0]["ordenes_pago"]
        assert len(ops) == 1, (
            f"Solo debe exportarse 1 OP con importe valido (no {len(ops)}). "
            "El bug original creaba 4 Egresos: 1 con importe y 3 en $0."
        )
        op = ops[0]
        assert op["external_id"]["nro_op"] == 8001
        assert op["Egreso"]["total"] == 2500.00
        assert op["gasto_nro_comprobante"] == cc

    def test_warning_log_cuando_se_skipea(self, caplog):
        """Las OPs skipeadas deben dejar trazabilidad en el log."""
        import logging
        exp = self._make_exporter()
        rows = [
            self._row(self._columns(), NRO_OP="7001", IMPORTE_TOTAL="0.00"),
            self._row(self._columns(), NRO_OP="7002", IMPORTE_TOTAL=None),
        ]
        with caplog.at_level(logging.WARNING):
            self._capture(exp, rows)

        msgs = " ".join(rec.getMessage() for rec in caplog.records)
        assert "OP 2026-7001" in msgs
        assert "OP 2026-7002" in msgs
        assert "IMPORTE_TOTAL" in msgs
