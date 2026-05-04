# Guía de instalación y operación

## Requisitos previos

| Requisito | Detalle |
|-----------|---------|
| Python | 3.10 o superior |
| Oracle Instant Client | Descargado en `C:\oracle\instantclient` (ver más abajo) |
| Acceso de red a Oracle | VPN / red interna de la municipalidad activa |
| Usuario Oracle de solo lectura | Creado por el DBA (ver sección Permisos) |

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone <url-del-repo>
cd rafam-ba-proveedores
```

### 2. Instalar dependencias Python

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 3. Instalar Oracle Instant Client

1. Descargar **Instant Client Basic** para Windows 64-bit desde:  
   https://www.oracle.com/database/technologies/instant-client/winx64-64-downloads.html
2. Descomprimir en `C:\oracle\instantclient`
3. Verificar que el archivo `oci.dll` exista en esa carpeta

### 4. Configurar credenciales

```bash
copy .env.example .env
```

Editar `.env` con los valores reales (nunca commitear este archivo):

```
RAFAM_SOURCE_BACKEND=oracle
RAFAM_SOURCE_HOST=<IP del servidor Oracle>
RAFAM_SOURCE_PORT=1521
RAFAM_SOURCE_SERVICE=BDRAFAM
RAFAM_SOURCE_USER=<usuario de solo lectura>
RAFAM_SOURCE_PASSWORD=<password>

LOCAL_STATE_DB_PATH=state/checkpoint.db

PAXAPOS_URL=https://proveedores.madariaga.gob.ar
PAXAPOS_TENANT=madariaga
PAXAPOS_JWT=<jwt de Paxapos, solo si se usa modo gateway directo>
PAXAPOS_API_KEY=<api key del migrator RAFAM>
PAXAPOS_PROVEEDORES_ENDPOINT=account/proveedores.json
```

---

## Permisos Oracle (tarea del DBA)

El script usa un usuario de **solo lectura**. El DBA debe ejecutar:

```sql
CREATE USER rafam_ro IDENTIFIED BY <password>;
GRANT CREATE SESSION TO rafam_ro;

GRANT SELECT ON OWNER_RAFAM.PROVEEDORES    TO rafam_ro;
GRANT SELECT ON OWNER_RAFAM.JURISDICCIONES TO rafam_ro;
GRANT SELECT ON OWNER_RAFAM.PEDIDOS        TO rafam_ro;
GRANT SELECT ON OWNER_RAFAM.PED_ITEMS      TO rafam_ro;
GRANT SELECT ON OWNER_RAFAM.SOLIC_GASTOS   TO rafam_ro;
GRANT SELECT ON OWNER_RAFAM.ORDEN_COMPRA   TO rafam_ro;
GRANT SELECT ON OWNER_RAFAM.OC_ITEMS       TO rafam_ro;
GRANT SELECT ON OWNER_RAFAM.ORDEN_PAGO     TO rafam_ro;
```

---

## Operación diaria

### Ver estado de los checkpoints

```bash
.venv/bin/python main.py status
```

Muestra para cada entidad: estado, último ID/timestamp procesado, cuándo fue el último run y cuántos registros se enviaron.

### Ejecutar sincronización

```bash
# Sincronización normal (incremental si ya hay checkpoints, full load si es primera vez)
.venv/bin/python main.py run

# Solo una entidad
.venv/bin/python main.py run --entity=proveedores

# Limitar filas (útil para testear)
.venv/bin/python main.py run --limit=100

# Solo validar checkpoints sin escribir archivos
.venv/bin/python main.py run --export=noop

# Enviar proveedores al gateway JSON de Paxapos
.venv/bin/python main.py run --entity=proveedores --export=gateway
```

### Forzar full reload de una entidad

```bash
.venv/bin/python main.py reset --entity=proveedores
.venv/bin/python main.py run --entity=proveedores
```

### Forzar full reload de todo

```bash
.venv/bin/python main.py reset --all
.venv/bin/python main.py run
```

---

## Primera ejecución (migración histórica)

La primera vez no existen checkpoints → el script hace full scan de todas las tablas automáticamente.
Dependiendo del volumen puede tardar. Se recomienda:

```bash
# Correr entidad por entidad para monitorear
.venv/bin/python main.py run --entity=jurisdicciones
.venv/bin/python main.py run --entity=proveedores
.venv/bin/python main.py run --entity=pedidos
.venv/bin/python main.py run --entity=ped_items
.venv/bin/python main.py run --entity=solic_gastos
.venv/bin/python main.py run --entity=orden_compra
.venv/bin/python main.py run --entity=oc_items
.venv/bin/python main.py run --entity=orden_pago
```

---

## Exploración del esquema Oracle

Para regenerar `docs/rafam_schema.md` con la estructura real de las tablas:

```bash
python scripts/explore_schema.py
```

Requiere credenciales válidas en `.env`.

---

## Tests

Los tests no requieren conexión a Oracle:

```bash
pytest tests/ -v
```

---

## Archivos generados

| Ruta | Descripción |
|------|-------------|
| `state/checkpoint.db` | SQLite local de estado: checkpoints y vínculos RAFAM -> Paxapos. **No commitear.** |
| `output/<entidad>_<timestamp>.csv` | CSVs exportados por cada run. **No commitear.** |

---

## Solución de problemas

| Error | Causa probable | Solución |
|-------|---------------|----------|
| `ORA-12170: TCP connect timeout` | Sin acceso de red al servidor Oracle | Conectarse a VPN / red interna |
| `ORA-01017: invalid username/password` | Credenciales incorrectas en `.env` | Verificar `RAFAM_SOURCE_USER` y `RAFAM_SOURCE_PASSWORD` |
| `ORA-00904: invalid identifier` | Nombre de columna incorrecto en `sync_engine.py` | Correr `explore_schema.py` y actualizar el `ts_field` correspondiente |
| `DPI-1047: Cannot locate a 64-bit Oracle Client` | Instant Client no instalado o path incorrecto | Verificar que `oci.dll` exista en `C:\oracle\instantclient` |
| Checkpoint no avanza | Error registrado en la última ejecución | Correr `python main.py status` para ver el error, corregir y volver a correr |
