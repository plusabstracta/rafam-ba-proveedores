SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

PY := .venv/bin/python
PIP := $(PY) -m pip
PYTEST := $(PY) -m pytest
COVERAGE := $(PY) -m coverage

CSV_DIR ?= output
DEV_DB ?= state/dev_rafam.db
BATCH ?= 500
LIMIT ?=

.PHONY: help setup install env load-dev update-mapping update-mapping-oracle explore-schema dump-full-schema \
	explore-clasificaciones \
	extract-cat-uni-med rafam-context status migrator-spec migrator-lookups \
	migrate-proveedores migrate-proveedores-dry \
	migrate-oc migrate-oc-dry \
	migrate-facturas migrate-facturas-dry \
	migrate-op migrate-op-dry \
	migrate-retenciones migrate-retenciones-dry \
	migrate-all migrate-all-dry \
	sync-proveedores sync-oc sync-all \
	reset-all reset-proveedores reset-oc_items reset-solic_gastos reset-orden_pago reset-retenciones \
	check-integrity-dry check-integrity install-cron show-cron uninstall-cron \
	backfill-gastos backfill-gastos-dry \
	test coverage

help:
	@echo "RAFAM BA Proveedores - comandos rapidos"
	@echo ""
	@echo "  make setup              Crea .venv, instala deps y genera .env si no existe"
	@echo "  make load-dev           Carga snapshot CSV a SQLite local (solo DEV)"
	@echo "  make update-mapping     Regenera docs/field_mapping.md desde la DB (SQLite o Oracle)"
	@echo "  make explore-schema     Genera docs/rafam_schema_and_joins.md desde Oracle"
	@echo "  make dump-full-schema   Genera output/rafam_context/full_schema.{md,json} de toda la DB"
	@echo "  make explore-clasificaciones  Detecta tablas de clasificaciones/partidas (inciso/par_prin/par_parc)"
	@echo "  make extract-cat-uni-med  Extrae CAT_UNI_MED de Oracle a docs/cat_uni_med.md"
	@echo "  make rafam-context      Genera output/rafam_context/*.md con contexto RAFAM medido"
	@echo "  make status             Muestra estado de checkpoints"
	@echo "  make migrator-spec      Consulta spec.json del migrator RAFAM"
	@echo "  make migrator-lookups   Consulta lookups.json del migrator RAFAM"
	@echo ""
	@echo "  --- Migracion RAFAM -> Paxapos (5 migradores, en orden de FKs) ---"
	@echo "  make migrate-proveedores       1. Migra PROVEEDORES"
	@echo "  make migrate-oc                2. Migra ORDEN_COMPRA + OC_ITEMS"
	@echo "  make migrate-facturas          3. Migra FACTURAS/GASTOS (SOLIC_GASTOS)"
	@echo "  make migrate-op                4. Migra ORDENES DE PAGO (auto-crea gastos si faltan)"
	@echo "  make migrate-retenciones       5. Migra RETENCIONES (ORDEN_PAGO_DEDUC)"
	@echo "  make migrate-all               Pipeline completo (los 5 en orden)"
	@echo "  make migrate-<x>-dry           Cualquiera de los anteriores en dry-run (preview, no escribe)"
	@echo ""
	@echo "  make reset-proveedores  Resetea checkpoint de proveedores"
	@echo "  make reset-oc_items     Resetea checkpoint de oc_items"
	@echo "  make reset-solic_gastos Resetea checkpoint de solic_gastos (facturas)"
	@echo "  make reset-orden_pago   Resetea checkpoint de orden_pago"
	@echo "  make reset-retenciones  Resetea checkpoint de retenciones"
	@echo "  make reset-all          Resetea todos los checkpoints"
	@echo "  make check-integrity-dry  Ejecuta verificador de integridad en modo lectura (dry-run)"
	@echo "  make check-integrity      Aplica correcciones de integridad (anulaciones + reenvio de proveedores)"
	@echo "  make backfill-gastos      Recupera links faltantes de gastos ya migrados (escaneo completo, no toca checkpoint)"
	@echo "  make backfill-gastos-dry  Preview del backfill (no persiste, solo muestra cuantos gastos se reenviarian)"
	@echo "  make install-cron         Instala/actualiza los cron jobs basados en cron.conf con flock"
	@echo "  make show-cron            Muestra los cron jobs activos de este proyecto"
	@echo "  make uninstall-cron       Elimina todos los cron jobs de este proyecto en el crontab"
	@echo "  make test               Corre tests"
	@echo "  make coverage           Corre tests y exige 80%+ de cobertura en src/"
	@echo ""
	@echo "Variables opcionales:"
	@echo "  BATCH=500 LIMIT=1000 DEV_DB=state/dev_rafam.db RAFAM_CONTEXT_ARGS='--years 1' RAFAM_SCHEMA_ARGS='--row-counts'"

setup:
	python -m venv .venv
	$(PIP) install -r requirements.txt
	@if [[ ! -f .env ]]; then cp .env.example .env; echo "Archivo .env creado desde .env.example"; else echo ".env ya existe"; fi

install:
	$(PIP) install -r requirements.txt

env:
	@if [[ ! -f .env ]]; then cp .env.example .env; echo "Archivo .env creado desde .env.example"; else echo ".env ya existe"; fi

load-dev:
	$(PY) scripts/load_csv_to_sqlite.py --csv-dir $(CSV_DIR) --output-db $(DEV_DB)

update-mapping:
	SQLITE_DB_PATH=$(DEV_DB) DB_BACKEND=sqlite $(PY) scripts/update_field_mapping.py

update-mapping-oracle:
	DB_BACKEND=oracle $(PY) scripts/update_field_mapping.py

explore-schema:
	$(PY) scripts/explore_schema.py

dump-full-schema:
	$(PY) scripts/dump_full_schema.py $(RAFAM_SCHEMA_ARGS)

explore-clasificaciones:
	$(PY) scripts/explore_clasificaciones.py $(RAFAM_CLASIF_ARGS)

extract-cat-uni-med:
	$(PY) scripts/extract_cat_uni_med.py

rafam-context:
	$(PY) scripts/generate_rafam_context.py $(RAFAM_CONTEXT_ARGS)

status:
	$(PY) main.py status

migrator-spec:
	$(PY) main.py spec --target migrator

migrator-lookups:
	$(PY) main.py lookups

# ───────────────────────────────────────────────────────────────────────────
# Migracion RAFAM -> Paxapos (5 migradores independientes)
#
# Cada target migra exactamente UN dominio del flujo RAFAM -> Paxapos via
# POST /:tenant/rafam/migracion/importar.json (RafamMigracionesController).
# El destino siempre es el migrator (no hay otros exporters). Agregar -dry a
# cualquier target para previsualizar sin escribir en Paxapos (--dry-run).
# Orden de FKs: proveedores -> oc -> facturas -> op -> retenciones.
# Ver docs/rafam_paxapos_equivalencias.md para el detalle de mapeos.
# ───────────────────────────────────────────────────────────────────────────

# 1. PROVEEDORES (PROVEEDORES -> account_proveedores)
migrate-proveedores:
	$(PY) main.py run --entity proveedores --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),)

migrate-proveedores-dry:
	$(PY) main.py run --entity proveedores --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --dry-run

# 2. ORDENES DE COMPRA (ORDEN_COMPRA + OC_ITEMS -> compras_pedidos + items)
#    El exporter despacha por --entity oc_items y arma el payload ordenes_compra[]
#    con items embebidos (un POST por OC). Sin pagos ni gastos.
migrate-oc:
	$(PY) main.py run --entity oc_items --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),)

migrate-oc-dry:
	$(PY) main.py run --entity oc_items --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --dry-run

# 3. FACTURAS / GASTOS (SOLIC_GASTOS + CTA_COMPROB -> account_gastos)
#    Migra comprobantes de proveedores (facturas recibidas) como gastos en Paxapos.
#    Requiere que los proveedores y OCs ya estén migrados (usa links para resolver FKs).
migrate-facturas:
	$(PY) main.py run --entity solic_gastos --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),)

migrate-facturas-dry:
	$(PY) main.py run --entity solic_gastos --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --dry-run

# 4. ORDENES DE PAGO (ORDEN_PAGO -> account_egresos)
#    Envia gasto_nro_comprobante (PDV-NRO_COMPROB) por OP. Si Paxapos no encuentra
#    el gasto, lo auto-crea desde los datos de CTA_COMPROB embebidos en gastos[].
migrate-op:
	$(PY) main.py run --entity orden_pago --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),)

migrate-op-dry:
	$(PY) main.py run --entity orden_pago --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --dry-run

# 5. RETENCIONES (ORDEN_PAGO_DEDUC -> retenciones vinculadas a OPs)
#    Escanea las mismas OPs confirmadas y trae deducciones de ORDEN_PAGO_DEDUC.
#    Requiere que las OPs ya estén migradas (usa link de orden_pago para vincular).
migrate-retenciones:
	$(PY) main.py run --entity retenciones --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),)

migrate-retenciones-dry:
	$(PY) main.py run --entity retenciones --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --dry-run

# Detección de cambios (Updates por Hash)
sync-proveedores:
	$(PY) main.py sync-changes --entity proveedores $(if $(BACKFILL),--backfill-only,) $(if $(DRY),--dry-run,)

sync-oc:
	$(PY) main.py sync-changes --entity oc_items $(if $(BACKFILL),--backfill-only,) $(if $(DRY),--dry-run,)

sync-all: sync-proveedores sync-oc

# Pipeline completo: respeta orden de FKs (proveedores -> OC -> facturas -> OP -> retenciones)
migrate-all: migrate-proveedores migrate-oc migrate-facturas migrate-op migrate-retenciones

migrate-all-dry: migrate-proveedores-dry migrate-oc-dry migrate-facturas-dry migrate-op-dry migrate-retenciones-dry

reset-all:
	$(PY) main.py reset --all

reset-proveedores:
	$(PY) main.py reset --entity proveedores

reset-oc_items:
	$(PY) main.py reset --entity oc_items

reset-solic_gastos:
	$(PY) main.py reset --entity solic_gastos

reset-orden_pago:
	$(PY) main.py reset --entity orden_pago

reset-retenciones:
	$(PY) main.py reset --entity retenciones

test:
	$(PYTEST) -q

coverage:
	$(COVERAGE) run --source=src -m pytest -q
	$(COVERAGE) report --fail-under=80 -m

# ─── Integridad y Cron ────────────────────────────────────────────────────────

check-integrity-dry:
	$(PY) scripts/check_integrity.py --dry-run

check-integrity:
	$(PY) scripts/check_integrity.py --apply

# Backfill unico: recupera links locales faltantes de gastos ya migrados.
# Fuerza un escaneo COMPLETO de solic_gastos (ignora la ventana de 30 dias) sin
# tocar el checkpoint incremental; solo reenvia gastos aun sin link (Solucion B).
backfill-gastos:
	$(PY) main.py backfill-gastos --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),)

backfill-gastos-dry:
	$(PY) main.py backfill-gastos --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --dry-run

install-cron:
	bash scripts/install_crons.sh

show-cron:
	@crontab -l 2>/dev/null | grep "$(shell pwd)" || echo "Sin cron jobs instalados para este proyecto."

uninstall-cron:
	@( crontab -l 2>/dev/null | grep -v "$(shell pwd)" ) | crontab - && echo "Cron jobs de este proyecto eliminados."

