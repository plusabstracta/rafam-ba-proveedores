---
description: "Use when working on any part of the RAFAM sync project: ETL pipeline, Oracle queries, CakePHP 2 gateway, migrator API, checkpoint logic, incremental sync, exporters, entity mapping, SQLAlchemy, or batch processing. Defines what this project is, its invariants, and quality criteria for building reliable scheduled sync scripts."
---

# RAFAM BA Proveedores — Visión del Proyecto y Criterios de Construcción

## 1. Qué es este proyecto

Script de **sincronización incremental programada** que corre cada N minutos en una VM.
Lee datos de una base Oracle (RAFAM — sistema financiero provincial) y los envía
a un portal de proveedores basado en **Paxapos** (CakePHP 2) a través de APIs REST.

```
┌──────────┐     SQLAlchemy      ┌──────────────┐     HTTP JSON      ┌────────────┐
│  Oracle  │ ──────────────────► │  Este script │ ─────────────────► │  Paxapos   │
│  RAFAM   │   (lectura only)   │  (Python VM) │  (migrator API)   │  CakePHP 2 │
└──────────┘                    └──────┬───────┘                    └────────────┘
                                       │
                                 ┌─────┴─────┐
                                 │  SQLite    │
                                 │ checkpoint │
                                 │  + links   │
                                 └───────────┘
```

### Flujo de datos

1. **Origen:** Oracle RAFAM (schema `OWNER_RAFAM`) — solo lectura, sin escritura jamás.
2. **Intermediario:** SQLite local para checkpoints (`state/checkpoint.db`) y vínculos RAFAM↔Paxapos (`state/entity_links.db`).
3. **Destino:** API REST Paxapos — endpoint migrator (`/rafam/migracion/importar.json`) o gateway directo.
4. **Dev local:** SQLite (`state/dev_rafam.db`) cargada desde snapshots CSV — reemplaza Oracle sin cambiar lógica.

### Entidades sincronizadas (orden de dependencia)

1. `jurisdicciones` → `rubros` + `clasificaciones` — catálogo base, cada jurisdicción agrupa sus propios proveedores
2. `proveedores` — dependen de jurisdicciones/rubros
3. `ped_items` → `pedidos` — solicitudes internas
4. `oc_items` → `ordenes_compra` — requieren proveedor
5. `solic_gastos` → `gastos` — facturas del proveedor
6. `orden_pago` → `ordenes_pago` — requieren gastos ya importados

**Regla:** el orden de ejecución es estricto. Cada entidad depende de las anteriores.

---

## 2. Invariantes del proyecto (NUNCA violar)

### Arquitectura

- **Solo lectura en Oracle.** Este script JAMÁS escribe en RAFAM. Es consumidor pasivo.
- **Idempotencia.** Ejecutar el mismo batch dos veces no debe duplicar datos en destino.
- **Checkpoints atómicos.** Si un batch falla, el checkpoint NO avanza. La próxima corrida reintenta automáticamente desde el último punto exitoso.
- **Sin estado en memoria entre corridas.** Todo estado persistente vive en SQLite.

### Dependencias

- **Solo stdlib para HTTP.** Usar `urllib.request` / `urllib.error`. Prohibido `requests`, `httpx`, u otra librería HTTP de terceros.
- **SQLAlchemy 2.x** como única capa de acceso a datos (Oracle y SQLite).
- **`oracledb`** como driver Oracle (thick mode para Oracle < 12.2).
- **Sin frameworks web.** Esto es un script CLI, no un servidor.

### Archivos protegidos

No modificar sin justificación explícita del usuario:
- `main.py` — orquestador CLI
- `src/config.py` — configuración de entidades
- `src/models.py` — dataclasses del dominio

---

## 3. Criterios de calidad para scripts de sincronización programada

### 3.1 Resiliencia ante fallos

- **Timeout configurable** en cada llamada HTTP (`MIGRATOR_TIMEOUT_SECONDS`).
- **Reintentos seguros:** el diseño checkpoint-first garantiza que un crash no pierde progreso ni duplica datos.
- **Logging estructurado** en cada punto de decisión — si algo falla a las 3 AM en la VM, los logs deben bastar para diagnosticar sin reproducir.
- **Validación de datos en frontera:** sanitizar y validar ANTES de enviar. Nunca confiar en que Oracle devuelve datos limpios (campos NULL, strings vacíos donde se espera int, decimales desbordados).

### 3.2 Batch processing

- **Tamaño de batch configurable** (`--batch-size`, default 500).
- **Límite opcional** (`--limit`) para pruebas controladas.
- **Stream results** en SQLAlchemy (`stream_results=True`) — no cargar todas las filas en memoria.
- **Delay entre batches** (`MIGRATOR_BATCH_DELAY_SECONDS`) para no saturar el destino.
- **Dry-run real:** `--dry-run` envía al endpoint con `dry_run=true` pero NO avanza checkpoints.

### 3.3 Separación de responsabilidades

```
main.py              → CLI parsing + orquestación
src/config.py        → metadata de entidades (tabla, campos cursor)
src/models.py        → dataclasses puros (Checkpoint, EntityConfig, SyncResult)
src/db.py            → factory de engines SQLAlchemy
src/source_repository.py → construcción de queries SQLAlchemy
src/sync_engine.py   → lógica incremental (checkpoints, cursores)
src/exporter.py      → destinos de salida (CSV, Gateway, Migrator, Noop)
src/gateway_mapper.py → transformación RAFAM → formato Paxapos
src/checkpoint_store.py → persistencia ORM de checkpoints
src/entity_link_store.py → vínculos RAFAM_ID ↔ Paxapos_ID
```

**Regla:** cada módulo tiene una sola razón para cambiar. Si una modificación toca más de 2 módulos, cuestionar el diseño.

### 3.4 Configuración por entorno

- **Variables de entorno** (`.env` vía `python-dotenv`) como única fuente de configuración runtime.
- **`APP_ENV`** controla defaults: `dev` → `LOG_LEVEL=DEBUG`, `prod` → `LOG_LEVEL=INFO`.
- **`DB_BACKEND`** permite intercambiar Oracle ↔ SQLite sin cambiar código.
- **SSL configurable** (`GATEWAY_VERIFY_SSL`, `MIGRATOR_VERIFY_SSL`) — `false` solo en dev.

### 3.5 Compatibilidad Oracle

- Oracle 11g no soporta `FETCH FIRST N ROWS` — usar reflection manual con `get_columns()` + `Table.append_column()`.
- Column names vienen lowercase desde `python-oracledb` — uppercasear al reflejar para consistencia.
- Thick mode requerido: `oracledb.init_oracle_client()`.

### 3.6 Contrato con Paxapos (CakePHP 2)

- Tenant viaja por header `X-Tenant-Id`, no en la URL.
- Auth por `Authorization: Bearer {JWT}` o `X-Api-Key`.
- Payloads CakePHP 2 usan wrapper con nombre del modelo: `{"Proveedor": {...}}`.
- Responses batch (HTTP 207): parsear `results` item por item — un error parcial no invalida todo el batch.

### 3.7 Testing

- Tests con `pytest` usando SQLite in-memory.
- Fixtures mock de lookups para evitar dependencia de red.
- Tests de mapping: verificar que cada campo RAFAM se transforma correctamente al formato Paxapos.
- No testear lógica de Oracle directamente — eso se valida en integración con contenedor Docker.

---

## 4. Anti-patrones a evitar

| Anti-patrón | Por qué es peligroso | Alternativa |
|---|---|---|
| Full reload en cada corrida | Sobrecarga Oracle y destino, duplica datos | Checkpoints incrementales |
| Guardar estado en archivos planos | No atómico, corrupción en crash | SQLite con transacciones |
| Hardcodear URLs/tokens | Imposible cambiar entre ambientes | Variables de entorno |
| `try/except: pass` | Oculta errores a las 3 AM | Log + `mark_error()` sin avanzar cursor |
| Cargar todo en memoria | OOM con tablas grandes | `stream_results=True` + `fetchmany()` |
| `requests` como dependencia | Agrega supply chain sin necesidad | `urllib` stdlib |
| SQL crudo como strings | Inyección SQL, no portable Oracle↔SQLite | SQLAlchemy expressions |
| Ignorar orden de entidades | Foreign keys rotas en destino | Orden estricto documentado |
