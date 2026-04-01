# Tablas y datos enviados a Paxapos

Inventario completo de todas las entidades que el script exporta hacia el sistema Paxapos.

> **Endpoint base:** `/rafam/migracion/importar.json` (modo Migrator, POST masivo)  
> **Opciones globales:** `upsert: true`, `atomic: false`

---

## Estructura raíz del payload (común a todos los envíos)

```json
{
  "dry_run": false,
  "options": {
    "upsert": true,
    "atomic": false,
    "fail_fast": false,
    "send_oc_mail": false,
    "strict_mail": false
  },
  "rubros": [],
  "clasificaciones": [],
  "proveedores": [],
  "pedidos": [],
  "ordenes_compra": [],
  "gastos": [],
  "ordenes_pago": []
}
```

En cada batch se llenan solo las listas correspondientes a la entidad que se está enviando; el resto queda vacío.

---

## 1. Proveedores

Fuente RAFAM: `PROVEEDORES` · Referencia: [src/gateway_mapper.py](../src/gateway_mapper.py)

| Campo Paxapos | Fuente RAFAM | Regla / Transformación |
|---|---|---|
| `name` | `FANTASIA` / `RAZON_SOCIAL` | Primer valor no nulo, máx. 100 caracteres |
| `razon_social` | `RAZON_SOCIAL` | Trimmed |
| `mail` | `EMAIL` | Trimmed |
| `telefono` | `NRO_PAIS_TE1..3`, `TE_CELULAR` | Concatena país + característica + número; intenta 3 teléfonos |
| `domicilio` | `CALLE_LEGAL` + `NRO_LEGAL` | Concatena calle y número; fallback a `CALLE_POSTAL` |
| `localidad` | `LOCA_LEGAL` / `LOCA_POSTAL` | Primer valor no nulo |
| `provincia` | `PROV_LEGAL` / `PROV_POSTAL` | Primer valor no nulo |
| `codigo_postal` | `COD_LEGAL` / `COD_POSTAL` | Primer valor no nulo |
| `cuit` | `CUIT` | Solo dígitos, debe tener exactamente 11 |
| `tipo_documento_id` | `CUIT` | `1` si tiene CUIT, `None` si no |
| `iva_condicion_id` | `COD_IVA` | RINS=1, MONOT=2, EXEN=3, CF=4, NGAN=5, RNI=6 |
| `external_id` | `COD_PROV` | `{"cod_prov": int(COD_PROV)}` |

**Payload de ejemplo:**
```json
{
  "proveedores": [
    {
      "external_id": { "cod_prov": 984 },
      "Proveedor": {
        "name": "DISTRIBUIDORA EL SOL",
        "razon_social": "DISTRIBUIDORA EL SOL S.A.",
        "cuit": "30712345678",
        "mail": "contacto@elsol.com",
        "telefono": "54 11 44445555",
        "domicilio": "AV. RIVADAVIA 1234",
        "localidad": "LA PLATA",
        "provincia": "BUENOS AIRES",
        "codigo_postal": "1900",
        "tipo_documento_id": 1,
        "iva_condicion_id": 1
      }
    }
  ]
}
```

---

## 2. Rubros y Clasificaciones (Jurisdicciones)

Fuente RAFAM: `JURISDICCIONES` · Genera **dos** colecciones en el mismo payload: `rubros` y `clasificaciones`.

| Campo Paxapos | Fuente RAFAM | Regla / Transformación |
|---|---|---|
| `name` | `DENOMINACION` | Fallback a `JURISDICCION` si es nulo |
| `external_id` | `JURISDICCION` | `{"jurisdiccion": str(JURISDICCION)}` |

**Payload de ejemplo:**
```json
{
  "rubros": [
    {
      "external_id": { "jurisdiccion": "1110100000" },
      "Rubro": { "name": "DEPARTAMENTO EJECUTIVO" }
    }
  ],
  "clasificaciones": [
    {
      "external_id": { "jurisdiccion": "1110100000" },
      "Clasificacion": { "name": "DEPARTAMENTO EJECUTIVO", "parent_id": null }
    }
  ]
}
```

---

## 3. Pedidos (Solicitudes de bienes)

Fuente RAFAM: `PEDIDOS` (cabecera) + `PED_ITEMS` (ítems)

| Campo Paxapos | Fuente RAFAM | Regla / Transformación |
|---|---|---|
| `internal_id` | `EJERCICIO`, `NUM_PED` | `"rafam-ped-{ejercicio}-{num_ped}"` |
| `tipo` | — | Fijo: `"solicitud"` |
| `monto_presupuestado` | `PED_COSTO_TOT` | Float, de la cabecera |
| `observacion` | — | `"Migrado RAFAM PED {ejercicio}-{num_ped}"` |
| `items[].mercaderia_external_ref` | `EJERCICIO`, `NUM_PED`, `ORDEN`, claves contables | Referencia compuesta (clase, tipo, inciso, etc.) |
| `items[].cantidad` | `CANTIDAD` | Float, obligatorio |
| `items[].precio` | `COSTO_UNI` | Float, opcional |
| `items[].unidad_de_medida_id` | `UNI_MED` | Lookup remoto por nombre; default: `MIGRATOR_DEFAULT_UNIDAD_ID` |
| `items[].descripcion` | `DESCRIP_BIE` | Máx. 255 caracteres |
| `items[].observacion` | `DESCRIP_BIE` | Mismo valor que `descripcion` |

**Payload de ejemplo:**
```json
{
  "pedidos": [
    {
      "external_id": { "ejercicio": 2024, "num_ped": 123 },
      "Pedido": {
        "internal_id": "rafam-ped-2024-123",
        "tipo": "solicitud",
        "observacion": "Migrado RAFAM PED 2024-123",
        "monto_presupuestado": 15000.50
      },
      "items": [
        {
          "mercaderia_external_ref": {
            "source": "rafam",
            "entity": "ped_items",
            "ejercicio": 2024,
            "num_ped": 123,
            "orden": 1
          },
          "cantidad": 10.0,
          "precio": 1500.05,
          "unidad_de_medida_id": 1,
          "descripcion": "RESMA DE PAPEL A4",
          "observacion": "RESMA DE PAPEL A4"
        }
      ]
    }
  ]
}
```

---

## 4. Órdenes de Compra

Fuente RAFAM: `ORDEN_COMPRA` (cabecera) + `OC_ITEMS` (ítems)

| Campo Paxapos | Fuente RAFAM | Regla / Transformación |
|---|---|---|
| `internal_id` | `EJERCICIO`, `UNI_COMPRA`, `NRO_OC` | `"rafam-oc-{ejercicio}-{uni_compra}-{nro_oc}"` |
| `tipo` | — | Fijo: `"orden_compra"` |
| `proveedor_id` | `COD_PROV` | ID externo del proveedor (ya migrado) |
| `items[].mercaderia_external_ref` | `EJERCICIO`, `UNI_COMPRA`, `NRO_OC`, `ITEM_OC` | Referencia al ítem de la OC |
| `items[].cantidad` | `CANTIDAD` | Float, obligatorio |
| `items[].precio` | `IMP_UNITARIO` | Precio unitario |
| `items[].recibida_cantidad` | `CANT_RECIB` | Cantidad ya recibida en RAFAM |
| `items[].unidad_de_medida_id` | `UNI_MED` | Igual que pedidos |

**Payload de ejemplo:**
```json
{
  "ordenes_compra": [
    {
      "external_id": { "ejercicio": 2024, "uni_compra": 1, "nro_oc": 456 },
      "Pedido": {
        "internal_id": "rafam-oc-2024-1-456",
        "tipo": "orden_compra",
        "proveedor_id": 984,
        "observacion": "Migrado RAFAM OC 2024-1-456"
      },
      "items": [
        {
          "mercaderia_external_ref": {
            "source": "rafam",
            "entity": "oc_items",
            "ejercicio": 2024,
            "uni_compra": 1,
            "nro_oc": 456,
            "item_oc": 1
          },
          "cantidad": 10.0,
          "recibida_cantidad": 5.0,
          "precio": 1500.0,
          "unidad_de_medida_id": 1
        }
      ]
    }
  ]
}
```

---

## 5. Gastos (Solicitudes de gasto de fondos)

Fuente RAFAM: `SOLIC_GASTOS`

| Campo Paxapos | Fuente RAFAM | Regla / Transformación |
|---|---|---|
| `external_id` | `EJERCICIO`, `DELEG_SOLIC`, `NRO_SOLIC` | `{"rafam_ref": "SG-{ejercicio}-{deleg_solic}-{nro_solic}"}` |
| `fecha` | `FECH_SOLIC` | Formato `YYYY-MM-DD` |
| `importe_total` | `IMPORTE_TOT` | Float |
| `importe_neto` | `IMPORTE_TOT` | Mismo valor (sin discriminar IVA) |
| `punto_de_venta` | — | Fijo: `"RAFAM"` |
| `tipo_factura_id` | `TIPO_DOC` | Lookup por codename/name; default: `MIGRATOR_DEFAULT_TIPO_FACTURA_ID` |
| `factura_nro` | `NRO_DOC` | Cero-padding a 8 dígitos |
| `clasificacion_id` | `JURISDICCION` | Lookup local en `EntityLinkStore` |
| `fecha_vencimiento` | `FECH_NECESIDAD` / `FECH_ENTREGA` | Prioriza `FECH_NECESIDAD` |
| `observacion` | — | Opcional |

**Payload de ejemplo:**
```json
{
  "gastos": [
    {
      "external_id": { "rafam_ref": "SG-2024-1-789" },
      "Gasto": {
        "fecha": "2024-03-28",
        "importe_total": 50000.0,
        "importe_neto": 50000.0,
        "punto_de_venta": "RAFAM",
        "tipo_factura_id": 1,
        "factura_nro": "00001234",
        "clasificacion_id": 101,
        "fecha_vencimiento": "2024-04-28"
      }
    }
  ]
}
```

---

## 6. Órdenes de Pago (Egresos)

Fuente RAFAM: `ORDEN_PAGO` (con JOIN a `SOLIC_GASTOS` vía `NRO_CANCE`)

| Campo Paxapos | Fuente RAFAM | Regla / Transformación |
|---|---|---|
| `external_id` | `EJERCICIO`, `NRO_OP` | `{"ejercicio": int, "nro_op": int}` |
| `identificador_pago` | `EJERCICIO`, `NRO_OP` | `"RAFAM-OP-{ejercicio}-{nro_op}"` |
| `total` | `IMPORTE_TOTAL` | Float |
| `estado` | `ESTADO_OP` | `3` (Pagado) si `'C'`; `0` (Pendiente) si no; `'A'` (Anulada) → omitida |
| `fecha` | `FECH_CONFIRM` / `FECH_OP` | Solo para OPs con estado `'C'` (confirmadas) |
| `tipo_de_pago_id` | — | Fijo: env `MIGRATOR_DEFAULT_TIPO_PAGO_ID` (default `1`) |
| `observacion` | — | Opcional |
| `gasto_external_ids` | `SG_DELEG_SOLIC`, `SG_NRO_SOLIC` | Lista de refs `"SG-{ej}-{deleg}-{nro}"` del gasto cancelado |

**Payload de ejemplo:**
```json
{
  "ordenes_pago": [
    {
      "external_id": { "ejercicio": 2024, "nro_op": 321 },
      "Egreso": {
        "identificador_pago": "RAFAM-OP-2024-321",
        "total": 50000.0,
        "tipo_de_pago_id": 1,
        "estado": 3,
        "fecha": "2024-03-31"
      },
      "gasto_external_ids": ["SG-2024-1-789"]
    }
  ]
}
```

> **Nota:** Las OPs con `ESTADO_OP = 'A'` (anuladas) se omiten completamente del envío.

---

## Resumen de tablas fuente

| Entidad Paxapos | Tablas RAFAM involucradas |
|---|---|
| Proveedores | `PROVEEDORES` |
| Rubros / Clasificaciones | `JURISDICCIONES` |
| Pedidos | `PEDIDOS`, `PED_ITEMS` |
| Órdenes de Compra | `ORDEN_COMPRA`, `OC_ITEMS` |
| Gastos | `SOLIC_GASTOS` |
| Órdenes de Pago | `ORDEN_PAGO`, `SOLIC_GASTOS` |

## Variables de entorno relevantes

| Variable | Uso |
|---|---|
| `MIGRATOR_DEFAULT_UNIDAD_ID` | ID de unidad de medida por defecto (pedidos) |
| `MIGRATOR_DEFAULT_TIPO_FACTURA_ID` | ID de tipo de factura por defecto (gastos) |
| `MIGRATOR_DEFAULT_TIPO_PAGO_ID` | ID de tipo de pago por defecto (órdenes de pago, default `1`) |
