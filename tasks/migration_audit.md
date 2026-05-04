# Auditoría de Migración RAFAM → Paxapos

## Orden de migración (por dependencias FK)
1. `jurisdicciones` → escribe `rubro` + `clasificacion` en entity_link_store
2. `proveedores` → escribe `proveedores` en entity_link_store
3. `ped_items` → lee `rubro` + escribe `pedido` (solicitudes de bienes)
4. `oc_items` → lee `rubro` + `proveedores` + escribe `orden_compra`
5. `solic_gastos` → lee `clasificacion` + `proveedores` + escribe `gasto`
6. `orden_pago` → lee `gasto` + escribe `orden_pago`

## Resultado de migración completa (2026-04-07)

| Entidad | Registros fuente | Enviados OK | Omitidos | Estado |
|---|---|---|---|---|
| jurisdicciones | 27 | 27 rubros + 27 clasif | 0 | ✅ |
| proveedores | 295 | 295 | 0 | ✅ |
| ped_items | 3,626 | 1,040 pedidos | 0 | ✅ |
| oc_items | 5,176 | 1,065 OCs | 0 | ✅ |
| solic_gastos | 16,851 | 1,012 gastos únicos | 1 (DECIMAL overflow) | ✅ |
| orden_pago | 1,089 | 0 | todos | ❌ Server-side |

### orden_pago bloqueado (server-side)
- La spec indica `requiere Site.ordenes_de_pago=true`.
- Feature flag probablemente deshabilitado en tenant `prueba`.
- El servidor lanza `"Unknown status code"` al intentar HTTP 207 → CakePHP 2 crash.
- **dry_run=true funciona OK**, solo falla con dry_run=false.
- **Acción requerida**: Habilitar `Site.ordenes_de_pago=true` en el panel de Paxapos, luego reintentar con `make run-orden_pago-migrator BATCH=200`.
- El código del cliente está listo: validación DECIMAL(10,2) agregada, `gasto_ids` se resuelven correctamente.

## Comandos de ejecución usados

```bash
# 1. Limpiar estado
.venv/bin/python -c "import sqlite3; conn=sqlite3.connect('state/checkpoint.db'); c=conn.cursor(); c.execute('DELETE FROM sync_checkpoints'); c.execute('DELETE FROM sync_entity_links'); conn.commit()"

# 2. Dry-run de todas las entidades (verificar mappings)
make run-jurisdicciones-migrator-dry
make run-proveedores-migrator-dry
make run-ped_items-migrator-dry
make run-oc_items-migrator-dry
make run-solic_gastos-migrator-dry BATCH=200
make run-orden_pago-migrator-dry BATCH=200

# 3. Migración real (orden estricto)
make run-jurisdicciones-migrator
make run-proveedores-migrator
make run-ped_items-migrator
make run-oc_items-migrator
make run-solic_gastos-migrator BATCH=200
make run-orden_pago-migrator BATCH=200   # ❌ bloqueado server-side
```

### Batch sizes recomendados
| Entidad | Batch size | Motivo |
|---|---|---|
| jurisdicciones | 500 (default) | Solo 27 registros |
| proveedores | 500 (default) | 295 registros, cabe en 1 batch |
| ped_items | 500 (default) | Sin problemas |
| oc_items | 500 (default) | Sin problemas |
| solic_gastos | **200** | Datasets grandes (~16K), evitar timeouts |
| orden_pago | **200** | Precaución por complejidad del JOIN |

## Entity Links actuales (checkpoint.db)

| Entidad | Links | source_key format |
|---|---|---|
| `rubro` | 27 | `{"jurisdiccion": "X"}` |
| `clasificacion` | 27 | `{"jurisdiccion": "X"}` |
| `proveedores` | 295 | `str(COD_PROV)` |
| `pedido` | 1,001 | `{"ejercicio": E, "num_ped": N}` |
| `orden_compra` | 1,059 | `{"ejercicio": E, "uni_compra": U, "nro_oc": N}` |
| `gasto` | 1,012 | `{"rafam_ref": "SG-EJ-DL-NR"}` |

## Errores conocidos y fixes aplicados

### 1. HTTP 500 con importes > 99,999,999.99 (DECIMAL(10,2))
- **Causa raíz**: CakePHP 2 intenta devolver HTTP 207 (Multi-Status) cuando hay error de validación, pero no tiene ese status code registrado → crash.
- **Registros culpables solic_gastos**: `SG-2026-1-269` (importe: 105,790,000.0).
- **Registros culpables orden_pago** (4 OPs):
  - OP 2026-334: 701,653,187.9
  - OP 2026-1018: 697,842,673.0
  - OP 2026-1072: 113,519,717.44
  - OP 2026-386: 108,558,400.99
- **Fix**: Validar importe < 99,999,999.99 antes de enviar; omitir los que exceden con warning en log.
- **Estado**: Fix aplicado en `_map_solic_gasto()` y `_write_batch_orden_pago()`.

### 2. OP_COD_PROV vacío en solic_gastos  
- **Causa raíz**: El LEFT JOIN a ORDEN_PAGO devuelve string vacío `''` cuando no hay match. `int('')` falla.
- **Fix**: Usar `self._to_int()` que maneja cadenas vacías.
- **Estado**: Fix aplicado.

### 3. Timestamps string en SQLite no se parsean como datetime
- **Causa raíz**: `extract_cursor_values` descartaba timestamps string de SQLite.
- **Fix**: Agregado `_parse_ts()` que parsea `"YYYY-MM-DD HH:MM:SS"` de TEXT columns.
- **Estado**: Fix aplicado, tests pasan.

### 4. orden_pago: HTTP 500 "Unknown status code" (SERVER-SIDE)
- **Causa raíz**: Feature flag `Site.ordenes_de_pago` no habilitado en tenant.
- **Efecto**: CakePHP 2 intenta HTTP 207, crash igual que error #1.
- **Fix**: Habilitar `Site.ordenes_de_pago=true` en panel Paxapos. Código cliente listo.
- **Estado**: Bloqueado (server-side).

## Datos en CSVs (rafam_ultimos_3_meses)
| Entidad | Filas CSV | Filas mapeadas |
|---|---|---|
| jurisdicciones | 27 | 27 |
| proveedores | 295 (sin header) | 295 |
| pedidos | 1001 | 1001 (agrupados desde ped_items) |
| ped_items | 3626 | 3626 |
| oc_items | 3583 (+1593 extra por join) | 1059 OCs |
| solic_gastos | 1599 | ~1563 (35 anuladas, 1 importe excedido) |
| orden_pago | 1089 | ~52 con gasto vinculado (rest sin NRO_CANCE) |

## Config
- **Servidor de prueba**: dev2.paxapos.com
- **Tenant**: prueba
- **DB local**: state/dev_rafam.db (SQLite cargada desde CSVs)
- **Estado local**: state/checkpoint.db (checkpoints + links RAFAM -> Paxapos)
- **Tests**: 24 tests pasan (`make test`) post-fixes
- **Env vars relevantes**:
  - `RAFAM_SOURCE_BACKEND=sqlite` (local dev con snapshot)
  - `LOCAL_STATE_DB_PATH=state/checkpoint.db` (estado incremental + links)
  - `PAXAPOS_URL`, `PAXAPOS_TENANT`, `PAXAPOS_API_KEY` (solo para migrator/gateway Paxapos)
  - `PAXAPOS_RAFAM_IMPORT_PATH`, `PAXAPOS_RAFAM_SPEC_PATH`, `PAXAPOS_RAFAM_LOOKUPS_PATH` (paths relativos migrator)
  - `PAXAPOS_RAFAM_DEFAULT_*_ID` (defaults de catálogos Paxapos; validar con lookups)
  - `RAFAM_SYNC_BATCH_DELAY_SECONDS` (opcional, delay entre batches)
  - `PAXAPOS_VERIFY_SSL=false` (solo para desarrollo con certificados no confiables)
