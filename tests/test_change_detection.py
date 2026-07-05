import json
from unittest.mock import MagicMock, patch

import pytest

from src.change_detection import compute_payload_hash
from src.change_sync import ChangeSyncService
from src.entity_link_store import EntityLinkStore
from src.exporter import MigratorExporter
from src.gateway_mapper import map_proveedor_migrator_row


def _sync_entity_changes(*, source_repo, exporter, link_store, entity, backfill_only, dry_run):
    """Wrapper de compatibilidad: delega en ChangeSyncService (dominio real)."""
    service = ChangeSyncService(source_repo, exporter, link_store)
    return service.sync_entity(entity, backfill_only=backfill_only, dry_run=dry_run)


def test_compute_payload_hash_normalization():
    # Test that key ordering does not affect the hash
    payload1 = {"a": 1, "b": 2, "c": [1, 2, 3]}
    payload2 = {"c": [1, 2, 3], "b": 2, "a": 1}
    assert compute_payload_hash(payload1) == compute_payload_hash(payload2)

    # Test distinct payloads yield distinct hashes
    payload3 = {"a": 1, "b": 2, "c": [1, 2, 4]}
    assert compute_payload_hash(payload1) != compute_payload_hash(payload3)


class TestSyncEntityChangesProveedores:

    @pytest.fixture
    def setup_env(self):
        # Setup an in-memory Link Store
        link_store = EntityLinkStore(db_path=":memory:")
        
        # Setup a mock Source Repository
        source_repo = MagicMock()
        
        # Setup a mock Exporter
        exporter = MagicMock(spec=MigratorExporter)
        exporter.dry_run = False
        
        return source_repo, exporter, link_store

    def test_sync_no_links(self, setup_env):
        source_repo, exporter, link_store = setup_env
        # Should immediately return True since there are no local links
        res = _sync_entity_changes(
            source_repo=source_repo,
            exporter=exporter,
            link_store=link_store,
            entity="proveedores",
            backfill_only=False,
            dry_run=False
        )
        assert res is True
        source_repo.fetch_proveedores_by_keys.assert_not_called()
        exporter.write_batch.assert_not_called()

    def test_sync_unchanged_proveedores(self, setup_env):
        source_repo, exporter, link_store = setup_env
        
        # Row from RAFAM
        columns = ["COD_PROV", "FANTASIA", "RAZON_SOCIAL", "CUIT", "COD_IVA"]
        row = ("100", "Proveedor A", "Proveedor A SA", "30-12345678-9", "RINS")
        
        # Dynamically compute expected hash to match exactly what mapper returns
        raw = dict(zip(columns, row))
        mapped = map_proveedor_migrator_row(raw)
        stored_hash = compute_payload_hash(mapped.get("Proveedor", {}))
        
        link_store.save_link(
            entity="proveedores",
            source_key="100",
            remote_id="500",
            cuit="30-12345678-9",
            cod_estado="A",
            payload_hash=stored_hash
        )

        source_repo.fetch_proveedores_by_keys.return_value = (columns, [row])

        res = _sync_entity_changes(
            source_repo=source_repo,
            exporter=exporter,
            link_store=link_store,
            entity="proveedores",
            backfill_only=False,
            dry_run=False
        )
        
        assert res is True
        source_repo.fetch_proveedores_by_keys.assert_called_once_with([100])
        exporter.write_batch.assert_not_called()

    def test_sync_changed_proveedores(self, setup_env):
        source_repo, exporter, link_store = setup_env
        
        # Save a link in the store with an old hash
        link_store.save_link(
            entity="proveedores",
            source_key="100",
            remote_id="500",
            cuit="30-12345678-9",
            cod_estado="A",
            payload_hash="old_outdated_hash"
        )

        # Source repo returns updated values
        columns = ["COD_PROV", "FANTASIA", "RAZON_SOCIAL", "CUIT", "COD_IVA"]
        rows = [("100", "Proveedor A New Name", "Proveedor A SA", "30-12345678-9", "RINS")]
        source_repo.fetch_proveedores_by_keys.return_value = (columns, rows)

        res = _sync_entity_changes(
            source_repo=source_repo,
            exporter=exporter,
            link_store=link_store,
            entity="proveedores",
            backfill_only=False,
            dry_run=False
        )
        
        assert res is True
        source_repo.fetch_proveedores_by_keys.assert_called_once_with([100])
        exporter.write_batch.assert_called_once_with("proveedores", columns, [rows[0]])

    def test_sync_proveedores_backfill_only(self, setup_env):
        source_repo, exporter, link_store = setup_env
        
        # Link exists without hash
        link_store.save_link(
            entity="proveedores",
            source_key="100",
            remote_id="500",
            cuit="30-12345678-9",
            cod_estado="A",
            payload_hash=None
        )

        # Source repo returns current values
        columns = ["COD_PROV", "FANTASIA", "RAZON_SOCIAL", "CUIT", "COD_IVA"]
        rows = [("100", "Proveedor A", "Proveedor A SA", "30-12345678-9", "RINS")]
        source_repo.fetch_proveedores_by_keys.return_value = (columns, rows)

        res = _sync_entity_changes(
            source_repo=source_repo,
            exporter=exporter,
            link_store=link_store,
            entity="proveedores",
            backfill_only=True,
            dry_run=False
        )
        
        assert res is True
        exporter.write_batch.assert_not_called()
        
        # Check that the hash was backfilled in the db
        link = link_store.get_link("proveedores", "100")
        assert link["payload_hash"] is not None
        
        raw = dict(zip(columns, rows[0]))
        mapped = map_proveedor_migrator_row(raw)
        expected_hash = compute_payload_hash(mapped.get("Proveedor", {}))
        assert link["payload_hash"] == expected_hash

    def test_sync_proveedores_dry_run(self, setup_env):
        source_repo, exporter, link_store = setup_env
        
        link_store.save_link(
            entity="proveedores",
            source_key="100",
            remote_id="500",
            cuit="30-12345678-9",
            cod_estado="A",
            payload_hash=None
        )

        columns = ["COD_PROV", "FANTASIA", "RAZON_SOCIAL", "CUIT", "COD_IVA"]
        rows = [("100", "Proveedor A", "Proveedor A SA", "30-12345678-9", "RINS")]
        source_repo.fetch_proveedores_by_keys.return_value = (columns, rows)

        res = _sync_entity_changes(
            source_repo=source_repo,
            exporter=exporter,
            link_store=link_store,
            entity="proveedores",
            backfill_only=False,
            dry_run=True
        )
        
        assert res is True
        exporter.write_batch.assert_not_called()
        
        # Links should still have None hash because of dry_run
        link = link_store.get_link("proveedores", "100")
        assert link["payload_hash"] is None


class TestSyncEntityChangesOcItems:

    OC_COLUMNS = [
        "EJERCICIO", "UNI_COMPRA", "NRO_OC", "ITEM_OC",
        "DELEG_SOLIC", "NRO_SOLIC", "ITEM_REAL",
        "DESCRIPCION", "CANTIDAD", "IMP_UNITARIO", "CANT_RECIB", "IMPORTE_EJER",
        "COD_PROV",
        "OC_FECH_OC", "OC_OBSERVACIONES", "OC_ESTADO_OC", "OC_FECH_CONFIRM",
        "OC_IMPORTE_TOT", "SG_JURISDICCION",
    ]

    def _oc_row(
        self,
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
        return tuple(vals.get(c, "") for c in self.OC_COLUMNS)

    @pytest.fixture
    def setup_env(self):
        link_store = EntityLinkStore(db_path=":memory:")
        
        # Save provider link so grouping doesn't skip the OC
        link_store.save_link("proveedores", "99", remote_id="777")
        
        source_repo = MagicMock()
        
        # Setup Exporter with mock lookups so _group_oc_rows runs fine
        with patch("src.exporter.fetch_migrator_lookups") as mock_lookups:
            mock_lookups.return_value = {
                "unidades_de_medida": [{"id": "1", "name": "Unidad"}],
                "tipos_factura": [],
                "tipos_de_pago": [],
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
                exporter = MigratorExporter(dry_run=True)
                
        # Link the exporter's link store to the shared memory link store
        exporter._link_store = link_store
        # El mapper de OC guarda su propia referencia al link_store (creada en
        # __init__); propagar la compartida para que group_rows resuelva el
        # proveedor y no descarte la OC.
        exporter._oc_mapper._link_store = link_store

        return source_repo, exporter, link_store

    def test_sync_oc_items_changed(self, setup_env):
        source_repo, exporter, link_store = setup_env
        
        # Save OC link in local store
        oc_key = json.dumps(
            {"ejercicio": 2026, "nro_oc": 100, "uni_compra": 1},
            sort_keys=True,
        )
        link_store.save_link(
            entity="orden_compra",
            source_key=oc_key,
            remote_id="999",
            estado_oc="R",
            fech_confirm="2026-03-16 00:00:00",
            cod_prov="99",
            importe_tot="500.00",
            gasto_refs="",
            payload_hash="old_wrong_hash"
        )
        
        # Source repo returns updated row
        row = self._oc_row(cantidad="12", imp_unitario="50.0", importe_tot="600.00") # Changed qty and total
        source_repo.fetch_oc_items_by_keys.return_value = (self.OC_COLUMNS, [row])
        
        # Exporter mock setup to intercept write_batch call
        exporter.write_batch = MagicMock()
        
        res = _sync_entity_changes(
            source_repo=source_repo,
            exporter=exporter,
            link_store=link_store,
            entity="oc_items",
            backfill_only=False,
            dry_run=False
        )
        
        assert res is True
        source_repo.fetch_oc_items_by_keys.assert_called_once()
        args, kwargs = source_repo.fetch_oc_items_by_keys.call_args
        assert args[0] == [{"ejercicio": 2026, "nro_oc": 100, "uni_compra": 1}]
        assert "ejercicio_min" in kwargs
        exporter.write_batch.assert_called_once()
        args, kwargs = exporter.write_batch.call_args
        assert args[0] == "oc_items"
        assert len(args[2]) == 1 # 1 row sent
        
    def test_sync_oc_items_unchanged(self, setup_env):
        source_repo, exporter, link_store = setup_env
        
        # First compute the expected hash for the OC payload
        row = self._oc_row()
        grouped, _, _, _ = exporter._oc_mapper.group_rows(self.OC_COLUMNS, [row])
        expected_hash = compute_payload_hash(grouped[(2026, 1, 100)])
        
        oc_key = json.dumps(
            {"ejercicio": 2026, "nro_oc": 100, "uni_compra": 1},
            sort_keys=True,
        )
        link_store.save_link(
            entity="orden_compra",
            source_key=oc_key,
            remote_id="999",
            estado_oc="R",
            fech_confirm="2026-03-16 00:00:00",
            cod_prov="99",
            importe_tot="500.00",
            gasto_refs="",
            payload_hash=expected_hash
        )
        
        source_repo.fetch_oc_items_by_keys.return_value = (self.OC_COLUMNS, [row])
        exporter.write_batch = MagicMock()
        
        res = _sync_entity_changes(
            source_repo=source_repo,
            exporter=exporter,
            link_store=link_store,
            entity="oc_items",
            backfill_only=False,
            dry_run=False
        )
        
        assert res is True
        exporter.write_batch.assert_not_called()
