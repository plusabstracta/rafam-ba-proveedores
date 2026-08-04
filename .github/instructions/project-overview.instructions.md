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

### Entidades sincronizadas (orden de dependencia — pipeline oficial de `main.py run`)

1. `proveedores` (tabla RAFAM `PROVEEDORES`)
2. `oc_items` (tablas RAFAM `OC_ITEMS` + `ORDEN_COMPRA` + `SOLIC_GASTOS`) — OC completa con items embebidos; requiere proveedor
3. `solic_gastos` (tablas RAFAM `SOLIC_GASTOS` + `CTA_COMPROB` vía `REG_COMP`) — enriquecimiento UPDATE-ONLY de gastos que Paxapos ya creó
4. `orden_pago` (tabla RAFAM `ORDEN_PAGO`) — vincula comprobantes vía `ORDEN_PAGO_IMPUT` + `CTA_COMPROB` y la OC canónica vía `REG_COMP`
5. `retenciones` (tabla RAFAM `ORDEN_PAGO_DEDUC`, escaneando las mismas OP) — tipo resuelto contra el catálogo `tipos_retencion` de Paxapos

Entidades adicionales invocables con `--entity` pero fuera del pipeline por defecto: `clasificaciones` (catálogo desde `GASTOS`), `orden_compra` (legacy, deshabilitada en el exporter: warning + no-op).

**Regla:** el orden de ejecución es estricto. Cada entidad depende de las anteriores. El campo `JURISDICCION` no es una entidad: se mapea a `centro_costo_id` vía `_JURISDICCION_CENTRO_COSTO_MAP` en `gateway_mapper.py`. La VIEW `CTA_HOJA_DE_RUTA` y la tabla `RETENCIONES` son estructuras obsoletas: el código usa las tablas reales (`ORDEN_PAGO_IMPUT`, `REG_COMP`, `ORDEN_PAGO_DEDUC`).

> Mapeo completo RAFAM ↔ Paxapos: ver [docs/rafam_paxapos_equivalencias.md](../../docs/rafam_paxapos_equivalencias.md) (fuente de verdad).

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
src/exporter.py      → salida al migrator Paxapos (único destino; orquesta mappers + HTTP + links)
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

#### Variables canónicas

| Grupo | Variables | Requeridas para |
|---|---|---|
| App | `APP_ENV`, `LOG_LEVEL` | Todos los perfiles |
| SOURCE RAFAM | `RAFAM_SOURCE_BACKEND`, `RAFAM_SOURCE_HOST`, `RAFAM_SOURCE_PORT`, `RAFAM_SOURCE_SERVICE`, `RAFAM_SOURCE_USER`, `RAFAM_SOURCE_PASSWORD`, `RAFAM_SOURCE_SQLITE_DB_PATH`, `ORACLE_CLIENT_DIR`/`ORACLE_CLIENT_LIB_DIR` | Export CSV desde RAFAM y sync/import |
| LOCAL state | `LOCAL_STATE_DB_PATH`, `RAFAM_RUN_HISTORY_PATH` | `main.py run/status/reset`; guarda checkpoints, links RAFAM->Paxapos, retry queue e historial |
| DESTINATION Paxapos | `PAXAPOS_URL`, `PAXAPOS_TENANT`, `PAXAPOS_VERIFY_SSL`, `PAXAPOS_TIMEOUT_SECONDS`, `PAXAPOS_API_KEY` | Solo migrator Paxapos |
| RAFAM en Paxapos | `PAXAPOS_RAFAM_IMPORT_PATH`, `PAXAPOS_RAFAM_SPEC_PATH`, `PAXAPOS_RAFAM_LOOKUPS_PATH`, `PAXAPOS_RAFAM_RESOLVER_MERCADERIA_PATH`, `PAXAPOS_RAFAM_RESOLVER_GASTO_PATH`, `PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID`, `PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID`, `RAFAM_SYNC_BATCH_DELAY_SECONDS`, `RAFAM_EJERCICIO_MIN`, `RAFAM_EXCLUDED_COD_PROV`, `RAFAM_STRICT_PARTIAL_ERRORS`, `RAFAM_MIGRAR_OP_SIN_OC` | Solo migrator Paxapos |
| Notificaciones | `NOTIFY_ENABLED`, `NOTIFY_SMTP_HOST`, `NOTIFY_SMTP_PORT`, `NOTIFY_SMTP_USER`, `NOTIFY_SMTP_PASSWORD`, `NOTIFY_FROM`, `NOTIFY_TO`, `NOTIFY_SUBJECT_PREFIX`, `NOTIFY_SMTP_TIMEOUT` | `main.py daily-report` y alertas de integridad |
| Logs/Debug | `RAFAM_LOG_DIR`, `RAFAM_LOG_FILE`, `RAFAM_LOG_DISABLE`, `DUMP_PAYLOAD`, `DUMP_PAYLOAD_FORCE` | Opcionales |

No agregar aliases ni fallbacks legacy a `DB_*`, `SQLITE_DB_PATH`, `CHECKPOINT_DB_PATH`, `ENTITY_LINK_DB_PATH`, `GATEWAY_*`, `MIGRATOR_*`, `LOCAL_CHECKPOINT_DB_PATH` ni `LOCAL_ENTITY_LINK_DB_PATH`. Si aparece un nombre viejo, migrarlo al nombre canónico y actualizar documentación/tests en el mismo cambio.

### 3.4.1 Invariantes de documentación

- `README.md` explica uso diario y perfiles operativos.
- `.env.example` es la plantilla única por roles y debe listar solo variables runtime vigentes.
- `docs/rafam_paxapos_equivalencias.md` es la **única fuente de verdad** sobre qué tablas RAFAM se migran y cómo se mapean a Paxapos.
- `.github/instructions/*.instructions.md` debe reflejar las mismas reglas que los docs para evitar drift de ingeniería.
- Todo cambio de configuración, contrato Paxapos, orden de entidades, payload o comandos Makefile debe actualizar docs e instrucciones relacionadas en el mismo commit.

### 3.5 Compatibilidad Oracle

- Oracle 11g no soporta `FETCH FIRST N ROWS` — usar reflection manual con `get_columns()` + `Table.append_column()`.
- Column names vienen lowercase desde `python-oracledb` — uppercasear al reflejar para consistencia.
- Thick mode requerido: `oracledb.init_oracle_client()`.

### 3.6 Contrato con Paxapos (CakePHP 2)

- Tenant viaja duplicado por compatibilidad: en la URL construida como `{PAXAPOS_URL}/{PAXAPOS_TENANT}/{PAXAPOS_RAFAM_*_PATH}` y en el header `X-Tenant-Id`. `PAXAPOS_URL` nunca debe incluir tenant.
- Auth por `Authorization: Bearer {JWT}` o `X-Api-Key`.
- Payloads CakePHP 2 usan wrapper con nombre del modelo: `{"Proveedor": {...}}`.
- Responses batch (HTTP 207): parsear `results` item por item — un error parcial no invalida todo el batch.

#### Endpoint migrator: `RafamMigracionesController::importar()`

Controller: `Plugin/Account/Controller/RafamMigracionesController.php`

Orden interno de procesamiento (hardcodeado en foreach):
```
proveedores → ordenes_compra → gastos → ordenes_pago
```
Se pueden enviar todas las entidades en un solo payload y el endpoint respeta el orden. Las retenciones viajan dentro del bloque de la OP correspondiente.

#### Órdenes de Compra (`_importPedido`)

- Modelo: `Compras.Pedido` → tabla `compras_pedidos` (con `tablePrefix = 'compras_'`).
- Upsert por `Pedido.internal_id` (formato: `{ej}-{nro}`).
- Estado: `estado_aprobacion` — valor `4` para anular una OC existente.
- Acepta `gasto_nro_comprobante` para vincular OC↔Gasto por número fiscal; si el gasto no existe, el endpoint lo auto-crea.
- Respuesta: `{success, id, mode: create|update, external_id}`.

#### Gastos (`_importGasto`)

- Modelo: `Account.Gasto` → tabla `gastos`.
- Upsert por `proveedor_id + factura_nro` (+ `punto_de_venta` si viene). NO usa `external_id` para dedup.
- `external_id` se graba como traza en `Gasto.observacion` con formato `RAFAM:{...json...}`.
- Sin proveedor o sin factura_nro → siempre INSERT nuevo (sin posibilidad de dedup).
- Campos obligatorios: `importe_total`, `fecha`. Todo lo demás es opcional.
- **No existe mecanismo de anulación** — omitir gastos con `ESTADO_SOLIC=A` del envío.
- Acepta `pedido_id`; Paxapos lo usa para vincular el gasto encontrado o auto-creado con la OC por `Gasto.pedido_id`.
- Asociaciones relevantes: `belongsTo => Proveedor, Clasificacion`, `hasMany => Compras.Pedido`, `HABTM => Egreso` (via `account_egresos_gastos`).
- Respuesta: `{success, id, mode: create|update, external_id}`.

#### Órdenes de Pago (`_importOrdenPago`)

- Modelo: `Account.Egreso` → tabla `egresos`.
- Upsert por `Egreso.identificador_pago` (formato: `RAFAM-OP-{ej}-{nro}`). Si no viene, se autogenera como `RAFAM-{md5(externalId)}`.
- Si ya existe → `skip_existing` (NO actualiza estado ni campos). No hay forma de hacer N→C post-creación.
- Requiere mínimo 1 gasto resoluble — falla explícitamente si `gastoIds` está vacío.
- Usa `gasto_nro_comprobante` como nexo obligatorio hacia gastos; el endpoint auto-crea el gasto si no existe y usa `pedido_id` para vincularlo a la OC. El script resuelve `pedido_id` contra `link_orden_compra`. Si la OC canónica no existe en RAFAM (gasto directo: la OP tiene factura imputada pero su `REG_COMP` no referencia OC), con `RAFAM_MIGRAR_OP_SIN_OC=true` (default) la OP se envía SIN `pedido_id` — Paxapos deduplica el Gasto por `proveedor + factura_nro`; con `false` se omite (solo pagos respaldados por OC). Si la OC existe pero aún no está migrada, la OP se encola y se reintenta.
- Feature flag: `Site.ordenes_de_pago` debe estar en `true` — si no, devuelve HTTP 400 inmediatamente.
- Estados del Egreso: `0=Pendiente, 1=Aprobado, 2=Rechazado, 3=Pagado`. Enviar solo OPs RAFAM con `ESTADO_OP=C`, `CONFIRMADO=S`, `FECH_CONFIRM` presente y comprobante imputado; omitir anuladas, pendientes, no confirmadas o sin fecha. La OC se vincula vía `pedido_id` cuando existe; el gasto directo sin OC se envía sin `pedido_id` (ver `RAFAM_MIGRAR_OP_SIN_OC`).
- Si no se envía `estado`: con `fecha` → auto `PAGADO(3)`, sin `fecha` → auto `PENDIENTE(0)`. Para OPs confirmadas RAFAM, enviar `fecha=FECH_CONFIRM`.
- `allowedFields` del save: `identificador_pago, fecha, tipo_de_pago_id, total, observacion, estado, fecha_programada, cuenta_bancaria_id, numero_operacion`. Notar que `proveedor_id` NO está.
- Respuesta: `{success, id, mode: create|skip_existing, external_id, gasto_ids, gastos_creados}`.

#### Cadena de vínculos en Paxapos

```
OC (compras_pedidos.id) ◄── account_gastos.pedido_id ── Gasto ◄──HABTM (account_egresos_gastos)── Egreso (OP)
```

- OC→Gasto: se establece enviando `gasto_nro_comprobante`; si el gasto no existe, se auto-crea.
- Gasto→OC: si se envia `pedido_id`, Paxapos vincula el gasto por `account_gastos.pedido_id`.
- OP→Gasto: se establece enviando `gasto_nro_comprobante`; si el gasto no existe, se auto-crea y luego se vincula a la OP.

#### Cadena de vínculos en RAFAM (fuente)

```
CTA_COMPROB ◄──(REG_COMP)──► ORDEN_COMPRA / SOLIC_GASTOS
      ▲
      │ (ORDEN_PAGO_IMPUT: bridge físico OP ↔ comprobante)
      │
  ORDEN_PAGO ──► ORDEN_PAGO_DEDUC (EJERCICIO + NRO_OP + CODIGO_DEDUC)
```

- **CTA_COMPROB ↔ ORDEN_COMPRA/SOLIC_GASTOS:** vía `REG_COMP` (por `EJERCICIO + NRO_REG_COMP`). Permite setear `account_gastos.pedido_id`.
- **ORDEN_PAGO ↔ CTA_COMPROB:** vía `ORDEN_PAGO_IMPUT` (PK incluye `NRO_REG_COMP+TIPO_COMPROB+NRO_COMPROB+COD_PROV`); la OC canónica se resuelve por el mismo `NRO_REG_COMP` imputado (NO usar `ORDEN_PAGO.NRO_CANCE` como puente).
- **Retenciones ↔ ORDEN_PAGO:** tabla `ORDEN_PAGO_DEDUC`, match por `EJERCICIO + NRO_OP`. El tipo de retención se resuelve contra el catálogo remoto `tipos_retencion` (con alias por `DEDUCCIONES.DESCRIPCION`).
- **Obsoletas (NO usar):** la VIEW `CTA_HOJA_DE_RUTA` y la tabla `RETENCIONES`.

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
| `proveedores` | `cuit`, `cod_estado`, `payload_hash`, `content_hash`, `deleted_at` | `"<COD_PROV>"` |
| `orden_compra` | `fech_confirm`, `estado_oc`, `cod_prov`, `importe_tot`, `gasto_refs`, `gasto_linked_refs`, `paxapos_gasto_ids`, `has_op`, `payload_hash`, `deleted_at` | `json({"ejercicio": N, "nro_oc": N, "uni_compra": N})` |
| `gasto` | `estado_solic`, `importe_tot`, `cod_prov`, `pedido_id`, `nro_comprobante`, `payload_hash`, `deleted_at` | `json({"deleg_solic": N, "ejercicio": N, "nro_solic": N})` (+ alias `json({"rafam_ref": "SG-..."})`) |
| `orden_pago` | `estado_op`, `confirmado`, `fech_confirm`, `importe_total`, `deleted_at` | `json({"ejercicio": N, "nro_op": N})` |
| `retenciones` | `fingerprint`, `retenciones_count`, `deleted_at` | `json({"ejercicio": N, "nro_op": N})` (1 fila por OP) |
| `clasificacion` | `denominacion`, `nivel`, `parent_codigo`, `deleted_at` | código del clasificador |
| `mercaderia` / `unidad_medida` / `tipo_*` | catálogos auxiliares | ver `DEFAULT_LINK_SCHEMAS` en `src/entity_link_store.py` |

La fuente de verdad del esquema es `DEFAULT_LINK_SCHEMAS` (`src/entity_link_store.py`). Los extras permiten detectar cambios de estado/contenido entre corridas (ej: `estado_oc` o `payload_hash` guardado vs actual).

### 3.8 Detección de cambio de estado

Implementado para Órdenes de Compra:
- OC con estado R sin link previo → se crea en Paxapos.
- `R→A` (Registrada→Anulada): la OC existía con `estado_oc=R` en link_store, ahora viene con `A` → se envía con `Pedido.deleted = 1` (soft-delete), salvo que tenga OP asociada (`has_op`), en cuyo caso se conserva.
- Cambio de contenido con mismo estado R: se detecta por `payload_hash` y se re-envía con upsert.
- `pending_reprocess_days=30`: re-consulta OCs recientes para detectar transiciones.

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
| Reintroducir aliases legacy de env | Configuración ambigua y difícil de operar por roles | Usar solo variables canónicas documentadas |
| Cambiar payload/config sin docs | Drift entre código, operación y agentes | Actualizar README/docs/instructions en el mismo cambio |
| `try/except: pass` | Oculta errores a las 3 AM | Log + `mark_error()` sin avanzar cursor |
| Cargar todo en memoria | OOM con tablas grandes | `stream_results=True` + `fetchmany()` |
| `requests` como dependencia | Agrega supply chain sin necesidad | `urllib` stdlib |
| SQL crudo como strings | Inyección SQL, no portable Oracle↔SQLite | SQLAlchemy expressions |
| Ignorar orden de entidades | Foreign keys rotas en destino | Orden estricto documentado |
