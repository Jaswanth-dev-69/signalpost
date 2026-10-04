from __future__ import annotations

import json
import ipaddress
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup
import extruct
import tldextract
import trafilatura

from .evidence import evidence

USER_AGENT = "builderr-signalpost-poc/0.1 (+https://builderr.ai)"
SOCIAL_HOSTS = {
    "linkedin.com": "linkedin",
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "x.com": "x",
    "twitter.com": "x",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "tiktok.com": "tiktok",
}
PRIORITY_TERMS = (
    "om-oss", "om_oss", "about", "kontakt", "contact", "ledelse", "management",
    "team", "people", "locations", "lokasjoner", "avdelinger", "butikker",
    "news", "press", "aktuelt", "nyheter", "blog", "blogg", "presse",
    "ledige-stillinger", "stillinger", "karriere", "career", "careers",
    "jobb", "jobs", "rekruttering", "bli-med", "work-with-us",
)

NEWS_TERMS = ("aktuelt", "nyheter", "nyhet", "news", "blog", "blogg", "presse", "siste-nytt", "artikler")
JOB_TERMS = ("ledige-stillinger", "stillinger", "karriere", "career", "careers", "jobb", "jobs", "rekruttering", "bli-med", "work-with-us")
JOB_PLATFORM_HOSTS = {"finn.no", "webcruiter.no", "webcruiter.com", "easycruit.com", "teamtailor.com", "recman.no"}
NORWEGIAN_MONTHS = {
    "januar": "01", "februar": "02", "mars": "03", "april": "04", "mai": "05", "juni": "06",
    "juli": "07", "august": "08", "september": "09", "oktober": "10", "november": "11", "desember": "12",
}
DATE_PATTERN = re.compile(
    r"\b(?:20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]20\d{2}|"
    r"\d{1,2}\.\s*(?:januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember)\s+20\d{2})\b",
    re.IGNORECASE,
)


def assert_public_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("Only public HTTP(S) URLs are allowed")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("Local hosts are blocked")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("Hostname did not resolve") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("Private, loopback, link-local, multicast, and reserved addresses are blocked")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        assert_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


SAFE_OPENER = urllib.request.build_opener(SafeRedirectHandler())


def normalize_homepage(value: str | None) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))


def _registered_domain(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    ext = tldextract.extract(parsed.hostname or "")
    return ext.top_domain_under_public_suffix


def _robots_allowed(url: str, timeout: float) -> bool:
    assert_public_url(url)
    from .webclaims import robots_allowed

    return robots_allowed(url, timeout)


CREDIT_CONTEXT = re.compile(r"levert av|utviklet av|laget av|design(et)? av|nettside(r)? (av|fra)|webdesign|powered by|made by|built by|byr[aå]", re.I)


def _social_links_raw(base_url: str, soup: BeautifulSoup) -> list[dict[str, str]]:
    """Social profile links with the raw href as it appears on the page."""
    found: dict[tuple[str, str], dict[str, str]] = {}
    nodes = [(node, "href") for node in soup.select("a[href]")]
    nodes.extend((node, "data-href") for node in soup.select("[data-href]"))
    nodes.extend((node, "src") for node in soup.select("iframe[src]"))
    nodes.extend((node, "href") for node in soup.select('link[rel~="me"][href]'))
    nodes.extend((node, "content") for node in soup.select('meta[property="og:see_also"][content]'))
    for node, attribute in nodes:
        candidate = str(node.get(attribute) or "").strip()
        url = urllib.parse.urljoin(base_url, candidate)
        parsed_candidate = urllib.parse.urlparse(url)
        if (parsed_candidate.hostname or "").casefold().removeprefix("www.") == "facebook.com" and parsed_candidate.path.startswith("/plugins/"):
            embedded = urllib.parse.parse_qs(parsed_candidate.query).get("href", [])
            if embedded:
                url = embedded[0]
        normalized = normalize_social_url(url)
        if not normalized:
            continue
        # Skip web-agency / supplier credits ("Nettside levert av ...").
        context = node.parent.get_text(" ", strip=True)[:200] if node.parent is not None else ""
        if CREDIT_CONTEXT.search(context) or CREDIT_CONTEXT.search(node.get_text(" ", strip=True)):
            continue
        found.setdefault((normalized["platform"], normalized["url"]), {**normalized, "href": candidate[:300]})
    return sorted(found.values(), key=lambda item: (item["platform"], item["url"]))


def _social_links(base_url: str, soup: BeautifulSoup) -> list[dict[str, str]]:
    return [{"platform": item["platform"], "url": item["url"]} for item in _social_links_raw(base_url, soup)]


def structured_social_links(value: Any) -> list[dict[str, str]]:
    found: dict[tuple[str, str], dict[str, str]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            same_as = node.get("sameAs")
            urls = same_as if isinstance(same_as, list) else [same_as]
            for raw in urls:
                if not isinstance(raw, str):
                    continue
                normalized = normalize_social_url(raw.strip())
                if normalized:
                    found[(normalized["platform"], normalized["url"])] = normalized
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return sorted(found.values(), key=lambda item: (item["platform"], item["url"]))


def strip_private_fields(record: dict[str, Any] | None) -> None:
    """Drop in-memory page bytes before a website record is serialized."""
    value = (record or {}).get("value")
    if isinstance(value, dict):
        value.pop("_homepage", None)
        value.pop("_subpages", None)


def normalize_social_url(url: str) -> dict[str, str] | None:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")
    platform = next((label for domain, label in SOCIAL_HOSTS.items() if host == domain or host.endswith("." + domain)), None)
    if not platform:
        return None
    parts = [part.strip() for part in parsed.path.split("/") if part.strip()]
    lowered = [part.casefold() for part in parts]
    if platform == "facebook" and lowered[:1] in (["pg"], ["people"]) and len(parts) > 1:
        parts, lowered = parts[1:], lowered[1:]
    rejected_first = {
        "facebook": {
            "sharer", "sharer.php", "share.php", "share", "dialog", "policy.php", "privacy", "events", "groups",
            "plugins", "login", "login.php", "watch", "marketplace", "help", "hashtag", "business", "home.php",
            "l.php", "tr", "facebook", "permalink.php", "photo.php", "story.php", "media", "notes",
        },
        "instagram": {"p", "reel", "reels", "stories", "explore", "accounts", "instagram", "tv"},
        "x": {"intent", "share", "home", "search", "i", "hashtag", "login", "twitter", "x", "settings"},
        "linkedin": set(),
        "tiktok": set(),
    }
    if not parts or lowered[0] in rejected_first.get(platform, set()):
        return None
    if platform == "facebook" and lowered[0] == "profile.php":
        return None
    if platform == "linkedin" and (lowered[0] != "company" or len(parts) < 2):
        return None
    if platform == "youtube" and lowered[0] not in {"channel", "user", "c"} and not parts[0].startswith("@"):
        return None
    if host == "youtu.be":
        return None
    if platform == "tiktok" and not parts[0].startswith("@"):
        return None
    if platform == "x" and len(parts) != 1:
        return None
    canonical_host = {
        "linkedin": "linkedin.com",
        "facebook": "facebook.com",
        "instagram": "instagram.com",
        "x": "x.com",
        "youtube": "youtube.com",
        "tiktok": "tiktok.com",
    }[platform]
    if platform == "linkedin":
        parts = parts[:2]
    elif platform == "facebook":
        parts = parts[:3] if lowered[0] == "pages" else parts[:1]
    elif platform in {"instagram", "tiktok"}:
        parts = parts[:1]
    elif platform == "youtube":
        parts = parts[:1] if parts[0].startswith("@") else parts[:2]
    return {"platform": platform, "url": f"https://{canonical_host}/{'/'.join(parts)}"}


def _priority_links(base_url: str, soup: BeautifulSoup, limit: int = 4, include_common_paths: bool = False) -> list[str]:
    base = urllib.parse.urlparse(base_url)
    candidates: dict[str, int] = {}
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        url = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != base.netloc.lower():
            continue
        haystack = (parsed.path + " " + anchor.get_text(" ", strip=True)).casefold()
        rank = next((index for index, term in enumerate(PRIORITY_TERMS) if term in haystack), None)
        if rank is None:
            continue
        clean = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))
        if clean.rstrip("/") == base_url.rstrip("/"):
            continue
        candidates[clean] = min(rank, candidates.get(clean, rank))
    if include_common_paths:
        common_paths = (
            "/aktuelt", "/nyheter", "/nyhet", "/news", "/blogg", "/blog", "/presse",
            "/siste-nytt", "/artikler", "/ledige-stillinger", "/stillinger", "/karriere",
            "/jobb", "/jobs", "/careers", "/rekruttering", "/bli-med",
        )
        for index, path in enumerate(common_paths, start=len(PRIORITY_TERMS)):
            clean = urllib.parse.urljoin(base_url, path)
            candidates.setdefault(clean, index)
    return [url for url, _ in sorted(candidates.items(), key=lambda item: (item[1], item[0]))[:limit]]


IDENTITY_PAGE_LIMIT = 4
IDENTITY_TERMS = (
    "kontakt", "contact",
    "om-oss", "om_oss", "omoss", "about",
    "personvern", "privacy", "firma", "selskapet",
    "vilkar", "vilkår", "betingelser", "terms", "impressum", "imprint",
)
IDENTITY_GROUPS = (2, 6, 10, len(IDENTITY_TERMS))  # contact | about | privacy/company | terms/impressum


def _identity_links(base_url: str, soup: BeautifulSoup, limit: int = IDENTITY_PAGE_LIMIT) -> list[str]:
    base_domain = _registered_domain(base_url)
    ranked: dict[str, int] = {}
    for anchor in soup.select("a[href]"):
        url = urllib.parse.urldefrag(urllib.parse.urljoin(base_url, str(anchor.get("href") or "").strip()))[0]
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or _registered_domain(url) != base_domain:
            continue
        haystack = (parsed.path + " " + anchor.get_text(" ", strip=True)).casefold()
        rank = next((index for index, term in enumerate(IDENTITY_TERMS) if term in haystack), None)
        if rank is None or url.rstrip("/") == base_url.rstrip("/"):
            continue
        ranked[url] = min(rank, ranked.get(url, rank))
    chosen: list[str] = []
    seen_ranks: set[int] = set()
    # Prefer one contact page, one about page, one privacy page over three variants of one.
    for url, rank in sorted(ranked.items(), key=lambda item: (item[1], len(item[0]))):
        group = next(index for index, bound in enumerate(IDENTITY_GROUPS) if rank < bound)
        if group in seen_ranks:
            continue
        seen_ranks.add(group)
        chosen.append(url)
    return chosen[:limit]


def _fetch_secondary_page(url: str, *, homepage_domain: str, timeout: float, max_bytes: int) -> tuple[dict[str, Any] | None, list[dict[str, str]], int, int, int, str | None]:
    if not _robots_allowed(url, timeout):
        return None, [], 1, 0, 0, "robots.txt disallows page"
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        with SAFE_OPENER.open(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            elapsed = int((time.monotonic() - started) * 1000)
            final_url = response.geturl()
            if len(raw) > max_bytes or "html" not in response.headers.get("content-type", "").lower():
                return None, [], 2, len(raw), elapsed, "unsupported or oversized page"
            if _registered_domain(final_url) != homepage_domain:
                return None, [], 2, len(raw), elapsed, "redirected outside registered domain"
        page_html = raw.decode("utf-8", errors="replace")
        page_soup = BeautifulSoup(page_html, "lxml")
        page_text = trafilatura.extract(page_html, url=final_url, include_links=False, include_tables=False, favor_precision=True) or ""
        page_dates = [str(node.get("datetime")).strip() for node in page_soup.select("time[datetime]") if node.get("datetime")]
        page_dates.extend(re.findall(r'"datePublished"\s*:\s*"([^"]+)"', page_html, re.IGNORECASE))
        page = {
            "url": final_url,
            "title": page_soup.title.get_text(" ", strip=True)[:500] if page_soup.title else "",
            "main_text_excerpt": page_text[:5000],
            "content_sha256": __import__("hashlib").sha256(raw).hexdigest(),
            "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "date_candidates": page_dates,
        }
        return page, _social_links(final_url, page_soup), 2, len(raw), elapsed, None
    except Exception as exc:
        return None, [], 2, 0, int((time.monotonic() - started) * 1000), f"{type(exc).__name__}: {str(exc)[:120]}"


def _jsonld_organisations(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            kind = value.get("@type")
            kinds = set(kind if isinstance(kind, list) else [kind])
            if kinds & {"Organization", "Corporation", "LocalBusiness", "Store", "Restaurant"}:
                values.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(metadata.get("json-ld", []))
    return values[:20]


def _extraction_state(text: str, soup: BeautifulSoup) -> str:
    return "js_fallback_candidate" if len(text.strip()) < 100 and len(soup.select("script[src]")) >= 2 else "static_complete"


def fetch_website(url: str | None, *, timeout: float = 15.0, max_bytes: int = 2_000_000) -> tuple[dict[str, Any], dict[str, Any]]:
    supplied_url = str(url or "").strip()
    supplied_scheme = bool(re.match(r"^https?://", supplied_url, re.I))
    normalized = normalize_homepage(url)
    if not normalized:
        return evidence("website", "not_found", "registry_linked_company_website", "https://data.brreg.no/enhetsregisteret/api/enheter", note="No valid registry website URL"), {"requests": 0, "bytes": 0, "latencies_ms": []}
    try:
        assert_public_url(normalized)
    except ValueError as exc:
        return evidence("website", "blocked", "registry_linked_company_website", normalized, note=str(exc)), {"requests": 0, "bytes": 0, "latencies_ms": []}
    if not _robots_allowed(normalized, timeout):
        return evidence("website", "blocked", "registry_linked_company_website", normalized, note="robots.txt disallows this user agent"), {"requests": 1, "bytes": 0, "latencies_ms": []}
    started = time.monotonic()
    request = urllib.request.Request(normalized, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        with SAFE_OPENER.open(request, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "")
            raw = response.read(max_bytes + 1)
            elapsed = int((time.monotonic() - started) * 1000)
            if len(raw) > max_bytes:
                return evidence("website", "blocked", "registry_linked_company_website", normalized, note="Homepage exceeds byte limit"), {"requests": 2, "bytes": len(raw), "latencies_ms": [elapsed]}
            if "html" not in content_type.lower():
                return evidence("website", "source_error", "registry_linked_company_website", normalized, note=f"Unsupported content type: {content_type}"), {"requests": 2, "bytes": len(raw), "latencies_ms": [elapsed]}
            final_url = response.geturl()
            assert_public_url(final_url)
        fetched_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        html = raw.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")
        structured = extruct.extract(html, base_url=final_url, syntaxes=["json-ld", "microdata", "opengraph"])
        text = trafilatura.extract(html, url=final_url, include_links=False, include_tables=False, favor_precision=True) or ""
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        description_tag = soup.select_one('meta[name="description"], meta[property="og:description"]')
        description = str(description_tag.get("content") or "").strip() if description_tag else ""
        value = {
            "requested_url": normalized,
            "final_url": final_url,
            "registered_domain": _registered_domain(final_url),
            "title": title[:500],
            "description": description[:2000],
            "main_text_excerpt": text[:5000],
            "social_links": _social_links(final_url, soup),
            "structured_organisations": _jsonld_organisations(structured),
            "content_sha256": __import__("hashlib").sha256(raw).hexdigest(),
            "extraction_state": _extraction_state(text, soup),
        }
        pages = [{
            "url": final_url,
            "title": title[:500],
            "main_text_excerpt": text[:5000],
            "content_sha256": value["content_sha256"],
            "retrieved_at": fetched_at,
        }]
        social = [{**item, "found_on_page": final_url} for item in _social_links_raw(final_url, soup)]
        social.extend(
            {**item, "href": item["url"], "found_on_page": final_url}
            for item in structured_social_links(structured)
        )
        requests = 2
        bytes_received = len(raw)
        page_latencies = [elapsed]
        # Identity pages (about/contact/privacy) carry org numbers, addresses and footer links.
        from .webclaims import SiteFetcher

        fetcher = SiteFetcher(value["registered_domain"], timeout=timeout, max_bytes=min(max_bytes, 1_000_000))
        subpages = []
        for page_url in _identity_links(final_url, soup, limit=IDENTITY_PAGE_LIMIT):
            page = fetcher.get(page_url, "identity")
            if not page or "html" not in page["content_type"]:
                continue
            page_html = page["raw"].decode("utf-8", errors="replace")
            page_soup = BeautifulSoup(page_html, "lxml")
            page_text = trafilatura.extract(page_html, url=page["url"], include_links=False, include_tables=False, favor_precision=True) or ""
            footer_text = " ".join(page_soup.get_text(" ", strip=True).split())
            pages.append({
                "url": page["url"],
                "title": (page_soup.title.get_text(" ", strip=True)[:500] if page_soup.title else ""),
                "main_text_excerpt": page_text[:5000],
                "identity_text_excerpt": footer_text[-3000:],
                "content_sha256": page["content_sha256"],
                "retrieved_at": page["retrieved_at"],
            })
            social.extend({**item, "found_on_page": page["url"]} for item in _social_links_raw(page["url"], page_soup))
            subpages.append(page)
        # Organisation numbers printed on the site (footer, contact, privacy pages).
        from .identity import org_numbers_in_text

        site_orgs = org_numbers_in_text(" ".join(soup.get_text(" ", strip=True).split()))
        for page in subpages:
            page_text = " ".join(BeautifulSoup(page["raw"].decode("utf-8", errors="replace"), "lxml").get_text(" ", strip=True).split())
            site_orgs.extend(o for o in org_numbers_in_text(page_text) if o not in site_orgs)
        value["org_numbers_on_site"] = site_orgs
        metrics = fetcher.metrics()
        requests += metrics["requests"]
        bytes_received += metrics["bytes"]
        page_latencies.extend(metrics["latencies_ms"])
        value["pages"] = pages
        first_seen: dict[tuple[str, str], dict[str, str]] = {}
        for item in social:
            first_seen.setdefault((item["platform"], item["url"]), item)
        value["social_links"] = list(first_seen.values())
        value["crawl_errors"] = fetcher.errors
        # In-memory only (bytes): reused by the web-claims crawl, stripped before serialization.
        value["_homepage"] = {"url": final_url, "requested_url": normalized, "raw": raw, "content_type": content_type.lower(), "content_sha256": value["content_sha256"], "retrieved_at": fetched_at}
        value["_subpages"] = subpages
        return evidence("website", "available", "registry_linked_company_website", final_url, value=value, note="Company-controlled claim layer; not an official registry fact", content_sha256=value["content_sha256"], retrieved_at=fetched_at), {"requests": requests, "bytes": bytes_received, "latencies_ms": page_latencies}
    except urllib.error.HTTPError as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        status = "not_found" if exc.code in {404, 410} else "source_error"
        return evidence("website", status, "registry_linked_company_website", normalized, note=f"HTTP {exc.code}"), {"requests": 2, "bytes": 0, "latencies_ms": [elapsed]}
    except urllib.error.URLError as exc:
        if not supplied_scheme and normalized.startswith("https://"):
            first_elapsed = int((time.monotonic() - started) * 1000)
            record, metrics = fetch_website("http://" + supplied_url, timeout=timeout, max_bytes=max_bytes)
            metrics["requests"] += 2
            metrics["latencies_ms"].insert(0, first_elapsed)
            return record, metrics
        elapsed = int((time.monotonic() - started) * 1000)
        return evidence("website", "source_error", "registry_linked_company_website", normalized, note=f"URLError: {str(exc.reason)[:180]}"), {"requests": 2, "bytes": 0, "latencies_ms": [elapsed]}
    except Exception as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        return evidence("website", "source_error", "registry_linked_company_website", normalized, note=f"{type(exc).__name__}: {str(exc)[:180]}"), {"requests": 2, "bytes": 0, "latencies_ms": [elapsed]}
