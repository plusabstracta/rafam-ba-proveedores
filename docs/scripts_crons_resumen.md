# Resumen de scripts y cron jobs

Fecha: 2026-07-06

## 1) Scripts que envian email

### Produccion
- main.py (comando `daily-report`)
  - Envia UN unico mail resumen del dia (tiempo total y, si hubo errores, que entidad fallo y que devolvio el migrator) mediante src/notifier.py, y purga el historial reportado.
  - El comando `run` NO envia mail: registra cada corrida en state/run_history.jsonl.
- scripts/check_integrity.py
  - Envia alertas de integridad mediante src/notifier.py si detecta anomalias.

### Desarrollo / pruebas
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
- Pipeline completo cada 10 min (proveedores -> oc_items -> solic_gastos -> orden_pago -> retenciones), sin mail.
- daily-report (resumen diario por email, una vez al dia)
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
- TestWeek/*

## 6) Simplificacion aplicada

- Cron de produccion reducido a 3 entradas: pipeline (10 min, sin mail),
  resumen diario por email y check_integrity.
- El pipeline corre todas las entidades en un unico proceso, en orden de FK,
  y registra cada corrida en state/run_history.jsonl.
- El mail pasa de ser por corrida a UN unico resumen diario (main.py daily-report).
- Codigo legacy eliminado: notify_sync_error y notify_entity_detailed_report en
  src/notifier.py, la variable NOTIFY_RUN_REPORT y scripts/simulate_report_emails.py.
