# Esquema RAFAM — `OWNER_RAFAM`

> Generado automáticamente por `scripts/explore_schema.py` el 2026-05-02 10:55:56
> **No editar manualmente** — regenerar ejecutando el script.

## Índice de tablas

- [ACT_IMP_PROV](#act_imp_prov)
- [ADJUDICACIONES](#adjudicaciones)
- [BENEFICIARIOS](#beneficiarios)
- [CALCULO_MODIF](#calculo_modif)
- [CESIONARIOS](#cesionarios)
- [COTIZA_PROV](#cotiza_prov)
- [COTIZA_PROV_ITEMS](#cotiza_prov_items)
- [CTA_COMPROB](#cta_comprob)
- [CTA_CTACTE_MOVS](#cta_ctacte_movs)
- [CTA_HOJA_DE_RUTA](#cta_hoja_de_ruta)
- [CTA_IMPUT_PERSONAL](#cta_imput_personal)
- [CTA_PROVEEDORES_ALICUOTAS](#cta_proveedores_alicuotas)
- [CTA_TMP_REG_DEVEN_IMP](#cta_tmp_reg_deven_imp)
- [CTA_UTE](#cta_ute)
- [CTR_DOCUM_PROV](#ctr_docum_prov)
- [CUOTAS_JURISDIC](#cuotas_jurisdic)
- [DATOS_PART_CONS](#datos_part_cons)
- [DATOS_PART_CONT](#datos_part_cont)
- [DEDUCCIONES](#deducciones)
- [DEPENDENCIAS](#dependencias)
- [DEUFLO_PROV](#deuflo_prov)
- [DEVENGAMIENTOS](#devengamientos)
- [DEVOLUCION](#devolucion)
- [EGRESOS](#egresos)
- [EMBARGOS](#embargos)
- [ESTRUC_PROG](#estruc_prog)
- [FORMULARIO1](#formulario1)
- [FORMULARIO2](#formulario2)
- [FORMULARIO4](#formulario4)
- [FORMULARIOC1](#formularioc1)
- [FORMULARIOC2](#formularioc2)
- [FORMULARIOP4](#formulariop4)
- [HISTO_ESTADOS](#histo_estados)
- [INGRESOS](#ingresos)
- [ING_COD_INGRESOS_DET](#ing_cod_ingresos_det)
- [JURISDICCIONES](#jurisdicciones)
- [METAS_PROG](#metas_prog)
- [MOV_EXTRAPRES_DEV](#mov_extrapres_dev)
- [MOV_EXTRAPRES_PAG](#mov_extrapres_pag)
- [MOV_EXTRAPRES_REC](#mov_extrapres_rec)
- [MOV_PRES_COMP](#mov_pres_comp)
- [MOV_PRES_DEV](#mov_pres_dev)
- [MOV_PRES_PAG](#mov_pres_pag)
- [MOV_PRES_REC_DEV](#mov_pres_rec_dev)
- [NOMINA_PROV](#nomina_prov)
- [OC_ITEMS](#oc_items)
- [OC_PLAN_ENT](#oc_plan_ent)
- [ORDEN_COMPRA](#orden_compra)
- [ORDEN_DEVOL](#orden_devol)
- [ORDEN_PAGO](#orden_pago)
- [ORDEN_PAGOEA](#orden_pagoea)
- [ORDEN_PAGOEA_DEDUC](#orden_pagoea_deduc)
- [ORDEN_PAGOEA_DEDUC_UTE](#orden_pagoea_deduc_ute)
- [ORDEN_PAGO_DEDUC](#orden_pago_deduc)
- [ORDEN_PAGO_DEDUC_UTE](#orden_pago_deduc_ute)
- [ORDEN_REINT](#orden_reint)
- [ORDEN_REINT_PRESUP](#orden_reint_presup)
- [PEDIDOS](#pedidos)
- [PED_COTIZACIONES](#ped_cotizaciones)
- [PED_ITEMS](#ped_items)
- [PER_AGENTES](#per_agentes)
- [PER_AGENTES_HIST](#per_agentes_hist)
- [PER_CONCEPTOS_GASTOS_M](#per_conceptos_gastos_m)
- [PER_CONCEPTOS_PROVEEDOR](#per_conceptos_proveedor)
- [PER_SELECCION_DET](#per_seleccion_det)
- [PRE_JURIS_RECURSOS](#pre_juris_recursos)
- [PROVEEDORES](#proveedores)
- [RECEPCION](#recepcion)
- [REGUL_CAMBIO](#regul_cambio)
- [REGUL_CAMBIO_OCEA](#regul_cambio_ocea)
- [REGUL_CAMBIO_PE_IMPUT](#regul_cambio_pe_imput)
- [REGUL_CORREC_EX_IMPUT](#regul_correc_ex_imput)
- [REGUL_CORREC_IMPUT](#regul_correc_imput)
- [REGUL_CORREC_RECUR_IMPUT](#regul_correc_recur_imput)
- [REGUL_DESAF](#regul_desaf)
- [REGUL_GASTOS](#regul_gastos)
- [REGUL_GASTOS_EX](#regul_gastos_ex)
- [REGUL_OPE_DEVOL](#regul_ope_devol)
- [REGUL_RECURSOS_EX_IMPUT](#regul_recursos_ex_imput)
- [REGUL_RETENCIONES](#regul_retenciones)
- [REGUL_RETENCIONES_IMPUT](#regul_retenciones_imput)
- [REG_COMP](#reg_comp)
- [REG_DEVEN](#reg_deven)
- [RETENCIONES](#retenciones)
- [RETENCIONES_REGDED](#retenciones_regded)
- [SOLIC_GASTOS](#solic_gastos)
- [SOLIC_GASTOS_ITEMS](#solic_gastos_items)
- [TES_DEPOSITOS_GARANTIAS](#tes_depositos_garantias)
- [USUARIOS_JURISDICCIONES](#usuarios_jurisdicciones)
- [VI_SUBRUB_PROV](#vi_subrub_prov)

---

## ACT_IMP_PROV

**PK:** `COD_PROV`, `COD_IMP`, `COD_ACTIV`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `COD_IMP` → `OWNER_RAFAM.ACTIVIDADES`, `COD_IMP` → `OWNER_RAFAM.IMPUESTOS`, `COD_ACTIV` → `OWNER_RAFAM.ACTIVIDADES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `COD_IMP` | `VARCHAR2(5)` | ✗ |  |  |
| `COD_ACTIV` | `VARCHAR2(5)` | ✗ |  |  |
| `COEF_CONV_MULTI` | `NUMBER(6,5)` | ✗ | 1 |  |

---

## ADJUDICACIONES

**PK:** `EJERCICIO`, `NRO_ADJUDIC`  
**FK:** `TIPO_DOC_APROB` → `OWNER_RAFAM.TIPO_DOC_RES`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_ADJ`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_ADJUDIC` | `NUMBER(6,0)` | ✗ |  |  |
| `NRO_COTI` | `NUMBER(6,0)` | ✓ |  |  |
| `DELEG_SOLIC` | `NUMBER(4,0)` | ✓ |  |  |
| `NRO_SOLIC` | `NUMBER(6,0)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `FECH_ADJUD` | `DATE` | ✗ |  |  |
| `TIPO_DOC_APROB` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC_APROB` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC_APROB` | `NUMBER(4,0)` | ✓ |  |  |
| `ESTADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `FECH_ENTREGA` | `DATE` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(2000)` | ✓ |  |  |
| `COND_PAGO` | `VARCHAR2(6)` | ✗ |  |  |
| `DESC_COND_PAGO` | `VARCHAR2(45)` | ✓ |  |  |
| `NRO_LLAMADO` | `NUMBER(6,0)` | ✗ | 1 |  |
| `CERRADA` | `VARCHAR2(1)` | ✓ | 'N' |  |

---

## BENEFICIARIOS

**PK:** `COD_BEN`  
**FK:** `LOCA_POS` → `OWNER_RAFAM.LOCALIDADES`, `PROVINCIA` → `OWNER_RAFAM.PROVINCIAS`, `TIPO_DOC11` → `OWNER_RAFAM.TIPO_ID_TRIBUTARIAS`, `TIPO_DOC21` → `OWNER_RAFAM.TIPO_DOC_PERSONALES`, `TIPO_DOC12` → `OWNER_RAFAM.TIPO_ID_TRIBUTARIAS`, `TIPO_DOC22` → `OWNER_RAFAM.TIPO_DOC_PERSONALES`, `TIPO_DOC32` → `OWNER_RAFAM.TIPO_DOC_PERSONALES`, `MOTIVO` → `OWNER_RAFAM.MOTIVOS_SITUACION_TES`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `TIPO_DOC31` → `OWNER_RAFAM.TIPO_DOC_PERSONALES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `COD_BEN` | `NUMBER(7,0)` | ✗ |  |  |
| `APYNOM` | `VARCHAR2(70)` | ✗ |  |  |
| `FECHA_ALTA` | `DATE` | ✗ |  |  |
| `PRIORIDAD` | `NUMBER(1,0)` | ✓ |  |  |
| `SITUACION` | `VARCHAR2(1)` | ✗ |  |  |
| `FECHA_SITUACION` | `DATE` | ✓ |  |  |
| `MOTIVO` | `VARCHAR2(5)` | ✓ |  |  |
| `OBSER_SITUACION` | `VARCHAR2(100)` | ✓ |  |  |
| `CALLE` | `VARCHAR2(40)` | ✓ |  |  |
| `NUMERO` | `VARCHAR2(5)` | ✓ |  |  |
| `NUMERO_AD` | `VARCHAR2(3)` | ✓ |  |  |
| `PISO` | `VARCHAR2(4)` | ✓ |  |  |
| `DEPTO` | `VARCHAR2(4)` | ✓ |  |  |
| `LOCA_POS` | `VARCHAR2(5)` | ✓ |  |  |
| `COD_POS` | `VARCHAR2(8)` | ✓ |  |  |
| `PROVINCIA` | `VARCHAR2(5)` | ✓ |  |  |
| `PAIS` | `VARCHAR2(20)` | ✓ |  |  |
| `CARACTER` | `VARCHAR2(20)` | ✓ |  |  |
| `TIPO_INSTR` | `VARCHAR2(1)` | ✓ |  |  |
| `COPIA_INSTR` | `VARCHAR2(1)` | ✓ |  |  |
| `FECHA_DESIG` | `DATE` | ✓ |  |  |
| `COPIA_DESIG` | `VARCHAR2(1)` | ✓ |  |  |
| `SOLICITANTE1` | `VARCHAR2(40)` | ✓ |  |  |
| `TIPO_DOC11` | `VARCHAR2(5)` | ✓ |  |  |
| `NUM_DOC11` | `VARCHAR2(13)` | ✓ |  |  |
| `F5601` | `VARCHAR2(1)` | ✓ |  |  |
| `FECHA_VEN1` | `DATE` | ✓ |  |  |
| `TIPO_DOC21` | `VARCHAR2(5)` | ✓ |  |  |
| `NUM_DOC21` | `VARCHAR2(13)` | ✓ |  |  |
| `EXPEDIDA1` | `VARCHAR2(20)` | ✓ |  |  |
| `TIPO_DOC31` | `VARCHAR2(5)` | ✓ |  |  |
| `NUM_DOC31` | `VARCHAR2(15)` | ✓ |  |  |
| `PAIS_DOC31` | `VARCHAR2(20)` | ✓ |  |  |
| `SOLICITANTE2` | `VARCHAR2(40)` | ✓ |  |  |
| `TIPO_DOC12` | `VARCHAR2(5)` | ✓ |  |  |
| `NUM_DOC12` | `VARCHAR2(13)` | ✓ |  |  |
| `F5602` | `VARCHAR2(1)` | ✓ |  |  |
| `FECHA_VEN2` | `DATE` | ✓ |  |  |
| `TIPO_DOC22` | `VARCHAR2(5)` | ✓ |  |  |
| `NUM_DOC22` | `VARCHAR2(13)` | ✓ |  |  |
| `EXPEDIDA2` | `VARCHAR2(20)` | ✓ |  |  |
| `TIPO_DOC32` | `VARCHAR2(5)` | ✓ |  |  |
| `NUM_DOC32` | `VARCHAR2(15)` | ✓ |  |  |
| `PAIS_DOC32` | `VARCHAR2(20)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(1000)` | ✓ |  |  |
| `LEYENDA` | `VARCHAR2(1)` | ✓ |  |  |

---

## CALCULO_MODIF

**PK:** *(no encontrada)*  
**FK:** `ANIO_PRESUP` → `OWNER_RAFAM.RECURSOS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `TIPO` → `OWNER_RAFAM.RECURSOS`, `CLASE` → `OWNER_RAFAM.RECURSOS`, `CONCEPTO` → `OWNER_RAFAM.RECURSOS`, `SUBCONCEPTO` → `OWNER_RAFAM.RECURSOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `ANIO_PRESUP` | `NUMBER(4,0)` | ✗ |  |  |
| `FECH_MOV` | `DATE` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `TIPO` | `NUMBER(2,0)` | ✗ |  |  |
| `CLASE` | `NUMBER(1,0)` | ✗ |  |  |
| `CONCEPTO` | `NUMBER(2,0)` | ✗ |  |  |
| `SUBCONCEPTO` | `NUMBER(2,0)` | ✗ |  |  |
| `IMPORTE_MODIF` | `NUMBER(15,2)` | ✓ |  |  |
| `ORIGEN` | `VARCHAR2(20)` | ✓ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `FECH_HORA` | `DATE` | ✓ | SYSDATE |  |

---

## CESIONARIOS

**PK:** `COD_CES`  
**FK:** `COD_BEN` → `OWNER_RAFAM.BENEFICIARIOS`, `LOCA_POS` → `OWNER_RAFAM.LOCALIDADES`, `PROVINCIA` → `OWNER_RAFAM.PROVINCIAS`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `MOTIVO` → `OWNER_RAFAM.MOTIVOS_SITUACION_TES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `COD_BEN` | `NUMBER(7,0)` | ✗ |  |  |
| `COD_CES` | `NUMBER(7,0)` | ✗ |  |  |
| `APYNOM` | `VARCHAR2(70)` | ✗ |  |  |
| `FECHA_ALTA` | `DATE` | ✗ |  |  |
| `FECHA_INICIO` | `DATE` | ✗ |  |  |
| `PRIORIDAD` | `NUMBER(1,0)` | ✓ |  |  |
| `SITUACION` | `VARCHAR2(1)` | ✗ |  |  |
| `FECHA_SITUACION` | `DATE` | ✓ |  |  |
| `MOTIVO` | `VARCHAR2(5)` | ✓ |  |  |
| `OBSER_SITUACION` | `VARCHAR2(100)` | ✓ |  |  |
| `CALLE` | `VARCHAR2(40)` | ✓ |  |  |
| `NUMERO` | `VARCHAR2(5)` | ✓ |  |  |
| `NUMERO_AD` | `VARCHAR2(3)` | ✓ |  |  |
| `PISO` | `VARCHAR2(4)` | ✓ |  |  |
| `DEPTO` | `VARCHAR2(4)` | ✓ |  |  |
| `LOCA_POS` | `VARCHAR2(5)` | ✓ |  |  |
| `COD_POS` | `VARCHAR2(8)` | ✓ |  |  |
| `PROVINCIA` | `VARCHAR2(5)` | ✓ |  |  |
| `PAIS` | `VARCHAR2(20)` | ✓ |  |  |
| `INSTRUMENTO` | `VARCHAR2(40)` | ✓ |  |  |
| `PUBLICO` | `VARCHAR2(1)` | ✓ |  |  |
| `ESCRIBANO` | `VARCHAR2(40)` | ✓ |  |  |
| `REGISTRO` | `VARCHAR2(10)` | ✓ |  |  |
| `ESCRITURA` | `VARCHAR2(15)` | ✓ |  |  |
| `FECHA_ESCRITURA` | `DATE` | ✓ |  |  |
| `TESTIMONIO` | `VARCHAR2(1)` | ✓ |  |  |
| `PRIVADO` | `VARCHAR2(1)` | ✓ |  |  |
| `COPIA` | `VARCHAR2(1)` | ✓ |  |  |
| `CERTIFICA` | `VARCHAR2(40)` | ✓ |  |  |
| `IMPO_CEDIDO` | `NUMBER(10,2)` | ✗ |  |  |
| `IMPO_CANCELADO` | `NUMBER(10,2)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(1000)` | ✓ |  |  |
| `LEYENDA` | `VARCHAR2(1)` | ✓ |  |  |

---

## COTIZA_PROV

**PK:** `EJERCICIO`, `NRO_COTI`, `COD_PROV`, `NRO_LLAMADO`  
**FK:** `COND_PAGO` → `OWNER_RAFAM.PLAZOS_CONDPAGO`, `PLAZO_ENT` → `OWNER_RAFAM.PLAZOS_ENTREGA`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_COTI` | `NUMBER(6,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `PLAZO_ENT` | `VARCHAR2(6)` | ✗ |  |  |
| `DESC_PLAZO_ENT` | `VARCHAR2(45)` | ✓ |  |  |
| `FECH_ENTREGA` | `DATE` | ✓ |  |  |
| `COD_LUG_ENT` | `VARCHAR2(5)` | ✗ |  |  |
| `COND_PAGO` | `VARCHAR2(6)` | ✗ |  |  |
| `DESC_COND_PAGO` | `VARCHAR2(45)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(1000)` | ✓ |  |  |
| `ESTADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECHA_CARGA` | `DATE` | ✓ |  |  |
| `FECHA_ANUL` | `DATE` | ✓ |  |  |
| `MOTIV_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `MANT_OFERTA` | `VARCHAR2(6)` | ✓ |  |  |
| `DESC_MANT_OFERTA` | `VARCHAR2(45)` | ✓ |  |  |
| `NRO_LLAMADO` | `NUMBER(6,0)` | ✗ | 1 |  |

---

## COTIZA_PROV_ITEMS

**PK:** `EJERCICIO`, `NRO_COTI`, `COD_PROV`, `ITEM_REAL`, `NRO_ALTER`, `NRO_LLAMADO`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_COTI` | `NUMBER(6,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `ITEM_REAL` | `NUMBER(5,0)` | ✗ |  |  |
| `NRO_ALTER` | `NUMBER(2,0)` | ✗ |  |  |
| `CANTIDAD` | `NUMBER(10,3)` | ✗ |  |  |
| `DETALLE` | `VARCHAR2(4000)` | ✗ |  |  |
| `COSTO_UNITARIO` | `NUMBER(15,5)` | ✗ |  |  |
| `ESTADO` | `VARCHAR2(1)` | ✗ |  |  |
| `ESPEC_TEC` | `VARCHAR2(1)` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(1000)` | ✓ |  |  |
| `FECHA_CARGA` | `DATE` | ✓ |  |  |
| `CODIGO_UM` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_LLAMADO` | `NUMBER(6,0)` | ✗ | 1 |  |

---

## CTA_COMPROB

**PK:** `EJERCICIO`, `TIPO`, `NRO_COMPROB`, `COD_PROV`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.REG_COMP`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `TIPO` → `OWNER_RAFAM.TIPOS_COMPROB`, `COD_PROV_REAL` → `OWNER_RAFAM.PROVEEDORES`, `NRO_REG_COMP` → `OWNER_RAFAM.REG_COMP`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `TIPO` | `VARCHAR2(3)` | ✗ |  |  |
| `NRO_COMPROB` | `VARCHAR2(13)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `NRO_REG_COMP` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_MOVIM` | `DATE` | ✗ |  |  |
| `FECH_COMPROB` | `DATE` | ✗ |  |  |
| `FECH_VENCIM` | `DATE` | ✓ |  |  |
| `FECH_CONFORMAC` | `DATE` | ✓ |  |  |
| `PORC_BONIF` | `NUMBER(5,2)` | ✓ |  |  |
| `FECH_BONIF` | `DATE` | ✓ |  |  |
| `IMPORTE_COMPR` | `NUMBER(15,2)` | ✗ |  |  |
| `IMPORTE_PAGADO` | `NUMBER(15,2)` | ✓ |  |  |
| `RINDE_IVA` | `VARCHAR2(1)` | ✗ |  |  |
| `PORC_IVA` | `NUMBER(5,2)` | ✓ |  |  |
| `PORC_CRED_FISCAL` | `NUMBER(5,2)` | ✓ |  |  |
| `LIST_LIBRO_IVA` | `NUMBER(4,0)` | ✓ |  |  |
| `FECH_LIST_IVA` | `DATE` | ✓ |  |  |
| `COD_PROV_REAL` | `NUMBER(5,0)` | ✓ |  |  |
| `RAZON_SOCIAL` | `VARCHAR2(70)` | ✓ |  |  |
| `CUIT` | `VARCHAR2(13)` | ✓ |  |  |
| `DETALLE` | `VARCHAR2(200)` | ✓ |  |  |
| `IMPORTE_SIN_IVA` | `NUMBER(15,2)` | ✓ |  |  |

---

## CTA_CTACTE_MOVS

**PK:** `EJERCICIO`, `ORDEN`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `ORDEN` | `NUMBER(7,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `FECH_MOV` | `DATE` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `CODIGO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_HORA` | `DATE` | ✗ | SYSDATE |  |

---

## CTA_HOJA_DE_RUTA

**PK:** *(no encontrada)*  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `USUARIO` | `NUMBER` | ✓ |  |  |
| `PE_EJERCICIO` | `NUMBER` | ✓ |  |  |
| `PE_NRO` | `NUMBER` | ✓ |  |  |
| `PE_FECH` | `DATE` | ✓ |  |  |
| `PE_CODIGO_DEP` | `VARCHAR2(6)` | ✓ |  |  |
| `PE_CODIGO_UE` | `NUMBER` | ✓ |  |  |
| `PE_JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `PE_ESTADO` | `VARCHAR2(5)` | ✓ |  |  |
| `PE_COSTO_TOTAL` | `NUMBER` | ✓ |  |  |
| `SG_EJERCICIO` | `NUMBER` | ✓ |  |  |
| `SG_DELEG_SOLIC` | `NUMBER` | ✓ |  |  |
| `SG_NRO` | `NUMBER` | ✓ |  |  |
| `SG_NRO_PED` | `NUMBER` | ✓ |  |  |
| `SG_JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `SG_CODIGO_UE` | `NUMBER` | ✓ |  |  |
| `SG_CODIGO_DEP` | `VARCHAR2(6)` | ✓ |  |  |
| `SG_FECH` | `DATE` | ✓ |  |  |
| `SG_TIPO_REGIS` | `VARCHAR2(1)` | ✓ |  |  |
| `SG_CODIGO_FF` | `NUMBER` | ✓ |  |  |
| `SG_IMPORTE` | `NUMBER` | ✓ |  |  |
| `SG_ESTADO` | `VARCHAR2(1)` | ✓ |  |  |
| `SG_CONFIRMADO` | `VARCHAR2(1)` | ✓ |  |  |
| `OC_EJERCICIO` | `NUMBER` | ✓ |  |  |
| `OC_UNI_COMPRA` | `NUMBER` | ✓ |  |  |
| `OC_NRO` | `NUMBER` | ✓ |  |  |
| `OC_NRO_ADJUD` | `NUMBER` | ✓ |  |  |
| `OC_FECH` | `DATE` | ✓ |  |  |
| `OC_COD_PROV` | `NUMBER` | ✓ |  |  |
| `OC_ESTADO` | `VARCHAR2(1)` | ✓ |  |  |
| `OC_CONFIRMADO` | `VARCHAR2(1)` | ✓ |  |  |
| `OC_IMPORTE` | `NUMBER` | ✓ |  |  |
| `RC_EJERCICIO` | `NUMBER` | ✓ |  |  |
| `RC_NRO` | `NUMBER` | ✓ |  |  |
| `RC_FECH` | `DATE` | ✓ |  |  |
| `RC_JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `RC_COD_PROV` | `NUMBER` | ✓ |  |  |
| `RC_TIPO_REGIS` | `VARCHAR2(1)` | ✓ |  |  |
| `RC_NRO_ORIG` | `NUMBER` | ✓ |  |  |
| `RC_CODIGO_FF` | `NUMBER` | ✓ |  |  |
| `RC_UNI_COMPRA` | `NUMBER` | ✓ |  |  |
| `RC_NRO_OC` | `NUMBER` | ✓ |  |  |
| `RC_DELEG_SOLIC` | `NUMBER` | ✓ |  |  |
| `RC_NRO_SOLIC` | `NUMBER` | ✓ |  |  |
| `RC_IMPORTE` | `NUMBER` | ✓ |  |  |
| `RC_ESTADO` | `VARCHAR2(1)` | ✓ |  |  |
| `RC_CONFIRMADO` | `VARCHAR2(1)` | ✓ |  |  |
| `RC_DEPENDENCIA` | `VARCHAR2(6)` | ✓ |  |  |
| `RD_EJERCICIO` | `NUMBER` | ✓ |  |  |
| `RD_NRO` | `NUMBER` | ✓ |  |  |
| `RD_FECH` | `DATE` | ✓ |  |  |
| `RD_NRO_REG_COMP` | `NUMBER` | ✓ |  |  |
| `RD_JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `RD_COD_PROV` | `NUMBER` | ✓ |  |  |
| `RD_CODIGO_FF` | `NUMBER` | ✓ |  |  |
| `RD_IMPORTE` | `NUMBER` | ✓ |  |  |
| `RD_ESTADO` | `VARCHAR2(1)` | ✓ |  |  |
| `RD_CONFIRMADO` | `VARCHAR2(1)` | ✓ |  |  |
| `CC_TIPO_COMPROB` | `VARCHAR2(3)` | ✓ |  |  |
| `CC_NRO` | `VARCHAR2(13)` | ✓ |  |  |
| `CC_COD_PROV` | `NUMBER` | ✓ |  |  |
| `CC_NRO_REG_COMP` | `NUMBER` | ✓ |  |  |
| `CC_FECH_MOVIM` | `DATE` | ✓ |  |  |
| `CC_FECH_COMPROB` | `DATE` | ✓ |  |  |
| `CC_IMPORTE` | `NUMBER` | ✓ |  |  |
| `CC_IMPORTE_PAG` | `NUMBER` | ✓ |  |  |
| `OP_EJERCICIO` | `NUMBER` | ✓ |  |  |
| `OP_NRO` | `NUMBER` | ✓ |  |  |
| `OP_FECH` | `DATE` | ✓ |  |  |
| `OP_CODIGO_FF` | `NUMBER` | ✓ |  |  |
| `OP_JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `OP_CODIGO_UE` | `NUMBER` | ✓ |  |  |
| `OP_COD_PROV` | `NUMBER` | ✓ |  |  |
| `OP_TIPO` | `VARCHAR2(1)` | ✓ |  |  |
| `OP_ESTADO` | `VARCHAR2(1)` | ✓ |  |  |
| `OP_NRO_CANCE` | `NUMBER` | ✓ |  |  |
| `OP_CONFIRMADO` | `VARCHAR2(1)` | ✓ |  |  |
| `OP_IMPORTE` | `NUMBER` | ✓ |  |  |
| `OP_IMPORTE_LIQUIDO` | `NUMBER` | ✓ |  |  |

---

## CTA_IMPUT_PERSONAL

**PK:** `NRO_IMPUT`, `EJERCICIO`, `NRO_REG_COMP`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.REG_DEVEN`, `EJERCICIO` → `OWNER_RAFAM.ORDEN_PAGO`, `NRO_REG_DEVEN` → `OWNER_RAFAM.REG_DEVEN`, `NRO_OP` → `OWNER_RAFAM.ORDEN_PAGO`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `NRO_IMPUT` | `NUMBER(9,0)` | ✗ |  |  |
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REG_COMP` | `NUMBER(7,0)` | ✗ |  |  |
| `NRO_REG_DEVEN` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_COMPROB` | `VARCHAR2(13)` | ✓ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✓ |  |  |
| `IMPORTE_DEVEN` | `NUMBER(15,2)` | ✓ |  |  |

---

## CTA_PROVEEDORES_ALICUOTAS

**PK:** `ANIO`, `MES`, `COD_PROV`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `ANIO` | `NUMBER(4,0)` | ✗ |  |  |
| `MES` | `NUMBER(2,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `ALICUOTA` | `NUMBER(4,2)` | ✓ |  |  |
| `FECHA_CONSULTA` | `DATE` | ✓ |  |  |

---

## CTA_TMP_REG_DEVEN_IMP

**PK:** *(no encontrada)*  
**FK:** `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `EJERCICIO` → `OWNER_RAFAM.ESTRUC_PROG`, `EJERCICIO` → `OWNER_RAFAM.GASTOS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `JURISDICCION` → `OWNER_RAFAM.ESTRUC_PROG`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `INCISO` → `OWNER_RAFAM.GASTOS`, `PROGRAMA` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_PRIN` → `OWNER_RAFAM.GASTOS`, `PAR_PARC` → `OWNER_RAFAM.GASTOS`, `ACTIV_PROY` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_SUBP` → `OWNER_RAFAM.GASTOS`, `ACTIV_OBRA` → `OWNER_RAFAM.ESTRUC_PROG`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✗ |  |  |
| `INCISO` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PRIN` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PARC` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_SUBP` | `NUMBER(1,0)` | ✗ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |

---

## CTA_UTE

**PK:** `COD_PROV_UTE`, `COD_PROV`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `COD_PROV_UTE` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV_UTE` | `NUMBER(5,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `PORCENTAJE` | `NUMBER(5,2)` | ✗ |  |  |
| `PORC_GAN` | `NUMBER(5,2)` | ✓ |  |  |
| `PORC_ING_BRUT` | `NUMBER(5,2)` | ✓ |  |  |

---

## CTR_DOCUM_PROV

**PK:** `COD_PROV`, `COD_DOC`  
**FK:** `COD_DOC` → `OWNER_RAFAM.TIPO_DOC_PROVEEDORES`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `COD_DOC` | `VARCHAR2(5)` | ✗ |  |  |
| `FECHA_VENC` | `DATE` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(60)` | ✓ |  |  |
| `FECHA_ACTUALIZ` | `DATE` | ✓ |  |  |

---

## CUOTAS_JURISDIC

**PK:** `ANIO_PRESUP`, `JURISDICCION`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `ANIO_PRESUP` | `NUMBER(4,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `TRIM1_CUOTA` | `NUMBER(15,2)` | ✓ | 0 |  |
| `TRIM2_CUOTA` | `NUMBER(15,2)` | ✓ | 0 |  |
| `TRIM3_CUOTA` | `NUMBER(15,2)` | ✓ | 0 |  |
| `TRIM4_CUOTA` | `NUMBER(15,2)` | ✓ | 0 |  |
| `TRIM1_COMPR` | `NUMBER(15,2)` | ✓ | 0 |  |
| `TRIM2_COMPR` | `NUMBER(15,2)` | ✓ | 0 |  |
| `TRIM3_COMPR` | `NUMBER(15,2)` | ✓ | 0 |  |
| `TRIM4_COMPR` | `NUMBER(15,2)` | ✓ | 0 |  |

---

## DATOS_PART_CONS

**PK:** `COD_PROV`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `ESPECIALIDAD` | `VARCHAR2(100)` | ✓ |  |  |
| `TRABAJOS` | `VARCHAR2(300)` | ✗ |  |  |

---

## DATOS_PART_CONT

**PK:** `COD_PROV`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `CAPITAL` | `NUMBER(12,0)` | ✗ |  |  |
| `CONSTANCIA_BCO` | `VARCHAR2(300)` | ✗ |  |  |
| `ESPECIALIDAD` | `VARCHAR2(100)` | ✓ |  |  |
| `CANT_PERSONAL` | `NUMBER(4,0)` | ✗ |  |  |
| `TRABAJOS` | `VARCHAR2(300)` | ✗ |  |  |
| `TIEMPO_EXIS_EMP` | `DATE` | ✗ |  |  |

---

## DEDUCCIONES

**PK:** *(no encontrada)*  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `CODIGO` | `NUMBER(3,0)` | ✓ |  |  |
| `DESCRIPCION` | `VARCHAR2(100)` | ✓ |  |  |
| `TIPO_DEDUC` | `VARCHAR2(1)` | ✓ |  |  |
| `PORCENTAJE` | `NUMBER(5,2)` | ✓ |  |  |
| `SALDO` | `NUMBER(15,2)` | ✓ |  |  |
| `DECRIPCION_AB` | `VARCHAR2(5)` | ✓ |  |  |
| `CODIGO_AXT` | `NUMBER(5,0)` | ✓ |  |  |
| `EJERCICIO` | `NUMBER(4,0)` | ✓ |  |  |

---

## DEPENDENCIAS

**PK:** `CODIGO`  
**FK:** `PADRE` → `OWNER_RAFAM.DEPENDENCIAS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `CODIGO` | `VARCHAR2(6)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `DESCRIPCION` | `VARCHAR2(50)` | ✓ |  |  |
| `PADRE` | `VARCHAR2(6)` | ✓ |  |  |
| `SELECCIONABLE` | `VARCHAR2(1)` | ✓ | 'S' |  |

---

## DEUFLO_PROV

**PK:** `EJERCICIO`, `COD_PROV`, `EJERCICIO_OC`, `ORDEN_COMPRA`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `EJERCICIO_OC` | `NUMBER(4,0)` | ✗ |  |  |
| `ORDEN_COMPRA` | `NUMBER(6,0)` | ✗ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✓ |  |  |
| `ES_PROY` | `VARCHAR2(1)` | ✗ |  |  |
| `IMPORTE_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |

---

## DEVENGAMIENTOS

**PK:** `ANIO_PRESUP`, `SECUENCIA`  
**FK:** `ANIO_PRESUP` → `OWNER_RAFAM.ASIENTOS`, `ANIO_PRESUP` → `OWNER_RAFAM.ASIENTOS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `ANIO_PRESUP` → `OWNER_RAFAM.RECURSOS`, `TIPO` → `OWNER_RAFAM.RECURSOS`, `ASIENTO_ANUL` → `OWNER_RAFAM.ASIENTOS`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`, `CLASE` → `OWNER_RAFAM.RECURSOS`, `CONCEPTO` → `OWNER_RAFAM.RECURSOS`, `SUBCONCEPTO` → `OWNER_RAFAM.RECURSOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `ANIO_PRESUP` | `NUMBER(4,0)` | ✗ |  |  |
| `SECUENCIA` | `NUMBER(7,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `TIPO` | `NUMBER(2,0)` | ✗ |  |  |
| `CLASE` | `NUMBER(1,0)` | ✗ |  |  |
| `CONCEPTO` | `NUMBER(2,0)` | ✗ |  |  |
| `SUBCONCEPTO` | `NUMBER(2,0)` | ✗ |  |  |
| `ANIO_CUOTA` | `NUMBER(4,0)` | ✗ |  |  |
| `CUOTA` | `VARCHAR2(10)` | ✗ |  |  |
| `FECH_DEVEN` | `DATE` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `FECH_MOV` | `DATE` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(100)` | ✓ |  |  |
| `ESTADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |

---

## DEVOLUCION

**PK:** `EJERCICIO`, `NRO_DEV`  
**FK:** `CODIGO_DEP` → `OWNER_RAFAM.DEPENDENCIAS`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_DEVOLUCION`, `EJERCICIO` → `OWNER_RAFAM.RECEPCION`, `UNI_RECEP` → `OWNER_RAFAM.UNI_RECEPCION`, `UNI_RECEP` → `OWNER_RAFAM.RECEPCION`, `NRO_RECEP` → `OWNER_RAFAM.RECEPCION`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_DEV` | `NUMBER(6,0)` | ✗ |  |  |
| `FECH_DEV` | `DATE` | ✗ |  |  |
| `NRO_RECEP` | `NUMBER(6,0)` | ✗ |  |  |
| `FECH_RECEP` | `DATE` | ✓ |  |  |
| `UNI_COMPRA` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_OC` | `NUMBER(6,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `CODIGO_DEP` | `VARCHAR2(6)` | ✓ |  |  |
| `FECH_EMI_DEV` | `DATE` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(4)` | ✓ |  |  |
| `ESTADO` | `VARCHAR2(1)` | ✗ |  |  |
| `UNI_RECEP` | `VARCHAR2(5)` | ✗ |  |  |
| `FECHA_HORA` | `DATE` | ✗ |  |  |

---

## EGRESOS

**PK:** `EJERCICIO`, `NRO_CANCE`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_CANCE` | `NUMBER(7,0)` | ✗ |  |  |
| `ESTADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECHA_ANULA` | `DATE` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `TIPO_CANCE` | `VARCHAR2(1)` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(250)` | ✓ |  |  |
| `USUARIO` | `VARCHAR2(20)` | ✓ |  |  |
| `FECHA_ALTA` | `DATE` | ✓ |  |  |

---

## EMBARGOS

**PK:** `COD_EMB`  
**FK:** `COD_BEN` → `OWNER_RAFAM.BENEFICIARIOS`, `MOTIVO` → `OWNER_RAFAM.MOTIVOS_SITUACION_TES`, `PROVINCIA` → `OWNER_RAFAM.PROVINCIAS`, `JUZGADO` → `OWNER_RAFAM.JUZGADOS`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `LOCA_POS` → `OWNER_RAFAM.LOCALIDADES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `COD_BEN` | `NUMBER(7,0)` | ✗ |  |  |
| `COD_EMB` | `NUMBER(7,0)` | ✗ |  |  |
| `AUTOS` | `VARCHAR2(70)` | ✗ |  |  |
| `JUZGADO` | `VARCHAR2(5)` | ✗ |  |  |
| `SECRETARIA` | `VARCHAR2(40)` | ✗ |  |  |
| `OFICIO` | `VARCHAR2(15)` | ✗ |  |  |
| `FECHA_ALTA` | `DATE` | ✗ |  |  |
| `FECHA_EMB` | `DATE` | ✗ |  |  |
| `SITUACION` | `VARCHAR2(1)` | ✗ |  |  |
| `FECHA_SITUACION` | `DATE` | ✓ |  |  |
| `MOTIVO` | `VARCHAR2(5)` | ✓ |  |  |
| `OBSER_SITUACION` | `VARCHAR2(100)` | ✓ |  |  |
| `CALLE` | `VARCHAR2(40)` | ✓ |  |  |
| `NUMERO` | `VARCHAR2(5)` | ✓ |  |  |
| `NUMERO_AD` | `VARCHAR2(3)` | ✓ |  |  |
| `PISO` | `VARCHAR2(4)` | ✓ |  |  |
| `DEPTO` | `VARCHAR2(4)` | ✓ |  |  |
| `LOCA_POS` | `VARCHAR2(5)` | ✓ |  |  |
| `COD_POS` | `VARCHAR2(8)` | ✓ |  |  |
| `PROVINCIA` | `VARCHAR2(5)` | ✓ |  |  |
| `PAIS` | `VARCHAR2(20)` | ✓ |  |  |
| `IMPO_EMBARGADO` | `NUMBER(10,2)` | ✗ |  |  |
| `IMPO_CANCELADO` | `NUMBER(10,2)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(1000)` | ✓ |  |  |
| `LEYENDA` | `VARCHAR2(1)` | ✓ |  |  |

---

## ESTRUC_PROG

**PK:** `ANIO_PRESUP`, `JURISDICCION`, `PROGRAMA`, `ACTIV_PROY`, `ACTIV_OBRA`  
**FK:** `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `FINALIDAD` → `OWNER_RAFAM.FIN_FUN`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `CODIGO_PRESTAMO` → `OWNER_RAFAM.EMPRESTITOS`, `FUNCION` → `OWNER_RAFAM.FIN_FUN`, `SUBFUNCION` → `OWNER_RAFAM.FIN_FUN`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `ANIO_PRESUP` | `NUMBER(4,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✗ |  |  |
| `DESAGREGA` | `VARCHAR2(1)` | ✗ |  |  |
| `DENOMINACION` | `VARCHAR2(100)` | ✗ |  |  |
| `DENOMINACION_AB` | `VARCHAR2(25)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✓ |  |  |
| `EJECUTADO` | `NUMBER(15,2)` | ✓ | 0 |  |
| `ESTIMADO` | `NUMBER(15,2)` | ✓ | 0 |  |
| `PROGRAMADO` | `NUMBER(15,2)` | ✓ | 0 |  |
| `CODIGO_PRESTAMO` | `VARCHAR2(5)` | ✓ |  |  |
| `FINALIDAD` | `NUMBER(1,0)` | ✓ |  |  |
| `FUNCION` | `NUMBER(1,0)` | ✓ |  |  |
| `SUBFUNCION` | `NUMBER(1,0)` | ✓ |  |  |
| `CREDITO_INIC` | `NUMBER(15,2)` | ✗ | 0 |  |
| `CREDITO_MODIF` | `NUMBER(15,2)` | ✗ | 0 |  |
| `PREVENTIVO` | `NUMBER(15,2)` | ✗ | 0 |  |
| `COMPROMISO` | `NUMBER(15,2)` | ✗ | 0 |  |
| `DEVENGADO` | `NUMBER(15,2)` | ✗ | 0 |  |
| `PAGADO` | `NUMBER(15,2)` | ✗ | 0 |  |
| `PPG` | `VARCHAR2(1)` | ✓ |  |  |
| `PPG_PORCEN` | `NUMBER(5,2)` | ✓ |  |  |

---

## FORMULARIO1

**PK:** `ANIO_PRESUP`, `JURISDICCION`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `ANIO_PRESUP` | `NUMBER(4,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `FECHA_REGIS` | `DATE` | ✗ |  |  |
| `ITEM1A` | `VARCHAR2(2000)` | ✓ |  |  |
| `ITEM1B` | `VARCHAR2(2000)` | ✓ |  |  |
| `ITEM1C` | `VARCHAR2(2000)` | ✓ |  |  |
| `ITEM1D` | `VARCHAR2(2000)` | ✓ |  |  |
| `ITEM1E` | `VARCHAR2(2000)` | ✓ |  |  |
| `ITEM2A` | `VARCHAR2(2000)` | ✓ |  |  |
| `ITEM2B` | `VARCHAR2(2000)` | ✓ |  |  |
| `ITEM2C` | `VARCHAR2(2000)` | ✓ |  |  |
| `ITEM2D` | `VARCHAR2(2000)` | ✓ |  |  |
| `ITEM3A` | `VARCHAR2(2000)` | ✓ |  |  |
| `FIRMA` | `VARCHAR2(30)` | ✓ |  |  |

---

## FORMULARIO2

**PK:** `ANIO_PRESUP`, `JURISDICCION`, `TIPO`, `CLASE`, `CONCEPTO`, `SUBCONCEPTO`  
**FK:** `ANIO_PRESUP` → `OWNER_RAFAM.RECURSOS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `TIPO` → `OWNER_RAFAM.RECURSOS`, `CLASE` → `OWNER_RAFAM.RECURSOS`, `CONCEPTO` → `OWNER_RAFAM.RECURSOS`, `SUBCONCEPTO` → `OWNER_RAFAM.RECURSOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `ANIO_PRESUP` | `NUMBER(4,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `TIPO` | `NUMBER(2,0)` | ✗ |  |  |
| `CLASE` | `NUMBER(1,0)` | ✗ |  |  |
| `CONCEPTO` | `NUMBER(2,0)` | ✗ |  |  |
| `SUBCONCEPTO` | `NUMBER(2,0)` | ✗ |  |  |
| `EJECUTADO` | `NUMBER(15,2)` | ✓ |  |  |
| `ESTIMADO` | `NUMBER(15,2)` | ✓ |  |  |
| `PROGRAMADO` | `NUMBER(15,2)` | ✗ |  |  |
| `PROY1` | `NUMBER(15,2)` | ✓ |  |  |
| `PROY2` | `NUMBER(15,2)` | ✓ |  |  |
| `EXENCIONES` | `NUMBER(15,2)` | ✓ |  |  |
| `OTRAS` | `NUMBER(15,2)` | ✓ |  |  |
| `POLITICA_TRIB_1` | `NUMBER(5,2)` | ✓ | 0 |  |
| `POLITICA_TRIB_2` | `NUMBER(5,2)` | ✓ | 0 |  |
| `VAL_PROY_MODIF` | `VARCHAR2(1)` | ✓ | 'N' |  |

---

## FORMULARIO4

**PK:** `ANIO_PRESUP`, `JURISDICCION`, `PROGRAMA`  
**FK:** `ANIO_PRESUP` → `OWNER_RAFAM.ESTRUC_PROG`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `JURISDICCION` → `OWNER_RAFAM.ESTRUC_PROG`, `PROGRAMA` → `OWNER_RAFAM.ESTRUC_PROG`, `ACTIV_PROY` → `OWNER_RAFAM.ESTRUC_PROG`, `ACTIV_OBRA` → `OWNER_RAFAM.ESTRUC_PROG`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `ANIO_PRESUP` | `NUMBER(4,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✗ |  |  |
| `FECHA_REGIS` | `DATE` | ✗ |  |  |
| `DESCRIPCION1` | `VARCHAR2(1978)` | ✗ |  |  |
| `DESCRIPCION2` | `VARCHAR2(1978)` | ✓ |  |  |
| `DESCRIPCION3` | `VARCHAR2(1978)` | ✓ |  |  |
| `DESCRIPCION4` | `VARCHAR2(1978)` | ✓ |  |  |
| `DESCRIPCION5` | `VARCHAR2(1978)` | ✓ |  |  |
| `DESCRIPCION6` | `VARCHAR2(1978)` | ✓ |  |  |

---

## FORMULARIOC1

**PK:** `ANIO_PRESUP`, `JURISDICCION`, `GASTO`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `GASTO` → `OWNER_RAFAM.ITEM_C1_DETALLE`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `ANIO_PRESUP` | `NUMBER(4,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `GASTO` | `VARCHAR2(2)` | ✗ |  |  |
| `TRIMESTRE1` | `NUMBER(12,2)` | ✓ |  |  |
| `TRIMESTRE2` | `NUMBER(12,2)` | ✓ |  |  |
| `TRIMESTRE3` | `NUMBER(12,2)` | ✓ |  |  |
| `TRIMESTRE4` | `NUMBER(12,2)` | ✓ |  |  |

---

## FORMULARIOC2

**PK:** `ANIO_PRESUP`, `JURISDICCION`, `CODIGO_PROY`, `INGRESOS_GASTOS`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `CODIGO_PROY` → `OWNER_RAFAM.PROYECTOS_INV`, `INGRESOS_GASTOS` → `OWNER_RAFAM.ITEM_C2_DETALLE`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `ANIO_PRESUP` | `NUMBER(4,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_PROY` | `VARCHAR2(6)` | ✗ |  |  |
| `INGRESOS_GASTOS` | `VARCHAR2(3)` | ✗ |  |  |
| `ANIO1` | `NUMBER(12,2)` | ✓ |  |  |
| `ANIO2` | `NUMBER(12,2)` | ✓ |  |  |
| `ANIO3` | `NUMBER(12,2)` | ✓ |  |  |
| `ANIO4` | `NUMBER(12,2)` | ✓ |  |  |
| `ANIO5` | `NUMBER(12,2)` | ✓ |  |  |
| `ANIO6` | `NUMBER(12,2)` | ✓ |  |  |
| `ANIO7` | `NUMBER(12,2)` | ✓ |  |  |
| `ANIO8` | `NUMBER(12,2)` | ✓ |  |  |
| `ANIO9` | `NUMBER(12,2)` | ✓ |  |  |
| `ANIO10` | `NUMBER(12,2)` | ✓ |  |  |

---

## FORMULARIOP4

**PK:** `ANIO_PRESUP`, `JURISDICCION`, `TRIMESTRE`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `ANIO_PRESUP` | `NUMBER(4,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `TRIMESTRE` | `NUMBER(1,0)` | ✗ |  |  |

---

## HISTO_ESTADOS

**PK:** `COD_PROV`, `FECHA_CARGA`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `COD_ESTADO` | `NUMBER(1,0)` | ✗ |  |  |
| `CAUSA` | `VARCHAR2(200)` | ✗ |  |  |
| `FECHA_CARGA` | `DATE` | ✗ |  |  |

---

## INGRESOS

**PK:** `EJERCICIO`, `NRO_ORDEN`  
**FK:** `DEPENDENCIA` → `OWNER_RAFAM.DEPENDENCIAS`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_ORDEN` | `NUMBER(7,0)` | ✗ |  |  |
| `DOCU_TIPO` | `VARCHAR2(5)` | ✗ |  |  |
| `DOCU_NRO` | `NUMBER(7,0)` | ✗ |  |  |
| `FECHA_DE_REGISTRO` | `DATE` | ✗ |  |  |
| `NRO_CANCE` | `NUMBER(7,0)` | ✓ |  |  |
| `BOCA_RECAUDA` | `NUMBER(5,0)` | ✓ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `DEPENDENCIA` | `VARCHAR2(6)` | ✓ |  |  |
| `DOCU_TIPO_REGULADO` | `VARCHAR2(5)` | ✓ |  |  |
| `DOCU_NRO_REGULADO` | `NUMBER(7,0)` | ✓ |  |  |
| `DOCU_TIPO_REGULADOR` | `VARCHAR2(5)` | ✓ |  |  |
| `DOCU_NRO_REGULADOR` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `TIPO_DE_INGRESO` | `VARCHAR2(2)` | ✓ |  |  |
| `CONTRIBUYENTE` | `VARCHAR2(40)` | ✓ |  |  |
| `NRO_CONTRIB` | `VARCHAR2(11)` | ✓ |  |  |
| `ESTADO` | `VARCHAR2(1)` | ✓ |  |  |
| `DEDUCCIONES` | `VARCHAR2(1)` | ✓ |  |  |
| `REIM_NRO` | `NUMBER(7,0)` | ✓ |  |  |
| `FECHA_DOC` | `DATE` | ✓ | TRUNC(SYSDATE) |  |
| `FECHA_ANUL` | `DATE` | ✓ |  |  |

---

## ING_COD_INGRESOS_DET

**PK:** `EJERCICIO`, `COD_INGRESO`, `ORDEN`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `EJERCICIO` → `OWNER_RAFAM.RECURSOS`, `EJERCICIO` → `OWNER_RAFAM.CTA_CUENTAS`, `EJERCICIO` → `OWNER_RAFAM.ING_COD_INGRESOS_CAB`, `EJERCICIO` → `OWNER_RAFAM.AXT_RECURSOS`, `COD_INGRESO` → `OWNER_RAFAM.ING_COD_INGRESOS_CAB`, `TIPO` → `OWNER_RAFAM.RECURSOS`, `CODIGO_AXT` → `OWNER_RAFAM.AXT_RECURSOS`, `CUENTA` → `OWNER_RAFAM.CTA_CUENTAS`, `CLASE` → `OWNER_RAFAM.RECURSOS`, `CONCEPTO` → `OWNER_RAFAM.RECURSOS`, `SUBCONCEPTO` → `OWNER_RAFAM.RECURSOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `COD_INGRESO` | `NUMBER(6,0)` | ✗ |  |  |
| `ORDEN` | `NUMBER(2,0)` | ✗ |  |  |
| `PORCENTAJE` | `NUMBER(5,2)` | ✗ |  | Porcentaje de lo recaudado que irá a la cuenta. |
| `TIPO_INGRESO` | `VARCHAR2(1)` | ✗ |  | Presupuestario o Extrapresupuestario |
| `TIPO` | `NUMBER(2,0)` | ✓ |  |  |
| `CLASE` | `NUMBER(1,0)` | ✓ |  |  |
| `CONCEPTO` | `NUMBER(2,0)` | ✓ |  |  |
| `SUBCONCEPTO` | `NUMBER(2,0)` | ✓ |  |  |
| `CODIGO_AXT` | `NUMBER(5,0)` | ✓ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `CUENTA` | `VARCHAR2(9)` | ✓ |  |  |

---

## JURISDICCIONES

**PK:** `JURISDICCION`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `DENOMINACION` | `VARCHAR2(50)` | ✓ |  |  |
| `SELECCIONABLE` | `VARCHAR2(1)` | ✓ |  |  |
| `VIGENTE_DESDE` | `NUMBER(4,0)` | ✓ |  |  |
| `VIGENTE_HASTA` | `NUMBER(4,0)` | ✓ |  |  |

---

## METAS_PROG

**PK:** `ANIO_PRESUP`, `JURISDICCION`, `PROGRAMA`, `CODIGO_META`, `CODIGO_UM`  
**FK:** `ANIO_PRESUP` → `OWNER_RAFAM.UNI_MED`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `ANIO_PRESUP` → `OWNER_RAFAM.METAS`, `ANIO_PRESUP` → `OWNER_RAFAM.ESTRUC_PROG`, `CODIGO_UM` → `OWNER_RAFAM.UNI_MED`, `CODIGO_META` → `OWNER_RAFAM.METAS`, `JURISDICCION` → `OWNER_RAFAM.ESTRUC_PROG`, `PROGRAMA` → `OWNER_RAFAM.ESTRUC_PROG`, `ACTIV_PROY` → `OWNER_RAFAM.ESTRUC_PROG`, `ACTIV_OBRA` → `OWNER_RAFAM.ESTRUC_PROG`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `ANIO_PRESUP` | `NUMBER(4,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✗ |  |  |
| `CODIGO_META` | `NUMBER(4,0)` | ✗ |  |  |
| `CODIGO_UM` | `NUMBER(4,0)` | ✗ |  |  |
| `CANT_EJECUTADO` | `NUMBER(6,0)` | ✓ |  |  |
| `CANT_ESTIMADO` | `NUMBER(6,0)` | ✓ |  |  |
| `CANT_PROGRAMADO` | `NUMBER(6,0)` | ✓ |  |  |
| `CODIGO_PRESTAMO` | `NUMBER(3,0)` | ✓ |  |  |

---

## MOV_EXTRAPRES_DEV

**PK:** `SEC_MOV_DEV_EX`  
**FK:** `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `EJERCICIO` → `OWNER_RAFAM.ORDEN_PAGO`, `EJERCICIO` → `OWNER_RAFAM.AXT_EGRESOS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `NRO_OP` → `OWNER_RAFAM.ORDEN_PAGO`, `CODIGO_AXT` → `OWNER_RAFAM.AXT_EGRESOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `SEC_MOV_DEV_EX` | `NUMBER(7,0)` | ✗ |  |  |
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `FECH_MOV` | `DATE` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✓ |  |  |
| `CODIGO_AXT` | `NUMBER(5,0)` | ✗ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `DEUDA` | `VARCHAR2(1)` | ✗ | 'N' |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_REINT` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_OPEA` | `NUMBER(7,0)` | ✓ |  |  |

---

## MOV_EXTRAPRES_PAG

**PK:** `SEC_MOV_PAG_EX`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `EJERCICIO` → `OWNER_RAFAM.AXT_EGRESOS`, `EJERCICIO` → `OWNER_RAFAM.ORDEN_PAGO`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `NRO_OP` → `OWNER_RAFAM.ORDEN_PAGO`, `CODIGO_AXT` → `OWNER_RAFAM.AXT_EGRESOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `SEC_MOV_PAG_EX` | `NUMBER(7,0)` | ✗ |  |  |
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `FECH_MOV` | `DATE` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✓ |  |  |
| `CODIGO_AXT` | `NUMBER(5,0)` | ✗ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `NRO_REINT` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_OPEA` | `NUMBER(7,0)` | ✓ |  |  |

---

## MOV_EXTRAPRES_REC

**PK:** `SEC_MOV_EX_REC`, `EJERCICIO`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.AXT_RECURSOS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `CODIGO_AXT` → `OWNER_RAFAM.AXT_RECURSOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `SEC_MOV_EX_REC` | `NUMBER(7,0)` | ✗ |  |  |
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `FECH_MOV` | `DATE` | ✗ |  |  |
| `DOCU_TIPO` | `VARCHAR2(5)` | ✓ |  |  |
| `DOCU_NRO` | `NUMBER(7,0)` | ✓ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_AXT` | `NUMBER(5,0)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |

---

## MOV_PRES_COMP

**PK:** `SEC_MOV_COMP`  
**FK:** `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `EJERCICIO` → `OWNER_RAFAM.ESTRUC_PROG`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `EJERCICIO` → `OWNER_RAFAM.ORDEN_PAGOEA`, `EJERCICIO` → `OWNER_RAFAM.ORDEN_REINT`, `EJERCICIO` → `OWNER_RAFAM.GASTOS`, `JURISDICCION` → `OWNER_RAFAM.ESTRUC_PROG`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `NRO_OPEA` → `OWNER_RAFAM.ORDEN_PAGOEA`, `NRO_REINT` → `OWNER_RAFAM.ORDEN_REINT`, `INCISO` → `OWNER_RAFAM.GASTOS`, `PAR_PRIN` → `OWNER_RAFAM.GASTOS`, `PROGRAMA` → `OWNER_RAFAM.ESTRUC_PROG`, `ACTIV_PROY` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_PARC` → `OWNER_RAFAM.GASTOS`, `PAR_SUBP` → `OWNER_RAFAM.GASTOS`, `ACTIV_OBRA` → `OWNER_RAFAM.ESTRUC_PROG`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `SEC_MOV_COMP` | `NUMBER(7,0)` | ✗ |  |  |
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `FECH_MOV` | `DATE` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✓ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✓ |  |  |
| `INCISO` | `NUMBER(1,0)` | ✓ |  |  |
| `PAR_PRIN` | `NUMBER(1,0)` | ✓ |  |  |
| `PAR_PARC` | `NUMBER(1,0)` | ✓ |  |  |
| `PAR_SUBP` | `NUMBER(1,0)` | ✓ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✓ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✓ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✓ |  |  |
| `NRO_REG_COMP` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✓ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `NRO_REINT` | `NUMBER(7,0)` | ✓ |  |  |
| `FECH_HORA` | `DATE` | ✗ | SYSDATE |  |
| `NRO_OPEA` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_RENG` | `NUMBER(7,0)` | ✓ |  |  |
| `IMPORTE_DIFER` | `NUMBER(16,5)` | ✓ |  |  |

---

## MOV_PRES_DEV

**PK:** `SEC_MOV_DEV`, `EJERCICIO`  
**FK:** `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `EJERCICIO` → `OWNER_RAFAM.GASTOS`, `EJERCICIO` → `OWNER_RAFAM.REG_DEVEN`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS_RENG`, `EJERCICIO` → `OWNER_RAFAM.ESTRUC_PROG`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `EJERCICIO` → `OWNER_RAFAM.ORDEN_REINT`, `JURISDICCION` → `OWNER_RAFAM.ESTRUC_PROG`, `INCISO` → `OWNER_RAFAM.GASTOS`, `NRO_REINT` → `OWNER_RAFAM.ORDEN_REINT`, `NRO_REG_DEVEN` → `OWNER_RAFAM.REG_DEVEN`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS_RENG`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `PAR_PRIN` → `OWNER_RAFAM.GASTOS`, `ASIENTO_RENG` → `OWNER_RAFAM.ASIENTOS_RENG`, `PROGRAMA` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_PARC` → `OWNER_RAFAM.GASTOS`, `ACTIV_PROY` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_SUBP` → `OWNER_RAFAM.GASTOS`, `ACTIV_OBRA` → `OWNER_RAFAM.ESTRUC_PROG`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `SEC_MOV_DEV` | `NUMBER(7,0)` | ✗ |  |  |
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `FECH_MOV` | `DATE` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✗ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✗ |  |  |
| `INCISO` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PRIN` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PARC` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_SUBP` | `NUMBER(1,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✗ |  |  |
| `NRO_REG_DEVEN` | `NUMBER(7,0)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `IMPORTE_COMP` | `NUMBER(15,2)` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_RENG` | `NUMBER(4,0)` | ✓ |  |  |
| `NRO_REINT` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✓ |  |  |
| `DEUDA` | `VARCHAR2(1)` | ✗ | 'N' |  |
| `NRO_OPEA` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_RENG` | `NUMBER(7,0)` | ✓ |  |  |

---

## MOV_PRES_PAG

**PK:** `SEC_MOV_PAG`, `EJERCICIO`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `EJERCICIO` → `OWNER_RAFAM.GASTOS`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `EJERCICIO` → `OWNER_RAFAM.ESTRUC_PROG`, `EJERCICIO` → `OWNER_RAFAM.ORDEN_PAGO`, `NRO_OP` → `OWNER_RAFAM.ORDEN_PAGO`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `JURISDICCION` → `OWNER_RAFAM.ESTRUC_PROG`, `INCISO` → `OWNER_RAFAM.GASTOS`, `PROGRAMA` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_PRIN` → `OWNER_RAFAM.GASTOS`, `PAR_PARC` → `OWNER_RAFAM.GASTOS`, `ACTIV_PROY` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_SUBP` → `OWNER_RAFAM.GASTOS`, `ACTIV_OBRA` → `OWNER_RAFAM.ESTRUC_PROG`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `SEC_MOV_PAG` | `NUMBER(7,0)` | ✗ |  |  |
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `FECH_MOV` | `DATE` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✗ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✗ |  |  |
| `INCISO` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PRIN` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PARC` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_SUBP` | `NUMBER(1,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✗ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✓ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✓ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `NRO_REINT` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_OPEA` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_RENG` | `NUMBER(7,0)` | ✓ |  |  |

---

## MOV_PRES_REC_DEV

**PK:** `SEC_MOV_REC_DEV`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `SEC_MOV_REC_DEV` | `NUMBER(7,0)` | ✗ |  |  |
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `FECH_MOV` | `DATE` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `TIPO` | `NUMBER(2,0)` | ✗ |  |  |
| `CLASE` | `NUMBER(1,0)` | ✗ |  |  |
| `CONCEPTO` | `NUMBER(2,0)` | ✗ |  |  |
| `SUBCONCEPTO` | `NUMBER(2,0)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `DOCU_TIPO` | `VARCHAR2(5)` | ✓ |  |  |
| `DOCU_NRO` | `NUMBER(7,0)` | ✓ |  |  |
| `CUOTA` | `VARCHAR2(10)` | ✓ |  |  |
| `RECURSO_ING` | `VARCHAR2(3)` | ✓ |  |  |
| `CONCEPTO_ING` | `VARCHAR2(10)` | ✓ |  |  |

---

## NOMINA_PROV

**PK:** `EJERCICIO`, `NRO_COTI`, `COD_PROV`, `NRO_LLAMADO`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_COTI` | `NUMBER(6,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `FECH_EMI_COTI` | `DATE` | ✓ |  |  |
| `NRO_CERTIF` | `NUMBER(6,0)` | ✓ |  |  |
| `NRO_LLAMADO` | `NUMBER(6,0)` | ✗ | 1 |  |
| `ESTADO` | `VARCHAR2(1)` | ✓ | 'N' |  |

---

## OC_ITEMS

**PK:** `EJERCICIO`, `UNI_COMPRA`, `NRO_OC`, `ITEM_OC`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.ORDEN_COMPRA`, `UNI_COMPRA` → `OWNER_RAFAM.ORDEN_COMPRA`, `NRO_OC` → `OWNER_RAFAM.ORDEN_COMPRA`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `UNI_COMPRA` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_OC` | `NUMBER(6,0)` | ✗ |  |  |
| `ITEM_OC` | `NUMBER(4,0)` | ✗ |  |  |
| `DELEG_SOLIC` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_SOLIC` | `NUMBER(6,0)` | ✗ |  |  |
| `ITEM_REAL` | `NUMBER(4,0)` | ✗ |  |  |
| `DESCRIPCION` | `VARCHAR2(4000)` | ✗ |  |  |
| `CANTIDAD` | `NUMBER(10,3)` | ✗ |  |  |
| `IMP_UNITARIO` | `NUMBER(15,5)` | ✗ |  |  |
| `CANT_RECIB` | `NUMBER(10,3)` | ✓ | 0 |  |
| `IMPORTE_EJER` | `NUMBER(16,5)` | ✓ |  |  |

---

## OC_PLAN_ENT

**PK:** `EJERCICIO`, `UNI_COMPRA`, `NRO_OC`, `ITEM_OC`, `OC_PLAN_SEC`  
**FK:** `COD_LUG_ENT` → `OWNER_RAFAM.LUGARES_ENT`, `EJERCICIO` → `OWNER_RAFAM.ORDEN_COMPRA`, `UNI_COMPRA` → `OWNER_RAFAM.ORDEN_COMPRA`, `NRO_OC` → `OWNER_RAFAM.ORDEN_COMPRA`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `UNI_COMPRA` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_OC` | `NUMBER(6,0)` | ✗ |  |  |
| `ITEM_OC` | `NUMBER(4,0)` | ✗ |  |  |
| `OC_PLAN_SEC` | `NUMBER(2,0)` | ✗ |  |  |
| `COD_LUG_ENT` | `VARCHAR2(5)` | ✗ |  |  |
| `CANTIDAD` | `NUMBER(10,3)` | ✗ |  |  |
| `FECH_ENTREGA` | `DATE` | ✓ |  |  |

---

## ORDEN_COMPRA

**PK:** `EJERCICIO`, `UNI_COMPRA`, `NRO_OC`  
**FK:** `COD_LUG_ENT` → `OWNER_RAFAM.LUGARES_ENT`, `UNI_COMPRA` → `OWNER_RAFAM.UNI_COMPRA`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `UNI_COMPRA` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_OC` | `NUMBER(6,0)` | ✗ |  |  |
| `NRO_ADJUD` | `NUMBER(6,0)` | ✗ |  |  |
| `FECH_OC` | `DATE` | ✓ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `COD_LUG_ENT` | `VARCHAR2(5)` | ✓ |  |  |
| `FECH_ENTREGA` | `DATE` | ✓ |  |  |
| `ESTADO_OC` | `VARCHAR2(1)` | ✓ |  |  |
| `TIPO_DOC_APROB` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC_APROB` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC_APROB` | `NUMBER(4,0)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✓ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `CANT_IMPRES` | `NUMBER(3,0)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(1000)` | ✓ |  |  |
| `IMPORTE_TOT` | `NUMBER(15,5)` | ✗ |  |  |
| `COND_PAGO` | `VARCHAR2(6)` | ✗ |  |  |
| `DESC_COND_PAGO` | `VARCHAR2(45)` | ✓ |  |  |
| `OC_DIFERIDO` | `VARCHAR2(1)` | ✓ | 'N' |  |

---

## ORDEN_DEVOL

**PK:** `EJERCICIO`, `NRO_DEVOL`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_OP`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `FORMA_DE_PAGO` → `OWNER_RAFAM.FORMAS_DE_PAGO`, `ASIENTO_ANUL` → `OWNER_RAFAM.ASIENTOS`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_DEVOL` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_DEVOL` | `DATE` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `ESTADO_DEVOL` | `VARCHAR2(1)` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `NRO_CANCE` | `NUMBER(7,0)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `IMPORTE_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |
| `FORMA_DE_PAGO` | `NUMBER(1,0)` | ✗ |  |  |

---

## ORDEN_PAGO

**PK:** `EJERCICIO`, `NRO_OP`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `COD_EMP` → `OWNER_RAFAM.EMPRESTITOS`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`, `ASIENTO_ANUL` → `OWNER_RAFAM.ASIENTOS`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_OP` | `DATE` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✓ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `TIPO_OP` | `VARCHAR2(1)` | ✗ |  |  |
| `ESTADO_OP` | `VARCHAR2(1)` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `NRO_CANCE` | `NUMBER(7,0)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `IMPORTE_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `IMPORTE_LIQUIDO` | `NUMBER(15,2)` | ✗ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `CONCEPTO` | `VARCHAR2(1000)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `COD_EMP` | `VARCHAR2(5)` | ✓ |  |  |
| `IMPORTE_BONIFICACION` | `NUMBER(15,2)` | ✗ |  |  |
| `IMPORTE_DEDUCCIONES` | `NUMBER(15,2)` | ✗ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |
| `MONTO_SIN_IVA` | `NUMBER(15,2)` | ✓ |  |  |
| `DEUDA` | `VARCHAR2(1)` | ✗ | 'N' |  |
| `BLOQUEADA` | `VARCHAR2(1)` | ✓ | 'N' |  |
| `RECURSO` | `VARCHAR2(15)` | ✓ |  |  |
| `PERCIBIDO` | `NUMBER(15,2)` | ✓ |  |  |
| `NO_PAGADO` | `NUMBER(15,2)` | ✓ |  |  |
| `PAGADO` | `NUMBER(15,2)` | ✓ |  |  |
| `RECO_DEU_ORDEN` | `NUMBER(7,0)` | ✓ |  |  |
| `RECO_DEU_EJERCICIO` | `NUMBER(4,0)` | ✓ |  |  |
| `RECO_DEU_COMPRA` | `NUMBER(7,0)` | ✓ |  |  |
| `RECO_DEU_COMPRA_EJER` | `NUMBER(4,0)` | ✓ |  |  |
| `F931` | `VARCHAR2(1)` | ✓ |  |  |
| `SICORE` | `VARCHAR2(1)` | ✓ | 'S' |  |

---

## ORDEN_PAGOEA

**PK:** `EJERCICIO`, `NRO_OP`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `EJERCICIO_ANT` → `OWNER_RAFAM.REG_COMP`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `EJERCICIO_ANT` → `OWNER_RAFAM.ORDEN_PAGO`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_OP`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `EJERCICIO` → `OWNER_RAFAM.GASTOS`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `EJERCICIO` → `OWNER_RAFAM.ESTRUC_PROG`, `NRO_OP_ANT` → `OWNER_RAFAM.ORDEN_PAGO`, `ASIENTO_ANUL` → `OWNER_RAFAM.ASIENTOS`, `JURISDICCION` → `OWNER_RAFAM.ESTRUC_PROG`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `NRO_REG_COMP_ANT` → `OWNER_RAFAM.REG_COMP`, `INCISO` → `OWNER_RAFAM.GASTOS`, `PROGRAMA` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_PRIN` → `OWNER_RAFAM.GASTOS`, `ACTIV_PROY` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_PARC` → `OWNER_RAFAM.GASTOS`, `ACTIV_OBRA` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_SUBP` → `OWNER_RAFAM.GASTOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_OP` | `DATE` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `ORIGEN_OP` | `VARCHAR2(1)` | ✗ |  |  |
| `TIPO_OP` | `VARCHAR2(1)` | ✗ |  |  |
| `EJERCICIO_ANT` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REG_COMP_ANT` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_OP_ANT` | `NUMBER(7,0)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✓ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✓ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✓ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✓ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✓ |  |  |
| `INCISO` | `NUMBER(1,0)` | ✓ |  |  |
| `PAR_PRIN` | `NUMBER(1,0)` | ✓ |  |  |
| `PAR_PARC` | `NUMBER(1,0)` | ✓ |  |  |
| `PAR_SUBP` | `NUMBER(1,0)` | ✓ |  |  |
| `CODIGO_AXT` | `NUMBER(5,0)` | ✓ |  |  |
| `ESTADO_OP` | `VARCHAR2(1)` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `IMPORTE_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `IMPORTE_LIQUIDO` | `NUMBER(15,2)` | ✗ |  |  |
| `IMPORTE_DEDUCCIONES` | `NUMBER(15,2)` | ✗ |  |  |
| `NRO_CANCE` | `NUMBER(7,0)` | ✓ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✗ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(1000)` | ✓ |  |  |
| `CONCEPTO` | `VARCHAR2(1000)` | ✗ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |
| `IMPORTE_SIN_IVA` | `NUMBER(15,2)` | ✓ |  |  |
| `PORCENTAJE_IVA` | `NUMBER(15,2)` | ✓ |  |  |

---

## ORDEN_PAGOEA_DEDUC

**PK:** `EJERCICIO`, `NRO_OP`, `CODIGO_DEDUC`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.DEDUCCIONES`, `CODIGO_DEDUC` → `OWNER_RAFAM.DEDUCCIONES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✗ |  |  |
| `CODIGO_DEDUC` | `NUMBER(3,0)` | ✗ |  |  |
| `IMPORTE_RETEN` | `NUMBER(15,2)` | ✗ |  |  |
| `COMPROB_DEDUC` | `NUMBER(7,0)` | ✗ |  |  |
| `ALICUOTA` | `NUMBER(5,2)` | ✓ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✓ |  |  |
| `TIPO_GENERAC` | `VARCHAR2(1)` | ✗ |  |  |
| `CUENTA` | `VARCHAR2(9)` | ✓ |  |  |
| `COEF_CONV_MULTI` | `NUMBER(6,5)` | ✗ | 1 |  |
| `ACTIVIDAD` | `VARCHAR2(10)` | ✓ |  |  |
| `TIPO_ALICUOTA` | `VARCHAR2(5)` | ✓ |  | PA: corresponde al padrón para año y mes. PMA: Padrón mes anterior. D: Alicuota default. M: Modificada por el usuario |

---

## ORDEN_PAGOEA_DEDUC_UTE

**PK:** `EJERCICIO`, `NRO_OP`, `CODIGO_DEDUC`, `COD_PROV`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✗ |  |  |
| `CODIGO_DEDUC` | `NUMBER(3,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `PORCENTAJE` | `NUMBER(5,2)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `COD_ACTIV` | `VARCHAR2(5)` | ✓ |  |  |

---

## ORDEN_PAGO_DEDUC

**PK:** `EJERCICIO`, `NRO_OP`, `CODIGO_DEDUC`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.DEDUCCIONES`, `CODIGO_DEDUC` → `OWNER_RAFAM.DEDUCCIONES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✗ |  |  |
| `CODIGO_DEDUC` | `NUMBER(3,0)` | ✗ |  |  |
| `IMPORTE_RETEN` | `NUMBER(15,2)` | ✗ |  |  |
| `COMPROB_DEDUC` | `NUMBER(7,0)` | ✗ |  |  |
| `ALICUOTA` | `NUMBER(5,2)` | ✓ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✓ |  |  |
| `TIPO_GENERAC` | `VARCHAR2(1)` | ✗ |  |  |
| `CUENTA` | `VARCHAR2(9)` | ✓ |  |  |
| `COEF_CONV_MULTI` | `NUMBER(6,5)` | ✗ | 1 |  |
| `ACTIVIDAD` | `VARCHAR2(10)` | ✓ |  |  |
| `TIPO_ALICUOTA` | `VARCHAR2(5)` | ✓ |  | PA: corresponde al padrón para año y mes. PMA: Padrón mes anterior. D: Alicuota default. M: Modificada por el usuario |

---

## ORDEN_PAGO_DEDUC_UTE

**PK:** `EJERCICIO`, `NRO_OP`, `CODIGO_DEDUC`, `COD_PROV`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✗ |  |  |
| `CODIGO_DEDUC` | `NUMBER(3,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `PORCENTAJE` | `NUMBER(5,2)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `COD_ACTIV` | `VARCHAR2(5)` | ✓ |  |  |

---

## ORDEN_REINT

**PK:** `EJERCICIO`, `NRO_REINT`  
**FK:** `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_OP`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `FORMA_DE_PAGO` → `OWNER_RAFAM.FORMAS_DE_PAGO`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `CLEARING` → `OWNER_RAFAM.CLEARING`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `ASIENTO_ANUL` → `OWNER_RAFAM.ASIENTOS`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REINT` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_REINT` | `DATE` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✓ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `TIPO_REINT` | `VARCHAR2(1)` | ✗ |  |  |
| `ESTADO_REINT` | `VARCHAR2(1)` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `NRO_CANCE` | `NUMBER(7,0)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `IMPORTE_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |
| `FORMA_DE_PAGO` | `NUMBER(1,0)` | ✗ |  |  |
| `CLEARING` | `VARCHAR2(3)` | ✗ |  |  |
| `DEUDA` | `VARCHAR2(1)` | ✗ | 'N' |  |

---

## ORDEN_REINT_PRESUP

**PK:** `EJERCICIO`, `NRO_REINT`, `CODIGO_FF`, `INCISO`, `PAR_PRIN`, `PAR_PARC`, `PAR_SUBP`, `JURISDICCION`, `PROGRAMA`, `ACTIV_PROY`, `ACTIV_OBRA`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `EJERCICIO` → `OWNER_RAFAM.GASTOS`, `EJERCICIO` → `OWNER_RAFAM.ESTRUC_PROG`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `JURISDICCION` → `OWNER_RAFAM.ESTRUC_PROG`, `INCISO` → `OWNER_RAFAM.GASTOS`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `PAR_PRIN` → `OWNER_RAFAM.GASTOS`, `PROGRAMA` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_PARC` → `OWNER_RAFAM.GASTOS`, `ACTIV_PROY` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_SUBP` → `OWNER_RAFAM.GASTOS`, `ACTIV_OBRA` → `OWNER_RAFAM.ESTRUC_PROG`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REINT` | `NUMBER(7,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✓ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✗ |  |  |
| `INCISO` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PRIN` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PARC` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_SUBP` | `NUMBER(1,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✓ |  |  |

---

## PEDIDOS

**PK:** `EJERCICIO`, `NUM_PED`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.DEPENDENCIAS`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `CODIGO_DEP` → `OWNER_RAFAM.DEPENDENCIAS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NUM_PED` | `NUMBER(6,0)` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `FECH_EMI` | `DATE` | ✗ |  |  |
| `NUM_PED_ORI` | `NUMBER(6,0)` | ✓ |  |  |
| `FECH_EMI_ORI` | `DATE` | ✓ |  |  |
| `CODIGO_DEP` | `VARCHAR2(6)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `COSTO_TOT` | `NUMBER(15,2)` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(4000)` | ✓ |  |  |
| `PED_ESTADO` | `VARCHAR2(5)` | ✗ |  |  |
| `CANT_IMP` | `NUMBER(2,0)` | ✗ |  |  |
| `FECH_MODI_ULT` | `DATE` | ✓ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✓ |  |  |
| `COD_LUG_ENT` | `VARCHAR2(5)` | ✓ |  |  |
| `PLAZO_ENT` | `VARCHAR2(6)` | ✓ |  |  |
| `PER_CONSUMO` | `VARCHAR2(1000)` | ✓ |  |  |
| `FECH_ING_COMP` | `DATE` | ✓ |  |  |
| `RESP_RETIRA_PED` | `VARCHAR2(5)` | ✓ |  |  |

---

## PED_COTIZACIONES

**PK:** `EJERCICIO`, `NRO_COTI`, `NRO_LLAMADO`  
**FK:** `MANT_OFERTA` → `OWNER_RAFAM.PLAZOS_MANTOFER`, `EJERCICIO` → `OWNER_RAFAM.PEDIDOS`, `COND_PAGO` → `OWNER_RAFAM.PLAZOS_CONDPAGO`, `TIPO_DOC_RES` → `OWNER_RAFAM.TIPO_DOC_RES`, `TIPO_CONT` → `OWNER_RAFAM.TIPOS_CONT`, `PLAZO_ENT` → `OWNER_RAFAM.PLAZOS_ENTREGA`, `NRO_PED` → `OWNER_RAFAM.PEDIDOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_COTI` | `NUMBER(6,0)` | ✗ |  |  |
| `NRO_PED` | `NUMBER(6,0)` | ✗ |  |  |
| `DELEG_SOLIC` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_SOLIC` | `NUMBER(6,0)` | ✗ |  |  |
| `TIPO_DOC_RES` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC_RES` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC_RES` | `NUMBER(4,0)` | ✓ |  |  |
| `TIPO_CONT` | `VARCHAR2(5)` | ✗ |  |  |
| `NRO_CONT` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_CONT` | `NUMBER(4,0)` | ✗ |  |  |
| `FECH_APERT` | `DATE` | ✓ |  |  |
| `HORA_APERT` | `VARCHAR2(8)` | ✓ |  |  |
| `FECH_EMI_COMP` | `DATE` | ✓ |  |  |
| `PLAZO_ENT` | `VARCHAR2(6)` | ✗ |  |  |
| `DESC_PLAZO_ENT` | `VARCHAR2(45)` | ✓ |  |  |
| `COD_LUG_ENT` | `VARCHAR2(5)` | ✗ |  |  |
| `MANT_OFERTA` | `VARCHAR2(6)` | ✗ |  |  |
| `DESC_MANT_OFERTA` | `VARCHAR2(45)` | ✓ |  |  |
| `COND_PAGO` | `VARCHAR2(6)` | ✗ |  |  |
| `DESC_COND_PAGO` | `VARCHAR2(45)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(1000)` | ✓ |  |  |
| `ESTADO` | `VARCHAR2(1)` | ✗ |  |  |
| `COSTO_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `NRO_LLAMADO` | `NUMBER(6,0)` | ✗ |  |  |
| `CARGA_NOMINA` | `VARCHAR2(1)` | ✓ |  |  |
| `FECH_PED` | `DATE` | ✓ |  |  |
| `CERRADA` | `VARCHAR2(1)` | ✓ | 'N' |  |

---

## PED_ITEMS

**PK:** `EJERCICIO`, `NUM_PED`, `ORDEN`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.PEDIDOS`, `CLASE` → `OWNER_RAFAM.CAT_ITEM`, `UNI_MED` → `OWNER_RAFAM.CAT_UNI_MED`, `EJERCICIO` → `OWNER_RAFAM.ESTRUC_PROG`, `NUM_PED` → `OWNER_RAFAM.PEDIDOS`, `TIPO` → `OWNER_RAFAM.CAT_ITEM`, `JURISDICCION` → `OWNER_RAFAM.ESTRUC_PROG`, `PROGRAMA` → `OWNER_RAFAM.ESTRUC_PROG`, `ACTIV_PROY` → `OWNER_RAFAM.ESTRUC_PROG`, `ACTIV_OBRA` → `OWNER_RAFAM.ESTRUC_PROG`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NUM_PED` | `NUMBER(6,0)` | ✗ |  |  |
| `ORDEN` | `NUMBER(5,0)` | ✗ |  |  |
| `INCISO` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PRIN` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PARC` | `NUMBER(1,0)` | ✗ |  |  |
| `CLASE` | `NUMBER(5,0)` | ✗ |  |  |
| `TIPO` | `NUMBER(4,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✗ |  |  |
| `CANTIDAD` | `NUMBER(10,3)` | ✗ |  |  |
| `UNI_MED` | `NUMBER(4,0)` | ✗ |  |  |
| `DESCRIP_BIE` | `VARCHAR2(4000)` | ✗ |  |  |
| `COSTO_UNI` | `NUMBER(15,5)` | ✗ |  |  |

---

## PER_AGENTES

**PK:** `LEGAJO`, `NRO_CARGO`  
**FK:** `LUGAR_PAGO` → `OWNER_RAFAM.PER_LUGAR_PAGOS`, `RELACION_LABORAL` → `OWNER_RAFAM.PER_RELACIONES_LABORALES`, `TIPO_RELACION` → `OWNER_RAFAM.PER_TIPO_RELACIONES`, `FRECUENCIA_PAGO` → `OWNER_RAFAM.PER_FRECUENCIA_PAGOS`, `LEGAJO` → `OWNER_RAFAM.LEGAJOS`, `COD_PROV_INTERNO` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `LEGAJO` | `NUMBER(12,0)` | ✗ |  |  |
| `NRO_CARGO` | `NUMBER(2,0)` | ✗ |  |  |
| `FECH_MOV` | `DATE` | ✗ |  |  |
| `NRO_OFICINA` | `VARCHAR2(5)` | ✓ |  |  |
| `TIPO_RELACION` | `VARCHAR2(5)` | ✗ |  |  |
| `DEDICACION` | `VARCHAR2(1)` | ✗ |  |  |
| `FORMA_PAGO` | `NUMBER(1,0)` | ✗ |  |  |
| `LUGAR_PAGO` | `VARCHAR2(5)` | ✗ |  |  |
| `FRECUENCIA_PAGO` | `VARCHAR2(5)` | ✗ |  |  |
| `VALOR_MULTI_1` | `NUMBER(10,2)` | ✓ |  |  |
| `VALOR_MULTI_2` | `NUMBER(10,2)` | ✓ |  |  |
| `VALOR_MULTI_3` | `NUMBER(10,2)` | ✓ |  |  |
| `VALOR_MULTI_4` | `NUMBER(10,2)` | ✓ |  |  |
| `VALOR_MULTI_5` | `NUMBER(10,2)` | ✓ |  |  |
| `VALOR_MULTI_6` | `NUMBER(10,2)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(1000)` | ✓ |  |  |
| `RELACION_LABORAL` | `VARCHAR2(5)` | ✗ |  |  |
| `COD_PROV_INTERNO` | `NUMBER(5,0)` | ✗ |  |  |
| `LIQUIDAR` | `VARCHAR2(1)` | ✓ | 'S' |  |
| `INCENTIVO_DOC` | `VARCHAR2(1)` | ✓ |  |  |

---

## PER_AGENTES_HIST

**PK:** `LEGAJO`, `NRO_CARGO`  
**FK:** `LUGAR_PAGO` → `OWNER_RAFAM.PER_LUGAR_PAGOS`, `RELACION_LABORAL` → `OWNER_RAFAM.PER_RELACIONES_LABORALES`, `TIPO_RELACION` → `OWNER_RAFAM.PER_TIPO_RELACIONES`, `LEGAJO` → `OWNER_RAFAM.LEGAJOS`, `FRECUENCIA_PAGO` → `OWNER_RAFAM.PER_FRECUENCIA_PAGOS`, `COD_PROV_INTERNO` → `OWNER_RAFAM.PROVEEDORES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `LEGAJO` | `NUMBER(12,0)` | ✗ |  |  |
| `NRO_CARGO` | `NUMBER(2,0)` | ✗ |  |  |
| `FECH_MOV` | `DATE` | ✗ |  |  |
| `NRO_OFICINA` | `VARCHAR2(5)` | ✓ |  |  |
| `TIPO_RELACION` | `VARCHAR2(5)` | ✗ |  |  |
| `DEDICACION` | `VARCHAR2(1)` | ✗ |  |  |
| `FORMA_PAGO` | `NUMBER(1,0)` | ✗ |  |  |
| `LUGAR_PAGO` | `VARCHAR2(5)` | ✗ |  |  |
| `FRECUENCIA_PAGO` | `VARCHAR2(5)` | ✗ |  |  |
| `VALOR_MULTI_1` | `NUMBER(10,2)` | ✓ |  |  |
| `VALOR_MULTI_2` | `NUMBER(10,2)` | ✓ |  |  |
| `VALOR_MULTI_3` | `NUMBER(10,2)` | ✓ |  |  |
| `VALOR_MULTI_4` | `NUMBER(10,2)` | ✓ |  |  |
| `VALOR_MULTI_5` | `NUMBER(10,2)` | ✓ |  |  |
| `VALOR_MULTI_6` | `NUMBER(10,2)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(1000)` | ✓ |  |  |
| `RELACION_LABORAL` | `VARCHAR2(5)` | ✗ |  |  |
| `COD_PROV_INTERNO` | `NUMBER(5,0)` | ✗ |  |  |
| `LIQUIDAR` | `VARCHAR2(1)` | ✓ | 'S' |  |

---

## PER_CONCEPTOS_GASTOS_M

**PK:** `CONCEPTO`, `TIPO_PLANTA`, `JURISDICCION`, `AGRUPAMIENTO`, `ANIO_PRESUP`, `INCISO`, `PAR_PRIN`, `PAR_PARC`, `PAR_SUBP`  
**FK:** `ANIO_PRESUP` → `OWNER_RAFAM.AGRUPAMIENTOS`, `ANIO_PRESUP` → `OWNER_RAFAM.GASTOS`, `TIPO_PLANTA` → `OWNER_RAFAM.TIPO_PLANTAS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `CONCEPTO` → `OWNER_RAFAM.PER_CONCEPTOS`, `JURISDICCION` → `OWNER_RAFAM.AGRUPAMIENTOS`, `INCISO` → `OWNER_RAFAM.GASTOS`, `PAR_PRIN` → `OWNER_RAFAM.GASTOS`, `AGRUPAMIENTO` → `OWNER_RAFAM.AGRUPAMIENTOS`, `PAR_PARC` → `OWNER_RAFAM.GASTOS`, `PAR_SUBP` → `OWNER_RAFAM.GASTOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `CONCEPTO` | `VARCHAR2(5)` | ✗ |  |  |
| `TIPO_PLANTA` | `NUMBER(1,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `AGRUPAMIENTO` | `NUMBER(2,0)` | ✗ |  |  |
| `ANIO_PRESUP` | `NUMBER(4,0)` | ✗ |  |  |
| `INCISO` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PRIN` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PARC` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_SUBP` | `NUMBER(1,0)` | ✗ |  |  |

---

## PER_CONCEPTOS_PROVEEDOR

**PK:** `CONCEPTO`, `PROVEEDOR`  
**FK:** `PROVEEDOR` → `OWNER_RAFAM.PROVEEDORES`, `CONCEPTO` → `OWNER_RAFAM.PER_CONCEPTOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `CONCEPTO` | `VARCHAR2(5)` | ✗ |  |  |
| `PROVEEDOR` | `NUMBER(5,0)` | ✗ |  |  |

---

## PER_SELECCION_DET

**PK:** `SELECCION`, `INDICE`  
**FK:** `JURISDICCIONF` → `OWNER_RAFAM.JURISDICCIONES`, `DEPENDENCIA` → `OWNER_RAFAM.DEPENDENCIAS`, `LEGAJO` → `OWNER_RAFAM.PER_AGENTES`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `SELECCION` → `OWNER_RAFAM.PER_SELECCION_CAB`, `DEPENDENCIAF` → `OWNER_RAFAM.DEPENDENCIAS`, `NRO_CARGO` → `OWNER_RAFAM.PER_AGENTES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `SELECCION` | `NUMBER(5,0)` | ✗ |  |  |
| `INDICE` | `NUMBER(5,0)` | ✗ |  |  |
| `TIPO` | `VARCHAR2(2)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `JURISDICCIONF` | `VARCHAR2(10)` | ✓ |  |  |
| `DEPENDENCIA` | `VARCHAR2(6)` | ✓ |  |  |
| `DEPENDENCIAF` | `VARCHAR2(6)` | ✓ |  |  |
| `LEGAJO` | `NUMBER(12,0)` | ✓ |  |  |
| `NRO_CARGO` | `NUMBER(2,0)` | ✓ |  |  |

---

## PRE_JURIS_RECURSOS

**PK:** `EJERCICIO`, `JURISDICCION`, `TIPO`, `CLASE`, `CONCEPTO`, `SUBCONCEPTO`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.RECURSOS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `TIPO` → `OWNER_RAFAM.RECURSOS`, `CLASE` → `OWNER_RAFAM.RECURSOS`, `CONCEPTO` → `OWNER_RAFAM.RECURSOS`, `SUBCONCEPTO` → `OWNER_RAFAM.RECURSOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `TIPO` | `NUMBER(2,0)` | ✗ |  |  |
| `CLASE` | `NUMBER(1,0)` | ✗ |  |  |
| `CONCEPTO` | `NUMBER(2,0)` | ✗ |  |  |
| `SUBCONCEPTO` | `NUMBER(2,0)` | ✗ |  |  |

---

## PROVEEDORES

**PK:** `COD_PROV`  
**FK:** `TIPO_PROV` → `OWNER_RAFAM.TIPOS_PROVEEDORES`, `TIPO_SOC` → `OWNER_RAFAM.TIPOS_SOCIEDADES`, `LOCA_POSTAL` → `OWNER_RAFAM.LOCALIDADES`, `PROV_LEGAL` → `OWNER_RAFAM.PROVINCIAS`, `COD_IVA` → `OWNER_RAFAM.POS_IVA`, `CALIF_PROV` → `OWNER_RAFAM.CALIFICACIONES`, `PROV_POSTAL` → `OWNER_RAFAM.PROVINCIAS`, `LOCA_LEGAL` → `OWNER_RAFAM.LOCALIDADES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `RAZON_SOCIAL` | `VARCHAR2(70)` | ✗ |  |  |
| `TIPO_PROV` | `VARCHAR2(5)` | ✗ |  |  |
| `CUIT` | `VARCHAR2(13)` | ✗ |  |  |
| `FANTASIA` | `VARCHAR2(70)` | ✗ |  |  |
| `TIPO_SOC` | `VARCHAR2(5)` | ✗ |  |  |
| `COD_IVA` | `VARCHAR2(5)` | ✗ |  |  |
| `ING_BRUTOS` | `VARCHAR2(25)` | ✓ |  |  |
| `FECHA_ALTA` | `DATE` | ✗ |  |  |
| `FECHA_ULT_COMP` | `DATE` | ✓ |  |  |
| `CALIF_PROV` | `VARCHAR2(5)` | ✗ |  |  |
| `COD_ESTADO` | `NUMBER(1,0)` | ✗ |  |  |
| `CALLE_POSTAL` | `VARCHAR2(40)` | ✗ |  |  |
| `NRO_POSTAL` | `VARCHAR2(5)` | ✗ |  |  |
| `NRO_POSTAL_MED` | `VARCHAR2(3)` | ✓ |  |  |
| `PISO_POSTAL` | `VARCHAR2(4)` | ✓ |  |  |
| `DEPT_POSTAL` | `VARCHAR2(4)` | ✓ |  |  |
| `LOCA_POSTAL` | `VARCHAR2(5)` | ✗ |  |  |
| `COD_POSTAL` | `VARCHAR2(8)` | ✗ |  |  |
| `PROV_POSTAL` | `VARCHAR2(5)` | ✗ |  |  |
| `PAIS_POSTAL` | `VARCHAR2(20)` | ✗ |  |  |
| `CALLE_LEGAL` | `VARCHAR2(40)` | ✗ |  |  |
| `NRO_LEGAL` | `VARCHAR2(5)` | ✗ |  |  |
| `NRO_LEGAL_MED` | `VARCHAR2(3)` | ✓ |  |  |
| `PISO_LEGAL` | `VARCHAR2(4)` | ✓ |  |  |
| `DEPT_LEGAL` | `VARCHAR2(4)` | ✓ |  |  |
| `LOCA_LEGAL` | `VARCHAR2(5)` | ✗ |  |  |
| `COD_LEGAL` | `VARCHAR2(8)` | ✗ |  |  |
| `PROV_LEGAL` | `VARCHAR2(5)` | ✗ |  |  |
| `PAIS_LEGAL` | `VARCHAR2(20)` | ✗ |  |  |
| `NRO_PAIS_TE1` | `VARCHAR2(3)` | ✓ |  |  |
| `NRO_INTE_TE1` | `VARCHAR2(6)` | ✓ |  |  |
| `NRO_TELE_TE1` | `VARCHAR2(12)` | ✓ |  |  |
| `NRO_PAIS_TE2` | `VARCHAR2(3)` | ✓ |  |  |
| `NRO_INTE_TE2` | `VARCHAR2(6)` | ✓ |  |  |
| `NRO_TELE_TE2` | `VARCHAR2(12)` | ✓ |  |  |
| `NRO_PAIS_TE3` | `VARCHAR2(3)` | ✓ |  |  |
| `NRO_INTE_TE3` | `VARCHAR2(6)` | ✓ |  |  |
| `NRO_TELE_TE3` | `VARCHAR2(12)` | ✓ |  |  |
| `TE_CELULAR` | `VARCHAR2(15)` | ✓ |  |  |
| `FAX` | `VARCHAR2(15)` | ✓ |  |  |
| `EMAIL` | `VARCHAR2(50)` | ✓ |  |  |
| `OBSERVACION` | `VARCHAR2(2000)` | ✓ |  |  |
| `PROV_CAJA_CHICA` | `VARCHAR2(1)` | ✗ |  |  |
| `NRO_HAB_MUN` | `VARCHAR2(6)` | ✓ |  |  |
| `DISC_RET_SUSS` | `VARCHAR2(1)` | ✓ | 'S' |  |
| `DISC_GCIAS_UTE` | `VARCHAR2(1)` | ✓ | 'S' |  |
| `DISC_IIBB_UTE` | `VARCHAR2(1)` | ✓ | 'N' |  |

---

## RECEPCION

**PK:** `EJERCICIO`, `UNI_RECEP`, `NRO_RECEP`  
**FK:** `UNI_RECEP` → `OWNER_RAFAM.UNI_RECEPCION`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_RECEPCION`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `EJERCICIO_OC` → `OWNER_RAFAM.ORDEN_COMPRA`, `TIPO_DOC_APROB` → `OWNER_RAFAM.TIPO_DOC_RES`, `UNI_COMPRA` → `OWNER_RAFAM.ORDEN_COMPRA`, `NRO_OC` → `OWNER_RAFAM.ORDEN_COMPRA`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_RECEP` | `NUMBER(6,0)` | ✗ |  |  |
| `FECH_RECEP` | `DATE` | ✗ |  |  |
| `UNI_COMPRA` | `NUMBER(4,0)` | ✓ |  |  |
| `NRO_OC` | `NUMBER(6,0)` | ✓ |  |  |
| `TIPO_DOC_APROB` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC_APROB` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC_APROB` | `NUMBER(4,0)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✓ |  |  |
| `ESTADO` | `VARCHAR2(1)` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(1000)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(4)` | ✓ |  |  |
| `UNI_RECEP` | `VARCHAR2(5)` | ✗ |  |  |
| `EJERCICIO_OC` | `NUMBER(4,0)` | ✓ |  |  |
| `FECHA_HORA` | `DATE` | ✗ |  |  |
| `DONANTE` | `VARCHAR2(50)` | ✓ |  |  |
| `EJERCICIO_REG_COM` | `NUMBER(4,0)` | ✓ |  |  |
| `NRO_REG_COMP` | `NUMBER(7,0)` | ✓ |  |  |

---

## REGUL_CAMBIO

**PK:** `EJERCICIO`, `NRO_REGUL`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `EJERCICIO` → `OWNER_RAFAM.ORDEN_PAGO`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_OP`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `ASIENTO_ANUL` → `OWNER_RAFAM.ASIENTOS`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`, `NRO_OP` → `OWNER_RAFAM.ORDEN_PAGO`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_REGUL` | `DATE` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `TIPO_CAMBIO` | `NUMBER(3,0)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✓ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✓ |  |  |
| `ESTADO_REGUL` | `VARCHAR2(1)` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `IMPORTE_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✓ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |

---

## REGUL_CAMBIO_OCEA

**PK:** `EJERCICIO`, `NRO_REGUL`  
**FK:** `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `EJERCICIO` → `OWNER_RAFAM.ORDEN_PAGOEA`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_OP`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `NRO_OP` → `OWNER_RAFAM.ORDEN_PAGOEA`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_REGUL` | `DATE` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `TIPO_CAMBIO` | `NUMBER(3,0)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✓ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✓ |  |  |
| `ESTADO_REGUL` | `VARCHAR2(1)` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `IMPORTE_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✓ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |

---

## REGUL_CAMBIO_PE_IMPUT

**PK:** `EJERCICIO`, `NRO_REGUL`, `NRO_RENG`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `EJERCICIO` → `OWNER_RAFAM.REGUL_CAMBIO_PE`, `NRO_REGUL` → `OWNER_RAFAM.REGUL_CAMBIO_PE`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `NRO_RENG` | `NUMBER(7,0)` | ✗ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✓ |  |  |
| `INCISO` | `NUMBER(1,0)` | ✓ |  |  |
| `PAR_PRIN` | `NUMBER(1,0)` | ✓ |  |  |
| `PAR_PARC` | `NUMBER(1,0)` | ✓ |  |  |
| `PAR_SUBP` | `NUMBER(1,0)` | ✓ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✓ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✓ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✓ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✓ |  |  |
| `CODIGO_AXT` | `NUMBER(5,0)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✓ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `DEUDA` | `VARCHAR2(1)` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |

---

## REGUL_CORREC_EX_IMPUT

**PK:** `EJERCICIO`, `NRO_REGUL`, `NRO_RENG`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.AXT_EGRESOS`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `CODIGO_AXT` → `OWNER_RAFAM.AXT_EGRESOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `NRO_RENG` | `NUMBER(7,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✓ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_AXT` | `NUMBER(5,0)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `DEUDA` | `VARCHAR2(1)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✓ |  |  |

---

## REGUL_CORREC_IMPUT

**PK:** `EJERCICIO`, `NRO_REGUL`, `NRO_RENG`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `EJERCICIO` → `OWNER_RAFAM.REGUL_CORREC`, `EJERCICIO` → `OWNER_RAFAM.GASTOS`, `EJERCICIO` → `OWNER_RAFAM.ESTRUC_PROG`, `INCISO` → `OWNER_RAFAM.GASTOS`, `JURISDICCION` → `OWNER_RAFAM.ESTRUC_PROG`, `NRO_REGUL` → `OWNER_RAFAM.REGUL_CORREC`, `PAR_PRIN` → `OWNER_RAFAM.GASTOS`, `PROGRAMA` → `OWNER_RAFAM.ESTRUC_PROG`, `ACTIV_PROY` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_PARC` → `OWNER_RAFAM.GASTOS`, `ACTIV_OBRA` → `OWNER_RAFAM.ESTRUC_PROG`, `PAR_SUBP` → `OWNER_RAFAM.GASTOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `NRO_RENG` | `NUMBER(7,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✗ |  |  |
| `INCISO` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PRIN` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PARC` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_SUBP` | `NUMBER(1,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `DEUDA` | `VARCHAR2(1)` | ✗ |  |  |

---

## REGUL_CORREC_RECUR_IMPUT

**PK:** `EJERCICIO`, `NRO_REGUL`, `NRO_RENG`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `EJERCICIO` → `OWNER_RAFAM.RECURSOS`, `TIPO` → `OWNER_RAFAM.RECURSOS`, `CLASE` → `OWNER_RAFAM.RECURSOS`, `CONCEPTO` → `OWNER_RAFAM.RECURSOS`, `SUBCONCEPTO` → `OWNER_RAFAM.RECURSOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `NRO_RENG` | `NUMBER(7,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `TIPO` | `NUMBER(2,0)` | ✓ |  |  |
| `CLASE` | `NUMBER(1,0)` | ✓ |  |  |
| `CONCEPTO` | `NUMBER(2,0)` | ✓ |  |  |
| `SUBCONCEPTO` | `NUMBER(2,0)` | ✓ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |

---

## REGUL_DESAF

**PK:** `EJERCICIO`, `NRO_REGUL`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.SOLIC_GASTOS_DEF`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_OP`, `EJERCICIO` → `OWNER_RAFAM.REG_DEVEN`, `EJERCICIO` → `OWNER_RAFAM.REG_COMP`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `ASIENTO_ANUL` → `OWNER_RAFAM.ASIENTOS`, `NRO_REG_COMP` → `OWNER_RAFAM.REG_COMP`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`, `NRO_REG_DEVEN` → `OWNER_RAFAM.REG_DEVEN`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `DELEG_SOLIC` → `OWNER_RAFAM.SOLIC_GASTOS_DEF`, `NRO_SOLIC` → `OWNER_RAFAM.SOLIC_GASTOS_DEF`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_REGUL` | `DATE` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `TIPO_DESA` | `VARCHAR2(1)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✓ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✓ |  |  |
| `DELEG_SOLIC` | `NUMBER(4,0)` | ✓ |  |  |
| `NRO_SOLIC` | `NUMBER(6,0)` | ✓ |  |  |
| `NRO_REG_COMP` | `NUMBER(7,0)` | ✓ |  |  |
| `NRO_REG_DEVEN` | `NUMBER(7,0)` | ✓ |  |  |
| `ESTADO_REGUL` | `VARCHAR2(1)` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `IMPORTE_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |

---

## REGUL_GASTOS

**PK:** `EJERCICIO`, `NRO_REGUL`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_OP`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `ASIENTO_ANUL` → `OWNER_RAFAM.ASIENTOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_REGUL` | `DATE` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(4,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `ESTADO_REGUL` | `VARCHAR2(1)` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `IMPORTE_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |
| `CONCEPTO` | `VARCHAR2(1000)` | ✗ |  |  |
| `FECH_HORA` | `DATE` | ✗ | SYSDATE |  |
| `NRO_CANCE` | `NUMBER(7,0)` | ✓ |  |  |

---

## REGUL_GASTOS_EX

**PK:** `EJERCICIO`, `NRO_REGUL`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_OP`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `ASIENTO_ANUL` → `OWNER_RAFAM.ASIENTOS`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_REGUL` | `DATE` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✓ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(4,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `ESTADO_REGUL` | `VARCHAR2(1)` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `IMPORTE_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |
| `CONCEPTO` | `VARCHAR2(1000)` | ✗ |  |  |
| `FECH_HORA` | `DATE` | ✗ | SYSDATE |  |
| `NRO_CANCE` | `NUMBER(7,0)` | ✓ |  |  |

---

## REGUL_OPE_DEVOL

**PK:** `EJERCICIO`, `NRO_REGUL`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `EJERCICIO` → `OWNER_RAFAM.ORDEN_PAGO`, `FORMA_DE_PAGO` → `OWNER_RAFAM.FORMAS_DE_PAGO`, `EJERCICIO` → `OWNER_RAFAM.RECURSOS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_OP`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`, `NRO_OP` → `OWNER_RAFAM.ORDEN_PAGO`, `TIPO` → `OWNER_RAFAM.RECURSOS`, `ASIENTO_ANUL` → `OWNER_RAFAM.ASIENTOS`, `CLASE` → `OWNER_RAFAM.RECURSOS`, `CONCEPTO` → `OWNER_RAFAM.RECURSOS`, `SUBCONCEPTO` → `OWNER_RAFAM.RECURSOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_REGUL` | `DATE` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(4,0)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `ESTADO_REGUL` | `VARCHAR2(1)` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `FORMA_DE_PAGO` | `NUMBER(1,0)` | ✓ |  |  |
| `NRO_OP` | `NUMBER(7,0)` | ✓ |  |  |
| `TIPO` | `NUMBER(2,0)` | ✓ |  |  |
| `CLASE` | `NUMBER(1,0)` | ✓ |  |  |
| `CONCEPTO` | `NUMBER(2,0)` | ✓ |  |  |
| `SUBCONCEPTO` | `NUMBER(2,0)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✓ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `IMPORTE_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |
| `FECH_HORA` | `DATE` | ✗ |  |  |
| `NRO_CANCE` | `NUMBER(7,0)` | ✓ |  |  |

---

## REGUL_RECURSOS_EX_IMPUT

**PK:** `EJERCICIO`, `NRO_REGUL`, `NRO_RENG`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `EJERCICIO` → `OWNER_RAFAM.AXT_RECURSOS`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `EJERCICIO` → `OWNER_RAFAM.RECURSOS`, `CODIGO_AXT` → `OWNER_RAFAM.AXT_RECURSOS`, `TIPO` → `OWNER_RAFAM.RECURSOS`, `CLASE` → `OWNER_RAFAM.RECURSOS`, `CONCEPTO` → `OWNER_RAFAM.RECURSOS`, `SUBCONCEPTO` → `OWNER_RAFAM.RECURSOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `NRO_RENG` | `NUMBER(7,0)` | ✗ |  |  |
| `SUBCONCEPTO` | `NUMBER(2,0)` | ✓ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✓ |  |  |
| `TIPO` | `NUMBER(2,0)` | ✓ |  |  |
| `CLASE` | `NUMBER(1,0)` | ✓ |  |  |
| `CONCEPTO` | `NUMBER(2,0)` | ✓ |  |  |
| `CODIGO_AXT` | `NUMBER(5,0)` | ✓ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✓ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |

---

## REGUL_RETENCIONES

**PK:** *(no encontrada)*  
**FK:** `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_OP`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`, `ASIENTO_ANUL` → `OWNER_RAFAM.ASIENTOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_REGUL` | `DATE` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(4,0)` | ✗ |  |  |
| `ESTADO_REGUL` | `VARCHAR2(1)` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `IMPORTE_TOTAL` | `NUMBER(15,2)` | ✗ |  |  |
| `CANT_IMPRES` | `NUMBER(4,0)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |

---

## REGUL_RETENCIONES_IMPUT

**PK:** *(no encontrada)*  
**FK:** `EJERCICIO` → `OWNER_RAFAM.CTA_CUENTAS`, `EJERCICIO` → `OWNER_RAFAM.DEDUCCIONES`, `CUENTA` → `OWNER_RAFAM.CTA_CUENTAS`, `CODIGO` → `OWNER_RAFAM.DEDUCCIONES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `NRO_RENG` | `NUMBER(7,0)` | ✗ |  |  |
| `CODIGO` | `NUMBER(3,0)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✗ |  |  |
| `CUENTA` | `VARCHAR2(9)` | ✗ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `CUENTA_GASTO` | `VARCHAR2(9)` | ✓ |  |  |

---

## REG_COMP

**PK:** `EJERCICIO`, `NRO_REG_COMP`  
**FK:** `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_RC`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `JURISDICCION` → `OWNER_RAFAM.DEPENDENCIAS`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `DEPENDENCIA` → `OWNER_RAFAM.DEPENDENCIAS`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REG_COMP` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_REG_COMP` | `DATE` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `TIPO_REGIS` | `VARCHAR2(1)` | ✗ |  |  |
| `NRO_ORIG` | `NUMBER(6,0)` | ✓ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✗ |  |  |
| `UNI_COMPRA` | `NUMBER(4,0)` | ✓ |  |  |
| `NRO_OC` | `NUMBER(6,0)` | ✓ |  |  |
| `DELEG_SOLIC` | `NUMBER(4,0)` | ✓ |  |  |
| `NRO_SOLIC` | `NUMBER(6,0)` | ✓ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `IMPORTE_TOT` | `NUMBER(15,2)` | ✗ |  |  |
| `ESTADO_REG_COMP` | `VARCHAR2(1)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `CANT_IMPRES` | `NUMBER(3,0)` | ✓ |  |  |
| `CONCEPTO` | `VARCHAR2(1000)` | ✓ |  |  |
| `FECH_RELOJ` | `DATE` | ✓ |  |  |
| `DEUDA` | `VARCHAR2(1)` | ✗ |  |  |
| `DEPENDENCIA` | `VARCHAR2(6)` | ✗ |  |  |
| `INSISTIDO` | `DATE` | ✓ |  |  |
| `RC_DIFERIDO` | `VARCHAR2(1)` | ✓ | 'N' |  |
| `EJERCICIO_ANT` | `NUMBER(4,0)` | ✓ |  |  |
| `NRO_REG_COMP_ANT` | `NUMBER(7,0)` | ✓ |  |  |
| `RC_EJERCICIO_ANT` | `VARCHAR2(1)` | ✓ | 'N' |  |

---

## REG_DEVEN

**PK:** `EJERCICIO`, `NRO_REG_DEVEN`  
**FK:** `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `LUG_EMI` → `OWNER_RAFAM.LOCALIDADES`, `EJERCICIO` → `OWNER_RAFAM.REG_COMP`, `EJERCICIO` → `OWNER_RAFAM.ASIENTOS`, `MOTIVO_ANUL` → `OWNER_RAFAM.MOT_BAJ_RD`, `ASIENTO` → `OWNER_RAFAM.ASIENTOS`, `NRO_REG_COMP` → `OWNER_RAFAM.REG_COMP`, `ASIENTO_ANUL` → `OWNER_RAFAM.ASIENTOS`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REG_DEVEN` | `NUMBER(7,0)` | ✗ |  |  |
| `FECH_REG_DEVEN` | `DATE` | ✗ |  |  |
| `NRO_REG_COMP` | `NUMBER(7,0)` | ✗ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✗ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✗ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `IMPORTE_TOT` | `NUMBER(15,2)` | ✗ |  |  |
| `ESTADO_REG_DEVEN` | `VARCHAR2(1)` | ✗ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `CANT_IMPRES` | `NUMBER(3,0)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(300)` | ✓ |  |  |
| `ASIENTO` | `NUMBER(7,0)` | ✓ |  |  |
| `ASIENTO_ANUL` | `NUMBER(7,0)` | ✓ |  |  |
| `F931` | `VARCHAR2(1)` | ✓ |  |  |

---

## RETENCIONES

**PK:** `EJERCICIO`, `NRO_CANCE`, `COD_RET`, `CUENTA`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.EGRESOS`, `EJERCICIO` → `OWNER_RAFAM.DEDUCCIONES`, `NRO_CANCE` → `OWNER_RAFAM.EGRESOS`, `COD_RET` → `OWNER_RAFAM.DEDUCCIONES`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_CANCE` | `NUMBER(7,0)` | ✗ |  |  |
| `COD_RET` | `NUMBER(3,0)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(15,2)` | ✓ |  |  |
| `CUENTA` | `VARCHAR2(9)` | ✗ |  |  |

---

## RETENCIONES_REGDED

**PK:** `EJERCICIO`, `NRO_REGUL`, `CODIGO`  
**FK:** `EJERCICIO` → `OWNER_RAFAM.DEDUCCIONES`, `EJERCICIO` → `OWNER_RAFAM.CTA_CUENTAS`, `CODIGO` → `OWNER_RAFAM.DEDUCCIONES`, `CUENTA` → `OWNER_RAFAM.CTA_CUENTAS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_REGUL` | `NUMBER(7,0)` | ✗ |  |  |
| `CODIGO` | `NUMBER(3,0)` | ✗ |  |  |
| `IMPORTE` | `NUMBER(10,2)` | ✓ |  |  |
| `CUENTA` | `VARCHAR2(9)` | ✗ |  |  |

---

## SOLIC_GASTOS

**PK:** `EJERCICIO`, `DELEG_SOLIC`, `NRO_SOLIC`  
**FK:** `DELEG_SOLIC` → `OWNER_RAFAM.DELEGACIONES`, `TIPO_DOC` → `OWNER_RAFAM.TIPO_DOC_RES`, `JURISDICCION` → `OWNER_RAFAM.DEPENDENCIAS`, `EJERCICIO` → `OWNER_RAFAM.PEDIDOS`, `CODIGO_UE` → `OWNER_RAFAM.UNI_EJEC`, `COD_LUG_ENT` → `OWNER_RAFAM.LUGARES_ENT`, `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `EJERCICIO` → `OWNER_RAFAM.FUEN_FIN`, `CODIGO_DEP` → `OWNER_RAFAM.DEPENDENCIAS`, `NRO_PED` → `OWNER_RAFAM.PEDIDOS`, `CODIGO_FF` → `OWNER_RAFAM.FUEN_FIN`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `DELEG_SOLIC` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_SOLIC` | `NUMBER(6,0)` | ✗ |  |  |
| `NRO_PED` | `NUMBER(6,0)` | ✓ |  |  |
| `LUG_EMI` | `VARCHAR2(5)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `CODIGO_UE` | `NUMBER(2,0)` | ✗ |  |  |
| `CODIGO_DEP` | `VARCHAR2(6)` | ✗ |  |  |
| `FECH_SOLIC` | `DATE` | ✗ |  |  |
| `TIPO_REGIS` | `VARCHAR2(1)` | ✗ |  |  |
| `NRO_ORIG` | `NUMBER(6,0)` | ✓ |  |  |
| `CODIGO_FF` | `NUMBER(3,0)` | ✗ |  |  |
| `IMPORTE_TOT` | `NUMBER(15,2)` | ✗ |  |  |
| `FECH_ENTREGA` | `DATE` | ✓ |  |  |
| `FECH_NECESIDAD` | `DATE` | ✓ |  |  |
| `FECH_EST_OC` | `DATE` | ✓ |  |  |
| `TIPO_DOC` | `VARCHAR2(5)` | ✓ |  |  |
| `NRO_DOC` | `NUMBER(7,0)` | ✓ |  |  |
| `ANIO_DOC` | `NUMBER(4,0)` | ✓ |  |  |
| `COD_LUG_ENT` | `VARCHAR2(5)` | ✓ |  |  |
| `ESTADO_SOLIC` | `VARCHAR2(1)` | ✓ |  |  |
| `CONFIRMADO` | `VARCHAR2(1)` | ✗ |  |  |
| `FECH_CONFIRM` | `DATE` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(120)` | ✓ |  |  |
| `CANT_IMP` | `NUMBER(2,0)` | ✗ |  |  |
| `SG_DIFERIDO` | `VARCHAR2(1)` | ✓ |  |  |

---

## SOLIC_GASTOS_ITEMS

**PK:** `EJERCICIO`, `DELEG_SOLIC`, `NRO_SOLIC`, `SOLIC_ITEM`  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `EJERCICIO` → `OWNER_RAFAM.ESTRUC_PROG`, `JURISDICCION` → `OWNER_RAFAM.ESTRUC_PROG`, `PROGRAMA` → `OWNER_RAFAM.ESTRUC_PROG`, `ACTIV_PROY` → `OWNER_RAFAM.ESTRUC_PROG`, `ACTIV_OBRA` → `OWNER_RAFAM.ESTRUC_PROG`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `EJERCICIO` | `NUMBER(4,0)` | ✗ |  |  |
| `DELEG_SOLIC` | `NUMBER(4,0)` | ✗ |  |  |
| `NRO_SOLIC` | `NUMBER(6,0)` | ✗ |  |  |
| `SOLIC_ITEM` | `NUMBER(4,0)` | ✗ |  |  |
| `INCISO` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PRIN` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_PARC` | `NUMBER(1,0)` | ✗ |  |  |
| `PAR_SUBP` | `NUMBER(1,0)` | ✗ |  |  |
| `TIPO` | `NUMBER(4,0)` | ✗ |  |  |
| `CLASE` | `NUMBER(5,0)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |
| `PROGRAMA` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_PROY` | `NUMBER(2,0)` | ✗ |  |  |
| `ACTIV_OBRA` | `NUMBER(2,0)` | ✗ |  |  |
| `DESCRIPCION` | `VARCHAR2(4000)` | ✗ |  |  |
| `CODIGO_UM` | `NUMBER(4,0)` | ✗ |  |  |
| `CANTIDAD` | `NUMBER(10,3)` | ✗ |  |  |
| `IMP_UNITARIO` | `NUMBER(15,5)` | ✗ |  |  |
| `CANT_ADJ` | `NUMBER(10,3)` | ✗ |  |  |
| `CANT_COTI` | `NUMBER(10,3)` | ✗ |  |  |
| `CANTIDAD_REAL` | `NUMBER(10,3)` | ✓ |  |  |
| `IMP_UNITARIO_REAL` | `NUMBER(15,5)` | ✓ |  |  |
| `IMPORTE_EJER` | `NUMBER(16,5)` | ✓ |  |  |
| `IMPORTE_DIFER` | `NUMBER(16,5)` | ✓ |  |  |
| `IMPORTE_EJER_REAL` | `NUMBER(16,5)` | ✓ |  |  |
| `IMPORTE_DIFER_REAL` | `NUMBER(16,5)` | ✓ |  |  |

---

## TES_DEPOSITOS_GARANTIAS

**PK:** `NRO_REC`, `NRO_RES`  
**FK:** `TIPO_GARAN` → `OWNER_RAFAM.TES_TIPO_GARANTIAS`, `CARACTER_GAR` → `OWNER_RAFAM.TES_CARACTER_GARANTIA`, `COMPA` → `OWNER_RAFAM.TES_COMPANIAS`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `MONEDA` → `OWNER_RAFAM.MONEDAS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `NRO_REC` | `NUMBER(9,0)` | ✗ |  |  |
| `NRO_RES` | `NUMBER(9,0)` | ✗ |  |  |
| `FECHA_ALTA` | `DATE` | ✗ |  |  |
| `NRO_EXPE` | `VARCHAR2(20)` | ✓ |  |  |
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `DETALLE` | `VARCHAR2(240)` | ✓ |  |  |
| `TIPO_GARAN` | `VARCHAR2(5)` | ✗ |  |  |
| `NRO_GARAN` | `VARCHAR2(15)` | ✓ |  |  |
| `COMPA` | `VARCHAR2(5)` | ✓ |  |  |
| `MONEDA` | `NUMBER(3,0)` | ✗ |  |  |
| `VALOR` | `NUMBER(12,2)` | ✗ |  |  |
| `VALOR_PESOS` | `NUMBER(12,2)` | ✗ |  |  |
| `ESTADO` | `VARCHAR2(2)` | ✗ |  |  |
| `FECHA_ESTADO` | `DATE` | ✗ |  |  |
| `CANT_REC` | `NUMBER(4,0)` | ✗ | 0 |  |
| `CANT_DEV` | `NUMBER(4,0)` | ✗ | 0 |  |
| `FECH_VENC` | `DATE` | ✓ |  |  |
| `CARACTER_GAR` | `VARCHAR2(25)` | ✓ |  |  |

---

## USUARIOS_JURISDICCIONES

**PK:** *(no encontrada)*  
**FK:** `JURISDICCION` → `OWNER_RAFAM.JURISDICCIONES`, `USUARIO` → `OWNER_RAFAM.USUARIOS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `USUARIO` | `VARCHAR2(20)` | ✗ |  |  |
| `JURISDICCION` | `VARCHAR2(10)` | ✗ |  |  |

---

## VI_SUBRUB_PROV

**PK:** `COD_PROV`, `CODIGO`, `COD_SUBRUBRO`  
**FK:** `CODIGO` → `OWNER_RAFAM.SUBRUBROS`, `CODIGO` → `OWNER_RAFAM.CAT_AGRUP`, `COD_PROV` → `OWNER_RAFAM.PROVEEDORES`, `COD_SUBRUBRO` → `OWNER_RAFAM.SUBRUBROS`  

| Columna | Tipo | Nulo | Default | Comentario |
|---------|------|------|---------|------------|
| `COD_PROV` | `NUMBER(5,0)` | ✗ |  |  |
| `CODIGO` | `NUMBER(4,0)` | ✗ |  |  |
| `COD_SUBRUBRO` | `NUMBER(3,0)` | ✗ |  |  |
