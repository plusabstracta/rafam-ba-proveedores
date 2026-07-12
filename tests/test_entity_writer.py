from src.entity_writer import EntityWriter
from src.exporter import MigratorExporter


class FakeMapper:
    def build_payload(self, columns, rows, *, dry_run, payload_options):
        return {"proveedores": [{"id": 1}, {"id": 2}]}, {"ctx": True}

    def log_stats(self, parsed, dry_run):
        return None


def test_entity_writer_captures_last_migrator_counts():
    persisted = []

    def persist_fn(parsed, context, link_store, dry_run):
        persisted.append((parsed, context, link_store, dry_run))

    writer = EntityWriter("proveedores", FakeMapper(), persist_fn, result_section="proveedores")

    parsed = writer.write_batch(
        [],
        [],
        dry_run=False,
        payload_options={},
        import_url="http://paxapos.test/rafam/migracion/importar.json",
        post_fn=lambda _url, _payload: {"stats": {"proveedores": {"ok": 1, "error": 1}}},
        link_store="store",
        raise_on_errors_fn=lambda _parsed: None,
    )

    assert parsed == {"stats": {"proveedores": {"ok": 1, "error": 1}}}
    assert writer.last_payload_count == 2
    assert writer.last_saved_count == 1
    assert writer.last_error_count == 1
    assert persisted


class FailingWriter:
    result_section = "proveedores"
    last_payload_count = 2
    last_saved_count = 0
    last_error_count = 2

    def write_batch(self, *args, **kwargs):
        raise RuntimeError("migrator rechazo el batch")


def test_migrator_exporter_keeps_last_batch_metrics_when_writer_raises():
    exporter = MigratorExporter.__new__(MigratorExporter)
    exporter._writers = {"proveedores": FailingWriter()}
    exporter._dry_run = False
    exporter._import_url = "http://paxapos.test/rafam/migracion/importar.json"
    exporter._link_store = object()
    exporter._last_batch_migrator_metrics = {"sent": 0, "saved": 0, "errors": 0}

    try:
        exporter._write_batch_proveedores([], [])
    except RuntimeError:
        pass

    assert exporter.get_last_batch_migrator_metrics() == {"sent": 2, "saved": 0, "errors": 2}