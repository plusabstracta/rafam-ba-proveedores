# Esquema completo RAFAM — `default`

> Generado por `scripts/dump_full_schema.py` el 2026-07-17T14:58:33.695407Z
> Backend: `sqlite`
> **No editar manualmente** — regenerar ejecutando el script.

- Tablas: **19**
- Vistas: **1**

## Indice de tablas

- [ADJUDICACIONES](#adjudicaciones)
- [ADJUDICACIONES_ITEMS](#adjudicaciones_items)
- [CTA_COMPROB](#cta_comprob)
- [DEDUCCIONES](#deducciones)
- [GASTOS](#gastos)
- [JURISDICCIONES](#jurisdicciones)
- [OC_ITEMS](#oc_items)
- [ORDEN_COMPRA](#orden_compra)
- [ORDEN_PAGO](#orden_pago)
- [ORDEN_PAGO_DEDUC](#orden_pago_deduc)
- [ORDEN_PAGO_IMPUT](#orden_pago_imput)
- [PEDIDOS](#pedidos)
- [PED_ITEMS](#ped_items)
- [PROVEEDORES](#proveedores)
- [REG_COMP](#reg_comp)
- [RETENCIONES](#retenciones)
- [SOLIC_GASTOS](#solic_gastos)
- [SOLIC_GASTOS_ITEMS](#solic_gastos_items)
- [TIPOS_COMPROB](#tipos_comprob)

## Indice de vistas

- [CTA_HOJA_DE_RUTA](#view-cta_hoja_de_ruta)

---

## ADJUDICACIONES

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `NRO_ADJUDIC` | `TEXT` | ✓ |  |
| 3 | `NRO_COTI` | `TEXT` | ✓ |  |
| 4 | `DELEG_SOLIC` | `TEXT` | ✓ |  |
| 5 | `NRO_SOLIC` | `TEXT` | ✓ |  |
| 6 | `COD_PROV` | `TEXT` | ✓ |  |
| 7 | `FECH_ADJUD` | `TEXT` | ✓ |  |
| 8 | `TIPO_DOC_APROB` | `TEXT` | ✓ |  |
| 9 | `NRO_DOC_APROB` | `TEXT` | ✓ |  |
| 10 | `ANIO_DOC_APROB` | `TEXT` | ✓ |  |
| 11 | `ESTADO` | `TEXT` | ✓ |  |
| 12 | `FECH_ANUL` | `TEXT` | ✓ |  |
| 13 | `MOTIVO_ANUL` | `TEXT` | ✓ |  |
| 14 | `FECH_ENTREGA` | `TEXT` | ✓ |  |
| 15 | `OBSERVACIONES` | `TEXT` | ✓ |  |
| 16 | `COND_PAGO` | `TEXT` | ✓ |  |
| 17 | `DESC_COND_PAGO` | `TEXT` | ✓ |  |
| 18 | `NRO_LLAMADO` | `TEXT` | ✓ |  |
| 19 | `CERRADA` | `TEXT` | ✓ |  |

---

## ADJUDICACIONES_ITEMS

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `DELEG_SOLIC` | `TEXT` | ✓ |  |
| 3 | `NRO_SOLIC` | `TEXT` | ✓ |  |
| 4 | `NRO_COTI` | `TEXT` | ✓ |  |
| 5 | `COD_PROV` | `TEXT` | ✓ |  |
| 6 | `NRO_ADJUDIC` | `TEXT` | ✓ |  |
| 7 | `ITEM_REAL` | `TEXT` | ✓ |  |
| 8 | `NRO_ALTER` | `TEXT` | ✓ |  |
| 9 | `DESCRIPCION` | `TEXT` | ✓ |  |
| 10 | `COSTO_UNITARIO` | `TEXT` | ✓ |  |
| 11 | `ESPEC_TEC` | `TEXT` | ✓ |  |
| 12 | `CANTIDAD` | `TEXT` | ✓ |  |
| 13 | `CANT_ADJ` | `TEXT` | ✓ |  |
| 14 | `CANT_COTI` | `TEXT` | ✓ |  |
| 15 | `OBSERVACIONES` | `TEXT` | ✓ |  |
| 16 | `NRO_LLAMADO` | `TEXT` | ✓ |  |
| 17 | `PRECIO_MAXIMO` | `TEXT` | ✓ |  |

---

## CTA_COMPROB

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `TIPO` | `TEXT` | ✓ |  |
| 3 | `NRO_COMPROB` | `TEXT` | ✓ |  |
| 4 | `COD_PROV` | `TEXT` | ✓ |  |
| 5 | `NRO_REG_COMP` | `TEXT` | ✓ |  |
| 6 | `FECH_MOVIM` | `TEXT` | ✓ |  |
| 7 | `FECH_COMPROB` | `TEXT` | ✓ |  |
| 8 | `FECH_VENCIM` | `TEXT` | ✓ |  |
| 9 | `FECH_CONFORMAC` | `TEXT` | ✓ |  |
| 10 | `PORC_BONIF` | `TEXT` | ✓ |  |
| 11 | `FECH_BONIF` | `TEXT` | ✓ |  |
| 12 | `IMPORTE_COMPR` | `TEXT` | ✓ |  |
| 13 | `IMPORTE_PAGADO` | `TEXT` | ✓ |  |
| 14 | `RINDE_IVA` | `TEXT` | ✓ |  |
| 15 | `PORC_IVA` | `TEXT` | ✓ |  |
| 16 | `PORC_CRED_FISCAL` | `TEXT` | ✓ |  |
| 17 | `LIST_LIBRO_IVA` | `TEXT` | ✓ |  |
| 18 | `FECH_LIST_IVA` | `TEXT` | ✓ |  |
| 19 | `COD_PROV_REAL` | `TEXT` | ✓ |  |
| 20 | `RAZON_SOCIAL` | `TEXT` | ✓ |  |
| 21 | `CUIT` | `TEXT` | ✓ |  |
| 22 | `DETALLE` | `TEXT` | ✓ |  |
| 23 | `IMPORTE_SIN_IVA` | `TEXT` | ✓ |  |

---

## DEDUCCIONES

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `CODIGO` | `TEXT` | ✓ |  |
| 2 | `DESCRIPCION` | `TEXT` | ✓ |  |
| 3 | `TIPO_DEDUC` | `TEXT` | ✓ |  |
| 4 | `PORCENTAJE` | `TEXT` | ✓ |  |
| 5 | `SALDO` | `TEXT` | ✓ |  |
| 6 | `DECRIPCION_AB` | `TEXT` | ✓ |  |
| 7 | `CODIGO_AXT` | `TEXT` | ✓ |  |
| 8 | `EJERCICIO` | `TEXT` | ✓ |  |

---

## GASTOS

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `ANIO_PRESUP` | `TEXT` | ✓ |  |
| 2 | `INCISO` | `TEXT` | ✓ |  |
| 3 | `PAR_PRIN` | `TEXT` | ✓ |  |
| 4 | `PAR_PARC` | `TEXT` | ✓ |  |
| 5 | `PAR_SUBP` | `TEXT` | ✓ |  |
| 6 | `DENOMINACION` | `TEXT` | ✓ |  |
| 7 | `DENOMINACION_AB` | `TEXT` | ✓ |  |
| 8 | `TOTALIZADORA` | `TEXT` | ✓ |  |
| 9 | `FINALIDAD` | `TEXT` | ✓ |  |
| 10 | `FUNCION` | `TEXT` | ✓ |  |
| 11 | `SUBFUNCION` | `TEXT` | ✓ |  |
| 12 | `NO_CLASIF` | `TEXT` | ✓ |  |
| 13 | `CREDITO_INIC` | `TEXT` | ✓ |  |
| 14 | `CREDITO_MODIF` | `TEXT` | ✓ |  |
| 15 | `PREVENTIVO` | `TEXT` | ✓ |  |
| 16 | `COMPROMISO` | `TEXT` | ✓ |  |
| 17 | `DEVENGADO` | `TEXT` | ✓ |  |
| 18 | `PAGADO` | `TEXT` | ✓ |  |

---

## JURISDICCIONES

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `JURISDICCION` | `TEXT` | ✓ |  |
| 2 | `DENOMINACION` | `TEXT` | ✓ |  |
| 3 | `SELECCIONABLE` | `TEXT` | ✓ |  |
| 4 | `VIGENTE_DESDE` | `TEXT` | ✓ |  |
| 5 | `VIGENTE_HASTA` | `TEXT` | ✓ |  |

---

## OC_ITEMS

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `UNI_COMPRA` | `TEXT` | ✓ |  |
| 3 | `NRO_OC` | `TEXT` | ✓ |  |
| 4 | `ITEM_OC` | `TEXT` | ✓ |  |
| 5 | `DELEG_SOLIC` | `TEXT` | ✓ |  |
| 6 | `NRO_SOLIC` | `TEXT` | ✓ |  |
| 7 | `ITEM_REAL` | `TEXT` | ✓ |  |
| 8 | `DESCRIPCION` | `TEXT` | ✓ |  |
| 9 | `CANTIDAD` | `TEXT` | ✓ |  |
| 10 | `IMP_UNITARIO` | `TEXT` | ✓ |  |
| 11 | `CANT_RECIB` | `TEXT` | ✓ |  |
| 12 | `IMPORTE_EJER` | `TEXT` | ✓ |  |

---

## ORDEN_COMPRA

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `UNI_COMPRA` | `TEXT` | ✓ |  |
| 3 | `NRO_OC` | `TEXT` | ✓ |  |
| 4 | `NRO_ADJUD` | `TEXT` | ✓ |  |
| 5 | `FECH_OC` | `TEXT` | ✓ |  |
| 6 | `LUG_EMI` | `TEXT` | ✓ |  |
| 7 | `COD_PROV` | `TEXT` | ✓ |  |
| 8 | `COD_LUG_ENT` | `TEXT` | ✓ |  |
| 9 | `FECH_ENTREGA` | `TEXT` | ✓ |  |
| 10 | `ESTADO_OC` | `TEXT` | ✓ |  |
| 11 | `TIPO_DOC_APROB` | `TEXT` | ✓ |  |
| 12 | `NRO_DOC_APROB` | `TEXT` | ✓ |  |
| 13 | `ANIO_DOC_APROB` | `TEXT` | ✓ |  |
| 14 | `CONFIRMADO` | `TEXT` | ✓ |  |
| 15 | `FECH_CONFIRM` | `TEXT` | ✓ |  |
| 16 | `CANT_IMPRES` | `TEXT` | ✓ |  |
| 17 | `FECH_ANUL` | `TEXT` | ✓ |  |
| 18 | `MOTIVO_ANUL` | `TEXT` | ✓ |  |
| 19 | `OBSERVACIONES` | `TEXT` | ✓ |  |
| 20 | `IMPORTE_TOT` | `TEXT` | ✓ |  |
| 21 | `COND_PAGO` | `TEXT` | ✓ |  |
| 22 | `DESC_COND_PAGO` | `TEXT` | ✓ |  |
| 23 | `OC_DIFERIDO` | `TEXT` | ✓ |  |

---

## ORDEN_PAGO

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `NRO_OP` | `TEXT` | ✓ |  |
| 3 | `FECH_OP` | `TEXT` | ✓ |  |
| 4 | `LUG_EMI` | `TEXT` | ✓ |  |
| 5 | `CODIGO_FF` | `TEXT` | ✓ |  |
| 6 | `JURISDICCION` | `TEXT` | ✓ |  |
| 7 | `CODIGO_UE` | `TEXT` | ✓ |  |
| 8 | `COD_PROV` | `TEXT` | ✓ |  |
| 9 | `TIPO_OP` | `TEXT` | ✓ |  |
| 10 | `ESTADO_OP` | `TEXT` | ✓ |  |
| 11 | `TIPO_DOC` | `TEXT` | ✓ |  |
| 12 | `NRO_DOC` | `TEXT` | ✓ |  |
| 13 | `ANIO_DOC` | `TEXT` | ✓ |  |
| 14 | `NRO_CANCE` | `TEXT` | ✓ |  |
| 15 | `CONFIRMADO` | `TEXT` | ✓ |  |
| 16 | `FECH_CONFIRM` | `TEXT` | ✓ |  |
| 17 | `IMPORTE_TOTAL` | `TEXT` | ✓ |  |
| 18 | `IMPORTE_LIQUIDO` | `TEXT` | ✓ |  |
| 19 | `CANT_IMPRES` | `TEXT` | ✓ |  |
| 20 | `FECH_ANUL` | `TEXT` | ✓ |  |
| 21 | `MOTIVO_ANUL` | `TEXT` | ✓ |  |
| 22 | `CONCEPTO` | `TEXT` | ✓ |  |
| 23 | `OBSERVACIONES` | `TEXT` | ✓ |  |
| 24 | `COD_EMP` | `TEXT` | ✓ |  |
| 25 | `IMPORTE_BONIFICACION` | `TEXT` | ✓ |  |
| 26 | `IMPORTE_DEDUCCIONES` | `TEXT` | ✓ |  |
| 27 | `ASIENTO` | `TEXT` | ✓ |  |
| 28 | `ASIENTO_ANUL` | `TEXT` | ✓ |  |
| 29 | `MONTO_SIN_IVA` | `TEXT` | ✓ |  |
| 30 | `DEUDA` | `TEXT` | ✓ |  |
| 31 | `BLOQUEADA` | `TEXT` | ✓ |  |
| 32 | `RECURSO` | `TEXT` | ✓ |  |
| 33 | `PERCIBIDO` | `TEXT` | ✓ |  |
| 34 | `NO_PAGADO` | `TEXT` | ✓ |  |
| 35 | `PAGADO` | `TEXT` | ✓ |  |
| 36 | `RECO_DEU_ORDEN` | `TEXT` | ✓ |  |
| 37 | `RECO_DEU_EJERCICIO` | `TEXT` | ✓ |  |
| 38 | `RECO_DEU_COMPRA` | `TEXT` | ✓ |  |
| 39 | `RECO_DEU_COMPRA_EJER` | `TEXT` | ✓ |  |
| 40 | `F931` | `TEXT` | ✓ |  |
| 41 | `SICORE` | `TEXT` | ✓ |  |

---

## ORDEN_PAGO_DEDUC

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `NRO_OP` | `TEXT` | ✓ |  |
| 3 | `CODIGO_DEDUC` | `TEXT` | ✓ |  |
| 4 | `IMPORTE_RETEN` | `TEXT` | ✓ |  |
| 5 | `COMPROB_DEDUC` | `TEXT` | ✓ |  |
| 6 | `ALICUOTA` | `TEXT` | ✓ |  |
| 7 | `TIPO_GENERAC` | `TEXT` | ✓ |  |
| 8 | `CUENTA` | `TEXT` | ✓ |  |
| 9 | `COEF_CONV_MULTI` | `TEXT` | ✓ |  |
| 10 | `ACTIVIDAD` | `TEXT` | ✓ |  |
| 11 | `TIPO_ALICUOTA` | `TEXT` | ✓ |  |

---

## ORDEN_PAGO_IMPUT

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `NRO_OP` | `TEXT` | ✓ |  |
| 3 | `NRO_REG_COMP` | `TEXT` | ✓ |  |
| 4 | `TIPO_COMPROB` | `TEXT` | ✓ |  |
| 5 | `NRO_COMPROB` | `TEXT` | ✓ |  |
| 6 | `COD_PROV` | `TEXT` | ✓ |  |
| 7 | `CODIGO_FF` | `TEXT` | ✓ |  |
| 8 | `INCISO` | `TEXT` | ✓ |  |
| 9 | `PAR_PRIN` | `TEXT` | ✓ |  |
| 10 | `PAR_PARC` | `TEXT` | ✓ |  |
| 11 | `PAR_SUBP` | `TEXT` | ✓ |  |
| 12 | `JURISDICCION` | `TEXT` | ✓ |  |
| 13 | `PROGRAMA` | `TEXT` | ✓ |  |
| 14 | `ACTIV_PROY` | `TEXT` | ✓ |  |
| 15 | `ACTIV_OBRA` | `TEXT` | ✓ |  |
| 16 | `IMPORTE_IMPUT` | `TEXT` | ✓ |  |

---

## PEDIDOS

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `NUM_PED` | `TEXT` | ✓ |  |
| 3 | `LUG_EMI` | `TEXT` | ✓ |  |
| 4 | `FECH_EMI` | `TEXT` | ✓ |  |
| 5 | `NUM_PED_ORI` | `TEXT` | ✓ |  |
| 6 | `FECH_EMI_ORI` | `TEXT` | ✓ |  |
| 7 | `CODIGO_DEP` | `TEXT` | ✓ |  |
| 8 | `CODIGO_UE` | `TEXT` | ✓ |  |
| 9 | `JURISDICCION` | `TEXT` | ✓ |  |
| 10 | `COSTO_TOT` | `TEXT` | ✓ |  |
| 11 | `OBSERVACIONES` | `TEXT` | ✓ |  |
| 12 | `PED_ESTADO` | `TEXT` | ✓ |  |
| 13 | `CANT_IMP` | `TEXT` | ✓ |  |
| 14 | `FECH_MODI_ULT` | `TEXT` | ✓ |  |
| 15 | `CODIGO_FF` | `TEXT` | ✓ |  |
| 16 | `COD_LUG_ENT` | `TEXT` | ✓ |  |
| 17 | `PLAZO_ENT` | `TEXT` | ✓ |  |
| 18 | `PER_CONSUMO` | `TEXT` | ✓ |  |
| 19 | `FECH_ING_COMP` | `TEXT` | ✓ |  |
| 20 | `RESP_RETIRA_PED` | `TEXT` | ✓ |  |

---

## PED_ITEMS

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `NUM_PED` | `TEXT` | ✓ |  |
| 3 | `ORDEN` | `TEXT` | ✓ |  |
| 4 | `INCISO` | `TEXT` | ✓ |  |
| 5 | `PAR_PRIN` | `TEXT` | ✓ |  |
| 6 | `PAR_PARC` | `TEXT` | ✓ |  |
| 7 | `CLASE` | `TEXT` | ✓ |  |
| 8 | `TIPO` | `TEXT` | ✓ |  |
| 9 | `JURISDICCION` | `TEXT` | ✓ |  |
| 10 | `PROGRAMA` | `TEXT` | ✓ |  |
| 11 | `ACTIV_PROY` | `TEXT` | ✓ |  |
| 12 | `ACTIV_OBRA` | `TEXT` | ✓ |  |
| 13 | `CANTIDAD` | `TEXT` | ✓ |  |
| 14 | `UNI_MED` | `TEXT` | ✓ |  |
| 15 | `DESCRIP_BIE` | `TEXT` | ✓ |  |
| 16 | `COSTO_UNI` | `TEXT` | ✓ |  |

---

## PROVEEDORES

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `COD_PROV` | `TEXT` | ✓ |  |
| 2 | `RAZON_SOCIAL` | `TEXT` | ✓ |  |
| 3 | `TIPO_PROV` | `TEXT` | ✓ |  |
| 4 | `CUIT` | `TEXT` | ✓ |  |
| 5 | `FANTASIA` | `TEXT` | ✓ |  |
| 6 | `TIPO_SOC` | `TEXT` | ✓ |  |
| 7 | `COD_IVA` | `TEXT` | ✓ |  |
| 8 | `ING_BRUTOS` | `TEXT` | ✓ |  |
| 9 | `FECHA_ALTA` | `TEXT` | ✓ |  |
| 10 | `FECHA_ULT_COMP` | `TEXT` | ✓ |  |
| 11 | `CALIF_PROV` | `TEXT` | ✓ |  |
| 12 | `COD_ESTADO` | `TEXT` | ✓ |  |
| 13 | `CALLE_POSTAL` | `TEXT` | ✓ |  |
| 14 | `NRO_POSTAL` | `TEXT` | ✓ |  |
| 15 | `NRO_POSTAL_MED` | `TEXT` | ✓ |  |
| 16 | `PISO_POSTAL` | `TEXT` | ✓ |  |
| 17 | `DEPT_POSTAL` | `TEXT` | ✓ |  |
| 18 | `LOCA_POSTAL` | `TEXT` | ✓ |  |
| 19 | `COD_POSTAL` | `TEXT` | ✓ |  |
| 20 | `PROV_POSTAL` | `TEXT` | ✓ |  |
| 21 | `PAIS_POSTAL` | `TEXT` | ✓ |  |
| 22 | `CALLE_LEGAL` | `TEXT` | ✓ |  |
| 23 | `NRO_LEGAL` | `TEXT` | ✓ |  |
| 24 | `NRO_LEGAL_MED` | `TEXT` | ✓ |  |
| 25 | `PISO_LEGAL` | `TEXT` | ✓ |  |
| 26 | `DEPT_LEGAL` | `TEXT` | ✓ |  |
| 27 | `LOCA_LEGAL` | `TEXT` | ✓ |  |
| 28 | `COD_LEGAL` | `TEXT` | ✓ |  |
| 29 | `PROV_LEGAL` | `TEXT` | ✓ |  |
| 30 | `PAIS_LEGAL` | `TEXT` | ✓ |  |
| 31 | `NRO_PAIS_TE1` | `TEXT` | ✓ |  |
| 32 | `NRO_INTE_TE1` | `TEXT` | ✓ |  |
| 33 | `NRO_TELE_TE1` | `TEXT` | ✓ |  |
| 34 | `NRO_PAIS_TE2` | `TEXT` | ✓ |  |
| 35 | `NRO_INTE_TE2` | `TEXT` | ✓ |  |
| 36 | `NRO_TELE_TE2` | `TEXT` | ✓ |  |
| 37 | `NRO_PAIS_TE3` | `TEXT` | ✓ |  |
| 38 | `NRO_INTE_TE3` | `TEXT` | ✓ |  |
| 39 | `NRO_TELE_TE3` | `TEXT` | ✓ |  |
| 40 | `TE_CELULAR` | `TEXT` | ✓ |  |
| 41 | `FAX` | `TEXT` | ✓ |  |
| 42 | `EMAIL` | `TEXT` | ✓ |  |
| 43 | `OBSERVACION` | `TEXT` | ✓ |  |
| 44 | `PROV_CAJA_CHICA` | `TEXT` | ✓ |  |
| 45 | `NRO_HAB_MUN` | `TEXT` | ✓ |  |
| 46 | `DISC_RET_SUSS` | `TEXT` | ✓ |  |
| 47 | `DISC_GCIAS_UTE` | `TEXT` | ✓ |  |
| 48 | `DISC_IIBB_UTE` | `TEXT` | ✓ |  |

---

## REG_COMP

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `NRO_REG_COMP` | `TEXT` | ✓ |  |
| 3 | `FECH_REG_COMP` | `TEXT` | ✓ |  |
| 4 | `LUG_EMI` | `TEXT` | ✓ |  |
| 5 | `JURISDICCION` | `TEXT` | ✓ |  |
| 6 | `CODIGO_UE` | `TEXT` | ✓ |  |
| 7 | `COD_PROV` | `TEXT` | ✓ |  |
| 8 | `TIPO_REGIS` | `TEXT` | ✓ |  |
| 9 | `NRO_ORIG` | `TEXT` | ✓ |  |
| 10 | `CODIGO_FF` | `TEXT` | ✓ |  |
| 11 | `UNI_COMPRA` | `TEXT` | ✓ |  |
| 12 | `NRO_OC` | `TEXT` | ✓ |  |
| 13 | `DELEG_SOLIC` | `TEXT` | ✓ |  |
| 14 | `NRO_SOLIC` | `TEXT` | ✓ |  |
| 15 | `TIPO_DOC` | `TEXT` | ✓ |  |
| 16 | `NRO_DOC` | `TEXT` | ✓ |  |
| 17 | `ANIO_DOC` | `TEXT` | ✓ |  |
| 18 | `IMPORTE_TOT` | `TEXT` | ✓ |  |
| 19 | `ESTADO_REG_COMP` | `TEXT` | ✓ |  |
| 20 | `CONFIRMADO` | `TEXT` | ✓ |  |
| 21 | `FECH_CONFIRM` | `TEXT` | ✓ |  |
| 22 | `FECH_ANUL` | `TEXT` | ✓ |  |
| 23 | `MOTIVO_ANUL` | `TEXT` | ✓ |  |
| 24 | `CANT_IMPRES` | `TEXT` | ✓ |  |
| 25 | `CONCEPTO` | `TEXT` | ✓ |  |
| 26 | `FECH_RELOJ` | `TEXT` | ✓ |  |
| 27 | `DEUDA` | `TEXT` | ✓ |  |
| 28 | `DEPENDENCIA` | `TEXT` | ✓ |  |
| 29 | `INSISTIDO` | `TEXT` | ✓ |  |
| 30 | `RC_DIFERIDO` | `TEXT` | ✓ |  |
| 31 | `EJERCICIO_ANT` | `TEXT` | ✓ |  |
| 32 | `NRO_REG_COMP_ANT` | `TEXT` | ✓ |  |
| 33 | `RC_EJERCICIO_ANT` | `TEXT` | ✓ |  |

---

## RETENCIONES

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `NRO_CANCE` | `TEXT` | ✓ |  |
| 3 | `COD_RET` | `TEXT` | ✓ |  |
| 4 | `IMPORTE` | `TEXT` | ✓ |  |
| 5 | `CUENTA` | `TEXT` | ✓ |  |

---

## SOLIC_GASTOS

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `DELEG_SOLIC` | `TEXT` | ✓ |  |
| 3 | `NRO_SOLIC` | `TEXT` | ✓ |  |
| 4 | `NRO_PED` | `TEXT` | ✓ |  |
| 5 | `LUG_EMI` | `TEXT` | ✓ |  |
| 6 | `JURISDICCION` | `TEXT` | ✓ |  |
| 7 | `CODIGO_UE` | `TEXT` | ✓ |  |
| 8 | `CODIGO_DEP` | `TEXT` | ✓ |  |
| 9 | `FECH_SOLIC` | `TEXT` | ✓ |  |
| 10 | `TIPO_REGIS` | `TEXT` | ✓ |  |
| 11 | `NRO_ORIG` | `TEXT` | ✓ |  |
| 12 | `CODIGO_FF` | `TEXT` | ✓ |  |
| 13 | `IMPORTE_TOT` | `TEXT` | ✓ |  |
| 14 | `FECH_ENTREGA` | `TEXT` | ✓ |  |
| 15 | `FECH_NECESIDAD` | `TEXT` | ✓ |  |
| 16 | `FECH_EST_OC` | `TEXT` | ✓ |  |
| 17 | `TIPO_DOC` | `TEXT` | ✓ |  |
| 18 | `NRO_DOC` | `TEXT` | ✓ |  |
| 19 | `ANIO_DOC` | `TEXT` | ✓ |  |
| 20 | `COD_LUG_ENT` | `TEXT` | ✓ |  |
| 21 | `ESTADO_SOLIC` | `TEXT` | ✓ |  |
| 22 | `CONFIRMADO` | `TEXT` | ✓ |  |
| 23 | `FECH_CONFIRM` | `TEXT` | ✓ |  |
| 24 | `FECH_ANUL` | `TEXT` | ✓ |  |
| 25 | `MOTIVO_ANUL` | `TEXT` | ✓ |  |
| 26 | `OBSERVACIONES` | `TEXT` | ✓ |  |
| 27 | `CANT_IMP` | `TEXT` | ✓ |  |
| 28 | `SG_DIFERIDO` | `TEXT` | ✓ |  |

---

## SOLIC_GASTOS_ITEMS

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `EJERCICIO` | `TEXT` | ✓ |  |
| 2 | `DELEG_SOLIC` | `TEXT` | ✓ |  |
| 3 | `NRO_SOLIC` | `TEXT` | ✓ |  |
| 4 | `SOLIC_ITEM` | `TEXT` | ✓ |  |
| 5 | `INCISO` | `TEXT` | ✓ |  |
| 6 | `PAR_PRIN` | `TEXT` | ✓ |  |
| 7 | `PAR_PARC` | `TEXT` | ✓ |  |
| 8 | `PAR_SUBP` | `TEXT` | ✓ |  |
| 9 | `TIPO` | `TEXT` | ✓ |  |
| 10 | `CLASE` | `TEXT` | ✓ |  |
| 11 | `JURISDICCION` | `TEXT` | ✓ |  |
| 12 | `PROGRAMA` | `TEXT` | ✓ |  |
| 13 | `ACTIV_PROY` | `TEXT` | ✓ |  |
| 14 | `ACTIV_OBRA` | `TEXT` | ✓ |  |
| 15 | `DESCRIPCION` | `TEXT` | ✓ |  |
| 16 | `CODIGO_UM` | `TEXT` | ✓ |  |
| 17 | `CANTIDAD` | `TEXT` | ✓ |  |
| 18 | `IMP_UNITARIO` | `TEXT` | ✓ |  |
| 19 | `CANT_ADJ` | `TEXT` | ✓ |  |
| 20 | `CANT_COTI` | `TEXT` | ✓ |  |
| 21 | `CANTIDAD_REAL` | `TEXT` | ✓ |  |
| 22 | `IMP_UNITARIO_REAL` | `TEXT` | ✓ |  |
| 23 | `IMPORTE_EJER` | `TEXT` | ✓ |  |
| 24 | `IMPORTE_DIFER` | `TEXT` | ✓ |  |
| 25 | `IMPORTE_EJER_REAL` | `TEXT` | ✓ |  |
| 26 | `IMPORTE_DIFER_REAL` | `TEXT` | ✓ |  |

---

## TIPOS_COMPROB

**PK:** *(no encontrada)*

| # | Columna | Tipo | Nulo | Default |
|---|---------|------|------|---------|
| 1 | `TIPO` | `TEXT` | ✓ |  |
| 2 | `DESCRIPCION` | `TEXT` | ✓ |  |
| 3 | `IVA` | `TEXT` | ✓ |  |
| 4 | `DEBITO_CREDITO` | `TEXT` | ✓ |  |
| 5 | `FORMULA_NETO` | `TEXT` | ✓ |  |
| 6 | `RINDE_PERCEP` | `TEXT` | ✓ |  |

---

# Vistas

## VIEW CTA_HOJA_DE_RUTA <a id="view-cta_hoja_de_ruta"></a>

```sql
CREATE VIEW CTA_HOJA_DE_RUTA AS
SELECT DISTINCT
    sg.EJERCICIO    AS SG_EJERCICIO,
    sg.NRO_SOLIC    AS SG_NRO,
    sg.DELEG_SOLIC  AS SG_DELEG,
    oc.EJERCICIO    AS OC_EJERCICIO,
    oc.NRO_OC       AS OC_NRO_OC,
    oc.COD_PROV     AS OC_COD_PROV,
    pe.EJERCICIO    AS PE_EJERCICIO,
    pe.NUM_PED      AS PE_NRO,
    pe.JURISDICCION AS PE_JURISDICCION,
    oc.FECH_CONFIRM AS FECH_HOJA
FROM OC_ITEMS oci
JOIN SOLIC_GASTOS sg
  ON sg.EJERCICIO = oci.EJERCICIO
 AND sg.DELEG_SOLIC = oci.DELEG_SOLIC
 AND sg.NRO_SOLIC = oci.NRO_SOLIC
JOIN ORDEN_COMPRA oc
  ON oc.EJERCICIO = oci.EJERCICIO
 AND oc.UNI_COMPRA = oci.UNI_COMPRA
 AND oc.NRO_OC = oci.NRO_OC
LEFT JOIN PEDIDOS pe
  ON pe.EJERCICIO = sg.EJERCICIO
 AND pe.NUM_PED = sg.NRO_PED
```

---
