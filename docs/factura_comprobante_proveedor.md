# Factura o comprobante presentado por el proveedor

Este documento resume de donde deberia salir el numero de factura o comprobante presentado por un proveedor en RAFAM, y como se relaciona con la orden de compra, la hoja de ruta y el pago.

## Resumen corto

Para obtener la factura real asociada a una orden de compra, el camino recomendado es:

```text
ORDEN_COMPRA
  -> REG_COMP
  -> CTA_COMPROB
```

- `ORDEN_COMPRA` identifica la compra y el proveedor adjudicado.
- `REG_COMP` registra el comprobante en RAFAM y conserva el vinculo con la OC.
- `CTA_COMPROB` contiene el comprobante fiscal presentado por el proveedor, incluyendo `NRO_COMPROB`.
- `CTA_HOJA_DE_RUTA` puede verse como una vista operativa/desnormalizada del circuito, util para seguir el recorrido entre pedido, solicitud de gasto, OC, comprobante y pago.
- `ORDEN_PAGO` representa el pago y se vincula con el gasto/comprobante por la cadena de solicitud de gasto, registro de comprobante o referencias de OC, segun el caso.

## Tablas principales

| Etapa | Tabla | Campos clave | Uso |
|---|---|---|---|
| Orden de compra | `ORDEN_COMPRA` | `EJERCICIO`, `UNI_COMPRA`, `NRO_OC`, `COD_PROV` | Documento contractual de compra y proveedor adjudicado. |
| Items de OC | `OC_ITEMS` | `EJERCICIO`, `UNI_COMPRA`, `NRO_OC`, `DELEG_SOLIC`, `NRO_SOLIC` | Nexo entre la OC y la solicitud de gasto. |
| Solicitud de gasto | `SOLIC_GASTOS` | `EJERCICIO`, `DELEG_SOLIC`, `NRO_SOLIC` | Gasto presupuestario que origina o respalda la OC. |
| Registro de comprobante | `REG_COMP` | `EJERCICIO`, `NRO_REG_COMP`, `UNI_COMPRA`, `NRO_OC`, `COD_PROV` | Registro RAFAM del comprobante. Es el puente entre OC y comprobante. |
| Comprobante proveedor | `CTA_COMPROB` | `EJERCICIO`, `TIPO`, `NRO_COMPROB`, `COD_PROV`, `NRO_REG_COMP` | Comprobante/factura presentada por el proveedor. |
| Hoja de ruta | `CTA_HOJA_DE_RUTA` | `OC_*`, `RC_*`, `CC_*`, `OP_*` | Vista del recorrido administrativo completo. |
| Orden de pago | `ORDEN_PAGO` | `EJERCICIO`, `NRO_OP`, `COD_PROV`, `NRO_REG_COMP`, `SG_DELEG_SOLIC`, `SG_NRO_SOLIC`, `RECO_DEU_COMPRA` | Pago asociado al proveedor y a los gastos/comprobantes. |

## Donde esta el numero de factura

El numero mas confiable para la factura o comprobante presentado por el proveedor esta en:

```text
CTA_COMPROB.NRO_COMPROB
```

Ejemplos de formato encontrados en los snapshots:

```text
0009-00014669
0002-00000570
```

Ese campo conserva el numero completo del comprobante, normalmente con punto de venta y numero. La tabla tambien aporta:

| Campo | Significado |
|---|---|
| `TIPO` | Tipo de comprobante, por ejemplo factura A/B u otro codigo RAFAM. |
| `NRO_COMPROB` | Numero completo del comprobante presentado. |
| `COD_PROV` | Proveedor asociado al comprobante. |
| `COD_PROV_REAL` | Proveedor real, cuando RAFAM lo informa separado del proveedor principal. |
| `NRO_REG_COMP` | Registro de comprobante al que pertenece. |
| `FECH_COMPROB` | Fecha del comprobante. |
| `FECH_VENCIM` | Fecha de vencimiento. |
| `IMPORTE_COMPR` | Importe del comprobante. |
| `IMPORTE_PAGADO` | Importe ya pagado. |

## Relacion con la orden de compra

La orden de compra no guarda por si sola el numero fiscal de factura. La relacion aparece al pasar por `REG_COMP`:

```text
ORDEN_COMPRA.EJERCICIO   = REG_COMP.EJERCICIO
ORDEN_COMPRA.UNI_COMPRA  = REG_COMP.UNI_COMPRA
ORDEN_COMPRA.NRO_OC      = REG_COMP.NRO_OC
ORDEN_COMPRA.COD_PROV    = REG_COMP.COD_PROV
```

Luego, desde el registro de comprobante se llega al comprobante presentado:

```text
REG_COMP.EJERCICIO       = CTA_COMPROB.EJERCICIO
REG_COMP.NRO_REG_COMP    = CTA_COMPROB.NRO_REG_COMP
```

Consulta base para obtener la factura de una OC:

```sql
SELECT
    rc.EJERCICIO,
    rc.UNI_COMPRA,
    rc.NRO_OC,
    rc.COD_PROV,
    rc.NRO_REG_COMP,
    cc.TIPO,
    cc.NRO_COMPROB,
    cc.FECH_COMPROB,
    cc.FECH_VENCIM,
    cc.IMPORTE_COMPR,
    cc.IMPORTE_PAGADO
FROM OWNER_RAFAM.REG_COMP rc
JOIN OWNER_RAFAM.CTA_COMPROB cc
  ON cc.EJERCICIO = rc.EJERCICIO
 AND cc.NRO_REG_COMP = rc.NRO_REG_COMP
WHERE rc.EJERCICIO = :ejercicio
  AND rc.UNI_COMPRA = :uni_compra
  AND rc.NRO_OC = :nro_oc;
```

Si se quiere acotar por proveedor:

```sql
  AND rc.COD_PROV = :cod_prov
```

## Relacion con la hoja de ruta

`CTA_HOJA_DE_RUTA` funciona como una vista del recorrido administrativo. En el esquema real aparecen grupos de columnas con prefijos:

| Prefijo | Entidad representada | Ejemplos |
|---|---|---|
| `PE_` | Pedido | `PE_EJERCICIO`, `PE_NRO`, `PE_JURISDICCION` |
| `SG_` | Solicitud de gasto | `SG_EJERCICIO`, `SG_DELEG_SOLIC`, `SG_NRO` |
| `OC_` | Orden de compra | `OC_EJERCICIO`, `OC_UNI_COMPRA`, `OC_NRO`, `OC_COD_PROV` |
| `RC_` | Registro de comprobante | `RC_NRO`, `RC_NRO_OC`, `RC_COD_PROV` |
| `RD_` | Registro de devengado | `RD_NRO`, `RD_NRO_REG_COMP` |
| `CC_` | Comprobante de proveedor | `CC_TIPO_COMPROB`, `CC_NRO`, `CC_NRO_REG_COMP`, `CC_FECH_COMPROB` |
| `OP_` | Orden de pago | `OP_NRO`, `OP_COD_PROV`, `OP_ESTADO`, `OP_IMPORTE` |

Cuando esta vista tiene datos completos, permite consultar el circuito en una sola lectura:

```sql
SELECT
    OC_EJERCICIO,
    OC_UNI_COMPRA,
    OC_NRO,
    OC_COD_PROV,
    RC_NRO,
    CC_TIPO_COMPROB,
    CC_NRO,
    CC_FECH_COMPROB,
    OP_NRO,
    OP_ESTADO,
    OP_IMPORTE
FROM OWNER_RAFAM.CTA_HOJA_DE_RUTA
WHERE OC_EJERCICIO = :ejercicio
  AND OC_UNI_COMPRA = :uni_compra
  AND OC_NRO = :nro_oc;
```

Esta vista es especialmente util para auditoria y trazabilidad, pero para obtener el comprobante de forma robusta conviene mantener como fuente primaria el join `REG_COMP -> CTA_COMPROB`.

## Relacion con el pago

El pago vive en `ORDEN_PAGO`. Puede conectarse con la compra por mas de un camino, porque RAFAM no siempre carga todos los vinculos de la misma forma.

### Camino por solicitud de gasto

La OC llega a la solicitud de gasto por los items:

```text
ORDEN_COMPRA
  -> OC_ITEMS
  -> SOLIC_GASTOS
  -> ORDEN_PAGO
```

Vinculos principales:

```text
OC_ITEMS.EJERCICIO    = SOLIC_GASTOS.EJERCICIO
OC_ITEMS.DELEG_SOLIC  = SOLIC_GASTOS.DELEG_SOLIC
OC_ITEMS.NRO_SOLIC    = SOLIC_GASTOS.NRO_SOLIC

ORDEN_PAGO.EJERCICIO        = SOLIC_GASTOS.EJERCICIO
ORDEN_PAGO.SG_DELEG_SOLIC   = SOLIC_GASTOS.DELEG_SOLIC
ORDEN_PAGO.SG_NRO_SOLIC     = SOLIC_GASTOS.NRO_SOLIC
```

### Camino por registro de comprobante

Cuando la OP informa el registro de comprobante, el vinculo puede pasar por:

```text
ORDEN_PAGO.NRO_REG_COMP = REG_COMP.NRO_REG_COMP
ORDEN_PAGO.EJERCICIO    = REG_COMP.EJERCICIO
```

Este camino es util para validar que el pago corresponde al mismo comprobante que se obtuvo en `CTA_COMPROB`.

### Camino por referencia de OC

En algunos casos, `ORDEN_PAGO.RECO_DEU_COMPRA` referencia el numero de OC que se esta pagando:

```text
ORDEN_PAGO.RECO_DEU_COMPRA      -> ORDEN_COMPRA.NRO_OC
ORDEN_PAGO.RECO_DEU_COMPRA_EJER -> ORDEN_COMPRA.EJERCICIO
```

Este camino se usa como fallback cuando no alcanza el vinculo directo por solicitud de gasto o por hoja de ruta.

## Criterio recomendado para el mapeo

Para representar una factura de proveedor en Paxapos como `Gasto.factura_nro`, la fuente recomendada es:

```text
CTA_COMPROB.NRO_COMPROB
```

Con estos datos complementarios:

| Campo Paxapos | Fuente RAFAM recomendada |
|---|---|
| `factura_nro` | `CTA_COMPROB.NRO_COMPROB` |
| `punto_de_venta` | Parte izquierda de `NRO_COMPROB` si viene con formato `0002-00000570`; si no, usar criterio operativo definido. |
| `tipo_factura_id` | Resolver desde `CTA_COMPROB.TIPO` contra catalogo Paxapos. |
| `fecha` | `CTA_COMPROB.FECH_COMPROB` o `REG_COMP.FECH_REG_COMP` como fallback. |
| `fecha_vencimiento` | `CTA_COMPROB.FECH_VENCIM`. |
| `importe_total` | `CTA_COMPROB.IMPORTE_COMPR` o `REG_COMP.IMPORTE_TOT` como fallback. |
| `proveedor_id` | Preferir `CTA_COMPROB.COD_PROV_REAL` si existe; si no, `CTA_COMPROB.COD_PROV` / `REG_COMP.COD_PROV`. |

## Advertencias

- `SOLIC_GASTOS.NRO_DOC` existe y hoy aparece en algunos mapeos como origen de `factura_nro`, pero en los snapshots recientes aparece vacio o en cero. No parece ser la mejor fuente para la factura presentada por el proveedor.
- `REG_COMP.NRO_DOC` tambien existe, pero en los datos revisados suele venir vacio. `REG_COMP` es mas confiable como puente entre OC y comprobante que como fuente del numero fiscal completo.
- `CTA_HOJA_DE_RUTA` es muy util para explicar y auditar el circuito, pero no conviene depender exclusivamente de ella si se puede consultar `REG_COMP` y `CTA_COMPROB` directamente.
- El proveedor de la OC (`ORDEN_COMPRA.COD_PROV`) y el proveedor del comprobante (`CTA_COMPROB.COD_PROV` / `COD_PROV_REAL`) pueden diferir en casos administrativos. Para la factura, manda el proveedor del comprobante; para la compra, manda el proveedor adjudicado de la OC.

## Diagrama del circuito

```text
PEDIDOS
  |
  | EJERCICIO + NUM_PED/NRO_PED
  v
SOLIC_GASTOS
  ^
  | EJERCICIO + DELEG_SOLIC + NRO_SOLIC
  |
OC_ITEMS
  |
  | EJERCICIO + UNI_COMPRA + NRO_OC
  v
ORDEN_COMPRA
  |
  | EJERCICIO + UNI_COMPRA + NRO_OC
  v
REG_COMP
  |
  | EJERCICIO + NRO_REG_COMP
  v
CTA_COMPROB
  |
  | comprobante presentado por proveedor
  v
ORDEN_PAGO
```

La lectura funcional seria: la OC formaliza la compra, `REG_COMP` registra el comprobante asociado a esa OC, `CTA_COMPROB` guarda el numero real del comprobante/factura presentado por el proveedor, `CTA_HOJA_DE_RUTA` permite ver el recorrido completo y `ORDEN_PAGO` registra el pago aplicado a ese gasto/comprobante.