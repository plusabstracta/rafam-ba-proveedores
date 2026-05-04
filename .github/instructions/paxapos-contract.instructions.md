---
description: "Use when implementing mappers, exporters, payload construction, entity linking, docs, env templates, or any code that sends data TO Paxapos. Covers the full RAFAM lifecycle, the Paxapos data model, API contract, authentication, validation rules, upsert behavior, env contract, and field-level mapping for every entity."
applyTo: "src/exporter.py,src/gateway_mapper.py,src/entity_link_store.py,README.md,.env.example,docs/deployment.md,docs/tablas_datos_paxapos.md,docs/field_mapping.md,tests/test_migrator_mapping.py"
---

# Contrato Paxapos + Flujo RAFAM — Referencia Completa

## 1. Ciclo de vida de una compra en RAFAM

### 1.1 Flujo lineal

```
JURISDICCIONES → PEDIDOS → PED_ITEMS
                    ↓
              SOLIC_GASTOS ← PROVEEDORES
                    ↓              ↓
               OC_ITEMS → ORDEN_COMPRA
                    ↓
               ORDEN_PAGO
```

### 1.2 Conexiones FK en el flujo

| Paso | Tabla origen | Tabla destino | FK en origen | PK referenciada en destino | Qué representa |
|------|-------------|---------------|--------------|---------------------------|----------------|
| 1 | PEDIDOS | JURISDICCIONES | `JURISDICCION` | `JURISDICCION` | Jurisdicción que emite el pedido |
| 2 | PED_ITEMS | PEDIDOS | `EJERCICIO` + `NUM_PED` | `EJERCICIO` + `NUM_PED` | Líneas del pedido |
| 3 | SOLIC_GASTOS | PEDIDOS | `EJERCICIO` + `NRO_PED` | `EJERCICIO` + `NUM_PED` | Solicitud que formaliza el pedido *(NRO_PED → NUM_PED, nombres distintos)* |
| 4 | SOLIC_GASTOS | JURISDICCIONES | `JURISDICCION` | `JURISDICCION` | Jurisdicción de la solicitud |
| 5 | SOLIC_GASTOS | PROVEEDORES | `OP_COD_PROV` | `COD_PROV` | Proveedor asociado a la solicitud |
| 6 | ORDEN_COMPRA | PROVEEDORES | `COD_PROV` | `COD_PROV` | Proveedor al que se le compra |
| 7 | OC_ITEMS | ORDEN_COMPRA | `EJERCICIO` + `UNI_COMPRA` + `NRO_OC` | `EJERCICIO` + `UNI_COMPRA` + `NRO_OC` | Líneas de la OC |
| 8 | OC_ITEMS | SOLIC_GASTOS | `EJERCICIO` + `DELEG_SOLIC` + `NRO_SOLIC` | `EJERCICIO` + `DELEG_SOLIC` + `NRO_SOLIC` | Vincula cada ítem de OC con su solicitud de gasto |
| 9 | OC_ITEMS | PROVEEDORES | `COD_PROV` | `COD_PROV` | Proveedor a nivel ítem (desnormalizado) |
| 10 | ORDEN_PAGO | SOLIC_GASTOS | `EJERCICIO` + `SG_DELEG_SOLIC` + `SG_NRO_SOLIC` | `EJERCICIO` + `DELEG_SOLIC` + `NRO_SOLIC` | Solicitud que origina el pago *(prefijo SG_ en los nombres)* |
| 11 | ORDEN_PAGO | ORDEN_COMPRA | `RECO_DEU_COMPRA_EJER` + `RECO_DEU_COMPRA` | `EJERCICIO` + `NRO_OC` | OC que se está pagando *(falta confirmar UNI_COMPRA)* |
| 12 | ORDEN_PAGO | PROVEEDORES | `COD_PROV` | `COD_PROV` | Proveedor que cobra |
| 13 | ORDEN_PAGO | JURISDICCIONES | `JURISDICCION` | `JURISDICCION` | Jurisdicción que paga |

### 1.3 Etapas del ciclo

| Etapa | Tabla RAFAM | PK | Qué pasa |
|-------|------------|-----|----------|
| 1. Pedido | `PEDIDOS` | `EJERCICIO` + `NUM_PED` | Una jurisdicción genera un pedido interno con sus ítems (`PED_ITEMS`) |
| 2. Solicitud de gasto | `SOLIC_GASTOS` | `EJERCICIO` + `DELEG_SOLIC` + `NRO_SOLIC` | Se formaliza el pedido como solicitud presupuestaria; se asigna proveedor |
| 3. Orden de compra | `ORDEN_COMPRA` | `EJERCICIO` + `UNI_COMPRA` + `NRO_OC` | Se emite la OC al proveedor; sus ítems (`OC_ITEMS`) referencian la solicitud de gasto |
| 4. Orden de pago | `ORDEN_PAGO` | `EJERCICIO` + `NRO_OP` | Se paga al proveedor; referencia tanto la solicitud de gasto como la OC |

> `EJERCICIO` (año fiscal) es el hilo conductor que atraviesa **todas** las tablas del flujo.

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
OC (compras_pedidos.gasto_id) ──HABTM──► Gasto ◄──HABTM (account_egresos_gastos)── Egreso (OP)
```

- **OC→Gasto**: se establece enviando `gasto_ids` en el payload de la OC
- **Gasto→OC**: no hay forma desde `_importGasto`
- **OP→Gasto**: se establece enviando `gasto_ids` en el payload de la OP

### 2.2 Cadena de vínculos en RAFAM (fuente)

```
OC_ITEMS ──(DELEG_SOLIC, NRO_SOLIC)──► SOLIC_GASTOS ◄──(SG_DELEG_SOLIC, SG_NRO_SOLIC)── ORDEN_PAGO
                                              ▲
                         ORDEN_PAGO.RECO_DEU_COMPRA ──► ORDEN_COMPRA.NRO_OC (nexo OP↔OC)
```

El Gasto (`SOLIC_GASTOS`) es el puente entre OC y OP. La FK de `OC_ITEMS` a `SOLIC_GASTOS` permite resolver qué gastos pertenecen a cada OC.

**Resolución de gasto_refs para OP** — tres niveles de fallback:

1. **SG directo:** `ORDEN_PAGO.SG_DELEG_SOLIC` + `SG_NRO_SOLIC` matchea SOLIC_GASTOS (~5% de OPs).
2. **CTA_HOJA_DE_RUTA JOIN** (solo Oracle): vista desnormalizada que consolida PE→SG→OC→OP. LEFT JOIN en `source_repository` agrega `HDR_SG_NRO`, `HDR_SG_DELEG`, `HDR_OC_NRO_OC`. No existe en SQLite dev.
3. **RECO_DEU_COMPRA → OC link_store** (~85% de OPs): `RECO_DEU_COMPRA` = `NRO_OC` de la OC que se paga. Se buscan los `gasto_refs` ya persistidos de esa OC en `entity_link_store`. Funciona tanto en Oracle como SQLite.

> `NRO_CANCE` NO es el nexo OP↔OC. Su uso principal es para RETENCIONES.

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
  "rubros": [],
  "clasificaciones": [],
  "proveedores": [],
  "pedidos": [],
  "ordenes_compra": [],
  "gastos": [],
  "ordenes_pago": []
}
```

**Orden interno de procesamiento** (hardcodeado): `rubros → clasificaciones → proveedores → pedidos → ordenes_compra → gastos → ordenes_pago`. Se pueden enviar todas en un solo payload.

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

### 5.2 Pedidos y OCs (`compras_pedidos`)

Pedidos y Órdenes de Compra comparten la misma tabla, diferenciados por `tipo`.

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
| `unidad_de_medida_id` | int | NO | Resolver por link/lookup; no asumir que el default del tenant es "Unidad" |
| `cantidad` | decimal(10,2) | NO | Obligatorio |
| `observacion` | text | SÍ | |
| `recibida_unidad_de_medida_id` | int | SÍ | |
| `recibida_cantidad` | decimal(10,2) | SÍ | |
| `precio` | decimal(14,2) | SÍ | |
| `deleted` | tinyint(1) | — | default 0 |

**Validaciones server-side**: Sin validaciones en el modelo ($validate = array()). Controller valida: items no vacío, cada item requiere `mercaderia_id` o `mercaderia_external_ref` + `cantidad`.

**Mercadería auto-creación**: con `mercaderia_external_ref` y `auto_create_mercaderia=true` (default), Paxapos crea automáticamente Producto + Mercadería con `barcode = 'RAFAM:{sha1(ref)}'`. El nombre se genera como `"{descripcion} [RAFAM-{hash10}]"`.

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

**NO necesita que la OC ya exista**. El gasto es independiente; el vínculo Gasto↔OC solo se establece desde el lado de la OC (via `gasto_ids`).

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

**Campos obligatorios**: `identificador_pago`, `total`, `gasto_ids` (array con al menos 1 ID).

**Upsert**: por `identificador_pago`. Si ya existe → `skip_existing` (NO actualiza, solo devuelve el existente). No hay forma de hacer N→C post-creación.

**Usa `gasto_ids`** (IDs numéricos internos de Paxapos). Alternativa: `gasto_external_ids` para resolver automáticamente buscando traza `RAFAM:{...}` en `Gasto.observacion`.

**Allowed fields** del save: `identificador_pago, fecha, tipo_de_pago_id, total, observacion, estado, fecha_programada, cuenta_bancaria_id, numero_operacion`. Notar que `proveedor_id` NO está en la whitelist.

**Feature flag**: `Site.ordenes_de_pago` debe estar en `true`. Si no → HTTP 400. Verificar llamando con bloque `ordenes_pago` vacío en `dry_run`.

**Omitir OPs con `ESTADO_OP=A`** del envío — no existe estado "Anulado" en Paxapos.

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

> Esta tabla corresponde a seeds legacy donde `id=1` es "Planta" y `id=5` es "Unidad". No asumir que esos IDs son iguales en todos los tenants: confirmar con `GET /{tenant}/rafam/migracion/lookups.json?only=unidades_de_medida` o `make migrator-lookups` y configurar `PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID`.

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
| Pedidos/OCs | `internal_id` | **Actualiza** cabecera, **reemplaza** todos los items (delete+insert) | `update` |
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
      { "success": true, "external_id": {...}, "id": 789, "mode": "create", "items": 2, "internal_id": "rafam-oc-...", "public_url": "https://...", "gasto_ids": [1] }
    ]
  }
}
```

### 9.2 Errores parciales (HTTP 207 Multi-Status)

```json
{
  "success": false,
  "errors": [
    { "section": "pedidos", "index": 0, "external_id": {...}, "message": "Pedido sin items" }
  ],
  "results": {
    "pedidos": [
      { "success": false, "external_id": {...}, "message": "Pedido sin items" }
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
1. jurisdicciones → escribe `rubro` + `clasificacion` en entity_link_store
2. proveedores    → escribe `proveedores` en entity_link_store
3. ped_items      → lee `rubro` + escribe `pedido` (solicitudes de bienes)
4. oc_items       → lee `rubro` + `proveedores` + escribe `orden_compra`
5. solic_gastos   → lee `clasificacion` + `proveedores` + escribe `gasto`
6. orden_pago     → lee `gasto` + escribe `orden_pago`
```

> El orden es **estricto**. Cada entidad depende de que las anteriores ya hayan sido importadas y sus IDs remotos guardados en el entity_link_store.

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

### 12.2 Jurisdicciones → Rubros + Clasificaciones

```json
{
  "rubros": [{
    "external_id": { "jurisdiccion": "JURISDICCION" },
    "Rubro": { "name": "DENOMINACION o JURISDICCION" }
  }],
  "clasificaciones": [{
    "external_id": { "jurisdiccion": "JURISDICCION" },
    "Clasificacion": { "name": "DENOMINACION o JURISDICCION", "parent_id": null }
  }]
}
```

### 12.3 Pedidos

```json
{
  "external_id": { "ejercicio": int, "num_ped": int },
  "Pedido": {
    "internal_id": "rafam-ped-{ejercicio}-{num_ped}",
    "tipo": "solicitud",
    "observacion": "Migrado RAFAM PED {ejercicio}-{num_ped}",
    "monto_presupuestado": float(PED_COSTO_TOT)
  },
  "items": [{
    "mercaderia_external_ref": { "source": "rafam", "entity": "ped_items", "ejercicio": ..., "num_ped": ..., "orden": ... },
    "cantidad": float(CANTIDAD),
    "precio": float(COSTO_UNI),
    "unidad_de_medida_id": 5,
    "descripcion": "DESCRIP_BIE (max 255)",
    "observacion": "DESCRIP_BIE"
  }]
}
```

### 12.4 Órdenes de Compra

```json
{
  "external_id": { "ejercicio": int, "uni_compra": int, "nro_oc": int },
  "Pedido": {
    "internal_id": "rafam-oc-{ejercicio}-{uni_compra}-{nro_oc}",
    "tipo": "orden_compra",
    "proveedor_id": int(lookup COD_PROV),
    "observacion": "Migrado RAFAM OC {ejercicio}-{uni_compra}-{nro_oc}"
  },
  "items": [{
    "mercaderia_external_ref": { "source": "rafam", "entity": "oc_items", ... },
    "cantidad": float(CANTIDAD),
    "precio": float(IMP_UNITARIO),
    "recibida_cantidad": float(CANT_RECIB),
    "unidad_de_medida_id": 5
  }]
}
```

### 12.5 Gastos (Solicitudes de Gasto)

```json
{
  "external_id": { "rafam_ref": "SG-{ejercicio}-{deleg_solic}-{nro_solic}" },
  "Gasto": {
    "fecha": "YYYY-MM-DD",
    "importe_total": float(IMPORTE_TOT),
    "importe_neto": float(IMPORTE_TOT),
    "punto_de_venta": "RAFAM",
    "tipo_factura_id": int(lookup TIPO_DOC),
    "factura_nro": "NRO_DOC (zero-pad 8)",
    "clasificacion_id": int(lookup JURISDICCION en entity_link_store),
    "fecha_vencimiento": "FECH_NECESIDAD o FECH_ENTREGA",
    "observacion": "opcional"
  }
}
```

### 12.6 Órdenes de Pago

```json
{
  "external_id": { "ejercicio": int, "nro_op": int },
  "Egreso": {
    "identificador_pago": "RAFAM-OP-{ejercicio}-{nro_op}",
    "total": float(IMPORTE_TOTAL),
    "tipo_de_pago_id": int(PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID),
    "estado": 3,
    "fecha": "FECH_CONFIRM o FECH_OP (solo si ESTADO_OP='C')"
  },
  "gasto_external_ids": ["SG-{ej}-{deleg}-{nro}"]
}
```

> OPs con `ESTADO_OP='A'` (anuladas) se omiten completamente del envío.

---

## 13. Variables de entorno relevantes

| Variable | Uso | Default |
|----------|-----|---------|
| `PAXAPOS_URL` | URL base del server Paxapos | (requerida) |
| `PAXAPOS_TENANT` | Tenant ID | (requerida) |
| `PAXAPOS_API_KEY` | API key para auth | (requerida) |
| `PAXAPOS_RAFAM_IMPORT_PATH` | Path relativo del importador RAFAM dentro de Paxapos | `rafam/migracion/importar.json` |
| `PAXAPOS_RAFAM_SPEC_PATH` | Path relativo de spec RAFAM dentro de Paxapos | `rafam/migracion/spec.json` |
| `PAXAPOS_RAFAM_LOOKUPS_PATH` | Path relativo de lookups RAFAM dentro de Paxapos | `rafam/migracion/lookups.json` |
| `PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID` | ID unidad de medida Paxapos default | Verificar contra `lookups`; ejemplo `.env`: `1` |
| `PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID` | ID tipo factura Paxapos default | (vacío) |
| `PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID` | ID tipo de pago Paxapos default | `1` |
| `RAFAM_SYNC_BATCH_DELAY_SECONDS` | Delay local entre batches | `2` |
| `PAXAPOS_VERIFY_SSL` | Verificación SSL | `false` en dev |
| `PAXAPOS_TIMEOUT_SECONDS` | Timeout HTTP | `20` |

---

## 14. Gotchas y comportamientos no obvios

Reglas que no se deducen de la documentación estándar pero causan bugs si se ignoran.

### 14.1 Unidad de medida default depende del tenant

No asumir que `id=1` es "Unidad" en todos los tenants. En seeds legacy de gastronomía, `id=1` era **"Planta"** y **"Unidad" era `id=5`**. El script resuelve primero por `link_unidad_medida`, luego por lookup remoto con nombre `Unidad`, luego usa `PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID` y finalmente fallback interno. Antes de una importación real, consultar `make migrator-lookups` y configurar `PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID` con el ID correcto del tenant.

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

### 14.7 `gasto_external_ids` busca por LIKE en `observacion`

Resuelve buscando la traza `RAFAM:{json}` que el propio migrador graba en `Gasto.observacion`. Funciona tanto en requests separados (gastos primero, OPs después) como en el mismo request (el orden interno garantiza que gastos se graban antes que OPs).

### 14.8 `mercaderia_external_ref` agrupa por clasificación presupuestaria

Si dos items de pedidos distintos tienen la misma clasificación presupuestaria RAFAM (mismos `clase`, `tipo`, `inciso`, `par_prin`, `par_parc`), Paxapos los **agrupa en la misma Mercadería**. Usa los campos de clasificación (no `ejercicio`/`num_ped`/`orden`) como clave de dedup. Esto es intencional para evitar duplicados de mercaderías.

### 14.9 `monto_presupuestado` se auto-calcula si no se envía

Si no se incluye `monto_presupuestado` en el payload del Pedido/OC, Paxapos lo calcula como `sum(precio * cantidad)` de todos los items. Si se necesita un valor específico (ej: monto aprobado RAFAM distinto al calculado), enviarlo explícitamente.

### 14.10 La tabla `tipo_facturas` varía por tenant

El seed base tiene ~33 tipos, pero cada tenant puede tener tipos adicionales o distintos. **Siempre usar el endpoint `lookups.json?only=tipos_factura`** del tenant destino para mapear. No hardcodear IDs.

### 14.11 `internal_id` auto-generado es determinístico

Si no se envía `Pedido.internal_id` pero sí `external_id` con los campos esperados, el controller genera:
- Solicitudes: `rafam-ped-{ejercicio}-{num_ped}`
- OCs: `rafam-oc-{ejercicio}-{uni_compra}-{nro_oc}`

Si se quiere control total del upsert, enviar `internal_id` propio. Si no, dejar que lo genere pero asegurar que `external_id` tenga los campos necesarios.

### 14.12 Validación `gastos_pagos` deshabilitada durante import masivo

El check normal verifica que los gastos no estén ya pagados, pero con datasets grandes revienta memoria. El migrador lo bypasea. Esto significa que **se puede crear una OP que pague un gasto ya pagado** — no da error pero contablemente queda mal. **Validar del lado del script** que no se dupliquen pagos.

### 14.13 Sin rollback parcial sin `atomic=true`

Si se envían 100 proveedores y el #50 falla, los primeros 49 ya están grabados. Con `atomic=true` se revierte todo. **Para migración inicial usar `atomic=false`** (más resiliente); **para correcciones puntuales usar `atomic=true`**.

### 14.14 Endpoint de dedup de proveedores disponible

`GET /{tenant}/account/proveedores/check_duplicados/{id}.json` detecta proveedores duplicados post-migración usando similitud de nombre + CUIT. Útil para auditoría después de la carga inicial.

### 14.15 Orden de importación es crítico — mismo request o requests separados

El orden interno de procesamiento es: `rubros → clasificaciones → proveedores → pedidos → ordenes_compra → gastos → ordenes_pago`. Si se envía todo en un solo request, el controller respeta este orden automáticamente. Si se hacen requests separados, **respetar la secuencia estrictamente** para que las FKs se resuelvan.
