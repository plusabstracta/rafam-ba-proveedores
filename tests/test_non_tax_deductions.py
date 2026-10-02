"""Deducciones NO impositivas: Garantia (cod 4) y Caja de Medicos (cod 8).

paxapos/paxapos#738 (espejo: plusabstracta/rafam-ba-proveedores#18).

RAFAM clasifica sus deducciones en ``DEDUCCIONES.TIPO_DEDUC``: 'I' (impositiva)
y 'O' (otra). Dos 'O' las aplica a proveedores reales y restan del neto que
cobran: Garantia (cod 4) y Retenciones Caja de Medicos (cod 8). Antes el
migrador las omitia (Paxapos no las podia representar) y el neto pagado de esas
OP quedaba sobreestimado ($2.063.270 en 27 OP + $2.224.050 en 12 OP, madariaga).

Ahora el migrador las manda dentro de ``retenciones[]`` con
``no_impositiva: true`` + ``concepto`` + ``codigo_externo`` (sin
``tipo_impuesto_id`` ni ``numero_certificado``), segun el mapa configurable
``RAFAM_NON_TAX_DEDUCTION_MAP``. Cualquier otra 'O' sin mapeo (IPS, IOMA,
sindicatos...) sigue omitida y encolada como ``non_tax_deduction``.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.config import non_tax_deduction_concept, non_tax_deduction_map
from src.exporter import MigratorExporter
from src.retry_store import REASON_DEPENDENCY_MISSING, RetryStore

_OP_SK = json.dumps({"ejercicio": 2026, "nro_op": 100}, sort_keys=True)
_COLUMNS = ["EJERCICIO", "NRO_OP"]

_GARANTIA = {"codigo_deduc": "4", "importe_reten": 2500.0, "descripcion": "GARANTIA", "tipo_deduc": "O"}
_CAJA_MEDICOS = {"codigo_deduc": "8", "importe_reten": 1000.0, "descripcion": "RETENCIONES CAJA DE MEDICOS", "tipo_deduc": "O"}
_IPS = {"codigo_deduc": "1", "importe_reten": 300.0, "descripcion": "RETENCIONES I.P.S.", "tipo_deduc": "O"}
_GANANCIAS = {"codigo_deduc": "3", "importe_reten": 400.0, "descripcion": "Retencion ganancias", "tipo_deduc": "I", "alicuota": 4.13}


@pytest.fixture(autouse=True)
def _mapa_por_default(monkeypatch):
    """Cada test arranca con el mapa de fabrica (cod 4 y 8), sin env heredado."""
    monkeypatch.delenv("RAFAM_NON_TAX_DEDUCTION_MAP", raising=False)


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
            "tipos_retencion": [{"id": "103", "name": "Retencion ganancias"}],
        }
    }
    with patch("src.exporter.fetch_migrator_lookups", return_value=lookup_payload):
        return MigratorExporter(dry_run=False)


class _FakeSourceRepo:
    def __init__(self, deducciones_by_op):
        self._deducciones_by_op = deducciones_by_op

    def fetch_deducciones_for_ops(self, op_keys):
        return self._deducciones_by_op


def _ok_response():
    return {
        "success": True,
        "stats": {"retenciones": {"ok": 1, "error": 0}},
        "results": {"retenciones": [
            {"success": True, "external_id": {"ejercicio": 2026, "nro_op": 100}, "id": 5001},
        ]},
    }


def _enviar(exporter, deducciones, *, post_response=None):
    """Corre el batch F3 de la OP (2026, 100) y devuelve los payloads POSTeados."""
    exporter.attach_source(_FakeSourceRepo({(2026, 100): deducciones}))
    posted: list = []

    def fake_post(url, payload):
        posted.append(payload)
        return post_response or _ok_response()

    with patch.object(exporter, "_post_json", side_effect=fake_post):
        exporter.write_batch("retenciones", _COLUMNS, [(2026, 100)])
    return posted


def _montado(monkeypatch, tmp_path):
    exporter = _migrator(monkeypatch, tmp_path)
    retry = RetryStore(db_path=str(tmp_path / "retry.db"))
    exporter.attach_retry_store(retry)
    exporter._link_store.save_link("orden_pago", _OP_SK, "5001")
    return exporter, retry


# ── Mapa configurable ────────────────────────────────────────────────────────

class TestMapaConfigurable:
    def test_default_es_garantia_y_caja_de_medicos(self):
        assert non_tax_deduction_map() == {"4": "Fondo de garantía", "8": "Caja de Médicos"}

    def test_el_codigo_se_normaliza(self):
        assert non_tax_deduction_concept(4, "O") == "Fondo de garantía"
        assert non_tax_deduction_concept("04", "O") == "Fondo de garantía"
        assert non_tax_deduction_concept(" 8 ") == "Caja de Médicos"
        assert non_tax_deduction_concept("1", "O") is None  # IPS: sin mapeo

    def test_una_deduccion_impositiva_nunca_es_no_impositiva(self):
        # Un mapa mal configurado no puede esconder una retencion fiscal.
        assert non_tax_deduction_concept("4", "I") is None
        assert non_tax_deduction_concept("4", "i") is None
        assert non_tax_deduction_concept("4", None) == "Fondo de garantía"

    def test_el_env_reemplaza_al_default(self, monkeypatch):
        monkeypatch.setenv("RAFAM_NON_TAX_DEDUCTION_MAP", "4=Garantia de obra, 12 = Embargo judicial ,xx,=sin codigo,9=")
        assert non_tax_deduction_map() == {"4": "Garantia de obra", "12": "Embargo judicial"}
        assert non_tax_deduction_concept("8", "O") is None  # ya no esta mapeado

    def test_env_vacio_desactiva_todo(self, monkeypatch):
        monkeypatch.setenv("RAFAM_NON_TAX_DEDUCTION_MAP", "")
        assert non_tax_deduction_map() == {}
        assert non_tax_deduction_concept("4", "O") is None

    def test_el_nombre_se_acota_al_largo_de_la_columna(self, monkeypatch):
        monkeypatch.setenv("RAFAM_NON_TAX_DEDUCTION_MAP", "4=" + "x" * 150)
        assert len(non_tax_deduction_map()["4"]) == 100


# ── Payload de la pasada F3 (retenciones standalone) ─────────────────────────

class TestPayloadRetencionesStandalone:
    def test_garantia_y_caja_de_medicos_se_envian_como_no_impositivas(self, monkeypatch, tmp_path):
        exporter, retry = _montado(monkeypatch, tmp_path)

        posted = _enviar(exporter, [_GARANTIA, _CAJA_MEDICOS])

        assert len(posted) == 1
        op = posted[0]["retenciones"][0]
        assert op["egreso_id"] == 5001
        by_codigo = {r["codigo_externo"]: r for r in op["retenciones"]}
        assert set(by_codigo) == {"4", "8"}

        garantia = by_codigo["4"]
        assert garantia["no_impositiva"] is True
        assert garantia["concepto"] == "Fondo de garantía"
        assert garantia["monto_retenido"] == 2500.0
        assert garantia["external_id"] == {"ejercicio": 2026, "nro_op": 100, "codigo_deduc": "4"}
        # No es una retencion fiscal: ni regimen del catalogo ni certificado.
        assert "tipo_impuesto_id" not in garantia
        assert "numero_certificado" not in garantia
        assert by_codigo["8"]["concepto"] == "Caja de Médicos"
        retry.close()

    def test_la_cola_non_tax_deduction_se_resuelve_al_enviarse(self, monkeypatch, tmp_path):
        """Las 39 OP de madariaga estaban 'pending' con non_tax_deduction: al
        reprocesarse con el mapeo, la corrida las envia y las saca de la cola."""
        exporter, retry = _montado(monkeypatch, tmp_path)
        retry.enqueue("retenciones", _OP_SK, REASON_DEPENDENCY_MISSING, "legacy", reason_detail="non_tax_deduction")

        posted = _enviar(exporter, [_GARANTIA])

        assert len(posted) == 1
        assert retry.pending_external_ids("retenciones") == set()
        link = exporter._link_store.get_link("retenciones", _OP_SK)
        assert link and link["fingerprint"]
        retry.close()

    def test_una_op_con_ganancias_y_garantia_manda_las_dos(self, monkeypatch, tmp_path):
        exporter, retry = _montado(monkeypatch, tmp_path)

        posted = _enviar(exporter, [_GANANCIAS, _GARANTIA])

        items = posted[0]["retenciones"][0]["retenciones"]
        impositiva = next(r for r in items if r.get("tipo_impuesto_id") == 103)
        no_impositiva = next(r for r in items if r.get("no_impositiva"))
        assert "no_impositiva" not in impositiva
        assert impositiva["numero_certificado"].startswith("RAFAM-RET-")
        assert no_impositiva["codigo_externo"] == "4"
        retry.close()

    def test_una_no_impositiva_sin_mapeo_se_omite_pero_las_mapeadas_viajan(self, monkeypatch, tmp_path):
        exporter, retry = _montado(monkeypatch, tmp_path)

        posted = _enviar(exporter, [_GARANTIA, _IPS])

        items = posted[0]["retenciones"][0]["retenciones"]
        assert [r["codigo_externo"] for r in items] == ["4"]
        # La OP viajo (hay algo mapeado): no queda encolada por el IPS omitido.
        assert retry.pending_external_ids("retenciones") == set()
        retry.close()

    def test_solo_no_impositivas_sin_mapeo_sigue_encolando_non_tax_deduction(self, monkeypatch, tmp_path):
        exporter, retry = _montado(monkeypatch, tmp_path)

        posted = _enviar(exporter, [_IPS])

        assert posted == []
        item = retry.list_items("retenciones")[0]
        assert item.reason_detail == "non_tax_deduction"
        retry.close()

    def test_una_deduccion_impositiva_con_codigo_mapeado_sigue_siendo_retencion(self, monkeypatch, tmp_path):
        exporter, retry = _montado(monkeypatch, tmp_path)
        ded = {"codigo_deduc": "4", "importe_reten": 80.0, "descripcion": "Retencion ganancias", "tipo_deduc": "I"}

        posted = _enviar(exporter, [ded])

        item = posted[0]["retenciones"][0]["retenciones"][0]
        assert item["tipo_impuesto_id"] == 103
        assert "no_impositiva" not in item
        retry.close()

    def test_con_el_mapa_vacio_vuelve_al_comportamiento_anterior(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RAFAM_NON_TAX_DEDUCTION_MAP", "")
        exporter, retry = _montado(monkeypatch, tmp_path)

        posted = _enviar(exporter, [_GARANTIA])

        assert posted == []
        assert retry.list_items("retenciones")[0].reason_detail == "non_tax_deduction"
        retry.close()

    def test_el_mapa_del_env_cambia_el_concepto_y_los_codigos(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RAFAM_NON_TAX_DEDUCTION_MAP", "4=Retencion de garantia,12=Embargo")
        exporter, retry = _montado(monkeypatch, tmp_path)
        embargo = {"codigo_deduc": "12", "importe_reten": 50.0, "descripcion": "EMBARGO", "tipo_deduc": "O"}

        posted = _enviar(exporter, [_GARANTIA, embargo, _CAJA_MEDICOS])

        items = {r["codigo_externo"]: r["concepto"] for r in posted[0]["retenciones"][0]["retenciones"]}
        assert items == {"4": "Retencion de garantia", "12": "Embargo"}  # el 8 ya no esta mapeado
        retry.close()


# ── Reproceso: una OP ya enviada solo con lo impositivo se reenvia ───────────

class TestReproceso:
    def test_una_op_enviada_sin_la_garantia_se_reenvia_con_replace_al_activar_el_mapeo(self, monkeypatch, tmp_path):
        exporter, retry = _montado(monkeypatch, tmp_path)

        # 1) Estado de hoy en prod: solo Ganancias viajo; la garantia se omitia.
        monkeypatch.setenv("RAFAM_NON_TAX_DEDUCTION_MAP", "")
        primera = _enviar(exporter, [_GANANCIAS, _GARANTIA])
        assert len(primera[0]["retenciones"][0]["retenciones"]) == 1
        assert retry.pending_external_ids("retenciones") == set()

        # 2) Sin cambios y sin mapeo: idempotente, no reenvia.
        assert _enviar(exporter, [_GANANCIAS, _GARANTIA]) == []

        # 3) Se activa el mapeo (deploy del backend + migrador): el conjunto cambia,
        #    el fingerprint cambia y la OP se reenvia completa (el receptor hace replace).
        monkeypatch.delenv("RAFAM_NON_TAX_DEDUCTION_MAP")
        tercera = _enviar(exporter, [_GANANCIAS, _GARANTIA])
        assert len(tercera) == 1
        assert len(tercera[0]["retenciones"][0]["retenciones"]) == 2

        # 4) Y de ahi en mas queda al dia.
        assert _enviar(exporter, [_GANANCIAS, _GARANTIA]) == []
        retry.close()

    def test_el_dry_run_no_persiste_links_ni_toca_la_cola(self, monkeypatch, tmp_path):
        exporter, retry = _montado(monkeypatch, tmp_path)
        retry.enqueue("retenciones", _OP_SK, REASON_DEPENDENCY_MISSING, "legacy", reason_detail="non_tax_deduction")
        exporter._dry_run = True

        posted = _enviar(exporter, [_GARANTIA])

        assert posted[0]["dry_run"] is True
        assert posted[0]["retenciones"][0]["retenciones"][0]["no_impositiva"] is True
        assert exporter._link_store.get_link("retenciones", _OP_SK) is None
        assert retry.pending_external_ids("retenciones") == {_OP_SK}
        retry.close()


# ── Retenciones embebidas en ordenes_pago ────────────────────────────────────

class TestOrdenPagoEmbebido:
    def test_la_ruta_de_ordenes_pago_manda_la_misma_forma(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)

        mapped = exporter._map_deduccion_dict(
            {"codigo_deduc": 8, "importe_reten": 1000.0, "descripcion": "CAJA DE MEDICOS", "tipo_deduc": "O", "alicuota": 5.0},
            2026,
            100,
        )

        assert mapped == {
            "external_id": {"ejercicio": 2026, "nro_op": 100, "codigo_deduc": "8"},
            "no_impositiva": True,
            "codigo_externo": "8",
            "concepto": "Caja de Médicos",
            "monto_retenido": 1000.0,
            "alicuota": 5.0,
            "observacion": "Deduccion RAFAM CAJA DE MEDICOS OP 2026/100",
        }

    def test_una_no_impositiva_sin_mapeo_no_se_manda(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        assert exporter._map_deduccion_dict(_IPS, 2026, 100) is None

    def test_una_impositiva_sigue_resolviendo_su_tipo(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        mapped = exporter._map_deduccion_dict(_GANANCIAS, 2026, 100)
        assert mapped["tipo_impuesto_id"] == 103
        assert "no_impositiva" not in mapped
