# Mapeo de campos RAFAM → Paxapos

> Completar con los nombres de columna reales luego de ejecutar `scripts/explore_schema.py`
> y confirmar con el equipo RAFAM.

---

## 1. Proveedores

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| PROVEEDORES | COD_PROV | proveedores | id_externo | ninguna |
| PROVEEDORES | CUIT | proveedores | cuit | ninguna |
| PROVEEDORES | RAZON_SOCIAL | proveedores | razon_social | trim() |
| PROVEEDORES | COD_ESTADO | proveedores | estado | mapeo de código (ver nota 1) |
| PROVEEDORES | *(FECHA_ALTA?)* | proveedores | created_at | ninguna |
| PROVEEDORES | *(FECHA_MODIFICACION?)* | proveedores | updated_at | ninguna |

> **Nota 1 — estados de proveedor:** confirmar con el equipo los valores posibles de `COD_ESTADO`.

---

## 2. Jurisdicciones

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| JURISDICCIONES | *(COD_JURISDICCION?)* | jurisdicciones | id_externo | ninguna |
| JURISDICCIONES | *(NOMBRE?)* | jurisdicciones | nombre | trim() |
| JURISDICCIONES | *(completar)* | jurisdicciones | *(completar)* | |

---

## 3. Pedidos

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| PEDIDOS | NRO_PEDIDO | pedidos | numero_pedido | ninguna |
| PEDIDOS | *(COD_JURISDICCION?)* | pedidos | jurisdiccion_id | lookup por id_externo |
| PEDIDOS | *(FECHA_PEDIDO?)* | pedidos | fecha | ninguna |
| PEDIDOS | *(IMPORTE_TOTAL?)* | pedidos | importe_total | ninguna |
| PEDIDOS | *(ESTADO?)* | pedidos | estado | mapeo de código |
| PED_ITEMS | *(NRO_ITEM?)* | pedido_items | nro_item | ninguna |
| PED_ITEMS | *(DESCRIPCION?)* | pedido_items | descripcion | trim() |
| PED_ITEMS | *(CANTIDAD?)* | pedido_items | cantidad | ninguna |
| PED_ITEMS | *(PRECIO_UNIT?)* | pedido_items | precio_unitario | ninguna |

---

## 4. Solicitudes de gasto

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| SOLIC_GASTOS | *(NRO_SOLIC?)* | solicitudes_gasto | numero_solicitud | ninguna |
| SOLIC_GASTOS | NRO_PEDIDO | solicitudes_gasto | pedido_id | lookup por numero_pedido |
| SOLIC_GASTOS | *(FECHA?)* | solicitudes_gasto | fecha | ninguna |
| SOLIC_GASTOS | *(IMPORTE?)* | solicitudes_gasto | importe | ninguna |
| SOLIC_GASTOS | *(completar)* | solicitudes_gasto | *(completar)* | |

---

## 5. Órdenes de compra

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| ORDEN_COMPRA | *(NRO_OC?)* | ordenes_compra | numero_oc | ninguna |
| ORDEN_COMPRA | COD_PROV | ordenes_compra | proveedor_id | lookup por id_externo |
| ORDEN_COMPRA | CUIT | ordenes_compra | cuit_proveedor | ninguna (desnormalizado) |
| ORDEN_COMPRA | *(FECHA_OC?)* | ordenes_compra | fecha | ninguna |
| ORDEN_COMPRA | *(IMPORTE_TOTAL?)* | ordenes_compra | importe_total | ninguna |
| ORDEN_COMPRA | *(ESTADO?)* | ordenes_compra | estado | mapeo de código |
| OC_ITEMS | *(NRO_ITEM?)* | oc_items | nro_item | ninguna |
| OC_ITEMS | *(DESCRIPCION?)* | oc_items | descripcion | trim() |
| OC_ITEMS | *(CANTIDAD?)* | oc_items | cantidad | ninguna |
| OC_ITEMS | *(PRECIO_UNIT?)* | oc_items | precio_unitario | ninguna |

---

## 6. Órdenes de pago

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| ORDEN_PAGO | *(NRO_OP?)* | ordenes_pago | numero_op | ninguna |
| ORDEN_PAGO | *(NRO_OC?)* | ordenes_pago | orden_compra_id | lookup por numero_oc |
| ORDEN_PAGO | *(COD_PROV?)* | ordenes_pago | proveedor_id | lookup por id_externo |
| ORDEN_PAGO | *(FECHA_OP?)* | ordenes_pago | fecha | ninguna |
| ORDEN_PAGO | *(IMPORTE?)* | ordenes_pago | importe | ninguna |
| ORDEN_PAGO | ESTADO_OP | ordenes_pago | estado | C→pagada, A→anulada, N→pendiente |

---

## Notas generales

- Los campos marcados con `?` deben confirmarse con `scripts/explore_schema.py`.
- `trim()` se aplica a todos los campos de texto como limpieza defensiva.
- Los lookups asumen que la entidad padre ya fue sincronizada antes.
- Confirmar con el equipo Paxapos los nombres exactos de campos destino.
