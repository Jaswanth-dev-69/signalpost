from __future__ import annotations

import hashlib
import http.client
import json
import threading
import urllib.parse
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


RATE_LIMITED = {"count": 0}


@dataclass
class FetchResult:
    url: str
    status: int
    elapsed_ms: int
    bytes_received: int
    body: Any = None
    error: str | None = None
    content_sha256: str | None = None
    retrieved_at: str | None = None
    effective_at: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_local = threading.local()
USER_AGENT = "builderr-signalpost-poc/0.1 (+https://builderr.ai)"


def _connection(host: str, timeout: float) -> http.client.HTTPSConnection:
    pool = getattr(_local, "connections", None)
    if pool is None:
        pool = _local.connections = {}
    connection = pool.get(host)
    if connection is None:
        connection = pool[host] = http.client.HTTPSConnection(host, timeout=timeout)
    return connection


def _drop_connection(host: str) -> None:
    connection = (getattr(_local, "connections", None) or {}).pop(host, None)
    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass


def fetch_json(url: str, *, timeout: float = 20.0, attempts: int = 3) -> FetchResult:
    """GET a JSON API over a per-thread keep-alive connection (3x lower latency than a new TLS
    session per request on data.brreg.no). 404/410 bodies are kept and hashed as evidence."""
    parsed = urllib.parse.urlsplit(url)
    host = parsed.netloc
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    last_error = "request failed"
    for attempt in range(attempts):
        started = time.monotonic()
        try:
            connection = _connection(host, timeout)
            connection.request("GET", path, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
            response = connection.getresponse()
            raw = response.read()
            elapsed = int((time.monotonic() - started) * 1000)
            if response.status == 200:
                return FetchResult(url, 200, elapsed, len(raw), json.loads(raw), content_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=_utc_now())
            if response.status in {404, 410}:
                try:
                    body = json.loads(raw) if raw else None
                except ValueError:
                    body = None
                return FetchResult(url, response.status, elapsed, len(raw), body, error=f"HTTP {response.status}", content_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=_utc_now())
            last_error = f"HTTP {response.status}"
            if response.status == 429:
                RATE_LIMITED["count"] += 1
            if response.status == 429 or response.status >= 500:
                retry_after = response.getheader("Retry-After")
                time.sleep(min(10.0, float(retry_after)) if retry_after and retry_after.isdigit() else 1.5 * (attempt + 1))
            elif 300 <= response.status < 400:
                _drop_connection(host)
                return _fetch_json_urllib(url, timeout=timeout, attempts=attempts)
        except (http.client.HTTPException, OSError, json.JSONDecodeError) as exc:
            last_error = type(exc).__name__
            _drop_connection(host)
        if attempt + 1 < attempts:
            time.sleep(0.4 * (2**attempt))
    return FetchResult(url, 0, 0, 0, error=last_error, retrieved_at=_utc_now())


def _fetch_json_urllib(url: str, *, timeout: float = 20.0, attempts: int = 3) -> FetchResult:
    last_error = "request failed"
    for attempt in range(attempts):
        started = time.monotonic()
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "builderr-signalpost-poc/0.1 (+https://builderr.ai)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                elapsed = int((time.monotonic() - started) * 1000)
                return FetchResult(url, response.status, elapsed, len(raw), json.loads(raw), content_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=_utc_now())
        except urllib.error.HTTPError as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            raw = exc.read()
            if exc.code in {404, 410}:
                try:
                    body = json.loads(raw) if raw else None
                except ValueError:
                    body = None
                return FetchResult(url, exc.code, elapsed, len(raw), body, error=f"HTTP {exc.code}", content_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=_utc_now())
            last_error = f"HTTP {exc.code}"
            if exc.code == 429:
                RATE_LIMITED["count"] += 1
            if exc.code == 429 or exc.code >= 500:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                time.sleep(min(10.0, float(retry_after)) if retry_after and retry_after.isdigit() else 1.5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = type(exc).__name__
        if attempt + 1 < attempts:
            time.sleep(0.4 * (2**attempt))
    return FetchResult(url, 0, 0, 0, error=last_error, retrieved_at=_utc_now())
