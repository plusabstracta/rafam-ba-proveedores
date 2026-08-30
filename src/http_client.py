"""http_client.py â Cliente HTTP para la API Paxapos (migrator).

Encapsula toda la lÃ³gica de transporte HTTP:
  - AutenticaciÃ³n (X-Api-Key, X-Tenant-Id)
  - Retry con backoff exponencial + jitter
  - SSL context (configurable vÃ­a PAXAPOS_VERIFY_SSL)
  - ConstrucciÃ³n de URLs con tenant
  - POST JSON + GET JSON
  - Dump/redacciÃ³n de payloads para debugging

Usa exclusivamente urllib (cero dependencias externas).
"""

from __future__ import annotations

import json
import logging
import os
import random
import ssl
import time
from typing import Any
from urllib import error, parse, request

from . import auth_circuit_breaker
from .utils import env_verify_ssl, redact_payload_for_dump

logger = logging.getLogger(__name__)


class _NoRedirectHandler(request.HTTPRedirectHandler):
    """Convierte cualquier redirect (3xx) en HTTPError.

    El handler por defecto de urllib sigue redirects convirtiendo POST en GET
    sin body y reenviando TODOS los headers (incluida X-Api-Key) al Location,
    aunque sea otro host. Para un import de datos eso significa: credencial
    filtrada + un GET 200 que el caller interpreta como "batch importado" y
    avanza el checkpoint sin haber migrado nada. Preferimos fallar ruidoso.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        raise error.HTTPError(
            req.full_url,
            code,
            f"Redirect a {newurl} bloqueado: revisar PAXAPOS_URL (esquema/slash final)",
            headers,
            fp,
        )

# Errores HTTP transitorios que vale la pena reintentar.
RETRYABLE_HTTP_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

# User-Agent constante para todas las llamadas del migrator.
_USER_AGENT = "rafam-sync/1.0"


def build_auth_headers(
    *,
    api_key: str | None,
    tenant: str,
    content_type: str | None = None,
) -> dict[str, str]:
    """Headers comunes para TODAS las llamadas HTTP al migrator Paxapos.

    Unico lugar que decide que headers de auth lleva un request. Antes de
    paxapos#361, `exporter._fetch_migrator_json` (spec/lookups/resolver_*)
    reconstruia este dict a mano por su cuenta, separado de
    `PaxaposHttpClient._build_headers` (import). Esa duplicacion es
    exactamente el tipo de gap que deja una llamada mandando (o no) el header
    segun quien la haya escrito ese dia — cualquier nuevo call-site DEBE pasar
    por esta funcion en vez de armar su propio dict.
    """
    headers = {
        "Accept": "application/json",
        "X-Tenant-Id": tenant,
        "User-Agent": _USER_AGENT,
    }
    if api_key:
        headers["X-Api-Key"] = api_key
    if content_type:
        headers["Content-Type"] = content_type
    return headers


class PaxaposHttpClient:
    """Cliente HTTP para la API Paxapos.

    Encapsula autenticaciÃ³n, retries, SSL, dump, y construcciÃ³n de URLs.
    Desacoplado del dominio â no conoce entidades, payloads, ni mappers.

    Uso:
        client = PaxaposHttpClient()
        parsed = client.post_json("rafam/migracion/importar.json", payload)
        spec = client.get_json("rafam/migracion/spec.json")
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        tenant: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        verify_ssl: bool | None = None,
        max_retries: int = 3,
        base_backoff: float = 0.5,
    ):
        # Resolver desde env si no se pasa explÃ­citamente.
        self._base_url = (base_url or _env_paxapos_url()).rstrip("/")
        self._tenant = (tenant or _env_paxapos_tenant()).strip("/")
        self._api_key = api_key or os.getenv("PAXAPOS_API_KEY", "").strip()
        if not self._api_key:
            raise ValueError("Falta PAXAPOS_API_KEY en .env")

        self._timeout = timeout if timeout is not None else _env_timeout_seconds()
        self._verify_ssl = verify_ssl if verify_ssl is not None else env_verify_ssl()
        self._max_retries = max_retries
        self._base_backoff = base_backoff

        if not self._verify_ssl:
            logger.warning(
                "PaxaposHttpClient: SSL certificate verification deshabilitada (PAXAPOS_VERIFY_SSL=false)"
            )

    # ââ Propiedades de solo lectura ââââââââââââââââââââââââââââââââââââââ

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def tenant(self) -> str:
        return self._tenant

    @property
    def import_url(self) -> str:
        """URL completa del endpoint de importaciÃ³n."""
        endpoint = _resolve_endpoint("PAXAPOS_RAFAM_IMPORT_PATH", "rafam/migracion/importar.json")
        return build_url(self._base_url, self._tenant, endpoint)

    # ââ MÃ©todos pÃºblicos âââââââââââââââââââââââââââââââââââââââââââââââââ

    def post_json(self, endpoint_or_url: str, payload: dict) -> dict:
        """POST JSON al endpoint dado. Devuelve el body parseado como dict.

        Args:
            endpoint_or_url: Path relativo (e.g. "rafam/migracion/importar.json")
                            o URL absoluta pre-construida.
            payload: Dict que se serializa a JSON.

        Returns:
            Dict parseado de la respuesta JSON.

        Raises:
            RuntimeError: En HTTP errors, respuesta no-JSON, o timeouts.
        """
        if endpoint_or_url.startswith("http://") or endpoint_or_url.startswith("https://"):
            url = endpoint_or_url
        else:
            url = build_url(self._base_url, self._tenant, endpoint_or_url)

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        _dump_request(url, payload)

        headers = self._build_headers(content_type="application/json")
        req = request.Request(url=url, data=data, headers=headers, method="POST")

        parsed = self._execute_json_request(req)
        _dump_response(url, parsed)
        return parsed

    def get_json(
        self,
        endpoint: str,
        *,
        query_params: dict[str, str] | None = None,
    ) -> dict:
        """GET JSON desde el endpoint dado. Devuelve el body parseado como dict.

        Args:
            endpoint: Path relativo (e.g. "rafam/migracion/lookups.json").
            query_params: Query string params opcionales.

        Returns:
            Dict parseado de la respuesta JSON.
        """
        url = build_url(self._base_url, self._tenant, endpoint)
        if query_params:
            url = f"{url}?{parse.urlencode(query_params)}"

        headers = self._build_headers()
        req = request.Request(url=url, headers=headers, method="GET")
        return self._execute_json_request(req)

    # ââ Internals ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

    def _build_headers(self, *, content_type: str | None = None) -> dict[str, str]:
        """Construye headers comunes para todas las llamadas (ver build_auth_headers)."""
        return build_auth_headers(
            api_key=self._api_key, tenant=self._tenant, content_type=content_type
        )

    def _ssl_context(self):
        """Devuelve SSL context si verify_ssl=false, None si es normal."""
        if not self._verify_ssl:
            return ssl._create_unverified_context()
        return None

    def _execute_json_request(self, req: request.Request) -> dict:
        """Ejecuta request con retries, valida content-type, parsea JSON.

        Antes de tocar la red, chequea el circuit breaker de auth (paxapos#361):
        si venimos de fallar 401/403 hace poco, corta acá sin emitir el
        request — un reintento no arregla una api_key mala.
        """
        auth_circuit_breaker.check(context=req.full_url)
        try:
            with http_request_with_retries(
                req,
                timeout=self._timeout,
                ssl_context=self._ssl_context(),
                max_attempts=self._max_retries,
                base_backoff=self._base_backoff,
            ) as resp:
                status = resp.getcode()
                final_url = resp.geturl()
                content_type = (resp.headers.get("Content-Type") or "").lower()
                body = resp.read().decode("utf-8", errors="replace")

                logger.debug(
                    "HTTP response status=%s content_type=%s final_url=%s",
                    status, content_type, final_url,
                )

                if status < 200 or status >= 300:
                    raise RuntimeError(f"HTTP {status}: {body[:500]}")

                if "json" not in content_type:
                    raise RuntimeError(f"Respuesta no JSON (Content-Type={content_type})")

                auth_circuit_breaker.record_success()
                return json.loads(body) if body else {}

        except error.HTTPError as exc:
            auth_circuit_breaker.record_failure(exc.code, context=req.full_url)
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"URL error: {exc.reason}") from exc


# ââ Retry engine (standalone function, testeable sin instanciar client) ââ

def _open_request(
    req: request.Request,
    *,
    timeout: float,
    ssl_context: ssl.SSLContext | None = None,
):
    """Abre el request con un opener que NO sigue redirects (seam de tests)."""
    handlers: list = [_NoRedirectHandler()]
    if ssl_context is not None:
        handlers.append(request.HTTPSHandler(context=ssl_context))
    opener = request.build_opener(*handlers)
    return opener.open(req, timeout=timeout)


def http_request_with_retries(
    req: request.Request,
    *,
    timeout: float,
    ssl_context: ssl.SSLContext | None = None,
    max_attempts: int = 3,
    base_backoff: float = 0.5,
) -> Any:
    """Ejecuta urlopen con retries acotados ante errores transitorios.

    Reintenta URLError (red caÃ­da, DNS), TimeoutError y HTTPError con status en
    `RETRYABLE_HTTP_STATUS`. Errores 4xx normales (validaciÃ³n, auth) NO se
    reintentan â falla rÃ¡pido para que el caller actÃºe.

    Usa backoff exponencial con jitter aleatorio para evitar thundering herd
    si varios cron salen al mismo tiempo. Devuelve el response object abierto;
    el caller debe usarlo dentro de `with`.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return _open_request(req, timeout=timeout, ssl_context=ssl_context)
        except error.HTTPError as exc:
            # Solo reintentamos status transitorios. 4xx no transitorios suben directo.
            if exc.code not in RETRYABLE_HTTP_STATUS or attempt == max_attempts:
                raise
            last_exc = exc
        except error.URLError as exc:
            if attempt == max_attempts:
                raise
            last_exc = exc
        except TimeoutError as exc:
            if attempt == max_attempts:
                raise
            last_exc = exc

        backoff = base_backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
        logger.warning(
            "HTTP retry %d/%d a %s tras error transitorio: %s (backoff %.2fs)",
            attempt, max_attempts - 1, req.full_url, last_exc, backoff,
        )
        time.sleep(backoff)
    # Defensa: nunca se alcanza, pero si llega significa que loop saliÃ³ sin raise.
    raise RuntimeError("HTTP retries agotados sin excepcion observable") from last_exc


# ââ URL helpers ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def build_url(base_url: str, tenant: str, endpoint: str) -> str:
    """Construye URL completa: base/tenant/endpoint o devuelve URL absoluta."""
    endpoint = endpoint.strip()
    parsed = parse.urlparse(endpoint)
    if parsed.scheme and parsed.netloc:
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("endpoint absoluto debe usar http o https")
        return endpoint
    return f"{base_url.rstrip('/')}/{tenant.strip('/')}/{endpoint.strip('/')}"


def resolve_endpoint(endpoint_env: str, default_endpoint: str) -> str:
    """Alias pÃºblico de _resolve_endpoint para uso externo."""
    return _resolve_endpoint(endpoint_env, default_endpoint)


def _resolve_endpoint(endpoint_env: str, default_endpoint: str) -> str:
    """Lee endpoint de env o usa default. Acepta path relativo o URL absoluta."""
    endpoint = os.getenv(endpoint_env, default_endpoint).strip()
    parsed = parse.urlparse(endpoint)
    if parsed.scheme and parsed.netloc:
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"{endpoint_env} debe usar URL absoluta http(s)")
        return endpoint
    if parsed.scheme or parsed.netloc:
        raise ValueError(f"{endpoint_env} debe ser un path relativo o una URL absoluta http(s) valida")
    endpoint = endpoint.strip("/")
    if not endpoint:
        raise ValueError(f"{endpoint_env} no puede estar vacÃ­o")
    return endpoint


# ââ Env helpers ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _env_timeout_seconds() -> int:
    """PAXAPOS_TIMEOUT_SECONDS tolerante: acepta enteros o floats, y ante un
    valor invalido usa el default con warning en vez de reventar el arranque."""
    raw = os.getenv("PAXAPOS_TIMEOUT_SECONDS", "20").strip()
    try:
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        logger.warning("PAXAPOS_TIMEOUT_SECONDS=%r invalido; usando 20s", raw)
        return 20


def _env_paxapos_url() -> str:
    base_url = os.getenv("PAXAPOS_URL", "").strip().rstrip("/")
    if not base_url:
        raise ValueError("Falta PAXAPOS_URL en .env para destino Paxapos")
    if base_url.startswith("http://"):
        logger.warning(
            "PAXAPOS_URL usa http:// (sin TLS): la API key viaja en texto plano. "
            "Usar https:// en produccion."
        )
    return base_url


def _env_paxapos_tenant() -> str:
    tenant = os.getenv("PAXAPOS_TENANT", "").strip().strip("/")
    if not tenant:
        raise ValueError("Falta PAXAPOS_TENANT en .env para destino Paxapos")
    return tenant


# ââ Dump helpers âââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def _dump_payload_path() -> str | None:
    """Devuelve path de DUMP_PAYLOAD si estÃ¡ habilitado y APP_ENV no es 'prod'."""
    path = os.environ.get("DUMP_PAYLOAD")
    if not path:
        return None
    app_env = os.environ.get("APP_ENV", "").strip().lower()
    if app_env == "prod" and os.environ.get("DUMP_PAYLOAD_FORCE", "").strip() != "1":
        logger.warning(
            "DUMP_PAYLOAD ignorado en APP_ENV=prod. Setear DUMP_PAYLOAD_FORCE=1 para forzar."
        )
        return None
    return path


def _dump_request(url: str, payload: dict) -> None:
    """Escribe el payload de request al dump file (si habilitado)."""
    dump_path = _dump_payload_path()
    if not dump_path:
        return
    try:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        redacted = redact_payload_for_dump(serialized)
        with open(dump_path, "ab") as fh:
            fh.write(f"\n=== POST {url} ===\n".encode("utf-8"))
            fh.write(redacted.encode("utf-8"))
            fh.write(b"\n")
    except OSError:
        pass


def _dump_response(url: str, parsed: dict) -> None:
    """Escribe la respuesta al dump file (si habilitado)."""
    dump_path = _dump_payload_path()
    if not dump_path:
        return
    try:
        serialized = json.dumps(parsed, ensure_ascii=False, indent=2)
        redacted = redact_payload_for_dump(serialized)
        with open(dump_path, "ab") as fh:
            fh.write(b"--- RESPONSE ---\n")
            fh.write(redacted.encode("utf-8"))
            fh.write(b"\n")
    except OSError:
        pass
