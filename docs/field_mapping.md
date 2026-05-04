# Mapeo de campos RAFAM → Paxapos

> Generado automáticamente por `scripts/update_field_mapping.py` el 2026-05-02 11:19:31  
> Fuente de columnas: Oracle `OWNER_RAFAM`  
> Para actualizar el mapeo: editar `PAXAPOS_MAPPINGS` en el script y re-ejecutar.

---

## 1. Proveedores

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| PROVEEDORES | [PK] `COD_PROV` *(tipo: `NUMBER`)* | proveedores | id_externo | ninguna |
| PROVEEDORES | `RAZON_SOCIAL` *(tipo: `VARCHAR(70)`)* | proveedores | razon_social | trim() |
| PROVEEDORES | `TIPO_PROV` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `CUIT` *(tipo: `VARCHAR(13)`)* | proveedores | cuit | _normalize_cuit() |
| PROVEEDORES | `FANTASIA` *(tipo: `VARCHAR(70)`)* | proveedores | name | trim(); fallback a RAZON_SOCIAL |
| PROVEEDORES | `TIPO_SOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `COD_IVA` *(tipo: `VARCHAR(5)`)* | proveedores | iva_condicion_id | mapeo IVA_MAP (RINS/MONOT/EXEN/CF/NGAN/RNI) |
| PROVEEDORES | `ING_BRUTOS` *(tipo: `VARCHAR(25)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `FECHA_ALTA` *(tipo: `DATE`)* | proveedores | created_at | ninguna |
| PROVEEDORES | `FECHA_ULT_COMP` *(tipo: `DATE`)* | proveedores | updated_at | ninguna |
| PROVEEDORES | `CALIF_PROV` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `COD_ESTADO` *(tipo: `NUMBER`)* | proveedores | estado | mapeo de código |
| PROVEEDORES | `CALLE_POSTAL` *(tipo: `VARCHAR(40)`)* | proveedores | domicilio | _join_address(CALLE_POSTAL, NRO_POSTAL) |
| PROVEEDORES | `NRO_POSTAL` *(tipo: `VARCHAR(5)`)* | proveedores | domicilio | parte de _join_address (ver CALLE_POSTAL) |
| PROVEEDORES | `NRO_POSTAL_MED` *(tipo: `VARCHAR(3)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `PISO_POSTAL` *(tipo: `VARCHAR(4)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `DEPT_POSTAL` *(tipo: `VARCHAR(4)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `LOCA_POSTAL` *(tipo: `VARCHAR(5)`)* | proveedores | localidad | _first_non_empty(LOCA_POSTAL, LOCA_LEGAL) |
| PROVEEDORES | `COD_POSTAL` *(tipo: `VARCHAR(8)`)* | proveedores | codigo_postal | _first_non_empty(COD_POSTAL, COD_LEGAL) |
| PROVEEDORES | `PROV_POSTAL` *(tipo: `VARCHAR(5)`)* | proveedores | provincia | _first_non_empty(PROV_POSTAL, PROV_LEGAL) |
| PROVEEDORES | `PAIS_POSTAL` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `CALLE_LEGAL` *(tipo: `VARCHAR(40)`)* | proveedores | domicilio | _join_address(CALLE_LEGAL, NRO_LEGAL) — fallback |
| PROVEEDORES | `NRO_LEGAL` *(tipo: `VARCHAR(5)`)* | proveedores | domicilio | parte de _join_address (ver CALLE_LEGAL) |
| PROVEEDORES | `NRO_LEGAL_MED` *(tipo: `VARCHAR(3)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `PISO_LEGAL` *(tipo: `VARCHAR(4)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `DEPT_LEGAL` *(tipo: `VARCHAR(4)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `LOCA_LEGAL` *(tipo: `VARCHAR(5)`)* | proveedores | localidad | _first_non_empty fallback |
| PROVEEDORES | `COD_LEGAL` *(tipo: `VARCHAR(8)`)* | proveedores | codigo_postal | _first_non_empty fallback |
| PROVEEDORES | `PROV_LEGAL` *(tipo: `VARCHAR(5)`)* | proveedores | provincia | _first_non_empty fallback |
| PROVEEDORES | `PAIS_LEGAL` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `NRO_PAIS_TE1` *(tipo: `VARCHAR(3)`)* | proveedores | telefono | _build_phone(NRO_PAIS_TE1, NRO_INTE_TE1, NRO_TELE_TE1) |
| PROVEEDORES | `NRO_INTE_TE1` *(tipo: `VARCHAR(6)`)* | proveedores | telefono | parte de _build_phone (ver NRO_PAIS_TE1) |
| PROVEEDORES | `NRO_TELE_TE1` *(tipo: `VARCHAR(12)`)* | proveedores | telefono | parte de _build_phone (ver NRO_PAIS_TE1) |
| PROVEEDORES | `NRO_PAIS_TE2` *(tipo: `VARCHAR(3)`)* | proveedores | telefono | _build_phone — segundo teléfono (fallback) |
| PROVEEDORES | `NRO_INTE_TE2` *(tipo: `VARCHAR(6)`)* | proveedores | telefono | parte de _build_phone segundo |
| PROVEEDORES | `NRO_TELE_TE2` *(tipo: `VARCHAR(12)`)* | proveedores | telefono | parte de _build_phone segundo |
| PROVEEDORES | `NRO_PAIS_TE3` *(tipo: `VARCHAR(3)`)* | proveedores | telefono | _build_phone — tercer teléfono (fallback) |
| PROVEEDORES | `NRO_INTE_TE3` *(tipo: `VARCHAR(6)`)* | proveedores | telefono | parte de _build_phone tercero |
| PROVEEDORES | `NRO_TELE_TE3` *(tipo: `VARCHAR(12)`)* | proveedores | telefono | parte de _build_phone tercero |
| PROVEEDORES | `TE_CELULAR` *(tipo: `VARCHAR(15)`)* | proveedores | telefono | _first_non_empty fallback celular |
| PROVEEDORES | `FAX` *(tipo: `VARCHAR(15)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `EMAIL` *(tipo: `VARCHAR(50)`)* | proveedores | mail | trim() |
| PROVEEDORES | `OBSERVACION` *(tipo: `VARCHAR(2000)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `PROV_CAJA_CHICA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `NRO_HAB_MUN` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `DISC_RET_SUSS` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `DISC_GCIAS_UTE` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| PROVEEDORES | `DISC_IIBB_UTE` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |

---

## 2. Jurisdicciones

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| JURISDICCIONES | [PK] `JURISDICCION` *(tipo: `VARCHAR(10)`)* | jurisdicciones | id_externo | ninguna |
| JURISDICCIONES | `DENOMINACION` *(tipo: `VARCHAR(50)`)* | jurisdicciones | nombre | trim() |
| JURISDICCIONES | `SELECCIONABLE` *(tipo: `VARCHAR(1)`)* | jurisdicciones | seleccionable | ninguna |
| JURISDICCIONES | `VIGENTE_DESDE` *(tipo: `NUMBER`)* | jurisdicciones | vigente_desde | ninguna |
| JURISDICCIONES | `VIGENTE_HASTA` *(tipo: `NUMBER`)* | jurisdicciones | vigente_hasta | ninguna |

---

## 3. Pedidos

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| PEDIDOS | [PK] `EJERCICIO` *(tipo: `NUMBER`)* | pedidos | ejercicio | ninguna |
| PEDIDOS | [PK] `NUM_PED` *(tipo: `NUMBER`)* | pedidos | numero_pedido | ninguna |
| PEDIDOS | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `FECH_EMI` *(tipo: `DATE`)* | pedidos | fecha | ninguna |
| PEDIDOS | `NUM_PED_ORI` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `FECH_EMI_ORI` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `CODIGO_DEP` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | pedidos | jurisdiccion_id | lookup por id_externo (FK → JURISDICCIONES) |
| PEDIDOS | `COSTO_TOT` *(tipo: `NUMBER`)* | pedidos | importe_total | ninguna |
| PEDIDOS | `OBSERVACIONES` *(tipo: `VARCHAR(4000)`)* | pedidos | observaciones | trim() |
| PEDIDOS | `PED_ESTADO` *(tipo: `VARCHAR(5)`)* | pedidos | estado | mapeo de código |
| PEDIDOS | `CANT_IMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `FECH_MODI_ULT` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `COD_LUG_ENT` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `PLAZO_ENT` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `PER_CONSUMO` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `FECH_ING_COMP` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| PEDIDOS | `RESP_RETIRA_PED` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | [PK] `EJERCICIO` *(tipo: `NUMBER`)* | pedido_items | ejercicio | parte de FK → PEDIDOS |
| PED_ITEMS | [PK] `NUM_PED` *(tipo: `NUMBER`)* | pedido_items | pedido_id | lookup por ejercicio+numero_pedido (FK → PEDIDOS) |
| PED_ITEMS | [PK] `ORDEN` *(tipo: `NUMBER`)* | pedido_items | nro_item | ninguna |
| PED_ITEMS | `INCISO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `PAR_PRIN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `PAR_PARC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `CLASE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `TIPO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | pedido_items | jurisdiccion_id | lookup por id_externo (FK → JURISDICCIONES) |
| PED_ITEMS | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `CANTIDAD` *(tipo: `NUMBER`)* | pedido_items | cantidad | ninguna |
| PED_ITEMS | `UNI_MED` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_ITEMS | `DESCRIP_BIE` *(tipo: `VARCHAR(4000)`)* | pedido_items | descripcion | trim() |
| PED_ITEMS | `COSTO_UNI` *(tipo: `NUMBER`)* | pedido_items | precio_unitario | ninguna |

---

## 4. Solicitudes de gasto

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| SOLIC_GASTOS | [PK] `EJERCICIO` *(tipo: `NUMBER`)* | solicitudes_gasto | ejercicio | ninguna |
| SOLIC_GASTOS | [PK] `DELEG_SOLIC` *(tipo: `NUMBER`)* | solicitudes_gasto | deleg_solic | ninguna |
| SOLIC_GASTOS | [PK] `NRO_SOLIC` *(tipo: `NUMBER`)* | solicitudes_gasto | numero_solicitud | ninguna |
| SOLIC_GASTOS | `NRO_PED` *(tipo: `NUMBER`)* | solicitudes_gasto | pedido_id | lookup ejercicio+numero_pedido (FK → PEDIDOS; NRO_PED → NUM_PED) |
| SOLIC_GASTOS | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | solicitudes_gasto | jurisdiccion_id | lookup por id_externo (FK → JURISDICCIONES) |
| SOLIC_GASTOS | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `CODIGO_DEP` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `FECH_SOLIC` *(tipo: `DATE`)* | solicitudes_gasto | fecha | ninguna |
| SOLIC_GASTOS | `TIPO_REGIS` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `NRO_ORIG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `IMPORTE_TOT` *(tipo: `NUMBER`)* | solicitudes_gasto | importe | ninguna |
| SOLIC_GASTOS | `FECH_ENTREGA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `FECH_NECESIDAD` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `FECH_EST_OC` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `COD_LUG_ENT` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `ESTADO_SOLIC` *(tipo: `VARCHAR(1)`)* | solicitudes_gasto | estado | mapeo de código |
| SOLIC_GASTOS | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `OBSERVACIONES` *(tipo: `VARCHAR(120)`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `CANT_IMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS | `SG_DIFERIDO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |

---

## 5. Órdenes de compra

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| ORDEN_COMPRA | [PK] `EJERCICIO` *(tipo: `NUMBER`)* | ordenes_compra | ejercicio | ninguna |
| ORDEN_COMPRA | [PK] `UNI_COMPRA` *(tipo: `NUMBER`)* | ordenes_compra | uni_compra | ninguna |
| ORDEN_COMPRA | [PK] `NRO_OC` *(tipo: `NUMBER`)* | ordenes_compra | numero_oc | ninguna |
| ORDEN_COMPRA | `NRO_ADJUD` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `FECH_OC` *(tipo: `DATE`)* | ordenes_compra | fecha | ninguna |
| ORDEN_COMPRA | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `COD_PROV` *(tipo: `NUMBER`)* | ordenes_compra | proveedor_id | lookup por id_externo (FK → PROVEEDORES) |
| ORDEN_COMPRA | `COD_LUG_ENT` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `FECH_ENTREGA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `ESTADO_OC` *(tipo: `VARCHAR(1)`)* | ordenes_compra | estado | N→pendiente, A→anulada |
| ORDEN_COMPRA | `TIPO_DOC_APROB` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `NRO_DOC_APROB` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `ANIO_DOC_APROB` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `OBSERVACIONES` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `IMPORTE_TOT` *(tipo: `NUMBER`)* | ordenes_compra | importe_total | ninguna |
| ORDEN_COMPRA | `COND_PAGO` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `DESC_COND_PAGO` *(tipo: `VARCHAR(45)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_COMPRA | `OC_DIFERIDO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| OC_ITEMS | [PK] `EJERCICIO` *(tipo: `NUMBER`)* | oc_items | ejercicio | parte de FK → ORDEN_COMPRA |
| OC_ITEMS | [PK] `UNI_COMPRA` *(tipo: `NUMBER`)* | oc_items | uni_compra | parte de FK → ORDEN_COMPRA |
| OC_ITEMS | [PK] `NRO_OC` *(tipo: `NUMBER`)* | oc_items | orden_compra_id | lookup por clave compuesta (FK → ORDEN_COMPRA) |
| OC_ITEMS | [PK] `ITEM_OC` *(tipo: `NUMBER`)* | oc_items | nro_item | ninguna |
| OC_ITEMS | `DELEG_SOLIC` *(tipo: `NUMBER`)* | oc_items | deleg_solic | parte de FK → SOLIC_GASTOS |
| OC_ITEMS | `NRO_SOLIC` *(tipo: `NUMBER`)* | oc_items | solic_gasto_id | lookup por clave compuesta (FK → SOLIC_GASTOS) |
| OC_ITEMS | `ITEM_REAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| OC_ITEMS | `DESCRIPCION` *(tipo: `VARCHAR(4000)`)* | oc_items | descripcion | trim() |
| OC_ITEMS | `CANTIDAD` *(tipo: `NUMBER`)* | oc_items | cantidad | ninguna |
| OC_ITEMS | `IMP_UNITARIO` *(tipo: `NUMBER`)* | oc_items | precio_unitario | ninguna |
| OC_ITEMS | `CANT_RECIB` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| OC_ITEMS | `IMPORTE_EJER` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |

---

## 6. Órdenes de pago

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| ORDEN_PAGO | [PK] `EJERCICIO` *(tipo: `NUMBER`)* | ordenes_pago | ejercicio | ninguna |
| ORDEN_PAGO | [PK] `NRO_OP` *(tipo: `NUMBER`)* | ordenes_pago | numero_op | ninguna |
| ORDEN_PAGO | `FECH_OP` *(tipo: `DATE`)* | ordenes_pago | fecha | ninguna |
| ORDEN_PAGO | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | ordenes_pago | jurisdiccion_id | lookup por id_externo (FK → JURISDICCIONES) |
| ORDEN_PAGO | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `COD_PROV` *(tipo: `NUMBER`)* | ordenes_pago | proveedor_id | lookup por id_externo (FK → PROVEEDORES) |
| ORDEN_PAGO | `TIPO_OP` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `ESTADO_OP` *(tipo: `VARCHAR(1)`)* | ordenes_pago | estado | C→pagada, A→anulada, N→pendiente |
| ORDEN_PAGO | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `NRO_CANCE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `IMPORTE_TOTAL` *(tipo: `NUMBER`)* | ordenes_pago | importe | ninguna |
| ORDEN_PAGO | `IMPORTE_LIQUIDO` *(tipo: `NUMBER`)* | ordenes_pago | importe_liquido | ninguna |
| ORDEN_PAGO | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `CONCEPTO` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `COD_EMP` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `IMPORTE_BONIFICACION` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `IMPORTE_DEDUCCIONES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `MONTO_SIN_IVA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `DEUDA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `BLOQUEADA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `RECURSO` *(tipo: `VARCHAR(15)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `PERCIBIDO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `NO_PAGADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `PAGADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `RECO_DEU_ORDEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `RECO_DEU_EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `RECO_DEU_COMPRA` *(tipo: `NUMBER`)* | ordenes_pago | orden_compra_id | lookup por clave compuesta (FK → ORDEN_COMPRA; confirmar UNI_COMPRA) |
| ORDEN_PAGO | `RECO_DEU_COMPRA_EJER` *(tipo: `NUMBER`)* | ordenes_pago | orden_compra_ejercicio | parte de FK → ORDEN_COMPRA |
| ORDEN_PAGO | `F931` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO | `SICORE` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |

---

## 7. Retenciones, deducciones y comprobantes

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| RG_COMP | *(sin columnas — verificar que la DB está cargada)* | | | |
| CTA_HOJA_DE_RUTA | `USUARIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `PE_EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `PE_NRO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `PE_FECH` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `PE_CODIGO_DEP` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `PE_CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `PE_JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `PE_ESTADO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `PE_COSTO_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_DELEG_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_NRO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_NRO_PED` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_CODIGO_DEP` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_FECH` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_TIPO_REGIS` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `SG_CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OC_EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OC_UNI_COMPRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OC_NRO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OC_NRO_ADJUD` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OC_FECH` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OC_COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OC_ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OC_CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OC_IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_NRO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_FECH` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_TIPO_REGIS` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_NRO_ORIG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_UNI_COMPRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_NRO_OC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_DELEG_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_NRO_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RC_DEPENDENCIA` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RD_EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RD_NRO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RD_FECH` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RD_NRO_REG_COMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RD_JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RD_COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RD_CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RD_IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RD_ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `RD_CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `CC_TIPO_COMPROB` *(tipo: `VARCHAR(3)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `CC_NRO` *(tipo: `VARCHAR(13)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `CC_COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `CC_NRO_REG_COMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `CC_FECH_MOVIM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `CC_FECH_COMPROB` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `CC_IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `CC_IMPORTE_PAG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_NRO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_FECH` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_TIPO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_NRO_CANCE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_HOJA_DE_RUTA | `OP_IMPORTE_LIQUIDO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RETENCIONES | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RETENCIONES | `NRO_CANCE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RETENCIONES | `COD_RET` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RETENCIONES | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RETENCIONES | `CUENTA` *(tipo: `VARCHAR(9)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEDUCCIONES | `CODIGO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEDUCCIONES | `DESCRIPCION` *(tipo: `VARCHAR(100)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEDUCCIONES | `TIPO_DEDUC` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEDUCCIONES | `PORCENTAJE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEDUCCIONES | `SALDO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEDUCCIONES | `DECRIPCION_AB` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEDUCCIONES | `CODIGO_AXT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEDUCCIONES | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |

---

## 8. Tablas relacionadas — Proveedores

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| ACT_IMP_PROV | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ACT_IMP_PROV | `COD_IMP` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ACT_IMP_PROV | `COD_ACTIV` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ACT_IMP_PROV | `COEF_CONV_MULTI` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `NRO_ADJUDIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `NRO_COTI` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `DELEG_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `NRO_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `FECH_ADJUD` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `TIPO_DOC_APROB` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `NRO_DOC_APROB` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `ANIO_DOC_APROB` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `FECH_ENTREGA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `OBSERVACIONES` *(tipo: `VARCHAR(2000)`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `COND_PAGO` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `DESC_COND_PAGO` *(tipo: `VARCHAR(45)`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `NRO_LLAMADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ADJUDICACIONES | `CERRADA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `COD_BEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `APYNOM` *(tipo: `VARCHAR(70)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `FECHA_ALTA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `PRIORIDAD` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `SITUACION` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `FECHA_SITUACION` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `MOTIVO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `OBSER_SITUACION` *(tipo: `VARCHAR(100)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `CALLE` *(tipo: `VARCHAR(40)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `NUMERO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `NUMERO_AD` *(tipo: `VARCHAR(3)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `PISO` *(tipo: `VARCHAR(4)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `DEPTO` *(tipo: `VARCHAR(4)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `LOCA_POS` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `COD_POS` *(tipo: `VARCHAR(8)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `PROVINCIA` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `PAIS` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `CARACTER` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `TIPO_INSTR` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `COPIA_INSTR` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `FECHA_DESIG` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `COPIA_DESIG` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `SOLICITANTE1` *(tipo: `VARCHAR(40)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `TIPO_DOC11` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `NUM_DOC11` *(tipo: `VARCHAR(13)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `F5601` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `FECHA_VEN1` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `TIPO_DOC21` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `NUM_DOC21` *(tipo: `VARCHAR(13)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `EXPEDIDA1` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `TIPO_DOC31` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `NUM_DOC31` *(tipo: `VARCHAR(15)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `PAIS_DOC31` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `SOLICITANTE2` *(tipo: `VARCHAR(40)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `TIPO_DOC12` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `NUM_DOC12` *(tipo: `VARCHAR(13)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `F5602` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `FECHA_VEN2` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `TIPO_DOC22` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `NUM_DOC22` *(tipo: `VARCHAR(13)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `EXPEDIDA2` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `TIPO_DOC32` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `NUM_DOC32` *(tipo: `VARCHAR(15)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `PAIS_DOC32` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `OBSERVACIONES` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| BENEFICIARIOS | `LEYENDA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `COD_BEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `COD_CES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `APYNOM` *(tipo: `VARCHAR(70)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `FECHA_ALTA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `FECHA_INICIO` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `PRIORIDAD` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `SITUACION` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `FECHA_SITUACION` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `MOTIVO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `OBSER_SITUACION` *(tipo: `VARCHAR(100)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `CALLE` *(tipo: `VARCHAR(40)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `NUMERO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `NUMERO_AD` *(tipo: `VARCHAR(3)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `PISO` *(tipo: `VARCHAR(4)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `DEPTO` *(tipo: `VARCHAR(4)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `LOCA_POS` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `COD_POS` *(tipo: `VARCHAR(8)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `PROVINCIA` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `PAIS` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `INSTRUMENTO` *(tipo: `VARCHAR(40)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `PUBLICO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `ESCRIBANO` *(tipo: `VARCHAR(40)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `REGISTRO` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `ESCRITURA` *(tipo: `VARCHAR(15)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `FECHA_ESCRITURA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `TESTIMONIO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `PRIVADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `COPIA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `CERTIFICA` *(tipo: `VARCHAR(40)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `IMPO_CEDIDO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `IMPO_CANCELADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `OBSERVACIONES` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| CESIONARIOS | `LEYENDA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `NRO_COTI` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `PLAZO_ENT` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `DESC_PLAZO_ENT` *(tipo: `VARCHAR(45)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `FECH_ENTREGA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `COD_LUG_ENT` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `COND_PAGO` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `DESC_COND_PAGO` *(tipo: `VARCHAR(45)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `OBSERVACIONES` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `FECHA_CARGA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `FECHA_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `MOTIV_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `MANT_OFERTA` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `DESC_MANT_OFERTA` *(tipo: `VARCHAR(45)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV | `NRO_LLAMADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `NRO_COTI` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `ITEM_REAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `NRO_ALTER` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `CANTIDAD` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `DETALLE` *(tipo: `VARCHAR(4000)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `COSTO_UNITARIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `ESPEC_TEC` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `OBSERVACIONES` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `FECHA_CARGA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `CODIGO_UM` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| COTIZA_PROV_ITEMS | `NRO_LLAMADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `TIPO` *(tipo: `VARCHAR(3)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `NRO_COMPROB` *(tipo: `VARCHAR(13)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `NRO_REG_COMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `FECH_MOVIM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `FECH_COMPROB` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `FECH_VENCIM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `FECH_CONFORMAC` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `PORC_BONIF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `FECH_BONIF` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `IMPORTE_COMPR` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `IMPORTE_PAGADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `RINDE_IVA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `PORC_IVA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `PORC_CRED_FISCAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `LIST_LIBRO_IVA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `FECH_LIST_IVA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `COD_PROV_REAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `RAZON_SOCIAL` *(tipo: `VARCHAR(70)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `CUIT` *(tipo: `VARCHAR(13)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `DETALLE` *(tipo: `VARCHAR(200)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_COMPROB | `IMPORTE_SIN_IVA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_CTACTE_MOVS | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_CTACTE_MOVS | `ORDEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_CTACTE_MOVS | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_CTACTE_MOVS | `FECH_MOV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_CTACTE_MOVS | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_CTACTE_MOVS | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_CTACTE_MOVS | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_CTACTE_MOVS | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_CTACTE_MOVS | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_CTACTE_MOVS | `CODIGO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_CTACTE_MOVS | `FECH_HORA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_PROVEEDORES_ALICUOTAS | `ANIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_PROVEEDORES_ALICUOTAS | `MES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_PROVEEDORES_ALICUOTAS | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_PROVEEDORES_ALICUOTAS | `ALICUOTA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_PROVEEDORES_ALICUOTAS | `FECHA_CONSULTA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_UTE | `COD_PROV_UTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_UTE | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_UTE | `PORCENTAJE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_UTE | `PORC_GAN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_UTE | `PORC_ING_BRUT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTR_DOCUM_PROV | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTR_DOCUM_PROV | `COD_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTR_DOCUM_PROV | `FECHA_VENC` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CTR_DOCUM_PROV | `OBSERVACIONES` *(tipo: `VARCHAR(60)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTR_DOCUM_PROV | `FECHA_ACTUALIZ` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| DATOS_PART_CONS | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DATOS_PART_CONS | `ESPECIALIDAD` *(tipo: `VARCHAR(100)`)* | *(completar)* | *(completar)* | *(completar)* |
| DATOS_PART_CONS | `TRABAJOS` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| DATOS_PART_CONT | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DATOS_PART_CONT | `CAPITAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DATOS_PART_CONT | `CONSTANCIA_BCO` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| DATOS_PART_CONT | `ESPECIALIDAD` *(tipo: `VARCHAR(100)`)* | *(completar)* | *(completar)* | *(completar)* |
| DATOS_PART_CONT | `CANT_PERSONAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DATOS_PART_CONT | `TRABAJOS` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| DATOS_PART_CONT | `TIEMPO_EXIS_EMP` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| DEUFLO_PROV | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEUFLO_PROV | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEUFLO_PROV | `EJERCICIO_OC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEUFLO_PROV | `ORDEN_COMPRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEUFLO_PROV | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEUFLO_PROV | `ES_PROY` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEUFLO_PROV | `IMPORTE_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEUFLO_PROV | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `NRO_DEV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `FECH_DEV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `NRO_RECEP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `FECH_RECEP` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `UNI_COMPRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `NRO_OC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `CODIGO_DEP` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `FECH_EMI_DEV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `MOTIVO_ANUL` *(tipo: `VARCHAR(4)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `UNI_RECEP` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVOLUCION | `FECHA_HORA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| EGRESOS | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| EGRESOS | `NRO_CANCE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| EGRESOS | `ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| EGRESOS | `FECHA_ANULA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| EGRESOS | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| EGRESOS | `TIPO_CANCE` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| EGRESOS | `OBSERVACIONES` *(tipo: `VARCHAR(250)`)* | *(completar)* | *(completar)* | *(completar)* |
| EGRESOS | `USUARIO` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| EGRESOS | `FECHA_ALTA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `COD_BEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `COD_EMB` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `AUTOS` *(tipo: `VARCHAR(70)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `JUZGADO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `SECRETARIA` *(tipo: `VARCHAR(40)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `OFICIO` *(tipo: `VARCHAR(15)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `FECHA_ALTA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `FECHA_EMB` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `SITUACION` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `FECHA_SITUACION` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `MOTIVO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `OBSER_SITUACION` *(tipo: `VARCHAR(100)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `CALLE` *(tipo: `VARCHAR(40)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `NUMERO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `NUMERO_AD` *(tipo: `VARCHAR(3)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `PISO` *(tipo: `VARCHAR(4)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `DEPTO` *(tipo: `VARCHAR(4)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `LOCA_POS` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `COD_POS` *(tipo: `VARCHAR(8)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `PROVINCIA` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `PAIS` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `IMPO_EMBARGADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `IMPO_CANCELADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `OBSERVACIONES` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| EMBARGOS | `LEYENDA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| HISTO_ESTADOS | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| HISTO_ESTADOS | `COD_ESTADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| HISTO_ESTADOS | `CAUSA` *(tipo: `VARCHAR(200)`)* | *(completar)* | *(completar)* | *(completar)* |
| HISTO_ESTADOS | `FECHA_CARGA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| NOMINA_PROV | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| NOMINA_PROV | `NRO_COTI` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| NOMINA_PROV | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| NOMINA_PROV | `FECH_EMI_COTI` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| NOMINA_PROV | `NRO_CERTIF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| NOMINA_PROV | `NRO_LLAMADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| NOMINA_PROV | `ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC_UTE | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC_UTE | `NRO_OP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC_UTE | `CODIGO_DEDUC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC_UTE | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC_UTE | `PORCENTAJE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC_UTE | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC_UTE | `COD_ACTIV` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC_UTE | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC_UTE | `NRO_OP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC_UTE | `CODIGO_DEDUC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC_UTE | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC_UTE | `PORCENTAJE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC_UTE | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC_UTE | `COD_ACTIV` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `NRO_REINT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `INCISO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `PAR_PRIN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `PAR_PARC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `PAR_SUBP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT_PRESUP | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `LEGAJO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `NRO_CARGO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `FECH_MOV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `NRO_OFICINA` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `TIPO_RELACION` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `DEDICACION` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `FORMA_PAGO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `LUGAR_PAGO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `FRECUENCIA_PAGO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `VALOR_MULTI_1` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `VALOR_MULTI_2` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `VALOR_MULTI_3` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `VALOR_MULTI_4` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `VALOR_MULTI_5` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `VALOR_MULTI_6` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `OBSERVACIONES` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `RELACION_LABORAL` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `COD_PROV_INTERNO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `LIQUIDAR` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES | `INCENTIVO_DOC` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `LEGAJO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `NRO_CARGO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `FECH_MOV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `NRO_OFICINA` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `TIPO_RELACION` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `DEDICACION` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `FORMA_PAGO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `LUGAR_PAGO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `FRECUENCIA_PAGO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `VALOR_MULTI_1` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `VALOR_MULTI_2` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `VALOR_MULTI_3` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `VALOR_MULTI_4` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `VALOR_MULTI_5` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `VALOR_MULTI_6` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `OBSERVACIONES` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `RELACION_LABORAL` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `COD_PROV_INTERNO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_AGENTES_HIST | `LIQUIDAR` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_CONCEPTOS_PROVEEDOR | `CONCEPTO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_CONCEPTOS_PROVEEDOR | `PROVEEDOR` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `FECH_REGUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `TIPO_CAMBIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `NRO_OP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `ESTADO_REGUL` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `IMPORTE_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_OCEA | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `NRO_RENG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `INCISO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `PAR_PRIN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `PAR_PARC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `PAR_SUBP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_IMPUT | `DEUDA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `FECH_REGUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `TIPO_DESA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `DELEG_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `NRO_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `NRO_REG_COMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `NRO_REG_DEVEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `ESTADO_REGUL` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `IMPORTE_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_DESAF | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `NRO_REC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `NRO_RES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `FECHA_ALTA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `NRO_EXPE` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `DETALLE` *(tipo: `VARCHAR(240)`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `TIPO_GARAN` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `NRO_GARAN` *(tipo: `VARCHAR(15)`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `COMPA` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `MONEDA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `VALOR` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `VALOR_PESOS` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `ESTADO` *(tipo: `VARCHAR(2)`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `FECHA_ESTADO` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `CANT_REC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `CANT_DEV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `FECH_VENC` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| TES_DEPOSITOS_GARANTIAS | `CARACTER_GAR` *(tipo: `VARCHAR(25)`)* | *(completar)* | *(completar)* | *(completar)* |
| VI_SUBRUB_PROV | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| VI_SUBRUB_PROV | `CODIGO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| VI_SUBRUB_PROV | `COD_SUBRUBRO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |

---

## 9. Tablas relacionadas — Jurisdicciones

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| CALCULO_MODIF | `ANIO_PRESUP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CALCULO_MODIF | `FECH_MOV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CALCULO_MODIF | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| CALCULO_MODIF | `TIPO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CALCULO_MODIF | `CLASE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CALCULO_MODIF | `CONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CALCULO_MODIF | `SUBCONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CALCULO_MODIF | `IMPORTE_MODIF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CALCULO_MODIF | `ORIGEN` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| CALCULO_MODIF | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| CALCULO_MODIF | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CALCULO_MODIF | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CALCULO_MODIF | `FECH_HORA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| CUOTAS_JURISDIC | `ANIO_PRESUP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CUOTAS_JURISDIC | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| CUOTAS_JURISDIC | `TRIM1_CUOTA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CUOTAS_JURISDIC | `TRIM2_CUOTA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CUOTAS_JURISDIC | `TRIM3_CUOTA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CUOTAS_JURISDIC | `TRIM4_CUOTA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CUOTAS_JURISDIC | `TRIM1_COMPR` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CUOTAS_JURISDIC | `TRIM2_COMPR` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CUOTAS_JURISDIC | `TRIM3_COMPR` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CUOTAS_JURISDIC | `TRIM4_COMPR` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_TMP_REG_DEVEN_IMP | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_TMP_REG_DEVEN_IMP | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_TMP_REG_DEVEN_IMP | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_TMP_REG_DEVEN_IMP | `INCISO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_TMP_REG_DEVEN_IMP | `PAR_PRIN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_TMP_REG_DEVEN_IMP | `PAR_PARC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_TMP_REG_DEVEN_IMP | `PAR_SUBP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_TMP_REG_DEVEN_IMP | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_TMP_REG_DEVEN_IMP | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_TMP_REG_DEVEN_IMP | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_TMP_REG_DEVEN_IMP | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEPENDENCIAS | `CODIGO` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEPENDENCIAS | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEPENDENCIAS | `DESCRIPCION` *(tipo: `VARCHAR(50)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEPENDENCIAS | `PADRE` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEPENDENCIAS | `SELECCIONABLE` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `ANIO_PRESUP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `SECUENCIA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `TIPO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `CLASE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `CONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `SUBCONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `ANIO_CUOTA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `CUOTA` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `FECH_DEVEN` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `FECH_MOV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `OBSERVACIONES` *(tipo: `VARCHAR(100)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| DEVENGAMIENTOS | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `ANIO_PRESUP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `DESAGREGA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `DENOMINACION` *(tipo: `VARCHAR(100)`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `DENOMINACION_AB` *(tipo: `VARCHAR(25)`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `EJECUTADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `ESTIMADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `PROGRAMADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `CODIGO_PRESTAMO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `FINALIDAD` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `FUNCION` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `SUBFUNCION` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `CREDITO_INIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `CREDITO_MODIF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `PREVENTIVO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `COMPROMISO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `DEVENGADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `PAGADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `PPG` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ESTRUC_PROG | `PPG_PORCEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `ANIO_PRESUP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `FECHA_REGIS` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `ITEM1A` *(tipo: `VARCHAR(2000)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `ITEM1B` *(tipo: `VARCHAR(2000)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `ITEM1C` *(tipo: `VARCHAR(2000)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `ITEM1D` *(tipo: `VARCHAR(2000)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `ITEM1E` *(tipo: `VARCHAR(2000)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `ITEM2A` *(tipo: `VARCHAR(2000)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `ITEM2B` *(tipo: `VARCHAR(2000)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `ITEM2C` *(tipo: `VARCHAR(2000)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `ITEM2D` *(tipo: `VARCHAR(2000)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `ITEM3A` *(tipo: `VARCHAR(2000)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO1 | `FIRMA` *(tipo: `VARCHAR(30)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `ANIO_PRESUP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `TIPO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `CLASE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `CONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `SUBCONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `EJECUTADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `ESTIMADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `PROGRAMADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `PROY1` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `PROY2` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `EXENCIONES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `OTRAS` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `POLITICA_TRIB_1` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `POLITICA_TRIB_2` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO2 | `VAL_PROY_MODIF` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO4 | `ANIO_PRESUP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO4 | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO4 | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO4 | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO4 | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO4 | `FECHA_REGIS` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO4 | `DESCRIPCION1` *(tipo: `VARCHAR(1978)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO4 | `DESCRIPCION2` *(tipo: `VARCHAR(1978)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO4 | `DESCRIPCION3` *(tipo: `VARCHAR(1978)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO4 | `DESCRIPCION4` *(tipo: `VARCHAR(1978)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO4 | `DESCRIPCION5` *(tipo: `VARCHAR(1978)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIO4 | `DESCRIPCION6` *(tipo: `VARCHAR(1978)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC1 | `ANIO_PRESUP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC1 | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC1 | `GASTO` *(tipo: `VARCHAR(2)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC1 | `TRIMESTRE1` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC1 | `TRIMESTRE2` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC1 | `TRIMESTRE3` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC1 | `TRIMESTRE4` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `ANIO_PRESUP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `CODIGO_PROY` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `INGRESOS_GASTOS` *(tipo: `VARCHAR(3)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `ANIO1` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `ANIO2` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `ANIO3` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `ANIO4` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `ANIO5` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `ANIO6` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `ANIO7` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `ANIO8` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `ANIO9` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOC2 | `ANIO10` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOP4 | `ANIO_PRESUP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOP4 | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| FORMULARIOP4 | `TRIMESTRE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `NRO_ORDEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `DOCU_TIPO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `DOCU_NRO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `FECHA_DE_REGISTRO` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `NRO_CANCE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `BOCA_RECAUDA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `DEPENDENCIA` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `DOCU_TIPO_REGULADO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `DOCU_NRO_REGULADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `DOCU_TIPO_REGULADOR` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `DOCU_NRO_REGULADOR` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `TIPO_DE_INGRESO` *(tipo: `VARCHAR(2)`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `CONTRIBUYENTE` *(tipo: `VARCHAR(40)`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `NRO_CONTRIB` *(tipo: `VARCHAR(11)`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `DEDUCCIONES` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `REIM_NRO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `FECHA_DOC` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| INGRESOS | `FECHA_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ING_COD_INGRESOS_DET | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ING_COD_INGRESOS_DET | `COD_INGRESO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ING_COD_INGRESOS_DET | `ORDEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ING_COD_INGRESOS_DET | `PORCENTAJE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ING_COD_INGRESOS_DET | `TIPO_INGRESO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ING_COD_INGRESOS_DET | `TIPO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ING_COD_INGRESOS_DET | `CLASE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ING_COD_INGRESOS_DET | `CONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ING_COD_INGRESOS_DET | `SUBCONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ING_COD_INGRESOS_DET | `CODIGO_AXT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ING_COD_INGRESOS_DET | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| ING_COD_INGRESOS_DET | `CUENTA` *(tipo: `VARCHAR(9)`)* | *(completar)* | *(completar)* | *(completar)* |
| METAS_PROG | `ANIO_PRESUP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| METAS_PROG | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| METAS_PROG | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| METAS_PROG | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| METAS_PROG | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| METAS_PROG | `CODIGO_META` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| METAS_PROG | `CODIGO_UM` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| METAS_PROG | `CANT_EJECUTADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| METAS_PROG | `CANT_ESTIMADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| METAS_PROG | `CANT_PROGRAMADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| METAS_PROG | `CODIGO_PRESTAMO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `SEC_MOV_COMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `FECH_MOV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `INCISO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `PAR_PRIN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `PAR_PARC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `PAR_SUBP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `NRO_REG_COMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `NRO_REINT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `FECH_HORA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `NRO_OPEA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `NRO_RENG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_COMP | `IMPORTE_DIFER` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `SEC_MOV_REC_DEV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `FECH_MOV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `TIPO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `CLASE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `CONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `SUBCONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `DOCU_TIPO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `DOCU_NRO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `CUOTA` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `RECURSO_ING` *(tipo: `VARCHAR(3)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_REC_DEV | `CONCEPTO_ING` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_CONCEPTOS_GASTOS_M | `CONCEPTO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_CONCEPTOS_GASTOS_M | `TIPO_PLANTA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_CONCEPTOS_GASTOS_M | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_CONCEPTOS_GASTOS_M | `AGRUPAMIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_CONCEPTOS_GASTOS_M | `ANIO_PRESUP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_CONCEPTOS_GASTOS_M | `INCISO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_CONCEPTOS_GASTOS_M | `PAR_PRIN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_CONCEPTOS_GASTOS_M | `PAR_PARC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_CONCEPTOS_GASTOS_M | `PAR_SUBP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_SELECCION_DET | `SELECCION` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_SELECCION_DET | `INDICE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_SELECCION_DET | `TIPO` *(tipo: `VARCHAR(2)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_SELECCION_DET | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_SELECCION_DET | `JURISDICCIONF` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_SELECCION_DET | `DEPENDENCIA` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_SELECCION_DET | `DEPENDENCIAF` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_SELECCION_DET | `LEGAJO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PER_SELECCION_DET | `NRO_CARGO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PRE_JURIS_RECURSOS | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PRE_JURIS_RECURSOS | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| PRE_JURIS_RECURSOS | `TIPO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PRE_JURIS_RECURSOS | `CLASE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PRE_JURIS_RECURSOS | `CONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PRE_JURIS_RECURSOS | `SUBCONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_RECUR_IMPUT | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_RECUR_IMPUT | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_RECUR_IMPUT | `NRO_RENG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_RECUR_IMPUT | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_RECUR_IMPUT | `TIPO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_RECUR_IMPUT | `CLASE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_RECUR_IMPUT | `CONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_RECUR_IMPUT | `SUBCONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_RECUR_IMPUT | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_RECUR_IMPUT | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RECURSOS_EX_IMPUT | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RECURSOS_EX_IMPUT | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RECURSOS_EX_IMPUT | `NRO_RENG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RECURSOS_EX_IMPUT | `SUBCONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RECURSOS_EX_IMPUT | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RECURSOS_EX_IMPUT | `TIPO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RECURSOS_EX_IMPUT | `CLASE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RECURSOS_EX_IMPUT | `CONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RECURSOS_EX_IMPUT | `CODIGO_AXT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RECURSOS_EX_IMPUT | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RECURSOS_EX_IMPUT | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RECURSOS_EX_IMPUT | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `FECH_REGUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `ESTADO_REGUL` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `IMPORTE_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `DELEG_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `NRO_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `SOLIC_ITEM` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `INCISO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `PAR_PRIN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `PAR_PARC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `PAR_SUBP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `TIPO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `CLASE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `DESCRIPCION` *(tipo: `VARCHAR(4000)`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `CODIGO_UM` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `CANTIDAD` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `IMP_UNITARIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `CANT_ADJ` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `CANT_COTI` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `CANTIDAD_REAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `IMP_UNITARIO_REAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `IMPORTE_EJER` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `IMPORTE_DIFER` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `IMPORTE_EJER_REAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| SOLIC_GASTOS_ITEMS | `IMPORTE_DIFER_REAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| USUARIOS_JURISDICCIONES | `USUARIO` *(tipo: `VARCHAR(20)`)* | *(completar)* | *(completar)* | *(completar)* |
| USUARIOS_JURISDICCIONES | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |

---

## 10. Tablas relacionadas — Órdenes de compra y pago

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| CTA_IMPUT_PERSONAL | `NRO_IMPUT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_IMPUT_PERSONAL | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_IMPUT_PERSONAL | `NRO_REG_COMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_IMPUT_PERSONAL | `NRO_REG_DEVEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_IMPUT_PERSONAL | `NRO_COMPROB` *(tipo: `VARCHAR(13)`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_IMPUT_PERSONAL | `NRO_OP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| CTA_IMPUT_PERSONAL | `IMPORTE_DEVEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `SEC_MOV_PAG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `FECH_MOV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `INCISO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `PAR_PRIN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `PAR_PARC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `PAR_SUBP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `NRO_OP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `NRO_REINT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `NRO_OPEA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_PAG | `NRO_RENG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `FECH_REGUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `TIPO_CAMBIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `NRO_OP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `ESTADO_REGUL` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `IMPORTE_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| OC_PLAN_ENT | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| OC_PLAN_ENT | `UNI_COMPRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| OC_PLAN_ENT | `NRO_OC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| OC_PLAN_ENT | `ITEM_OC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| OC_PLAN_ENT | `OC_PLAN_SEC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| OC_PLAN_ENT | `COD_LUG_ENT` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| OC_PLAN_ENT | `CANTIDAD` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| OC_PLAN_ENT | `FECH_ENTREGA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `NRO_RECEP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `FECH_RECEP` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `UNI_COMPRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `NRO_OC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `TIPO_DOC_APROB` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `NRO_DOC_APROB` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `ANIO_DOC_APROB` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `OBSERVACIONES` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `MOTIVO_ANUL` *(tipo: `VARCHAR(4)`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `UNI_RECEP` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `EJERCICIO_OC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `FECHA_HORA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `DONANTE` *(tipo: `VARCHAR(50)`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `EJERCICIO_REG_COM` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RECEPCION | `NRO_REG_COMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |

---

## 11. Tablas relacionadas — Pedidos y deducciones

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| PED_COTIZACIONES | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `NRO_COTI` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `NRO_PED` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `DELEG_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `NRO_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `TIPO_DOC_RES` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `NRO_DOC_RES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `ANIO_DOC_RES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `TIPO_CONT` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `NRO_CONT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `ANIO_CONT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `FECH_APERT` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `HORA_APERT` *(tipo: `VARCHAR(8)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `FECH_EMI_COMP` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `PLAZO_ENT` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `DESC_PLAZO_ENT` *(tipo: `VARCHAR(45)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `COD_LUG_ENT` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `MANT_OFERTA` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `DESC_MANT_OFERTA` *(tipo: `VARCHAR(45)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `COND_PAGO` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `DESC_COND_PAGO` *(tipo: `VARCHAR(45)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `OBSERVACIONES` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `ESTADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `COSTO_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `NRO_LLAMADO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `CARGA_NOMINA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `FECH_PED` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| PED_COTIZACIONES | `CERRADA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC | `NRO_OP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC | `CODIGO_DEDUC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC | `IMPORTE_RETEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC | `COMPROB_DEDUC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC | `ALICUOTA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC | `TIPO_GENERAC` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC | `CUENTA` *(tipo: `VARCHAR(9)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC | `COEF_CONV_MULTI` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC | `ACTIVIDAD` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA_DEDUC | `TIPO_ALICUOTA` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC | `NRO_OP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC | `CODIGO_DEDUC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC | `IMPORTE_RETEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC | `COMPROB_DEDUC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC | `ALICUOTA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC | `TIPO_GENERAC` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC | `CUENTA` *(tipo: `VARCHAR(9)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC | `COEF_CONV_MULTI` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC | `ACTIVIDAD` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGO_DEDUC | `TIPO_ALICUOTA` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES_IMPUT | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES_IMPUT | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES_IMPUT | `NRO_RENG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES_IMPUT | `CODIGO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES_IMPUT | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES_IMPUT | `CUENTA` *(tipo: `VARCHAR(9)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES_IMPUT | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_RETENCIONES_IMPUT | `CUENTA_GASTO` *(tipo: `VARCHAR(9)`)* | *(completar)* | *(completar)* | *(completar)* |
| RETENCIONES_REGDED | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RETENCIONES_REGDED | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RETENCIONES_REGDED | `CODIGO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RETENCIONES_REGDED | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| RETENCIONES_REGDED | `CUENTA` *(tipo: `VARCHAR(9)`)* | *(completar)* | *(completar)* | *(completar)* |

---

## 12. Tablas con múltiples relaciones

| Tabla RAFAM | Campo RAFAM | Tabla Paxapos | Campo Paxapos | Transformación |
|-------------|-------------|---------------|---------------|----------------|
| MOV_EXTRAPRES_DEV | `SEC_MOV_DEV_EX` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_DEV | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_DEV | `FECH_MOV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_DEV | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_DEV | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_DEV | `CODIGO_AXT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_DEV | `NRO_OP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_DEV | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_DEV | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_DEV | `DEUDA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_DEV | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_DEV | `NRO_REINT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_DEV | `NRO_OPEA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_PAG | `SEC_MOV_PAG_EX` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_PAG | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_PAG | `FECH_MOV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_PAG | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_PAG | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_PAG | `CODIGO_AXT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_PAG | `NRO_OP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_PAG | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_PAG | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_PAG | `NRO_REINT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_PAG | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_PAG | `NRO_OPEA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_REC | `SEC_MOV_EX_REC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_REC | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_REC | `FECH_MOV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_REC | `DOCU_TIPO` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_REC | `DOCU_NRO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_REC | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_REC | `CODIGO_AXT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_EXTRAPRES_REC | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `SEC_MOV_DEV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `FECH_MOV` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `INCISO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `PAR_PRIN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `PAR_PARC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `PAR_SUBP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `NRO_REG_DEVEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `IMPORTE_COMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `ASIENTO_RENG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `NRO_REINT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `DEUDA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `NRO_OPEA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| MOV_PRES_DEV | `NRO_RENG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `NRO_DEVOL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `FECH_DEVOL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `ESTADO_DEVOL` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `NRO_CANCE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `IMPORTE_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_DEVOL | `FORMA_DE_PAGO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `NRO_OP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `FECH_OP` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `ORIGEN_OP` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `TIPO_OP` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `EJERCICIO_ANT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `NRO_REG_COMP_ANT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `NRO_OP_ANT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `INCISO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `PAR_PRIN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `PAR_PARC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `PAR_SUBP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `CODIGO_AXT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `ESTADO_OP` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `IMPORTE_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `IMPORTE_LIQUIDO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `IMPORTE_DEDUCCIONES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `NRO_CANCE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `OBSERVACIONES` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `CONCEPTO` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `IMPORTE_SIN_IVA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_PAGOEA | `PORCENTAJE_IVA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `NRO_REINT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `FECH_REINT` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `TIPO_REINT` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `ESTADO_REINT` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `NRO_CANCE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `IMPORTE_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `FORMA_DE_PAGO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `CLEARING` *(tipo: `VARCHAR(3)`)* | *(completar)* | *(completar)* | *(completar)* |
| ORDEN_REINT | `DEUDA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `NRO_REG_COMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `FECH_REG_COMP` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `TIPO_REGIS` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `NRO_ORIG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `UNI_COMPRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `NRO_OC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `DELEG_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `NRO_SOLIC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `IMPORTE_TOT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `ESTADO_REG_COMP` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `CONCEPTO` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `FECH_RELOJ` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `DEUDA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `DEPENDENCIA` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `INSISTIDO` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `RC_DIFERIDO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `EJERCICIO_ANT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `NRO_REG_COMP_ANT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_COMP | `RC_EJERCICIO_ANT` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `NRO_REG_DEVEN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `FECH_REG_DEVEN` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `NRO_REG_COMP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `IMPORTE_TOT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `ESTADO_REG_DEVEN` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REG_DEVEN | `F931` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `NRO_RENG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `INCISO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `PAR_PRIN` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `PAR_PARC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `PAR_SUBP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `PROGRAMA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `ACTIV_PROY` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `ACTIV_OBRA` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `CODIGO_AXT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `DEUDA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CAMBIO_PE_IMPUT | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_EX_IMPUT | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_EX_IMPUT | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_EX_IMPUT | `NRO_RENG` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_EX_IMPUT | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_EX_IMPUT | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_EX_IMPUT | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_EX_IMPUT | `CODIGO_AXT` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_EX_IMPUT | `IMPORTE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_EX_IMPUT | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_EX_IMPUT | `DEUDA` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_CORREC_EX_IMPUT | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `FECH_REGUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `ESTADO_REGUL` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `IMPORTE_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `CONCEPTO` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `FECH_HORA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS | `NRO_CANCE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `FECH_REGUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `CODIGO_FF` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `ESTADO_REGUL` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `IMPORTE_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `CONCEPTO` *(tipo: `VARCHAR(1000)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `FECH_HORA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_GASTOS_EX | `NRO_CANCE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `EJERCICIO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `NRO_REGUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `FECH_REGUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `LUG_EMI` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `JURISDICCION` *(tipo: `VARCHAR(10)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `CODIGO_UE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `COD_PROV` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `ESTADO_REGUL` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `TIPO_DOC` *(tipo: `VARCHAR(5)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `NRO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `ANIO_DOC` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `FORMA_DE_PAGO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `NRO_OP` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `TIPO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `CLASE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `CONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `SUBCONCEPTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `CONFIRMADO` *(tipo: `VARCHAR(1)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `FECH_CONFIRM` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `IMPORTE_TOTAL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `CANT_IMPRES` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `FECH_ANUL` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `MOTIVO_ANUL` *(tipo: `VARCHAR(6)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `OBSERVACIONES` *(tipo: `VARCHAR(300)`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `ASIENTO` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `ASIENTO_ANUL` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `FECH_HORA` *(tipo: `DATE`)* | *(completar)* | *(completar)* | *(completar)* |
| REGUL_OPE_DEVOL | `NRO_CANCE` *(tipo: `NUMBER`)* | *(completar)* | *(completar)* | *(completar)* |

---

## 13. Relaciones entre tablas (claves foráneas)

### 13.1 Claves primarias

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

### 13.2 Tabla de FKs

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

## 14. Relaciones inferidas por coincidencia de columnas

> Columnas con el mismo nombre presentes en 2 o mas tablas — indican joins posibles.
> Complementa la seccion 7 (FKs declaradas).

| Columna compartida | Tabla A | Tabla B |
|--------------------|---------|---------|
| `EJERCICIO` | PEDIDOS | PED_ITEMS |
| `EJERCICIO` | PEDIDOS | SOLIC_GASTOS |
| `EJERCICIO` | PEDIDOS | ORDEN_COMPRA |
| `EJERCICIO` | PEDIDOS | OC_ITEMS |
| `EJERCICIO` | PEDIDOS | ORDEN_PAGO |
| `EJERCICIO` | PED_ITEMS | SOLIC_GASTOS |
| `EJERCICIO` | PED_ITEMS | ORDEN_COMPRA |
| `EJERCICIO` | PED_ITEMS | OC_ITEMS |
| `EJERCICIO` | PED_ITEMS | ORDEN_PAGO |
| `EJERCICIO` | SOLIC_GASTOS | ORDEN_COMPRA |
| `EJERCICIO` | SOLIC_GASTOS | OC_ITEMS |
| `EJERCICIO` | SOLIC_GASTOS | ORDEN_PAGO |
| `EJERCICIO` | ORDEN_COMPRA | OC_ITEMS |
| `EJERCICIO` | ORDEN_COMPRA | ORDEN_PAGO |
| `EJERCICIO` | OC_ITEMS | ORDEN_PAGO |
| `COD_PROV` | PROVEEDORES | ORDEN_COMPRA |
| `COD_PROV` | PROVEEDORES | ORDEN_PAGO |
| `COD_PROV` | ORDEN_COMPRA | ORDEN_PAGO |
| `JURISDICCION` | JURISDICCIONES | PEDIDOS |
| `JURISDICCION` | JURISDICCIONES | PED_ITEMS |
| `JURISDICCION` | JURISDICCIONES | SOLIC_GASTOS |
| `JURISDICCION` | JURISDICCIONES | ORDEN_PAGO |
| `JURISDICCION` | PEDIDOS | PED_ITEMS |
| `JURISDICCION` | PEDIDOS | SOLIC_GASTOS |
| `JURISDICCION` | PEDIDOS | ORDEN_PAGO |
| `JURISDICCION` | PED_ITEMS | SOLIC_GASTOS |
| `JURISDICCION` | PED_ITEMS | ORDEN_PAGO |
| `JURISDICCION` | SOLIC_GASTOS | ORDEN_PAGO |
| `NRO_OC` | ORDEN_COMPRA | OC_ITEMS |
| `NRO_SOLIC` | SOLIC_GASTOS | OC_ITEMS |
| `NUM_PED` | PEDIDOS | PED_ITEMS |
| `UNI_COMPRA` | ORDEN_COMPRA | OC_ITEMS |
| `DELEG_SOLIC` | SOLIC_GASTOS | OC_ITEMS |

---

## 15. Flujo de negocio — queries de ejemplo

> Queries que recorren el ciclo de compra completo.
> Compatible con Oracle y SQLite (sustituir prefijo de schema segun entorno).

### Pedido completo con sus items

Navega PEDIDOS → PED_ITEMS para ver las lineas de cada solicitud interna.

```sql
SELECT
  p.EJERCICIO,
  p.NUM_PED,
  p.FECH_EMI,
  p.PED_ESTADO,
  p.COSTO_TOT,
  pi.ORDEN        AS item_nro,
  pi.DESCRIP_BIE  AS descripcion,
  pi.CANTIDAD,
  pi.COSTO_UNI
FROM OWNER_RAFAM.PEDIDOS  p
JOIN OWNER_RAFAM.PED_ITEMS pi ON  pi.EJERCICIO = p.EJERCICIO
                         AND pi.NUM_PED   = p.NUM_PED
ORDER BY p.EJERCICIO DESC, p.NUM_PED DESC, pi.ORDEN
FETCH FIRST 10 ROWS ONLY
```

### Flujo completo: Pedido → Solicitud de gasto → OC → OP

Recorre el ciclo de compra completo desde el pedido original hasta el pago efectivo. Util para auditar una compra de punta a punta.

```sql
SELECT
  p.EJERCICIO,
  p.NUM_PED,
  p.FECH_EMI          AS fecha_pedido,
  p.PED_ESTADO        AS estado_pedido,
  sg.NRO_SOLIC,
  sg.FECH_SOLIC       AS fecha_solic,
  sg.ESTADO_SOLIC,
  sg.IMPORTE_TOT      AS importe_sg,
  oc.NRO_OC,
  oc.FECH_OC          AS fecha_oc,
  oc.ESTADO_OC,
  oc.IMPORTE_TOT      AS importe_oc,
  oc.COD_PROV         AS prov_oc,
  op.NRO_OP,
  op.FECH_OP          AS fecha_pago,
  op.ESTADO_OP,
  op.IMPORTE_TOTAL    AS importe_pago,
  op.COD_PROV         AS prov_op
FROM      OWNER_RAFAM.PEDIDOS      p
JOIN      OWNER_RAFAM.SOLIC_GASTOS sg ON  sg.EJERCICIO = p.EJERCICIO
                                  AND sg.NRO_PED   = p.NUM_PED
LEFT JOIN OWNER_RAFAM.ORDEN_COMPRA oc ON  oc.EJERCICIO = sg.EJERCICIO
LEFT JOIN OWNER_RAFAM.ORDEN_PAGO   op ON  op.EJERCICIO       = sg.EJERCICIO
                                  AND op.SG_DELEG_SOLIC  = sg.DELEG_SOLIC
                                  AND op.SG_NRO_SOLIC    = sg.NRO_SOLIC
ORDER BY p.EJERCICIO DESC, p.NUM_PED, sg.NRO_SOLIC
FETCH FIRST 10 ROWS ONLY
```

### OC con todos sus items y proveedor

Detalle de lineas de cada Orden de Compra junto con razon social del proveedor.

```sql
SELECT
  oc.EJERCICIO,
  oc.UNI_COMPRA,
  oc.NRO_OC,
  oc.FECH_OC,
  oc.ESTADO_OC,
  oc.IMPORTE_TOT,
  pr.RAZON_SOCIAL,
  oi.ITEM_OC,
  oi.DESCRIPCION,
  oi.CANTIDAD,
  oi.IMP_UNITARIO
FROM OWNER_RAFAM.ORDEN_COMPRA oc
JOIN OWNER_RAFAM.PROVEEDORES  pr ON pr.COD_PROV   = oc.COD_PROV
JOIN OWNER_RAFAM.OC_ITEMS     oi ON  oi.EJERCICIO  = oc.EJERCICIO
                             AND oi.UNI_COMPRA = oc.UNI_COMPRA
                             AND oi.NRO_OC     = oc.NRO_OC
ORDER BY oc.EJERCICIO DESC, oc.NRO_OC, oi.ITEM_OC
FETCH FIRST 10 ROWS ONLY
```

### Ordenes de pago por proveedor

Resumen de pagos agrupados por proveedor y estado.

```sql
SELECT
  pr.COD_PROV,
  pr.RAZON_SOCIAL,
  op.ESTADO_OP,
  COUNT(*)                    AS cant_op,
  SUM(op.IMPORTE_TOTAL)       AS total_pagado
FROM OWNER_RAFAM.ORDEN_PAGO  op
JOIN OWNER_RAFAM.PROVEEDORES pr ON pr.COD_PROV = op.COD_PROV
GROUP BY pr.COD_PROV, pr.RAZON_SOCIAL, op.ESTADO_OP
ORDER BY total_pagado DESC
FETCH FIRST 10 ROWS ONLY
```

---

## 16. Analisis de consistencia del proveedor

> Detecta divergencias de COD_PROV entre tablas relacionadas.
> Ejecutar contra Oracle o SQLite con datos reales para obtener resultados.

### OC_ITEMS donde COD_PROV difiere de su ORDEN_COMPRA

Detecta items de OC cuyo proveedor registrado no coincide con el proveedor de la cabecera de la OC. Puede indicar datos inconsistentes.

```sql
SELECT
  oi.EJERCICIO,
  oi.UNI_COMPRA,
  oi.NRO_OC,
  oi.ITEM_OC,
  oi.COD_PROV       AS prov_item,
  oc.COD_PROV       AS prov_oc,
  oi.DESCRIPCION
FROM OWNER_RAFAM.OC_ITEMS     oi
JOIN OWNER_RAFAM.ORDEN_COMPRA oc ON  oc.EJERCICIO  = oi.EJERCICIO
                             AND oc.UNI_COMPRA = oi.UNI_COMPRA
                             AND oc.NRO_OC     = oi.NRO_OC
WHERE oi.COD_PROV != oc.COD_PROV
ORDER BY oi.EJERCICIO DESC, oi.NRO_OC
FETCH FIRST 20 ROWS ONLY
```

### ORDEN_PAGO donde COD_PROV difiere de la ORDEN_COMPRA asociada

Detecta ordenes de pago cuyo proveedor no coincide con el proveedor de la OC referenciada (RECO_DEU_COMPRA). Puede indicar reasignaciones o errores de carga.

```sql
SELECT
  op.EJERCICIO,
  op.NRO_OP,
  op.COD_PROV             AS prov_op,
  op.RECO_DEU_COMPRA      AS nro_oc_ref,
  op.RECO_DEU_COMPRA_EJER AS ejer_oc_ref,
  oc.COD_PROV             AS prov_oc,
  oc.IMPORTE_TOT          AS importe_oc,
  op.IMPORTE_TOTAL        AS importe_pago
FROM OWNER_RAFAM.ORDEN_PAGO   op
JOIN OWNER_RAFAM.ORDEN_COMPRA oc ON  oc.EJERCICIO = op.RECO_DEU_COMPRA_EJER
                             AND oc.NRO_OC    = op.RECO_DEU_COMPRA
WHERE op.COD_PROV != oc.COD_PROV
ORDER BY op.EJERCICIO DESC, op.NRO_OP
FETCH FIRST 20 ROWS ONLY
```

### Proveedores referenciados en OC pero ausentes en PROVEEDORES

Detecta COD_PROV usados en ORDEN_COMPRA que no tienen registro en la tabla maestra PROVEEDORES. Indica posibles datos huerfanos.

```sql
SELECT DISTINCT
  oc.COD_PROV,
  COUNT(*) AS cant_oc
FROM OWNER_RAFAM.ORDEN_COMPRA oc
WHERE NOT EXISTS (
  SELECT 1 FROM OWNER_RAFAM.PROVEEDORES pr WHERE pr.COD_PROV = oc.COD_PROV
)
GROUP BY oc.COD_PROV
ORDER BY cant_oc DESC
FETCH FIRST 20 ROWS ONLY
```

### Proveedores referenciados en ORDEN_PAGO pero ausentes en PROVEEDORES

Mismo analisis para ORDEN_PAGO.COD_PROV.

```sql
SELECT DISTINCT
  op.COD_PROV,
  COUNT(*) AS cant_op
FROM OWNER_RAFAM.ORDEN_PAGO op
WHERE NOT EXISTS (
  SELECT 1 FROM OWNER_RAFAM.PROVEEDORES pr WHERE pr.COD_PROV = op.COD_PROV
)
GROUP BY op.COD_PROV
ORDER BY cant_op DESC
FETCH FIRST 20 ROWS ONLY
```

---

## 17. Datos reales de muestra

> Primeras filas de cada tabla clave (hasta 8 registros).
> Util para validar el comportamiento del sistema y confirmar mappings.

### Muestra de PROVEEDORES

| cod_prov|razon_social|cuit|cod_iva|cod_estado|fecha_alta |
| ---|---|---|---|---|--- |
| 1 | CORBELLINI HUGO CESAR | 20-22630728-2 | MONOT | 0 | 2003-09-17 00:00:00 |
| 2 | VEYRA RAMON ROBERTO | 20-13810238-7 | MONOT | 0 | 2000-02-23 00:00:00 |
| 3 | RAMOS DELFOR SAUL ( NO USAR ) | 20-05318329-9 | RINS | 0 | 2000-02-17 00:00:00 |
| 4 | RUZZO CARLOS DANIEL | 30-67779639-8 | RINS | 0 | 2000-03-07 00:00:00 |
| 5 | ANDRES PONSA S.A. | 30-56811894-0 | RINS | 0 | 2000-03-17 00:00:00 |
| 6 | COMAR AUTOMOTORES S.A. | 30-67680490-7 | RINS | 0 | 2000-03-14 00:00:00 |
| 7 | ECHEGARAY JUAN P | 20-05282069-4 | RINS | 0 | 2000-03-15 00:00:00 |
| 8 | PASINI JUAN CARLOS | 20-21447175-3 | RNIS | 0 | 2000-10-17 00:00:00 |

### Muestra de PEDIDOS recientes

| ejercicio|num_ped|fech_emi|jurisdiccion|costo_tot|ped_estado |
| ---|---|---|---|---|--- |
| 2026 | 1081 | 2026-03-17 00:00:00 | 1110104000 | 134576 | N |
| 2026 | 1080 | 2026-03-17 00:00:00 | 1110104000 | 137978.1 | N |
| 2026 | 1079 | 2026-03-17 00:00:00 | 1110104000 | 527339.43 | N |
| 2026 | 1078 | 2026-03-17 00:00:00 | 1110104000 | 80000 | N |
| 2026 | 1077 | 2026-03-17 00:00:00 | 1110118000 | 98000 | N |
| 2026 | 1076 | 2026-03-17 00:00:00 | 1110113000 | 547888 | N |
| 2026 | 1075 | 2026-03-16 00:00:00 | 1110106000 | 224500 | N |
| 2026 | 1074 | 2026-03-16 00:00:00 | 1110106000 | 195500 | N |

### Muestra de ORDEN_COMPRA recientes

| ejercicio|uni_compra|nro_oc|fech_oc|cod_prov|estado_oc|importe_tot |
| ---|---|---|---|---|---|--- |
| 2026 | 1 | 1060 | 2026-03-17 00:00:00 | 3511 | N | 2847000 |
| 2026 | 1 | 1059 | 2026-03-17 00:00:00 | 1527 | N | 203000 |
| 2026 | 1 | 1058 | 2026-03-16 00:00:00 | 3430 | N | 255966.48 |
| 2026 | 1 | 1057 | 2026-03-16 00:00:00 | 2627 | N | 18800 |
| 2026 | 1 | 1056 | 2026-03-16 00:00:00 | 879 | N | 12600 |
| 2026 | 1 | 1055 | 2026-03-16 00:00:00 | 688 | N | 263000 |
| 2026 | 1 | 1054 | 2026-03-16 00:00:00 | 2595 | N | 133090 |
| 2026 | 1 | 1053 | 2026-03-16 00:00:00 | 2595 | N | 238565 |

### Muestra de ORDEN_PAGO recientes

| ejercicio|nro_op|fech_op|cod_prov|estado_op|importe_total|importe_liquido |
| ---|---|---|---|---|---|--- |
| 2026 | 1453 | 2026-03-17 00:00:00 | 3557 | N | 880000 | 880000 |
| 2026 | 1452 | 2026-03-17 00:00:00 | 50012 | N | 40898.56 | 40898.56 |
| 2026 | 1451 | 2026-03-17 00:00:00 | 50002 | N | 859024.5 | 859024.5 |
| 2026 | 1450 | 2026-03-17 00:00:00 | 50370 | N | 111818.92 | 111818.92 |
| 2026 | 1449 | 2026-03-17 00:00:00 | 50031 | N | 16000 | 16000 |
| 2026 | 1448 | 2026-03-17 00:00:00 | 2627 | N | 6500 | 6240 |
| 2026 | 1447 | 2026-03-17 00:00:00 | 2627 | N | 6000 | 5760 |
| 2026 | 1446 | 2026-03-17 00:00:00 | 2627 | N | 58800 | 56448 |

### Muestra de SOLIC_GASTOS recientes

| ejercicio|deleg_solic|nro_solic|nro_ped|fech_solic|estado_solic|importe_tot |
| ---|---|---|---|---|---|--- |
| 2026 | 1 | 1144 | 1062 | 2026-03-17 00:00:00 | N | 600000 |
| 2026 | 1 | 1143 | 947 | 2026-03-17 00:00:00 | N | 414571.08 |
| 2026 | 1 | 1142 | 949 | 2026-03-17 00:00:00 | N | 115505.6 |
| 2026 | 1 | 1141 | 950 | 2026-03-17 00:00:00 | N | 97393.86 |
| 2026 | 1 | 1140 | 952 | 2026-03-17 00:00:00 | N | 107348.86 |
| 2026 | 1 | 1139 | 1022 | 2026-03-17 00:00:00 | N | 78460.44 |
| 2026 | 1 | 1138 | 1042 | 2026-03-17 00:00:00 | N | 414000 |
| 2026 | 1 | 1137 | 1048 | 2026-03-17 00:00:00 | N | 190000 |

---
