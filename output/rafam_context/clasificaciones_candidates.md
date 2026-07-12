# Clasificaciones RAFAM (partidas) — `default`

> Generado por `scripts/explore_clasificaciones.py` el 2026-07-12T18:25:11.925309Z
> Backend: `sqlite` · Solo lectura
> **No editar manualmente** — regenerar ejecutando el script.

## Objetivo

Detectar y analizar las tablas que contienen la jerarquía de partidas (`inciso`→`par_prin`→`par_parc`[→`par_subp`] + `DENOMINACION`) para diseñar una entidad de migración *clasificaciones* hacia la `Categoria` (nested-set) de Paxapos.

## Resumen del escaneo

- Objetos escaneados: **19**
- Candidatas (score ≥ 2): **3**
- Con jerarquía completa (3+ niveles): **3**
- Con `DENOMINACION` co-localizada: **0**

## Fuente canónica recomendada

➡️ **`ORDEN_PAGO_IMPUT`** es la mejor fuente para el catálogo de partidas (tiene la jerarquía completa; **NINGUNA candidata trae `DENOMINACION` local** — los nombres de partida habrá que resolverlos aparte (otra tabla/vista o mapeo manual)).

Orden de preferencia:
1. `ORDEN_PAGO_IMPUT`
2. `SOLIC_GASTOS_ITEMS`
3. `PED_ITEMS`

> ⚠️ Nota arquitectónica: RAFAM no tiene una tabla maestra relacional limpia de partidas. La entidad *clasificaciones* deberá construirse con un `SELECT DISTINCT` de la jerarquía + denominación sobre la fuente recomendada.

## Candidatas

| Objeto | Tipo | Score | Niveles | DENOMINACION | Filas (est.) | Combos distintos |
|--------|------|-------|---------|--------------|--------------|------------------|
| `ORDEN_PAGO_IMPUT` | table | 4 | `INCISO`, `PAR_PRIN`, `PAR_PARC`, `PAR_SUBP` | — | ? | — |
| `PED_ITEMS` | table | 3 | `INCISO`, `PAR_PRIN`, `PAR_PARC` | — | ? | — |
| `SOLIC_GASTOS_ITEMS` | table | 4 | `INCISO`, `PAR_PRIN`, `PAR_PARC`, `PAR_SUBP` | — | ? | — |

## Detalle por candidata

### ORDEN_PAGO_IMPUT (table)

- **Jerarquía:** `INCISO` (N1), `PAR_PRIN` (N2), `PAR_PARC` (N3), `PAR_SUBP` (N4)
- **Columnas de texto:** *(ninguna — sin denominación local)*

Muestra del árbol distinct (hasta 50 filas):

| INCISO | PAR_PRIN | PAR_PARC | PAR_SUBP |
|---|---|---|---|
| 1 | 1 | 1 | 0 |
| 1 | 1 | 3 | 0 |
| 1 | 1 | 4 | 0 |
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
| 1 | 4 | 0 | 0 |
| 1 | 5 | 0 | 0 |
| 1 | 6 | 0 | 0 |
| 2 | 1 | 1 | 0 |
| 2 | 1 | 4 | 0 |
| 2 | 1 | 5 | 0 |
| 2 | 1 | 9 | 0 |
| 2 | 2 | 1 | 0 |
| 2 | 2 | 2 | 0 |
| 2 | 2 | 3 | 0 |
| 2 | 2 | 9 | 0 |
| 2 | 3 | 1 | 0 |
| 2 | 3 | 2 | 0 |
| 2 | 3 | 4 | 0 |
| 2 | 3 | 5 | 0 |
| 2 | 3 | 9 | 0 |
| 2 | 4 | 2 | 0 |
| 2 | 4 | 3 | 0 |
| 2 | 4 | 4 | 0 |
| 2 | 5 | 1 | 0 |
| 2 | 5 | 2 | 0 |
| 2 | 5 | 4 | 0 |
| 2 | 5 | 5 | 0 |
| 2 | 5 | 6 | 0 |
| 2 | 5 | 7 | 0 |
| 2 | 5 | 8 | 0 |
| 2 | 5 | 9 | 0 |
| 2 | 6 | 1 | 0 |
| 2 | 6 | 2 | 0 |
| 2 | 6 | 3 | 0 |
| 2 | 6 | 4 | 0 |
| 2 | 6 | 5 | 0 |
| 2 | 6 | 9 | 0 |
| 2 | 7 | 1 | 0 |
| 2 | 7 | 2 | 0 |
| 2 | 7 | 4 | 0 |
| 2 | 7 | 5 | 0 |

### PED_ITEMS (table)

- **Jerarquía:** `INCISO` (N1), `PAR_PRIN` (N2), `PAR_PARC` (N3)
- **Columnas de texto:** `DESCRIP_BIE`

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
| 2 | 1 | 1 | 0 | ACEITE COMESTIBLE - ACEITE COMESTIBLE (GENERICO) ACEITE OLIVA x 500c.c |
