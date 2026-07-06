# Resumen de scripts y cron jobs

Fecha: 2026-07-06

## 1) Scripts que envian email

### Produccion
- main.py
  - Envia reporte de corrida y errores mediante src/notifier.py cuando NOTIFY_RUN_REPORT=true o ante fallos.
- scripts/check_integrity.py
  - Envia alertas de integridad mediante src/notifier.py si detecta anomalias.

### Desarrollo / pruebas
- scripts/simulate_report_emails.py
  - Simula correos en consola para validar formato (no uso productivo).
- TestWeek/run_migrate_report.sh
  - Script temporal de experimento con reporte por email para una ventana de prueba.

## 2) Cron jobs de produccion (actual)

### Fuente de verdad de horarios
- cron.conf

### Instalacion / mantenimiento
- scripts/install_crons.sh
  - Instala o actualiza crons del proyecto en el crontab del usuario.
  - Usa lock por entidad y lock de integridad para evitar solapamientos.

### Ejecucion por cron
- scripts/run_entity.sh <entidad>
  - Wrapper con flock por entidad.
  - Ejecuta main.py run --entity ...

### Entidades productivas programadas
- proveedores
- oc_items
- solic_gastos
- orden_pago
- retenciones
- check_integrity (diario)

## 3) Cron jobs de desarrollo / temporales

- TestWeek/run_migrate_report.sh --install-cron
- TestWeek/remove_cron.sh

Estos cron jobs estan orientados a una prueba acotada ("TestWeek") y no forman parte del esquema productivo estandar.

## 4) Scripts productivos recomendados (operacion diaria)

- main.py
- scripts/run_entity.sh
- scripts/install_crons.sh
- scripts/check_integrity.py
- scripts/load_csv_to_sqlite.py (solo para entorno dev local)

## 5) Scripts de desarrollo / analisis (no criticos para produccion)

- scripts/dump_full_schema.py
- scripts/explore_schema.py
- scripts/explore_oc_uni_med.py
- scripts/extract_cat_uni_med.py
- scripts/generate_rafam_context.py
- scripts/update_field_mapping.py
- scripts/export_2026.py
- scripts/export_by_oc_2026.py
- scripts/export_last_3_months.py
- scripts/trace_oc_flow_dev_rafam.py
- scripts/simulate_report_emails.py
- TestWeek/*

## 6) Simplificacion aplicada

Se redujo complejidad en cron.conf:
- Antes: OC, SG, OP y RET repetian variables de horario separadas.
- Ahora: se definio frecuencia comun con CORE_LABORAL y CORE_FUERA.
- scripts/install_crons.sh ahora soporta:
  - CORE_* como base para las 4 entidades operativas.
  - Overrides por entidad (OC_*, SG_*, OP_*, RET_*) cuando se necesite.

Resultado:
- Menos variables repetidas.
- Menos riesgo de desalinear horarios entre entidades hermanas.
- Misma compatibilidad operativa.
