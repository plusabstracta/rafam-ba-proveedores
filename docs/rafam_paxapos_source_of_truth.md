# RAFAM -> Paxapos: fuente de verdad

Estado: canonico  
Ultima evidencia RAFAM real: `output/rafam_context/rafam_context_20260505_135301.md`  
Origen de esa evidencia: Oracle `OWNER_RAFAM`, generado el `2026-05-05T16:53:01+00:00`  
Periodo medido: `EJERCICIO >= 2024`  
Script commit medido por el reporte: `5e68132`

Este archivo reemplaza los documentos fragmentados anteriores dentro de `docs/`.
El unico archivo adicional que se conserva es `docs/rafam_der.drawio`, porque sirve como vista grafica del modelo.

## Regla de uso

- Si un dato aparece como `verificado`, viene de la corrida Oracle real, del codigo actual del script, o del contrato Paxapos ya implementado.
- Si un dato aparece como `pendiente`, no debe usarse como verdad hasta que se mida o confirme.
- Si un documento viejo contradice este archivo, gana este archivo.
- No asumir columnas o joins por nombre. Medirlos contra Oracle o leer el codigo que realmente envia el payload.

## Alcance real

Tablas RAFAM relevantes para Paxapos:

| Tabla | Estado | Uso |
| --- | --- | --- |
| `JURISDICCIONES` | verificada | Centros de costo, rubros y clasificaciones Paxapos. |
| `PROVEEDORES` | verificada | Proveedores Paxapos. |
| `PEDIDOS` | verificada | Cabecera de pedidos internos. Actualmente no se envia directo al migrator. |
| `PED_ITEMS` | verificada | Items de pedidos. En migrator actual esta deshabilitado como envio directo. |
| `SOLIC_GASTOS` | verificada | Base actual para `gastos`; necesita mejora para facturas reales via `REG_COMP`/`CTA_COMPROB`. |
| `ORDEN_COMPRA` | verificada | Cabecera de OC. |
| `OC_ITEMS` | verificada | Items de OC y nexo OC -> SOLIC_GASTOS. |
| `ORDEN_PAGO` | verificada | Egresos/ordenes de pago. |
| `REG_COMP` | verificada | Registro/puente de comprobantes. No contiene `NRO_COMPROB`. |
| `CTA_COMPROB` | verificada | Comprobantes fiscales del proveedor. Contiene `NRO_COMPROB`. |
| `CTA_HOJA_DE_RUTA` | verificada | Vista desnormalizada de auditoria PE/SG/OC/RC/RD/CC/OP. |
| `RETENCIONES` | verificada | Retenciones de OP por `EJERCICIO + NRO_CANCE`. |
| `DEDUCCIONES` | verificada | Catalogo/detalle usado para describir retenciones. |
| `RG_COMP` | verificada ausente | No existe en el schema Oracle medido. No usar. |

## Arquitectura del proyecto

El proyecto es un sincronizador incremental programado:

```text
Oracle RAFAM OWNER_RAFAM -> script Python -> Paxapos CakePHP 2
                           |
                           -> SQLite local de checkpoints y links
```

Invariantes:

- Oracle RAFAM es solo lectura.
- El estado persistente vive en SQLite local (`LOCAL_STATE_DB_PATH`, default `state/checkpoint.db`).
- Los checkpoints no deben avanzar si un batch falla.
- `--dry-run` envia payload con `dry_run=true` y no debe avanzar checkpoints.
- Los vinculos RAFAM -> Paxapos se guardan en `EntityLinkStore` (`link_*`).
- El desarrollo offline puede usar `RAFAM_SOURCE_BACKEND=sqlite` y `state/dev_rafam.db`.

Modulos principales:

| Archivo | Responsabilidad |
| --- | --- |
| `main.py` | CLI y orquestacion. |
| `src/config.py` | Entidades, tabla origen, cursor incremental y ventana de reproceso. |
| `src/source_repository.py` | Queries SQLAlchemy contra RAFAM/SQLite. |
| `src/sync_engine.py` | Batches, checkpoints y ejecucion incremental. |
| `src/exporter.py` | CSV, noop, gateway y migrator Paxapos. |
| `src/gateway_mapper.py` | Mapeo de proveedores al gateway legacy. |
| `src/entity_link_store.py` | Links RAFAM -> Paxapos y datos extra por entidad. |

## Entidades del script

Fuente: `src/config.py` y reporte Oracle.

| Entidad script | Tabla RAFAM | Cursor | Full load | Reproceso pendiente |
| --- | --- | --- | --- | --- |
| `jurisdicciones` | `JURISDICCIONES` | ninguno | si | no |
| `proveedores` | `PROVEEDORES` | `FECHA_ULT_COMP` | no | no |
| `pedidos` | `PEDIDOS` | `FECH_EMI` | no | no |
| `ped_items` | `PED_ITEMS` | ninguno | si | no |
| `orden_compra` | `ORDEN_COMPRA` | `FECH_OC` | no | `ESTADO_OC = N`, 30 dias |
| `oc_items` | `OC_ITEMS` | ninguno | si | no |
| `solic_gastos` | `SOLIC_GASTOS` | `FECH_SOLIC` | no | `ESTADO_SOLIC = C`, 30 dias |
| `orden_pago` | `ORDEN_PAGO` | `FECH_CONFIRM` | no | `ESTADO_OP = N`, `CONFIRMADO = S`, 30 dias |

Estado real del migrator actual:

| Entidad | Envio migrator actual |
| --- | --- |
| `jurisdicciones` | Envia `centros_costo`, `rubros`, `clasificaciones`. |
| `proveedores` | Envia `proveedores`. |
| `ped_items` | Deshabilitado en `write_batch`; no se envia directo. |
| `pedidos` | No se envia directo; si llega sin items, se advierte. |
| `oc_items` | Envia `ordenes_compra`. |
| `orden_compra` | Envia `ordenes_compra` usando la misma logica que `oc_items`. |
| `solic_gastos` | Envia `gastos`, solo si el gasto esta vinculado a una OC ya enviada. |
| `orden_pago` | Envia `ordenes_pago`, solo si puede resolver al menos un gasto importado. |

## Evidencia Oracle: volumen de tablas

Fuente: reporte Oracle `2026-05-05`, periodo `EJERCICIO >= 2024` cuando aplica.

| Tabla | Existe | Filas totales | Filas periodo | Columnas |
| --- | --- | ---: | ---: | ---: |
| `JURISDICCIONES` | si | 27 | n/a | 5 |
| `PROVEEDORES` | si | 4.341 | n/a | 48 |
| `PEDIDOS` | si | 112.414 | 12.960 | 20 |
| `PED_ITEMS` | si | 377.904 | 44.029 | 16 |
| `SOLIC_GASTOS` | si | 121.772 | 13.603 | 28 |
| `ORDEN_COMPRA` | si | 114.282 | 13.222 | 23 |
| `OC_ITEMS` | si | 381.236 | 44.447 | 12 |
| `ORDEN_PAGO` | si | 260.043 | 24.324 | 41 |
| `REG_COMP` | si | 247.448 | 23.585 | 33 |
| `RG_COMP` | no | n/a | n/a | n/a |
| `CTA_COMPROB` | si | 389.450 | 27.207 | 23 |
| `CTA_HOJA_DE_RUTA` | si | 4.802 | n/a | 78 |
| `RETENCIONES` | si | 79.321 | 5.417 | 5 |
| `DEDUCCIONES` | si | 613 | 87 | 8 |

## Claves primarias y relaciones declaradas por Oracle

| Tabla | PK verificada | FKs relevantes para Paxapos |
| --- | --- | --- |
| `JURISDICCIONES` | `JURISDICCION` | ninguna directa. |
| `PROVEEDORES` | `COD_PROV` | catalogos auxiliares (`POS_IVA`, localidades, provincias, tipos). |
| `PEDIDOS` | `EJERCICIO, NUM_PED` | `JURISDICCION -> JURISDICCIONES`, `CODIGO_DEP`, `CODIGO_UE`, `CODIGO_FF`. |
| `PED_ITEMS` | `EJERCICIO, NUM_PED, ORDEN` | `EJERCICIO, NUM_PED -> PEDIDOS`; `UNI_MED -> CAT_UNI_MED`. |
| `SOLIC_GASTOS` | `EJERCICIO, DELEG_SOLIC, NRO_SOLIC` | `EJERCICIO, NRO_PED -> PEDIDOS`; `JURISDICCION -> JURISDICCIONES`; `TIPO_DOC -> TIPO_DOC_RES`. |
| `ORDEN_COMPRA` | `EJERCICIO, UNI_COMPRA, NRO_OC` | `UNI_COMPRA -> UNI_COMPRA`; no FK declarada a `PROVEEDORES`, aunque `COD_PROV` existe y el script lo usa. |
| `OC_ITEMS` | `EJERCICIO, UNI_COMPRA, NRO_OC, ITEM_OC` | `EJERCICIO, UNI_COMPRA, NRO_OC -> ORDEN_COMPRA`. No FK declarada a `SOLIC_GASTOS`, pero el join medido funciona. |
| `ORDEN_PAGO` | `EJERCICIO, NRO_OP` | `COD_PROV -> PROVEEDORES`; `JURISDICCION -> JURISDICCIONES`; `TIPO_DOC -> TIPO_DOC_RES`. |
| `REG_COMP` | `EJERCICIO, NRO_REG_COMP` | `COD_PROV -> PROVEEDORES`; `JURISDICCION -> JURISDICCIONES`; `TIPO_DOC -> TIPO_DOC_RES`. |
| `CTA_COMPROB` | `EJERCICIO, TIPO, NRO_COMPROB, COD_PROV` | `EJERCICIO, NRO_REG_COMP -> REG_COMP`; `COD_PROV` y `COD_PROV_REAL -> PROVEEDORES`; `TIPO -> TIPOS_COMPROB`. |
| `CTA_HOJA_DE_RUTA` | sin PK | vista sin FKs declaradas. |
| `RETENCIONES` | `EJERCICIO, NRO_CANCE, COD_RET, CUENTA` | `EJERCICIO, NRO_CANCE -> EGRESOS`; `EJERCICIO, COD_RET -> DEDUCCIONES`. |
| `DEDUCCIONES` | sin PK declarada | sin FKs declaradas. |

## Flujo RAFAM verificado para compras

Flujo funcional:

```text
JURISDICCIONES
    -> PEDIDOS -> PED_ITEMS
    -> SOLIC_GASTOS
    -> OC_ITEMS -> ORDEN_COMPRA
    -> REG_COMP -> CTA_COMPROB
    -> ORDEN_PAGO
```

Joins medidos en Oracle para `EJERCICIO >= 2024`:

| Join candidato | Cobertura | Sin match | Multi-match | Fuente de verdad |
| --- | ---: | ---: | ---: | --- |
| `PEDIDOS(EJERCICIO, NUM_PED) -> PED_ITEMS(EJERCICIO, NUM_PED)` | 99,99% | 0,01% | 45,52% | Oracle medido. |
| `PEDIDOS(EJERCICIO, NUM_PED) -> SOLIC_GASTOS(EJERCICIO, NRO_PED)` | 98,92% | 1,08% | 3,25% | Oracle medido. |
| `SOLIC_GASTOS(EJERCICIO, DELEG_SOLIC, NRO_SOLIC) -> OC_ITEMS(EJERCICIO, DELEG_SOLIC, NRO_SOLIC)` | 95,32% | 4,68% | 44,00% | Oracle medido. |
| `OC_ITEMS(EJERCICIO, UNI_COMPRA, NRO_OC) -> ORDEN_COMPRA(EJERCICIO, UNI_COMPRA, NRO_OC)` | 100,00% | 0,00% | 0,00% | Oracle medido. |
| `REG_COMP(EJERCICIO, NRO_REG_COMP) -> CTA_COMPROB(EJERCICIO, NRO_REG_COMP)` | 81,65% | 18,35% | 8,35% | Oracle medido. |
| `REG_COMP(EJERCICIO, UNI_COMPRA, NRO_OC) -> ORDEN_COMPRA(EJERCICIO, UNI_COMPRA, NRO_OC)` | 59,39% | 40,61% | 0,00% | Oracle medido. |
| `ORDEN_PAGO(EJERCICIO, NRO_CANCE) -> SOLIC_GASTOS(EJERCICIO, NRO_SOLIC)` | 92,71% | 7,29% | 0,46% | Oracle medido. |
| `ORDEN_PAGO.RECO_DEU_COMPRA -> ORDEN_COMPRA.NRO_OC` | 0,00% | 100,00% | 0,00% | Oracle medido; `RECO_DEU_COMPRA` vino 100% vacio en periodo. |

Conclusion operativa:

- Para OC -> gasto, el camino real fuerte es `OC_ITEMS -> SOLIC_GASTOS`.
- Para OP -> gasto, el camino real medido en esta corrida es `ORDEN_PAGO.NRO_CANCE -> SOLIC_GASTOS.NRO_SOLIC` con mismo `EJERCICIO`.
- No usar `RECO_DEU_COMPRA` como verdad para este RAFAM sin nueva medicion: en `EJERCICIO >= 2024` vino 100% vacio.
- `CTA_HOJA_DE_RUTA` existe y tiene columnas prefijadas, pero el generador marco las estrategias actuales como `skipped` por falta de columnas esperadas. Hay que ajustar el join si se quiere usarla como fuente operativa.

## REG_COMP, RG_COMP y comprobantes

Hechos verificados:

- `RG_COMP` no existe en el schema Oracle medido.
- `REG_COMP` existe, tiene PK `EJERCICIO, NRO_REG_COMP`, y no tiene columna `NRO_COMPROB`.
- `REG_COMP` tiene `NRO_REG_COMP`, `UNI_COMPRA`, `NRO_OC`, `DELEG_SOLIC`, `NRO_SOLIC`, `TIPO_DOC`, `NRO_DOC`, `COD_PROV`, `IMPORTE_TOT`.
- `CTA_COMPROB` existe, tiene PK `EJERCICIO, TIPO, NRO_COMPROB, COD_PROV`, y si tiene `NRO_COMPROB`.
- `CTA_COMPROB` tiene FK declarada a `REG_COMP` por `EJERCICIO, NRO_REG_COMP`.
- En el periodo medido, `CTA_COMPROB.NRO_COMPROB` tiene 0% faltantes.
- En el periodo medido, `REG_COMP.TIPO_DOC` y `REG_COMP.NRO_DOC` tienen 94,17% faltantes.

Conclusion:

```text
REG_COMP no es la tabla de numero fiscal de factura.
REG_COMP es registro/puente administrativo del comprobante.
CTA_COMPROB es la tabla de comprobantes fiscales del proveedor.
El numero fiscal debe salir de CTA_COMPROB.NRO_COMPROB.
```

Implicacion para el script:

- La implementacion actual de `solic_gastos -> gastos` usa `SOLIC_GASTOS.NRO_DOC` como `factura_nro` si viene cargado.
- Con la evidencia Oracle actual, eso no debe considerarse fuente final de factura.
- Para cerrar correctamente `Gasto.factura_nro`, hay que extender la query/mapeo para resolver `SOLIC_GASTOS/OC_ITEMS/ORDEN_COMPRA -> REG_COMP -> CTA_COMPROB` y usar `CTA_COMPROB.NRO_COMPROB`.
- Hay que definir que hacer con el 18,35% de `REG_COMP` sin `CTA_COMPROB` y con el 8,35% de `REG_COMP` con multiples comprobantes.

## CTA_HOJA_DE_RUTA

Hechos verificados:

- `CTA_HOJA_DE_RUTA` existe como vista/tabla consultable con 78 columnas.
- No tiene PK ni FKs declaradas.
- Expone datos prefijados: `PE_`, `SG_`, `OC_`, `RC_`, `RD_`, `CC_`, `OP_`.
- Columnas relevantes vistas en Oracle: `SG_EJERCICIO`, `SG_DELEG_SOLIC`, `SG_NRO`, `OC_EJERCICIO`, `OC_UNI_COMPRA`, `OC_NRO`, `RC_EJERCICIO`, `RC_NRO`, `CC_TIPO_COMPROB`, `CC_NRO`, `CC_NRO_REG_COMP`, `OP_EJERCICIO`, `OP_NRO`, `OP_NRO_CANCE`.

Estado operativo:

- Sirve para auditoria y para explicar el circuito completo.
- No debe ser unica fuente para factura si se puede usar `REG_COMP -> CTA_COMPROB` directo.
- Para OP, el join operativo debe usar los nombres reales `OP_EJERCICIO + OP_NRO`; no usar nombres viejos/inventados como `OP_NRO_OP`, `SG_DELEG` u `OC_NRO_OC`.
- La SQLite dev se carga desde los CSV de `output/rafam_ultimos_3_meses`. El CSV real `cta_hoja_de_ruta_*.csv` trae columnas reales (`SG_DELEG_SOLIC`, `OC_NRO`, `OP_NRO`). El loader local debe preservar esa tabla CSV; solo puede crear una vista derivada si el CSV no existe.

## Dominios verificados

Estados y codigos en `EJERCICIO >= 2024`:

| Campo | Valores medidos |
| --- | --- |
| `ORDEN_COMPRA.ESTADO_OC` | `R=12715`, `A=479`, `N=28` |
| `ORDEN_COMPRA.CONFIRMADO` | `S=13214`, `N=8` |
| `SOLIC_GASTOS.ESTADO_SOLIC` | `C=12676`, `N=517`, `A=410` |
| `SOLIC_GASTOS.CONFIRMADO` | `S=13603` |
| `ORDEN_PAGO.ESTADO_OP` | `C=23220`, `A=857`, `N=247` |
| `ORDEN_PAGO.CONFIRMADO` | `S=24169`, `N=155` |
| `REG_COMP.TIPO_REGIS` | `R=22505`, `A=613`, `D=462`, `C=5` |
| `REG_COMP.ESTADO_REG_COMP` | `D=21728`, `N=1219`, `A=638` |
| `CTA_COMPROB.TIPO` | principales: `FAB=13239`, `LIQ=4981`, `FAC=4355`, `COM=2249`, `TKT=1826` |
| `RETENCIONES.COD_RET` | principales: `3=2294`, `6=2181`, `4=243`, `2=103`, `1=103`, `784=93` |
| `PROVEEDORES.COD_IVA` | `MONOT=1751`, `RINS=1696`, `EXEN=830`, `M.SOC=50`, `RNIS=10`, `NGAN=3`, `CF=1` |
| `PROVEEDORES.COD_ESTADO` | `0=4313`, `2=27`, `1=1` |

Significado funcional confirmado hasta ahora:

| Tabla | Campo | Valores | Significado conocido |
| --- | --- | --- | --- |
| `PEDIDOS` | `PED_ESTADO` | `G`, `N` | `N=normal`; `G` pendiente de confirmar. |
| `ORDEN_COMPRA` | `ESTADO_OC` | `R`, `A`, `N` | `R=registrado`, `A=anulado`, `N=normal`. |
| `SOLIC_GASTOS` | `ESTADO_SOLIC` | `C`, `N`, `A` | `C=cancelado`, `N=normal`, `A=anulado`. |
| `SOLIC_GASTOS` | `TIPO_REGIS` | `S`, `A`, `M` | `A=anulado`; `S` y `M` pendientes de confirmar. |
| `REG_COMP` | `ESTADO_REG_COMP` | `D`, `N`, `A` | `D=devengado`, `N=normal`, `A=anulado`. |
| `REG_COMP` | `TIPO_REGIS` | `R`, `A`, `D`, `C` | `R=registrado`, `A=anulado`, `D=devengado`, `C=cancelado`. |
| `DEDUCCIONES` | `TIPO_DEDUC` | `I`, `O` | `I` y `O` pendientes de confirmar. |
| `ORDEN_PAGO` | `ESTADO_OP` | `C`, `A`, `N` | `C=cancelado`, `A=anulado`, `N=normal`. Solo `N` confirmado (`CONFIRMADO=S` y `FECH_CONFIRM`) se envia a Paxapos. |
| `ORDEN_PAGO` | `TIPO_OP` | `N`, `P` | `N=normal`, `P=pagado`. |

Pendientes de confirmar en campos de estado/tipo: `S`, `G`, `I`, `O` y `M`. No aplicar esa regla a campos `CONFIRMADO`, donde `S` significa confirmado.

Para el script actual, las reglas implementadas son:

- `ORDEN_COMPRA`: se envia a Paxapos cuando `ESTADO_OC = R`; si pasa a `A` y ya tenia link remoto, se anula como `estado_aprobacion=4`.
- `SOLIC_GASTOS`: se omite si `ESTADO_SOLIC = A`.
- `ORDEN_PAGO`: se envia solo si `ESTADO_OP = N`, `CONFIRMADO = S` y `FECH_CONFIRM` existe. Se crea en Paxapos con `fecha=FECH_CONFIRM` y `estado=3`. `A`, `C`, no confirmadas o sin fecha de confirmacion se omiten.

## Calidad de datos verificada

Completitud de campos criticos en `EJERCICIO >= 2024`:

| Tabla.campo | Faltantes |
| --- | ---: |
| `PROVEEDORES.FECHA_ULT_COMP` | 24,21% |
| `ORDEN_PAGO.NRO_CANCE` | 4,54% |
| `ORDEN_PAGO.RECO_DEU_COMPRA` | 100,00% |
| `ORDEN_PAGO.RECO_DEU_COMPRA_EJER` | 100,00% |
| `REG_COMP.UNI_COMPRA` | 40,61% |
| `REG_COMP.NRO_OC` | 40,61% |
| `REG_COMP.DELEG_SOLIC` | 40,61% |
| `REG_COMP.NRO_SOLIC` | 40,61% |
| `REG_COMP.TIPO_DOC` | 94,17% |
| `REG_COMP.NRO_DOC` | 94,17% |
| `CTA_COMPROB.COD_PROV_REAL` | 100,00% |
| `CTA_COMPROB.FECH_VENCIM` | 18,31% |

Riesgos numericos:

| Tabla.campo | Min | Max | Negativos | Overflow DECIMAL(10,2) |
| --- | ---: | ---: | ---: | ---: |
| `SOLIC_GASTOS.IMPORTE_TOT` | -135.800.000 | 13.681.426.737 | 411 | 14 |
| `ORDEN_COMPRA.IMPORTE_TOT` | 26,50 | 578.621.401,30 | 0 | 6 |
| `ORDEN_PAGO.IMPORTE_TOTAL` | 0,01 | 701.653.187,90 | 0 | 77 |
| `ORDEN_PAGO.IMPORTE_LIQUIDO` | 0,01 | 561.467.956,69 | 0 | 67 |
| `REG_COMP.IMPORTE_TOT` | -274.415.555,39 | 701.653.187,90 | 1075 | 62 |
| `CTA_COMPROB.IMPORTE_COMPR` | 0,01 | 701.653.187,90 | 0 | 58 |

Implicacion: Paxapos/CakePHP con campos `DECIMAL(10,2)` puede fallar con importes mayores a `99.999.999,99`. Todo mapeo de importes debe validar o capear/omitir segun decision de negocio antes de enviar.

## Contrato Paxapos implementado

Endpoint migrator:

```text
POST {PAXAPOS_URL}/{PAXAPOS_TENANT}/{PAXAPOS_RAFAM_IMPORT_PATH}
default path: rafam/migracion/importar.json
```

Headers:

```text
Content-Type: application/json
Accept: application/json
X-Tenant-Id: {PAXAPOS_TENANT}
X-Api-Key: {PAXAPOS_API_KEY}
```

Opciones enviadas por el script:

```json
{
  "upsert": true,
  "atomic": false,
  "fail_fast": false,
  "send_oc_mail": false,
  "strict_mail": false,
  "auto_create_mercaderia": true,
  "auto_calcular_retenciones": false,
  "notificar_proveedor_pago": false
}
```

Colecciones raiz usadas:

- `centros_costo`
- `rubros`
- `clasificaciones`
- `proveedores`
- `pedidos` (codigo existe, envio directo deshabilitado actualmente)
- `ordenes_compra`
- `gastos`
- `ordenes_pago`

Orden interno Paxapos conocido por contrato: `rubros -> clasificaciones -> proveedores -> pedidos -> ordenes_compra -> gastos -> ordenes_pago`.

## Mapeo actual: RAFAM -> Paxapos

### Jurisdicciones

Fuente: `JURISDICCIONES`.

Por cada jurisdiccion se envia:

- `CentroCosto.name = DENOMINACION` con fallback a `JURISDICCION`.
- `CentroCosto.description = "Jurisdiccion RAFAM {JURISDICCION}"`.
- `Rubro.name = DENOMINACION`.
- `Clasificacion.name = DENOMINACION`.
- `external_id = {"jurisdiccion": "..."}`.

Los links se guardan para resolver `centro_costo_id`, `rubro_id` y `clasificacion_id`.

### Proveedores

Fuente: `PROVEEDORES`.

Campos enviados por `map_proveedor_migrator_row`:

| Paxapos | Fuente RAFAM | Regla |
| --- | --- | --- |
| `external_id.cod_prov` | `COD_PROV` | int obligatorio. |
| `Proveedor.name` | `FANTASIA`, fallback `RAZON_SOCIAL` | max 100. |
| `Proveedor.razon_social` | `RAZON_SOCIAL` | trim. |
| `Proveedor.mail` | `EMAIL` | trim. |
| `Proveedor.telefono` | telefonos 1/2/3 o `TE_CELULAR` | primer no vacio. |
| `Proveedor.domicilio` | legal o postal | calle + numero. |
| `Proveedor.localidad` | `LOCA_LEGAL`, fallback `LOCA_POSTAL` | primer no vacio. |
| `Proveedor.provincia` | `PROV_LEGAL`, fallback `PROV_POSTAL` | primer no vacio. |
| `Proveedor.codigo_postal` | `COD_LEGAL`, fallback `COD_POSTAL` | primer no vacio. |
| `Proveedor.cuit` | `CUIT` | solo si normaliza a 11 digitos. |
| `Proveedor.tipo_documento_id` | `CUIT` | `1` si hay CUIT valido. |
| `Proveedor.iva_condicion_id` | `COD_IVA` | `RINS=1`, `MONOT=2`, `EXEN=3`, `CF=4`, `NGAN=5`, `RNI/RNIS=6`. |

### Pedidos y ped_items

Estado actual:

- El codigo tiene mapeo para `ped_items -> pedidos` con `tipo="solicitud"`.
- Pero `MigratorExporter.write_batch("ped_items")` lo deshabilita y solo loguea warning.
- Por lo tanto, no tratar `ped_items` como envio migrator activo hasta cambiar el codigo.

### Ordenes de compra

Fuentes: `ORDEN_COMPRA`, `OC_ITEMS`, `SOLIC_GASTOS`.

La query real trae filas a nivel item y agrega datos de cabecera OC y jurisdiccion de SG.

Cabecera enviada:

| Paxapos | Fuente RAFAM | Regla |
| --- | --- | --- |
| `external_id` | `EJERCICIO, UNI_COMPRA, NRO_OC` | objeto estructurado. |
| `Pedido.internal_id` | `EJERCICIO, UNI_COMPRA, NRO_OC` | `rafam-oc-{ej}-{uni}-{nro}`. |
| `Pedido.tipo` | fijo | `orden_compra`. |
| `Pedido.estado_aprobacion` | regla interna | `2` al crear; `4` al anular. |
| `Pedido.proveedor_id` | `COD_PROV` | resuelto por `link_proveedores`; si falta, la OC se omite. |
| `Pedido.observacion` | observaciones OC | solo si existe texto real. |
| `Pedido.created` | `OC_FECH_OC` | `YYYY-MM-DD 00:00:00` si existe. |
| `centro_costo_id` | `SG_JURISDICCION` | resuelto desde links/lookups de jurisdiccion. |
| `gasto_external_ids` | `OC_ITEMS.DELEG_SOLIC, NRO_SOLIC` | refs SG estructuradas. |
| `gasto_ids` | link local de gastos | si ya fueron importados. |

Item enviado:

| Paxapos | Fuente RAFAM | Regla |
| --- | --- | --- |
| `mercaderia_external_ref` | `EJERCICIO, UNI_COMPRA, NRO_OC, ITEM_OC` y rubros RAFAM si existen | referencia deterministica. |
| `cantidad` | `OC_ITEMS.CANTIDAD` | float obligatorio. |
| `precio` | `OC_ITEMS.IMP_UNITARIO` | redondeado a 2 decimales. |
| `recibida_cantidad` | `OC_ITEMS.CANT_RECIB` | si existe. |
| `name` | `OC_ITEMS.DESCRIPCION` | max 255; alimenta autocreacion de mercaderia. |
| `unidad_de_medida_id` | decision tenant Paxapos | fijo `5`, porque en Paxapos la unidad requerida para todos los items OC es `Unidad`. |
| `rubro_id` | `SG_JURISDICCION` | resuelto por link de rubro. |

Estados OC:

- `R`: se crea/envia si no habia link previo o si hay gastos nuevos para vincular.
- `A`: si ya estaba enviada como `R`, se envia con `estado_aprobacion=4` y `motivo_rechazo="Anulada en RAFAM"`.
- `N` u otros: se registran localmente, no se envian como OC nueva.

### Gastos

Fuente actual del script: `SOLIC_GASTOS` enriquecida con proveedor desde `OC_ITEMS -> ORDEN_COMPRA`.

Campos actuales:

| Paxapos | Fuente RAFAM | Regla actual |
| --- | --- | --- |
| `external_id` | `EJERCICIO, DELEG_SOLIC, NRO_SOLIC` | objeto estructurado. |
| `Gasto.fecha` | `FECH_SOLIC` | obligatorio. |
| `Gasto.importe_total` | `IMPORTE_TOT` | round 2. |
| `Gasto.importe_neto` | `IMPORTE_TOT` | igual al total. |
| `Gasto.punto_de_venta` | fijo | `RAFAM`. |
| `Gasto.tipo_factura_id` | `CTA_COMPROB.TIPO`, fallback `TIPO_DOC` | lookup/default. |
| `Gasto.factura_nro` | `CTA_COMPROB.NRO_COMPROB` | obligatorio para enviar gasto; no usar `SOLIC_GASTOS.NRO_DOC` como fuente fiscal. |
| `Gasto.clasificacion_id` | `JURISDICCION` | link clasificacion. |
| `Gasto.fecha_vencimiento` | `CTA_COMPROB.FECH_VENCIM`, fallback `FECH_NECESIDAD`, fallback `FECH_ENTREGA` | si existe. |
| `Gasto.proveedor_id` | `OC_COD_PROV` | link proveedor. |
| `Gasto.observacion` | `OBSERVACIONES` | max 255. |

Reglas actuales:

- `ESTADO_SOLIC = A` se omite.
- Solo se envian gastos cuya ref `SG-{ejercicio}-{deleg_solic}-{nro_solic}` ya este vinculada a una OC enviada.
- Solo se envian gastos con un unico comprobante fiscal resuelto por `REG_COMP -> CTA_COMPROB`. Si no hay comprobante o hay multiples comprobantes para la misma SG, se omiten hasta definir politica de negocio.

Correccion aplicada por evidencia Oracle:

- `factura_nro` ya no sale de `SOLIC_GASTOS.NRO_DOC`.
- La fuente real de numero fiscal es `CTA_COMPROB.NRO_COMPROB`.
- Queda pendiente resolver multiples comprobantes por `REG_COMP` y los casos sin `CTA_COMPROB`.

### Ordenes de pago

Fuente: `ORDEN_PAGO`, con joins a `SOLIC_GASTOS`, `CTA_HOJA_DE_RUTA`, `RETENCIONES`, `DEDUCCIONES` cuando existan.

Campos enviados:

| Paxapos | Fuente RAFAM | Regla |
| --- | --- | --- |
| `external_id` | `EJERCICIO, NRO_OP` | objeto estructurado. |
| `Egreso.identificador_pago` | `EJERCICIO, NRO_OP` | `RAFAM-OP-{ejercicio}-{nro_op}`. |
| `Egreso.total` | `IMPORTE_TOTAL` | round 2; fallback 0 si invalido. |
| `Egreso.tipo_de_pago_id` | env/default | `PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID`, default `1`. |
| `Egreso.estado` | `ESTADO_OP`, `CONFIRMADO` | `3` solo si `ESTADO_OP = N`, `CONFIRMADO = S` y `FECH_CONFIRM` existe; `A` y `C` se omiten. |
| `Egreso.fecha` | `FECH_CONFIRM` | obligatoria para enviar la OP; Paxapos la usa como fecha del egreso y confirma `estado=3`. |
| `Egreso.observacion` | `CONCEPTO`, fallback `OBSERVACIONES` | max 255. |
| `gasto_ids` | links locales de gastos | obligatorio para enviar la OP. |
| `gasto_external_ids` | refs SG | fallback para migrator. |
| `retenciones` | `RETENCIONES` + `DEDUCCIONES` | si hay `RET_COD_RET` e importe no cero. |

Resolucion actual de gastos para OP:

1. `ORDEN_PAGO.NRO_CANCE -> SOLIC_GASTOS.NRO_SOLIC` en mismo `EJERCICIO`, con `SG_DELEG_SOLIC`/`SG_NRO_SOLIC` tomados del join.
2. `CTA_HOJA_DE_RUTA`, si la query devuelve `HDR_SG_*`.
3. Fallback por `RECO_DEU_COMPRA -> link_orden_compra.gasto_refs`.

Evidencia real del periodo:

- Camino 1 cubre 92,71% de OPs.
- Camino 3 no aporto nada en el reporte Oracle porque `RECO_DEU_COMPRA` esta 100% vacio en `EJERCICIO >= 2024`.
- Cualquier doc que diga que `RECO_DEU_COMPRA` cubre la mayoria no aplica a esta evidencia.

Retenciones:

- `external_id = {ejercicio, nro_op, cod_ret}`.
- `monto_retenido = RETENCIONES.IMPORTE`.
- `numero_certificado = RAFAM-RET-{ejercicio}-{nro_op}-{cod_ret}`.
- `tipo_impuesto_id` se resuelve por `link_tipo_retencion` o lookups; si no, se usa alias/nombre cuando sea posible.

## EntityLinkStore

SQLite local con tablas `link_*`.

| Link | Extras | Uso |
| --- | --- | --- |
| `link_proveedores` | `cuit`, `cod_estado` | Resolver proveedor RAFAM -> Paxapos. |
| `link_centro_costo` | ninguno | Resolver centro de costo por jurisdiccion. |
| `link_clasificacion` | ninguno | Resolver clasificacion de gastos. |
| `link_rubro` | ninguno | Resolver rubro de items. |
| `link_unidad_medida` | `name`, `codigo` | Overrides de unidades. |
| `link_tipo_factura` | `name`, `codigo` | Overrides de tipos factura. |
| `link_tipo_pago` | `name`, `codigo` | Overrides de tipos de pago. |
| `link_tipo_retencion` | `name`, `codigo` | Overrides de tipos de retencion. |
| `link_pedido` | ninguno | Pedidos si se reactiva envio. |
| `link_orden_compra` | `fech_confirm`, `estado_oc`, `cod_prov`, `importe_tot`, `gasto_refs`, `gasto_linked_refs` | Estado OC, refs SG conocidas y refs SG ya enviadas como `gasto_ids` para no reenviar la misma OC indefinidamente. |
| `link_gasto` | `estado_solic`, `importe_tot`, `cod_prov` | Resolver OP -> gastos. |
| `link_orden_pago` | `estado_op`, `confirmado`, `fech_confirm`, `importe_total` | Control de OPs enviadas. |

## Variables de entorno canonicas

| Grupo | Variables |
| --- | --- |
| App | `APP_ENV`, `LOG_LEVEL` |
| Source RAFAM | `RAFAM_SOURCE_BACKEND`, `RAFAM_SOURCE_HOST`, `RAFAM_SOURCE_PORT`, `RAFAM_SOURCE_SERVICE`, `RAFAM_SOURCE_USER`, `RAFAM_SOURCE_PASSWORD`, `RAFAM_SOURCE_SQLITE_DB_PATH`, `ORACLE_CLIENT_DIR` |
| Local | `LOCAL_STATE_DB_PATH` |
| Paxapos | `PAXAPOS_URL`, `PAXAPOS_TENANT`, `PAXAPOS_VERIFY_SSL`, `PAXAPOS_TIMEOUT_SECONDS`, `PAXAPOS_JWT`, `PAXAPOS_API_KEY` |
| Migrator RAFAM | `PAXAPOS_RAFAM_IMPORT_PATH`, `PAXAPOS_RAFAM_SPEC_PATH`, `PAXAPOS_RAFAM_LOOKUPS_PATH`, `PAXAPOS_RAFAM_DEFAULT_UNIDAD_ID`, `PAXAPOS_RAFAM_DEFAULT_TIPO_FACTURA_ID`, `PAXAPOS_RAFAM_DEFAULT_TIPO_PAGO_ID`, `RAFAM_SYNC_BATCH_DELAY_SECONDS` |

No usar nombres legacy `DB_*`, `SQLITE_DB_PATH`, `CHECKPOINT_DB_PATH`, `ENTITY_LINK_DB_PATH`, `GATEWAY_*`, `MIGRATOR_*`, `LOCAL_CHECKPOINT_DB_PATH`, `LOCAL_ENTITY_LINK_DB_PATH`.

## Comandos operativos

Setup:

```bash
make setup
```

Generar contexto RAFAM real:

```bash
make rafam-context RAFAM_CONTEXT_ARGS="--years 3 --sample-limit 20"
```

Si Oracle se pone lento en completitud:

```bash
make rafam-context RAFAM_CONTEXT_ARGS="--years 3 --sample-limit 20 --skip-completeness"
```

Export CSV RAFAM-only:

```bash
make export-rafam-csv
```

Cargar snapshot a SQLite dev:

```bash
make load-dev
```

Consultar Paxapos migrator:

```bash
make migrator-spec
make migrator-lookups
```

Ejecutar importacion dry-run:

```bash
make run-proveedores-migrator-dry LIMIT=20 BATCH=20
make run-oc_items-migrator-dry LIMIT=50 BATCH=50
make run-solic_gastos-migrator-dry LIMIT=50 BATCH=50
make run-orden_pago-migrator-dry LIMIT=50 BATCH=50
```

## Decisiones ya cerradas

| Decision | Estado | Motivo |
| --- | --- | --- |
| Mantener `rafam_der.drawio` | cerrado | Aporta lectura grafica de tablas. |
| Borrar docs fragmentados anteriores | cerrado | Mezclaban evidencias viejas, supuestos y campos pendientes. |
| `RG_COMP` | cerrado | No existe en Oracle medido. |
| `REG_COMP` | cerrado | Es registro/puente; no fuente de `NRO_COMPROB`. |
| `CTA_COMPROB` | cerrado | Es fuente real de `NRO_COMPROB`. |
| `RECO_DEU_COMPRA` | cerrado para periodo 2024+ | 100% faltante en reporte Oracle; no usar como camino principal. |

## Pendientes reales para terminar el proyecto

Estos puntos requieren nueva consulta, decision del usuario o cambio de codigo. No son supuestos.

1. Validar en Oracle/Paxapos la lectura implementada de comprobantes reales: `REG_COMP -> CTA_COMPROB`.
2. Definir como representar en Paxapos los `REG_COMP` con multiples `CTA_COMPROB`.
3. Definir que hacer con `REG_COMP` sin `CTA_COMPROB` (18,35% en periodo 2024+).
4. Medir una estrategia correcta para `CTA_HOJA_DE_RUTA` con los nombres reales de columnas (`OP_NRO`, `SG_DELEG_SOLIC`, etc.).
5. Confirmar si se deben importar pedidos internos (`PEDIDOS`/`PED_ITEMS`) o si Paxapos solo necesita OC/gastos/OP.
6. Confirmar IDs default del tenant Paxapos con `make migrator-lookups` antes de una importacion real.
7. Definir politica de importes con overflow `DECIMAL(10,2)` y negativos.
8. Confirmar significado funcional de `REG_COMP.ESTADO_REG_COMP` (`D`, `N`, `A`) antes de usarlo para filtros de envio.
9. Definir politica de checkpoints para registros omitidos por dependencias faltantes: hoy no deben considerarse enviados aunque el batch fuente haya sido procesado.

## Documentos eliminados

Se eliminaron porque ahora su contenido valido queda consolidado aca, y el resto era redundante, incompleto o mezclaba supuestos con datos:

- `docs/Docu_RAFAM.md`
- `docs/factura_comprobante_proveedor.md`
- `docs/field_mapping.md`
- `docs/flow_rafam.md`
- `docs/incremental_strategy.md`
- `docs/RAFAM_DOCU_4-5.md`
- `docs/tablas_datos_paxapos.md`

## Mapeos de Catálogos RAFAM → Paxapos

### Tipo de Comprobante (CTA_COMPROB.TIPO → tipo_facturas.name)

Definido en `src/gateway_mapper.py :: RAFAM_TIPO_COMPROB_TO_PAXAPOS_NAME`.

| RAFAM TIPO | Paxapos nombre | Notas |
|------------|---------------|-------|
| FAA | A | Factura A |
| FAS | A | Factura A (servicio) |
| FAB | B | Factura B |
| FAC | C | Factura C |
| FAM | M | Factura M |
| TKT | Otros | Ticket |
| NCB | NCB | Nota de Crédito B |
| NDB | NDB | Nota de Débito B |
| NDC | NDC | Nota de Débito C |
| EXB | B | Exenta B |
| REB | B | Recibo B |
| REA | A | Recibo A |
| LIQ, COM, VIA, REC, CEO, LIR | Otros | Liquidaciones, comisiones, viáticos, etc. |

Resolución dinámica: se busca por `codename` primero, luego por `name` normalizado en el lookup de `tipos_factura`.

### Tipo de Pago (ORDEN_PAGO.TIPO_CANCE → tipo_de_pagos.name)

Definido en `src/gateway_mapper.py :: RAFAM_TIPO_CANCE_TO_PAXAPOS_PAGO_NAME`.

| RAFAM TIPO_CANCE | Paxapos nombre | Significado |
|------------------|---------------|-------------|
| CA | Cheque | Cheque al día |
| CM | Cheque | Cheque múltiple |
| NO | Transferencia bancaria | Normal (transferencia) |
| (otros/vacío) | Transferencia bancaria | Fallback |

Resolución dinámica: se busca por `name` normalizado en el lookup de `tipos_de_pago`.

### Unidades de Medida (PED_ITEMS.UNI_MED → compras_unidad_de_medidas)

Estado: **pendiente de extracción**. Ejecutar `make extract-cat-uni-med` para generar `docs/cat_uni_med.md` con el catálogo RAFAM `CAT_UNI_MED`. Actualmente fallback a id=5 (Unidad).
