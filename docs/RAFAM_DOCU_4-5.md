**RAFAM**

**Sistema de Gestión Financiera y Administrativa Municipal**

Documentación Técnica Completa — Módulo de Compras

Este documento consolida toda la información disponible sobre el esquema de base de datos OWNER\_RAFAM, el flujo funcional del módulo de compras, el modelo de datos (DER), las reglas de negocio críticas y el mapeo de campos hacia sistemas externos.

| Aspecto                            | Detalle                                               |
| :--------------------------------- | :---------------------------------------------------- |
| **Base de datos**                  | Oracle — Schema OWNER\_RAFAM                          |
| **Módulo documentado**             | Compras y Pagos                                       |
| **Tablas clave del flujo**         | PEDIDOS · SOLIC\_GASTOS · ORDEN\_COMPRA · ORDEN\_PAGO |
| **Tablas maestras**                | PROVEEDORES · JURISDICCIONES                          |
| **Sistema destino de integración** | Paxapos                                               |
| **Fecha del documento**            | 2 de mayo de 2026                                     |

# 1\. Introducción y contexto

RAFAM (Sistema de Gestión Financiera y Administrativa Municipal) es el sistema de información presupuestaria, contable y de compras utilizado por municipios y organismos públicos. Opera sobre una base de datos Oracle bajo el schema propietario OWNER\_RAFAM, que concentra la totalidad de la información transaccional y de referencia del organismo.

El módulo de compras es el núcleo de la actividad económica del sistema. Registra cada etapa desde que surge una necesidad interna hasta que se acredita el pago al proveedor, dejando trazabilidad completa en cada paso del proceso.

## 1.1 Alcance de este documento

Este documento cubre:

  * Descripción funcional del flujo de compras (las cuatro etapas)
  * Tablas maestras de referencia (PROVEEDORES y JURISDICCIONES)
  * Esquema técnico detallado de cada tabla del flujo principal
  * Diagrama Entidad-Relación (DER) del módulo de compras
  * Relaciones entre tablas y reglas de trazabilidad
  * Análisis crítico del campo proveedor en cada etapa
  * Tablas complementarias del ecosistema (retenciones, deducciones, hoja de ruta)
  * Mapeo de campos RAFAM → Paxapos para las entidades del flujo
  * Consultas SQL de diagnóstico y validación
  * Datos reales de muestra del entorno productivo

# 2\. Flujo funcional del módulo de compras

El proceso de compras en RAFAM tiene cuatro etapas bien definidas que se encadenan en orden. Cada etapa formaliza un paso del ciclo: necesidad → autorización → adjudicación → pago.

|                    |       |                                |       |                             |       |                           |
| :----------------- | :---- | :----------------------------- | :---- | :-------------------------- | :---- | :------------------------ |
| **PEDIDO** Etapa 1 | **→** | **SOLICITUD DE GASTO** Etapa 2 | **→** | **ORDEN DE COMPRA** Etapa 3 | **→** | **ORDEN DE PAGO** Etapa 4 |

## 2.1 Etapa 1 — Pedido

\*\*Tablas: \*\*`PEDIDOS` + `PED_ITEMS`

El pedido es el punto de partida del proceso. Una dependencia o área del organismo detecta una necesidad (insumos de oficina, servicios de mantenimiento, materiales de obra, etc.) y la registra en el sistema.

El pedido documenta qué se necesita (los ítems, con descripción, cantidad y clasificación presupuestaria) y desde qué jurisdicción se solicita. No implica ningún compromiso presupuestario ni designa proveedor; es la expresión de una necesidad interna.

**Estados posibles:**

|       |                                                                     |
| :---- | :------------------------------------------------------------------ |
| **N** | Normal — estado activo habitual                                     |
| **G** | Generado / derivado — el pedido dio origen a una solicitud de gasto |
| **A** | Anulado — pedido cancelado                                          |

## 2.2 Etapa 2 — Solicitud de gasto

\*\*Tabla: \*\*`SOLIC_GASTOS`

La solicitud de gasto formaliza y autoriza el pedido desde el punto de vista presupuestario. Es el paso en que el organismo dice "sí, este gasto está justificado y hay crédito disponible para afrontarlo". A partir de este momento el gasto queda comprometido en el presupuesto.

En esta etapa puede aparecer un proveedor sugerido (campo OP\_COD\_PROV), aunque todavía no es definitivo porque la adjudicación formal ocurre en la siguiente etapa.

## 2.3 Etapa 3 — Orden de compra

\*\*Tablas: \*\*`ORDEN_COMPRA` + `OC_ITEMS`

La orden de compra (OC) es el documento contractual de la compra. Define quién va a proveer los bienes o servicios, en qué condiciones y por qué monto. Es el acto administrativo que le da forma legal a la adquisición.

  * Se designa oficialmente al proveedor adjudicado (COD\_PROV).
  * Se detallan los ítems contratados con cantidades y precios unitarios (OC\_ITEMS).
  * Se establece el monto total y las condiciones de pago.
  * Cada ítem de OC\_ITEMS recuerda de cuál solicitud de gasto proviene (NRO\_SOLIC), permitiendo trazar el recorrido completo.

**Estados posibles:**

|       |                                                          |
| :---- | :------------------------------------------------------- |
| **R** | Registrado — estado operativo habitual de una OC vigente |
| **N** | Normal                                                   |
| **A** | Anulado                                                  |

## 2.4 Etapa 4 — Orden de pago

\*\*Tabla: \*\*`ORDEN_PAGO`

La orden de pago es la instrucción formal de abonar al proveedor. Es el cierre administrativo y financiero del proceso. Registra el monto a pagar, los descuentos, retenciones impositivas y el importe líquido que efectivamente recibe el proveedor.

**Estado clave:**

|       |                                                              |
| :---- | :----------------------------------------------------------- |
| **C** | Cancelado / Acreditado — el pago fue efectivamente realizado |
| **N** | Normal — pendiente de acreditación                           |
| **A** | Anulado                                                      |

# 3\. Tablas maestras de referencia

Las tablas maestras no pertenecen a ninguna etapa del proceso: existen antes que cualquier compra y son compartidas por todas las entidades transaccionales. Deben sincronizarse antes que cualquier otra entidad en una integración con sistemas externos.

## 3.1 PROVEEDORES

Es el registro oficial de todos los proveedores habilitados para operar con el organismo. Toda referencia a un proveedor en el sistema apunta a un registro de esta tabla. Si un proveedor no está en el padrón, el sistema no puede procesar ninguna operación con él.

| Campo                  | Tipo         | Descripción                                          |
| :--------------------- | :----------- | :--------------------------------------------------- |
| **COD\_PROV (PK)**     | NUMBER(5)    | Código único del proveedor                           |
| **RAZON\_SOCIAL**      | VARCHAR2(70) | Razón social legal                                   |
| **FANTASIA**           | VARCHAR2(70) | Nombre de fantasía (fallback a RAZON\_SOCIAL)        |
| **CUIT**               | VARCHAR2(13) | CUIT con formato XX-XXXXXXXX-X                       |
| **COD\_IVA**           | VARCHAR2(5)  | Condición IVA: RINS / MONOT / EXEN / CF / NGAN / RNI |
| **ING\_BRUTOS**        | VARCHAR2(25) | Número de inscripción Ingresos Brutos                |
| **COD\_ESTADO**        | NUMBER       | Estado: 0 = Habilitado                               |
| **CALLE\_POSTAL**      | VARCHAR2(40) | Domicilio postal — calle                             |
| **NRO\_POSTAL**        | VARCHAR2(5)  | Domicilio postal — número                            |
| **CALLE\_LEGAL**       | VARCHAR2(40) | Domicilio legal — calle                              |
| **NRO\_LEGAL**         | VARCHAR2(5)  | Domicilio legal — número                             |
| **EMAIL**              | VARCHAR2(50) | Correo electrónico de contacto                       |
| **NRO\_TELE\_TE1/2/3** | VARCHAR2(12) | Teléfonos de contacto (hasta 3)                      |
| **TE\_CELULAR**        | VARCHAR2(15) | Celular                                              |
| **FECHA\_ALTA**        | DATE         | Fecha de registro en el padrón                       |
| **FECHA\_ULT\_COMP**   | DATE         | Fecha de última compra realizada                     |

## 3.2 JURISDICCIONES

Las jurisdicciones son las unidades organizativas del organismo: áreas, secretarías, subsecretarías, departamentos. Aparecen en casi todas las etapas del proceso para identificar qué área del organismo está involucrada en cada operación.

| Campo                 | Tipo         | Descripción                                   |
| :-------------------- | :----------- | :-------------------------------------------- |
| **JURISDICCION (PK)** | VARCHAR2(10) | Código de jurisdicción (ej: 1110104000)       |
| **DENOMINACION**      | VARCHAR2(50) | Nombre descriptivo del área                   |
| **SELECCIONABLE**     | VARCHAR2(1)  | Indica si se puede seleccionar en formularios |
| **VIGENTE\_DESDE**    | NUMBER(4)    | Año de inicio de vigencia                     |
| **VIGENTE\_HASTA**    | NUMBER(4)    | Año de fin de vigencia (NULL = activa)        |

# 4\. Diagrama Entidad-Relación — Módulo de Compras

A continuación se presenta el esquema de relaciones entre las tablas principales del módulo de compras, incluyendo las tablas maestras y las auxiliares de retenciones.

``` 
DIAGRAMA ENTIDAD-RELACIÓN — MÓDULO DE COMPRAS RAFAM
┌─────────────────────────────┐
**│  PROVEEDORES (MAESTRA)      │**
│  PK: COD_PROV               │
│  RAZON_SOCIAL, CUIT         │
│  COD_IVA, COD_ESTADO        │
└──────────┬──────────────────┘
           │ referenciado por SOLIC_GASTOS.OP_COD_PROV
           │ referenciado por ORDEN_COMPRA.COD_PROV
           │ referenciado por ORDEN_PAGO.COD_PROV
┌─────────────────────────────┐
**│  JURISDICCIONES (MAESTRA)   │**
│  PK: JURISDICCION           │
│  DENOMINACION               │
└──────────┬──────────────────┘
           │ referenciada por PEDIDOS, SOLIC_GASTOS, ORDEN_PAGO
┌─────────────────────────────────────────────────┐
**│  PEDIDOS                                        │**
│  PK: EJERCICIO + NUM_PED                        │
│  FECH_EMI, JURISDICCION (FK→JURISDICCIONES)     │
│  COSTO_TOT, PED_ESTADO [N/G/A]                  │
│  ─────────────────────────────────────────────  │
│  ├── PED_ITEMS (1:N)                            │
│       PK: EJERCICIO+NUM_PED+ORDEN               │
│       DESCRIP_BIE, CANTIDAD, COSTO_UNI          │
└────────────────────┬────────────────────────────┘
                     │ 1:1  NRO_PED → NUM_PED
┌─────────────────────────────────────────────────┐
**│  SOLIC_GASTOS                                   │**
│  PK: EJERCICIO + DELEG_SOLIC + NRO_SOLIC        │
│  NRO_PED (FK→PEDIDOS), JURISDICCION (FK)        │
│  IMPORTE_TOT, ESTADO_SOLIC, FECH_SOLIC          │
│  OP_COD_PROV (*sugerido — no definitivo*)        │
└────────────────────┬────────────────────────────┘
                     │ referenciada por OC_ITEMS.NRO_SOLIC
┌─────────────────────────────────────────────────┐
**│  ORDEN_COMPRA                                   │**
│  PK: EJERCICIO + UNI_COMPRA + NRO_OC            │
│  FECH_OC, COD_PROV (FK→PROVEEDORES) ★           │
│  ESTADO_OC [R/N/A], IMPORTE_TOT                 │
│  COND_PAGO, CONFIRMADO                          │
│  ─────────────────────────────────────────────  │
│  ├── OC_ITEMS (1:N)                             │
│       PK: EJERCICIO+UNI_COMPRA+NRO_OC+ITEM_OC  │
│       NRO_SOLIC (FK→SOLIC_GASTOS) ← nexo clave  │
│       DESCRIPCION, CANTIDAD, IMP_UNITARIO       │
└────────────────────┬────────────────────────────┘
                     │ RECO_DEU_COMPRA → NRO_OC (referencia en OP)
┌─────────────────────────────────────────────────┐
**│  ORDEN_PAGO                                     │**
│  PK: EJERCICIO + NRO_OP                         │
│  COD_PROV (FK→PROVEEDORES) ★                    │
│  ESTADO_OP [C/N/A], IMPORTE_TOTAL               │
│  IMPORTE_LIQUIDO, JURISDICCION (FK)             │
│  RECO_DEU_COMPRA / RECO_DEU_COMPRA_EJER (→OC)  │
│  ─────────────────────────────────────────────  │
│  ├── RETENCIONES (1:N via NRO_CANCE)            │
│       EJERCICIO+NRO_CANCE+COD_RET+CUENTA        │
│       IMPORTE de la retención                   │
│  ├── DEDUCCIONES (descripción de retención)      │
│       CODIGO (FK←RETENCIONES.COD_RET)           │
└─────────────────────────────────────────────────┘
**★ = fuente de verdad del proveedor en cada contexto**

```

# 5\. Esquema técnico de tablas del flujo

## 5.1 PEDIDOS

\*\*PK: \*\*`EJERCICIO` + `NUM_PED`   |   \*\*FK: \*\*`JURISDICCION` → `JURISDICCIONES`

| Campo               | Tipo           | Nulo | Descripción                                     |
| :------------------ | :------------- | :--- | :---------------------------------------------- |
| **EJERCICIO**       | NUMBER(4)      | No   | Año del ejercicio presupuestario                |
| **NUM\_PED**        | NUMBER(6)      | No   | Número de pedido dentro del ejercicio           |
| **FECH\_EMI**       | DATE           | No   | Fecha de emisión del pedido                     |
| **JURISDICCION**    | VARCHAR2(10)   | No   | Jurisdicción solicitante (FK → JURISDICCIONES)  |
| **CODIGO\_DEP**     | VARCHAR2(6)    | No   | Dependencia interna                             |
| **CODIGO\_UE**      | NUMBER(2)      | No   | Unidad ejecutora                                |
| **CODIGO\_FF**      | NUMBER(3)      | No   | Fuente de financiamiento                        |
| **COSTO\_TOT**      | NUMBER(15,2)   | Sí   | Costo total estimado del pedido                 |
| **OBSERVACIONES**   | VARCHAR2(4000) | Sí   | Observaciones libres                            |
| **PED\_ESTADO**     | VARCHAR2(5)    | No   | Estado: N (Normal) / G (Generado) / A (Anulado) |
| **LUG\_EMI**        | VARCHAR2(5)    | No   | Lugar de emisión                                |
| **FECH\_MODI\_ULT** | DATE           | Sí   | Fecha de última modificación                    |

## 5.2 PED\_ITEMS

\*\*PK: \*\*`EJERCICIO` + `NUM_PED` + `ORDEN`   |   \*\*FK: \*\*`NUM_PED` → `PEDIDOS`

| Campo            | Tipo           | Nulo | Descripción                           |
| :--------------- | :------------- | :--- | :------------------------------------ |
| **EJERCICIO**    | NUMBER(4)      | No   | Año del ejercicio                     |
| **NUM\_PED**     | NUMBER(6)      | No   | FK → PEDIDOS.NUM\_PED                 |
| **ORDEN**        | NUMBER(4)      | No   | Número de ítem dentro del pedido      |
| **JURISDICCION** | VARCHAR2(10)   | No   | Jurisdicción del ítem                 |
| **DESCRIP\_BIE** | VARCHAR2(4000) | No   | Descripción del bien o servicio       |
| **CANTIDAD**     | NUMBER(10,3)   | No   | Cantidad solicitada                   |
| **COSTO\_UNI**   | NUMBER(15,5)   | No   | Precio unitario estimado              |
| **INCISO**       | NUMBER(1)      | No   | Clasificación presupuestaria — inciso |
| **PAR\_PRIN**    | NUMBER(1)      | No   | Partida principal                     |
| **PAR\_PARC**    | NUMBER(1)      | No   | Partida parcial                       |
| **CLASE**        | NUMBER(5)      | No   | Clase del bien                        |
| **TIPO**         | NUMBER(4)      | No   | Tipo del bien                         |
| **PROGRAMA**     | NUMBER(2)      | No   | Programa presupuestario               |

## 5.3 SOLIC\_GASTOS

\*\*PK: \*\*`EJERCICIO` + `DELEG_SOLIC` + `NRO_SOLIC`   |   \*\*FK: \*\*`NRO_PED` → `PEDIDOS`, `JURISDICCION` → `JURISDICCIONES`

| Campo             | Tipo         | Nulo | Descripción                                           |
| :---------------- | :----------- | :--- | :---------------------------------------------------- |
| **EJERCICIO**     | NUMBER(4)    | No   | Año del ejercicio                                     |
| **DELEG\_SOLIC**  | NUMBER(4)    | No   | Delegación que emite la solicitud                     |
| **NRO\_SOLIC**    | NUMBER(6)    | No   | Número de solicitud                                   |
| **NRO\_PED**      | NUMBER(6)    | Sí   | FK → PEDIDOS.NUM\_PED — pedido origen                 |
| **JURISDICCION**  | VARCHAR2(10) | No   | Jurisdicción de la solicitud                          |
| **CODIGO\_DEP**   | VARCHAR2(6)  | No   | Dependencia                                           |
| **FECH\_SOLIC**   | DATE         | No   | Fecha de la solicitud                                 |
| **IMPORTE\_TOT**  | NUMBER(15,2) | No   | Importe total de la solicitud                         |
| **ESTADO\_SOLIC** | VARCHAR2(1)  | Sí   | Estado de la solicitud                                |
| **CONFIRMADO**    | VARCHAR2(1)  | No   | Indica si la solicitud fue confirmada                 |
| **FECH\_CONFIRM** | DATE         | Sí   | Fecha de confirmación                                 |
| **FECH\_ANUL**    | DATE         | Sí   | Fecha de anulación                                    |
| **MOTIVO\_ANUL**  | VARCHAR2(6)  | Sí   | Motivo de anulación                                   |
| **CODIGO\_FF**    | NUMBER(3)    | No   | Fuente de financiamiento                              |
| **SG\_DIFERIDO**  | VARCHAR2(1)  | Sí   | Indica si el gasto es diferido al siguiente ejercicio |

## 5.4 ORDEN\_COMPRA

\*\*PK: \*\*`EJERCICIO` + `UNI_COMPRA` + `NRO_OC`   |   \*\*FK: \*\*`COD_PROV` → `PROVEEDORES`

| Campo                | Tipo           | Nulo | Descripción                                          |
| :------------------- | :------------- | :--- | :--------------------------------------------------- |
| **EJERCICIO**        | NUMBER(4)      | No   | Año del ejercicio                                    |
| **UNI\_COMPRA**      | NUMBER(4)      | No   | Unidad de compra                                     |
| **NRO\_OC**          | NUMBER(6)      | No   | Número de orden de compra                            |
| **NRO\_ADJUD**       | NUMBER(6)      | Sí   | FK → ADJUDICACIONES                                  |
| **FECH\_OC**         | DATE           | No   | Fecha de emisión de la OC                            |
| **COD\_PROV**        | NUMBER(5)      | No   | ★ Proveedor adjudicado (FK → PROVEEDORES)            |
| **ESTADO\_OC**       | VARCHAR2(1)    | No   | R = Registrado (activa) \| N = Normal \| A = Anulada |
| **IMPORTE\_TOT**     | NUMBER(15,2)   | No   | Importe total de la orden                            |
| **COND\_PAGO**       | VARCHAR2(6)    | No   | Condición de pago pactada                            |
| **DESC\_COND\_PAGO** | VARCHAR2(45)   | Sí   | Descripción de la condición de pago                  |
| **CONFIRMADO**       | VARCHAR2(1)    | No   | Estado de confirmación                               |
| **FECH\_CONFIRM**    | DATE           | Sí   | Fecha de confirmación                                |
| **FECH\_ENTREGA**    | DATE           | Sí   | Fecha de entrega pactada                             |
| **FECH\_ANUL**       | DATE           | Sí   | Fecha de anulación                                   |
| **MOTIVO\_ANUL**     | VARCHAR2(6)    | Sí   | Motivo de anulación                                  |
| **OBSERVACIONES**    | VARCHAR2(1000) | Sí   | Observaciones                                        |
| **OC\_DIFERIDO**     | VARCHAR2(1)    | Sí   | Indica si la OC cubre ejercicios futuros             |

## 5.5 OC\_ITEMS

\*\*PK: \*\*`EJERCICIO` + `UNI_COMPRA` + `NRO_OC` + `ITEM_OC`   |   Nexo clave: `NRO_SOLIC` → `SOLIC_GASTOS`

| Campo             | Tipo           | Nulo | Descripción                                                                   |
| :---------------- | :------------- | :--- | :---------------------------------------------------------------------------- |
| **EJERCICIO**     | NUMBER(4)      | No   | Año del ejercicio                                                             |
| **UNI\_COMPRA**   | NUMBER(4)      | No   | Unidad de compra (parte de FK → ORDEN\_COMPRA)                                |
| **NRO\_OC**       | NUMBER(6)      | No   | FK → ORDEN\_COMPRA.NRO\_OC                                                    |
| **ITEM\_OC**      | NUMBER(4)      | No   | Número de ítem en la OC                                                       |
| **DELEG\_SOLIC**  | NUMBER(4)      | Sí   | Delegación de la solicitud de origen                                          |
| **NRO\_SOLIC**    | NUMBER(6)      | Sí   | ★ FK → SOLIC\_GASTOS.NRO\_SOLIC — nexo con autorización                       |
| **ITEM\_REAL**    | NUMBER(5)      | Sí   | Referencia al ítem real de la cotización                                      |
| **COD\_PROV**     | NUMBER(5)      | Sí   | Proveedor del ítem (generalmente = OC cabecera; no usar como fuente primaria) |
| **DESCRIPCION**   | VARCHAR2(4000) | No   | Descripción del bien o servicio contratado                                    |
| **CANTIDAD**      | NUMBER(10,3)   | No   | Cantidad contratada                                                           |
| **IMP\_UNITARIO** | NUMBER(15,5)   | No   | Precio unitario contratado                                                    |
| **CANT\_RECIB**   | NUMBER(10,3)   | Sí   | Cantidad efectivamente recibida                                               |
| **IMPORTE\_EJER** | NUMBER(16,5)   | Sí   | Importe imputable al ejercicio corriente                                      |

## 5.6 ORDEN\_PAGO

\*\*PK: \*\*`EJERCICIO` + `NRO_OP`   |   \*\*FK: \*\*`COD_PROV` → `PROVEEDORES`, `JURISDICCION` → `JURISDICCIONES`

| Campo                       | Tipo         | Nulo | Descripción                                       |
| :-------------------------- | :----------- | :--- | :------------------------------------------------ |
| **EJERCICIO**               | NUMBER(4)    | No   | Año del ejercicio                                 |
| **NRO\_OP**                 | NUMBER(6)    | No   | Número de orden de pago                           |
| **FECH\_OP**                | DATE         | No   | Fecha de la orden de pago                         |
| **COD\_PROV**               | NUMBER(5)    | No   | ★ Proveedor al que se paga (FK → PROVEEDORES)     |
| **JURISDICCION**            | VARCHAR2(10) | No   | Jurisdicción que imputa el egreso                 |
| **ESTADO\_OP**              | VARCHAR2(1)  | No   | C = Cancelado/Pagado \| N = Normal \| A = Anulado |
| **IMPORTE\_TOTAL**          | NUMBER(15,2) | No   | Importe bruto de la orden                         |
| **IMPORTE\_LIQUIDO**        | NUMBER(15,2) | Sí   | Importe líquido a acreditar al proveedor          |
| **RECO\_DEU\_COMPRA**       | NUMBER(6)    | Sí   | Referencia al NRO\_OC de la compra origen         |
| **RECO\_DEU\_COMPRA\_EJER** | NUMBER(4)    | Sí   | Ejercicio del NRO\_OC referenciado                |
| **TIPO\_OP**                | VARCHAR2(1)  | Sí   | Tipo de orden de pago                             |
| **CODIGO\_FF**              | NUMBER(3)    | No   | Fuente de financiamiento                          |
| **CODIGO\_UE**              | NUMBER(2)    | No   | Unidad ejecutora                                  |
| **CONFIRMADO**              | VARCHAR2(1)  | No   | Estado de confirmación                            |
| **FECH\_CONFIRM**           | DATE         | Sí   | Fecha de confirmación/acreditación                |
| **NRO\_CANCE**              | NUMBER(7)    | Sí   | Número de cancelación (vincula con RETENCIONES)   |

# 6\. Tablas complementarias del ecosistema

## 6.1 CTA\_HOJA\_DE\_RUTA

Vista desnormalizada que consolida en una sola fila toda la trazabilidad de un expediente: el pedido origen, la solicitud de gasto, la orden de compra, la orden de pago y el número de cancelación. Es la tabla más utilizada para obtener el estado del pago (ESTADO\_OP = "C") y el número de OC asociado a una OP.

| Campo clave                     | Descripción                                     |
| :------------------------------ | :---------------------------------------------- |
| **PE\_EJERCICIO / PE\_NRO**     | Datos del pedido origen                         |
| **SG\_EJERCICIO / SG\_NRO**     | Datos de la solicitud de gasto                  |
| **OC\_EJERCICIO / OC\_NRO\_OC** | Datos de la orden de compra                     |
| **OP\_NRO\_OP / ESTADO\_OP**    | Datos de la orden de pago y su estado           |
| **OP\_NRO\_CANCE**              | Número de cancelación (vincula con RETENCIONES) |
| **OC\_COD\_PROV**               | Proveedor de la OC                              |
| **PE\_JURISDICCION**            | Jurisdicción del pedido                         |

## 6.2 RETENCIONES

Registra las retenciones impositivas aplicadas en el momento del pago. Se vincula con ORDEN\_PAGO a través del número de cancelación (NRO\_CANCE).

| Campo                                               | Descripción                                            |
| :-------------------------------------------------- | :----------------------------------------------------- |
| **EJERCICIO + NRO\_CANCE + COD\_RET + CUENTA (PK)** | Clave compuesta                                        |
| **COD\_RET**                                        | Código del tipo de retención (FK → DEDUCCIONES.CODIGO) |
| **IMPORTE**                                         | Monto retenido                                         |
| **CUENTA**                                          | Cuenta contable destino de la retención                |

## 6.3 DEDUCCIONES

Tabla de referencia que contiene la descripción de cada tipo de retención/deducción. Se vincula con RETENCIONES para obtener el nombre del impuesto aplicado.

| Campo           | Descripción                                                     |
| :-------------- | :-------------------------------------------------------------- |
| **CODIGO**      | Código del tipo de deducción (vincula con RETENCIONES.COD\_RET) |
| **DESCRIPCION** | Nombre de la retención (ej: "Ganancias", "IVA", "IIBB")         |
| **TIPO\_DEDUC** | Tipo de deducción                                               |
| **PORCENTAJE**  | Porcentaje aplicado                                             |
| **EJERCICIO**   | Año de vigencia                                                 |

## 6.4 REG\_COMP (Registro de Comprobantes)

Registra los comprobantes (facturas) asociados a las órdenes de compra. Es la tabla que vincula la OC con el comprobante fiscal y permite obtener el proveedor real de cada comprobante, así como la jurisdicción.

| Campo clave                         | Descripción                               |
| :---------------------------------- | :---------------------------------------- |
| **EJERCICIO + NRO\_REG\_COMP (PK)** | Identificador del registro de comprobante |
| **NRO\_OC**                         | FK → ORDEN\_COMPRA.NRO\_OC                |
| **COD\_PROV**                       | Proveedor del comprobante                 |
| **JURISDICCION**                    | Jurisdicción de imputación                |
| **FECH\_REG\_COMP**                 | Fecha del registro                        |

## 6.5 ADJUDICACIONES

Registra el proceso de adjudicación previo a la emisión de la OC. Vincula la cotización del proceso licitatorio con el proveedor adjudicado formalmente.

| Campo clave                       | Descripción                      |
| :-------------------------------- | :------------------------------- |
| **EJERCICIO + NRO\_ADJUDIC (PK)** | Identificador de la adjudicación |
| **NRO\_COTI**                     | Número de cotización licitada    |
| **COD\_PROV**                     | Proveedor adjudicado             |
| **FECH\_ADJUD**                   | Fecha de adjudicación            |
| **ESTADO**                        | Estado de la adjudicación        |
| **COND\_PAGO**                    | Condición de pago acordada       |

# 7\. Análisis crítico del campo proveedor

El campo `COD_PROV` aparece en múltiples tablas del sistema. Comprender cuándo y por qué puede diferir entre tablas es esencial para cualquier integración o análisis.

## 7.1 Dónde aparece el proveedor

| Etapa                       | Tabla         | Campo         | Significado                                       |
| :-------------------------- | :------------ | :------------ | :------------------------------------------------ |
| **Solicitud de gasto**      | SOLIC\_GASTOS | OP\_COD\_PROV | Proveedor sugerido — NO definitivo                |
| **Orden de compra**         | ORDEN\_COMPRA | COD\_PROV     | ★ Proveedor adjudicado formalmente                |
| **Ítems de la OC**          | OC\_ITEMS     | COD\_PROV     | Proveedor del ítem — NO usar como fuente primaria |
| **Orden de pago**           | ORDEN\_PAGO   | COD\_PROV     | ★ Proveedor que recibe el pago                    |
| **Registro de comprobante** | REG\_COMP     | COD\_PROV     | Proveedor de la factura vinculada                 |

## 7.2 Por qué pueden diferir

**SOLIC\_GASTOS.OP\_COD\_PROV vs ORDEN\_COMPRA.COD\_PROV:** En la solicitud de gasto no hubo proceso de adjudicación. El proveedor es una propuesta o sugerencia. El proceso licitatorio puede derivar en un proveedor diferente. Es normal que difieran.

**OC\_ITEMS.COD\_PROV vs ORDEN\_COMPRA.COD\_PROV:** En teoría deberían coincidir. Las diferencias responden a errores de carga o a OCs divididas. No usar OC\_ITEMS como fuente confiable.

**ORDEN\_PAGO.COD\_PROV vs ORDEN\_COMPRA.COD\_PROV:** Pueden diferir por cesión de crédito (el proveedor cedió el cobro a un tercero) o por ajustes administrativos. Esta diferencia es especialmente relevante para auditorías.

## 7.3 Regla de fuente de verdad

| Pregunta                              | Fuente de verdad            | Regla                               |
| :------------------------------------ | :-------------------------- | :---------------------------------- |
| **¿A quién se adjudicó la compra?**   | ORDEN\_COMPRA.COD\_PROV     | Dato contractual y jurídico         |
| **¿A quién se le pagó?**              | ORDEN\_PAGO.COD\_PROV       | Dato financiero real del desembolso |
| **¿Quién fue sugerido al autorizar?** | SOLIC\_GASTOS.OP\_COD\_PROV | Referencial — NO definitivo         |
| **¿El ítem fue provisto por quién?**  | ORDEN\_COMPRA.COD\_PROV     | Usar cabecera OC, no OC\_ITEMS      |

Las diferencias de proveedor entre tablas **no son errores de integración**: son datos del negocio que deben preservarse. Cuando se detecta discrepancia entre ORDEN\_PAGO.COD\_PROV y ORDEN\_COMPRA.COD\_PROV, ambos proveedores deben existir en el sistema destino.

# 8\. Mapeo de campos RAFAM → Paxapos

A continuación se detalla el mapeo de campos entre el schema OWNER\_RAFAM y el sistema Paxapos para las entidades del flujo de compras.

## 8.1 Proveedores

| RAFAM (PROVEEDORES)                              | Paxapos            | Transformación                                |
| :----------------------------------------------- | :----------------- | :-------------------------------------------- |
| **COD\_PROV (PK)**                               | id\_externo        | Directa                                       |
| **RAZON\_SOCIAL**                                | razon\_social      | trim()                                        |
| **FANTASIA**                                     | name               | trim(); fallback a RAZON\_SOCIAL si vacío     |
| **CUIT**                                         | cuit               | \_normalize\_cuit() — formato XX-XXXXXXXX-X   |
| **COD\_IVA**                                     | iva\_condicion\_id | Mapeo: RINS/MONOT/EXEN/CF/NGAN/RNI            |
| **COD\_ESTADO**                                  | estado             | Mapeo numérico → texto                        |
| **CALLE\_POSTAL + NRO\_POSTAL**                  | domicilio          | \_join\_address(); fallback a domicilio legal |
| **LOCA\_POSTAL / LOCA\_LEGAL**                   | localidad          | \_first\_non\_empty()                         |
| **COD\_POSTAL / COD\_LEGAL**                     | codigo\_postal     | \_first\_non\_empty()                         |
| **PROV\_POSTAL / PROV\_LEGAL**                   | provincia          | \_first\_non\_empty()                         |
| **NRO\_PAIS\_TE1+NRO\_INTE\_TE1+NRO\_TELE\_TE1** | telefono           | \_build\_phone(); fallback TE2, TE3, CELULAR  |
| **EMAIL**                                        | mail               | trim()                                        |
| **FECHA\_ALTA**                                  | created\_at        | Directa                                       |
| **FECHA\_ULT\_COMP**                             | updated\_at        | Directa                                       |

## 8.2 Jurisdicciones

| RAFAM (JURISDICCIONES) | Paxapos        | Transformación |
| :--------------------- | :------------- | :------------- |
| **JURISDICCION (PK)**  | id\_externo    | Directa        |
| **DENOMINACION**       | nombre         | trim()         |
| **SELECCIONABLE**      | seleccionable  | Directa        |
| **VIGENTE\_DESDE**     | vigente\_desde | Directa        |
| **VIGENTE\_HASTA**     | vigente\_hasta | Directa        |

## 8.3 Pedidos

| RAFAM                       | Paxapos                        | Transformación                          |
| :-------------------------- | :----------------------------- | :-------------------------------------- |
| **PEDIDOS.EJERCICIO (PK)**  | pedidos.ejercicio              | Directa                                 |
| **PEDIDOS.NUM\_PED (PK)**   | pedidos.numero\_pedido         | Directa                                 |
| **PEDIDOS.FECH\_EMI**       | pedidos.fecha                  | Directa                                 |
| **PEDIDOS.JURISDICCION**    | pedidos.jurisdiccion\_id       | Lookup por id\_externo → JURISDICCIONES |
| **PEDIDOS.COSTO\_TOT**      | pedidos.importe\_total         | Directa                                 |
| **PEDIDOS.OBSERVACIONES**   | pedidos.observaciones          | trim()                                  |
| **PEDIDOS.PED\_ESTADO**     | pedidos.estado                 | Mapeo de código                         |
| **PED\_ITEMS.ORDEN**        | pedido\_items.nro\_item        | Directa                                 |
| **PED\_ITEMS.NUM\_PED**     | pedido\_items.pedido\_id       | Lookup FK → PEDIDOS                     |
| **PED\_ITEMS.DESCRIP\_BIE** | pedido\_items.descripcion      | trim()                                  |
| **PED\_ITEMS.CANTIDAD**     | pedido\_items.cantidad         | Directa                                 |
| **PED\_ITEMS.COSTO\_UNI**   | pedido\_items.precio\_unitario | Directa                                 |
| **PED\_ITEMS.JURISDICCION** | pedido\_items.jurisdiccion\_id | Lookup por id\_externo                  |

## 8.4 Solicitudes de gasto

| RAFAM (SOLIC\_GASTOS) | Paxapos                              | Transformación                      |
| :-------------------- | :----------------------------------- | :---------------------------------- |
| **EJERCICIO (PK)**    | solicitudes\_gasto.ejercicio         | Directa                             |
| **DELEG\_SOLIC (PK)** | solicitudes\_gasto.deleg\_solic      | Directa                             |
| **NRO\_SOLIC (PK)**   | solicitudes\_gasto.numero\_solicitud | Directa                             |
| **NRO\_PED**          | solicitudes\_gasto.pedido\_id        | Lookup ejercicio+num\_ped → PEDIDOS |
| **JURISDICCION**      | solicitudes\_gasto.jurisdiccion\_id  | Lookup por id\_externo              |
| **FECH\_SOLIC**       | solicitudes\_gasto.fecha             | Directa                             |
| **IMPORTE\_TOT**      | solicitudes\_gasto.importe           | Directa                             |
| **ESTADO\_SOLIC**     | solicitudes\_gasto.estado            | Mapeo de código                     |

## 8.5 Órdenes de compra

| RAFAM                              | Paxapos                        | Transformación                           |
| :--------------------------------- | :----------------------------- | :--------------------------------------- |
| **ORDEN\_COMPRA.EJERCICIO (PK)**   | ordenes\_compra.ejercicio      | Directa                                  |
| **ORDEN\_COMPRA.UNI\_COMPRA (PK)** | ordenes\_compra.uni\_compra    | Directa                                  |
| **ORDEN\_COMPRA.NRO\_OC (PK)**     | ordenes\_compra.numero\_oc     | Directa                                  |
| **ORDEN\_COMPRA.FECH\_OC**         | ordenes\_compra.fecha          | Directa                                  |
| **ORDEN\_COMPRA.COD\_PROV**        | ordenes\_compra.proveedor\_id  | ★ Lookup por id\_externo → PROVEEDORES   |
| **ORDEN\_COMPRA.ESTADO\_OC**       | ordenes\_compra.estado         | N→pendiente, A→anulada                   |
| **ORDEN\_COMPRA.IMPORTE\_TOT**     | ordenes\_compra.importe\_total | Directa                                  |
| **OC\_ITEMS.NRO\_OC**              | oc\_items.orden\_compra\_id    | Lookup clave compuesta → ORDEN\_COMPRA   |
| **OC\_ITEMS.ITEM\_OC**             | oc\_items.nro\_item            | Directa                                  |
| **OC\_ITEMS.NRO\_SOLIC**           | oc\_items.solic\_gasto\_id     | ★ Lookup clave compuesta → SOLIC\_GASTOS |
| **OC\_ITEMS.DESCRIPCION**          | oc\_items.descripcion          | trim()                                   |
| **OC\_ITEMS.CANTIDAD**             | oc\_items.cantidad             | Directa                                  |
| **OC\_ITEMS.IMP\_UNITARIO**        | oc\_items.precio\_unitario     | Directa                                  |

## 8.6 Órdenes de pago

| RAFAM (ORDEN\_PAGO)   | Paxapos                          | Transformación                         |
| :-------------------- | :------------------------------- | :------------------------------------- |
| **EJERCICIO (PK)**    | ordenes\_pago.ejercicio          | Directa                                |
| **NRO\_OP (PK)**      | ordenes\_pago.numero\_op         | Directa                                |
| **FECH\_OP**          | ordenes\_pago.fecha              | Directa                                |
| **COD\_PROV**         | ordenes\_pago.proveedor\_id      | ★ Lookup por id\_externo → PROVEEDORES |
| **JURISDICCION**      | ordenes\_pago.jurisdiccion\_id   | Lookup por id\_externo                 |
| **ESTADO\_OP**        | ordenes\_pago.estado             | C→pagada, A→anulada, N→pendiente       |
| **IMPORTE\_TOTAL**    | ordenes\_pago.importe\_total     | Directa                                |
| **IMPORTE\_LIQUIDO**  | ordenes\_pago.importe\_liquido   | Directa                                |
| **RECO\_DEU\_COMPRA** | ordenes\_pago.orden\_compra\_ref | Referencia NRO\_OC origen              |

# 9\. Orden de sincronización recomendado

Para una integración correcta con sistemas externos, el orden de carga debe respetar las dependencias referenciales. Las entidades maestras deben existir antes que cualquier registro transaccional.

| Paso  | Entidad              | Tabla RAFAM               | Motivo                                                       |
| :---- | :------------------- | :------------------------ | :----------------------------------------------------------- |
| **1** | Jurisdicciones       | JURISDICCIONES            | Referenciada por todas las tablas transaccionales            |
| **2** | Proveedores          | PROVEEDORES               | Referenciada por OC, OP y SG. Sin proveedores no hay compras |
| **3** | Pedidos              | PEDIDOS + PED\_ITEMS      | Primera entidad transaccional del flujo                      |
| **4** | Solicitudes de gasto | SOLIC\_GASTOS             | Referencia PEDIDOS.NUM\_PED                                  |
| **5** | Órdenes de compra    | ORDEN\_COMPRA + OC\_ITEMS | OC\_ITEMS referencia SOLIC\_GASTOS                           |
| **6** | Órdenes de pago      | ORDEN\_PAGO               | Referencia ORDEN\_COMPRA y PROVEEDORES                       |
| **7** | Retenciones          | RETENCIONES + DEDUCCIONES | Dependen de ORDEN\_PAGO (NRO\_CANCE)                         |

# 10\. Consultas SQL de referencia

## 10.1 Trazabilidad completa de una compra

Obtiene el recorrido completo de una OC: pedido origen, solicitud de gasto, ítems y estado de pago.

``` sql
SELECT hr.PE_NRO, hr.SG_NRO, hr.OC_NRO_OC, hr.OP_NRO_OP,
       hr.ESTADO_OP, hr.OP_NRO_CANCE, pr.RAZON_SOCIAL
FROM OWNER_RAFAM.CTA_HOJA_DE_RUTA hr
JOIN OWNER_RAFAM.PROVEEDORES pr ON pr.COD_PROV = hr.OC_COD_PROV
WHERE hr.OC_EJERCICIO = :anio AND hr.OC_NRO_OC = :nro_oc

```

## 10.2 Órdenes de pago acreditadas (estado C)

Obtiene todas las órdenes de pago efectivamente pagadas en un ejercicio.

``` sql
SELECT op.EJERCICIO, op.NRO_OP, op.FECH_OP,
       op.IMPORTE_TOTAL, op.IMPORTE_LIQUIDO,
       pr.RAZON_SOCIAL, pr.CUIT, j.DENOMINACION
FROM OWNER_RAFAM.ORDEN_PAGO op
JOIN OWNER_RAFAM.PROVEEDORES pr ON pr.COD_PROV = op.COD_PROV
JOIN OWNER_RAFAM.JURISDICCIONES j  ON j.JURISDICCION = op.JURISDICCION
WHERE op.ESTADO_OP = 'C' AND op.EJERCICIO = :anio
ORDER BY op.FECH_OP DESC

```

## 10.3 Retenciones de una orden de pago

Obtiene el detalle de retenciones de un pago específico, identificando el tipo y monto de cada una.

``` sql
SELECT r.NRO_CANCE, d.DESCRIPCION AS tipo_retencion,
       r.IMPORTE, r.CUENTA
FROM OWNER_RAFAM.ORDEN_PAGO op
JOIN OWNER_RAFAM.RETENCIONES r   ON  r.EJERCICIO = op.EJERCICIO
                           AND r.NRO_CANCE = op.NRO_CANCE
JOIN OWNER_RAFAM.DEDUCCIONES d   ON  d.CODIGO    = r.COD_RET
WHERE op.EJERCICIO = :anio AND op.NRO_OP = :nro_op

```

## 10.4 Detección de diferencias de proveedor entre OC y OP

Identifica órdenes de pago cuyo proveedor difiere del proveedor adjudicado en la orden de compra. Útil para auditorías y detección de cesiones de crédito.

``` sql
SELECT op.EJERCICIO, op.NRO_OP,
       op.COD_PROV AS prov_pago, oc.COD_PROV AS prov_compra,
       op.RECO_DEU_COMPRA AS nro_oc
FROM OWNER_RAFAM.ORDEN_PAGO   op
JOIN OWNER_RAFAM.ORDEN_COMPRA oc ON oc.EJERCICIO = op.RECO_DEU_COMPRA_EJER
                             AND oc.NRO_OC   = op.RECO_DEU_COMPRA
WHERE op.COD_PROV != oc.COD_PROV
ORDER BY op.EJERCICIO DESC, op.NRO_OP

```

# 11\. Datos reales de muestra

A continuación se presentan registros reales del entorno productivo (ejercicio 2026) para validar comportamientos y confirmar mappings.

## 11.1 Muestra de PROVEEDORES

| COD\_PROV | RAZON\_SOCIAL               | CUIT          | COD\_IVA | FECHA\_ALTA |
| :-------- | :-------------------------- | :------------ | :------- | :---------- |
| **1**     | CORBELLINI HUGO CESAR       | 20-22630728-2 | MONOT    | 17/09/2003  |
| **2**     | VEYRA RAMON ROBERTO         | 20-13810238-7 | MONOT    | 23/02/2000  |
| **3**     | RAMOS DELFOR SAUL (NO USAR) | 20-05318329-9 | RINS     | 17/02/2000  |
| **4**     | RUZZO CARLOS DANIEL         | 30-67779639-8 | RINS     | 07/03/2000  |
| **5**     | ANDRES PONSA S.A.           | 30-56811894-0 | RINS     | 17/03/2000  |
| **6**     | COMAR AUTOMOTORES S.A.      | 30-67680490-7 | RINS     | 14/03/2000  |

## 11.2 Muestra de PEDIDOS recientes (2026)

| EJERCICIO | NUM\_PED | FECH\_EMI  | JURISDICCION | COSTO\_TOT | ESTADO |
| :-------- | :------- | :--------- | :----------- | :--------- | :----- |
| **2026**  | 1081     | 17/03/2026 | 1110104000   | $134.576   | N      |
| **2026**  | 1080     | 17/03/2026 | 1110104000   | $137.978   | N      |
| **2026**  | 1079     | 17/03/2026 | 1110104000   | $527.339   | N      |
| **2026**  | 1078     | 17/03/2026 | 1110104000   | $80.000    | N      |
| **2026**  | 1077     | 17/03/2026 | 1110118000   | $98.000    | N      |
| **2026**  | 1076     | 17/03/2026 | 1110113000   | $547.888   | N      |

## 11.3 Muestra de ORDEN\_COMPRA recientes (2026)

| EJERCICIO | NRO\_OC | FECH\_OC   | COD\_PROV | ESTADO | IMPORTE\_TOT |
| :-------- | :------ | :--------- | :-------- | :----- | :----------- |
| **2026**  | 1060    | 17/03/2026 | 3511      | N      | $2.847.000   |
| **2026**  | 1059    | 17/03/2026 | 1527      | N      | $203.000     |
| **2026**  | 1058    | 16/03/2026 | 3430      | N      | $255.966     |
| **2026**  | 1057    | 16/03/2026 | 2627      | N      | $18.800      |
| **2026**  | 1056    | 16/03/2026 | 879       | N      | $12.600      |
| **2026**  | 1055    | 16/03/2026 | 688       | N      | $263.000     |

## 11.4 Muestra de ORDEN\_PAGO recientes (2026)

| EJERCICIO | NRO\_OP | FECH\_OP   | COD\_PROV | ESTADO | IMPORTE\_TOTAL | LIQUIDO  |
| :-------- | :------ | :--------- | :-------- | :----- | :------------- | :------- |
| **2026**  | 1453    | 17/03/2026 | 3557      | N      | $880.000       | $880.000 |
| **2026**  | 1452    | 17/03/2026 | 50012     | N      | $40.899        | $40.899  |
| **2026**  | 1451    | 17/03/2026 | 50002     | N      | $859.025       | $859.025 |
| **2026**  | 1450    | 17/03/2026 | 50370     | N      | $111.819       | $111.819 |
| **2026**  | 1448    | 17/03/2026 | 2627      | N      | $6.500         | $6.240   |
| **2026**  | 1447    | 17/03/2026 | 2627      | N      | $6.000         | $5.760   |

Nota: las OPs con `IMPORTE_LIQUIDO` menor al `IMPORTE_TOTAL` indican que se aplicaron retenciones. Por ejemplo, la OP 1448 del proveedor 2627 tiene una retención de $260. Para obtener el detalle, consultar `RETENCIONES` por `NRO_CANCE`.

# 12\. Resumen ejecutivo

| Concepto                       | Definición                                                        |
| :----------------------------- | :---------------------------------------------------------------- |
| **Flujo de compras**           | Pedido → Solicitud de Gasto → Orden de Compra → Orden de Pago     |
| **Tablas maestras críticas**   | PROVEEDORES y JURISDICCIONES — sincronizar primero                |
| **Tabla central del proceso**  | ORDEN\_COMPRA                                                     |
| **Nexo compra ↔ autorización** | OC\_ITEMS.NRO\_SOLIC → SOLIC\_GASTOS                              |
| **Nexo OP ↔ OC**               | ORDEN\_PAGO.RECO\_DEU\_COMPRA → ORDEN\_COMPRA.NRO\_OC             |
| **Proveedor de una compra**    | ORDEN\_COMPRA.COD\_PROV (dato contractual)                        |
| **Proveedor de un pago**       | ORDEN\_PAGO.COD\_PROV (dato financiero)                           |
| **Pago efectivizado**          | ORDEN\_PAGO.ESTADO\_OP = 'C'                                      |
| **Retenciones de un pago**     | RETENCIONES.NRO\_CANCE → ORDEN\_PAGO.NRO\_CANCE                   |
| **Vista de trazabilidad**      | CTA\_HOJA\_DE\_RUTA — consolida todo el flujo en una fila         |
| **Diferencia prov. OC vs OP**  | No es error — puede ser cesión de crédito o ajuste administrativo |

**Regla de oro para integraciones:** Al registrar una orden de compra en el sistema destino, vincular `ORDEN_COMPRA.COD_PROV`. Al registrar una orden de pago, vincular `ORDEN_PAGO.COD_PROV`. Nunca usar `OC_ITEMS.COD_PROV` ni `SOLIC_GASTOS.OP_COD_PROV` como fuente primaria del proveedor.
