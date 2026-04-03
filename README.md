# RAFAM BA Proveedores Sync

Sincronizador incremental de RAFAM (Oracle) hacia Paxapos, con ejecución por entidad,
checkpoints persistentes y modo de desarrollo offline usando snapshots CSV.

## Objetivos del proyecto

- Extraer datos de RAFAM de forma incremental.
- Procesar y exportar por entidad (`proveedores`, `orden_compra`, `orden_pago`, etc.).
- Evitar full reload en cada corrida mediante checkpoints.
- Permitir desarrollo sin acceso a producción (SQLite cargado desde CSV).

## Stack técnico

- Python 3.11+
- SQLAlchemy 2.x
- Driver Oracle: `oracledb` (vía `oracle+oracledb://`)
- SQLite para checkpoints y modo dev local
- Pytest

## Arquitectura

- `main.py`: CLI (`status`, `run`, `reset`) y orquestación.
- `src/source_repository.py`: construcción de consultas SQLAlchemy por entidad.
- `src/sync_engine.py`: lógica incremental y avance de cursores.
- `src/checkpoint_store.py`: persistencia ORM de checkpoints (`state/checkpoint.db`).
- `src/exporter.py`: destinos de salida (`csv`, `noop`).
- `scripts/load_csv_to_sqlite.py`: carga snapshots CSV a SQLite para desarrollo.

## Modos de base origen

El proyecto soporta dos modos con la variable `DB_BACKEND`:

- `oracle`: conecta a RAFAM productivo o entorno Oracle de integración.
- `sqlite`: usa una base local (`state/dev_rafam.db`) para desarrollo y tests manuales.

## Setup rápido (desarrollo local)

1. Crear entorno virtual e instalar dependencias.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

2. Configurar entorno.

```bash
cp .env.example .env
```

3. Cargar CSVs a SQLite local.

```bash
.venv/bin/python scripts/load_csv_to_sqlite.py --csv-dir output --output-db state/dev_rafam.db
```

4. Ejecutar sincronización por entidad.

```bash
.venv/bin/python main.py run --entity proveedores
.venv/bin/python main.py status
```

## Uso recomendado (Makefile)

Flujo diario simplificado para el equipo:

```bash
make setup
make load-dev
make run-proveedores
make status
```

Comandos utiles:

```bash
make help
make run-all
make run-orden_compra
make run-proveedores-gateway
make run-proveedores-gateway-force-update
make run-proveedores-migrator-dry
make migrator-spec
make reset-proveedores
make reset-all
make test
```

Con variables opcionales:

```bash
make run-orden_compra BATCH=1000 LIMIT=5000 EXPORT=csv
```

## Gateway Paxapos (JSON)

Para enviar datos traducidos a Paxapos desde este script:

```bash
make run-proveedores-gateway
```

El exporter `gateway` arma la URL usando `GATEWAY_URL` + endpoint por entidad.
Para `proveedores` usa por defecto:

```text
{GATEWAY_URL}/account/proveedores.json
```

Headers enviados:

```text
Content-Type: application/json
Accept: application/json
X-Tenant-Id: {GATEWAY_TENANT}
Authorization: Bearer {GATEWAY_JWT}
```

Configuracion recomendada en `.env`:

```dotenv
APP_ENV=dev
LOG_LEVEL=DEBUG
GATEWAY_URL=https://proveedores.paxapos.com
GATEWAY_TENANT=prueba
GATEWAY_JWT=...
GATEWAY_VERIFY_SSL=false
GATEWAY_ENDPOINT_PROVEEDORES=account/proveedores.json
GATEWAY_ENDPOINT_PROVEEDORES_UPDATE=account/proveedores/edit/{id}.json
```

Contrato actual del gateway:

- `GATEWAY_URL`: dominio base de Paxapos
- `GATEWAY_TENANT`: tenant enviado en header `X-Tenant-Id`
- `GATEWAY_JWT`: token JWT enviado como `Authorization: Bearer ...`
- `GATEWAY_VERIFY_SSL`: `false` solo para desarrollo con certificados no confiables
- `GATEWAY_ENDPOINT_PROVEEDORES`: path del endpoint JSON
- `GATEWAY_ENDPOINT_PROVEEDORES_UPDATE`: path para update cuando se usa `--force-update` (`{id}` = id remoto)

Modo de operacion (gateway):

- Default (`--force-update` ausente): create-only. Si ya existe vinculacion local, se saltea.
- Con `--force-update`: si existe vinculacion local RAFAM->Paxapos, se envia update al endpoint de edicion.

## RAFAM Migrator API

Para usar el importador batch oficial de Paxapos en vez del endpoint directo de proveedores:

```dotenv
MIGRATOR_BASE_URL=https://dev2.paxapos.com
MIGRATOR_TENANT=prueba
MIGRATOR_API_KEY=...
MIGRATOR_VERIFY_SSL=false
MIGRATOR_TIMEOUT_SECONDS=20
MIGRATOR_IMPORT_ENDPOINT=rafam/migracion/importar.json
MIGRATOR_SPEC_ENDPOINT=rafam/migracion/spec.json
MIGRATOR_LOOKUPS_ENDPOINT=rafam/migracion/lookups.json
```

Uso estandar actualizado:

- URL sin tenant en path: `https://dev2.paxapos.com/rafam/migracion/importar.json`
- tenant por header: `X-Tenant-Id: prueba`

Uso inicial recomendado:

```bash
make migrator-spec
make migrator-lookups
make run-proveedores-migrator-dry LIMIT=20 BATCH=20
make run-proveedores-migrator LIMIT=20 BATCH=20
make run-ped_items-migrator-dry LIMIT=50 BATCH=50
make run-oc_items-migrator-dry LIMIT=50 BATCH=50
```

Comportamiento actual del modo `migrator`:

- Soporta `proveedores`.
- Soporta `ped_items` (genera bloque `pedidos` con items para migrator).
- Soporta `oc_items` (genera bloque `ordenes_compra` con items para migrator).
- Soporta `solic_gastos` (genera bloque `gastos` — facturas del proveedor).
- Soporta `orden_pago` (genera bloque `ordenes_pago` — vinculadas a gastos vía `gasto_external_ids`).
- Envía payload batch al endpoint `/rafam/migracion/importar.json`.
- `--dry-run` manda `dry_run=true` y no avanza checkpoints.
- En modo real, persiste el vínculo RAFAM -> Paxapos usando `results.proveedores[].id`.

Catálogos remotos del migrator:

- `make migrator-lookups`
- `.venv/bin/python main.py lookups`
- `.venv/bin/python main.py lookups --only mercaderias,unidades_de_medida,tipos_factura,tipos_de_pago,proveedores,gastos`

Notas de mapeo `ped_items` -> `pedidos` y `oc_items` -> `ordenes_compra`:

- `mercaderia_external_ref`: se envía referencia determinística RAFAM para resolución server-side en migrator.
- `unidad_de_medida_id`: match por `name` normalizado de `unidades_de_medida`; fallback `MIGRATOR_DEFAULT_UNIDAD_ID` (default `1`).
- Si un item no puede construir referencia externa mínima, se omite y se informa en logs.
- El matching textual de mercaderías ya no es responsabilidad del script Python.

Notas de mapeo `solic_gastos` -> `gastos`:

- `external_id.rafam_ref`: formato `SG-{ejercicio}-{deleg_solic}-{nro_solic}` — el migrator guarda traza `RAFAM:{...}` en observación del gasto.
- `tipo_factura_id`: match por `codename` o `name` de `tipos_factura`; fallback `MIGRATOR_DEFAULT_TIPO_FACTURA_ID`.
- Excluye solicitudes con `ESTADO_SOLIC=A` (anuladas).
- `factura_nro`: formateado a 8 dígitos (zfill) desde `NRO_DOC` de RAFAM.

Notas de mapeo `orden_pago` -> `ordenes_pago`:

- `gasto_external_ids`: referencia string `SG-{ejercicio}-{deleg_solic}-{nro_solic}` que el migrator busca en `Gasto.observacion` con LIKE.
- Requiere que los gastos (solic_gastos) estén importados previamente.
- `identificador_pago`: formato `RAFAM-OP-{ejercicio}-{nro_op}` para upsert.
- `fecha`: solo se envía si `ESTADO_OP=C` (confirmada/pagada).
- Excluye OPs con `ESTADO_OP=A` (anuladas).
- OPs sin gasto vinculado vía JOIN `NRO_CANCE=NRO_SOLIC` se omiten con warning.

Comportamiento por entorno:

- `APP_ENV=dev`: si no definis `LOG_LEVEL`, usa `DEBUG`
- `APP_ENV=prod`: si no definis `LOG_LEVEL`, usa `INFO`
- `GATEWAY_VERIFY_SSL=false`: desactiva validacion SSL del gateway, util para `dev2`
- `GATEWAY_VERIFY_SSL=true`: requerido en produccion

Payload enviado (CakePHP 2):

```json
{
	"Proveedor": {
		"name": "...",
		"razon_social": "...",
		"cuit": "20123456789",
		"mail": "...",
		"telefono": "...",
		"domicilio": "...",
		"localidad": "...",
		"provincia": "...",
		"codigo_postal": "...",
		"tipo_documento_id": 1,
		"iva_condicion_id": 1
	}
}
```

Nota sobre rutas CakePHP 2:

- En el flujo actual del proyecto, el tenant viaja por header `X-Tenant-Id`.
- El script ya no depende de incluir el tenant en la URL base.
- El endpoint de proveedores se consume directo como `account/proveedores.json`.

## CLI

```bash
.venv/bin/python main.py status
.venv/bin/python main.py spec --target migrator
.venv/bin/python main.py lookups --only mercaderias,proveedores
.venv/bin/python main.py run
.venv/bin/python main.py run --entity proveedores
.venv/bin/python main.py run --entity proveedores --export gateway --force-update
.venv/bin/python main.py run --entity proveedores --export migrator --dry-run
.venv/bin/python main.py run --entity orden_compra --batch-size 500 --limit 1000
.venv/bin/python main.py reset --entity proveedores
.venv/bin/python main.py reset --all
```

## Filtro de fecha y flujo encadenado (`--months` y `--linked`)

### `--months N`

Filtra los registros de los últimos N meses por la fecha principal de cada entidad
(`FECH_OC`, `FECH_OP`, `FECH_SOLIC`, etc.). Cuando se usa, reemplaza el cursor del
checkpoint — es decir, siempre trae datos del período indicado sin importar cuánto
haya avanzado la sincronización incremental.

```bash
python main.py run --months 3
```

### `--linked`

Garantiza que todos los registros exportados forman parte de un flujo OC completo,
anclando cada entidad a `ORDEN_COMPRA.FECH_OC` mediante subqueries SQL:

| Entidad | Lógica |
|---|---|
| `orden_compra` | Filtro directo por `FECH_OC >= since` |
| `oc_items` | JOIN a `ORDEN_COMPRA WHERE FECH_OC >= since` |
| `proveedores` | `WHERE COD_PROV IN (SELECT COD_PROV FROM ORDEN_COMPRA WHERE FECH_OC >= since)` |
| `solic_gastos` | `WHERE EXISTS (OC_ITEMS JOIN ORDEN_COMPRA WHERE NRO_SOLIC match AND FECH_OC >= since)` |
| `orden_pago` | `WHERE EXISTS (OC_ITEMS JOIN ORDEN_COMPRA WHERE NRO_CANCE match AND FECH_OC >= since)` |
| `jurisdicciones` | Full load (tabla catálogo, sin cambio) |

Esto resuelve el problema de datos huérfanos: OCs del 2019 y pagos del 2023 que no
se pueden encadenar. Con `--linked`, solo se exporta lo que tiene un flujo completo
trazable de punta a punta.

### `--output-dir DIR`

Guarda los CSV en una subcarpeta específica en vez de `output/` (default).

```bash
python main.py run --output-dir output/rafam_ultimos_3_meses
```

### Uso combinado (recomendado para entregas)

```bash
# Exportar últimos 3 meses con flujo encadenado, sin impactar Paxapos
python main.py run --months 3 --linked --dry-run --output-dir output/rafam_ultimos_3_meses
```

Este comando:
- Conecta a Oracle RAFAM
- Trae solo registros de los últimos 3 meses que pertenecen a un flujo OC completo
- Guarda los CSV en `output/rafam_ultimos_3_meses/`
- No avanza checkpoints ni envía nada al endpoint de Paxapos

### `--dry-run`

En cualquier modo de exportación:
- No avanza los checkpoints (la corrida es repetible sin efecto secundario)
- En modo `--export migrator`: envía el payload con `dry_run=true` al endpoint (sin persistir datos)
- Los CSV se generan igual en la carpeta especificada

## Checkpoints incrementales

Cada entidad guarda en `state/checkpoint.db`:

- `last_id`
- `last_ts`
- `last_run`
- `records_sent`
- `status`

Si una corrida falla, no se avanza cursor. La siguiente corrida reintenta sin pérdida.

## Oracle en contenedor (opcional para integración)

Para pruebas de integración SQL Oracle, pueden usar Oracle Free en Docker:

```bash
docker run -d -p 1521:1521 \
	-e ORACLE_PASSWORD=TuPasswordSeguro123 \
	--name oracle-free \
	container-registry.oracle.com/database/free:latest
```

Notas:

- No es obligatorio para el día a día del equipo.
- Para desarrollo funcional y lógica incremental, SQLite + CSV suele ser suficiente.
- Recomendada su utilización para validar compatibilidad SQL Oracle antes de release.

## Recomendación de flujo profesional

1. Desarrollo diario: `DB_BACKEND=sqlite` con snapshots CSV.
2. QA técnico: correr pruebas de integración con Oracle en contenedor.
3. Producción: `DB_BACKEND=oracle` desde Debian con acceso a RAFAM real.

## Ejecución en producción (Migrator API)

Orden de ejecución obligatorio — cada paso depende del anterior:

### 1. Validación previa (dry-run)

Antes de escribir datos reales, verificar con dry-run que todo se mapea correctamente:

```bash
# Verificar que el migrator es accesible
make migrator-spec
make migrator-lookups

# Dry-run de cada entidad con volumen limitado
make run-proveedores-migrator-dry   LIMIT=100 BATCH=100
make run-ped_items-migrator-dry     LIMIT=100 BATCH=100
make run-oc_items-migrator-dry      LIMIT=100 BATCH=100
make run-solic_gastos-migrator-dry   LIMIT=100 BATCH=100
make run-orden_pago-migrator-dry     LIMIT=100 BATCH=100
```

Verificar en los logs que no haya errores y que los conteos `ok` sean correctos.

### 2. Importación real (orden estricto)

```bash
# Paso 1: Proveedores (sin dependencias)
make run-proveedores-migrator BATCH=500

# Paso 2: Pedidos (solicitudes internas)
make run-ped_items-migrator BATCH=500

# Paso 3: Órdenes de compra (necesitan proveedor)
make run-oc_items-migrator BATCH=500

# Paso 4: Gastos/Facturas (necesitan existir para vincular con OPs)
make run-solic_gastos-migrator BATCH=500

# Paso 5: Órdenes de pago (necesitan gastos ya importados)
make run-orden_pago-migrator BATCH=500
```

**Importante:** `orden_pago` DEBE ejecutarse después de `solic_gastos` porque
resuelve sus gastos vía `gasto_external_ids` buscando la traza RAFAM:{...}
que el migrator guarda en la observación de cada gasto importado.

### 3. Variables de entorno para producción

```dotenv
APP_ENV=prod
LOG_LEVEL=INFO
DB_BACKEND=oracle
DB_HOST=ip.del.servidor.rafam
DB_PORT=1521
DB_SERVICE=BDRAFAM
DB_USER=usuario_lectura
DB_PASSWORD=secreto

MIGRATOR_BASE_URL=https://paxapos.dominio.gob.ar
MIGRATOR_TENANT=nombre_tenant_real
MIGRATOR_API_KEY=api_key_real
MIGRATOR_VERIFY_SSL=true
MIGRATOR_TIMEOUT_SECONDS=30
MIGRATOR_DEFAULT_UNIDAD_ID=1
MIGRATOR_DEFAULT_TIPO_PAGO_ID=1
```

### 4. Verificación post-importación

```bash
# Ver estado de checkpoints
make status

# Si algo falló, se puede re-ejecutar el mismo make.
# El sistema es incremental: no duplica datos ya enviados.
```

### 5. Re-ejecución y recuperación de errores

- Si una corrida falla a mitad de camino, el checkpoint no avanza.
- La siguiente ejecución retoma desde el último lote exitoso.
- Para forzar una recarga completa de una entidad:

```bash
make reset-proveedores
make run-proveedores-migrator
```

---

## Tests

```bash
.venv/bin/python -m pytest -q
```

## Nota de ejecucion

Los comandos del README usan `.venv/bin/python` a proposito para evitar errores
por Python de sistema (`externally-managed-environment`) y mantener ejecuciones
consistentes entre desarrolladores.