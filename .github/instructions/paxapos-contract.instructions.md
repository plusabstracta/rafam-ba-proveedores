---
description: "Use when implementing mappers, exporters, payload construction, entity linking, docs, env templates, or any code that sends data TO Paxapos. Covers el flujo RAFAM real, el modelo de datos Paxapos, contrato API, autenticación, validaciones, upsert, contrato de env y mapeo campo a campo de cada entidad migrada."
applyTo: "src/exporter.py,src/gateway_mapper.py,src/entity_link_store.py,README.md,.env.example,docs/rafam_paxapos_equivalencias.md,tests/test_migrator_mapping.py"
---

# Contrato Paxapos + Flujo RAFAM — Referencia Completa

> **Fuente de verdad de qué tablas se migran:** [docs/rafam_paxapos_equivalencias.md](../../docs/rafam_paxapos_equivalencias.md).
> Este documento profundiza en contrato HTTP, schema Paxapos y mapeo de payloads de las tablas migradas (`PROVEEDORES`, `ORDEN_COMPRA`, `OC_ITEMS`, `SOLIC_GASTOS`, `CTA_COMPROB`, `ORDEN_PAGO`, `ORDEN_PAGO_DEDUC`, con puentes `REG_COMP` y `ORDEN_PAGO_IMPUT`).

## 1. Ciclo de vida real (sólo tablas migradas)

### 1.1 Flujo lineal

```
PROVEEDORES ──► ORDEN_COMPRA ──► OC_ITEMS
                     │
                     ▼
              CTA_COMPROB (factura del proveedor, vía REG_COMP)
                     │
                     ▼ (ORDEN_PAGO_IMPUT)
              ORDEN_PAGO ──► ORDEN_PAGO_DEDUC (retenciones)
```

### 1.2 Conexiones FK en el flujo

| Paso | Tabla origen | Tabla destino | FK en origen | PK referenciada en destino | Qué representa |
|------|-------------|---------------|--------------|---------------------------|----------------|
| 1 | ORDEN_COMPRA | PROVEEDORES | `COD_PROV` | `COD_PROV` | Proveedor al que se le compra |
| 2 | OC_ITEMS | ORDEN_COMPRA | `EJERCICIO` + `UNI_COMPRA` + `NRO_OC` | `EJERCICIO` + `UNI_COMPRA` + `NRO_OC` | Líneas de la OC |
| 3 | CTA_COMPROB | PROVEEDORES | `COD_PROV` | `COD_PROV` | Factura del proveedor |
| 4 | CTA_COMPROB → ORDEN_COMPRA | (vía `REG_COMP`) | `EJERCICIO + NRO_REG_COMP` | `EJERCICIO + UNI_COMPRA + NRO_OC` | Vincula factura con la OC originante |
| 5 | ORDEN_PAGO | PROVEEDORES | `COD_PROV` | `COD_PROV` | Proveedor que cobra |
| 6 | ORDEN_PAGO ↔ CTA_COMPROB | (vía `ORDEN_PAGO_IMPUT`) | `EJERCICIO + NRO_OP` | `EJERCICIO + TIPO + NRO_COMPROB + COD_PROV` | Pago vinculado a una o varias facturas |
| 7 | ORDEN_PAGO_DEDUC | ORDEN_PAGO | `EJERCICIO` + `NRO_OP` | `EJERCICIO` + `NRO_OP` | Retención asociada al pago |
| 8 | ORDEN_PAGO_DEDUC | DEDUCCIONES | `CODIGO_DEDUC` | `COD_DEDUC` | Catálogo del tipo de retención (lookup, no se migra) |

> `EJERCICIO` (año fiscal) es el hilo conductor que atraviesa todas las tablas. `JURISDICCION` es **un campo** en cabeceras (no una tabla migrada): se usa para resolver `centro_costo_id` en Paxapos.

---

## 2. Flujo dentro de Paxapos

```
Pedido (solicitud) → [Aprobación interna] → Orden de Compra → [Envío mail proveedor]
   → Gasto (factura proveedor) → [Aprobación tesorería] → Orden de Pago (egreso)
```

- **Pedido** (`tipo=solicitud`): solicitud interna de compra
- **Aprobación** (opcional): `estado_aprobacion` pasa de pendiente a aprobado
- **OC** (`tipo=orden_compra`): se envía al proveedor con link público (`public_url`)
- **Gasto**: factura del proveedor, vinculada a OC(s)
- **OP/Egreso**: pago al proveedor, vinculada a gasto(s)
- **Flujo de aprobación OP**: `Pendiente(0) → Aprobado(1) → Pagado(3)`
- **Pago directo**: `Pagado(3)` si viene con fecha
- No hay recepción formal como paso intermedio obligatorio, aunque existe `recepcionado` boolean y `recibida_cantidad` por item.

### 2.1 Cadena de vínculos en Paxapos

```
OC (compras_pedidos.id) ◄── account_gastos.pedido_id ── Gasto ◄──HABTM (account_egresos_gastos)── Egreso (OP)
```

- **OC/OP→Gasto**: se establece enviando `gasto_nro_comprobante`; si no existe, el endpoint auto-crea el gasto.
- **Gasto→OC**: se establece con `Gasto.pedido_id` cuando el row trae `pedido_id`.
- **OP→Gasto**: se persiste en `account_egresos_gastos` con los gastos resueltos/creados.

### 2.2 Cadena de vínculos en RAFAM (fuente)

```
CTA_COMPROB ◄──(REG_COMP)──► ORDEN_COMPRA / SOLIC_GASTOS
      ▲
      │ (ORDEN_PAGO_IMPUT: bridge físico OP ↔ comprobante)
      │
  ORDEN_PAGO ──► ORDEN_PAGO_DEDUC (EJERCICIO + NRO_OP + CODIGO_DEDUC)
```

- **CTA_COMPROB ↔ ORDEN_COMPRA/SOLIC_GASTOS:** se resuelve por `REG_COMP` (tabla puente, `EJERCICIO + NRO_REG_COMP`). Permite setear `account_gastos.pedido_id` al migrar la factura.
- **ORDEN_PAGO ↔ CTA_COMPROB:** vía `ORDEN_PAGO_IMPUT` (una fila por comprobante imputado). La OC canónica de la OP se resuelve por el mismo `NRO_REG_COMP` imputado; **NO** usar `ORDEN_PAGO.NRO_CANCE` como puente (puede apuntar a otra solicitud).
- **Retenciones ↔ ORDEN_PAGO:** tabla `ORDEN_PAGO_DEDUC`, match por `EJERCICIO + NRO_OP`.
- **DEDUCCIONES:** sólo lookup; el tipo de retención se resuelve contra el catálogo remoto `tipos_retencion` (con alias por descripción: IVA, GANANCIAS, IIBB, SUSS, etc.).
- **Obsoletas (NO usar):** la VIEW `CTA_HOJA_DE_RUTA` y la tabla `RETENCIONES`.

---

## 3. API Paxapos — Endpoints y Autenticación

### 3.1 Rutas disponibles

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/{tenant}/rafam/migracion/importar.json` | POST | Importación masiva de todas las entidades |
| `/{tenant}/rafam/migracion/spec.json` | GET | Contrato/spec dinámica del endpoint |
| `/{tenant}/rafam/migracion/lookups.json` | GET | Catálogos (proveedores, mercaderías, unidades, tipos factura, etc.) |
| `/{tenant}/rafam/migracion/resolver_mercaderia.json` | POST | Resolución de mercadería por referencia |
| `/{tenant}/account/proveedores/check_duplicados/{id}.json` | GET | Detección de proveedores duplicados por similitud de nombre + CUIT |

> No hay Swagger/OpenAPI estático. La documentación de referencia es `RAFAM_MIGRATION_API.md` y el endpoint `spec.json`.

### 3.1.1 Construcción de URL y tenant

- `PAXAPOS_URL` es solo el host/base, sin tenant. Ejemplo: `https://proveedores.madariaga.gob.ar`.
- `PAXAPOS_TENANT` se agrega al path para rutas migrator. Ejemplo: `madariaga`.
- `PAXAPOS_RAFAM_*_PATH` son paths relativos dentro de Paxapos. Nunca deben ser URLs completas.
- La URL final se arma como `{PAXAPOS_URL}/{PAXAPOS_TENANT}/{PAXAPOS_RAFAM_*_PATH}`.
- El mismo tenant se envía también por header `X-Tenant-Id` porque el backend lo usa en autenticación/contexto.

### 3.2 Autenticación

**Para scripts de migración usar**: `X-Api-Key: {key}` + `X-Tenant-Id: {tenant}`

| Modo | Header | Implementación |
|------|--------|----------------|
| JWT Bearer | `Authorization: Bearer {jwt}` o `X-Json-Web-Token` o cookie JWT | `PaxaJwtTokenAuthenticate.php` |
| API Key (recomendado para scripts) | `X-Agent-Api-Key`, `X-Api-Key`, o `Authorization: Token {key}` | `RistoSecurityComponent.php` |

La key se valida contra env var `AGENT_API_KEY` (acepta múltiples separadas por coma).
El `beforeFilter` del controller habilita ambos: `allowAgentApiAccess` + `Auth->allow`.

### 3.3 Headers requeridos para el script

```python
{
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Tenant-Id": "{tenant}",
    "X-Api-Key": "{api_key}",
    "User-Agent": "rafam-sync/1.0",
}
```

---

## 4. Payload raíz del endpoint importar

```json
{
  "dry_run": false,
  "options": {
    "upsert": true,
    "atomic": false,
    "fail_fast": false,
    "send_oc_mail": false,
    "strict_mail": false
  },
  "proveedores": [],
  "ordenes_compra": [],
  "gastos": [],
  "ordenes_pago": []
}
```

**Orden interno de procesamiento** (hardcodeado): `proveedores → ordenes_compra → gastos → ordenes_pago`. Se pueden enviar todas en un solo payload.

> Las retenciones viajan dentro del bloque de la OP correspondiente (ver §12.5).

---

## 5. Modelos Paxapos — Schema completo

### 5.1 Proveedores (`account_proveedores`)

| Columna | Tipo | Nullable | Notas |
|---------|------|----------|-------|
| `id` | int PK auto | — | |
| `name` | varchar(100) | NO | Obligatorio (o `razon_social` que se copia a `name`) |
| `razon_social` | varchar(200) | SÍ | |
| `tipo_documento_id` | int | SÍ | 1=CUIT |
| `cuit` | varchar(12) | SÍ | UNIQUE, formato CUIT argentino si tipo_documento_id=1. Se auto-limpia (regex `\D+`) antes de guardar: `"30-71234567-8"` y `"30712345678"` son el mismo. La unicidad compara el CUIT limpio |
| `iva_condicion_id` | tinyint unsigned | SÍ | inList [1,2,3,4,5,6] |
| `mail` | varchar(100) | SÍ | |
| `telefono` | varchar(100) | SÍ | |
| `domicilio` | varchar(100) | SÍ | |
| `localidad` | varchar(100) | SÍ | |
| `provincia` | varchar(100) | SÍ | |
| `codigo_postal` | varchar(10) | SÍ | |
| `cbu` | varchar(22) | SÍ | regex exacto 22 dígitos |
| `cbu_alias` | varchar(100) | SÍ | |
| `created` | datetime | SÍ | |
| `modified` | datetime | SÍ | |
| `created_by` | varchar(36) | SÍ | |
| `deleted_date` | datetime | SÍ | |
| `deleted` | tinyint(1) | — | default 0, soft-delete |

**IVA condiciones**: 1=Resp.Inscripto, 2=Monotributo, 3=Exento, 4=Consumidor Final, 5=No Responsable, 6=Resp.No Inscripto

**Estados**: NO tiene estados activo/inactivo/suspendido. Solo soft-delete (`deleted`). RAFAM `COD_ESTADO` activo → `deleted=false` (default); inactivo/suspendido → no importar u omitir.

**Validaciones server-side**:
- `name`: minLength 1 (pero allowEmpty=true)
- `cuit`: formato CUIT argentino + unicidad (isUnique)
- `cbu`: regex exacto 22 dígitos
- `iva_condicion_id`: inList [1-6]
- Requiere `name` o `razon_social` (validación del controller)

### 5.2 Órdenes de Compra (`compras_pedidos`)

La tabla `compras_pedidos` se usa con `tipo='orden_compra'`. Otros valores de `tipo` no se sincronizan desde RAFAM.

| Columna | Tipo | Nullable | Notas |
|---------|------|----------|-------|
| `id` | int unsigned PK auto | — | |
| `internal_id` | varchar(36) | SÍ | Clave de upsert |
| `tipo` | varchar(20) | — | default `orden_compra`. Valores: `solicitud`, `presupuesto`, `orden_compra` |
| `estado_aprobacion` | tinyint unsigned | — | default 3. 1=Pendiente, 2=Aprobado, 3=No requiere, 4=Rechazado |
| `proveedor_id` | int | SÍ | FK → account_proveedores |
| `gasto_id` | int | SÍ | FK → account_gastos |
| `recepcionado` | tinyint(1) | — | default 0 |
| `enviado_at` | datetime | SÍ | |
| `media_id` | int | SÍ | |
| `observacion` | text | SÍ | |
| `monto_presupuestado` | decimal(14,2) | SÍ | |
| `prioridad` | varchar(10) | — | default `normal` |
| `aprobado_by` | varchar(36) | SÍ | |
| `aprobado_date` | datetime | SÍ | |
| `motivo_rechazo` | text | SÍ | |
| `public_viewed_at` | datetime | SÍ | |
| `public_viewed_count` | int unsigned | — | default 0 |
| `deleted` | tinyint(1) | — | default 0 |

**Items** (`compras_pedido_mercaderias`):

| Columna | Tipo | Nullable | Notas |
|---------|------|----------|-------|
| `id` | int unsigned PK auto | — | |
| `pedido_id` | int | SÍ | FK → compras_pedidos |
| `mercaderia_id` | int | NO | FK → compras_mercaderias (obligatorio o via `mercaderia_external_ref`) |
| `es_ajuste_precio` | tinyint(1) | — | default 0 |
| `proveedor_id` | int | SÍ | hereda de cabecera |
| `pedido_estado_id` | int | — | default 1. 1=Pendiente, 2=Completado, 3=Pedido |
| `unidad_de_medida_id` | int | NO | Default `5` (Unidad en seeds legacy — ver §14.1; `_UM_DEFAULT=5` en `gateway_mapper.py`). Confirmar el ID real del tenant con `make migrator-lookups`. |
| `cantidad` | decimal(10,2) | NO | Obligatorio |
| `observacion` | text | SÍ | |
| `recibida_unidad_de_medida_id` | int | SÍ | |
| `recibida_cantidad` | decimal(10,2) | SÍ | |
| `precio` | decimal(14,2) | SÍ | |
| `deleted` | tinyint(1) | — | default 0 |

**Validaciones server-side**: Sin validaciones en el modelo ($validate = array()). El controller desplegado valida items no vacío, `cantidad`, y `mercaderia_id` existente o `mercaderia_external_ref`; `name` por sí solo no es contrato aceptado por el endpoint actual.

**Mercadería auto-creación legacy**: con `mercaderia_external_ref` y `auto_create_mercaderia=true` (default), el importador final de OC puede crear Producto + Mercadería. El script RAFAM no usa esa vía en `ordenes_compra[].items[]` porque generaba nombres visibles con hash; primero resuelve por `resolver_mercaderia.json`.

**Regla del script RAFAM actual**: no enviar `mercaderia_external_ref` dentro de items de OC/pedido ni al resolver previo. Ese campo activa la creación determinística legacy (`create_deterministic`) y Paxapos agrega `[RAFAM-{hash}]` al nombre visible. El exportador primero resuelve la mercadería por link local, lookup limpio o `resolver_mercaderia.json` usando `item.name`, `item.descripcion`, `item.nombre_compra` y `item.producto_nombre` con la descripción RAFAM limpia. El hash/identidad única pertenece al `barcode` que devuelve Paxapos (por ejemplo `RAFAM-NAME:{hash}`), nunca al nombre visible. El script guarda `name:{descripcion_normalizada}` -> `mercaderia_id` en `entity_link_store`; y el payload final del importador envía siempre `mercaderia_id`.

**Mapeo de estados RAFAM→Paxapos**:
- `N` (normal) → `estado_aprobacion=3` (no requiere) o `2` (aprobado)
- `A` (anulada) → `estado_aprobacion=4` (rechazado) o soft-delete

**OC NO necesita pedido previo**. Son registros independientes en la misma tabla con `tipo` diferente. No hay relación directa OC→Pedido(solicitud).

### 5.3 Gastos (`account_gastos`)

| Columna | Tipo | Nullable | Notas |
|---------|------|----------|-------|
| `id` | int PK auto | — | |
| `cierre_id` | int | SÍ | |
| `proveedor_id` | int | SÍ | FK → account_proveedores |
| `clasificacion_id` | int | SÍ | FK → account_clasificaciones |
| `tipo_factura_id` | int | SÍ | FK → tipo_facturas |
| `punto_de_venta` | varchar(5) | SÍ | Se rellena con ceros a 5 dígitos |
| `factura_nro` | varchar(20) | SÍ | Se rellena con ceros a 20 dígitos |
| `fecha` | date | SÍ | **Obligatorio** (validación controller) |
| `fecha_vencimiento` | date | SÍ | Si no viene, se copia de `fecha` |
| `importe_neto` | decimal(14,2) | SÍ | default 0.00 |
| `importe_total` | decimal(14,2) | SÍ | default 0.00. **Obligatorio** (validación controller) |
| `observacion` | text | SÍ | Aquí se graba la traza `RAFAM:{...}` para idempotencia |
| `cae` | varchar(20) | SÍ | |
| `cae_vencimiento` | date | SÍ | |
| `deleted` | tinyint(1) | — | default 0 |

**Campos obligatorios**: `importe_total`, `fecha`. Todo lo demás es opcional.

**Upsert**: por `proveedor_id + factura_nro` (+ `punto_de_venta` si viene). NO usa `external_id` para dedup. El `external_id` se graba como traza en `observacion` con formato `RAFAM:{...json...}`.

**Sin proveedor o sin factura_nro** → siempre INSERT nuevo (sin posibilidad de dedup).

El gasto puede vincularse a la OC con `pedido_id` (`account_gastos.pedido_id`). Cuando OP/OC envian `gasto_nro_comprobante`, Paxapos busca o auto-crea el gasto; si viene `pedido_id`, lo usa para asociar ese gasto a la OC.

**No existe mecanismo de anulación** — omitir gastos con `ESTADO_SOLIC=A`.

**Validaciones server-side**:
- `factura_nro`: unicidad por `proveedor_id+tipo_factura_id+punto_de_venta` (custom `factura_no_repetida`)
- `fecha`: formato date válido
- `tipo_factura_id`, `importe_neto`, `importe_total`: numérico

### 5.4 Órdenes de Pago / Egresos (`account_egresos`)

| Columna | Tipo | Nullable | Notas |
|---------|------|----------|-------|
| `id` | int PK auto | — | |
| `total` | decimal(14,2) | NO | Obligatorio |
| `neto_transferido` | decimal(14,2) | SÍ | |
| `observacion` | text | SÍ | |
| `identificador_pago` | varchar(100) | SÍ | Clave de upsert |
| `tipo_de_pago_id` | int | SÍ | FK → tipo_de_pagos |
| `fecha` | datetime | SÍ | Con fecha → auto estado=3(Pagado); sin fecha → estado=0(Pendiente) |
| `fecha_programada` | datetime | SÍ | |
| `estado` | tinyint unsigned | — | default 3. 0=Pendiente, 1=Aprobado, 2=Rechazado, 3=Pagado |
| `aprobado_by` | varchar(36) | SÍ | |
| `aprobado_date` | datetime | SÍ | |
| `motivo_rechazo` | text | SÍ | |
| `cuenta_bancaria_id` | int unsigned | SÍ | |
| `numero_operacion` | varchar(100) | SÍ | |
| `deleted` | tinyint(1) | — | default 0 |

**Join table** (`account_egresos_gastos`): `egreso_id`, `gasto_id`, `importe decimal(14,2)`, `deleted`.

**Campos obligatorios**: `identificador_pago`, `total`, `gasto_nro_comprobante` (string o array con al menos 1 comprobante) y `pedido_id` resuelto para el flujo RAFAM.

**Upsert**: por `identificador_pago`. Si ya existe → `skip_existing` (NO actualiza, solo devuelve el existente). No hay forma de hacer N→C post-creación.

**Usa `gasto_nro_comprobante`** para buscar `Gasto` por `proveedor_id + punto_de_venta + factura_nro`; si no existe, lo auto-crea siempre. En el flujo RAFAM el script sólo debe enviar la OP si ya resolvió `pedido_id`, y Paxapos lo guarda en `Gasto.pedido_id` cuando está vacío.

**Allowed fields** del save: `identificador_pago, fecha, tipo_de_pago_id, total, observacion, estado, fecha_programada, cuenta_bancaria_id, numero_operacion`. Notar que `proveedor_id` NO está en la whitelist.

**Feature flag**: `Site.ordenes_de_pago` debe estar en `true`. Si no → HTTP 400. Verificar llamando con bloque `ordenes_pago` vacío en `dry_run`.

**Omitir OPs con `ESTADO_OP<>C`, `CONFIRMADO<>S`, sin `FECH_CONFIRM`, sin `gasto_nro_comprobante` o sin OC resuelta a `pedido_id`**. Enviar sólo pagos confirmados y linkeables.

**Validaciones server-side**:
- `total`: numérico, requerido
- `fecha`: datetime formato ymd
- `estado`: inList [0,1,2,3]
- Validación `gastos_pagos` deshabilitada durante import masivo

---

## 6. Catálogos de referencia

### 6.1 Tipos de factura (`tipo_facturas`)

| ID | Nombre | codigo_afip |
|----|--------|-------------|
| 1 | A | 001 |
| 2 | B | 006 |
| 3 | X | — |
| 4 | M | 051 |
| 5 | C | 011 |
| 6 | Vale | — |
| 7 | Otros | — |
| 8 | NCB | 008 |
| 9 | NCC | 013 |
| 10 | NCA | 003 |
| 11 | NDB | — |
| 12 | NDC | — |
| 13 | NDA | — |
| 14 | NCM | 053 |
| 15+ | TIQUE FACTURA A/B, TIQUE, REMITO, RESUMEN... | — |

> Para obtener la tabla exacta del tenant, usar `GET /{tenant}/rafam/migracion/lookups.json?only=tipos_factura`.

### 6.2 Unidades de medida (`compras_unidad_de_medidas`)

| ID | Nombre |
|----|--------|
| 1 | Planta |
| 2 | Penca |
| 3 | Kilo |
| 4 | Bolsa |
| 5 | **Unidad** |
| 6 | Atado |
| 7 | Cajón |
| 8 | Caja |
| 9 | Lata |
| 10 | Bidón |
| 11 | Pack |
| 12 | Botella |
| 13 | Pilón |
| 14 | Barra |
| 15 | Horma |
| 16 | Gancho |
| 17 | Frasco |
| 18 | Porción |
| 19 | Plancha |
| 20 | Litro |
| 21 | Docena |
| 22 | Maple |

> Esta tabla corresponde a seeds legacy donde `id=1` es "Planta" y `id=5` es "Unidad". No asumir que esos IDs son iguales en todos los tenants: confirmar con `GET /{tenant}/rafam/migracion/lookups.json?only=unidades_de_medida` o `make migrator-lookups`. El default del código es `_UM_DEFAULT=5` en `gateway_mapper.py` (no hay variable de entorno para esto).

### 6.3 IVA condiciones

| ID | Nombre |
|----|--------|
| 1 | Responsable Inscripto |
| 2 | Monotributista |
| 3 | Exento |
| 4 | Consumidor Final |
| 5 | No Responsable |
| 6 | Responsable No Inscripto |

### 6.4 Estados de aprobación (Pedido/OC)

| Valor | Constante | Significado |
|-------|-----------|-------------|
| 1 | COMPRAS_PEDIDO_APROBACION_PENDIENTE | Pendiente |
| 2 | COMPRAS_PEDIDO_APROBACION_APROBADO | Aprobado |
| 3 | COMPRAS_PEDIDO_APROBACION_NO_REQUIERE | No requiere aprobación (default) |
| 4 | COMPRAS_PEDIDO_APROBACION_RECHAZADO | Rechazado |

### 6.5 Estados de Egreso/OP

| Valor | Significado |
|-------|-------------|
| 0 | Pendiente |
| 1 | Aprobado |
| 2 | Rechazado |
| 3 | Pagado (default) |

---

## 7. Jurisdicción RAFAM → Rubro + Clasificación

Una jurisdicción RAFAM genera **AMBOS**: un `Rubro` y una `Clasificación`.

| Concepto | Tabla Paxapos | Uso | Relación con entidades |
|----------|--------------|-----|------------------------|
| **Rubro** | `compras_rubros` | Categorización de compras/mercaderías | `PedidoMercaderia.rubro_id`, `Mercaderia.rubro_id`, proveedores via HABTM |
| **Clasificación** | `account_clasificaciones` | Categorización contable/presupuestaria de gastos | `Gasto.clasificacion_id`. Soporta jerarquía (árbol con `parent_id`, `lft`, `rght`) |

> **Rubro** = categoría de qué se compra. **Clasificación** = categoría contable del gasto.

Proveedor↔Rubro: relación HABTM via `compras_proveedores_rubros`. No se gestiona desde el endpoint migrador.
Proveedor↔Clasificación: NO existe relación.

---

## 8. Comportamiento de Upsert por entidad

| Entidad | Match key | Comportamiento si existe | Mode |
|---------|-----------|--------------------------|------|
| Proveedores | `cuit` (o `name` si no hay cuit) | **Actualiza** datos | `update` |
| Rubros | `name` (case-sensitive, trim) | **Actualiza** | `update` |
| Clasificaciones | `name + parent_id` | **Actualiza** | `update` |
| OCs | `internal_id` | **Actualiza** cabecera, **reemplaza** todos los items (delete+insert) | `update` |
| Gastos | `proveedor_id + factura_nro` (+ `punto_de_venta`) | **Actualiza** | `update` |
| Órdenes de pago | `identificador_pago` | **NO actualiza** — devuelve existente | `skip_existing` |

> Nunca falla por duplicado con `upsert=true` (excepto conflicto de unicidad de CUIT en un proveedor diferente).

---

## 9. Respuesta de la API

### 9.1 POST exitoso (HTTP 200)

```json
{
  "success": true,
  "dry_run": false,
  "atomic": false,
  "stats": {
    "rubros": { "total": 27, "ok": 27, "error": 0 },
    "proveedores": { "total": 295, "ok": 295, "error": 0 }
  },
  "errors": [],
  "results": {
    "proveedores": [
      { "success": true, "external_id": {"cod_prov": 984}, "id": 123, "mode": "create" }
    ],
    "ordenes_compra": [
      { "success": true, "external_id": {...}, "id": 789, "mode": "create", "items": 2, "internal_id": "{ej}-{nro}", "public_url": "https://...", "gasto_ids": [1] }
    ]
  }
}
```

### 9.2 Errores parciales (HTTP 207 Multi-Status)

```json
{
  "success": false,
  "errors": [
    { "section": "ordenes_compra", "index": 0, "external_id": {...}, "message": "OC sin items" }
  ],
  "results": {
    "ordenes_compra": [
      { "success": false, "external_id": {...}, "message": "OC sin items" }
    ]
  }
}
```

- Cada item fallido se identifica por `section + index + external_id`
- Con `atomic=true`: cualquier error → rollback de TODO (HTTP 207)
- Con `fail_fast=true`: se detiene en el primer error

### 9.3 Lookups (`GET /lookups.json`)

```json
{
  "lookups": {
    "proveedores": [{ "id", "name", "razon_social", "cuit", "mail" }],
    "mercaderias": [{ "id", "nombre_compra", "producto_id", "barcode" }],
    "unidades_de_medida": [{ "id", "name" }],
    "tipos_factura": [{ "id", "name", "codename", "codigo_afip" }],
    "tipos_de_pago": [{ "id", "name", "codigo_afip" }],
    "gastos": [{ "id", "proveedor_id", "fecha", "punto_de_venta", "factura_nro", "tipo_factura_id", "importe_total", "external_id" }],
    "rubros": [{ "id", "name" }],
    "clasificaciones": [{ "id", "name", "parent_id" }]
  },
  "mapping_rules": { "..." },
  "pagination": { "gastos": { "page", "limit", "total", "pages", "has_next" } }
}
```

Filtrable con `?only=proveedores,tipos_factura` (CSV). Gastos paginados con `?page=1&limit=2000` (max 5000).

---

## 10. Límites y restricciones

| Restricción | Valor | Notas |
|-------------|-------|-------|
| Registros por request | Sin límite explícito en código | Procesamiento secuencial por bloque |
| Timeout | `max_execution_time` de PHP | No hay override específico. Usar `atomic=false` y `fail_fast=false` para batches grandes |
| Tamaño de payload | `post_max_size` de PHP (típicamente 8M-128M) | |
| Importes máximos | decimal(14,2) → hasta 999,999,999,999.99 | Schema actualizado de decimal(10,2) a decimal(14,2). Verificar ALTER en producción |
| OP performance | Validación `gastos_pagos` deshabilitada durante import | `enDeuda()` carga todos los gastos sin limit |

---

## 11. Orden de migración (dependencias estrictas)

```
1. proveedores  → escribe `proveedores` en entity_link_store
2. oc_items     → lee `proveedores` + escribe `orden_compra` (cabecera + items embebidos)
3. solic_gastos → lee `orden_compra` (gasto_refs) + enriquece gastos existentes (UPDATE-ONLY) + escribe `gasto`
4. orden_pago   → lee `orden_compra`/`gasto` + escribe `orden_pago` (comprobantes vía ORDEN_PAGO_IMPUT)
5. retenciones  → lee `orden_pago` + escribe `retenciones` (desde ORDEN_PAGO_DEDUC)
```

> El orden es **estricto**. Cada entidad depende de que las anteriores ya hayan sido importadas y sus IDs remotos guardados en el entity_link_store. El campo `JURISDICCION` se resuelve a `centro_costo_id` por mapeo hardcodeado en `gateway_mapper.py`.

---

## 12. Mapeo RAFAM → Paxapos por entidad (payloads)

### 12.1 Proveedores

```json
{
  "external_id": { "cod_prov": int(COD_PROV) },
  "Proveedor": {
    "name": "FANTASIA o RAZON_SOCIAL (max 100)",
    "razon_social": "RAZON_SOCIAL (trimmed)",
    "cuit": "11 dígitos solo números",
    "mail": "EMAIL (trimmed)",
    "telefono": "NRO_PAIS_TE1 NRO_INTE_TE1 NRO_TELE_TE1 (fallback TE2, TE3, CELULAR)",
    "domicilio": "CALLE_LEGAL NRO_LEGAL (fallback POSTAL)",
    "localidad": "LOCA_LEGAL o LOCA_POSTAL",
    "provincia": "PROV_LEGAL o PROV_POSTAL",
    "codigo_postal": "COD_LEGAL o COD_POSTAL",
    "tipo_documento_id": 1,
    "iva_condicion_id": "_IVA_MAP[COD_IVA]"
  }
}
```

### 12.2 Centros de Costo (resolución del campo `JURISDICCION`)

No se envía como entidad separada. El campo `JURISDICCION` (en cabeceras de OC, OP, CTA_COMPROB) se resuelve a `centro_costo_id` mediante `_JURISDICCION_CENTRO_COSTO_MAP` en `src/gateway_mapper.py` (default `8 = "Otro"`).

El mapping debe coincidir con los IDs reales de `centros_costo` del tenant destino.

### 12.3 Órdenes de Compra

```json
{
  "external_id": { "ejercicio": int, "uni_compra": int, "nro_oc": int },
  "Pedido": {
    "internal_id": "{ejercicio % 100}-{nro_oc}",
    "tipo": "orden_compra",
    "proveedor_id": int(lookup COD_PROV),
    "observacion": "solo si la OC tiene OBSERVACIONES reales en RAFAM (nunca fabricar traza)"
  },
  "items": [{
    "name": "DESCRIPCION limpia",
    "cantidad": float(CANTIDAD),
    "precio": float(IMP_UNITARIO),
    "recibida_cantidad": float(CANT_RECIB),
    "unidad_de_medida_id": 1
  }]
}
```

### 12.4 Gastos (facturas reales del proveedor — `SOLIC_GASTOS` + `CTA_COMPROB` vía `REG_COMP`)

**Modo UPDATE-ONLY (enriquecimiento):** el script NO crea gastos. Consulta
`resolver_gasto.json` para localizar gastos parciales que Paxapos ya creó
(cuando el proveedor subió la factura sobre una OC) y envía solo los campos
vacíos (`Gasto: {id, merge: "fill_empty", ...}`). El `external_id` usa la
identidad de la solicitud de gasto:

```json
{
  "external_id": { "ejercicio": int, "deleg_solic": int, "nro_solic": int },
  "Gasto": {
    "fecha": "YYYY-MM-DD",
    "importe_total": float(CTA_COMPROB.IMPORTE_COMPR),
    "importe_neto": float(CTA_COMPROB.IMPORTE_LIQUIDO || CTA_COMPROB.IMPORTE_NETO || CTA_COMPROB.IMPORTE_SIN_IVA),
    "punto_de_venta": "PV de CTA_COMPROB.NRO_COMPROB",
    "factura_nro": "NRO de CTA_COMPROB.NRO_COMPROB",
    "tipo_factura_id": int(lookup CTA_COMPROB.TIPO vía RAFAM_TIPO_COMPROB_TO_PAXAPOS_NAME),
    "centro_costo_id": int(resolve_centro_costo_id(JURISDICCION)),
    "fecha_vencimiento": "CTA_COMPROB.FECH_VENCIM",
    "observacion": "opcional"
  },
  "pedido_id": int(OC resuelta vía REG_COMP, requerido en flujo RAFAM)
}
```

`Gasto.importe_total` y `Gasto.importe_neto` son importes crudos RAFAM. El script no calcula netos: sólo parsea y redondea a 2 decimales para JSON. En dumps actuales el neto/líquido del comprobante llega como `CTA_COMPROB.IMPORTE_SIN_IVA`; si el schema real expone `IMPORTE_LIQUIDO` o `IMPORTE_NETO`, esos campos tienen prioridad.

### 12.5 Órdenes de Pago

```json
{
  "external_id": { "ejercicio": int, "nro_op": int },
  "importe_total": float(IMPORTE_TOTAL),
  "importe_neto": float(IMPORTE_LIQUIDO),
  "Egreso": {
    "identificador_pago": "RAFAM-OP-{ejercicio}-{nro_op}",
    "total": float(IMPORTE_TOTAL),
    "neto_transferido": float(IMPORTE_LIQUIDO),
    "tipo_de_pago_id": int(PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID),
    "estado": 3,
    "fecha": "FECH_CONFIRM"
  },
  "gasto_nro_comprobante": "0001-00000456",
  "pedido_id": 789
}
```

`importe_total` e `importe_neto` son los nombres Paxapos para los dos importes de la OP. `Egreso.total` y `Egreso.neto_transferido` se conservan en el payload por compatibilidad con el importador actual.

> Solo enviar OPs con `ESTADO_OP='C'`, `CONFIRMADO='S'`, `FECH_CONFIRM` presente y `gasto_nro_comprobante`. En Paxapos se crean con `fecha=FECH_CONFIRM` y `estado=3`. OPs anuladas, pendientes, no confirmadas o sin comprobante se omiten. `pedido_id` viaja cuando la OC está linkeada; los pagos de gasto directo (factura real sin OC en `REG_COMP`) se envían SIN `pedido_id` cuando `RAFAM_MIGRAR_OP_SIN_OC=true` (default) — Paxapos deduplica el Gasto por `proveedor + factura_nro`. Con la OC existente pero aún no migrada, la OP se encola y reintenta.

---

## 13. Variables de entorno relevantes

| Variable | Uso | Default |
|----------|-----|---------|
| `PAXAPOS_URL` | URL base del server Paxapos | (requerida) |
| `PAXAPOS_TENANT` | Tenant ID | (requerida) |
| `PAXAPOS_API_KEY` | API key para auth | (requerida) |
| `PAXAPOS_RAFAM_IMPORT_PATH` | Path relativo o URL absoluta del importador RAFAM dentro de Paxapos | `rafam/migracion/importar.json` |
| `PAXAPOS_RAFAM_SPEC_PATH` | Path relativo o URL absoluta de spec RAFAM dentro de Paxapos | `rafam/migracion/spec.json` |
| `PAXAPOS_RAFAM_LOOKUPS_PATH` | Path relativo o URL absoluta de lookups RAFAM dentro de Paxapos | `rafam/migracion/lookups.json` |
| `PAXAPOS_RAFAM_RESOLVER_MERCADERIA_PATH` | Path relativo o URL absoluta del resolver determinístico de mercaderías RAFAM dentro de Paxapos | `rafam/migracion/resolver_mercaderia.json` |
| `PAXAPOS_RAFAM_RESOLVER_GASTO_PATH` | Path relativo o URL absoluta del resolver de gastos (enriquecimiento UPDATE-ONLY) | `rafam/migracion/resolver_gasto.json` |
| `PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID` | ID tipo factura Paxapos default | (vacío) |
| `PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID` | ID tipo de pago Paxapos default (`Otros`) | `10` |
| `RAFAM_SYNC_BATCH_DELAY_SECONDS` | Delay local entre batches | `2` |
| `PAXAPOS_VERIFY_SSL` | Verificación SSL (default de código: `true`; solo apagar en dev) | `true` |
| `PAXAPOS_TIMEOUT_SECONDS` | Timeout HTTP | `20` |

> `PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID` NO existe en el código: la unidad default está hardcodeada (`_UM_DEFAULT=5` en `gateway_mapper.py`) y se resuelve primero por link/lookup remoto.

---

## 14. Gotchas y comportamientos no obvios

Reglas que no se deducen de la documentación estándar pero causan bugs si se ignoran.

### 14.1 Unidad de medida default depende del tenant

No asumir que `id=1` es "Unidad" en todos los tenants. En seeds legacy de gastronomía, `id=1` era **"Planta"** y **"Unidad" era `id=5`**. El script resuelve primero por `link_unidad_medida`, luego por lookup remoto con nombre `Unidad` y finalmente el fallback interno `_UM_DEFAULT=5` (`gateway_mapper.py`). Antes de una importación real, consultar `make migrator-lookups` y verificar que el ID de 'Unidad' del tenant coincida (si no, ajustar `_UM_DEFAULT`).

### 14.2 CUIT se limpia automáticamente — dedup por dígitos

Paxapos elimina guiones/puntos del CUIT con regex `\D+` antes de guardar. Se puede enviar `"30-71234567-8"` o `"30712345678"` indistintamente. La **validación de unicidad compara el CUIT limpio**, así que ambos formatos representan el mismo proveedor.

### 14.3 `factura_nro` y `punto_de_venta` se rellenan con ceros

`factura_nro` se rellena a 20 caracteres y `punto_de_venta` a 5 caracteres (pad left con ceros). Si se envía `"345"`, se guarda como `"00000000000000000345"`. Esto **no afecta el upsert de gastos** — Paxapos normaliza antes de comparar, así que `"345"` y `"00000000000000000345"` matchean.

### 14.4 Notas de Crédito invierten el signo automáticamente

Si `tipo_factura_id` corresponde a **NCA(10), NCB(8), NCC(9) o NCM(14)**, Paxapos hace `abs(importe) * -1` al guardar. **No enviar importes ya negativos** o quedarán positivos (doble negación).

### 14.5 Órdenes de pago con upsert NO actualizan

El upsert de OPs es `skip_existing`: si `identificador_pago` ya existe, devuelve el existente sin modificar nada. **No se puede corregir una OP importada re-enviándola.** Hay que borrarla manualmente o desde la UI.

### 14.6 Estado de Egreso depende de `fecha` en `beforeSave`

Sin `fecha` → `estado=0` (pendiente); con `fecha` → `estado=3` (pagado). Si se envía `estado: 3` pero sin `fecha`, el `beforeSave` lo sobrescribe a `estado=0`. **Siempre enviar `fecha` cuando `estado=3`.**

### 14.7 `gasto_nro_comprobante` resuelve o auto-crea gastos

Resuelve por `proveedor_id + punto_de_venta + factura_nro`. Si no encuentra el `Gasto`, lo auto-crea siempre. Si el row trae `pedido_id`, Paxapos lo usa para dejar el gasto existente o auto-creado vinculado con la OC.

### 14.8 OPs sin OC se omiten

El script RAFAM no debe confiar en `pedido_internal_id` como fallback para crear pagos. Si el `link_store` local no puede resolver la OC a `pedido_id`, la OP y su `gastos[]` se omiten. Si la OC es anterior a `RAFAM_EJERCICIO_MIN`, la query de `oc_items` debe traer esa OC por dependencia `ORDEN_PAGO_IMPUT -> REG_COMP` antes de procesar la OP, pero sólo para OPs confirmadas dentro del alcance actual (`EJERCICIO >= mínimo` o `FECH_CONFIRM` desde el 1/1 del mínimo). OPs históricas fuera de ese alcance no deben arrastrar OCs viejas.

### 14.9 Resolver mercaderías antes de enviar items

Paxapos soporta `mercaderia_external_ref` y puede agrupar/auto-crear mercaderías, pero el import final de OC/PED debe llegar con `mercaderia_id`. El script usa `resolver_mercaderia.json` antes del POST de importación por nombre limpio: no manda `mercaderia_external_ref`, porque esa ruta agrega hash al nombre visible. El resolver debe recibir `item.name` desde la descripción RAFAM y devolver un `barcode` único. Una mercadería con `barcode=RAFAM...` y nombre limpio es válida; una con nombre visible tipo `[RAFAM-...]`, `{RAFAM:...}` o `Mercaderia desarrollo #...` es stale/generada y no debe reutilizarse. Si un cambio futuro modifica el criterio de deduplicación, debe migrar los links locales o guardar aliases para no duplicar Producto + Mercadería.

### 14.10 `monto_presupuestado` se auto-calcula si no se envía

Si no se incluye `monto_presupuestado` en el payload del Pedido/OC, Paxapos lo calcula como `sum(precio * cantidad)` de todos los items. Si se necesita un valor específico (ej: monto aprobado RAFAM distinto al calculado), enviarlo explícitamente.

### 14.11 La tabla `tipo_facturas` varía por tenant

El seed base tiene ~33 tipos, pero cada tenant puede tener tipos adicionales o distintos. **Siempre usar el endpoint `lookups.json?only=tipos_factura`** del tenant destino para mapear. No hardcodear IDs.

### 14.12 `internal_id` auto-generado es determinístico

Si no se envía `Pedido.internal_id` pero sí `external_id` con los campos esperados, el controller genera el `internal_id` para OCs como `{ejercicio}-{nro_oc}`.

Si se quiere control total del upsert, enviar `internal_id` propio. Si no, dejar que lo genere pero asegurar que `external_id` tenga los campos necesarios.

### 14.13 Validación `gastos_pagos` deshabilitada durante import masivo

El check normal verifica que los gastos no estén ya pagados, pero con datasets grandes revienta memoria. El migrador lo bypasea. Esto significa que **se puede crear una OP que pague un gasto ya pagado** — no da error pero contablemente queda mal. **Validar del lado del script** que no se dupliquen pagos.

### 14.14 Sin rollback parcial sin `atomic=true`

Si se envían 100 proveedores y el #50 falla, los primeros 49 ya están grabados. Con `atomic=true` se revierte todo. **Para migración inicial usar `atomic=false`** (más resiliente); **para correcciones puntuales usar `atomic=true`**.

### 14.15 Endpoint de dedup de proveedores disponible

`GET /{tenant}/account/proveedores/check_duplicados/{id}.json` detecta proveedores duplicados post-migración usando similitud de nombre + CUIT. Útil para auditoría después de la carga inicial.

### 14.16 Orden de importación es crítico — mismo request o requests separados

El orden interno de procesamiento es: `proveedores → ordenes_compra → gastos → ordenes_pago`. Si se envía todo en un solo request, el controller respeta este orden automáticamente. Si se hacen requests separados, **respetar la secuencia estrictamente** para que las FKs se resuelvan.
