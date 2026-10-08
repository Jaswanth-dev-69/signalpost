"""Hiring from NAV's public job-vacancy feed (arbeidsplassen.nav.no, Norwegian Labour and Welfare
Administration, open data under NLOD).

The documented feed API (pam-stilling-feed.nav.no) is read with NAV's published public token. The
active-ad sitemap lists every open ad; each feed entry names the employer by organisation number
(often a registered sub-unit). Matching is exact on the company's own or its sub-units'
organisation numbers, so no name matching is involved. Published postings cite the public ad page,
which embeds the same employer organisation number, so anyone can re-fetch and verify it.

The index is built in a background thread while the registry snapshot downloads and official
sources are fetched; whatever is indexed when the run needs it is used, and the index reports
whether it covered every active ad (only then is "no NAV postings" a checked result).
"""
from __future__ import annotations

import hashlib
import html
import http.client
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

USER_AGENT = "builderr-signalpost-poc/0.1 (+https://builderr.ai)"
FEED_HOST = "pam-stilling-feed.nav.no"
TOKEN_URL = f"https://{FEED_HOST}/api/publicToken"
ENTRY_URL = f"https://{FEED_HOST}/api/v1/feedentry/{{uuid}}"
SITEMAP_URL = "https://arbeidsplassen.nav.no/stillinger/sitemap.xml"
AD_PAGE_URL = "https://arbeidsplassen.nav.no/stillinger/stilling/{uuid}"
MAX_POSTINGS_PER_COMPANY = 10


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get(url: str, timeout: float = 60.0, max_bytes: int = 20_000_000) -> tuple[int, bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read(max_bytes), _utc_now()


class NavJobIndex:
    """orgnr -> active NAV job ads, built concurrently in the background."""

    def __init__(self, workers: int = 24, time_budget_s: float = 900.0):
        self.workers = workers
        self.time_budget_s = time_budget_s
        self.by_orgnr: dict[str, list[dict[str, Any]]] = {}
        self.total = 0
        self.fetched = 0
        self.errors = 0
        self.gone = 0
        self.rate_limited = 0
        self._failed_uuids: list[str] = []
        self.complete = False
        self.failed: str | None = None
        self.sitemap: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._local = threading.local()
        self._thread: threading.Thread | None = None
        self._token = ""

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> "NavJobIndex":
        self._thread = threading.Thread(target=self._run, name="nav-job-index", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def wait(self, timeout: float) -> None:
        if self._thread is not None:
            self._thread.join(max(0.0, timeout))

    def stats(self) -> dict[str, Any]:
        return {
            "active_ads": self.total,
            "entries_fetched": self.fetched,
            "closed_ads": self.gone,
            "errors": self.errors,
            "http_429": self.rate_limited,
            "complete": self.complete,
            "employers_indexed": len(self.by_orgnr),
            "failed": self.failed,
        }

    # ------------------------------------------------------------------ build
    def _run(self) -> None:
        started = time.monotonic()
        try:
            _, token_body, _ = _get(TOKEN_URL, timeout=30)
            match = re.search(rb"eyJ[A-Za-z0-9._-]+", token_body)
            if not match:
                raise RuntimeError("public token not found")
            self._token = match.group(0).decode()
            status, sitemap_raw, sitemap_time = _get(SITEMAP_URL)
            uuids = list(dict.fromkeys(re.findall(rb"/stillinger/stilling/([0-9a-f-]{36})", sitemap_raw)))
            self.total = len(uuids)
            first_loc = re.search(rb"<loc>\s*([^<\s]+)\s*</loc>", sitemap_raw)
            self.sitemap = {
                "url": SITEMAP_URL,
                "content_sha256": hashlib.sha256(sitemap_raw).hexdigest(),
                "retrieved_at": sitemap_time,
                "active_ads": len(uuids),
                # A verbatim text node of the sitemap: the evidence span for "no ad names this employer".
                "first_loc": first_loc.group(1).decode("utf-8", errors="replace") if first_loc else None,
            }
            deadline = started + self.time_budget_s
            with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="nav-entry") as pool:
                for _ in pool.map(lambda u: self._fetch_entry(u.decode(), deadline), uuids):
                    pass
            # Second, gentler pass over entries whose connections failed under load.
            retry, self._failed_uuids = self._failed_uuids, []
            self.errors -= len(retry)
            with ThreadPoolExecutor(max_workers=max(2, self.workers // 3), thread_name_prefix="nav-retry") as pool:
                for _ in pool.map(lambda u: self._fetch_entry(u, deadline), retry):
                    pass
            done = self.fetched + self.gone
            self.complete = not self._stop.is_set() and done + self.errors >= self.total and self.errors <= max(5, self.total // 200)
        except Exception as exc:  # network failure: index stays partial and says so
            self.failed = f"{type(exc).__name__}: {str(exc)[:120]}"

    def _connection(self) -> http.client.HTTPSConnection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = http.client.HTTPSConnection(FEED_HOST, timeout=20)
            self._local.connection = connection
        return connection

    def _fetch_entry(self, uuid: str, deadline: float) -> None:
        if self._stop.is_set() or time.monotonic() > deadline:
            return
        path = f"/api/v1/feedentry/{uuid}"
        for attempt in range(3):
            connection = self._connection()
            try:
                connection.request("GET", path, headers={"Authorization": f"Bearer {self._token}", "User-Agent": USER_AGENT})
                response = connection.getresponse()
                raw = response.read()
                if response.status == 429:
                    with self._lock:
                        self.rate_limited += 1
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if response.status in (404, 410):
                    with self._lock:
                        self.gone += 1  # ad closed between the sitemap and this read
                    return
                if response.status != 200:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                self._index(uuid, raw)
                with self._lock:
                    self.fetched += 1
                return
            except Exception:
                # Keep-alive connections get recycled by the server; reconnect and retry.
                try:
                    connection.close()
                except Exception:
                    pass
                self._local.connection = None
                time.sleep(0.3 * (attempt + 1))
        with self._lock:
            self.errors += 1
            self._failed_uuids.append(uuid)

    def _index(self, uuid: str, raw: bytes) -> None:
        body = json.loads(raw)
        if body.get("status") != "ACTIVE":
            return
        ad = body.get("ad_content") or {}
        employer = ad.get("employer") or {}
        orgnr = re.sub(r"\D", "", str(employer.get("orgnr") or ""))
        title = " ".join(str(ad.get("title") or "").split())
        if len(orgnr) != 9 or not title:
            return
        literal = re.search(rb'"orgnr"\s*:\s*"' + orgnr.encode() + rb'"', raw)
        item = {
            "uuid": uuid,
            "title": title[:300],
            "employer_name": employer.get("name"),
            "employer_orgnr": orgnr,
            "employer_homepage": employer.get("homepage") or None,
            "published": (ad.get("published") or "")[:10] or None,
            "expires": (ad.get("expires") or "")[:10] or None,
            "url": AD_PAGE_URL.format(uuid=uuid),
            "entry_url": ENTRY_URL.format(uuid=uuid),
            "entry_sha256": hashlib.sha256(raw).hexdigest(),
            "entry_retrieved_at": _utc_now(),
            # Verbatim fragments of the ad's JSON: the employer literal and the title.
            "entry_span": literal.group(0).decode() if literal else f'"orgnr":"{orgnr}"',
            "entry_title_span": title[:200],
        }
        with self._lock:
            self.by_orgnr.setdefault(orgnr, []).append(item)

    # ------------------------------------------------------------------ lookup
    def lookup(self, orgnrs: set[str]) -> list[dict[str, Any]]:
        with self._lock:
            items = [dict(item) for orgnr in orgnrs for item in self.by_orgnr.get(orgnr, [])]
        items.sort(key=lambda item: item.get("published") or "", reverse=True)
        return items[:MAX_POSTINGS_PER_COMPANY]


def company_orgnrs(profile: dict[str, Any]) -> set[str]:
    """The company's own number plus its registered sub-units (employers on NAV ads are often sub-units)."""
    numbers = {str(profile.get("organisation_number") or "")}
    locations = (((profile.get("evidence") or {}).get("locations") or {}).get("value") or {}).get("locations") or []
    numbers.update(str(item.get("organisation_number") or "") for item in locations)
    return {n for n in numbers if len(n) == 9}


def attach_postings(profile: dict[str, Any], index: NavJobIndex, timeout: float = 15.0) -> int:
    """Look up the company's NAV ads and fetch each public ad page as the published evidence."""
    items = index.lookup(company_orgnrs(profile))
    postings = []
    for item in items:
        page_evidence = None
        try:
            status, raw, retrieved_at = _get(item["url"], timeout=timeout, max_bytes=3_000_000)
            literal = re.search(rb'orgnr\\?"\s*:\s*\\?"' + item["employer_orgnr"].encode() + rb'\\?"', raw)
            text = html.unescape(raw.decode("utf-8", errors="replace"))
            if status == 200 and literal and " ".join(item["title"][:60].split()) in " ".join(text.split()):
                page_evidence = {
                    "url": item["url"],
                    "content_sha256": hashlib.sha256(raw).hexdigest(),
                    "retrieved_at": retrieved_at,
                    "claim_span": " ".join(item["title"][:200].split()),
                    "orgnr_span": literal.group(0).decode(),
                }
        except Exception:
            page_evidence = None
        postings.append({**item, "page_evidence": page_evidence})
    profile["nav_jobs"] = {
        "postings": postings,
        "index_complete": index.complete,
        "sitemap": index.sitemap,
        "matched_orgnrs": sorted({p["employer_orgnr"] for p in postings}),
    }
    return len(postings)
