# RAFAM ↔ Paxapos — Equivalencias de Tablas (Fuente de verdad)

> **Este documento es la única fuente de verdad** sobre qué tablas de RAFAM se migran a Paxapos y cómo se mapean.
> Cualquier otra documentación que contradiga este archivo está desactualizada y debe corregirse.

El proyecto `rafam-ba-proveedores` migra **6 tablas principales** desde Oracle RAFAM (schema `OWNER_RAFAM`) hacia el schema tenant de Paxapos (CakePHP 2) vía el endpoint `POST /{tenant}/rafam/migracion/importar.json`.

La ejecución operativa del migrator se organiza en **3 pasadas/scripts**, no en 6 procesos independientes. Algunas tablas se migran como datos embebidos dentro de una pasada mayor:

1. `proveedores` migra `PROVEEDORES` → `account_proveedores`.
2. `oc_items` migra `ORDEN_COMPRA` + `OC_ITEMS` → `compras_pedidos` + `compras_pedido_mercaderias`.
3. `orden_pago` migra `ORDEN_PAGO` y, en la misma pasada, usa `CTA_COMPROB`, `CTA_HOJA_DE_RUTA`, `RETENCIONES` y `DEDUCCIONES` para crear/vincular `account_gastos`, `account_egresos_gastos` y `account_retenciones`.

Además, hay **tablas de lookup** que se leen para resolver datos (no se migran como entidad propia).

---

## 1. Resumen tabla por tabla

| # | RAFAM (Oracle) | Paxapos (MySQL tenant) | Modo operativo |
|---|---|---|---|
| 1 | `PROVEEDORES` | `account_proveedores` | pasada 1: `proveedores` |
| 2 | `ORDEN_COMPRA` | `compras_pedidos` (con `tipo='orden_compra'`) | pasada 2: embebida en `oc_items` |
| 3 | `OC_ITEMS` | `compras_pedido_mercaderias` | pasada 2: `oc_items` |
| 4 | `CTA_COMPROB` | `account_gastos` | pasada 3: embebida/auto-creada por `orden_pago` |
| 5 | `ORDEN_PAGO` | `account_egresos` | pasada 3: `orden_pago` |
| 6 | `RETENCIONES` | `account_retenciones` | pasada 3: embebida en `orden_pago` |

**Tablas RAFAM usadas como lookup (NO se migran):**

| RAFAM | Uso |
|---|---|
| `CTA_HOJA_DE_RUTA` | Vista que vincula `CTA_COMPROB` ↔ `ORDEN_COMPRA` ↔ `ORDEN_PAGO`. Trae `PE_EJERCICIO`, `PE_JURISDICCION`, `OC_NRO`, `OC_COD_PROV`, `OP_NRO`, `OP_ESTADO`, `OP_NRO_CANCE`. Se usa al migrar `account_egresos` para armar HABTM `account_egresos_gastos` y para filtrar por estado pagado (`OP_ESTADO='C'`). |
| `DEDUCCIONES` | Catálogo de tipos de retención. `RETENCIONES.COD_RET` ↔ `DEDUCCIONES.CODIGO` (vínculo naranja). Se lee `DEDUCCIONES.DESCRIPCION` para resolver `account_retenciones.tipo_impuesto_id` por heurística. |
| `REG_COMP` | Puente para vincular `CTA_COMPROB` con `ORDEN_COMPRA` (resuelve `account_gastos.pedido_id`). Comparte `EJERCICIO + NRO_OC + COD_PROV + JURISDICCION`. |
| `JURISDICCION` | Catálogo (`JURISDICCION`, `DENOMINACION`, `SELECCIONABLE`). Se lee la denominación para nombrar centros de costo si no están en `_JURISDICCION_CENTRO_COSTO_MAP`. |

**Diagrama de vínculos (colores del análisis funcional):**

```
                  ┌──────────────────────┐
                  │  CTA_HOJA_DE_RUTA    │  (pivot — vista)
                  │  PE_EJERCICIO        │
                  │  PE_JURISDICCION ◄──── JURISDICCION (rosa)
                  │  OC_NRO ───────────────► OC_ITEMS / RG_COMP (amarillo)
                  │  OC_COD_PROV ──────────► PROVEEDORES (violeta)
                  │  OP_NRO ───────────────► ORDEN_PAGO (verde)
                  │  OP_ESTADO  = 'C'  ◄──── ORDEN_PAGO.ESTADO_OP (rojo)
                  │  OP_NRO_CANCE ─────────► ORDEN_PAGO.NRO_CANCE
                  └──────────────────────┘            │
                                                       │ (celeste)
                                                       ▼
                                          ┌──────────────────────┐
                                          │  RETENCIONES         │
                                          │  EJERCICIO+NRO_CANCE │
                                          │  COD_RET ──┐         │
                                          └────────────┼─────────┘
                                                       │ (naranja)
                                                       ▼
                                              DEDUCCIONES.CODIGO
```


---

## 2. Detalle por par de tablas

### 2.1 `PROVEEDORES` → `account_proveedores`

| RAFAM | Paxapos | Notas |
|---|---|---|
| `COD_PROV` | `external_ref` (rafam, proveedores, cod_prov) | Identificador externo idempotente. |
| `RAZON_SOCIAL` | `razon_social` / `name` | |
| `CUIT` | `documento_fiscal` | |
| `COD_IVA` | `iva_responsabilidad_id` | Vía `_IVA_MAP` en `gateway_mapper.py` (RINS=1, EXEN=2, NGAN=3, CF=4, RNI=5, MONOT=6, etc.). |
| `CALLE_LEGAL` + `NRO_LEGAL` | `direccion` | Concatenados en `_join_address()`. |
| `LOC`, etc. | `localidad`, ... | |
| `EMAIL` | `mail` | Truncado a 100 caracteres. |
| `ING_BRUTOS` | (no mapeado) | **TODO**: pendiente mapear a `numero_ingresos_brutos` en `account_proveedores` cuando el schema lo soporte. |
| `FECHA_ULT_COMP` | (filtro incremental) | Usado como `ts_field` en `config.py` para cargas incrementales — sólo se reimportan proveedores con compras desde la última corrida. |

### 2.2 `ORDEN_COMPRA` → `compras_pedidos` (tipo='orden_compra')

| RAFAM | Paxapos | Notas |
|---|---|---|
| `EJERCICIO` + `UNI_COMPRA` + `NRO_OC` | `external_ref` | Identificador externo idempotente. |
| `COD_PROV` | `proveedor_id` | Resuelto por `external_ref`. |
| `JURISDICCION` | `centro_costo_id` | Vía `resolve_centro_costo_id()`. |
| `FECH_EMI` | `fecha` | |
| `IMPORTE_TOT` | `total` | |
| (siempre) | `tipo` | Hardcoded `'orden_compra'`. |

### 2.3 `OC_ITEMS` → `compras_pedido_mercaderias`

Ítems de la OC. Se enviarán dentro del payload `ordenes_compra[].items[]`.

| RAFAM | Paxapos | Notas |
|---|---|---|
| `EJERCICIO` + `UNI_COMPRA` + `NRO_OC` + `ITEM_OC` | `external_ref` | |
| `EJERCICIO` + `UNI_COMPRA` + `NRO_OC` | (FK) → OC | Vincula al pedido padre. |
| `DESCRIPCION` | `mercaderia.name` | Si no existe, se crea. |
| `UNI_MED` | `mercaderia.unidad_de_medida_id` | Vía `_UM` (UNIDAD=1, KILOGRAMO=2, LITRO=3, METRO=4, PAQUETE=5, HORAS=6, DIA=7). Default `1` (Unidad). |
| `CANT` | `cantidad` | |
| `PRECIO_UNIT` | `precio_unitario` | |
| `CLASE` + `TIPO` + `INCISO` + `PAR_PRIN` + `PAR_PARC` | `mercaderia.codigo_clasificacion` | Si dos ítems comparten la misma clasificación, comparten la misma `mercaderia` en Paxapos. |

### 2.4 `CTA_COMPROB` → `account_gastos`

Facturas reales del proveedor (con número fiscal AFIP).

En la ejecución actual no hay una pasada standalone `cta_comprob`. El script `orden_pago` lee los datos de comprobante y el endpoint de Paxapos busca o auto-crea el `Gasto` al importar la OP, usando `gasto_nro_comprobante`.

| RAFAM | Paxapos | Notas |
|---|---|---|
| `EJERCICIO` + `NRO_REG_COMP` (vía REG_COMP) | `external_ref` | |
| `COD_PROV` | `proveedor_id` | |
| `TIPO` (FAA/FAB/FAC/...) | `tipo_factura_id` | Vía `RAFAM_TIPO_COMPROB_TO_PAXAPOS_NAME` → lookup por `name` en `afip_tipo_facturas`. |
| `NRO_COMPROB` | `factura_nro` | Número fiscal de la factura. |
| `FECH_COMPROB` | `fecha` | |
| `IMPORTE_TOT` | `total` | |
| `JURISDICCION` | `centro_costo_id` | |
| (vía REG_COMP → ORDEN_COMPRA) | `pedido_id` | FK a `compras_pedidos.id` cuando la factura tiene OC asociada. |

### 2.5 `ORDEN_PAGO` → `account_egresos`

> **Filtro de migración:** se migran OPs con `ESTADO_OP IN ('C', 'N')`, `CONFIRMADO = 'S'`, `FECH_CONFIRM` presente, importe positivo y OC/gasto resoluble por la cadena canónica `ORDEN_PAGO_IMPUT -> REG_COMP -> ORDEN_COMPRA`. Las OPs anuladas (`A`), no confirmadas, sin fecha, sin importe válido o sin OC linkeada se omiten.

| RAFAM | Paxapos | Notas |
|---|---|---|
| `EJERCICIO` + `NRO_OP` | `external_ref` | |
| `COD_PROV` | `proveedor_id` | |
| `FECH_CONFIRM` | `fecha` | Sólo cuando `ESTADO_OP IN ('C', 'N')`, `CONFIRMADO='S'` y la OP tiene OC/gasto canónico. |
| `IMPORTE_TOTAL` | `total` | |
| `IMPORTE_LIQUIDO` | `importe_liquido` | Total menos retenciones. |
| `TIPO_CANCE` (CA/CM/NO) | `tipo_de_pago_id` | Vía `RAFAM_TIPO_CANCE_TO_PAXAPOS_PAGO_NAME` → lookup por `name` en `tipo_de_pagos`. Default `"Transferencia bancaria"`. |
| `JURISDICCION` | `centro_costo_id` | |
| `NRO_CANCE` | (clave para retenciones) | Se guarda para luego buscar `RETENCIONES` por `EJERCICIO + NRO_CANCE`. No se persiste como columna en Paxapos. |
| (vía `CTA_HOJA_DE_RUTA`) | HABTM `account_egresos_gastos` | Vincula el egreso con uno o varios gastos (`CTA_COMPROB`) usando `OP_NRO + OC_NRO`. |

### 2.6 `RETENCIONES` → `account_retenciones`

En la ejecución actual no hay una pasada standalone `retenciones`. El script `orden_pago` consulta `RETENCIONES` + `DEDUCCIONES`, mapea las retenciones y las envía embebidas dentro del row de `ordenes_pago[]`.

| RAFAM | Paxapos | Notas |
|---|---|---|
| `EJERCICIO` + `NRO_CANCE` + `COD_RET` | `external_ref` | (en RAFAM la columna es `COD_RET`; algunas vistas la exponen como `COD_DEDUC`). |
| (vía `ORDEN_PAGO` match `EJERCICIO + NRO_CANCE`) | `egreso_id` | FK a `account_egresos.id`. Vínculo celeste del diagrama. |
| `COD_RET` → `DEDUCCIONES.CODIGO` → `DEDUCCIONES.DESCRIPCION` | `tipo_impuesto_id` | Vínculo naranja. Heurística por substring en `DESCRIPCION`: `"IVA"`→102, `"GANANCIA"`→103, `"INGRESOS BRUTOS"` o `"IIBB"`→104, `"SUSS"`→105, `"MEDICOS"` o `"CAJA MED"`→110. |
| `IMPORTE` | `importe` | |
| `FECH_RET` | `fecha` | |

---

## 3. Alertas y validaciones

- **Idempotencia obligatoria:** todo registro migrado debe llevar `external_ref = {source: "rafam", entity: <tabla>, ...claves naturales}` para que reimportar no genere duplicados.
- **`compras_pedidos.tipo` siempre `'orden_compra'`** en esta migración. No se sincronizan otros tipos.
- **Filtro de OPs:** se migran las que tienen `ESTADO_OP IN ('C', 'N')` + `CONFIRMADO='S'` + `FECH_CONFIRM` + importe positivo + OC/gasto canónico. Las anuladas (`A`), no confirmadas o sin OC linkeada se omiten. Esto se verifica en `exporter.py` y `source_repository.py`.
- **`pedido_id` en `account_gastos`** debe resolverse desde la cadena `CTA_COMPROB → REG_COMP → ORDEN_COMPRA`. Si no hay OC migrada/linkeada, la OP y su `gastos[]` se omiten para evitar pagos o gastos sueltos.
- **`RAFAM_EJERCICIO_MIN` en OCs:** el filtro aplica a `orden_compra`/`oc_items`. La excepción para incluir OCs anteriores se limita a OPs confirmadas dentro del alcance actual (`EJERCICIO >= mínimo` o `FECH_CONFIRM` desde el 1/1 del mínimo); OPs históricas no deben arrastrar OCs viejas.
- **`unidad_de_medida_id` default = 1 (Unidad)**. Antes había un bug que ponía 5 (Paquete); está corregido en `gateway_mapper.py`.
- **`PROVEEDORES.ING_BRUTOS` no se migra hoy** — pendiente. Si el negocio lo necesita, agregar mapeo en `gateway_mapper.py::map_proveedor()`.

---

## 4. Orden lógico y pasadas operativas

El orden lógico de dependencias sigue siendo de 6 tablas, pero el migrator lo ejecuta en 3 pasadas oficiales:

1. `proveedores`: crea/actualiza `account_proveedores` desde `PROVEEDORES`.
2. `oc_items`: agrupa `ORDEN_COMPRA` + `OC_ITEMS` y envía `ordenes_compra[]` con `items[]` inline. Esto crea la cabecera de OC y sus mercaderías en una sola pasada.
3. `orden_pago`: procesa `ORDEN_PAGO` y, en la misma pasada, resuelve `CTA_COMPROB` para crear/vincular gastos y `RETENCIONES` + `DEDUCCIONES` para crear `account_retenciones`.

Así, las 6 tablas principales quedan cubiertas, pero no todas tienen un script independiente.

---

## 5. Catálogo de IDs de Paxapos (extraídos de `packages/cakephp/Config/Schema/risto.php`)

### 5.1 `tipo_documentos`

| id | codigo_fiscal | name | codigo_afip |
|---|---|---|---|
| 1 | C | CUIT | 80 |
| 2 | L | CUIL | 86 |
| 3 | 0 | Libreta de Enrolamiento | 89 |
| 4 | 1 | Libreta Cívica | 90 |
| 5 | 2 | DNI | 96 |
| 6 | 3 | Pasaporte | 94 |
| 7 | 4 | Cédula de Identidad | 0 |
| 8 | (vacío) | Sin identificar | 99 |

### 5.2 `afip_iva_responsabilidades`

| id | codigo_fiscal | name |
|---|---|---|
| 1 | I | Resp. Inscripto |
| 2 | E | Exento |
| 3 | A | No Responsable |
| 4 | C | Consumidor Final |
| 5 | T | No Categorizado |
| 6 | M | Responsable Monotributo |

### 5.3 `account_tipo_impuestos` (sólo retenciones — usadas por `RETENCIONES`)

| id | name | subsistema | tributo_afip_codigo |
|---|---|---|---|
| 102 | Retención de IVA | tributo | 1 (Nacional) |
| 103 | Retención de Ganancias | tributo | 1 (Nacional) |
| 104 | Retención de IIBB | tributo | 2 (Provincial) |
| 105 | Retención SUSS | tributo | 1 (Nacional) |
| 110 | Retención Caja de Médicos | tributo | 99 (Otros) |

> Otros IDs (1=IVA 21%, 2=IVA 10.5%, etc.) no se usan en esta migración.

### 5.4 `afip_tipo_facturas`

Lookup dinámico por `name` (no se hardcodean IDs). El mapping `RAFAM_TIPO_COMPROB_TO_PAXAPOS_NAME` resuelve el `name` y luego CakePHP busca por nombre.

### 5.5 `tipo_de_pagos`

Lookup dinámico por `name`. El mapping `RAFAM_TIPO_CANCE_TO_PAXAPOS_PAGO_NAME` resuelve el `name`.

### 5.6 `centros_costo` (por tenant)

Hardcoded en `_JURISDICCION_CENTRO_COSTO_MAP` (`gateway_mapper.py`):

| CentroCosto.id | Nombre | JURISDICCION RAFAM |
|---|---|---|
| 1 | Salud | 1110104000 |
| 2 | Obras Públicas | 1110103000 |
| 3 | Desarrollo | 1110106000 |
| 4 | Corralón / Mantenimiento | 1110118000 |
| 5 | Seguridad | 1110113000 |
| 6 | CASER | 1110111000 |
| 7 | Administrativo - General | 1110101000, 1110102000, 1110200000, 1110112000, 1110115000, 1110117000, 1110105000, 1110108000, 1110109000 |
| 8 | Otro | (default) |

### 5.7 `compras_unidad_de_medidas`

| id | name |
|---|---|
| 1 | Unidad (default) |
| 2 | Kilogramo |
| 3 | Litro |
| 4 | Metro |
| 5 | Paquete |
| 6 | Horas |
| 7 | Día |

---

## 6. Tablas RAFAM que NO se usan

Cualquier referencia en docs viejas a las siguientes tablas es **obsoleta** y debe ignorarse o eliminarse:

> _(Se omiten intencionalmente. El proyecto cubre exclusivamente las 6 tablas principales listadas en §1, distribuidas en 3 pasadas operativas, más los lookups documentados.)_

---

**Última actualización:** mayo 2026.
