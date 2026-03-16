# Esquema RAFAM — `OWNER_RAFAM`

> ⚠️ Este archivo es una plantilla inicial basada en las tablas conocidas del extractor.
> **Regenerar con valores reales** ejecutando:
> ```bash
> python scripts/explore_schema.py
> ```
> El script reemplazará este contenido con la estructura exacta del servidor Oracle.

---

## Índice de tablas

- [PROVEEDORES](#proveedores)
- [JURISDICCIONES](#jurisdicciones)
- [PEDIDOS](#pedidos)
- [PED_ITEMS](#ped_items)
- [SOLIC_GASTOS](#solic_gastos)
- [ORDEN_COMPRA](#orden_compra)
- [OC_ITEMS](#oc_items)
- [ORDEN_PAGO](#orden_pago)

---

## PROVEEDORES

**PK:** *(pendiente — ejecutar explore_schema.py)*
**FK:** *(pendiente)*

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV` | *(pendiente)* | ✗ | | Código único del proveedor |
| `CUIT` | *(pendiente)* | ✗ | | CUIT del proveedor |
| `RAZON_SOCIAL` | *(pendiente)* | ✗ | | Razón social |
| `COD_ESTADO` | *(pendiente)* | ✓ | | Estado del proveedor |
| *(completar con explore_schema.py)* | | | | |

---

## JURISDICCIONES

**PK:** *(pendiente)*

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| *(completar con explore_schema.py)* | | | | |

---

## PEDIDOS

**PK:** *(pendiente)*

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `NRO_PEDIDO` | *(pendiente)* | ✗ | | Número de pedido |
| *(completar con explore_schema.py)* | | | | |

---

## PED_ITEMS

**PK:** *(pendiente)*
**FK:** `NRO_PEDIDO` → `OWNER_RAFAM.PEDIDOS`

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| *(completar con explore_schema.py)* | | | | |

---

## SOLIC_GASTOS

**PK:** *(pendiente)*
**FK:** `NRO_PEDIDO` → `OWNER_RAFAM.PEDIDOS`

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| *(completar con explore_schema.py)* | | | | |

---

## ORDEN_COMPRA

**PK:** *(pendiente)*
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV` | *(pendiente)* | ✓ | | Código proveedor (FK) |
| `CUIT` | *(pendiente)* | ✓ | | CUIT (desnormalizado) |
| `ESTADO_PROVEEDOR` | *(pendiente)* | ✓ | | Estado del proveedor |
| *(completar con explore_schema.py)* | | | | |

---

## OC_ITEMS

**PK:** *(pendiente)*
**FK:** *(pendiente — probablemente → ORDEN_COMPRA)*

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| *(completar con explore_schema.py)* | | | | |

---

## ORDEN_PAGO

**PK:** *(pendiente)*

> **Estados ESTADO_OP:** `C` = Cancelada/pagada · `A` = Anulada · `N` = Normal/no pagada

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| *(completar con explore_schema.py)* | | | | |
