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
- SQLite para estado local del sync y modo dev local
- Pytest

## Arquitectura

- `main.py`: CLI (`status`, `run`, `reset`) y orquestación.
- `src/source_repository.py`: construcción de consultas SQLAlchemy por entidad.
- `src/sync_engine.py`: lógica incremental y avance de cursores.
- `src/checkpoint_store.py`: persistencia ORM de checkpoints en la SQLite local de estado.
- `src/exporter.py`: destinos de salida (`csv`, `noop`).
- `scripts/load_csv_to_sqlite.py`: carga snapshots CSV a SQLite para desarrollo.

## Arquitectura de entornos

El flujo tiene tres lugares claramente separados:

- **SOURCE RAFAM**: Oracle RAFAM real, o un snapshot SQLite para desarrollo.
- **LOCAL**: este servidor/script, con una SQLite de estado para checkpoints y links RAFAM->Paxapos.
- **DESTINATION Paxapos**: portal de proveedores/CakePHP 2 donde se exporta la información procesada.

El origen soporta dos modos con `RAFAM_SOURCE_BACKEND`:

- `oracle`: conecta a RAFAM productivo o entorno Oracle de integración.
- `sqlite`: usa una base local (`state/dev_rafam.db`) para desarrollo y tests manuales.

## Perfiles de uso

Hay dos perfiles operativos y no necesitan completar las mismas variables:

- **Operador RAFAM / CSV**: tiene acceso al Oracle RAFAM y genera snapshots CSV. Solo completa `APP_*`, `RAFAM_SOURCE_*` y, si corresponde, `ORACLE_CLIENT_DIR`. No necesita `PAXAPOS_*`.
- **Operador Paxapos / importacion**: importa o sincroniza hacia Paxapos. Completa `RAFAM_SOURCE_*` o `RAFAM_SOURCE_SQLITE_DB_PATH`, `LOCAL_STATE_DB_PATH` y las variables `PAXAPOS_*` que correspondan al modo usado.

Flujo RAFAM-only:

```bash
make setup
make export-rafam-csv
make export-rafam-csv MONTHS=6 TABLES=PROVEEDORES,ORDEN_PAGO
```

Ese flujo no consulta ni valida credenciales Paxapos.

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

Para desarrollo offline con snapshots, usar `RAFAM_SOURCE_BACKEND=sqlite`. Para exportar desde RAFAM real, usar `RAFAM_SOURCE_BACKEND=oracle` y completar las credenciales `RAFAM_SOURCE_*`.

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
make export-rafam-csv
make load-dev
make run-proveedores
make status
```

Comandos utiles:

```bash
make help
make export-rafam-csv
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

El exporter `gateway` es el endpoint directo legacy de Paxapos para proveedores. Usa el mismo destino `PAXAPOS_URL`/`PAXAPOS_TENANT` que el migrator, pero llama endpoints JSON específicos.
Para `proveedores` usa por defecto:

```text
{PAXAPOS_URL}/account/proveedores.json
```

Headers enviados:

```text
Content-Type: application/json
Accept: application/json
X-Tenant-Id: {PAXAPOS_TENANT}
Authorization: Bearer {PAXAPOS_JWT}
```

Configuracion recomendada en `.env`:

```dotenv
APP_ENV=dev
LOG_LEVEL=DEBUG
PAXAPOS_URL=https://proveedores.madariaga.gob.ar
PAXAPOS_TENANT=madariaga
PAXAPOS_JWT=...
PAXAPOS_VERIFY_SSL=true
PAXAPOS_PROVEEDORES_ENDPOINT=account/proveedores.json
PAXAPOS_PROVEEDORES_UPDATE_ENDPOINT=account/proveedores/edit/{id}.json
```

Contrato actual del gateway:

- `PAXAPOS_URL`: dominio base del portal de proveedores.
- `PAXAPOS_TENANT`: tenant enviado en header `X-Tenant-Id` y usado en paths del migrator RAFAM.
- `PAXAPOS_JWT`: token JWT enviado como `Authorization: Bearer ...` para endpoints directos.
- `PAXAPOS_VERIFY_SSL`: `false` solo para desarrollo con certificados no confiables.
- `PAXAPOS_PROVEEDORES_ENDPOINT`: path del endpoint JSON directo.
- `PAXAPOS_PROVEEDORES_UPDATE_ENDPOINT`: path para update cuando se usa `--force-update` (`{id}` = id remoto).

Modo de operacion (gateway):

- Default (`--force-update` ausente): create-only. Si ya existe vinculacion local, se saltea.
- Con `--force-update`: si existe vinculacion local RAFAM->Paxapos, se envia update al endpoint de edicion.

## RAFAM Migrator API

El modo `migrator` es el importador batch RAFAM que vive dentro del mismo Paxapos/Portal configurado por `PAXAPOS_URL` y `PAXAPOS_TENANT`. Por eso sus rutas se configuran como paths relativos `PAXAPOS_RAFAM_*_PATH`, no como otra URL base.

Para usar el importador batch oficial de Paxapos en vez del endpoint directo de proveedores:

```dotenv
PAXAPOS_URL=https://proveedores.madariaga.gob.ar
PAXAPOS_TENANT=madariaga
PAXAPOS_API_KEY=...
PAXAPOS_VERIFY_SSL=true
PAXAPOS_TIMEOUT_SECONDS=20
PAXAPOS_RAFAM_IMPORT_PATH=rafam/migracion/importar.json
PAXAPOS_RAFAM_SPEC_PATH=rafam/migracion/spec.json
PAXAPOS_RAFAM_LOOKUPS_PATH=rafam/migracion/lookups.json
```

Uso estandar actualizado:

- URL formada como `{PAXAPOS_URL}/{PAXAPOS_TENANT}/{PAXAPOS_RAFAM_*_PATH}`.
- Ejemplo producción: `https://proveedores.madariaga.gob.ar/madariaga/rafam/migracion/spec.json`.
- Ejemplo desarrollo: `https://dev.paxapos.com/prueba/rafam/migracion/spec.json`.
- `PAXAPOS_RAFAM_*_PATH` siempre debe ser un path relativo, nunca una URL completa.
- `PAXAPOS_URL` no incluye tenant; `PAXAPOS_TENANT` se usa en la URL y también en el header `X-Tenant-Id`.

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
- Soporta `jurisdicciones` como `centros_costo` + `rubros` + `clasificaciones`, y guarda los IDs remotos en SQLite para resolver FKs.
- Soporta `ped_items` (genera bloque `pedidos` con items para migrator).
- Soporta `oc_items` (genera bloque `ordenes_compra` con items para migrator).
- Soporta `solic_gastos` (genera bloque `gastos` — facturas del proveedor).
- Soporta `orden_pago` (genera bloque `ordenes_pago` — vinculadas a gastos vía `gasto_ids` y fallback `gasto_external_ids`).
- Si existen tablas RAFAM `RETENCIONES`/`DEDUCCIONES`, agrega retenciones al payload de `ordenes_pago`.
- Envía payload batch al endpoint `/rafam/migracion/importar.json`.
- Si Paxapos devuelve errores parciales (`errors` o `stats.*.error > 0`), la corrida falla y no avanza checkpoint.
- Las opciones batch del migrator activan `auto_create_mercaderia=true` y desactivan el cálculo/notificación automática de retenciones/pagos.
- `--dry-run` manda `dry_run=true` y no avanza checkpoints.
- En modo real, persiste el vínculo RAFAM -> Paxapos usando `results.proveedores[].id`.

Catálogos remotos del migrator:

- `make migrator-lookups`
- `.venv/bin/python main.py lookups`
- `.venv/bin/python main.py lookups --only mercaderias,unidades_de_medida,tipos_factura,tipos_de_pago,proveedores,gastos`

Notas de mapeo `ped_items` -> `pedidos` y `oc_items` -> `ordenes_compra`:

- `mercaderia_external_ref`: se envía referencia determinística RAFAM para resolución server-side en migrator.
- `unidad_de_medida_id`: primero busca override local `link_unidad_medida` por `UNI_MED` RAFAM; luego match por `name` normalizado de `unidades_de_medida`; fallback `PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID`, luego lookup `Unidad`, y finalmente `7`.
- `centro_costo_id`: se resuelve desde `link_centro_costo` generado al importar `jurisdicciones`.
- Si un item no puede construir referencia externa mínima, se omite y se informa en logs.
- El matching textual de mercaderías ya no es responsabilidad del script Python.

Notas de mapeo `solic_gastos` -> `gastos`:

- `external_id`: `{ejercicio, deleg_solic, nro_solic}` según spec beta; el link store conserva también el alias legacy `SG-{ejercicio}-{deleg_solic}-{nro_solic}`.
- `tipo_factura_id`: match por `codename` o `name` de `tipos_factura`; fallback `PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID`.
- Excluye solicitudes con `ESTADO_SOLIC=A` (anuladas).
- `factura_nro`: formateado a 8 dígitos (zfill) desde `NRO_DOC` de RAFAM.

Notas de mapeo `orden_pago` -> `ordenes_pago`:

- `gasto_ids`: IDs internos de Paxapos resueltos desde `link_gasto`.
- `gasto_external_ids`: referencia estructurada `{ejercicio, deleg_solic, nro_solic}` que el migrator puede resolver como fallback.
- `retenciones`: si el origen tiene `RETENCIONES`, se mapean por `COD_RET`/`IMPORTE`; el tipo se resuelve desde `link_tipo_retencion`, lookup `tipos_retencion`, o alias (`ganancias`, `iva`, `iibb`, `suss`).
- Requiere que los gastos (solic_gastos) estén importados previamente.
- `identificador_pago`: formato `RAFAM-OP-{ejercicio}-{nro_op}` para upsert.
- `fecha`: solo se envía si `ESTADO_OP=C` (confirmada/pagada).
- Excluye OPs con `ESTADO_OP=A` (anuladas).
- OPs sin gasto vinculado vía JOIN `NRO_CANCE=NRO_SOLIC` se omiten con warning.

Comportamiento por entorno:

- `APP_ENV=dev`: si no definis `LOG_LEVEL`, usa `DEBUG`
- `APP_ENV=prod`: si no definis `LOG_LEVEL`, usa `INFO`
- `PAXAPOS_VERIFY_SSL=false`: desactiva validacion SSL del destino, util solo en desarrollo.
- `PAXAPOS_VERIFY_SSL=true`: requerido en produccion.

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

- En endpoints directos gateway, el tenant viaja por header `X-Tenant-Id`.
- En migrator RAFAM, el tenant viaja en la URL final y también por header `X-Tenant-Id`.
- `PAXAPOS_URL` nunca debe incluir el tenant; el tenant vive en `PAXAPOS_TENANT`.
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

## Checkpoints incrementales

Cada entidad guarda checkpoints en la SQLite configurada por `LOCAL_STATE_DB_PATH`:

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

1. Desarrollo diario: `RAFAM_SOURCE_BACKEND=sqlite` con snapshots CSV.
2. QA técnico: correr pruebas de integración con Oracle en contenedor.
3. Producción: `RAFAM_SOURCE_BACKEND=oracle` desde Debian con acceso a RAFAM real.

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

### 3. Variables de entorno para producción con importación Paxapos

```dotenv
APP_ENV=prod
LOG_LEVEL=INFO
RAFAM_SOURCE_BACKEND=oracle
RAFAM_SOURCE_HOST=ip.del.servidor.rafam
RAFAM_SOURCE_PORT=1521
RAFAM_SOURCE_SERVICE=BDRAFAM
RAFAM_SOURCE_USER=usuario_lectura
RAFAM_SOURCE_PASSWORD=secreto

LOCAL_STATE_DB_PATH=state/checkpoint.db

PAXAPOS_URL=https://proveedores.madariaga.gob.ar
PAXAPOS_TENANT=madariaga
PAXAPOS_API_KEY=api_key_real
PAXAPOS_VERIFY_SSL=true
PAXAPOS_TIMEOUT_SECONDS=30
PAXAPOS_RAFAM_IMPORT_PATH=rafam/migracion/importar.json
PAXAPOS_RAFAM_SPEC_PATH=rafam/migracion/spec.json
PAXAPOS_RAFAM_LOOKUPS_PATH=rafam/migracion/lookups.json
PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID=1
PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID=
PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID=1
RAFAM_SYNC_BATCH_DELAY_SECONDS=2
```

Para producción RAFAM-only que solo genera CSVs, el bloque `PAXAPOS_*` no es necesario.
Antes de una importación real, confirmar `PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID` con `make migrator-lookups`, porque los IDs de catálogos pueden variar por tenant.

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