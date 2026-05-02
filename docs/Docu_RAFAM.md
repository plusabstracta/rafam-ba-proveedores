# RAFAM — Documentacion funcional de tablas y relaciones

---

## 1. Flujo funcional de compras

**Secuencia de etapas:**

```
Pedido (PEDIDOS + PED_ITEMS)
→ Solicitud de gasto (SOLIC_GASTOS)
→ Orden de compra (ORDEN_COMPRA + OC_ITEMS)
→ Orden de pago (ORDEN_PAGO)
```

El proceso de compras en RAFAM recorre cuatro etapas secuenciales. Cada etapa genera un documento formal que referencia al anterior mediante claves compuestas de ejercicio mas numero de comprobante.

### Etapa 1 — Pedido: PEDIDOS + PED_ITEMS

Representa la necesidad inicial de compra. Los items del pedido se almacenan en PED_ITEMS, relacionados por `EJERCICIO + NRO_PED`.

### Etapa 2 — Solicitud de gasto: SOLIC_GASTOS

Formaliza y autoriza el gasto a partir de un pedido. Se vincula con PEDIDOS mediante `EJERCICIO + NRO_PED = NRO_SOLIC`.

### Etapa 3 — Orden de compra: ORDEN_COMPRA + OC_ITEMS

Concreta la compra y define el proveedor adjudicado. OC_ITEMS actua como tabla nexo: cada item referencia tanto la OC cabecera como la solicitud de gasto que la origino.

### Etapa 4 — Orden de pago: ORDEN_PAGO

Registra el pago al proveedor. El estado `'C'` en `ESTADO_OP` indica que el pago fue efectivizado.

---

## 2. Diagrama Entidad-Relacion (DER)

El siguiente diagrama muestra todas las tablas del sistema RAFAM, sus atributos principales y las relaciones entre ellas. Las flechas indican la direccion de la referencia (FK hacia PK).

**Leyenda de colores:**
- Flujo principal
- Nexo / solicitudes
- Pago y retenciones
- Referencia
- Auxiliares

---

## 3. Tablas principales del flujo de compras

### PEDIDOS

| Campo | Tipo | Rol |
|---|---|---|
| EJERCICIO | int | PK |
| NRO_PED | int | PK |

### PED_ITEMS

| Campo | Tipo | Rol |
|---|---|---|
| EJERCICIO | int | FK |
| NRO_PED | int | FK |
| DESCRIPCION | string | |

### SOLIC_GASTOS

| Campo | Tipo | Rol |
|---|---|---|
| EJERCICIO | int | PK |
| DELEG_SOLIC | int | PK |
| NRO_SOLIC | int | PK |

### ORDEN_COMPRA

| Campo | Tipo | Rol |
|---|---|---|
| EJERCICIO | int | PK |
| UNI_COMPRA | int | PK |
| NRO_OC | int | PK |
| COD_PROV | string | FK |
| JURISDICCION | int | FK |

### OC_ITEMS

| Campo | Tipo | Rol |
|---|---|---|
| EJERCICIO | int | FK |
| UNI_COMPRA | int | FK |
| NRO_OC | int | FK |
| DELEG_SOLIC | int | FK |
| NRO_SOLIC | int | FK |
| DESCRIPCION | string | |

### ORDEN_PAGO

| Campo | Tipo | Rol |
|---|---|---|
| EJERCICIO | int | PK |
| NRO_OP | int | PK |
| ESTADO_OP | string | |
| NRO_CANCE | int | FK |
| COD_PROV | string | FK |
| JURISDICCION | int | FK |
| IMPORTE_TOTAL | float | |

---

## 4. Tablas auxiliares y de referencia

### PROVEEDORES

| Campo | Tipo | Rol |
|---|---|---|
| COD_PROV | string | PK |
| RAZON_SOCIAL | string | |
| CUIT | string | |
| EMAIL | string | |

### JURISDICCION

| Campo | Tipo | Rol |
|---|---|---|
| JURISDICCION | int | PK |
| DENOMINACION | string | |
| SELECCIONABLE | bool | |

### RG_COMP

| Campo | Tipo | Rol |
|---|---|---|
| NRO_REG_COMP | int | PK |
| EJERCICIO | int | FK |
| NRO_OC | int | FK |
| COD_PROV | string | FK |
| JURISDICCION | int | FK |
| FECHA_REG_COMP | date | |

### CTA_HOJA_DE_RUTA

| Campo | Tipo | Rol |
|---|---|---|
| EJERCICIO | int | FK |
| NRO_OC | int | FK |
| COD_PROV | string | FK |
| NRO_OP | int | FK |
| ESTADO_OP | string | |
| NRO_CANCE | int | FK |

### RETENCIONES

| Campo | Tipo | Rol |
|---|---|---|
| EJERCICIO | int | FK |
| NRO_CANCE | int | FK |
| COD_RET | string | FK |
| IMPORTE | float | |

### DEDUCCIONES

| Campo | Tipo | Rol |
|---|---|---|
| CODIGO | string | PK |
| DESCRIPCION | string | |
| EJERCICIO | int | |

---

## 5. Relaciones entre tablas

| Tabla origen | Tabla destino | Campos de join |
|---|---|---|
| PEDIDOS | SOLIC_GASTOS | `EJERCICIO + NRO_PED = NRO_SOLIC` |
| PEDIDOS | PED_ITEMS | `EJERCICIO + NRO_PED` |
| ORDEN_COMPRA | OC_ITEMS | `EJERCICIO + UNI_COMPRA + NRO_OC` |
| OC_ITEMS | SOLIC_GASTOS | `EJERCICIO + DELEG_SOLIC + NRO_SOLIC` |
| ORDEN_COMPRA | PROVEEDORES | `COD_PROV` |
| ORDEN_PAGO | PROVEEDORES | `COD_PROV` |
| ORDEN_COMPRA | JURISDICCION | `JURISDICCION` |
| ORDEN_PAGO | JURISDICCION | `JURISDICCION` |
| ORDEN_PAGO | RETENCIONES | `EJERCICIO + NRO_CANCE` |
| RETENCIONES | DEDUCCIONES | `COD_RET = CODIGO` |
| CTA_HOJA_DE_RUTA | ORDEN_COMPRA | `EJERCICIO + NRO_OC` |
| CTA_HOJA_DE_RUTA | ORDEN_PAGO | `EJERCICIO + NRO_OP` |
| RG_COMP | ORDEN_COMPRA | `EJERCICIO + NRO_OC` |

---

## 6. Reglas y consideraciones funcionales

### Proveedor oficial de la compra

El proveedor adjudicado siempre debe obtenerse de `ORDEN_COMPRA.COD_PROV`. Es el dato contractual del proceso.

> **Nota:** OC_ITEMS y ORDEN_PAGO tambien tienen COD_PROV, pero pueden diferir por ajustes o errores de carga. Tratar como datos secundarios.

### Estado de pago

Se lee desde `CTA_HOJA_DE_RUTA.ESTADO_OP` o `ORDEN_PAGO.ESTADO_OP`. El valor `'C'` indica pago efectivizado.

### OC_ITEMS como tabla nexo clave

OC_ITEMS es el unico punto donde se puede trazar la cadena completa desde la solicitud de gasto hasta la orden de compra. Sin esta tabla no es posible vincular ambos documentos.

### Retenciones

Las retenciones se vinculan a ORDEN_PAGO mediante `NRO_CANCE`. La descripcion se obtiene cruzando `RETENCIONES.COD_RET` con `DEDUCCIONES.CODIGO`.