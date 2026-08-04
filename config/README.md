# config/README.md — Carpeta de configuración del pipeline RAFAM

Esta carpeta contiene las plantillas de configuración para los distintos
componentes del pipeline RAFAM → Paxapos.

## Configuración de notificaciones

Las variables `NOTIFY_*` viven en el `.env` del proyecto (plantilla:
`.env.example`, sección NOTIFICACIONES). No hay un archivo de env separado
en esta carpeta.

**Setup:**
1. Completar la sección `NOTIFY_*` del `.env` del proyecto
2. Reemplazar usuario y contraseña SMTP con credenciales reales
3. Completar `NOTIFY_TO` con los destinatarios de las alertas

## Variables de entorno de notificaciones

| Variable | Descripción | Ejemplo |
|---|---|---|
| `NOTIFY_ENABLED` | Habilitar/deshabilitar alertas | `true` |
| `NOTIFY_SMTP_HOST` | Servidor SMTP | `neon.gnucleo.net` |
| `NOTIFY_SMTP_PORT` | Puerto SMTP (465=SSL, 587=STARTTLS) | `465` |
| `NOTIFY_SMTP_USER` | Usuario de autenticación | `usuario@gnucleo.net` |
| `NOTIFY_SMTP_PASSWORD` | Contraseña SMTP | `mi_clave` |
| `NOTIFY_FROM` | Dirección remitente | `rafam@gnucleo.net` |
| `NOTIFY_TO` | Destinatarios (separados por coma) | `admin@org.com` |
| `NOTIFY_SUBJECT_PREFIX` | Prefijo del asunto | `[RAFAM]` |
| `NOTIFY_SMTP_TIMEOUT` | Timeout de conexión en segundos | `15` |

## Cuándo se envía email

El script `check_integrity.py` envía un email automáticamente cuando detecta:

- **⚡ Proveedores modificados**: diferencia de hash entre RAFAM y lo sincronizado
- **⚡ Registros anulados**: estado anulado en RAFAM no reflejado en Paxapos  
- **⚠ Errores**: fallos durante el reenvío a Paxapos (ej: CUIT inválido)

En modo `--dry-run`: se notifica sin aplicar cambios (para alertar del estado).  
En modo `--apply`: se notifica con el resultado de las correcciones aplicadas.

Si no hay anomalías, **no se envía email** (sin ruido innecesario).
