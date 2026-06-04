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
EXPORT ?= csv

.PHONY: help setup install env load-dev update-mapping explore-schema extract-cat-uni-med rafam-context status run-all test coverage reset-all \
	run-proveedores run-solic_gastos \
	run-orden_compra run-oc_items run-orden_pago \
	run-proveedores-migrator run-proveedores-migrator-dry \
	run-oc_items-migrator run-oc_items-migrator-dry \
	run-orden_pago-migrator run-orden_pago-migrator-dry \
	migrate-proveedores migrate-proveedores-dry \
	migrate-oc migrate-oc-dry \
	migrate-facturas migrate-facturas-dry \
	migrate-op migrate-op-dry \
	migrate-retenciones migrate-retenciones-dry \
	migrate-all migrate-all-dry \
	migrator-spec migrator-lookups \
	reset-proveedores reset-solic_gastos \
	reset-orden_compra reset-oc_items reset-orden_pago

help:
	@echo "RAFAM BA Proveedores - comandos rapidos"
	@echo ""
	@echo "  make setup              Crea .venv, instala deps y genera .env si no existe"
	@echo "  make load-dev           Carga CSVs a SQLite local"
	@echo "  make update-mapping     Regenera docs/field_mapping.md desde la DB (SQLite o Oracle)"
	@echo "  make explore-schema     Genera docs/rafam_schema.md desde Oracle"
	@echo "  make extract-cat-uni-med  Extrae CAT_UNI_MED de Oracle a docs/cat_uni_med.md"
	@echo "  make rafam-context      Genera output/rafam_context/*.md con contexto RAFAM medido"
	@echo "  make status             Muestra estado de checkpoints"
	@echo "  make run-all            Ejecuta sync de todas las entidades"
	@echo "  make run-proveedores    Ejecuta sync solo de proveedores"
	@echo "  make run-orden_compra   Ejecuta sync solo de orden_compra"
	@echo "  make run-proveedores-migrator  Envia proveedores al migrator RAFAM"
	@echo "  make run-proveedores-migrator-dry  Prueba migrator con dry_run=true"
	@echo "  make run-oc_items-migrator-dry  Prueba migracion de oc_items -> ordenes_compra"
	@echo "  make run-oc_items-migrator  Migra oc_items -> ordenes_compra"
	@echo "  make run-orden_pago-migrator-dry  Prueba migracion de orden_pago"
	@echo "  make run-orden_pago-migrator  Migra ordenes_pago"
	@echo "  make migrator-spec      Consulta spec.json del migrator RAFAM"
	@echo "  make migrator-lookups   Consulta lookups.json del migrator RAFAM"
	@echo ""
	@echo "  --- Migracion RAFAM -> Paxapos (5 migradores) ---"
	@echo "  make migrate-proveedores       1. Migra PROVEEDORES"
	@echo "  make migrate-oc                2. Migra ORDEN_COMPRA + OC_ITEMS"
	@echo "  make migrate-facturas          3. Migra FACTURAS/GASTOS (SOLIC_GASTOS)"
	@echo "  make migrate-op                4. Migra ORDENES DE PAGO (auto-crea gastos si faltan)"
	@echo "  make migrate-retenciones       5. Migra RETENCIONES (ORDEN_PAGO_DEDUC)"
	@echo "  make migrate-all               Pipeline completo (los 5 en orden)"
	@echo "  make migrate-*-dry             Cualquiera de los anteriores en dry-run"
	@echo "  make reset-proveedores  Resetea checkpoint de proveedores"
	@echo "  make reset-all          Resetea todos los checkpoints"
	@echo "  make test               Corre tests"
	@echo "  make coverage           Corre tests y exige 80%+ de cobertura en src/"
	@echo ""
	@echo "Variables opcionales:"
	@echo "  BATCH=500 LIMIT=1000 EXPORT=csv CSV_DIR=output DEV_DB=state/dev_rafam.db RAFAM_CONTEXT_ARGS='--years 1'"

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

run-all:
	$(PY) main.py run --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export $(EXPORT)

run-proveedores:
	$(PY) main.py run --entity proveedores --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export $(EXPORT)

run-proveedores-migrator:
	$(PY) main.py run --entity proveedores --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

run-proveedores-migrator-dry:
	$(PY) main.py run --entity proveedores --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

run-oc_items-migrator-dry:
	$(PY) main.py run --entity oc_items --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

run-oc_items-migrator:
	$(PY) main.py run --entity oc_items --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

run-orden_pago-migrator-dry:
	$(PY) main.py run --entity orden_pago --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

run-orden_pago-migrator:
	$(PY) main.py run --entity orden_pago --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

# ───────────────────────────────────────────────────────────────────────────
# Migracion RAFAM -> Paxapos (5 migradores independientes)
#
# Cada target migra exactamente UN dominio del flujo RAFAM -> Paxapos via
# POST /:tenant/rafam/migracion/importar.json (RafamMigracionesController).
# Ver docs/rafam_paxapos_equivalencias.md para el detalle de mapeos.
# ───────────────────────────────────────────────────────────────────────────

# 1. PROVEEDORES (PROVEEDORES -> account_proveedores)
migrate-proveedores:
	$(PY) main.py run --entity proveedores --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

migrate-proveedores-dry:
	$(PY) main.py run --entity proveedores --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

# 2. ORDENES DE COMPRA (ORDEN_COMPRA + OC_ITEMS -> compras_pedidos + items)
#    El exporter despacha por --entity oc_items y arma el payload ordenes_compra[]
#    con items embebidos (un POST por OC). Sin pagos ni gastos.
migrate-oc:
	$(PY) main.py run --entity oc_items --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

migrate-oc-dry:
	$(PY) main.py run --entity oc_items --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

# 3. FACTURAS / GASTOS (SOLIC_GASTOS + CTA_COMPROB -> account_gastos)
#    Migra comprobantes de proveedores (facturas recibidas) como gastos en Paxapos.
#    Requiere que los proveedores y OCs ya estén migrados (usa links para resolver FKs).
migrate-facturas:
	$(PY) main.py run --entity solic_gastos --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

migrate-facturas-dry:
	$(PY) main.py run --entity solic_gastos --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

# 4. ORDENES DE PAGO (ORDEN_PAGO -> account_egresos)
#    Envia gasto_nro_comprobante (PDV-NRO_COMPROB) por OP. Si Paxapos no encuentra
#    el gasto, lo auto-crea desde los datos de CTA_COMPROB embebidos en gastos[].
migrate-op:
	$(PY) main.py run --entity orden_pago --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

migrate-op-dry:
	$(PY) main.py run --entity orden_pago --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

# 5. RETENCIONES (ORDEN_PAGO_DEDUC -> retenciones vinculadas a OPs)
#    Escanea las mismas OPs confirmadas y trae deducciones de ORDEN_PAGO_DEDUC.
#    Requiere que las OPs ya estén migradas (usa link de orden_pago para vincular).
migrate-retenciones:
	$(PY) main.py run --entity retenciones --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

migrate-retenciones-dry:
	$(PY) main.py run --entity retenciones --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

# Pipeline completo: respeta orden de FKs (proveedores -> OC -> facturas -> OP -> retenciones)
migrate-all: migrate-proveedores migrate-oc migrate-facturas migrate-op migrate-retenciones

migrate-all-dry: migrate-proveedores-dry migrate-oc-dry migrate-facturas-dry migrate-op-dry migrate-retenciones-dry

run-solic_gastos:
	$(PY) main.py run --entity solic_gastos --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export $(EXPORT)

run-orden_compra:
	$(PY) main.py run --entity orden_compra --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export $(EXPORT)

run-oc_items:
	$(PY) main.py run --entity oc_items --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export $(EXPORT)

run-orden_pago:
	$(PY) main.py run --entity orden_pago --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export $(EXPORT)

reset-all:
	$(PY) main.py reset --all

reset-proveedores:
	$(PY) main.py reset --entity proveedores

reset-solic_gastos:
	$(PY) main.py reset --entity solic_gastos

reset-orden_compra:
	$(PY) main.py reset --entity orden_compra

reset-oc_items:
	$(PY) main.py reset --entity oc_items

reset-orden_pago:
	$(PY) main.py reset --entity orden_pago

test:
	$(PYTEST) -q

coverage:
	$(COVERAGE) run --source=src -m pytest -q
	$(COVERAGE) report --fail-under=80 -m
