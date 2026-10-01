"""`main.py resend` — reenvio puntual de registros (Fase 1).

Antes, una OC/OP/gasto que no llegaba a Paxapos solo se podia recuperar con
`retry-queue --send-now` (que corre la entidad entera y solo ve lo que ya
estaba en la cola) o reseteando el checkpoint y reenviando TODO. Cubre:

1. Parseo de claves: forma corta, label del mail y JSON de la cola.
2. `build_statement(only_keys=...)` trae solo esas filas, aunque el pipeline
   las filtraria (ejercicio viejo, ESTADO_OP != C), y nunca la tabla entera.
3. "force" saltea solo el "sin cambios"/'permanent', nunca reglas de negocio.
4. El reporte por clave (OK / RECHAZADO / OMITIDO / NO EXISTE / FALLO /
   NO ENVIADO), sin tocar checkpoints, reencolando 'permanent'.
5. `retry-queue --send-now` manda solo las claves de la cola.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import threading
from dataclasses import replace
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

import main as main_module
from src.backend_errors import BackendInfraError
from src.change_detection import compute_payload_hash
from src.config import ENTITY_CONFIGS
from src.exporter import MigratorExporter
from src.gateway_mapper import map_proveedor_migrator_row
from src.models import Checkpoint
from src.record_events import RecordEventSink
from src.retry_labels import parse_record_key, record_base_key, record_key_from_row
from src.retry_store import STATUS_PERMANENT, RetryStore
from src.source_repository import SourceRepository
from tests.test_ejercicio_filter_and_oc_op_flow import engine_with_data  # noqa: F401 (fixture)


def _oc_key(ej, uni, nro):
    return json.dumps({"ejercicio": ej, "nro_oc": nro, "uni_compra": uni}, sort_keys=True)


def _op_key(ej, nro):
    return json.dumps({"ejercicio": ej, "nro_op": nro}, sort_keys=True)


def _sg_key(ej, deleg, nro):
    return json.dumps({"deleg_solic": deleg, "ejercicio": ej, "nro_solic": nro}, sort_keys=True)


# ─── 1. Claves ────────────────────────────────────────────────────────────────


class TestParseRecordKey:
    @pytest.mark.parametrize(
        "entity, text_in, expected",
        [
            ("oc_items", "2026-3-1023", _oc_key(2026, 3, 1023)),
            ("oc_items", "OC 2026-3-1023", _oc_key(2026, 3, 1023)),
            ("oc_items", " oc 2026/3/1023 ", _oc_key(2026, 3, 1023)),
            ("oc_items", _oc_key(2026, 3, 1023), _oc_key(2026, 3, 1023)),
            ("orden_pago", "OP 2026-1023", _op_key(2026, 1023)),
            ("orden_pago", "2026-1023", _op_key(2026, 1023)),
            ("retenciones", "Retencion de OP 2026-1023", _op_key(2026, 1023)),
            ("solic_gastos", "Gasto/Solicitud 2026-1-58", _sg_key(2026, 1, 58)),
            # JSON de la cola con el extra de las SG multi-comprobante.
            (
                "solic_gastos",
                json.dumps({"deleg_solic": 1, "ejercicio": 2026, "nro_comprob": "0001-11", "nro_solic": 58}),
                _sg_key(2026, 1, 58),
            ),
            ("proveedores", "110", "110"),
            ("proveedores", "Proveedor COD_PROV=110", "110"),
            ("proveedores", '{"cod_prov": 110}', "110"),
        ],
    )
    def test_formas_validas(self, entity, text_in, expected):
        assert parse_record_key(entity, text_in) == expected

    @pytest.mark.parametrize(
        "entity, text_in",
        [
            ("oc_items", "2026-1023"),          # falta un campo
            ("orden_pago", "2026-1-1023"),      # sobra un campo
            ("orden_pago", "OP dos-mil"),
            ("solic_gastos", '{"ejercicio": 2026}'),
            ("proveedores", ""),
            ("clasificaciones", "1.1.6.1"),     # no admite resend
        ],
    )
    def test_formas_invalidas(self, entity, text_in):
        with pytest.raises(ValueError):
            parse_record_key(entity, text_in)

    def test_key_from_row_y_base_key_coinciden_con_la_cola(self):
        raw = {"EJERCICIO": 2026.0, "UNI_COMPRA": "3", "NRO_OC": 1023, "ITEM_OC": 1}
        assert record_key_from_row("oc_items", raw) == _oc_key(2026, 3, 1023)
        assert record_base_key("orden_pago", {"ejercicio": 2026, "nro_op": 5}) == _op_key(2026, 5)
        assert record_base_key("orden_pago", "no-json") is None


# ─── 2. Query por claves / ventana ────────────────────────────────────────────


def _cfg(entity, **changes):
    return {entity: replace(ENTITY_CONFIGS[entity], **changes)}


def _rows(engine, entity, **kwargs):
    with engine.connect() as conn:
        repo = SourceRepository(conn)
        stmt = repo.build_statement(entity, Checkpoint(entity=entity), **kwargs)
        result = conn.execute(stmt)
        cols = list(result.keys())
        return [dict(zip(cols, row)) for row in result.fetchall()]


class TestBuildStatementOnlyKeys:
    def test_op_trae_solo_las_claves_aunque_el_pipeline_las_filtre(self, engine_with_data):
        with engine_with_data.connect() as conn:
            conn.execute(text(
                "INSERT INTO ORDEN_PAGO VALUES (2026, 600, 100, 'N', 'N', NULL, 10, NULL, 'Anulada')"
            ))
            conn.commit()
        with patch.dict("src.config.ENTITY_CONFIGS", _cfg("orden_pago", ejercicio_min=2026)):
            pipeline = {r["NRO_OP"] for r in _rows(engine_with_data, "orden_pago")}
            only = {
                r["NRO_OP"]
                for r in _rows(
                    engine_with_data, "orden_pago",
                    only_keys={_op_key(2025, 999), _op_key(2026, 600), _op_key(2026, 501)},
                )
            }
        # El pipeline excluye 2025 (ejercicio_min) y la OP no confirmada...
        assert 999 not in pipeline and 600 not in pipeline
        # ...pero el resend las trae igual, para que el mapper diga por que no van.
        assert only == {999, 600, 501}

    def test_retenciones_usa_la_misma_query_de_op(self, engine_with_data):
        rows = _rows(engine_with_data, "retenciones", only_keys={_op_key(2026, 502)})
        assert {r["NRO_OP"] for r in rows} == {502}

    def test_claves_que_no_parsean_no_traen_la_tabla_entera(self, engine_with_data):
        assert _rows(engine_with_data, "orden_pago", only_keys={"no-json"}) == []
        assert _rows(engine_with_data, "oc_items", only_keys=set()) == []

    def test_oc_items_por_clave_saltea_el_corte_por_ejercicio(self, engine_with_data):
        with patch.dict("src.config.ENTITY_CONFIGS", _cfg("oc_items", ejercicio_min=2026)):
            rows = _rows(engine_with_data, "oc_items", only_keys={_oc_key(2025, 1, 1)})
        assert {(r["EJERCICIO"], r["UNI_COMPRA"], r["NRO_OC"]) for r in rows} == {(2025, 1, 1)}

    def test_solic_gastos_y_proveedores(self, engine_with_data):
        sg = _rows(engine_with_data, "solic_gastos", only_keys={_sg_key(2026, 1, 202)})
        assert [(r["EJERCICIO"], r["DELEG_SOLIC"], r["NRO_SOLIC"]) for r in sg] == [(2026, 1, 202)]
        prov = _rows(engine_with_data, "proveedores", only_keys={"200"})
        assert [r["COD_PROV"] for r in prov] == [200]

    def test_ventana_de_fechas_inclusiva(self, engine_with_data):
        rows = _rows(
            engine_with_data, "orden_pago",
            date_range=(date(2026, 4, 2), date(2026, 4, 3)),
        )
        assert {r["NRO_OP"] for r in rows} == {502, 503}

    def test_claves_y_ventana_son_excluyentes(self, engine_with_data):
        with pytest.raises(ValueError):
            _rows(
                engine_with_data, "orden_pago",
                only_keys={_op_key(2026, 501)}, date_range=(date(2026, 1, 1), date(2026, 12, 31)),
            )


# ─── 3. Force en los mappers ──────────────────────────────────────────────────


def _migrator(monkeypatch, tmp_path, *, dry_run=False):
    monkeypatch.setenv("PAXAPOS_URL", "https://example.test")
    monkeypatch.setenv("PAXAPOS_TENANT", "tenant")
    monkeypatch.setenv("PAXAPOS_API_KEY", "key")
    monkeypatch.setenv("PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID", "4")
    monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(tmp_path / "links.db"))
    monkeypatch.setenv("PAXAPOS_VERIFY_SSL", "true")
    lookup_payload = {
        "lookups": {
            "unidades_de_medida": [{"id": "1", "name": "Unidad"}],
            "tipos_factura": [{"id": "2", "name": "A", "codename": "factura_a"}],
            "tipos_de_pago": [{"id": "4", "name": "Transferencia bancaria"}],
            "tipos_retencion": [{"id": "103", "codigo": "3", "name": "Retencion ganancias"}],
        }
    }
    with patch("src.exporter.fetch_migrator_lookups", return_value=lookup_payload):
        return MigratorExporter(dry_run=dry_run)


def _ok_response(section, payload_items, ext_of=lambda it: it["external_id"], base_id=9000):
    results = [
        {"success": True, "mode": "update", "external_id": ext_of(it), "id": base_id + i}
        for i, it in enumerate(payload_items)
    ]
    return {
        "stats": {section: {"ok": len(results), "error": 0}},
        "results": {section: results},
    }


_OC_COLUMNS = [
    "EJERCICIO", "UNI_COMPRA", "NRO_OC", "COD_PROV",
    "OC_FECH_OC", "OC_OBSERVACIONES", "OC_ESTADO_OC", "OC_FECH_CONFIRM", "OC_IMPORTE_TOT",
    "SG_JURISDICCION",
    "ITEM_OC", "DELEG_SOLIC", "NRO_SOLIC", "DESCRIPCION", "CANTIDAD", "IMP_UNITARIO", "CANT_RECIB",
]


def _oc_row(nro_oc=10, cod_prov=5):
    return (
        2026, 1, nro_oc, cod_prov,
        "2026-08-01", "OC test", "R", "2026-08-02", 500.0,
        None,
        1, 10, 30, "Item", 1.0, 500.0, 1.0,
    )


class TestForceOcItems:
    def _exporter(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        exporter._link_store.save_link("proveedores", "5", "9001")
        return exporter

    def _post(self, sent):
        def _p(url, payload):
            sent.append(payload)
            return _ok_response("ordenes_compra", payload["ordenes_compra"])
        return _p

    def test_oc_sin_cambios_solo_se_reenvia_forzada(self, monkeypatch, tmp_path):
        exporter = self._exporter(monkeypatch, tmp_path)
        sent = []
        with patch.object(exporter, "_post_json", side_effect=self._post(sent)):
            exporter.write_batch("oc_items", _OC_COLUMNS, [_oc_row()])
            exporter.write_batch("oc_items", _OC_COLUMNS, [_oc_row()])
            assert len(sent) == 1, "la 2da corrida sin cambios no debe reenviar"

            exporter.set_force_keys("oc_items", {_oc_key(2026, 1, 10)})
            exporter.write_batch("oc_items", _OC_COLUMNS, [_oc_row()])
        assert len(sent) == 2
        assert sent[-1]["ordenes_compra"][0]["external_id"]["nro_oc"] == 10
        [outcome] = exporter.get_last_batch_outcomes()
        assert outcome.ok and outcome.base_key == _oc_key(2026, 1, 10)

    def test_oc_permanent_se_reenvia_forzada(self, monkeypatch, tmp_path):
        exporter = self._exporter(monkeypatch, tmp_path)
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        exporter.attach_retry_store(retry)
        retry.mark_permanent("oc_items", _oc_key(2026, 1, 10), "backend_rejected", "rechazo viejo")

        sent = []
        with patch.object(exporter, "_post_json", side_effect=self._post(sent)):
            exporter.write_batch("oc_items", _OC_COLUMNS, [_oc_row()])
            assert sent == []
            exporter.set_force_keys("oc_items", {_oc_key(2026, 1, 10)})
            exporter.write_batch("oc_items", _OC_COLUMNS, [_oc_row()])
        assert len(sent) == 1
        assert retry.list_items("oc_items") == [], "el OK forzado resuelve la cola"
        retry.close()

    def test_force_no_saltea_reglas_de_negocio(self, monkeypatch, tmp_path):
        exporter = self._exporter(monkeypatch, tmp_path)
        sink = RecordEventSink()
        exporter.attach_event_sink(sink)
        exporter.set_force_keys("oc_items", {_oc_key(2026, 1, 11), _oc_key(2026, 1, 12)})
        sent = []
        with patch.object(exporter, "_post_json", side_effect=self._post(sent)):
            # 11: proveedor excluido por configuracion; 12: proveedor sin link.
            exporter.write_batch("oc_items", _OC_COLUMNS, [_oc_row(11, 50001), _oc_row(12, 77)])
        assert sent == []
        assert "excluido" in sink.reason_for("oc_items", _oc_key(2026, 1, 11))
        assert "resend --entity proveedores --key 77" in sink.reason_for("oc_items", _oc_key(2026, 1, 12))


class TestForceOrdenPago:
    COLUMNS = [
        "EJERCICIO", "NRO_OP", "ESTADO_OP", "CONFIRMADO", "FECH_CONFIRM",
        "IMPORTE_TOTAL", "CONCEPTO", "COD_PROV",
        "SG_DELEG_SOLIC", "SG_NRO_SOLIC", "OPI_NRO_COMPROB",
    ]
    ROW = ("2026", "1001", "C", "S", "2026-03-11 00:00:00", "500", "Pago", "555", "1", "100", "0001-00000100")

    def test_op_sin_cambios_forzada_va_con_el_id_de_egreso(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        exporter._link_store.save_link("proveedores", "555", remote_id="42")
        exporter._link_store.save_link(
            "orden_pago", _op_key(2026, 1001), "9001",
            estado_op="C", confirmado="S", fech_confirm="2026-03-11", importe_total="500",
        )
        sent = []

        def _post(url, payload):
            sent.append(payload)
            return _ok_response("ordenes_pago", payload["ordenes_pago"])

        with patch.object(exporter, "_post_json", side_effect=_post):
            exporter.write_batch("orden_pago", self.COLUMNS, [self.ROW])
            assert sent == [], "OP ya migrada y sin cambios: no se reenvia"
            exporter.set_force_keys("orden_pago", {_op_key(2026, 1001)})
            exporter.write_batch("orden_pago", self.COLUMNS, [self.ROW])
        assert len(sent) == 1
        assert sent[0]["ordenes_pago"][0]["Egreso"]["id"] == 9001


class _FakeDeduccionesRepo:
    def __init__(self, deducciones_by_op):
        self._deducciones_by_op = deducciones_by_op

    def fetch_deducciones_for_ops(self, op_keys):
        return self._deducciones_by_op


class TestForceRetenciones:
    def test_mismo_fingerprint_solo_se_reenvia_forzado(self, monkeypatch, tmp_path):
        exporter = _migrator(monkeypatch, tmp_path)
        op_sk = _op_key(2026, 100)
        exporter._link_store.save_link("orden_pago", op_sk, "5001")
        exporter.attach_source(_FakeDeduccionesRepo({
            (2026, 100): [{"codigo_deduc": "3", "importe_reten": 150.0, "descripcion": "Ganancias"}],
        }))
        sent = []

        def _post(url, payload):
            sent.append(payload)
            return _ok_response("retenciones", payload["retenciones"], base_id=5001)

        with patch.object(exporter, "_post_json", side_effect=_post):
            exporter.write_batch("retenciones", ["EJERCICIO", "NRO_OP"], [(2026, 100)])
            exporter.write_batch("retenciones", ["EJERCICIO", "NRO_OP"], [(2026, 100)])
            assert len(sent) == 1
            exporter.set_force_keys("retenciones", {op_sk})
            exporter.write_batch("retenciones", ["EJERCICIO", "NRO_OP"], [(2026, 100)])
        assert len(sent) == 2


class TestForceSolicGastos:
    COLUMNS = [
        "EJERCICIO", "DELEG_SOLIC", "NRO_SOLIC", "FECH_SOLIC", "ESTADO_SOLIC",
        "IMPORTE_TOT", "CTA_COMPROB_COUNT", "CTA_NRO_COMPROB", "CTA_TIPO_COMPROB",
        "CTA_FECH_COMPROB", "CTA_FECH_VENCIM", "CTA_IMPORTE_COMPR",
        "CTA_IMPORTE_NETO", "CTA_IMPORTE_SIN_IVA", "OC_COD_PROV",
    ]

    def _mapper(self, stored_links):
        from src.mappers.solic_gastos import SolicGastosMapper

        class _Lookup:
            def resolve_tipo_factura_id(self, _v):
                return 2

        class _LinkStore:
            def get_sent_oc_gasto_refs(self):
                return {"SG-2026-1-100"}

            def get_all_links(self, _entity):
                return [{
                    "source_key": _oc_key(2026, 1, 50),
                    "remote_id": "700",
                    "gasto_refs": "SG-2026-1-100",
                }]

            def get_remote_id(self, _entity, _key):
                return "42"

            def get_link(self, _entity, key):
                return stored_links.get(key)

        resolver = {
            "success": True,
            "gastos": [{
                "id": 91, "pedido_id": 700, "proveedor_id": 42,
                "factura_nro": "11", "punto_de_venta": "0001",
                "empty_fields": ["importe_neto"],
            }],
        }
        return SolicGastosMapper(
            link_store=_LinkStore(),
            lookup_resolver=_Lookup(),
            resolve_gastos_fn=lambda pedido_ids, comprobantes: resolver,
        )

    def _row(self):
        vals = {
            "EJERCICIO": "2026", "DELEG_SOLIC": "1", "NRO_SOLIC": "100",
            "FECH_SOLIC": "2026-03-01", "ESTADO_SOLIC": "C", "IMPORTE_TOT": "1000",
            "CTA_COMPROB_COUNT": "1", "CTA_NRO_COMPROB": "0001-11", "CTA_TIPO_COMPROB": "FA",
            "CTA_FECH_COMPROB": "2026-03-01", "CTA_IMPORTE_COMPR": "1000",
            "CTA_IMPORTE_NETO": "900", "OC_COD_PROV": "77",
        }
        return tuple(vals.get(c, "") for c in self.COLUMNS)

    def test_mismo_hash_solo_se_reenvia_forzado(self):
        stored: dict = {}
        mapper = self._mapper(stored)
        payload, raw_by_sk = mapper.build_payload(self.COLUMNS, [self._row()], dry_run=False, payload_options={})
        assert payload is not None
        # Simular que la corrida anterior guardo el link con ese mismo hash.
        for sk, raw in raw_by_sk.items():
            stored[sk] = {"payload_hash": raw["_payload_hash"]}

        payload, _ = mapper.build_payload(self.COLUMNS, [self._row()], dry_run=False, payload_options={})
        assert payload is None

        mapper._force_keys = frozenset({_sg_key(2026, 1, 100)})
        payload, _ = mapper.build_payload(self.COLUMNS, [self._row()], dry_run=False, payload_options={})
        assert payload is not None and payload["gastos"][0]["Gasto"]["id"] == 91


# ─── 4. _resend_records de punta a punta (proveedores) ────────────────────────


_PROV_ROWS = [
    (100, "Prov A", "Prov A SA", "2026-01-10"),
    (200, "Prov B", "Prov B SA", "2026-01-11"),
    (300, "Prov C", "Prov C SA", "2026-01-12"),
    (400, None, None, "2026-01-13"),           # sin nombre: fila invalida
    (50001, "Telefonica", "Telefonica", "2026-01-14"),  # excluido por config
]


@pytest.fixture
def resend_env(monkeypatch, tmp_path):
    """Origen SQLite + exporter real con `_post_json` falso + cola temporal.

    `_build_engine` (CheckpointStore) explota si se llama: el resend no debe
    leer ni escribir checkpoints.
    """
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'rafam.db'}")
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE PROVEEDORES (COD_PROV INTEGER PRIMARY KEY, FANTASIA TEXT, "
            "RAZON_SOCIAL TEXT, FECHA_ULT_COMP DATETIME)"
        ))
        for row in _PROV_ROWS:
            conn.execute(text("INSERT INTO PROVEEDORES VALUES (:a, :b, :c, :d)"),
                         dict(zip("abcd", row)))
        conn.commit()

    exporter = _migrator(monkeypatch, tmp_path)
    exporter.close = lambda: None
    behavior = {"reject": set(), "boom": set(), "infra": False}
    posts: list[list[int]] = []

    def _post(url, payload):
        cods = [p["external_id"]["cod_prov"] for p in payload["proveedores"]]
        posts.append(cods)
        if behavior["infra"]:
            raise BackendInfraError("SQLSTATE[42S02]: Base table or view not found")
        if behavior["boom"] & set(cods):
            raise RuntimeError("HTTP 500: Internal Server Error")
        results, errors = [], []
        for p in payload["proveedores"]:
            cod = p["external_id"]["cod_prov"]
            if cod in behavior["reject"]:
                errors.append({
                    "section": "proveedores",
                    "external_id": p["external_id"],
                    "message": "Error guardando proveedor",
                    "validationErrors": {"cuit": ["El CUIT ya existe"]},
                })
            else:
                results.append({"success": True, "mode": "create", "external_id": p["external_id"], "id": 7000 + cod})
        return {
            "stats": {"proveedores": {"ok": len(results), "error": len(errors)}},
            "results": {"proveedores": results},
            "errors": errors,
        }

    exporter._post_json = _post

    def _build_exporter(dry_run=False):
        exporter._dry_run = dry_run
        return exporter

    def _no_checkpoints():
        raise AssertionError("resend no debe tocar el CheckpointStore")

    monkeypatch.setattr(main_module, "create_source_engine", lambda: engine)
    monkeypatch.setattr(main_module, "build_exporter", _build_exporter)
    monkeypatch.setattr(main_module, "_build_engine", _no_checkpoints)
    retry = RetryStore(db_path=str(tmp_path / "retry.db"))
    yield {"exporter": exporter, "behavior": behavior, "posts": posts, "retry": retry}
    retry.close()


def _by_key(report):
    return {r.key: r for r in report.results}


class TestResendRecords:
    def test_reporte_por_clave(self, resend_env):
        resend_env["behavior"]["reject"] = {200}
        report = main_module._resend_records(
            resend_env["retry"], "proveedores", keys=["100", "200", "400", "50001", "999"],
        )
        res = _by_key(report)
        assert res["100"].status == main_module.RESEND_OK
        assert "id Paxapos=7100" in res["100"].detail
        assert res["200"].status == main_module.RESEND_REJECTED
        assert "El CUIT ya existe" in res["200"].detail
        assert res["400"].status == main_module.RESEND_SKIPPED
        assert "invalida" in res["400"].detail
        assert res["50001"].status == main_module.RESEND_SKIPPED
        assert "excluido" in res["50001"].detail
        assert res["999"].status == main_module.RESEND_NOT_FOUND
        assert report.exit_code() == 1
        # La cola refleja el resultado real: el rechazo queda, el OK no.
        assert [it.external_id for it in resend_env["retry"].list_items("proveedores")] == ["200"]

    def test_permanent_se_reencola_y_se_resuelve(self, resend_env):
        retry = resend_env["retry"]
        retry.mark_permanent("proveedores", "100", "backend_rejected", "CUIT invalido")

        report = main_module._resend_records(retry, "proveedores", keys=["100"])
        assert report.requeued == 1
        assert _by_key(report)["100"].status == main_module.RESEND_OK
        assert report.exit_code() == 0
        assert retry.list_items("proveedores") == []

    def test_dry_run_no_toca_la_cola(self, resend_env):
        retry = resend_env["retry"]
        retry.mark_permanent("proveedores", "100", "backend_rejected", "CUIT invalido")

        report = main_module._resend_records(retry, "proveedores", keys=["100"], dry_run=True)
        assert report.requeued == 0
        assert _by_key(report)["100"].status == main_module.RESEND_OK
        assert "dry-run" in _by_key(report)["100"].detail
        [item] = retry.list_items("proveedores")
        assert item.status == STATUS_PERMANENT

    def test_registro_ya_migrado_se_reenvia_forzado(self, resend_env):
        raw = {"COD_PROV": 100, "FANTASIA": "Prov A", "RAZON_SOCIAL": "Prov A SA"}
        current_hash = compute_payload_hash(map_proveedor_migrator_row(raw)["Proveedor"])
        resend_env["exporter"]._link_store.save_link("proveedores", "100", "7100", payload_hash=current_hash)

        report = main_module._resend_records(resend_env["retry"], "proveedores", keys=["100"])
        assert _by_key(report)["100"].status == main_module.RESEND_OK
        assert resend_env["posts"] == [[100]]

    def test_batch_caido_se_aisla_clave_por_clave(self, resend_env):
        resend_env["behavior"]["boom"] = {200}
        report = main_module._resend_records(
            resend_env["retry"], "proveedores", keys=["100", "200", "300"],
        )
        res = _by_key(report)
        assert res["100"].status == main_module.RESEND_OK
        assert res["300"].status == main_module.RESEND_OK
        assert res["200"].status == main_module.RESEND_FAILED
        assert "HTTP 500" in res["200"].detail
        assert resend_env["posts"] == [[100, 200, 300], [100], [200], [300]]

    def test_backend_caido_corta_sin_aislar(self, resend_env):
        resend_env["behavior"]["infra"] = True
        report = main_module._resend_records(
            resend_env["retry"], "proveedores", keys=["100", "200", "300"], batch_size=1,
        )
        assert {r.status for r in report.results} == {main_module.RESEND_NOT_SENT}
        assert len(resend_env["posts"]) == 1, "con el backend caido no se insiste"
        assert report.aborted_reason

    def test_ventana_reporta_sin_cambios_y_no_falla(self, resend_env):
        raw = {"COD_PROV": 100, "FANTASIA": "Prov A", "RAZON_SOCIAL": "Prov A SA"}
        current_hash = compute_payload_hash(map_proveedor_migrator_row(raw)["Proveedor"])
        resend_env["exporter"]._link_store.save_link("proveedores", "100", "7100", payload_hash=current_hash)

        report = main_module._resend_records(
            resend_env["retry"], "proveedores", date_range=(date(2026, 1, 10), date(2026, 1, 12)),
        )
        res = _by_key(report)
        assert set(res) == {"100", "200", "300"}
        assert res["100"].status == main_module.RESEND_UNCHANGED
        assert res["200"].status == main_module.RESEND_OK
        assert report.exit_code() == 0


# ─── 5. CLI ───────────────────────────────────────────────────────────────────


def _resend_args(**overrides):
    base = dict(
        entity="orden_pago", key=None, keys_file=None, from_queue=False,
        desde=None, hasta=None, status=None, batch_size=None, dry_run=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


class TestResendCli:
    def test_clave_invalida_sale_con_2(self):
        with pytest.raises(SystemExit) as exc:
            main_module.cmd_resend(_resend_args(key=["OP dos-mil"]))
        assert exc.value.code == 2

    def test_status_requiere_from_queue(self):
        with pytest.raises(SystemExit) as exc:
            main_module.cmd_resend(_resend_args(key=["2026-1"], status="permanent"))
        assert exc.value.code == 2

    def test_keys_file_y_exit_code(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "_LOCK_PATH", tmp_path / "migrator.lock")
        monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(tmp_path / "state.db"))
        keys_file = tmp_path / "claves.txt"
        keys_file.write_text("# OPs del mail\nOP 2026-10\n\n2026-11  # otra\n", encoding="utf-8")
        calls = []

        def _fake(retry_store, entity, *, keys=None, date_range=None, dry_run=False, batch_size=None):
            calls.append((entity, keys))
            report = main_module.ResendReport(entity=entity, dry_run=dry_run, by_keys=True)
            report.results = [
                main_module.ResendResult(keys[0], main_module.RESEND_OK),
                main_module.ResendResult(keys[1], main_module.RESEND_REJECTED, "x"),
            ]
            return report

        monkeypatch.setattr(main_module, "_resend_records", _fake)
        with pytest.raises(SystemExit) as exc:
            main_module.cmd_resend(_resend_args(keys_file=str(keys_file)))
        assert exc.value.code == 1
        assert calls == [("orden_pago", [_op_key(2026, 10), _op_key(2026, 11)])]

    def test_send_now_manda_solo_las_claves_de_la_cola(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "_LOCK_PATH", tmp_path / "migrator.lock")
        monkeypatch.setenv("LOCAL_STATE_DB_PATH", str(tmp_path / "state.db"))
        retry = RetryStore(db_path=str(tmp_path / "state.db"))
        retry.enqueue("orden_pago", _op_key(2026, 10), "backend_rejected", "x")
        retry.enqueue("orden_pago", _op_key(2026, 11), "dependency_missing", "OC aun no migrada")
        retry.close()
        calls = []

        def _fake(retry_store, entity, *, keys=None, date_range=None, dry_run=False, batch_size=None):
            calls.append((entity, keys))
            report = main_module.ResendReport(entity=entity, dry_run=False, by_keys=True)
            report.results = [
                main_module.ResendResult(keys[0], main_module.RESEND_OK),
                # Seguir esperando una dependencia no hace fallar --send-now.
                main_module.ResendResult(keys[1], main_module.RESEND_SKIPPED, "en espera"),
            ]
            return report

        monkeypatch.setattr(main_module, "_resend_records", _fake)
        args = argparse.Namespace(
            entity="orden_pago", status=None, external_id=None,
            requeue=False, dismiss=False, note=None, send_now=True,
        )
        main_module.cmd_retry_queue(args)
        assert calls == [("orden_pago", [_op_key(2026, 10), _op_key(2026, 11)])]


class TestLockConEspera:
    def test_espera_a_que_se_libere(self, tmp_path, monkeypatch):
        lock_path = tmp_path / "migrator.lock"
        monkeypatch.setattr(main_module, "_LOCK_PATH", lock_path)
        monkeypatch.setattr(main_module, "_LOCK_POLL_SECONDS", 0.05)
        holder = open(lock_path, "a")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        timer = threading.Timer(0.3, lambda: (fcntl.flock(holder.fileno(), fcntl.LOCK_UN), holder.close()))
        timer.start()
        try:
            with main_module._exclusive_run_lock(wait_seconds=5):
                acquired = True
        finally:
            timer.join()
        assert acquired

    def test_sin_espera_sale_con_75(self, tmp_path, monkeypatch):
        lock_path = tmp_path / "migrator.lock"
        monkeypatch.setattr(main_module, "_LOCK_PATH", lock_path)
        holder = open(lock_path, "a")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with pytest.raises(SystemExit) as exc:
                with main_module._exclusive_run_lock():
                    pass
            assert exc.value.code == 75
        finally:
            holder.close()
