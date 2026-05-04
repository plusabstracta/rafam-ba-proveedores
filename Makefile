SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

PY := .venv/bin/python
PIP := $(PY) -m pip
PYTEST := $(PY) -m pytest

CSV_DIR ?= output
DEV_DB ?= state/dev_rafam.db
BATCH ?= 500
LIMIT ?=
EXPORT ?= csv
FORCE_UPDATE ?= 0
MONTHS ?= 3
TABLES ?=
OUT ?= output/rafam_ultimos_3_meses

.PHONY: help setup install env load-dev export-rafam-csv update-mapping explore-schema status run-all test reset-all \
	run-jurisdicciones run-proveedores run-pedidos run-ped_items run-solic_gastos \
	run-orden_compra run-oc_items run-orden_pago \
	run-proveedores-gateway \
	run-jurisdicciones-migrator run-jurisdicciones-migrator-dry \
	run-proveedores-migrator run-proveedores-migrator-dry \
	run-ped_items-migrator run-ped_items-migrator-dry \
	run-oc_items-migrator run-oc_items-migrator-dry \
	run-solic_gastos-migrator run-solic_gastos-migrator-dry \
	run-orden_pago-migrator run-orden_pago-migrator-dry \
	migrator-spec migrator-lookups \
	reset-jurisdicciones reset-proveedores reset-pedidos reset-ped_items reset-solic_gastos \
	reset-orden_compra reset-oc_items reset-orden_pago

help:
	@echo "RAFAM BA Proveedores - comandos rapidos"
	@echo ""
	@echo "  make setup              Crea .venv, instala deps y genera .env si no existe"
	@echo "  make export-rafam-csv   Exporta CSVs desde Oracle RAFAM (no requiere Paxapos)"
	@echo "  make load-dev           Carga CSVs a SQLite local"
	@echo "  make update-mapping     Regenera docs/field_mapping.md desde la DB (SQLite o Oracle)"
	@echo "  make explore-schema     Genera docs/rafam_schema.md desde Oracle"
	@echo "  make status             Muestra estado de checkpoints"
	@echo "  make run-all            Ejecuta sync de todas las entidades"
	@echo "  make run-proveedores    Ejecuta sync solo de proveedores"
	@echo "  make run-orden_compra   Ejecuta sync solo de orden_compra"
	@echo "  make run-proveedores-gateway  Envia proveedores a Paxapos (POST JSON)"
	@echo "  make run-proveedores-gateway-force-update  Fuerza update de vinculados en gateway"
	@echo "  make run-jurisdicciones-migrator-dry  Prueba migrator jurisdicciones (rubros+clasif)"
	@echo "  make run-jurisdicciones-migrator  Migra jurisdicciones -> rubros y clasificaciones"
	@echo "  make run-proveedores-migrator  Envia proveedores al migrator RAFAM"
	@echo "  make run-proveedores-migrator-dry  Prueba migrator con dry_run=true"
	@echo "  make run-ped_items-migrator-dry  Prueba migracion de ped_items -> pedidos"
	@echo "  make run-ped_items-migrator  Migra ped_items -> pedidos"
	@echo "  make run-oc_items-migrator-dry  Prueba migracion de oc_items -> ordenes_compra"
	@echo "  make run-oc_items-migrator  Migra oc_items -> ordenes_compra"
	@echo "  make run-solic_gastos-migrator-dry  Prueba migracion de solic_gastos -> gastos"
	@echo "  make run-solic_gastos-migrator  Migra solic_gastos -> gastos (facturas)"
	@echo "  make run-orden_pago-migrator-dry  Prueba migracion de orden_pago"
	@echo "  make run-orden_pago-migrator  Migra ordenes_pago"
	@echo "  make migrator-spec      Consulta spec.json del migrator RAFAM"
	@echo "  make migrator-lookups   Consulta lookups.json del migrator RAFAM"
	@echo "  make reset-proveedores  Resetea checkpoint de proveedores"
	@echo "  make reset-all          Resetea todos los checkpoints"
	@echo "  make test               Corre tests"
	@echo ""
	@echo "Variables opcionales:"
	@echo "  BATCH=500 LIMIT=1000 EXPORT=csv FORCE_UPDATE=0 CSV_DIR=output DEV_DB=state/dev_rafam.db"
	@echo "  MONTHS=3 TABLES=PROVEEDORES,ORDEN_PAGO OUT=output/rafam_ultimos_3_meses"

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

export-rafam-csv:
	$(PY) scripts/export_last_3_months.py --months $(MONTHS) $(if $(TABLES),--tables $(TABLES),) --output-dir $(OUT)

update-mapping:
	RAFAM_SOURCE_SQLITE_DB_PATH=$(DEV_DB) RAFAM_SOURCE_BACKEND=sqlite $(PY) scripts/update_field_mapping.py

update-mapping-oracle:
	RAFAM_SOURCE_BACKEND=oracle $(PY) scripts/update_field_mapping.py

explore-schema:
	$(PY) scripts/explore_schema.py

status:
	$(PY) main.py status

migrator-spec:
	$(PY) main.py spec --target migrator

migrator-lookups:
	$(PY) main.py lookups

run-all:
	$(PY) main.py run --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export $(EXPORT)

run-jurisdicciones:
	$(PY) main.py run --entity jurisdicciones --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export $(EXPORT)

run-proveedores:
	$(PY) main.py run --entity proveedores --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export $(EXPORT)

run-proveedores-gateway:
	$(PY) main.py run --entity proveedores --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export gateway $(if $(filter 1 true TRUE yes YES on ON,$(FORCE_UPDATE)),--force-update,)

run-proveedores-gateway-force-update:
	$(PY) main.py run --entity proveedores --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export gateway --force-update

run-jurisdicciones-migrator:
	$(PY) main.py run --entity jurisdicciones --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

run-jurisdicciones-migrator-dry:
	$(PY) main.py run --entity jurisdicciones --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

run-proveedores-migrator:
	$(PY) main.py run --entity proveedores --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

run-proveedores-migrator-dry:
	$(PY) main.py run --entity proveedores --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

run-ped_items-migrator-dry:
	$(PY) main.py run --entity ped_items --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

run-ped_items-migrator:
	$(PY) main.py run --entity ped_items --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

run-oc_items-migrator-dry:
	$(PY) main.py run --entity oc_items --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

run-oc_items-migrator:
	$(PY) main.py run --entity oc_items --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

run-solic_gastos-migrator-dry:
	$(PY) main.py run --entity solic_gastos --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

run-solic_gastos-migrator:
	$(PY) main.py run --entity solic_gastos --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

run-orden_pago-migrator-dry:
	$(PY) main.py run --entity orden_pago --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator --dry-run

run-orden_pago-migrator:
	$(PY) main.py run --entity orden_pago --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export migrator

run-pedidos:
	$(PY) main.py run --entity pedidos --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export $(EXPORT)

run-ped_items:
	$(PY) main.py run --entity ped_items --batch-size $(BATCH) $(if $(LIMIT),--limit $(LIMIT),) --export $(EXPORT)

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

reset-jurisdicciones:
	$(PY) main.py reset --entity jurisdicciones

reset-proveedores:
	$(PY) main.py reset --entity proveedores

reset-pedidos:
	$(PY) main.py reset --entity pedidos

reset-ped_items:
	$(PY) main.py reset --entity ped_items

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
