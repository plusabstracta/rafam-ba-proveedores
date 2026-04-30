"""
Test de integración OC: DB SQLite local → MigratorExporter → payloads.

Usa la DB en state/dev_rafam.db (cargada desde CSVs de output/).
Pre-linkea proveedores y jurisdicciones para simular un sync previo,
luego procesa oc_items y valida que los payloads sean correctos.

Requiere: DB_BACKEND=sqlite (pytest.ini lo setea).
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

from src.exporter import MigratorExporter
from src.models import Checkpoint
from src.source_repository import SourceRepository

_DEV_DB = Path(__file__).resolve().parent.parent / "state" / "dev_rafam.db"

pytestmark = pytest.mark.skipif(
    not _DEV_DB.exists(),
    reason="state/dev_rafam.db no existe — correr scripts/load_csv_to_sqlite.py primero",
)


@pytest.fixture(scope="module")
def dev_engine():
    return create_engine(f"sqlite+pysqlite:///{_DEV_DB}", future=True)


@pytest.fixture(scope="module")
def exporter_with_links(dev_engine):
    """MigratorExporter con proveedores y rubros pre-linkeados desde la DB local."""
    with patch("src.exporter.fetch_migrator_lookups") as ml:
        ml.return_value = {
            "unidades_de_medida": [{"id": "1", "name": "Unidad"}],
            "tipos_factura": [{"id": "2", "name": "Factura A", "codename": "factura_a"}],
            "tipos_de_pago": [{"id": "4", "name": "Transferencia"}],
        }
        with patch.dict("os.environ", {
            "MIGRATOR_BASE_URL": "https://test.example.com",
            "MIGRATOR_TENANT": "test",
            "MIGRATOR_API_KEY": "key",
            "MIGRATOR_DEFAULT_UNIDAD_ID": "1",
            "MIGRATOR_DEFAULT_TIPO_PAGO_ID": "4",
        }):
            exp = MigratorExporter(dry_run=True)

    with dev_engine.connect() as conn:
        # Pre-linkear proveedores
        for (cod,) in conn.execute(text("SELECT COD_PROV FROM PROVEEDORES")).fetchall():
            exp._link_store.save_link(
                entity="proveedores",
                source_key=str(cod),
                remote_id=str(10000 + int(cod)),
            )
        # Pre-linkear rubros (jurisdicciones)
        for (j,) in conn.execute(text("SELECT JURISDICCION FROM JURISDICCIONES")).fetchall():
            rubro_key = json.dumps({"jurisdiccion": str(j)}, sort_keys=True)
            exp._link_store.save_link(
                entity="rubro",
                source_key=rubro_key,
                remote_id=str(abs(hash(j)) % 1000 + 1),
            )
    return exp


@pytest.fixture(scope="module")
def oc_payloads(dev_engine, exporter_with_links):
    """Procesa oc_items completo y captura los payloads enviados."""
    sent = []

    def fake_post(url, payload):
        sent.append(payload)
        n = len(payload.get("ordenes_compra", []))
        return {
            "stats": {"ordenes_compra": {"ok": n, "error": 0}},
            "results": {"ordenes_compra": []},
        }

    exporter_with_links._post_json = fake_post

    with dev_engine.connect() as conn:
        repo = SourceRepository(conn)
        cp = Checkpoint(entity="oc_items")
        stmt = repo.build_statement("oc_items", cp)
        result = conn.execute(stmt)
        columns = list(result.keys())
        all_rows = [tuple(r) for r in result.fetchall()]

        for i in range(0, len(all_rows), 500):
            batch = all_rows[i : i + 500]
            exporter_with_links.write_batch("oc_items", columns, batch)

    # Flatten all OCs from all payloads
    all_ocs = []
    for p in sent:
        all_ocs.extend(p.get("ordenes_compra", []))
    return sent, all_ocs


class TestOcIntegration:

    def test_se_generan_payloads(self, oc_payloads):
        sent, all_ocs = oc_payloads
        assert len(sent) > 0, "Debería generar al menos un payload"

    def test_total_ocs_con_estado_r(self, oc_payloads, dev_engine):
        """Solo OCs con estado R se envían (no A ni N)."""
        _, all_ocs = oc_payloads
        with dev_engine.connect() as conn:
            r_count = conn.execute(
                text("SELECT COUNT(DISTINCT EJERCICIO || '-' || UNI_COMPRA || '-' || NRO_OC) FROM ORDEN_COMPRA WHERE ESTADO_OC = 'R'")
            ).scalar()
        # Las OCs enviadas deberían ser ≤ R_count (puede ser menor si alguna no tiene items válidos)
        assert len(all_ocs) <= r_count
        assert len(all_ocs) > 0

    def test_cada_oc_tiene_proveedor_id(self, oc_payloads):
        _, all_ocs = oc_payloads
        for oc in all_ocs:
            pedido = oc["Pedido"]
            assert "proveedor_id" in pedido, f"OC {oc['external_id']} sin proveedor_id"
            assert isinstance(pedido["proveedor_id"], int)

    def test_cada_oc_tiene_created_real(self, oc_payloads):
        _, all_ocs = oc_payloads
        con_created = [oc for oc in all_ocs if "created" in oc["Pedido"]]
        # La gran mayoría debería tener fecha (FECH_OC casi nunca es NULL)
        assert len(con_created) > len(all_ocs) * 0.9
        for oc in con_created:
            created = oc["Pedido"]["created"]
            assert created.endswith(" 00:00:00"), f"Formato inesperado: {created}"
            assert len(created) == 19  # "YYYY-MM-DD 00:00:00"

    def test_no_hay_observacion_fabricada(self, oc_payloads):
        """Ninguna observación debería contener el texto 'Migrado RAFAM OC'."""
        _, all_ocs = oc_payloads
        for oc in all_ocs:
            obs = oc["Pedido"].get("observacion", "")
            assert "Migrado RAFAM" not in obs, f"Observación fabricada en {oc['external_id']}"

    def test_items_no_envian_descripcion(self, oc_payloads):
        _, all_ocs = oc_payloads
        for oc in all_ocs:
            for item in oc.get("items", []):
                assert "descripcion" not in item, f"Item con descripcion en {oc['external_id']}"
                assert "observacion" not in item, f"Item con observacion en {oc['external_id']}"

    def test_items_envian_name(self, oc_payloads):
        """Los items envían `name` para que Paxapos nombre la mercadería."""
        _, all_ocs = oc_payloads
        items_con_name = 0
        total_items = 0
        for oc in all_ocs:
            for item in oc.get("items", []):
                total_items += 1
                if "name" in item:
                    items_con_name += 1
                    assert len(item["name"]) > 0
        # Prácticamente todos los items RAFAM tienen DESCRIPCION
        assert items_con_name > total_items * 0.95

    def test_centro_costo_id_presente(self, oc_payloads):
        """Las OCs con jurisdicción deben tener centro_costo_id."""
        _, all_ocs = oc_payloads
        con_cc = [oc for oc in all_ocs if "centro_costo_id" in oc]
        # La mayoría debería tenerlo (solo 29 items de 5176 no tienen jurisdicción)
        assert len(con_cc) > len(all_ocs) * 0.9
        for oc in con_cc:
            assert isinstance(oc["centro_costo_id"], int)
            assert oc["centro_costo_id"] >= 1

    def test_items_tienen_campos_requeridos(self, oc_payloads):
        _, all_ocs = oc_payloads
        for oc in all_ocs:
            assert len(oc["items"]) > 0, f"OC {oc['external_id']} sin items"
            for item in oc["items"]:
                assert "mercaderia_external_ref" in item
                assert "cantidad" in item
                assert "unidad_de_medida_id" in item
                assert item["mercaderia_external_ref"]["entity"] == "oc_items"
                assert item["mercaderia_external_ref"]["source"] == "rafam"

    def test_external_id_completo(self, oc_payloads):
        _, all_ocs = oc_payloads
        for oc in all_ocs:
            ext = oc["external_id"]
            assert "ejercicio" in ext
            assert "uni_compra" in ext
            assert "nro_oc" in ext
            assert all(isinstance(v, int) for v in ext.values())

    def test_payload_structure(self, oc_payloads):
        """Cada payload tiene la estructura correcta para Paxapos."""
        sent, _ = oc_payloads
        for p in sent:
            assert p["dry_run"] is True
            assert p["options"]["upsert"] is True
            assert p["options"]["send_oc_mail"] is False
            assert "ordenes_compra" in p
            assert isinstance(p["ordenes_compra"], list)
