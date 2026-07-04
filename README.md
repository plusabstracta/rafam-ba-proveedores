# RAFAM BA Proveedores Sync

Sincronizador incremental de RAFAM (Oracle) hacia Paxapos. El script lee RAFAM en modo
solo lectura, transforma los datos al contrato del portal de proveedores y los envia al
migrator RAFAM de Paxapos, manteniendo checkpoints y vinculos RAFAM -> Paxapos en una
SQLite local.

Este README cubre el uso diario para desarrollo y el procedimiento recomendado para ejecutar
en produccion.

## Documentacion canonica

- [docs/rafam_paxapos_equivalencias.md](docs/rafam_paxapos_equivalencias.md): fuente de verdad de tablas RAFAM, mapeos y contrato Paxapos.
- [docs/deployment.md](docs/deployment.md): guia extendida de instalacion y operacion.
- [docs/rafam_der.drawio](docs/rafam_der.drawio): DER grafico del flujo RAFAM.

## Que hace el script

Flujo principal:

```text
Oracle RAFAM / snapshot SQLite
        -> main.py + SQLAlchemy
        -> SQLite local de estado
        -> Paxapos CakePHP 2 migrator API
```

Principios operativos:

- Oracle RAFAM es solo lectura. El script nunca escribe en RAFAM.
- Los checkpoints se guardan en `LOCAL_STATE_DB_PATH`.
- Si una corrida falla, no avanza checkpoint; la siguiente reintenta desde el ultimo lote exitoso.
- `--dry-run` no avanza checkpoints.
- El modo migrator usa lock local (`state/migrator.lock`) para evitar corridas concurrentes.

## Entidades y orden real de migracion

El contrato funcional migra estas tablas RAFAM: `PROVEEDORES`, `ORDEN_COMPRA`, `OC_ITEMS`,
`SOLIC_GASTOS`, `CTA_COMPROB`, `ORDEN_PAGO` y `ORDEN_PAGO_DEDUC`.

El migrator se ejecuta en 5 entidades independientes (1 comando = 1 checkpoint), en orden de
dependencia (FK):

| Paso | Entidad CLI | Comando | Payload Paxapos | Notas |
| --- | --- | --- | --- | --- |
| 1 | `proveedores` | `make migrate-proveedores` | `proveedores[]` | Crea/actualiza proveedores. |
| 2 | `oc_items` | `make migrate-oc` | `ordenes_compra[]` | Arma cabecera de OC + items embebidos. |
| 3 | `solic_gastos` | `make migrate-facturas` | `gastos[]` | Crea gastos desde `SOLIC_GASTOS` + `CTA_COMPROB` (via `REG_COMP`), resolviendo `pedido_id` contra OCs migradas. |
| 4 | `orden_pago` | `make migrate-op` | `ordenes_pago[]` + `gastos[]` + retenciones | Crea egresos, vincula gastos y embebe retenciones (`ORDEN_PAGO_DEDUC`). |
| 5 | `retenciones` | `make migrate-retenciones` | `retenciones[]` | Reenvia retenciones (`ORDEN_PAGO_DEDUC`, 1:1 por `NRO_OP`) de OPs ya migradas. |

La entidad `orden_compra` fue eliminada: queda reemplazada por `oc_items`, que manda la OC
completa con items. Las retenciones provienen de `ORDEN_PAGO_DEDUC` (no de la tabla `RETENCIONES`).
Ver [docs/rafam_paxapos_equivalencias.md](docs/rafam_paxapos_equivalencias.md).

## Requisitos

- Python 3.11 o superior.
- `make`.
- Acceso a Oracle RAFAM para produccion o para exportar snapshots.
- Oracle Instant Client cuando el servidor Oracle lo requiera.
- Acceso HTTP al portal Paxapos destino para migrator.

El proyecto no usa `requests` ni `httpx`; las llamadas HTTP salen por `urllib`.

## Setup inicial

Desde la carpeta del proyecto:

```bash
cd rafam-ba-proveedores
make setup
```

Eso crea `.venv`, instala `requirements.txt` y copia `.env.example` a `.env` si no existe.

Si preferis hacerlo manualmente:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Usamos `.venv/bin/python` en los comandos para evitar problemas con Python de sistema.

## Desarrollo local con snapshots SQLite

Este modo permite trabajar sin acceso al Oracle productivo. Usa CSVs exportados previamente y
los carga en `state/dev_rafam.db`.

### 1. Configurar `.env` para desarrollo offline

```dotenv
APP_ENV=dev
LOG_LEVEL=DEBUG

RAFAM_SOURCE_BACKEND=sqlite
RAFAM_SOURCE_SQLITE_DB_PATH=state/dev_rafam.db

LOCAL_STATE_DB_PATH=state/checkpoint.db

# Solo completar si vas a probar el migrator contra Paxapos.
PAXAPOS_URL=
PAXAPOS_TENANT=
PAXAPOS_API_KEY=
PAXAPOS_VERIFY_SSL=true
PAXAPOS_TIMEOUT_SECONDS=20
PAXAPOS_RAFAM_IMPORT_PATH=rafam/migracion/importar.json
PAXAPOS_RAFAM_SPEC_PATH=rafam/migracion/spec.json
PAXAPOS_RAFAM_LOOKUPS_PATH=rafam/migracion/lookups.json
PAXAPOS_RAFAM_RESOLVER_MERCADERIA_PATH=rafam/migracion/resolver_mercaderia.json
PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID=1
PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID=
PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID=1
RAFAM_SYNC_BATCH_DELAY_SECONDS=0
RAFAM_EJERCICIO_MIN=2026
```

Si solo vas a cargar snapshots o ver el estado con `make status`, no hace falta completar
`PAXAPOS_*`. El migrator (incluso en `--dry-run`) valida contra Paxapos, asi que requiere
`PAXAPOS_URL`, `PAXAPOS_TENANT` y `PAXAPOS_API_KEY`.

### 2. Cargar CSVs a SQLite

Con los snapshots incluidos o generados en `output/rafam_ultimos_3_meses`:

```bash
make load-dev CSV_DIR=output/rafam_ultimos_3_meses DEV_DB=state/dev_rafam.db
```

El loader toma el CSV mas reciente de cada entidad, normaliza columnas de joins y crea una vista
`CTA_HOJA_DE_RUTA` derivada cuando hace falta.

### 3. Inspeccionar estado y resetear

Ver checkpoints y pendientes (no toca Oracle ni Paxapos):

```bash
.venv/bin/python main.py status
```

Resetear estado local:

```bash
make reset-all
```

Para validar queries y el payload completo sin escribir en Paxapos, usar el dry-run del migrator
(ver paso 4): envia `dry_run=true` y Paxapos valida sin persistir.

### 4. Probar migrator en desarrollo

Completar `PAXAPOS_URL`, `PAXAPOS_TENANT` y `PAXAPOS_API_KEY` en `.env` y validar el destino:

```bash
make migrator-spec
make migrator-lookups
```

Dry-run completo con volumen limitado:

```bash
make migrate-all-dry LIMIT=20 BATCH=20
```

Dry-run por paso:

```bash
make migrate-proveedores-dry LIMIT=20 BATCH=20
make migrate-oc-dry          LIMIT=20 BATCH=20
make migrate-facturas-dry    LIMIT=20 BATCH=20
make migrate-op-dry          LIMIT=20 BATCH=20
make migrate-retenciones-dry LIMIT=20 BATCH=20
```

Recordatorio: `--dry-run` envia `dry_run=true` al migrator y no avanza checkpoints.

### 5. Tests

```bash
make test
```

Los tests corren contra SQLite/mocks y no requieren Oracle.

## Exportar snapshots desde RAFAM

Perfil RAFAM-only: sirve para el operador que tiene acceso a Oracle y solo necesita generar CSVs.
No requiere variables `PAXAPOS_*`.

`.env` minimo:

```dotenv
APP_ENV=prod
LOG_LEVEL=INFO

RAFAM_SOURCE_BACKEND=oracle
RAFAM_SOURCE_HOST=<ip-servidor-rafam>
RAFAM_SOURCE_PORT=1521
RAFAM_SOURCE_SERVICE=BDRAFAM
RAFAM_SOURCE_USER=<usuario-solo-lectura>
RAFAM_SOURCE_PASSWORD=<password>

# Opcional si hace falta thick mode / Instant Client.
ORACLE_CLIENT_DIR=/opt/oracle/instantclient
```

Exportar ultimos 3 meses:

```bash
.venv/bin/python scripts/export_last_3_months.py
```

Exportar otro rango o tablas puntuales:

```bash
.venv/bin/python scripts/export_last_3_months.py --months 6
.venv/bin/python scripts/export_last_3_months.py --months 6 --tables PROVEEDORES,ORDEN_PAGO,ORDEN_PAGO_DEDUC
```

Los CSV quedan en `output/rafam_ultimos_3_meses/` por defecto.

## Produccion con Paxapos migrator

Este es el modo recomendado para importar datos reales hacia el portal de proveedores.

### 1. Preparar `.env` productivo

```dotenv
APP_ENV=prod
LOG_LEVEL=INFO

RAFAM_SOURCE_BACKEND=oracle
RAFAM_SOURCE_HOST=<ip-servidor-rafam>
RAFAM_SOURCE_PORT=1521
RAFAM_SOURCE_SERVICE=BDRAFAM
RAFAM_SOURCE_USER=<usuario-solo-lectura>
RAFAM_SOURCE_PASSWORD=<password>
ORACLE_CLIENT_DIR=/opt/oracle/instantclient

LOCAL_STATE_DB_PATH=state/checkpoint.db

PAXAPOS_URL=https://proveedores.madariaga.gob.ar
PAXAPOS_TENANT=madariaga
PAXAPOS_API_KEY=<api-key-real>
PAXAPOS_VERIFY_SSL=true
PAXAPOS_TIMEOUT_SECONDS=30

PAXAPOS_RAFAM_IMPORT_PATH=rafam/migracion/importar.json
PAXAPOS_RAFAM_SPEC_PATH=rafam/migracion/spec.json
PAXAPOS_RAFAM_LOOKUPS_PATH=rafam/migracion/lookups.json
PAXAPOS_RAFAM_RESOLVER_MERCADERIA_PATH=rafam/migracion/resolver_mercaderia.json

# Confirmar IDs con make migrator-lookups antes de importar.
PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID=1
PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID=
PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID=1

RAFAM_SYNC_BATCH_DELAY_SECONDS=2
RAFAM_EJERCICIO_MIN=2026
```

Notas importantes:

- `PAXAPOS_URL` no incluye tenant.
- Las URLs migrator se arman como `{PAXAPOS_URL}/{PAXAPOS_TENANT}/{PAXAPOS_RAFAM_*_PATH}`.
- El tenant tambien viaja en header `X-Tenant-Id`.
- Para scripts productivos se recomienda `PAXAPOS_API_KEY`.
- `PAXAPOS_VERIFY_SSL=false` solo debe usarse en desarrollo.
- `RAFAM_EJERCICIO_MIN` no filtra proveedores; aplica a `oc_items`, `orden_pago` y `retenciones`. Si una OP confirmada dentro del alcance actual (`EJERCICIO >= mínimo` o `FECH_CONFIRM` desde el 1/1 del mínimo) requiere una OC anterior, esa OC se incluye igual para no crear pagos o gastos sueltos. Las OPs históricas fuera de ese alcance no arrastran OCs viejas.

### 2. Validacion previa obligatoria

Antes de escribir datos reales:

```bash
make migrator-spec
make migrator-lookups
make status
```

Confirmar en `migrator-lookups` los IDs default de unidad, tipo de factura, tipo de pago y, si se usará fallback, mercadería.

Luego correr dry-run con volumen acotado:

```bash
make migrate-all-dry LIMIT=100 BATCH=100
```

Si falla el dry-run, corregir mapeos/configuracion antes de avanzar.

### 3. Primera importacion real

Ejecutar en orden estricto:

```bash
make migrate-proveedores BATCH=500
make migrate-oc          BATCH=500
make migrate-facturas    BATCH=500
make migrate-op          BATCH=500
make migrate-retenciones BATCH=500
```

Atajo equivalente:

```bash
make migrate-all BATCH=500
```

En modo real, cada paso avanza checkpoint solo si el lote termina sin errores parciales del
migrator.

### 4. Corridas incrementales

Para una corrida completa incremental:

```bash
.venv/bin/python main.py run --batch-size 500
```

Ese comando, sin `--entity`, ejecuta las 5 entidades oficiales del migrator en orden de
dependencia: `proveedores`, `oc_items`, `solic_gastos`, `orden_pago`, `retenciones`.

Tambien se puede usar:

```bash
make migrate-all BATCH=500
```

### 5. Crontab Debian sin sudo para las 5 entidades oficiales

Si no hay acceso `sudo` al servidor, configurar el cron del usuario que tiene el proyecto y la
`.env` productiva. El ejemplo usa `flock` para evitar corridas superpuestas si una importacion
tarda mas que el intervalo.

Preparar carpetas una vez, desde el usuario que ejecuta el migrator:

```bash
cd /home/rafam/rafam-ba-proveedores
mkdir -p logs state
```

Reemplazar `/home/rafam/rafam-ba-proveedores` por la ruta real del proyecto en el servidor.

Editar el crontab del usuario:

```bash
crontab -e
```

Agregar:

```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
MAILTO=""

RAFAM_DIR=/home/rafam/rafam-ba-proveedores

# Pipeline oficial cada 15 minutos.
# Cada entidad corre independiente: si una falla, las otras siguen.
# Logs rotativos por mes en logs/rafam-{entidad}-YYYY-MM.log (gestionado por main.py).
# flock con lock separado por entidad evita corridas superpuestas.

# 1) PROVEEDORES -> account_proveedores
*/15 * * * * cd "$RAFAM_DIR" && /usr/bin/flock -n state/prov.lock .venv/bin/python main.py run --entity proveedores --batch-size 500

# 2) ORDEN_COMPRA + OC_ITEMS -> compras_pedidos + items
*/15 * * * * cd "$RAFAM_DIR" && /usr/bin/flock -n state/oc.lock .venv/bin/python main.py run --entity oc_items --batch-size 500

# 3) SOLIC_GASTOS + CTA_COMPROB -> account_gastos
*/15 * * * * cd "$RAFAM_DIR" && /usr/bin/flock -n state/sg.lock .venv/bin/python main.py run --entity solic_gastos --batch-size 500

# 4) ORDEN_PAGO + CTA_COMPROB + ORDEN_PAGO_DEDUC -> egresos + gastos + retenciones
*/15 * * * * cd "$RAFAM_DIR" && /usr/bin/flock -n state/op.lock .venv/bin/python main.py run --entity orden_pago --batch-size 500

# 5) ORDEN_PAGO_DEDUC -> account_retenciones (reenvio idempotente)
*/15 * * * * cd "$RAFAM_DIR" && /usr/bin/flock -n state/ret.lock .venv/bin/python main.py run --entity retenciones --batch-size 500
```

Notas sobre el crontab:

- No hace falta redirigir stdout/stderr con `>>`: `main.py` escribe automaticamente a
  `logs/rafam-{entidad}-YYYY-MM.log` (rotacion mensual). Se puede cambiar la carpeta con
  la variable de entorno `RAFAM_LOG_DIR`.
- Cada entidad tiene su propio lock (`prov.lock`, `oc.lock`, `sg.lock`, `op.lock`, `ret.lock`).
  Si una tarda mas de 15 minutos, `flock -n` salta esa entidad sin bloquear las otras.
- Si una entidad falla (ej: CUIT invalido en proveedores), las demas siguen corriendo.

Verificar que quedo instalado:

```bash
crontab -l
```

Ver logs en vivo (reemplazar `YYYY-MM` por el mes actual):

```bash
tail -f logs/rafam-proveedores-2026-05.log
tail -f logs/rafam-oc_items-2026-05.log
tail -f logs/rafam-solic_gastos-2026-05.log
tail -f logs/rafam-orden_pago-2026-05.log
tail -f logs/rafam-retenciones-2026-05.log
```

Para probar exactamente lo que ejecuta cron antes de dejarlo activo:

```bash
cd /home/rafam/rafam-ba-proveedores
.venv/bin/python main.py run --entity proveedores --batch-size 500 --dry-run
.venv/bin/python main.py run --entity oc_items --batch-size 500 --dry-run
.venv/bin/python main.py run --entity solic_gastos --batch-size 500 --dry-run
.venv/bin/python main.py run --entity orden_pago --batch-size 500 --dry-run
.venv/bin/python main.py run --entity retenciones --batch-size 500 --dry-run
```

### 6. Verificacion post-importacion

```bash
make status
```

Revisar tambien los logs del portal Paxapos si el migrator devuelve errores parciales.

## Recuperacion y re-ejecucion

Si una corrida falla:

1. El checkpoint de la entidad queda en error o sin avanzar.
2. Corregir la causa en datos/configuracion/mapeo.
3. Ejecutar nuevamente el mismo comando.

Para forzar recarga completa de una entidad:

```bash
make reset-proveedores
make migrate-proveedores BATCH=500
```

Para reiniciar todo el pipeline:

```bash
make reset-all
make migrate-all BATCH=500
```

`reset` borra tambien vinculos locales RAFAM -> Paxapos para la entidad afectada. Usarlo con cuidado en produccion.

## Detección de Cambios y Sincronización de Modificaciones (Updates)

Para mantener actualizados los registros que sufren modificaciones en RAFAM (por ejemplo, cambios de razón social, CUIT, importes o ítems de órdenes de compra), se implementó un subcomando `sync-changes` que utiliza detección de cambios basada en un hash SHA-256 determinista del payload.

### Entidades soportadas
* **Proveedores** (`proveedores`)
* **Órdenes de compra** (`oc_items` / `orden_compra`)

*Nota: Por diseño del sistema, no se procesan eliminaciones o bajas (deletes). Solo se detectan y sincronizan actualizaciones/ediciones (updates).*

### Funcionamiento básico
1. El script lee todos los vínculos guardados localmente en `state/checkpoint.db`.
2. Realiza consultas rápidas a RAFAM utilizando únicamente las claves de los registros vinculados.
3. Mapea el registro actual y calcula el hash de su payload normalizado.
4. Si el hash local no coincide (o es nulo), detecta que hubo un cambio, re-envía el payload al migrator de Paxapos (con `upsert=true`) y actualiza el hash local.

### Ejecución manual (Makefile)
Se dispone de los siguientes targets simplificados:
```bash
# Detectar y re-enviar proveedores modificados
make sync-proveedores

# Detectar y re-enviar órdenes de compra modificadas
make sync-oc

# Sincronizar ambas entidades
make sync-all
```

#### Opciones útiles:
* **Previsualización (Dry Run):** Muestra cuántos registros se hubieran enviado sin despachar las peticiones reales ni alterar la base de datos local:
  ```bash
  make sync-all DRY=1
  ```
* **Inicialización de hashes (Backfill):** Útil para la primera ejecución en un entorno donde ya se hayan migrado registros. Calcula y guarda los hashes de los registros ya vinculados en la SQLite local sin enviar peticiones HTTP a Paxapos:
  ```bash
  make sync-all BACKFILL=1
  ```

### Crontab para ejecución periódica semanal
Se recomienda integrar esta sincronización una vez por semana (por ejemplo, el domingo a la madrugada) para no sobrecargar los servidores durante días hábiles.

Editar el crontab del usuario:
```bash
crontab -e
```

Y agregar las siguientes líneas:
```cron
# Detección de cambios y sincronización semanal (Todos los domingos a las 03:00 y 04:00 AM)
0 3 * * 0 cd "$RAFAM_DIR" && /usr/bin/flock -n state/sync_changes_prov.lock .venv/bin/python main.py sync-changes --entity proveedores --export migrator
0 4 * * 0 cd "$RAFAM_DIR" && /usr/bin/flock -n state/sync_changes_oc.lock .venv/bin/python main.py sync-changes --entity oc_items --export migrator
```

## Modo gateway directo legacy

El exporter `gateway` existe para proveedores y usa endpoints JSON directos de Paxapos. Es util para
mantenimiento puntual, pero el flujo productivo recomendado es `--export migrator`.

Variables necesarias:

```dotenv
PAXAPOS_URL=https://proveedores.madariaga.gob.ar
PAXAPOS_TENANT=madariaga
PAXAPOS_JWT=<jwt>
PAXAPOS_PROVEEDORES_ENDPOINT=account/proveedores.json
PAXAPOS_PROVEEDORES_UPDATE_ENDPOINT=account/proveedores/edit/{id}.json
```

Crear solo proveedores nuevos:

```bash
.venv/bin/python main.py run --entity proveedores --export gateway
```

Actualizar proveedores ya vinculados localmente:

```bash
.venv/bin/python main.py run --entity proveedores --export gateway --force-update
```

## Referencia rapida de comandos

| Comando | Uso |
| --- | --- |
| `make setup` | Crea `.venv`, instala dependencias y crea `.env` si no existe. |
| `make load-dev CSV_DIR=...` | Carga CSVs a `state/dev_rafam.db`. |
| `make status` | Muestra checkpoints. |
| `make migrate-proveedores` | Migra proveedores. |
| `make migrate-oc` | Migra OCs con items. |
| `make migrate-facturas` | Migra gastos (`solic_gastos`). |
| `make migrate-op` | Migra ordenes de pago. |
| `make migrate-retenciones` | Migra retenciones. |
| `make migrator-spec` | Consulta contrato remoto del migrator. |
| `make migrator-lookups` | Consulta catalogos remotos. |
| `make migrate-proveedores-dry` | Dry-run de proveedores. |
| `make migrate-oc-dry` | Dry-run de OCs. |
| `make migrate-facturas-dry` | Dry-run de gastos (`solic_gastos`). |
| `make migrate-op-dry` | Dry-run de OPs. |
| `make migrate-retenciones-dry` | Dry-run de retenciones. |
| `make migrate-all-dry` | Dry-run del pipeline oficial completo. |
| `make migrate-all` | Import real del pipeline oficial completo. |
| `make reset-all` | Resetea checkpoints y links locales. |
| `make sync-proveedores` | Detecta y re-envía proveedores modificados en RAFAM. |
| `make sync-oc` | Detecta y re-envía OCs modificadas en RAFAM. |
| `make sync-all` | Ejecuta la detección de cambios para proveedores y OCs. |
| `make test` | Corre pytest. |

Variables Make utiles:

```bash
BATCH=500 LIMIT=100 CSV_DIR=output/rafam_ultimos_3_meses DEV_DB=state/dev_rafam.db
```

## Archivos generados

| Ruta | Descripcion |
| --- | --- |
| `state/dev_rafam.db` | Snapshot SQLite de RAFAM para desarrollo. |
| `state/checkpoint.db` | Checkpoints y vinculos RAFAM -> Paxapos. |
| `state/migrator.lock` | Lock de corridas concurrentes (migrator). |
| `state/prov.lock`, `oc.lock`, `sg.lock`, `op.lock`, `ret.lock` | Locks de cron por entidad. |
| `output/rafam_ultimos_3_meses/*.csv` | Snapshots de RAFAM (fuente para dev offline). |
| `logs/rafam-{entidad}-YYYY-MM.log` | Logs rotativos mensuales por entidad (auto-generados). |

No commitear `.env`, `state/*.db`, logs ni CSVs productivos.

## Problemas comunes

| Sintoma | Causa probable | Accion |
| --- | --- | --- |
| `Faltan RAFAM_SOURCE_USER/RAFAM_SOURCE_PASSWORD` | `.env` incompleto para Oracle. | Completar credenciales o usar `RAFAM_SOURCE_BACKEND=sqlite`. |
| `DPI-1047` | Oracle Instant Client no encontrado. | Configurar `ORACLE_CLIENT_DIR` o instalar Instant Client. |
| `ORA-12170` | Sin red/VPN hacia Oracle. | Verificar conectividad al host RAFAM. |
| `ORA-01017` | Usuario/password Oracle incorrectos. | Revisar credenciales con DBA. |
| `Respuesta no JSON` o redirect a login | Auth Paxapos incorrecta o endpoint equivocado. | Validar `PAXAPOS_API_KEY`, tenant y paths. |
| Checkpoint no avanza | Hubo error en el lote. | Leer logs, corregir y reejecutar. |
| Lock activo / exit 75 | Ya hay un `main.py run` corriendo. | Esperar a que termine; si quedo stale, verificar procesos antes de borrar `state/migrator.lock`. |

## Seguridad operativa

- No subir `.env` ni logs con credenciales.
- No pegar salidas de comandos que expandan variables sensibles.
- En produccion usar `PAXAPOS_VERIFY_SSL=true`.
- El usuario Oracle debe tener permisos `SELECT` solamente sobre las tablas RAFAM necesarias.
