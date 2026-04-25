# Mapeo de campos RAFAM → Paxapos

> Generado automáticamente por `scripts/update_field_mapping.py` el 2026-04-25 17:47:36  
> Fuente de columnas: SQLite dev (snapshots CSV)  
> Para actualizar el mapeo: editar `PAXAPOS_MAPPINGS` en el script y re-ejecutar.

---

## 1. Proveedores

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| PROVEEDORES | [PK] `COD_PROV` | proveedores | id_externo | ninguna |
| PROVEEDORES | `RAZON_SOCIAL` | proveedores | razon_social | trim() |
| PROVEEDORES | `TIPO_PROV` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `CUIT` | proveedores | cuit | _normalize_cuit() |
| PROVEEDORES | `FANTASIA` | proveedores | name | trim(); fallback a RAZON_SOCIAL |
| PROVEEDORES | `TIPO_SOC` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `COD_IVA` | proveedores | iva_condicion_id | mapeo IVA_MAP (RINS/MONOT/EXEN/CF/NGAN/RNI) |
| PROVEEDORES | `ING_BRUTOS` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `FECHA_ALTA` | proveedores | created_at | ninguna |
| PROVEEDORES | `FECHA_ULT_COMP` | proveedores | updated_at | ninguna |
| PROVEEDORES | `CALIF_PROV` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `COD_ESTADO` | proveedores | estado | mapeo de código |
| PROVEEDORES | `CALLE_POSTAL` | proveedores | domicilio | _join_address(CALLE_POSTAL, NRO_POSTAL) |
| PROVEEDORES | `NRO_POSTAL` | proveedores | domicilio | parte de _join_address (ver CALLE_POSTAL) |
| PROVEEDORES | `NRO_POSTAL_MED` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `PISO_POSTAL` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `DEPT_POSTAL` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `LOCA_POSTAL` | proveedores | localidad | _first_non_empty(LOCA_POSTAL, LOCA_LEGAL) |
| PROVEEDORES | `COD_POSTAL` | proveedores | codigo_postal | _first_non_empty(COD_POSTAL, COD_LEGAL) |
| PROVEEDORES | `PROV_POSTAL` | proveedores | provincia | _first_non_empty(PROV_POSTAL, PROV_LEGAL) |
| PROVEEDORES | `PAIS_POSTAL` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `CALLE_LEGAL` | proveedores | domicilio | _join_address(CALLE_LEGAL, NRO_LEGAL) — fallback |
| PROVEEDORES | `NRO_LEGAL` | proveedores | domicilio | parte de _join_address (ver CALLE_LEGAL) |
| PROVEEDORES | `NRO_LEGAL_MED` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `PISO_LEGAL` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `DEPT_LEGAL` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `LOCA_LEGAL` | proveedores | localidad | _first_non_empty fallback |
| PROVEEDORES | `COD_LEGAL` | proveedores | codigo_postal | _first_non_empty fallback |
| PROVEEDORES | `PROV_LEGAL` | proveedores | provincia | _first_non_empty fallback |
| PROVEEDORES | `PAIS_LEGAL` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `NRO_PAIS_TE1` | proveedores | telefono | _build_phone(NRO_PAIS_TE1, NRO_INTE_TE1, NRO_TELE_TE1) |
| PROVEEDORES | `NRO_INTE_TE1` | proveedores | telefono | parte de _build_phone (ver NRO_PAIS_TE1) |
| PROVEEDORES | `NRO_TELE_TE1` | proveedores | telefono | parte de _build_phone (ver NRO_PAIS_TE1) |
| PROVEEDORES | `NRO_PAIS_TE2` | proveedores | telefono | _build_phone — segundo teléfono (fallback) |
| PROVEEDORES | `NRO_INTE_TE2` | proveedores | telefono | parte de _build_phone segundo |
| PROVEEDORES | `NRO_TELE_TE2` | proveedores | telefono | parte de _build_phone segundo |
| PROVEEDORES | `NRO_PAIS_TE3` | proveedores | telefono | _build_phone — tercer teléfono (fallback) |
| PROVEEDORES | `NRO_INTE_TE3` | proveedores | telefono | parte de _build_phone tercero |
| PROVEEDORES | `NRO_TELE_TE3` | proveedores | telefono | parte de _build_phone tercero |
| PROVEEDORES | `TE_CELULAR` | proveedores | telefono | _first_non_empty fallback celular |
| PROVEEDORES | `FAX` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `EMAIL` | proveedores | mail | trim() |
| PROVEEDORES | `OBSERVACION` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `PROV_CAJA_CHICA` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `NRO_HAB_MUN` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `DISC_RET_SUSS` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `DISC_GCIAS_UTE` | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `DISC_IIBB_UTE` | *(completar)* | *(completar)* | *(completar)* |

---

## 2. Jurisdicciones

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| JURISDICCIONES | [PK] `JURISDICCION` | jurisdicciones | id_externo | ninguna |
| JURISDICCIONES | `DENOMINACION` | jurisdicciones | nombre | trim() |
| JURISDICCIONES | `SELECCIONABLE` | jurisdicciones | seleccionable | ninguna |
| JURISDICCIONES | `VIGENTE_DESDE` | jurisdicciones | vigente_desde | ninguna |
| JURISDICCIONES | `VIGENTE_HASTA` | jurisdicciones | vigente_hasta | ninguna |

---

## 3. Pedidos

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| PEDIDOS | [PK] `EJERCICIO` | pedidos | ejercicio | ninguna |
| PEDIDOS | [PK] `NUM_PED` | pedidos | numero_pedido | ninguna |
| PEDIDOS | `LUG_EMI` | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `FECH_EMI` | pedidos | fecha | ninguna |
| PEDIDOS | `NUM_PED_ORI` | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `FECH_EMI_ORI` | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `CODIGO_DEP` | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `CODIGO_UE` | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `JURISDICCION` | pedidos | jurisdiccion_id | lookup por id_externo (FK → JURISDICCIONES) |
| PEDIDOS | `COSTO_TOT` | pedidos | importe_total | ninguna |
| PEDIDOS | `OBSERVACIONES` | pedidos | observaciones | trim() |
| PEDIDOS | `PED_ESTADO` | pedidos | estado | mapeo de código |
| PEDIDOS | `CANT_IMP` | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `FECH_MODI_ULT` | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `CODIGO_FF` | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `COD_LUG_ENT` | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `PLAZO_ENT` | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `PER_CONSUMO` | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `FECH_ING_COMP` | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `RESP_RETIRA_PED` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | [PK] `EJERCICIO` | pedido_items | ejercicio | parte de FK → PEDIDOS |
| PED_ITEMS | [PK] `NUM_PED` | pedido_items | pedido_id | lookup por ejercicio+numero_pedido (FK → PEDIDOS) |
| PED_ITEMS | [PK] `ORDEN` | pedido_items | nro_item | ninguna |
| PED_ITEMS | `INCISO` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `PAR_PRIN` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `PAR_PARC` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `CLASE` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `TIPO` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `JURISDICCION` | pedido_items | jurisdiccion_id | lookup por id_externo (FK → JURISDICCIONES) |
| PED_ITEMS | `PROGRAMA` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `ACTIV_PROY` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `ACTIV_OBRA` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `CANTIDAD` | pedido_items | cantidad | ninguna |
| PED_ITEMS | `UNI_MED` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `DESCRIP_BIE` | pedido_items | descripcion | trim() |
| PED_ITEMS | `COSTO_UNI` | pedido_items | precio_unitario | ninguna |
| PED_ITEMS | `PED_FECH_EMI` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `PED_OBSERVACIONES` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `PED_CODIGO_DEP` | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `PED_COSTO_TOT` | *(completar)* | *(completar)* | *(completar)* |

---

## 4. Solicitudes de gasto

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| SOLIC_GASTOS | [PK] `EJERCICIO` | solicitudes_gasto | ejercicio | ninguna |
| SOLIC_GASTOS | [PK] `DELEG_SOLIC` | solicitudes_gasto | deleg_solic | ninguna |
| SOLIC_GASTOS | [PK] `NRO_SOLIC` | solicitudes_gasto | numero_solicitud | ninguna |
| SOLIC_GASTOS | `NRO_PED` | solicitudes_gasto | pedido_id | lookup ejercicio+numero_pedido (FK → PEDIDOS; NRO_PED → NUM_PED) |
| SOLIC_GASTOS | `LUG_EMI` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `JURISDICCION` | solicitudes_gasto | jurisdiccion_id | lookup por id_externo (FK → JURISDICCIONES) |
| SOLIC_GASTOS | `CODIGO_UE` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `CODIGO_DEP` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `FECH_SOLIC` | solicitudes_gasto | fecha | ninguna |
| SOLIC_GASTOS | `TIPO_REGIS` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `NRO_ORIG` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `CODIGO_FF` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `IMPORTE_TOT` | solicitudes_gasto | importe | ninguna |
| SOLIC_GASTOS | `FECH_ENTREGA` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `FECH_NECESIDAD` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `FECH_EST_OC` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `TIPO_DOC` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `NRO_DOC` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `ANIO_DOC` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `COD_LUG_ENT` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `ESTADO_SOLIC` | solicitudes_gasto | estado | mapeo de código |
| SOLIC_GASTOS | `CONFIRMADO` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `FECH_CONFIRM` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `FECH_ANUL` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `MOTIVO_ANUL` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `OBSERVACIONES` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `CANT_IMP` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `SG_DIFERIDO` | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `OP_COD_PROV` | solicitudes_gasto | proveedor_id | lookup por id_externo (FK → PROVEEDORES) |

---

## 5. Órdenes de compra

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| ORDEN_COMPRA | [PK] `EJERCICIO` | ordenes_compra | ejercicio | ninguna |
| ORDEN_COMPRA | [PK] `UNI_COMPRA` | ordenes_compra | uni_compra | ninguna |
| ORDEN_COMPRA | [PK] `NRO_OC` | ordenes_compra | numero_oc | ninguna |
| ORDEN_COMPRA | `NRO_ADJUD` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `FECH_OC` | ordenes_compra | fecha | ninguna |
| ORDEN_COMPRA | `LUG_EMI` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `COD_PROV` | ordenes_compra | proveedor_id | lookup por id_externo (FK → PROVEEDORES) |
| ORDEN_COMPRA | `COD_LUG_ENT` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `FECH_ENTREGA` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `ESTADO_OC` | ordenes_compra | estado | N→pendiente, A→anulada |
| ORDEN_COMPRA | `TIPO_DOC_APROB` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `NRO_DOC_APROB` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `ANIO_DOC_APROB` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `CONFIRMADO` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `FECH_CONFIRM` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `CANT_IMPRES` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `FECH_ANUL` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `MOTIVO_ANUL` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `OBSERVACIONES` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `IMPORTE_TOT` | ordenes_compra | importe_total | ninguna |
| ORDEN_COMPRA | `COND_PAGO` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `DESC_COND_PAGO` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `OC_DIFERIDO` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `CUIT` | ordenes_compra | cuit_proveedor | ninguna (desnormalizado) |
| ORDEN_COMPRA | `ESTADO_PROVEEDOR` | *(completar)* | *(completar)* | *(completar)* |
| OC_ITEMS | [PK] `EJERCICIO` | oc_items | ejercicio | parte de FK → ORDEN_COMPRA |
| OC_ITEMS | [PK] `UNI_COMPRA` | oc_items | uni_compra | parte de FK → ORDEN_COMPRA |
| OC_ITEMS | [PK] `NRO_OC` | oc_items | orden_compra_id | lookup por clave compuesta (FK → ORDEN_COMPRA) |
| OC_ITEMS | [PK] `ITEM_OC` | oc_items | nro_item | ninguna |
| OC_ITEMS | `DELEG_SOLIC` | oc_items | deleg_solic | parte de FK → SOLIC_GASTOS |
| OC_ITEMS | `NRO_SOLIC` | oc_items | solic_gasto_id | lookup por clave compuesta (FK → SOLIC_GASTOS) |
| OC_ITEMS | `ITEM_REAL` | *(completar)* | *(completar)* | *(completar)* |
| OC_ITEMS | `DESCRIPCION` | oc_items | descripcion | trim() |
| OC_ITEMS | `CANTIDAD` | oc_items | cantidad | ninguna |
| OC_ITEMS | `IMP_UNITARIO` | oc_items | precio_unitario | ninguna |
| OC_ITEMS | `CANT_RECIB` | *(completar)* | *(completar)* | *(completar)* |
| OC_ITEMS | `IMPORTE_EJER` | *(completar)* | *(completar)* | *(completar)* |
| OC_ITEMS | `COD_PROV` | oc_items | proveedor_id | lookup por id_externo (FK → PROVEEDORES) |
| OC_ITEMS | `OC_FECH_OC` | *(completar)* | *(completar)* | *(completar)* |
| OC_ITEMS | `OC_OBSERVACIONES` | *(completar)* | *(completar)* | *(completar)* |
| OC_ITEMS | `ESTADO_OC` | *(completar)* | *(completar)* | *(completar)* |
| OC_ITEMS | `SG_JURISDICCION` | oc_items | jurisdiccion_id | lookup por id_externo (FK → JURISDICCIONES) |

---

## 6. Órdenes de pago

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| ORDEN_PAGO | [PK] `EJERCICIO` | ordenes_pago | ejercicio | ninguna |
| ORDEN_PAGO | [PK] `NRO_OP` | ordenes_pago | numero_op | ninguna |
| ORDEN_PAGO | `FECH_OP` | ordenes_pago | fecha | ninguna |
| ORDEN_PAGO | `LUG_EMI` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `CODIGO_FF` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `JURISDICCION` | ordenes_pago | jurisdiccion_id | lookup por id_externo (FK → JURISDICCIONES) |
| ORDEN_PAGO | `CODIGO_UE` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `COD_PROV` | ordenes_pago | proveedor_id | lookup por id_externo (FK → PROVEEDORES) |
| ORDEN_PAGO | `TIPO_OP` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `ESTADO_OP` | ordenes_pago | estado | C→pagada, A→anulada, N→pendiente |
| ORDEN_PAGO | `TIPO_DOC` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `NRO_DOC` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `ANIO_DOC` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `NRO_CANCE` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `CONFIRMADO` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `FECH_CONFIRM` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `IMPORTE_TOTAL` | ordenes_pago | importe | ninguna |
| ORDEN_PAGO | `IMPORTE_LIQUIDO` | ordenes_pago | importe_liquido | ninguna |
| ORDEN_PAGO | `CANT_IMPRES` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `FECH_ANUL` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `MOTIVO_ANUL` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `CONCEPTO` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `OBSERVACIONES` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `COD_EMP` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `IMPORTE_BONIFICACION` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `IMPORTE_DEDUCCIONES` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `ASIENTO` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `ASIENTO_ANUL` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `MONTO_SIN_IVA` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `DEUDA` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `BLOQUEADA` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `RECURSO` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `PERCIBIDO` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `NO_PAGADO` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `PAGADO` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `RECO_DEU_ORDEN` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `RECO_DEU_EJERCICIO` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `RECO_DEU_COMPRA` | ordenes_pago | orden_compra_id | lookup por clave compuesta (FK → ORDEN_COMPRA; confirmar UNI_COMPRA) |
| ORDEN_PAGO | `RECO_DEU_COMPRA_EJER` | ordenes_pago | orden_compra_ejercicio | parte de FK → ORDEN_COMPRA |
| ORDEN_PAGO | `F931` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `SICORE` | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `SG_DELEG_SOLIC` | ordenes_pago | deleg_solic | parte de FK → SOLIC_GASTOS |
| ORDEN_PAGO | `SG_NRO_SOLIC` | ordenes_pago | solic_gasto_id | lookup por clave compuesta (FK → SOLIC_GASTOS) |

---

## 7. Relaciones entre tablas (claves foráneas)

### 7.1 Claves primarias

| Tabla | Clave primaria |
|-------|----------------|
| JURISDICCIONES | `JURISDICCION` |
| PROVEEDORES | `COD_PROV` |
| PEDIDOS | `EJERCICIO` + `NUM_PED` |
| PED_ITEMS | `EJERCICIO` + `NUM_PED` + `ORDEN` |
| SOLIC_GASTOS | `EJERCICIO` + `DELEG_SOLIC` + `NRO_SOLIC` |
| ORDEN_COMPRA | `EJERCICIO` + `UNI_COMPRA` + `NRO_OC` |
| OC_ITEMS | `EJERCICIO` + `UNI_COMPRA` + `NRO_OC` + `ITEM_OC` |
| ORDEN_PAGO | `EJERCICIO` + `NRO_OP` |

### 7.2 Tabla de FKs

| Tabla hija | Columna(s) FK | Tabla padre | Columna(s) referenciada | Nota |
|------------|---------------|-------------|-------------------------|------|
| PEDIDOS | `JURISDICCION` | JURISDICCIONES | `JURISDICCION` |  |
| PED_ITEMS | `EJERCICIO` + `NUM_PED` | PEDIDOS | `EJERCICIO` + `NUM_PED` |  |
| PED_ITEMS | `JURISDICCION` | JURISDICCIONES | `JURISDICCION` |  |
| SOLIC_GASTOS | `EJERCICIO` + `NRO_PED` | PEDIDOS | `EJERCICIO` + `NUM_PED` | NRO_PED → NUM_PED (nombres distintos en cada tabla) |
| SOLIC_GASTOS | `JURISDICCION` | JURISDICCIONES | `JURISDICCION` |  |
| SOLIC_GASTOS | `OP_COD_PROV` | PROVEEDORES | `COD_PROV` |  |
| ORDEN_COMPRA | `COD_PROV` | PROVEEDORES | `COD_PROV` |  |
| OC_ITEMS | `EJERCICIO` + `UNI_COMPRA` + `NRO_OC` | ORDEN_COMPRA | `EJERCICIO` + `UNI_COMPRA` + `NRO_OC` |  |
| OC_ITEMS | `EJERCICIO` + `DELEG_SOLIC` + `NRO_SOLIC` | SOLIC_GASTOS | `EJERCICIO` + `DELEG_SOLIC` + `NRO_SOLIC` |  |
| OC_ITEMS | `COD_PROV` | PROVEEDORES | `COD_PROV` |  |
| OC_ITEMS | `SG_JURISDICCION` | JURISDICCIONES | `JURISDICCION` |  |
| ORDEN_PAGO | `COD_PROV` | PROVEEDORES | `COD_PROV` |  |
| ORDEN_PAGO | `JURISDICCION` | JURISDICCIONES | `JURISDICCION` |  |
| ORDEN_PAGO | `EJERCICIO` + `SG_DELEG_SOLIC` + `SG_NRO_SOLIC` | SOLIC_GASTOS | `EJERCICIO` + `DELEG_SOLIC` + `NRO_SOLIC` |  |
| ORDEN_PAGO | `RECO_DEU_COMPRA_EJER` + `RECO_DEU_COMPRA` | ORDEN_COMPRA | `EJERCICIO` + `NRO_OC` | confirmar UNI_COMPRA |

---
