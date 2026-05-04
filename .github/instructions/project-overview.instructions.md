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
2. **Intermediario:** SQLite local de estado (`LOCAL_STATE_DB_PATH`, default `state/checkpoint.db`) para checkpoints y vínculos RAFAM↔Paxapos.
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
- **Operación local vía Makefile.** Para setup, carga, ejecución y reseteo usar objetivos `make` (evitar flujos ad-hoc de tooling externo para entorno Python).

### Archivos protegidos

No modificar sin justificación explícita del usuario:
- `main.py` — orquestador CLI
- `src/config.py` — configuración de entidades
- `src/models.py` — dataclasses del dominio

---

## 3. Criterios de calidad para scripts de sincronización programada

### 3.1 Resiliencia ante fallos

- **Timeout configurable** en cada llamada HTTP (`PAXAPOS_TIMEOUT_SECONDS`).
- **Reintentos seguros:** el diseño checkpoint-first garantiza que un crash no pierde progreso ni duplica datos.
- **Logging estructurado** en cada punto de decisión — si algo falla a las 3 AM en la VM, los logs deben bastar para diagnosticar sin reproducir.
- **Validación de datos en frontera:** sanitizar y validar ANTES de enviar. Nunca confiar en que Oracle devuelve datos limpios (campos NULL, strings vacíos donde se espera int, decimales desbordados).

### 3.2 Batch processing

- **Tamaño de batch configurable** (`--batch-size`, default 500).
- **Límite opcional** (`--limit`) para pruebas controladas.
- **Stream results** en SQLAlchemy (`stream_results=True`) — no cargar todas las filas en memoria.
- **Delay entre batches** (`RAFAM_SYNC_BATCH_DELAY_SECONDS`) para no saturar el destino.
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
- **`RAFAM_SOURCE_BACKEND`** permite intercambiar Oracle ↔ SQLite sin cambiar código.
- **Perfiles operativos:** RAFAM-only completa solo `RAFAM_SOURCE_*` para generar CSVs; importación Paxapos completa además `LOCAL_STATE_DB_PATH` y `PAXAPOS_*`.
- **SSL configurable** (`PAXAPOS_VERIFY_SSL`) — `false` solo en dev.

### 3.5 Compatibilidad Oracle

- Oracle 11g no soporta `FETCH FIRST N ROWS` — usar reflection manual con `get_columns()` + `Table.append_column()`.
- Column names vienen lowercase desde `python-oracledb` — uppercasear al reflejar para consistencia.
- Thick mode requerido: `oracledb.init_oracle_client()`.

### 3.6 Contrato con Paxapos (CakePHP 2)

- Tenant viaja por header `X-Tenant-Id`, no en la URL.
- Auth por `Authorization: Bearer {JWT}` o `X-Api-Key`.
- Payloads CakePHP 2 usan wrapper con nombre del modelo: `{"Proveedor": {...}}`.
- Responses batch (HTTP 207): parsear `results` item por item — un error parcial no invalida todo el batch.

#### Endpoint migrator: `RafamMigracionesController::importar()`

Controller: `Plugin/Account/Controller/RafamMigracionesController.php`

Orden interno de procesamiento (hardcodeado en foreach):
```
rubros → clasificaciones → proveedores → pedidos → ordenes_compra → gastos → ordenes_pago
```
Se pueden enviar todas las entidades en un solo payload y el endpoint respeta el orden.

#### Órdenes de Compra (`_importPedido`)

- Modelo: `Compras.Pedido` → tabla `compras_pedidos` (con `tablePrefix = 'compras_'`).
- Upsert por `Pedido.internal_id` (formato: `rafam-oc-{ej}-{uni}-{nro}`).
- Estado: `estado_aprobacion` — valor `4` para anular una OC existente.
- Acepta `gasto_ids: [int]` para vincular OC↔Gasto via HABTM (tanto en create como en update).
- Acepta `gasto_external_ids: [string]` como fallback (resuelve buscando traza `RAFAM:{...}` en `Gasto.observacion`).
- Respuesta: `{success, id, mode: create|update, external_id}`.

#### Gastos (`_importGasto`)

- Modelo: `Account.Gasto` → tabla `gastos`.
- Upsert por `proveedor_id + factura_nro` (+ `punto_de_venta` si viene). NO usa `external_id` para dedup.
- `external_id` se graba como traza en `Gasto.observacion` con formato `RAFAM:{...json...}`.
- Sin proveedor o sin factura_nro → siempre INSERT nuevo (sin posibilidad de dedup).
- Campos obligatorios: `importe_total`, `fecha`. Todo lo demás es opcional.
- **No existe mecanismo de anulación** — omitir gastos con `ESTADO_SOLIC=A` del envío.
- **No acepta `pedido_id`** — el vínculo Gasto↔OC solo se establece desde el lado de la OC (via `gasto_ids`).
- Asociaciones relevantes: `belongsTo => Proveedor, Clasificacion`, `hasMany => Compras.Pedido`, `HABTM => Egreso` (via `account_egresos_gastos`).
- Respuesta: `{success, id, mode: create|update, external_id}`.

#### Órdenes de Pago (`_importOrdenPago`)

- Modelo: `Account.Egreso` → tabla `egresos`.
- Upsert por `Egreso.identificador_pago` (formato: `RAFAM-OP-{ej}-{nro}`). Si no viene, se autogenera como `RAFAM-{md5(externalId)}`.
- Si ya existe → `skip_existing` (NO actualiza estado ni campos). No hay forma de hacer N→C post-creación.
- Requiere mínimo 1 gasto resoluble — falla explícitamente si `gastoIds` está vacío.
- `gasto_ids` (IDs numéricos) tiene prioridad. `gasto_external_ids` es fallback automático.
- Feature flag: `Site.ordenes_de_pago` debe estar en `true` — si no, devuelve HTTP 400 inmediatamente.
- Estados del Egreso: `0=Pendiente, 1=Aprobado, 2=Rechazado, 3=Pagado`. No existe "Anulado" — omitir OPs con `ESTADO_OP=A` del envío.
- Si no se envía `estado`: con `fecha` → auto `PAGADO(3)`, sin `fecha` → auto `PENDIENTE(0)`.
- `allowedFields` del save: `identificador_pago, fecha, tipo_de_pago_id, total, observacion, estado, fecha_programada, cuenta_bancaria_id, numero_operacion`. Notar que `proveedor_id` NO está.
- Respuesta: `{success, id, mode: create|skip_existing, external_id, gasto_ids}`.

#### Cadena de vínculos en Paxapos

```
OC (compras_pedidos.gasto_id) ──HABTM──► Gasto ◄──HABTM (account_egresos_gastos)── Egreso (OP)
```

- OC→Gasto: se establece enviando `gasto_ids` en el payload de la OC.
- Gasto→OC: no hay forma desde `_importGasto`.
- OP→Gasto: se establece enviando `gasto_ids` en el payload de la OP.

#### Cadena de vínculos en RAFAM (fuente)

```
OC_ITEMS ──(DELEG_SOLIC, NRO_SOLIC)──► SOLIC_GASTOS ◄──(NRO_CANCE)── ORDEN_PAGO
```

El Gasto (SOLIC_GASTOS) es el puente entre OC y OP. La FK de OC_ITEMS a SOLIC_GASTOS permite resolver qué gastos pertenecen a cada OC.

#### Colisión de columnas en JOINs

Cuando un LEFT JOIN trae columnas con el mismo nombre que la tabla principal (ej: `ESTADO_OC` existe en `OC_ITEMS` y en `ORDEN_COMPRA`), se debe usar `.label()` en SQLAlchemy para prefijar:
```python
orden_compra.c.ESTADO_OC.label("OC_ESTADO_OC")
```
Luego leer como `raw.get("OC_ESTADO_OC")` en el exporter. Bug real encontrado en Sprint 1.

### 3.7 Entity Link Store — esquema de extras por entidad

Cada entidad tiene una tabla `link_<entity>` en SQLite con columnas base (`source_key`, `remote_id`, `updated_at`) más extras configurables:

| Entidad | Extras | source_key format |
|---|---|---|
| `proveedores` | `cuit`, `cod_estado` | `"<COD_PROV>"` |
| `clasificacion` | — | `json({"jurisdiccion": "..."}`) |
| `rubro` | — | `json({"jurisdiccion": "..."})` |
| `pedido` | — | `json({"ejercicio": N, "num_ped": N})` |
| `orden_compra` | `fech_confirm`, `estado_oc`, `cod_prov`, `importe_tot` | `json({"ejercicio": N, "nro_oc": N, "uni_compra": N})` |
| `gasto` | `estado_solic`, `importe_tot`, `cod_prov` | `json({"rafam_ref": "SG-ej-deleg-nro"})` |
| `orden_pago` | `estado_op`, `importe_total` | `json({"ejercicio": N, "nro_op": N})` |

Los extras permiten detectar cambios de estado entre corridas (ej: `estado_oc` guardado vs actual).

### 3.8 Detección de cambio de estado

Implementado para Órdenes de Compra (Sprint 1):
- `R→N` (Registrada→Normal): la OC aparece con estado N, no existía en link_store → se crea.
- `N→A` (Normal→Anulada): la OC existía con `estado_oc=N` en link_store, ahora viene con `A` → se envía con `estado_aprobacion: 4`.
- `pending_reprocess_days=30`: re-consulta OCs con estado N de los últimos 30 días para detectar transiciones.

NO implementado para Gastos ni OPs (el endpoint no soporta anulación ni update post-creación).

### 3.9 Testing

- Tests con `pytest` usando SQLite in-memory.
- Fixtures mock de lookups para evitar dependencia de red.
- Tests de mapping: verificar que cada campo RAFAM se transforma correctamente al formato Paxapos.
- No testear lógica de Oracle directamente — eso se valida en integración con contenedor Docker.

#### Cuándo ejecutar tests

Ejecutar tests **siempre** que se modifique `src/exporter.py`, `src/gateway_mapper.py`, `src/entity_link_store.py`, `src/sync_engine.py`, o `src/source_repository.py`.

#### Comandos

```bash
# Unitarios (sin DB, <1s) — correr siempre
.venv/bin/python -m pytest tests/test_migrator_mapping.py tests/test_sync_engine.py -v

# Integración con datos reales (requiere state/dev_rafam.db)
RAFAM_SOURCE_BACKEND=sqlite .venv/bin/python -m pytest tests/test_oc_integration.py -v

# Todo junto
RAFAM_SOURCE_BACKEND=sqlite .venv/bin/python -m pytest tests/ -v
```

#### Suites de test

| Archivo | Tipo | Qué valida | Dependencias |
|---|---|---|---|
| `tests/test_migrator_mapping.py` | Unitario | Payload Paxapos: campos, name, centro_costo_id, agrupación OC, observaciones | Ninguna (mocks) |
| `tests/test_sync_engine.py` | Unitario | Lógica incremental, checkpoints, cursores | Ninguna (mocks) |
| `tests/test_oc_integration.py` | Integración | Pipeline OC completo con datos reales | `state/dev_rafam.db` |

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
