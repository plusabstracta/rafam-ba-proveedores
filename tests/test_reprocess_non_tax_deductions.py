"""scripts/reprocess_non_tax_deductions.py (paxapos/paxapos#738).

El reproceso de las OP ya migradas cuyas garantias / cajas de medicos se
omitieron: busca en RAFAM (solo lectura), clasifica contra el estado local y,
solo con --apply, encola en la cola LOCAL para que ``run --entity retenciones``
las reenvie. Nunca escribe en RAFAM ni en Paxapos.
"""

from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from src.retry_store import REASON_DEPENDENCY_MISSING, RetryStore
from src.source_repository import SourceRepository

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "reprocess_non_tax_deductions.py"
_SPEC = importlib.util.spec_from_file_location("reprocess_non_tax_deductions", SCRIPT_PATH)
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)


@pytest.fixture(autouse=True)
def _mapa_por_default(monkeypatch):
    monkeypatch.delenv("RAFAM_NON_TAX_DEDUCTION_MAP", raising=False)


def _sk(ejercicio, nro_op):
    return json.dumps({"ejercicio": ejercicio, "nro_op": nro_op}, sort_keys=True)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE ORDEN_PAGO_DEDUC (
                EJERCICIO INTEGER, NRO_OP INTEGER, CODIGO_DEDUC INTEGER, IMPORTE_RETEN REAL,
                COMPROB_DEDUC INTEGER, ALICUOTA REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE DEDUCCIONES (
                CODIGO INTEGER, DESCRIPCION TEXT, TIPO_DEDUC TEXT, EJERCICIO INTEGER
            )
        """))
        conn.execute(text("""
            INSERT INTO DEDUCCIONES VALUES
                (3, 'GANANCIAS', 'I', 2026), (4, 'GARANTIA', 'O', 2026),
                (8, 'RETENCIONES CAJA DE MEDICOS', 'O', 2026), (1, 'RETENCIONES I.P.S.', 'O', 2026)
        """))
        conn.execute(text("""
            INSERT INTO ORDEN_PAGO_DEDUC VALUES
                (2026, 100, 4, 2500, 0, NULL),   -- garantia, migrada, sin cola
                (2026, 100, 3, 400, 0, 4.13),    -- ganancias (no se reprocesa por esta via)
                (2026, 200, 8, 1000, 0, 5),      -- caja de medicos, ya en cola (non_tax_deduction)
                (2026, 300, 4, 700, 0, NULL),    -- garantia, OP aun sin migrar
                (2026, 400, 4, 900, 0, NULL),    -- garantia, Egreso borrado (permanente)
                (2026, 500, 1, 300, 0, NULL),    -- IPS: sin mapeo, no es candidata
                (2025, 600, 4, 800, 0, NULL),    -- ejercicio < min
                (2026, 700, 4, 0, 0, NULL)       -- importe 0
        """))
    return engine


def _candidatos(engine, ejercicio_min=2026):
    with engine.connect() as conn:
        return script.find_candidates(SourceRepository(conn), conn, ejercicio_min)


class TestFindCandidates:
    def test_solo_op_con_deduccion_mapeada_del_ejercicio_y_con_importe(self):
        cands = _candidatos(_engine())

        assert set(cands) == {(2026, 100), (2026, 200), (2026, 300), (2026, 400)}
        assert [d["codigo_deduc"] for d in cands[(2026, 100)]] == [4], "Ganancias (I) no es candidata"

    def test_el_mapa_vacio_no_encuentra_nada(self, monkeypatch):
        monkeypatch.setenv("RAFAM_NON_TAX_DEDUCTION_MAP", "")
        assert _candidatos(_engine()) == {}

    def test_una_impositiva_con_codigo_mapeado_no_es_candidata(self):
        engine = _engine()
        with engine.begin() as conn:
            conn.execute(text("UPDATE DEDUCCIONES SET TIPO_DEDUC = 'I' WHERE CODIGO = 8"))
        assert (2026, 200) not in _candidatos(engine)

    def test_ejercicio_min_acota(self):
        assert (2025, 600) in _candidatos(_engine(), ejercicio_min=2025)


class TestBuildPlan:
    def _plan(self):
        cands = _candidatos(_engine())
        op_links = {
            _sk(2026, 100): {"remote_id": "5001"},
            _sk(2026, 200): {"remote_id": "5002"},
            _sk(2026, 400): {"remote_id": "5004", "deleted_at": "2026-09-01"},
        }
        return {p["nro_op"]: p for p in script.build_plan(
            cands,
            op_links=op_links,
            pending_ids={_sk(2026, 200)},
            permanent_ids={_sk(2026, 400)},
        )}

    def test_clasifica_cada_op_contra_el_estado_local(self):
        plan = self._plan()

        assert plan[100]["state"] == script.ST_TO_ENQUEUE
        assert plan[200]["state"] == script.ST_ALREADY_PENDING
        assert plan[300]["state"] == script.ST_NOT_MIGRATED
        assert plan[400]["state"] == script.ST_NOT_MIGRATED, "Egreso borrado (deleted_at): no se reenvia"

    def test_una_op_permanente_en_cola_no_se_reencola(self):
        cands = _candidatos(_engine())
        plan = script.build_plan(
            cands,
            op_links={_sk(2026, 400): {"remote_id": "5004"}},
            pending_ids=set(),
            permanent_ids={_sk(2026, 400)},
        )
        assert {p["nro_op"]: p["state"] for p in plan}[400] == script.ST_PERMANENT

    def test_la_deduccion_lleva_concepto_y_importe(self):
        d = self._plan()[100]["deducciones"][0]
        assert d == {"codigo": "4", "concepto": "Fondo de garantía", "importe": Decimal("2500.0")}


class TestReporteYApply:
    def _plan(self):
        return script.build_plan(
            _candidatos(_engine()),
            op_links={_sk(2026, 100): {"remote_id": "5001"}, _sk(2026, 200): {"remote_id": "5002"}},
            pending_ids={_sk(2026, 200)},
            permanent_ids=set(),
        )

    def test_el_dry_run_informa_sin_encolar_nada(self, tmp_path):
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        report = script.format_report(self._plan(), apply=False, ejercicio_min=2026)

        assert "DRY-RUN" in report
        assert "A ENCOLAR (migradas; hay que reinyectarlas): 1 OP" in report
        assert "YA EN COLA" in report and "SIN MIGRAR" in report
        assert "Fondo de garantía" in report and "Caja de Médicos" in report
        # 2500 (OP 100, a encolar) + 1000 (OP 200, ya en cola) bajan del neto.
        assert "$3,500.00" in report
        assert retry.pending_external_ids("retenciones") == set()
        retry.close()

    def test_apply_encola_solo_las_que_faltan(self, tmp_path):
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        retry.enqueue("retenciones", _sk(2026, 200), REASON_DEPENDENCY_MISSING, "legacy", reason_detail="non_tax_deduction")

        n = script.apply_plan(self._plan(), retry)

        assert n == 1
        assert retry.pending_external_ids("retenciones") == {_sk(2026, 100), _sk(2026, 200)}
        nueva = [i for i in retry.list_items("retenciones") if i.external_id == _sk(2026, 100)][0]
        assert nueva.reason_code == REASON_DEPENDENCY_MISSING
        assert nueva.reason_detail == script.REASON_DETAIL_REPROCESS
        assert "paxapos#738" in nueva.error_message
        # La que ya estaba en cola no se pisa.
        vieja = [i for i in retry.list_items("retenciones") if i.external_id == _sk(2026, 200)][0]
        assert vieja.reason_detail == "non_tax_deduction"
        retry.close()

    def test_apply_es_idempotente(self, tmp_path):
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        retry.enqueue("retenciones", _sk(2026, 200), REASON_DEPENDENCY_MISSING, "legacy", reason_detail="non_tax_deduction")
        op_links = {_sk(2026, 100): {"remote_id": "5001"}, _sk(2026, 200): {"remote_id": "5002"}}

        def plan():
            return script.build_plan(
                _candidatos(_engine()),
                op_links=op_links,
                pending_ids=retry.pending_external_ids("retenciones"),
                permanent_ids=retry.permanent_external_ids("retenciones"),
            )

        assert script.apply_plan(plan(), retry) == 1
        # Segunda corrida: la OP 100 ya esta en cola -> el plan la ve como 'ya_en_cola'.
        assert script.apply_plan(plan(), retry) == 0
        retry.close()


class TestCli:
    def test_dry_run_y_apply_son_excluyentes(self):
        with pytest.raises(SystemExit):
            script.main(["--dry-run", "--apply"])


class TestRescatePermanent:
    """plusabstracta/rafam-ba-proveedores#20: permanent por rechazo de un backend viejo."""

    def _retry(self, tmp_path):
        retry = RetryStore(db_path=str(tmp_path / "retry.db"))
        # OP 100 (con link): permanent por rechazo del receptor viejo, en 'retenciones'.
        retry.mark_permanent("retenciones", _sk(2026, 100), "backend_rejected",
                             "requiere tipo_impuesto_id valido", reason_detail="validation")
        # OP 200 (con link): Egreso borrado a mano -> NO se rescata.
        retry.mark_permanent("retenciones", _sk(2026, 200), "backend_rejected",
                             "Egreso borrado", reason_detail="destination_deleted")
        # OP 300 (sin link): OP embebida rechazada entera -> permanent en orden_pago.
        retry.mark_permanent("orden_pago", _sk(2026, 300), "backend_rejected",
                             "requiere tipo_impuesto_id valido", reason_detail="validation")
        return retry

    def _plan(self, retry):
        op_links = {_sk(2026, 100): {"remote_id": "5001"}, _sk(2026, 200): {"remote_id": "5002"}}
        return {p["nro_op"]: p for p in script.build_plan(
            _candidatos(_engine()),
            op_links=op_links,
            pending_ids=retry.pending_external_ids("retenciones"),
            permanent_ids=retry.permanent_external_ids("retenciones"),
            requeue_permanent=script.rescuable_permanent(retry),
        )}

    def test_rescuable_excluye_destination_deleted(self, tmp_path):
        retry = self._retry(tmp_path)
        r = script.rescuable_permanent(retry)
        assert r["retenciones"] == {_sk(2026, 100)}
        assert r["orden_pago"] == {_sk(2026, 300)}
        retry.close()

    def test_clasifica_rescate_y_terminal(self, tmp_path):
        retry = self._retry(tmp_path)
        plan = self._plan(retry)
        assert plan[100]["state"] == script.ST_REQUEUE_PERMANENT
        assert plan[200]["state"] == script.ST_PERMANENT
        assert plan[300]["state"] == script.ST_REQUEUE_PERMANENT, "OP embebida sin link"
        assert plan[300]["requeue_entities"] == ["orden_pago"]
        retry.close()

    def test_dry_run_no_toca_la_cola_y_lista_el_rescate(self, tmp_path):
        retry = self._retry(tmp_path)
        report = script.format_report(list(self._plan(retry).values()), apply=False, ejercicio_min=2026)
        assert "PERMANENT POR RECHAZO" in report and ": 2 OP" in report
        assert retry.pending_external_ids("retenciones") == set()
        assert len(retry.permanent_external_ids("retenciones")) == 2
        retry.close()

    def test_apply_devuelve_a_pending_solo_las_rescatables(self, tmp_path):
        retry = self._retry(tmp_path)
        n = script.apply_plan(list(self._plan(retry).values()), retry)
        assert n == 2
        assert retry.pending_external_ids("retenciones") == {_sk(2026, 100)}
        assert retry.pending_external_ids("orden_pago") == {_sk(2026, 300)}
        assert retry.permanent_external_ids("retenciones") == {_sk(2026, 200)}, "destination_deleted intacta"
        # Idempotente: ya estan pending, el plan las ve como 'ya_en_cola' / no rescatables.
        assert script.rescuable_permanent(retry)["retenciones"] == set()
        retry.close()
