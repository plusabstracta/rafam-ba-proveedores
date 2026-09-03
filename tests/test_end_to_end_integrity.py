from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Column, MetaData, Table, create_engine, text, Integer, String

from scripts.check_integrity import (
    check_anulaciones,
    check_content_hash_proveedores,
    propagate_orden_compra_soft_delete,
)
from src.entity_link_store import EntityLinkStore
from src.source_repository import SourceRepository


@pytest.fixture
def mock_db_and_repo():
    """Genera una base de datos origen RAFAM (SQLite) y un SourceRepository."""
    engine = create_engine("sqlite:///:memory:", future=True)
    metadata = MetaData()

    # Tabla PROVEEDORES
    Table(
        "PROVEEDORES",
        metadata,
        Column("COD_PROV", Integer),
        Column("CUIT", String),
        Column("RAZON_SOCIAL", String),
        Column("COD_ESTADO", String),
        Column("FANTASIA", String),
        Column("COD_IVA", String),
        # Columnas mínimas requeridas por el hash
        Column("CALLE_LEGAL", String),
        Column("NRO_LEGAL", String),
        Column("LOCA_LEGAL", String),
        Column("PROV_LEGAL", String),
        Column("COD_LEGAL", String),
        Column("CALLE_POSTAL", String),
        Column("NRO_POSTAL", String),
        Column("LOCA_POSTAL", String),
        Column("PROV_POSTAL", String),
        Column("COD_POSTAL", String),
        Column("EMAIL", String),
        Column("NRO_PAIS_TE1", String),
        Column("NRO_INTE_TE1", String),
        Column("NRO_TELE_TE1", String),
        Column("TE_CELULAR", String),
    )

    # Tabla ORDEN_COMPRA
    Table(
        "ORDEN_COMPRA",
        metadata,
        Column("EJERCICIO", Integer),
        Column("UNI_COMPRA", Integer),
        Column("NRO_OC", Integer),
        Column("ESTADO_OC", String),
        Column("FECH_ANUL", String),
    )

    metadata.create_all(engine)
    conn = engine.connect()

    # Cargar fixtures
    conn.execute(
        text(
            "INSERT INTO PROVEEDORES (COD_PROV, CUIT, RAZON_SOCIAL, COD_ESTADO) "
            "VALUES (85, '30-70783071-5', 'SORBA S.R.L.', '0')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO ORDEN_COMPRA (EJERCICIO, UNI_COMPRA, NRO_OC, ESTADO_OC, FECH_ANUL) "
            "VALUES (2026, 1, 10, 'R', NULL)"
        )
    )
    conn.commit()

    repo = SourceRepository(conn)
    yield conn, repo

    conn.close()


@pytest.fixture
def mock_link_store(tmp_path):
    """Genera un link store EntityLinkStore temporal."""
    db_path = tmp_path / "links.db"
    store = EntityLinkStore(db_path=str(db_path))
    yield store
    store.close()


# ── Tests de Integridad ──

class TestIntegrityEndToEnd:
    def test_check_anulaciones_detecta_cambio_y_aplica(self, mock_db_and_repo, mock_link_store):
        conn, repo = mock_db_and_repo

        # Guardar link inicial
        source_key = '{"ejercicio": 2026, "nro_oc": 10, "uni_compra": 1}'
        mock_link_store.save_link("orden_compra", source_key, "remote-oc-10")

        # 1. Ejecutar dry-run inicial: sin cambios
        res = check_anulaciones("orden_compra", mock_link_store, repo, apply=False)
        assert res.verificados == 1
        assert res.sin_cambios == 1
        assert res.anulados == 0
        assert mock_link_store.get_link("orden_compra", source_key).get("deleted_at") is None

        # 2. Simular anulación en la base de origen
        conn.execute(
            text(
                "UPDATE ORDEN_COMPRA SET ESTADO_OC = 'A', FECH_ANUL = '2026-06-29 00:00:00' "
                "WHERE EJERCICIO = 2026 AND NRO_OC = 10 AND UNI_COMPRA = 1"
            )
        )
        conn.commit()

        # 3. Correr dry-run: debe reportar anulación sin persistirla
        res = check_anulaciones("orden_compra", mock_link_store, repo, apply=False)
        assert res.verificados == 1
        assert res.sin_cambios == 0
        assert res.anulados == 1
        assert mock_link_store.get_link("orden_compra", source_key).get("deleted_at") is None

        # 4. Correr apply: debe persistir deleted_at
        res = check_anulaciones("orden_compra", mock_link_store, repo, apply=True)
        assert res.verificados == 1
        assert res.anulados == 1
        link = mock_link_store.get_link("orden_compra", source_key)
        assert link.get("deleted_at") is not None

        # 5. Volver a correr: el link ahora está marcado como eliminado, se ignora
        res = check_anulaciones("orden_compra", mock_link_store, repo, apply=True)
        assert res.verificados == 0

    def test_check_anulaciones_propaga_baja_antes_de_marcar_link(self, mock_db_and_repo, mock_link_store):
        conn, repo = mock_db_and_repo
        source_key = '{"ejercicio": 2026, "nro_oc": 10, "uni_compra": 1}'
        mock_link_store.save_link("orden_compra", source_key, "880")
        conn.execute(
            text(
                "UPDATE ORDEN_COMPRA SET ESTADO_OC = 'A' "
                "WHERE EJERCICIO = 2026 AND NRO_OC = 10 AND UNI_COMPRA = 1"
            )
        )
        conn.commit()

        propagated = []
        result = check_anulaciones(
            "orden_compra",
            mock_link_store,
            repo,
            apply=True,
            propagate_delete_fn=lambda key, remote_id: propagated.append((key, remote_id)),
        )

        assert result.errores == 0
        assert propagated == [(source_key, "880")]
        assert mock_link_store.get_link("orden_compra", source_key).get("deleted_at") is not None

    def test_check_integrity_propaga_eliminacion_fisica_de_oc(self, mock_db_and_repo, mock_link_store):
        conn, repo = mock_db_and_repo
        source_key = '{"ejercicio": 2026, "nro_oc": 10, "uni_compra": 1}'
        mock_link_store.save_link("orden_compra", source_key, "880")
        conn.execute(
            text(
                "DELETE FROM ORDEN_COMPRA "
                "WHERE EJERCICIO = 2026 AND NRO_OC = 10 AND UNI_COMPRA = 1"
            )
        )
        conn.commit()

        propagated = []
        result = check_anulaciones(
            "orden_compra",
            mock_link_store,
            repo,
            apply=True,
            propagate_delete_fn=lambda key, remote_id: propagated.append((key, remote_id)),
        )

        assert result.fisicamente_eliminados == 1
        assert result.errores == 0
        assert propagated == [(source_key, "880")]
        assert mock_link_store.get_link("orden_compra", source_key).get("deleted_at") is not None

    def test_propagate_orden_compra_soft_delete_envia_id_y_sin_items(self):
        exporter = MagicMock()
        exporter._import_url = "https://example.test/tenant/rafam/migracion/importar.json"
        exporter._post_json.return_value = {
            "results": {
                "ordenes_compra": [{
                    "success": True,
                    "id": 880,
                    "mode": "soft_delete",
                }],
            },
        }

        source_key = '{"ejercicio": 2026, "nro_oc": 10, "uni_compra": 1}'
        propagate_orden_compra_soft_delete(exporter, source_key, "880")

        _, payload = exporter._post_json.call_args[0]
        row = payload["ordenes_compra"][0]
        assert row["external_id"] == {"ejercicio": 2026, "nro_oc": 10, "uni_compra": 1}
        assert row["Pedido"] == {"id": 880, "deleted": True}
        assert row["items"] == []
        exporter._raise_on_migrator_errors.assert_called_once()

    def test_check_content_hash_proveedores_detecta_y_reenvia(self, mock_db_and_repo, mock_link_store):
        conn, repo = mock_db_and_repo

        # Guardar link inicial con un hash inicial (distinto al actual)
        source_key = "85"
        mock_link_store.save_link(
            "proveedores",
            source_key,
            "remote-prov-85",
            content_hash="oldhash123",
        )

        mock_exporter = MagicMock()

        # 1. Correr en dry-run
        res = check_content_hash_proveedores(
            mock_link_store, repo, apply=False, exporter=mock_exporter
        )
        assert res.verificados == 1
        assert res.actualizados == 1  # detectado como pendiente de actualizar
        assert res.sin_cambios == 0
        mock_exporter.write_batch.assert_not_called()

        # 2. Correr en apply: debe llamar a write_batch del exporter para reenviar
        res = check_content_hash_proveedores(
            mock_link_store, repo, apply=True, exporter=mock_exporter
        )
        assert res.verificados == 1
        assert res.actualizados == 1
        assert mock_exporter.write_batch.call_count == 1

        from src.mappers.proveedores import compute_content_hash
        row = repo.fetch_proveedor_row(85)
        new_hash = compute_content_hash(row)
        assert mock_link_store.get_link("proveedores", source_key)["content_hash"] == new_hash

        # 3. Correr de nuevo: ahora el hash coincide, reporta sin cambios
        res = check_content_hash_proveedores(
            mock_link_store, repo, apply=True, exporter=mock_exporter
        )
        assert res.verificados == 1
        assert res.sin_cambios == 1
        assert res.actualizados == 0
