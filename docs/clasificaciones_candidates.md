# Clasificaciones RAFAM (partidas) — `OWNER_RAFAM`

> Generado por `scripts/explore_clasificaciones.py` el 2026-07-14T16:09:22.348024Z
> Backend: `oracle` · Solo lectura
> **No editar manualmente** — regenerar ejecutando el script.

## Objetivo

Detectar y analizar las tablas que contienen la jerarquía de partidas (`inciso`→`par_prin`→`par_parc`[→`par_subp`] + `DENOMINACION`) para diseñar una entidad de migración *clasificaciones* hacia la `Categoria` (nested-set) de Paxapos.

## Resumen del escaneo

- Objetos escaneados: **18**
- Candidatas (score ≥ 2): **4**
- Con jerarquía completa (3+ niveles): **4**
- Con `DENOMINACION` co-localizada: **1**

## Fuente canónica recomendada

➡️ **`GASTOS`** es la mejor fuente para el catálogo de partidas (tiene la jerarquía + `DENOMINACION` co-localizada; mejor relación catálogo/volumen).

Orden de preferencia:
1. `GASTOS`
2. `SOLIC_GASTOS_ITEMS`
3. `ORDEN_PAGO_IMPUT`
4. `PED_ITEMS`

> ⚠️ Nota arquitectónica: RAFAM no tiene una tabla maestra relacional limpia de partidas. La entidad *clasificaciones* deberá construirse con un `SELECT DISTINCT` de la jerarquía + denominación sobre la fuente recomendada.

## Candidatas

| Objeto | Tipo | Score | Niveles | DENOMINACION | Filas (est.) | Combos distintos |
|--------|------|-------|---------|--------------|--------------|------------------|
| `GASTOS` | table | 4 | `INCISO`, `PAR_PRIN`, `PAR_PARC`, `PAR_SUBP` | ✓ | 9,069 | 378 |
| `ORDEN_PAGO_IMPUT` | table | 4 | `INCISO`, `PAR_PRIN`, `PAR_PARC`, `PAR_SUBP` | — | 525,552 | 175 |
| `PED_ITEMS` | table | 3 | `INCISO`, `PAR_PRIN`, `PAR_PARC` | — | 366,992 | 128 |
| `SOLIC_GASTOS_ITEMS` | table | 4 | `INCISO`, `PAR_PRIN`, `PAR_PARC`, `PAR_SUBP` | — | 401,790 | 130 |

## Detalle por candidata

### GASTOS (table)

- **Jerarquía:** `INCISO` (N1), `PAR_PRIN` (N2), `PAR_PARC` (N3), `PAR_SUBP` (N4)
- **Columnas de texto:** `DENOMINACION`, `DENOMINACION_AB`
- **PK:** `anio_presup`, `inciso`, `par_prin`, `par_parc`, `par_subp`
- **Filas (estimadas):** 9,069
- **Combinaciones distintas de jerarquía:** 378

Muestra del árbol distinct (hasta 50 filas):

| INCISO | PAR_PRIN | PAR_PARC | PAR_SUBP | DENOMINACION |
|---|---|---|---|---|
| 1 | 0 | 0 | 0 | Gastos en personal |
| 1 | 1 | 0 | 0 | Personal permanente |
| 1 | 1 | 1 | 0 | Retribuciones del cargo |
| 1 | 1 | 2 | 0 | Retribuciones a personal directivo y de control |
| 1 | 1 | 3 | 0 | Retribuciones que no hacen al cargo |
| 1 | 1 | 4 | 0 | Sueldo anual complementario |
| 1 | 1 | 5 | 0 | Otros gastos en personal |
| 1 | 1 | 6 | 0 | Contribuciones patronales |
| 1 | 1 | 6 | 1 | al IPS |
| 1 | 1 | 6 | 2 | AL IOMA |
| 1 | 1 | 6 | 3 | Aporte a la Aseguradora de Riesgos de Trabajo |
| 1 | 1 | 7 | 0 | Complementos |
| 1 | 2 | 0 | 0 | Personal temporario |
| 1 | 2 | 1 | 0 | Retribuciones del cargo |
| 1 | 2 | 2 | 0 | Retribuciones que no hacen al cargo |
| 1 | 2 | 3 | 0 | Sueldo anual complementario |
| 1 | 2 | 4 | 0 | Otros gastos en personal |
| 1 | 2 | 5 | 0 | Contribuciones patronales |
| 1 | 2 | 5 | 1 | AL IPS |
| 1 | 2 | 5 | 2 | AL IOMA |
| 1 | 2 | 5 | 3 | Aporte a la Aseguradora de Riesgos de Trabajo |
| 1 | 2 | 6 | 0 | Complementos |
| 1 | 3 | 0 | 0 | Servicios extraordinarios |
| 1 | 3 | 1 | 0 | Retribuciones extraordinarias |
| 1 | 3 | 2 | 0 | Sueldo anual complementario |
| 1 | 3 | 3 | 0 | Contribuciones patronales |
| 1 | 4 | 0 | 0 | Asignaciones familiares |
| 1 | 5 | 0 | 0 | Asistencia social al personal |
| 1 | 6 | 0 | 0 | Beneficios y compensaciones |
| 2 | 0 | 0 | 0 | Bienes de consumo |
| 2 | 1 | 0 | 0 | Productos alimenticios agropecuarios y forestales |
| 2 | 1 | 1 | 0 | Alimentos para personas |
| 2 | 1 | 2 | 0 | Alimentos para animales |
| 2 | 1 | 3 | 0 | Productos pecuarios |
| 2 | 1 | 4 | 0 | Productos agroforestales |
| 2 | 1 | 5 | 0 | Madera, corcho y sus manufacturas |
| 2 | 1 | 9 | 0 | Otros |
| 2 | 2 | 0 | 0 | Textiles y vestuario |
| 2 | 2 | 1 | 0 | Hilados y telas |
| 2 | 2 | 2 | 0 | Prendas de vestir |
| 2 | 2 | 3 | 0 | Confecciones textiles |
| 2 | 2 | 9 | 0 | Otros |
| 2 | 3 | 0 | 0 | Productos de papel, cartón e impresos |
| 2 | 3 | 1 | 0 | Papel de escritorio y cartón |
| 2 | 3 | 2 | 0 | Papel para computación |
| 2 | 3 | 3 | 0 | Productos de artes gráficas |
| 2 | 3 | 4 | 0 | Productos de papel y cartón |
| 2 | 3 | 5 | 0 | Libros, revistas y periódicos |
| 2 | 3 | 6 | 0 | Textos de enseñanza |
| 2 | 3 | 7 | 0 | Especies timbradas y valores |

### ORDEN_PAGO_IMPUT (table)

- **Jerarquía:** `INCISO` (N1), `PAR_PRIN` (N2), `PAR_PARC` (N3), `PAR_SUBP` (N4)
- **Columnas de texto:** *(ninguna — sin denominación local)*
- **PK:** `ejercicio`, `nro_op`, `nro_reg_comp`, `tipo_comprob`, `nro_comprob`, `cod_prov`, `codigo_ff`, `inciso`, `par_prin`, `par_parc`, `par_subp`, `jurisdiccion`, `programa`, `activ_proy`, `activ_obra`
- **Filas (estimadas):** 525,552
- **Combinaciones distintas de jerarquía:** 175

Muestra del árbol distinct (hasta 50 filas):

| INCISO | PAR_PRIN | PAR_PARC | PAR_SUBP |
|---|---|---|---|
| 1 | 1 | 1 | 0 |
| 1 | 1 | 2 | 0 |
| 1 | 1 | 3 | 0 |
| 1 | 1 | 4 | 0 |
| 1 | 1 | 5 | 0 |
| 1 | 1 | 6 | 1 |
| 1 | 1 | 6 | 2 |
| 1 | 1 | 7 | 0 |
| 1 | 2 | 1 | 0 |
| 1 | 2 | 2 | 0 |
| 1 | 2 | 3 | 0 |
| 1 | 2 | 5 | 1 |
| 1 | 2 | 5 | 2 |
| 1 | 2 | 6 | 0 |
| 1 | 3 | 1 | 0 |
| 1 | 3 | 2 | 0 |
| 1 | 4 | 0 | 0 |
| 1 | 5 | 0 | 0 |
| 1 | 6 | 0 | 0 |
| 2 | 1 | 1 | 0 |
| 2 | 1 | 2 | 0 |
| 2 | 1 | 3 | 0 |
| 2 | 1 | 4 | 0 |
| 2 | 1 | 5 | 0 |
| 2 | 1 | 9 | 0 |
| 2 | 2 | 1 | 0 |
| 2 | 2 | 2 | 0 |
| 2 | 2 | 3 | 0 |
| 2 | 2 | 9 | 0 |
| 2 | 3 | 1 | 0 |
| 2 | 3 | 2 | 0 |
| 2 | 3 | 3 | 0 |
| 2 | 3 | 4 | 0 |
| 2 | 3 | 5 | 0 |
| 2 | 3 | 7 | 0 |
| 2 | 3 | 9 | 0 |
| 2 | 4 | 1 | 0 |
| 2 | 4 | 2 | 0 |
| 2 | 4 | 3 | 0 |
| 2 | 4 | 4 | 0 |
| 2 | 4 | 9 | 0 |
| 2 | 5 | 1 | 0 |
| 2 | 5 | 2 | 0 |
| 2 | 5 | 3 | 0 |
| 2 | 5 | 4 | 0 |
| 2 | 5 | 5 | 0 |
| 2 | 5 | 6 | 0 |
| 2 | 5 | 7 | 0 |
| 2 | 5 | 8 | 0 |
| 2 | 5 | 9 | 0 |

### PED_ITEMS (table)

- **Jerarquía:** `INCISO` (N1), `PAR_PRIN` (N2), `PAR_PARC` (N3)
- **Columnas de texto:** `DESCRIP_BIE`
- **PK:** `ejercicio`, `num_ped`, `orden`
- **FKs:**
  - (`ejercicio`, `num_ped`) → `owner_rafam.pedidos` (`ejercicio`, `num_ped`)
- **Filas (estimadas):** 366,992
- **Combinaciones distintas de jerarquía:** 128

Muestra del árbol distinct (hasta 50 filas):

| INCISO | PAR_PRIN | PAR_PARC | DESCRIP_BIE |
|---|---|---|---|
| 2 | 1 | 1 | ACEITE COMESTIBLE - 
ACEITE COMESTIBLE (GENERICO) X 3 LIT ROS |
| 2 | 1 | 1 | ACEITE COMESTIBLE - 
ACEITE COMESTIBLE Cocinero |
| 2 | 1 | 1 | ACEITE COMESTIBLE -  GIRASOL CAÑUELAS 5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE  1L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE  5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE  GIRASOL - 5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE  NATURA  X 5 LTS |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE 4.5 L |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO  5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO  CAPACIDAD 5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO  GIRASOL  5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO - CAPACIDAD 5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO 5 LTS |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO 5 LTS 5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO 5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO 5LT |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO 5LTS |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO CAPACIDAD 5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO GIRASOL -CAPACIDAD 5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO GIRASOL5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO X  5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE ARO X5LTS |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAPACIDAD 5L. GIRASOL |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS  5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS  BIDON - CAPACIDAD 5L. GIRASOL |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS 5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS 5LT |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS 5LT GIRASOL |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS 5LTS |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS 5LTS GIRASOL |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS DE GIRASOL 5 LTS |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS GIRASOL  5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS GIRASOL  X 5 L |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS GIRASOL 5LT |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS GIRASOL 5LTS |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS GIRASOL CAPACIDAD 5L. |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS X 5 L |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE CAÑUELAS X5LTS GIRASOL |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE COCINERO 5LT |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE COCINERO 5LTS |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE COMESTIBLE |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE COMESTIBLE  X 1 1/2 |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO ) X 900 CC |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO) |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO)
DON ROBERTO X 5 LT |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO)  1 1/2 |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO) 1 1/2 |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO) 1/2 |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO) 3X 12 |
| 2 | 1 | 1 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO) ACEITE ARCOR DE MAIZ |

### SOLIC_GASTOS_ITEMS (table)

- **Jerarquía:** `INCISO` (N1), `PAR_PRIN` (N2), `PAR_PARC` (N3), `PAR_SUBP` (N4)
- **Columnas de texto:** `DESCRIPCION`
- **PK:** `ejercicio`, `deleg_solic`, `nro_solic`, `solic_item`
- **Filas (estimadas):** 401,790
- **Combinaciones distintas de jerarquía:** 130

Muestra del árbol distinct (hasta 50 filas):

| INCISO | PAR_PRIN | PAR_PARC | PAR_SUBP | DESCRIPCION |
|---|---|---|---|---|
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - 
ACEITE COMESTIBLE (GENERICO) X 3 LIT ROS |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - 
ACEITE COMESTIBLE Cocinero |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE -  GIRASOL CAÑUELAS 5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE  1L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE  5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE  GIRASOL - 5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE  NATURA  X 5 LTS |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE 4.5 L |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO  5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO  CAPACIDAD 5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO  GIRASOL  5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO - CAPACIDAD 5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO 5 LTS |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO 5 LTS 5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO 5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO 5LT |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO 5LTS |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO CAPACIDAD 5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO GIRASOL -CAPACIDAD 5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO GIRASOL5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO X  5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE ARO X5LTS |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAPACIDAD 5L. GIRASOL |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS  5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS  BIDON - CAPACIDAD 5L. GIRASOL |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS 5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS 5LT |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS 5LT GIRASOL |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS 5LTS |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS 5LTS GIRASOL |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS DE GIRASOL 5 LTS |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS GIRASOL  5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS GIRASOL  X 5 L |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS GIRASOL 5LT |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS GIRASOL 5LTS |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS GIRASOL CAPACIDAD 5L. |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS X 5 L |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE CAÑUELAS X5LTS GIRASOL |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COCINERO 5LT |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COCINERO 5LTS |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COMESTIBLE |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COMESTIBLE  X 1 1/2 |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO ) X 900 CC |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO) |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO)
DON ROBERTO X 5 LT |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO)  1 1/2 |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO) 1 1/2 |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO) 1/2 |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO) 3X 12 |
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO) ACEITE ARCOR DE MAIZ |
