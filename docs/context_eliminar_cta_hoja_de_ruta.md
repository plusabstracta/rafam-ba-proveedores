# Contexto: Eliminación de CTA_HOJA_DE_RUTA del Proyecto

> **Fecha inicio:** 11-12 Mayo 2026  
> **Estado:** Análisis completado, pendiente ejecución de dump schema completo  
> **Archivos relacionados:** `prompts/eliminar_cta_hoja_de_ruta.txt`, `scripts/dump_full_schema.py`

---

## 1. Objetivo

Eliminar completamente la dependencia de `CTA_HOJA_DE_RUTA` del proyecto `rafam-ba-proveedores` y reemplazar todos los JOINs que pasan por esa tabla/vista con JOINs directos a las tablas fuente reales.

### Motivación

- `CTA_HOJA_DE_RUTA` es una vista/tabla desnormalizada en Oracle RAFAM
- En producción devuelve filas vacías para OPs del ejercicio en curso (caso real: OP_NRO vacío para todas las OPs 2026)
- Todas las columnas son nullable, no tiene PK consistente
- El proyecto ya tiene un fallback (`_build_op_fallback_subquery`) que usa `REG_COMP + CTA_COMPROB` cuando la vista falla
- Objetivo: promover ese fallback a ruta única y eliminar todo rastro de `CTA_HOJA_DE_RUTA`

---

## 2. Análisis Realizado

### 2.1 Estructura de CTA_HOJA_DE_RUTA

**Archivos adjuntos analizados:**

- `CTA_HOJA_DE_RUTA.sql` — DDL de la tabla física (67 columnas, todas nullable, sin PK)
- `CTA_VIS_HOJA_DE_RUTA.sql` — Vista Oracle que regenera los datos mediante 5 UNIONs
- `FLUJO_COMPRAS_RAFAM - copia.md` — Documentación del flujo de compras (10 etapas)
- `SCHEMA_FLUJO_COMPRAS_RAFAM - copia.md` — 24 tablas del flujo, excluye vistas

**Descubrimiento clave:** `CTA_HOJA_DE_RUTA` en Oracle es **TABLA física**, pero su contenido es claramente derivable (la vista `CTA_VIS_HOJA_DE_RUTA` lo demuestra). Probablemente se popula por trigger o job.

### 2.2 Cadena Canónica OC → Comprobante → OP

Según `CTA_VIS_HOJA_DE_RUTA`, el flujo real es:

```
ORDEN_COMPRA (EJERCICIO + UNI_COMPRA + NRO_OC)
    ↓
REG_COMP (EJERCICIO + NRO_REG_COMP + UNI_COMPRA + NRO_OC + DELEG_SOLIC + NRO_SOLIC)
    ↓
CTA_COMPROB (EJERCICIO + NRO_REG_COMP + TIPO + NRO_COMPROB) ← Factura
    ↓
ORDEN_PAGO_IMPUT (bridge N:M) — PK probable: (EJERCICIO + NRO_OP + NRO_REG_COMP + TIPO_COMPROB + NRO_COMPROB)
    ↓
ORDEN_PAGO (EJERCICIO + NRO_OP)
```

**Problema del código actual:** El proyecto linkea `ORDEN_PAGO ↔ SOLIC_GASTOS` por heurística `op.NRO_CANCE = sg.NRO_SOLIC`, que sólo funciona cuando la OP cancela una única SG. La vista real hace el vínculo **vía `ORDEN_PAGO_IMPUT`** (N:M robusto).

### 2.3 Estado de dev_rafam.db

**Tablas YA presentes:**

✅ `PROVEEDORES`, `PEDIDOS`, `PED_ITEMS`, `SOLIC_GASTOS`, `SOLIC_GASTOS_ITEMS`  
✅ `ORDEN_COMPRA`, `OC_ITEMS`  
✅ `REG_COMP`, `CTA_COMPROB`  
✅ `ORDEN_PAGO`, `RETENCIONES`, `DEDUCCIONES`  
✅ `JURISDICCIONES`  
✅ `CTA_HOJA_DE_RUTA` (VIEW derivada, creada por `load_csv_to_sqlite.py`)

**Tablas FALTANTES identificadas:**

| Tabla | Estado | Criticidad | Por qué la necesitamos |
|---|---|---|---|
| **`ORDEN_PAGO_IMPUT`** | ⚠️ Verificar nombre real | **BLOQUEANTE** | Único bridge formal OP ↔ comprobante en RAFAM. Sin esto seguimos con la heurística rota `NRO_CANCE = NRO_SOLIC` |
| **`CTA_IMPUT_PERSONAL`** | ✅ CSV disponible | **BLOQUEANTE** | Posible equivalente a `ORDEN_PAGO_IMPUT`. Tiene: `NRO_IMPUT, EJERCICIO, NRO_REG_COMP, NRO_REG_DEVEN, NRO_COMPROB, NRO_OP, IMPORTE_DEVEN`. **Falta confirmar** si tiene columna `TIPO_COMPROB` |
| **`REG_DEVEN`** | ✅ CSV disponible | Alta | Devengamiento (estado contable entre REG_COMP y ORDEN_PAGO). La vista lo usa en el primer UNION. Necesario para exponer `RD_NRO`/`RD_FECH` |
| **`ADJUDICACIONES`** | ✅ CSV disponible | Media | Ruta alternativa `SG → ADJUDICACIONES → ORDEN_COMPRA`. La vista usa 2 de 5 UNIONs para resolver OCs sin REG_COMP todavía |
| **`TIPOS_COMPROB`** | ❌ Falta CSV | Alta | Lookup para `debito_credito` (signo del importe). La vista usa `decode(debito_credito, 'D', importe_compr, importe_compr * -1)` |

**Nota sobre `CTA_IMPUT_PERSONAL`:**

- Columnas: `NRO_IMPUT, EJERCICIO, NRO_REG_COMP, NRO_REG_DEVEN, NRO_COMPROB, NRO_OP, IMPORTE_DEVEN`
- **Le falta `TIPO_COMPROB`** (necesaria para PK de `CTA_COMPROB`)
- Datos en CSV muestran 2007–2009, pero se necesita confirmar que cubre 2026
- El sufijo `_PERSONAL` sugiere pagos a personal, pero los NRO_COMPROB (`0000-85620230`, `4000-00000400`) son típicos de facturas de proveedores → nombre probablemente engañoso

### 2.4 Cardinalidades en dev_rafam.db

```sql
-- REG_COMP con NRO_OC poblado: 579/1075 filas (54%)
-- El otro 46% no trae OC resoluble desde REG_COMP; en el migrator actual esas OP/gastos se omiten para no crear registros sueltos.
-- Por lo tanto el path OC → REG_COMP es parcial por diseño
```

---

## 3. Archivos Clave del Proyecto

### 3.1 Código que usa CTA_HOJA_DE_RUTA

**`src/source_repository.py`:**

- `_build_orden_compra_statement()` — LEFT JOIN a `cta_hdr` para traer `HDR_CC_NRO`, `HDR_CC_TIPO_COMPROB`
- `_build_oc_items_statement()` — Idem
- `_build_orden_pago_statement()` — LEFT JOIN masivo a `cta_hdr` para resolver cadena OP→SG→OC→CC
- `_build_op_fallback_subquery()` — **Ruta alternativa que ya funciona sin la vista** (usa `REG_COMP + CTA_COMPROB`)

**`src/exporter.py`:**

- `_write_batch_oc_items()`, `_write_batch_orden_compra()` — Lógica de promote FB_* → HDR_* cuando la vista falla
- `_write_batch_orden_pago()` — Idem, con logs "sin CC_NRO en CTA_HOJA_DE_RUTA ni fallback"

**`scripts/load_csv_to_sqlite.py`:**

- `_SCHEMA_COLUMNS["CTA_HOJA_DE_RUTA"]` — 67 columnas
- `_CTA_HOJA_DE_RUTA_VIEW_SQL` — Definición de la vista derivada SQLite
- `_ensure_cta_hoja_de_ruta_view()` — Crea la vista si no existe como tabla CSV

### 3.2 Tests afectados

- `tests/test_ejercicio_filter_and_oc_op_flow.py` — Crea tabla `CTA_HOJA_DE_RUTA` con fixtures
- `tests/test_migrator_mapping.py` — Usa columnas `HDR_CC_NRO`, `HDR_OC_EJERCICIO`, etc.
- `tests/test_paxapos_id_mappings.py` — Idem
- `tests/test_exporter_extra_coverage.py` — Idem

### 3.3 Documentación

- `docs/rafam_schema.md` — Sección completa de CTA_HOJA_DE_RUTA
- `docs/rafam_paxapos_equivalencias.md` — Tabla de lookups + diagrama de vínculos
- `docs/deployment.md` — `GRANT SELECT ON CTA_HOJA_DE_RUTA`
- `.github/instructions/*.instructions.md` — Referencias varias

---

## 4. Script Creado: dump_full_schema.py

**Ubicación:** `scripts/dump_full_schema.py`

**Propósito:** Dumpear el esquema Oracle COMPLETO de `OWNER_RAFAM` (sin filtrar por tabla) para resolver las siguientes preguntas antes de refactorizar:

1. ¿Existe `ORDEN_PAGO_IMPUT` o sólo `CTA_IMPUT_PERSONAL`?
2. ¿Qué columnas tiene exactamente (incluyendo `TIPO_COMPROB`)?
3. ¿Cuál es su PK/FKs real?
4. ¿Qué índices tiene para optimizar los JOINs?
5. ¿`TIPOS_COMPROB` existe y qué columnas tiene?
6. Cardinalidad real OP ↔ comprobante (1:1, 1:N)

**Salida:**

- `output/rafam_context/full_schema.json` (machine-readable)
- `output/rafam_context/full_schema.md` (human-readable, commitear)

**Uso:**

```bash
cd /ruta/al/repo/rafam-ba-proveedores
python scripts/dump_full_schema.py
```

Flags opcionales si tarda:
- `--no-views` (saltea ALL_VIEWS)
- `--no-indexes`

---

## 5. Queries de Validación Pendientes (Ejecutar en Oracle)

Una vez tengamos el dump completo, estas queries complementan el análisis:

### 5.1 Buscar tablas *IMPUT*

```sql
SELECT TABLE_NAME 
FROM ALL_TABLES 
WHERE OWNER='OWNER_RAFAM' AND TABLE_NAME LIKE '%IMPUT%';
```

### 5.2 Cardinalidad OP ↔ comprobante

```sql
-- Si la tabla es ORDEN_PAGO_IMPUT:
SELECT cnt_comprob, COUNT(*) AS cant_ops FROM (
  SELECT EJERCICIO, NRO_OP, COUNT(*) AS cnt_comprob
  FROM OWNER_RAFAM.ORDEN_PAGO_IMPUT
  GROUP BY EJERCICIO, NRO_OP
) GROUP BY cnt_comprob ORDER BY cnt_comprob;

-- Si la tabla es CTA_IMPUT_PERSONAL:
SELECT cnt_comprob, COUNT(*) AS cant_ops FROM (
  SELECT EJERCICIO, NRO_OP, COUNT(*) AS cnt_comprob
  FROM OWNER_RAFAM.CTA_IMPUT_PERSONAL
  GROUP BY EJERCICIO, NRO_OP
) GROUP BY cnt_comprob ORDER BY cnt_comprob;
```

### 5.3 Cardinalidad REG_COMP por solicitud

```sql
SELECT
    CASE
        WHEN cnt = 1 THEN '1:1'
        WHEN cnt BETWEEN 2 AND 3 THEN '1:2-3'
        ELSE '1:4+'
    END AS relacion,
    COUNT(*) AS cantidad_SGs
FROM (
    SELECT EJERCICIO, DELEG_SOLIC, NRO_SOLIC, COUNT(*) AS cnt
    FROM OWNER_RAFAM.REG_COMP
    WHERE DELEG_SOLIC IS NOT NULL AND NRO_SOLIC IS NOT NULL
    GROUP BY EJERCICIO, DELEG_SOLIC, NRO_SOLIC
)
GROUP BY CASE
    WHEN cnt = 1 THEN '1:1'
    WHEN cnt BETWEEN 2 AND 3 THEN '1:2-3'
    ELSE '1:4+'
END
ORDER BY 1;
```

### 5.4 Cardinalidad CTA_COMPROB por REG_COMP

```sql
SELECT
    CASE
        WHEN cnt = 0 THEN '0 (sin comprob)'
        WHEN cnt = 1 THEN '1:1'
        ELSE '1:N'
    END AS relacion,
    COUNT(*) AS cantidad_RCs
FROM (
    SELECT rc.EJERCICIO, rc.NRO_REG_COMP,
           COUNT(cc.NRO_COMPROB) AS cnt
    FROM OWNER_RAFAM.REG_COMP rc
    LEFT JOIN OWNER_RAFAM.CTA_COMPROB cc
        ON cc.EJERCICIO = rc.EJERCICIO
       AND cc.NRO_REG_COMP = rc.NRO_REG_COMP
    GROUP BY rc.EJERCICIO, rc.NRO_REG_COMP
)
GROUP BY CASE
    WHEN cnt = 0 THEN '0 (sin comprob)'
    WHEN cnt = 1 THEN '1:1'
    ELSE '1:N'
END
ORDER BY 1;
```

---

## 6. Próximos Pasos (Checklist)

### Fase 1: Recolección de datos ⏳

- [ ] **Ejecutar `dump_full_schema.py` en la VM con acceso a Oracle**
- [ ] Subir `output/rafam_context/full_schema.{json,md}` al repo
- [ ] Ejecutar queries de validación 5.1–5.4 y documentar resultados
- [ ] **Exportar CSV de `TIPOS_COMPROB`** (tabla faltante)
- [ ] Confirmar si `CTA_IMPUT_PERSONAL` tiene columna `TIPO_COMPROB` (ver `DESC`)
- [ ] Confirmar cobertura 2026 en `CTA_IMPUT_PERSONAL` (SELECT COUNT WHERE EJERCICIO=2026)

### Fase 2: Actualizar dev_rafam.db 📦

- [ ] Agregar a `scripts/load_csv_to_sqlite.py` → `_SCHEMA_COLUMNS`:
  - `ADJUDICACIONES` (columnas del CSV adjunto)
  - `REG_DEVEN` (columnas del CSV adjunto)
  - `CTA_IMPUT_PERSONAL` o `ORDEN_PAGO_IMPUT` (según resultado Fase 1)
  - `TIPOS_COMPROB` (cuando tengamos el CSV)
- [ ] Regenerar `state/dev_rafam.db` con las nuevas tablas

### Fase 3: Refactorización del código 🔧

- [ ] **`src/source_repository.py`:**
  - Eliminar `_reflect_optional_table("CTA_HOJA_DE_RUTA")` de `_build_orden_compra_statement()`
  - Eliminar idem de `_build_oc_items_statement()`
  - Reescribir `_build_orden_pago_statement()` para usar:
    - `ORDEN_PAGO → CTA_IMPUT_PERSONAL → CTA_COMPROB` (vínculo comprobante)
    - `CTA_IMPUT_PERSONAL → REG_COMP → REG_DEVEN` (datos fiscales + devengamiento)
    - `REG_COMP → SOLIC_GASTOS → OC_ITEMS → ORDEN_COMPRA` (vínculo OC)
  - Promover `_build_op_fallback_subquery()` a ruta principal o inlinear
  - Renombrar columnas `FB_*` → `HDR_*` para mantener contrato con exporter

- [ ] **`src/exporter.py`:**
  - Eliminar toda lógica condicional `if raw.get('HDR_OC_NRO') is None: raw['HDR_OC_NRO'] = raw.get('FB_OC_NRO')`
  - Simplificar `_write_batch_oc_items()`, `_write_batch_orden_compra()`, `_write_batch_orden_pago()`
  - Actualizar logs que mencionan "CTA_HOJA_DE_RUTA"

- [ ] **`scripts/load_csv_to_sqlite.py`:**
  - Eliminar `"CTA_HOJA_DE_RUTA"` de `_SCHEMA_COLUMNS`
  - Eliminar `_CTA_HOJA_DE_RUTA_VIEW_SQL`
  - Eliminar `_ensure_cta_hoja_de_ruta_view()`
  - Eliminar llamada en `load_csvs()`

- [ ] **Otros scripts:**
  - `scripts/export_last_3_months.py` — Eliminar "CTA_HOJA_DE_RUTA" del dict de tablas
  - `scripts/explore_schema.py` — Eliminar de lista TARGET_TABLES
  - `scripts/generate_rafam_context.py` — Eliminar de TABLES_IN_SCOPE + FK_RELATIONSHIPS + glosario

### Fase 4: Tests 🧪

- [ ] **`tests/test_ejercicio_filter_and_oc_op_flow.py`:**
  - Eliminar `CREATE TABLE CTA_HOJA_DE_RUTA` + todos los INSERTs
  - Reescribir fixtures con datos en `REG_COMP + CTA_COMPROB + CTA_IMPUT_PERSONAL`
  - Actualizar asserts que verifican `HDR_CC_NRO` (ahora viene de otra ruta)

- [ ] **Otros tests:**
  - `test_migrator_mapping.py` — Verificar que fixtures siguen proveyendo `HDR_*`
  - `test_paxapos_id_mappings.py` — Idem
  - `test_exporter_extra_coverage.py` — Idem

- [ ] Ejecutar suite completa: `pytest tests/`

### Fase 5: Documentación 📚

- [ ] **`docs/rafam_schema.md`:**
  - Eliminar sección `## CTA_HOJA_DE_RUTA`
  - Eliminar del índice
  - Actualizar nota de alcance del header

- [ ] **`docs/rafam_paxapos_equivalencias.md`:**
  - Eliminar CTA_HOJA_DE_RUTA de tabla de lookups
  - Actualizar diagrama de vínculos (quitar caja pivot)
  - Actualizar sección 2.5 ORDEN_PAGO (ahora via REG_COMP + CTA_IMPUT_PERSONAL directo)

- [ ] **Otros docs:**
  - `docs/deployment.md` — Eliminar `GRANT SELECT ON CTA_HOJA_DE_RUTA`
  - `README.md` — Eliminar mención de vista derivada
  - `.github/instructions/*.instructions.md` — Eliminar referencias

### Fase 6: Validación final ✅

- [ ] Ejecutar `python main.py --ejercicio 2026 --full-load` contra SQLite dev
- [ ] Comparar conteos de registros migrados antes/después
- [ ] Verificar logs de exporter (no deben aparecer "sin CC_NRO en CTA_HOJA_DE_RUTA")
- [ ] Revisar payloads enviados a Paxapos (campo `gasto_nro_comprobante` poblado)
- [ ] Confirmar que el CSV `cta_hoja_de_ruta_*.csv` ya no se exporta

---

## 7. Notas Técnicas Importantes

### 7.1 Problema del min() en el fallback actual

El método `_build_op_fallback_subquery()` agrupa por `(EJERCICIO, DELEG_SOLIC, NRO_SOLIC)` y usa `min()` para elegir OC/comprobante. **Riesgo:** Si una `SOLIC_GASTOS` tiene múltiples `REG_COMP` (varios comprobantes o varias OCs), `min()` devuelve valores arbitrarios y puede perder vínculos.

**Solución:** Con `CTA_IMPUT_PERSONAL` que tiene `NRO_IMPUT` único, ya no necesitamos agrupar — traemos todas las filas y deduplicamos en Python si es necesario (el exporter ya tiene lógica de dedup por `ITEM_OC`).

### 7.2 Convención de nombres de columnas

Las columnas con prefijo `HDR_` (header) son las que el exporter espera. El refactor debe mantener esos nombres o actualizar el exporter también. Opción recomendada: mantener `HDR_*` en los labels del SELECT para no tocar exporter.

### 7.3 Ejercicio cruzado OC-OP

`REG_COMP.EJERCICIO` puede diferir de `ORDEN_COMPRA.EJERCICIO` y de `ORDEN_PAGO.EJERCICIO` (caso real: OP 2026 pagando una OC 2025). Los JOINs deben usar `REG_COMP.EJERCICIO` como pivote, no asumir que todos comparten el mismo ejercicio.

---

## 8. Contexto del Proyecto

**Nombre:** `rafam-ba-proveedores`  
**Ubicación:** `/mnt/datos/repos/core/packages/rafam-ba-proveedores`  
**Tech stack:** Python 3.11+, SQLAlchemy, Oracle (producción), SQLite (dev)  
**Propósito:** Sincronizar proveedores, órdenes de compra, órdenes de pago y comprobantes desde RAFAM (sistema legacy de la Provincia de Buenos Aires) a Paxapos (sistema moderno).

**Entidades migradas:**

- PROVEEDORES → proveedores
- ORDEN_COMPRA + OC_ITEMS → pedidos (con items)
- CTA_COMPROB → gastos (facturas)
- ORDEN_PAGO → ordenes_pago (con retenciones/deducciones)

**Flujo:** ETL incremental con checkpoint por tabla (FECH_* + ESTADO_*). Cada entidad se exporta en batch a API REST de Paxapos con retry + idempotencia vía `external_id`.

---

## 9. Comandos Útiles

```bash
# Regenerar dev DB desde CSVs
python scripts/load_csv_to_sqlite.py

# Ejecutar sync contra dev DB
python main.py --ejercicio 2026 --full-load

# Tests
pytest tests/ -v
pytest tests/test_ejercicio_filter_and_oc_op_flow.py -v

# Ver estructura de dev DB
sqlite3 state/dev_rafam.db ".schema CTA_HOJA_DE_RUTA"
sqlite3 state/dev_rafam.db "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name;"
```

---

## 10. Referencias

- **Prompt original:** `prompts/eliminar_cta_hoja_de_ruta.txt` (inventario completo de cambios necesarios)
- **DDLs:** Adjuntos `CTA_HOJA_DE_RUTA.sql`, `CTA_VIS_HOJA_DE_RUTA.sql`
- **Flujo:** Adjuntos `FLUJO_COMPRAS_RAFAM - copia.md`, `SCHEMA_FLUJO_COMPRAS_RAFAM - copia.md`
- **CSVs disponibles:** `output/rafam_ultimos_3_meses/` (snapshot 2026-05-04)
  - ✅ adjudicaciones_20260504_140052.csv
  - ✅ reg_deven_20260504_140052.csv
  - ✅ cta_imput_personal_20260504_140052.csv
  - ❌ tipos_comprob (falta exportar)

---

**Última actualización:** 12 Mayo 2026  
**Siguiente acción:** Ejecutar `dump_full_schema.py` en VM con acceso a Oracle y subir resultados al repo.
