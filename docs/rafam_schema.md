# Esquema RAFAM — `OWNER_RAFAM`

> Generado automáticamente por `scripts/explore_schema.py` el 2026-03-30 19:10:40
> **No editar manualmente** — regenerar ejecutando el script.

## Índice de tablas

- [JURISDICCIONES](#jurisdicciones)
- [OC_ITEMS](#oc_items)
- [ORDEN_COMPRA](#orden_compra)
- [ORDEN_PAGO](#orden_pago)
- [PEDIDOS](#pedidos)
- [PED_ITEMS](#ped_items)
- [PROVEEDORES](#proveedores)
- [SOLIC_GASTOS](#solic_gastos)

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
| `FECH_CONFIRM` | `DATE` | ✓ |  |  | -> esta es mi fecha de cambio estado a registrado
| `CANT_IMPRES` | `NUMBER(3,0)` | ✓ |  |  |
| `FECH_ANUL` | `DATE` | ✓ |  |  |
| `MOTIVO_ANUL` | `VARCHAR2(6)` | ✓ |  |  |
| `OBSERVACIONES` | `VARCHAR2(1000)` | ✓ |  |  |
| `IMPORTE_TOT` | `NUMBER(15,5)` | ✗ |  |  |
| `COND_PAGO` | `VARCHAR2(6)` | ✗ |  |  |
| `DESC_COND_PAGO` | `VARCHAR2(45)` | ✓ |  |  |
| `OC_DIFERIDO` | `VARCHAR2(1)` | ✓ | 'N' |  |

**Valores de `ESTADO_OC`:**

| Valor | Registros |
|-------|-----------|
| `A` | 5448 | anulado 
| `N` | 712 | normal 
| `R` | 108122 | registrado

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


**Valores de `PED_ESTADO`:**

| Valor | Registros |
|-------|-----------|
| `A` | 392 | anulado
| `G` | 109112 | "generado"
| `N` | 2910 | normal
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
