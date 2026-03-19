# Sistema de Traducción RAFAM → Paxapos

> **Audiencia:** equipo de desarrollo  
> **Última actualización:** 2026-03-19

---

## 1. Qué es el traductor y por qué existe

RAFAM y Paxapos hablan "idiomas" distintos. RAFAM almacena proveedores en una
tabla relacional Oracle con convenciones de los 90 (nombres en mayúsculas,
teléfono partido en 3 campos, CUIT con guiones). Paxapos espera un payload
JSON moderno con campos normalizados.

El traductor es la capa que convierte una fila cruda de Oracle en ese JSON,
validando los campos críticos **antes** de hacer el HTTP POST. Sin esta capa,
los errores de datos se detectarían recién en la respuesta de Paxapos, sin
contexto suficiente para identificar la fila problemática.

---

## 2. Ubicación en el proyecto

```
src/
└── Traductor/
    ├── __init__.py        # TRANSLATOR_REGISTRY — diccionario entidad → instancia
    ├── base.py            # BaseTranslator — contrato abstracto
    └── proveedores.py     # ProveedoresTranslator — implementación concreta
```

El `GatewayExporter` (en `src/exporter.py`) consulta el `TRANSLATOR_REGISTRY`
para obtener el traductor de cada entidad antes de enviar cada lote.

---

## 3. Contrato base (`BaseTranslator`)

```python
class BaseTranslator(ABC):

    @property
    @abstractmethod
    def endpoint_path(self) -> str:
        """Ruta relativa del endpoint Paxapos. Ej: 'account/proveedores/add'"""

    @abstractmethod
    def translate(self, columns: list[str], row: tuple) -> dict:
        """Convierte una fila Oracle en un payload JSON listo para POST."""
```

Toda entidad nueva **debe** heredar de `BaseTranslator` e implementar estos
dos métodos. El resto del flujo (HTTP, reintentos, logging, checkpoint) no
necesita cambios.

---

## 4. Cómo funciona `ProveedoresTranslator`

### 4.1 Entrada y salida

| Entrada | Salida |
|---------|--------|
| `columns: list[str]` — nombres de columna del cursor Oracle | `dict` — payload JSON para Paxapos |
| `row: tuple` — valores de la fila en el mismo orden | `ValueError` si un campo obligatorio es inválido |

El primer paso interno es construir un diccionario `{COLUMNA: valor}` con
claves en mayúsculas para hacer el acceso case-insensitive independientemente
de cómo Oracle devuelva los nombres.

### 4.2 Pipeline de campos

```
Fila Oracle
    │
    ├─ CUIT ──────────────── _normalize_cuit() ──► strip de guiones/puntos/espacios
    │                              │
    │                         ValueError si vacío o ≠ 11 dígitos
    │
    ├─ RAZON_SOCIAL ─────────────────────────────► .strip() → name
    │                              │                          razon_social
    │                         ValueError si vacío o nulo
    │
    ├─ tipo_documento_id ────────── hardcoded = 1 (RAFAM solo usa CUIT)
    │
    ├─ name_cuit ───────────────── derivado: "RAZON_SOCIAL - CUIT"
    │
    ├─ EMAIL ────────────────────── .strip() · omitido si nulo/vacío
    │
    ├─ TELEFONO ──────────── _build_telefono() ──► "+PAIS AREA NUMERO" o TE_CELULAR
    │
    ├─ DOMICILIO ─────────── _build_domicilio() ─► "CALLE NRO" (NRO opcional)
    │
    ├─ COD_POSTAL ───────────────── .strip() · omitido si nulo
    │
    ├─ FECHA_ALTA ────────── _format_date() ─────► "YYYY-MM-DD" desde date/datetime
    │
    └─ campos sin equivalente en RAFAM ──────────► null explícito en el payload
       (iva_condicion_id, localidad, provincia,
        cbu, cbu_alias, modified, created_by,
        deleted_date)
```

Los **nulls explícitos** son intencionales: si se omiten, Paxapos podría
rechazar el payload por campos requeridos ausentes o mantener valores
anteriores en un upsert.

### 4.3 Normalización del CUIT

```python
@staticmethod
def _normalize_cuit(value: str) -> str:
    return re.sub(r"\D", "", value or "")
```

Elimina todo carácter no-dígito. Soporta los formatos que almacena RAFAM:

| Formato en RAFAM | Resultado normalizado |
|------------------|-----------------------|
| `20-12345678-9`  | `20123456789`         |
| `20.12345678.9`  | `20123456789`         |
| `20 12345678 9`  | `20123456789`         |
| `20123456789`    | `20123456789`         |

### 4.4 Armado del teléfono

RAFAM parte el teléfono en tres campos:

| Campo RAFAM    | Ejemplo | Rol          |
|----------------|---------|--------------|
| `NRO_PAIS_TE1` | `54`    | código país  |
| `NRO_INTE_TE1` | `11`    | código área  |
| `NRO_TELE_TE1` | `45551234` | número    |

El método `_build_telefono()` los une como `"+54 11 45551234"`.  
Si `NRO_TELE_TE1` es nulo, hace **fallback a `TE_CELULAR`** (campo sin partir).  
Si ambos son nulos, el campo `telefono` se omite del payload.

---

## 5. Validaciones y cuándo se disparan

Las validaciones ocurren en **Etapa 2** del flujo (procesamiento), antes de
hacer cualquier llamada HTTP. Esto permite identificar exactamente qué fila
del origen tiene datos incorrectos.

| Condición | Excepción lanzada |
|-----------|-------------------|
| `CUIT` nulo o string vacío | `ValueError("CUIT vacío o nulo")` |
| `CUIT` con ≠ 11 dígitos tras normalizar | `ValueError("CUIT inválido: se esperan 11 dígitos, recibidos N")` |
| `RAZON_SOCIAL` nula o solo espacios | `ValueError("RAZON_SOCIAL está vacía o es nula")` |

El `GatewayExporter` captura estos `ValueError`, los registra en el log con
el contexto completo (`COD_PROV`, `CUIT`, `RAZON_SOCIAL`) y continúa con la
siguiente fila sin abortar el lote.

---

## 6. Flujo completo en producción

```
Oracle RAFAM
    │  SELECT * FROM OWNER_RAFAM.PROVEEDORES
    │  (cursor de 500 filas por lote)
    ▼
SyncEngine.build_incremental_query()
    │  WHERE FECHA_ALTA > :ultimo_ts  (modo incremental)
    │  sin WHERE                       (primer run / full load)
    ▼
GatewayExporter.write_batch()
    │  por cada fila:
    │    1. _row_context()          → identifica la fila en logs
    │    2. translator.translate()  → arma el payload / lanza ValueError
    │    3. session.post()          → HTTP POST a Paxapos
    │    4. _raise_if_gateway_error() → detecta errores en cuerpo JSON (HTTP 200 con error)
    ▼
CheckpointStore (SQLite)
    │  guarda last_ts = max(FECHA_ALTA) del lote
    │  próxima ejecución es incremental desde ese punto
    ▼
Log final:
    [proveedores] RESUMEN: 1498 OK | 2 ERROR de 1500
```

---

## 7. Cómo se testeó

### 7.1 Pruebas unitarias 

Se desarrollaron y ejecutaron localmente dos familias de tests:

**`test_traductor_proveedores` — 18 casos:**

| Grupo | Escenarios |
|-------|------------|
| CUIT con distintos separadores | guiones, puntos, espacios, sin separador |
| Teléfono | los 3 campos separados, solo celular, ambos nulos |
| Dirección | calle + número, solo calle, con piso/dpto |
| Fecha | `date`, `datetime`, nulo |
| Email | con espacios laterales (strip), nulo |
| Errores esperados | CUIT vacío → `ValueError`, CUIT de 8 dígitos → `ValueError`, RAZON_SOCIAL vacía → `ValueError` |

**`test_pilot_500_proveedores` — 23 casos sobre 500 filas simuladas:**

Construyó un dataset realista con el schema real de RAFAM (`SELECT *` devuelve
27 columnas). Resultado esperado y verificado: **390 OK | 110 ERROR**.

Los 110 errores cubrían: DNI (8 dígitos), CUIT nulo, RAZON_SOCIAL nula/espacios,
CUIT con letras, CUIT de 9 dígitos.

### 7.2 Prueba de integración real (`test_pilot_integration_30`)

Se ejecutó contra el endpoint real con 30 proveedores de datos simulados 
**con CUITs de dígito verificador válido**


**Descubrimientos durante la prueba:**

1. **SSL auto-firmado en desarrollo:** resuelto con `GATEWAY_VERIFY_SSL=false` en `.env`.
2. **HTTP 200 con cuerpo de error:** Paxapos devuelve `200 OK` incluso cuando
   rechaza un registro. `_raise_if_gateway_error()` parsea el JSON y levanta
   `RuntimeError` si detecta `error`, `validationErrors` o `success: false`.
3. **CUITs con check-digit inválido:** el servidor valida el dígito
   verificador AFIP — no alcanza con 11 dígitos, deben ser matemáticamente
   correctos.
4. **Idempotencia:** una segunda ejecución con los mismos CUITs devuelve
   `"El Cuit ya existe"` — esto es comportamiento esperado, no un error del script.

**Resultado final:** 30/30 OK en primera ejecución, 30/30 OK idempotente
en segunda ejecución.

---

## 8. Cómo agregar un nuevo traductor

1. Crear `src/Traductor/<entidad>.py` heredando `BaseTranslator`:

```python
from .base import BaseTranslator

class PedidosTranslator(BaseTranslator):

    endpoint_path = "account/pedidos/add"

    def translate(self, columns, row):
        raw = {k.upper(): v for k, v in self._row_to_raw(columns, row).items()}
        # ... mapear campos ...
        return payload
```

2. Registrar en `src/Traductor/__init__.py`:

```python
from .pedidos import PedidosTranslator

TRANSLATOR_REGISTRY = {
    "proveedores": ProveedoresTranslator(),
    "pedidos":     PedidosTranslator(),   # ← agregar esta línea
}
```

Eso es todo. El motor de sync y el exporter lo toman automáticamente.

