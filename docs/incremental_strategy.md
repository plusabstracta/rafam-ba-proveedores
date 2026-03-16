# Estrategia incremental por tabla

> Define qué campo usar como **cursor** para detectar registros nuevos o modificados
> en cada tabla RAFAM, habilitando sincronizaciones incrementales sin full-scan.

---

## Resumen ejecutivo

| Tabla | Cursor propuesto | Tipo | Confianza | Acción requerida |
|-------|-----------------|------|-----------|-----------------|
| PROVEEDORES | `FECHA_MODIFICACION` | timestamp | ⏳ pendiente | Confirmar existencia |
| JURISDICCIONES | `FECHA_MODIFICACION` o ID secuencial | timestamp/int | ⏳ pendiente | Confirmar con equipo |
| PEDIDOS | `FECHA_PEDIDO` + `FECHA_MODIFICACION` | timestamp | ⏳ pendiente | Confirmar si se modifica |
| PED_ITEMS | `NRO_PEDIDO` + seq. interno | int | ⏳ pendiente | Confirmar PK compuesta |
| SOLIC_GASTOS | `FECHA_ALTA` o seq. interno | timestamp/int | ⏳ pendiente | Confirmar con DBA |
| ORDEN_COMPRA | `FECHA_OC` + `FECHA_MODIFICACION` | timestamp | ⏳ pendiente | Confirmar |
| OC_ITEMS | seq. interno o FK a OC | int | ⏳ pendiente | Confirmar PK |
| ORDEN_PAGO | `FECHA_OP` + `ESTADO_OP` | timestamp/char | ⏳ pendiente | Confirmar si cambia estado |

---

## Detalle por tabla

### PROVEEDORES

**Estrategia:** Timestamp de modificación  
**Cursor ideal:** `FECHA_MODIFICACION`  
**Alternativa:** `FECHA_ALTA` (solo detecta altas, no modificaciones)  
**Consideración:** Los cambios de estado (`COD_ESTADO`) deben disparar una actualización.
Si no existe `FECHA_MODIFICACION`, considerar sincronización completa periódica (tabla chica).

```sql
-- Ejemplo de consulta incremental
SELECT * FROM OWNER_RAFAM.PROVEEDORES
WHERE FECHA_MODIFICACION > :ultimo_cursor
ORDER BY FECHA_MODIFICACION
```

---

### JURISDICCIONES

**Estrategia:** Tabla de referencia estática — sincronización completa en cada ejecución  
**Cursor ideal:** N/A (tabla probablemente pequeña y sin cambios frecuentes)  
**Consideración:** Si tiene > 1000 filas o cambia frecuentemente, revisar con el equipo.

---

### PEDIDOS

**Estrategia:** Timestamp de creación + detección de cambios de estado  
**Cursor ideal:** `FECHA_PEDIDO` (creación) + `FECHA_MODIFICACION` (si existe)  
**Alternativa:** `NRO_PEDIDO` como secuencial si es autoincremental  
**Consideración:** Un pedido puede cambiar de estado luego de creado; el cursor debe
cubrir también modificaciones, no solo altas.

```sql
SELECT * FROM OWNER_RAFAM.PEDIDOS
WHERE FECHA_MODIFICACION > :ultimo_cursor
   OR (FECHA_MODIFICACION IS NULL AND FECHA_PEDIDO > :ultimo_cursor)
ORDER BY COALESCE(FECHA_MODIFICACION, FECHA_PEDIDO)
```

---

### PED_ITEMS

**Estrategia:** FK + secuencial interno  
**Cursor ideal:** Cursor del padre (`NRO_PEDIDO`) más seq. propio si existe  
**Alternativa:** Join con PEDIDOS y usar el timestamp del pedido padre  
**Consideración:** Los ítems generalmente no se modifican una vez creados; con sincronizar
los pedidos nuevos/modificados alcanza para traer sus ítems.

```sql
-- Traer ítems de pedidos modificados desde el último cursor
SELECT i.* FROM OWNER_RAFAM.PED_ITEMS i
JOIN OWNER_RAFAM.PEDIDOS p ON p.NRO_PEDIDO = i.NRO_PEDIDO
WHERE COALESCE(p.FECHA_MODIFICACION, p.FECHA_PEDIDO) > :ultimo_cursor
```

---

### SOLIC_GASTOS

**Estrategia:** Timestamp de alta  
**Cursor ideal:** `FECHA_ALTA` o campo de fecha propio de la solicitud  
**Consideración:** Confirmar si las solicitudes pueden modificarse luego de creadas.

---

### ORDEN_COMPRA

**Estrategia:** Timestamp de creación + cambios de estado  
**Cursor ideal:** `FECHA_OC` + `FECHA_MODIFICACION` (si existe)  
**Alternativa:** Número de OC como secuencial, complementado con re-sync de estados  
**Consideración:** Las OC pueden cambiar de estado (emitida → aprobada → ejecutada).
Evaluar con el DBA si hay trigger que actualiza `FECHA_MODIFICACION`.

---

### OC_ITEMS

**Estrategia:** Heredado de ORDEN_COMPRA (igual que PED_ITEMS con PEDIDOS)  
**Cursor ideal:** Join con ORDEN_COMPRA y usar el cursor de la OC padre  
**Consideración:** Confirmar si los ítems pueden modificarse (cambios de precio, cantidad).

---

### ORDEN_PAGO

**Estrategia:** Timestamp + cambio de estado crítico  
**Cursor ideal:** `FECHA_OP` (creación) + re-sync de registros con `ESTADO_OP = 'N'` (pendientes)  
**Consideración:** Una OP en estado `N` (no pagada) puede pasar a `C` (cancelada/pagada)
o `A` (anulada). El cursor de timestamp puede perder estos cambios si `FECHA_OP` no se
actualiza. Estrategia recomendada: **re-procesar siempre las OPs en estado N de los
últimos N días** como red de seguridad.

```sql
-- Nuevas OPs + OPs pendientes recientes (ventana de seguridad de 30 días)
SELECT * FROM OWNER_RAFAM.ORDEN_PAGO
WHERE FECHA_OP > :ultimo_cursor
   OR (ESTADO_OP = 'N' AND FECHA_OP > SYSDATE - 30)
ORDER BY FECHA_OP
```

---

## Patrón general recomendado

```python
# Pseudo-código del motor incremental
ultimo_cursor = db_local.get_last_cursor(tabla)

rows = oracle.query(f"""
    SELECT * FROM OWNER_RAFAM.{tabla}
    WHERE {campo_cursor} > :1
    ORDER BY {campo_cursor}
""", [ultimo_cursor])

for row in rows:
    paxapos_api.upsert(tabla, row)

nuevo_cursor = max(row[campo_cursor] for row in rows) if rows else ultimo_cursor
db_local.set_last_cursor(tabla, nuevo_cursor)
```

---

## Pendientes con el equipo RAFAM / DBA

- [ ] Confirmar existencia de `FECHA_MODIFICACION` en: PROVEEDORES, PEDIDOS, ORDEN_COMPRA
- [ ] Confirmar si `NRO_PEDIDO` y `NRO_OC` son secuenciales monotónicos
- [ ] Verificar si hay triggers de auditoría que actualicen timestamps
- [ ] Definir retención: ¿cuántos días atrás puede volver un estado a `N`?
- [ ] Acordar frecuencia de sincronización (ej: cada 15 min, cada hora)
