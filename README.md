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

El migrator se ejecuta en 6 entidades independientes (1 comando = 1 checkpoint), en orden de
dependencia (FK):

| Paso | Entidad CLI | Comando | Payload Paxapos | Notas |
| --- | --- | --- | --- | --- |
| 1 | `clasificaciones` | `make migrate-clasificaciones` | `clasificaciones[]` | Consulta directamente `GASTOS` sin filtro temporal, arma el arbol por `INCISO`, `PAR_PRIN`, `PAR_PARC`, `PAR_SUBP` y guarda localmente cada codigo RAFAM vinculado al ID devuelto por Paxapos. No modifica el schema de Paxapos. |
| 2 | `proveedores` | `make migrate-proveedores` | `proveedores[]` | Crea/actualiza proveedores. |
| 3 | `oc_items` | `make migrate-oc` | `ordenes_compra[]` | Arma cabecera de OC + items embebidos. |
| 4 | `solic_gastos` | `make migrate-facturas` | `gastos[]` | Enriquecimiento UPDATE-ONLY: completa campos vacios de gastos que Paxapos ya creo (via `resolver_gasto`), desde `SOLIC_GASTOS` + `CTA_COMPROB` (via `REG_COMP`), resolviendo `pedido_id` contra OCs migradas. No crea gastos sueltos. |
| 5 | `orden_pago` | `make migrate-op` | `ordenes_pago[]` + `gastos[]` + retenciones | Crea egresos, vincula gastos y embebe retenciones (`ORDEN_PAGO_DEDUC`). Los pagos de gasto directo (factura real sin OC) se envian sin `pedido_id` cuando `RAFAM_MIGRAR_OP_SIN_OC=true` (default). |
| 6 | `retenciones` | `make migrate-retenciones` | `retenciones[]` | Reenvia retenciones (`ORDEN_PAGO_DEDUC`, 1:1 por `NRO_OP`) de OPs ya migradas. |

La entidad `orden_compra` quedo fuera del pipeline por defecto (el exporter la trata como
deshabilitada: warning + no-op): la reemplaza `oc_items`, que manda la OC completa con items.
Las retenciones provienen de `ORDEN_PAGO_DEDUC` (no de la tabla `RETENCIONES`).
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
PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID=
PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID=10
RAFAM_SYNC_BATCH_DELAY_SECONDS=0
RAFAM_OC_MAX_BATCH_ROWS=100
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

El loader toma el CSV mas reciente de cada entidad y normaliza columnas de joins.

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
PAXAPOS_TIMEOUT_SECONDS=120

PAXAPOS_RAFAM_IMPORT_PATH=rafam/migracion/importar.json
PAXAPOS_RAFAM_SPEC_PATH=rafam/migracion/spec.json
PAXAPOS_RAFAM_LOOKUPS_PATH=rafam/migracion/lookups.json
PAXAPOS_RAFAM_RESOLVER_MERCADERIA_PATH=rafam/migracion/resolver_mercaderia.json

# Confirmar IDs con make migrator-lookups antes de importar.
PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID=
PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID=10

RAFAM_SYNC_BATCH_DELAY_SECONDS=2
RAFAM_OC_MAX_BATCH_ROWS=100
RAFAM_EJERCICIO_MIN=2026
```

Los `PAXAPOS_RAFAM_*_PATH` aceptan paths relativos o las URLs absolutas del spec nuevo:

```dotenv
PAXAPOS_RAFAM_SPEC_PATH=https://proveedores.madariaga.gob.ar/madariaga/rafam/migracion/spec.json
PAXAPOS_RAFAM_LOOKUPS_PATH=https://proveedores.madariaga.gob.ar/madariaga/rafam/migracion/lookups.json
PAXAPOS_RAFAM_IMPORT_PATH=https://proveedores.madariaga.gob.ar/madariaga/rafam/migracion/importar.json
PAXAPOS_RAFAM_RESOLVER_MERCADERIA_PATH=https://proveedores.madariaga.gob.ar/madariaga/rafam/migracion/resolver_mercaderia.json
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

`oc_items` limita cada request a `RAFAM_OC_MAX_BATCH_ROWS` filas fuente (100 por defecto),
aunque `BATCH` sea mayor. El agrupador nunca divide los items de una misma OC.

En modo real, cada paso avanza checkpoint solo si el lote termina sin errores parciales del
migrator.

### 4. Corridas incrementales

Para una corrida completa incremental:

```bash
.venv/bin/python main.py run --batch-size 500
```

Ese comando, sin `--entity`, ejecuta las 6 entidades oficiales del migrator en orden de
dependencia: `clasificaciones`, `proveedores`, `oc_items`, `solic_gastos`, `orden_pago`,
`retenciones`.

Tambien se puede usar:

```bash
make migrate-all BATCH=500
```

### 5. Crontab de produccion (pipeline cada 10 min + resumen diario por email)

Resumen rapido de operacion (produccion vs desarrollo, scripts con email y crons):
`docs/scripts_crons_resumen.md`

La forma recomendada es dejar que el instalador arme el crontab desde `cron.conf`:

```bash
make install-cron   # o: bash scripts/install_crons.sh
make show-cron
```

Esto instala solo 3 entradas para este proyecto:

1. Pipeline completo cada 10 minutos (todas las entidades en orden de FK, sin mail).
2. Resumen diario por email una vez al dia (un unico mail con el total del dia).
3. `check_integrity` diario.

Los horarios se editan en `cron.conf` (`PIPELINE_SCHEDULE`, `DAILY_REPORT_SCHEDULE`,
`INTEGRITY_SCHEDULE`). `make install-cron` es idempotente: borra las entradas previas de
este proyecto y las reinstala.

#### Equivalente manual (sin `make`)

Si preferis editar el crontab a mano, `crontab -e` y agregar:

```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
MAILTO=""

RAFAM_DIR=/home/rafam/rafam-ba-proveedores

# 1) Pipeline completo cada 10 min, en orden de FK, en un unico proceso:
#    proveedores -> oc_items -> solic_gastos -> orden_pago -> retenciones.
#    NO envia mail: registra cada corrida en state/run_history.jsonl.
*/10 * * * * cd "$RAFAM_DIR" && /usr/bin/flock -n state/locks/pipeline.lock .venv/bin/python main.py run --batch-size 500 >> logs/rafam-pipeline-cron.log 2>&1

# 2) Resumen diario por email (UN unico mail con el total del dia y, si hubo
#    errores, que entidad fallo y que devolvio el migrator). Purga lo reportado.
55 23 * * * cd "$RAFAM_DIR" && /usr/bin/flock -n state/locks/daily_report.lock .venv/bin/python main.py daily-report >> logs/daily_report.log 2>&1

# 3) Verificacion de integridad diaria.
0 2 * * * cd "$RAFAM_DIR" && /usr/bin/flock -n state/locks/integrity.lock .venv/bin/python scripts/check_integrity.py --apply >> logs/check_integrity.log 2>&1
```

Notas:

- El pipeline corre en un solo proceso: si una entidad falla, se registra y las demas
  siguen; la corrida no aborta salvo error de sistema (DB caida, etc.).
- El mail es diario, no por corrida. Requiere `NOTIFY_SMTP_*` y `NOTIFY_TO` en `.env`.
- `main.py` escribe logs rotativos por mes en `logs/`. La carpeta se puede cambiar con
  `RAFAM_LOG_DIR`.

Verificar que quedo instalado:

```bash
crontab -l
```

Para probar antes de dejarlo activo:

```bash
cd /home/rafam/rafam-ba-proveedores
.venv/bin/python main.py run --batch-size 500 --dry-run   # pipeline completo, sin escribir
.venv/bin/python main.py daily-report                     # arma y envia el resumen del dia
```


### 6. Verificacion post-importacion

```bash
make status
```

Revisar tambien los logs del portal Paxapos si el migrator devuelve errores parciales.

## Fiabilidad: cola de reintentos, reportes y backups

- **Cola de reintentos**: las filas salteadas por dependencia faltante o rechazadas por el
  receptor (207 por fila) se encolan en `retry_queue` y se **reinyectan en la query** de la
  proxima corrida para `proveedores`, `solic_gastos`, `orden_pago` y `retenciones`
  (`oc_items` y `clasificaciones` son full-scan y se auto-recuperan solos — con la unica
  excepcion de lo que ya paso a `permanent`, ver abajo). Las filas esperando una dependencia
  no "queman" intentos; las rechazadas pasan a `permanent` tras 10 intentos.
- **Invariante de checkpoint**: el watermark de una entidad NUNCA avanza sobre una fila que no
  quedo, o bien confirmada por Paxapos, o bien registrada en `retry_queue`. Un batch cuyo POST
  responde 200 pero trae un error de fila que el pipeline **no puede** encolar (external_id
  ausente/incompleto en la respuesta del migrator) se trata igual que un batch que lanzo
  excepcion: el checkpoint de esa entidad se congela por el resto de la corrida (ver
  `main.py::_sync_entity`, freeze de `advance_partial`) y el error crudo queda en el log a
  nivel `ERROR` para que se pueda diagnosticar. Sin esta garantia esa fila quedaria fuera de la
  cola Y detras del cursor: bloqueada para siempre, sin que ni el forzado manual (`--requeue`)
  pudiera encontrarla, porque nunca se guardo en ningun lado.
- **Cada encolado se loguea apenas ocurre** (`WARNING`, no solo al llegar a `permanent`), con
  el numero de negocio en texto plano — "OC 2026-3-1023", "OP 2026-1023", "Retencion de OP
  2026-1023", "Gasto/Solicitud 2026-5-1023", "Proveedor COD_PROV=1234" — ademas del
  `entity`/`external_id` crudos para poder filtrar por `grep` o pasarlos tal cual a
  `--external-id`.
- **Ver la cola COMPLETA (sin el tope del mail)**: `main.py retry-queue --entity X` (agregar
  `--status pending` o `--status permanent` para filtrar) lista TODAS las filas de esa entidad,
  con el label legible, motivo, detalle, intentos, estado, `first_seen`/`last_attempt` y el
  ultimo error completo del receptor. Sin `--entity` lista toda la cola de todas las entidades.
- **Reencolar lo `permanent`**: una fila `permanent` NO se reinyecta mas, asi que cuando el
  rechazo se arregla del lado de Paxapos hay que devolverla a la cola a mano con `--requeue`
  (opcionalmente con `--external-id` para acotar a una sola fila). Caso tipico: core#406 — el
  gate de `cantidad > 0` tiraba la OC entera por un renglon con cantidad 0; tras deployar el
  fix, `main.py retry-queue --entity oc_items --requeue` (la cola usa el nombre de la
  entidad del pipeline, `oc_items`, no la seccion `ordenes_compra` del migrator).
- **Forzar el reenvio YA (sin esperar al proximo cron)**:
  - Uno o varios registros puntuales, esten o no en la cola: `main.py resend` (ver
    [Reenviar registros puntuales](#reenviar-registros-puntuales-mainpy-resend)).
  - Todo lo `pending` de UNA entidad: `main.py retry-queue --entity orden_pago --send-now`.
    Manda SOLO las claves de la cola (no la entidad entera), no toca el checkpoint y muestra
    el resultado de cada una. Toma el lock exclusivo (`state/migrator.lock`).
  - Toda la cola `permanent` de UNA entidad: `main.py retry-queue --entity oc_items --requeue
    --send-now`.
  - Toda la cola `pending` de TODAS las entidades (lo mas comun despues de un fix en Paxapos):
    `main.py run` sin `--entity` — ya reinyecta automaticamente todo lo `pending` de cada
    entidad, sin esperar el cron. Para `permanent`, primero `main.py retry-queue --requeue`
    (sin `--entity` reencola TODAS las entidades) y despues `main.py run`.
- **Inspeccionar una fila exacta**: `main.py retry-queue --entity retenciones --external-id
  '{"ejercicio": 2026, "nro_op": 123}'` muestra causa, detalle estable, primer registro,
  ultimo intento y error completo.
- **Descartar un falso positivo confirmado**: usar exclusivamente un ID exacto y dejar una
  justificacion auditable:
  `main.py retry-queue --dismiss --entity retenciones --external-id
  '{"ejercicio": 2026, "nro_op": 123}' --note 'retencion historica fuera de alcance'`.
  El descarte no modifica checkpoints ni links. No usar `reset-*` para limpiar retries: esos
  comandos reinician estado de sincronizacion y pueden provocar reenvios masivos.
- **Mail diario**: la seccion "COLA DE REINTENTOS" muestra el estado real de la cola al
  inicio y fin del dia, agrupado por entidad, estado y causa, y ademas un **detalle
  individual** por entidad (los mas viejos primero, con label legible, motivo, intentos y
  error) acotado a `RAFAM_MAIL_RETRY_DETAIL_LIMIT` filas (default 50) para no volver
  inmanejable el mail con una cola grande; si hay mas, el mail lo dice explicitamente y
  apunta a `main.py retry-queue --entity X` para el resto. `CON ADVERTENCIAS` significa
  que solo quedan dependencias pendientes; `CON ERRORES` indica rechazos del backend,
  validaciones, filas `permanent` o fallas tecnicas.
- **Reconciliacion** (`main.py reconcile`): compara origen RAFAM vs. migrado vs. cola para
  `proveedores`, `ordenes_compra`, `ordenes_pago`, `gastos` (`SOLIC_GASTOS`) y `retenciones`
  (universo = OPs con al menos una fila en `ORDEN_PAGO_DEDUC`). `drift != 0` en cualquier fila
  es señal de perdida silenciosa a investigar — correrlo despues de un incidente grande de
  backend es la forma mas rapida de confirmar que nada quedo afuera de la cola.
- **Metricas del mail**: "Filas leidas de RAFAM" es trabajo del scanner, "Items enviados a
  Paxapos" es el payload real y "Altas nuevas" cuenta exclusivamente resultados
  `mode=create`. Actualizaciones, reemplazos, bajas y omitidos se informan por separado.
  Proveedores ya vinculados cuyo `payload_hash` no cambio no se vuelven a enviar, excepto si
  estan en la cola de reintentos.
- **OPs sin orden de compra** (`RAFAM_MIGRAR_OP_SIN_OC`, default `true`): los pagos de gasto
  directo — con factura imputada en `ORDEN_PAGO_IMPUT`/`CTA_COMPROB` pero sin OC en
  `REG_COMP` — se envian sin `pedido_id`; Paxapos deduplica el gasto por
  `proveedor + factura_nro`. Con `false` se migran solo pagos respaldados por OC.
- **Gastos con varios comprobantes**: las solicitudes de gasto con 2+ facturas se expanden
  en un enriquecimiento por comprobante (antes se omitian por completo).
- **Anulaciones**: `check_integrity` alerta por email cuando detecta registros anulados o
  eliminados en RAFAM ya migrados a Paxapos (el endpoint no soporta anular egresos: hay que
  corregirlos a mano en el portal).
- **Backups**: `check_integrity` deja un backup diario de `state/checkpoint.db` en
  `state/backups/` (retencion 7 dias) antes de operar.

## Reenviar registros puntuales (`main.py resend`)

Manda a Paxapos **solo** los registros indicados, en el momento, y muestra que paso con cada
uno. No lee ni escribe checkpoints: no hace falta resetear nada ni reenviar la entidad entera.

```bash
# Por clave (se puede repetir --key). Acepta la forma corta o el label tal cual sale en el mail.
python main.py resend --entity oc_items --key 2026-3-1023
python main.py resend --entity orden_pago --key "OP 2026-1023" --key "OP 2026-1024"
python main.py resend --entity retenciones --key "Retencion de OP 2026-1023"
python main.py resend --entity solic_gastos --key "Gasto/Solicitud 2026-1-58"
python main.py resend --entity proveedores --key 110

# Muchas claves: un archivo con una por linea ('#' = comentario).
python main.py resend --entity orden_pago --keys-file claves.txt

# Lo que esta en la cola de reintentos (pending por defecto; --status permanent|all).
python main.py resend --entity retenciones --from-queue --status all

# Una ventana de fechas (FECH_CONFIRM para OP/retenciones, FECH_SOLIC para gastos,
# FECH_OC para OCs, FECHA_ULT_COMP para proveedores). --hasta es inclusivo (default: hoy).
python main.py resend --entity orden_pago --desde 2026-09-01 --hasta 2026-09-15

# Siempre se puede probar antes: Paxapos valida pero no persiste, y la cola no se toca.
python main.py resend --entity oc_items --key 2026-3-1023 --dry-run
```

**Claves vs. ventana**:

- Con claves (`--key`, `--keys-file`, `--from-queue`) el reenvio **se fuerza** aunque el
  registro figure "sin cambios" en el link local o este `permanent` en la cola (en ese caso se
  reencola con 0 intentos antes de enviar). La query ignora cursor, ventana de 30 dias,
  `RAFAM_EJERCICIO_MIN` y `ESTADO_OP`, para que el registro llegue al mapper y el reporte diga
  el motivo real si no se puede enviar.
- Con `--desde/--hasta` se aplican las reglas normales del pipeline sobre esa ventana: solo
  se manda lo nuevo o lo que cambio. Sirve para "pasar de nuevo" un periodo sin riesgo de
  reenviar miles de registros identicos.
- Las reglas de negocio se respetan siempre: una OC anulada sin migrar, una OP no confirmada
  o un proveedor excluido no se envian aunque se pidan por clave.

**Resultado por registro**:

| Resultado | Significado |
| --- | --- |
| `OK` | Paxapos lo acepto (muestra modo e id de Paxapos). |
| `RECHAZADO` | Paxapos lo rechazo; muestra el error con `validationErrors`. Queda en la cola. |
| `OMITIDO` | El script no lo envio y dice por que, con el comando a correr primero si falta una dependencia (ej. `resend --entity proveedores --key 2595`). |
| `NO EXISTE EN RAFAM` | No hay filas con esa clave en el origen. |
| `FALLO EL ENVIO` | El request fallo (HTTP 500, etc.). Si el batch tenia varios registros, se reintentan de a uno para aislar el que rompe. |
| `NO ENVIADO` | El backend o la red estaban caidos y se corto el reenvio. |
| `NO APLICADO` | El id de Paxapos ya no existe (baja manual en destino). |
| `SIN CAMBIOS` | (solo ventana) ya migrado y sin cambios en RAFAM. |

Exit code: `0` si todo quedo OK, `1` si algun registro no (con `--from-queue` y en ventana,
`OMITIDO` no cuenta como fallo), `2` si los argumentos son invalidos y `75` si el cron siguio
corriendo despues de esperarlo 10 minutos (el comando espera el lock en vez de salir de una).

## Recuperacion y re-ejecucion

Si una corrida falla:

1. El checkpoint de la entidad queda en error o sin avanzar.
2. Corregir la causa en datos/configuracion/mapeo.
3. Ejecutar nuevamente el mismo comando.

Para reenviar uno o pocos registros no hace falta resetear: usar `main.py resend` (ver
[Reenviar registros puntuales](#reenviar-registros-puntuales-mainpy-resend)).

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
0 3 * * 0 cd "$RAFAM_DIR" && /usr/bin/flock -n state/sync_changes_prov.lock .venv/bin/python main.py sync-changes --entity proveedores
0 4 * * 0 cd "$RAFAM_DIR" && /usr/bin/flock -n state/sync_changes_oc.lock .venv/bin/python main.py sync-changes --entity oc_items
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
| `python main.py resend --entity X --key K` | Reenvia registros puntuales sin tocar checkpoints (ver arriba). |
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
| `state/locks/pipeline.lock`, `daily_report.lock`, `integrity.lock`, `<entidad>.lock` | Locks de cron (flock) por job/entidad. |
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
