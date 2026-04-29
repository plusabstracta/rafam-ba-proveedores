# Flujo funcional RAFAM y relaciones entre tablas

## 1. Flujo general de compras en RAFAM

El flujo de gestión de compras en RAFAM sigue la siguiente secuencia:

PEDIDO → SOLICITUD DE GASTO → ORDEN DE COMPRA → ORDEN DE PAGO

### Descripción de cada etapa

1. **PEDIDOS (PEDIDOS)**

   * Representa la necesidad inicial de compra.
   * Contiene los bienes o servicios requeridos.
   * Se relaciona con sus ítems en `PED_ITEMS`.

2. **SOLICITUD DE GASTO (SOLIC_GASTOS)**

   * Formaliza y autoriza el gasto a partir de un pedido.
   * Se vincula con `PEDIDOS` mediante:

     * `EJERCICIO` + `NRO_PED`

3. **ORDEN DE COMPRA (ORDEN_COMPRA)**

   * Es el documento donde se concreta la compra.
   * Define el proveedor adjudicado.
   * Se relaciona con:

     * `PROVEEDORES` mediante `COD_PROV`
     * `OC_ITEMS` mediante `EJERCICIO + UNI_COMPRA + NRO_OC`

   `OC_ITEMS` actúa como tabla nexo entre `ORDEN_COMPRA` y `SOLIC_GASTOS`:
   cada ítem de OC referencia tanto la OC cabecera (`EJERCICIO + UNI_COMPRA + NRO_OC`)
   como la solicitud de gasto que lo originó (`EJERCICIO + DELEG_SOLIC + NRO_SOLIC`).

4. **ORDEN DE PAGO (ORDEN_PAGO)**

   * Representa el pago al proveedor.
   * Puede vincularse indirectamente con la orden de compra o con la solicitud de gasto.

---

## 2. Relaciones principales entre tablas

* `PEDIDOS` → `SOLIC_GASTOS`

  * Por: `EJERCICIO + NUM_PED = NRO_PED`

* `ORDEN_COMPRA` → `OC_ITEMS`

  * Por: `EJERCICIO + UNI_COMPRA + NRO_OC`

* `OC_ITEMS` → `SOLIC_GASTOS`

  * Por: `EJERCICIO + DELEG_SOLIC + NRO_SOLIC`
  * OC_ITEMS es el nexo que vincula una OC con la solicitud de gasto que la originó

* `ORDEN_COMPRA` → `PROVEEDORES`

  * Por: `COD_PROV`

* `ORDEN_PAGO` → `PROVEEDORES`

  * Por: `COD_PROV`

---

## 3. Origen del proveedor (criterio funcional)

El proveedor oficial de una compra se obtiene de:

-> `ORDEN_COMPRA.COD_PROV`

Este es el dato que debe utilizarse como referencia principal, ya que:

* Define a quién se adjudica la compra
* Es el dato contractual del proceso

---

## 4. Consideraciones sobre inconsistencias

Se detectan diferencias de proveedor en distintas tablas:

* `OC_ITEMS.COD_PROV`

  * Puede diferir del proveedor de la orden de compra
  * No debe utilizarse como fuente principal

* `ORDEN_PAGO.COD_PROV`

  * Puede diferir del proveedor de la orden de compra
  * Puede deberse a ajustes administrativos o errores de carga

### Regla recomendada

* Tomar siempre como proveedor principal:
  -> `ORDEN_COMPRA.COD_PROV`

* En caso de diferencias:

  * Considerar `OC_ITEMS` y `ORDEN_PAGO` como datos secundarios
  * Tratar las discrepancias como excepciones a analizar

---

## 5. Resumen

* El flujo de RAFAM es:
     Pedido → Solicitud de gasto → Orden de compra → Pago

* La tabla clave del proceso es:
     `ORDEN_COMPRA`

* El proveedor oficial siempre debe obtenerse de:
     `ORDEN_COMPRA.COD_PROV`

* Diferencias en otras tablas no definen la compra, sino que representan posibles inconsistencias o casos particulares.
