"""Typed, evidence-linked web claims (dated news, job postings) from a verified company site.

Only called for websites that already passed the strict entity gate. Every published item
points at a page or feed that was actually fetched, with the sha256 of those bytes, the fetch
time and a span quoting the title and the item's own date. Dates are never the retrieval date.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from bs4 import BeautifulSoup
import tldextract

USER_AGENT = "builderr-signalpost-poc/0.1 (+https://builderr.ai)"
FAMILY_FETCH_CAP = 6
MAX_NEWS_ITEMS = 10
# Article pages are fetched so each dated item cites its own page; they have their own budget.
FETCH_CAPS = {"news_article": MAX_NEWS_ITEMS}
MAX_JOB_POSTINGS = 25
PER_HOST_INTERVAL_S = 0.35

NEWS_SEGMENTS = {
    "aktuelt", "nyheter", "nyhet", "nyheiter", "news", "blogg", "blog", "presse", "pressemeldinger",
    "siste-nytt", "artikler", "artikkel", "aktuelt-og-nyheter", "nyhetsarkiv", "innsikt",
}
NEWS_PROBE_PATHS = ("/aktuelt", "/nyheter", "/news", "/blogg", "/presse", "/en/news")
NEWS_SKIP_SEGMENTS = {"side", "page", "kategori", "category", "tag", "tags", "author", "forfatter", "feed", "arkiv", "archive"}
JOB_SEGMENTS = {
    "ledige-stillinger", "stillinger", "stilling", "karriere", "career", "careers", "jobb", "jobs",
    "jobbe-hos-oss", "jobb-hos-oss", "rekruttering", "bli-med", "work-with-us", "ledig-stilling",
}
JOB_ANCHOR = re.compile(r"ledige?\s+stilling|karriere|jobb(e)?\s+(hos|i)\s|bli\s+med\s+på\s+laget|careers?\b|vacanc|job openings", re.I)
JOB_PROBE_PATHS = ("/ledige-stillinger", "/karriere", "/jobb", "/jobbe-hos-oss", "/careers", "/jobs", "/en/careers")
ABOUT_SEGMENTS = {"om-oss", "om", "about", "about-us", "selskapet", "company", "hvem-er-vi", "om-selskapet", "bedriften"}
FETCH_CAPS.update({"news_probe": 6, "jobs_depth2": 2, "jobs_probe": len(JOB_PROBE_PATHS), "sitemap": 2})
JOB_PLATFORMS = {
    "finn.no": re.compile(r"/job/|finnkode=", re.I),
    "webcruiter.no": re.compile(r"(advert|/job|AdvertId|ad\.aspx)", re.I),
    "webcruiter.com": re.compile(r"(advert|/job|AdvertId)", re.I),
    "teamtailor.com": re.compile(r"/jobs/\d+", re.I),
    "recman.no": re.compile(r"(job_id=|/job/|/stilling)", re.I),
    "jobylon.com": re.compile(r"/jobs/\d+", re.I),
    "easycruit.com": re.compile(r"/vacancy/\d+", re.I),
    "reachmee.com": re.compile(r"(job|vacancy)", re.I),
}
APPLY_MARKERS = re.compile(
    r"søknadsfrist|søk\s+(på\s+)?stillingen|send\s+(inn\s+)?søknad|søknad\s+(med\s+cv\s+)?sendes|"
    r"tiltredelse|stillingsprosent|apply\s+now|application\s+deadline|vi\s+søker\s+etter|vi\s+søker\s+en",
    re.I,
)
NO_OPENINGS = re.compile(
    r"[^.!?|]{0,40}(ingen\s+ledige|ikke\s+(noen\s+)?ledige|for\s+(tiden|øyeblikket)\s+ingen|"
    r"så\s+snart\s+det\s+kommer\s+ledige|no\s+(open\s+)?(positions|vacancies)|no\s+current\s+openings)[^.!?|]{0,100}[.!?]?",
    re.I,
)
NO_MONTHS = {
    "januar": 1, "februar": 2, "mars": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "okt": 10, "nov": 11, "des": 12,
}
NO_DATE_TEXT = re.compile(
    r"\b(\d{1,2})\.?\s+(januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember|"
    r"jan|feb|mar|apr|jun|jul|aug|sept?|okt|nov|des)\.?\s+(20\d{2})\b",
    re.I,
)
NUMERIC_DATE_TEXT = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b")
ISO_DATE_TEXT = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
URL_DATE = re.compile(r"/(20\d{2})[/-](\d{1,2})[/-](\d{1,2})(?:/|-|$)")

RATE_LIMITED = {"count": 0}
_robots_lock = threading.Lock()
_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_host_lock = threading.Lock()
_host_next: dict[str, float] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def registered_domain(url: str) -> str:
    return tldextract.extract(urllib.parse.urlparse(url).hostname or "").top_domain_under_public_suffix


def _opener():
    from .website import SAFE_OPENER  # late import: website imports this module

    return SAFE_OPENER


def robots_allowed(url: str, timeout: float) -> bool:
    """robots.txt check, cached per origin. A missing or unreadable robots.txt allows fetching."""
    parsed = urllib.parse.urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    with _robots_lock:
        cached = _robots_cache.get(origin, ...)
    if cached is ...:
        parser: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
        parser.set_url(origin + "/robots.txt")
        try:
            request = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": USER_AGENT})
            with _opener().open(request, timeout=min(timeout, 8.0)) as response:
                parser.parse(response.read(500_000).decode("utf-8", errors="replace").splitlines())
        except Exception:
            parser = None
        with _robots_lock:
            _robots_cache[origin] = parser
        cached = parser
    return True if cached is None else cached.can_fetch(USER_AGENT, url)


def _throttle(host: str) -> None:
    with _host_lock:
        now = time.monotonic()
        start = max(now, _host_next.get(host, 0.0))
        _host_next[host] = start + PER_HOST_INTERVAL_S
    if start > now:
        time.sleep(start - now)


class SiteFetcher:
    """Same-registered-domain fetcher with per-family fetch budgets and request metrics."""

    def __init__(self, domain: str, *, timeout: float, max_bytes: int = 1_500_000, deadline: float | None = None):
        self.deadline_hit = False
        self.domain = domain
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.deadline = deadline
        self.requests = 0
        self.bytes = 0
        self.latencies_ms: list[int] = []
        self.errors: list[dict[str, str]] = []
        self.budget: dict[str, int] = {}
        self.cache: dict[str, dict[str, Any] | None] = {}

    def metrics(self) -> dict[str, Any]:
        return {"requests": self.requests, "bytes": self.bytes, "latencies_ms": list(self.latencies_ms)}

    def get(self, url: str, family: str, *, accept: str = "text/html,application/xhtml+xml") -> dict[str, Any] | None:
        url = urllib.parse.urldefrag(url)[0]
        if url in self.cache:
            return self.cache[url]
        if self.budget.get(family, 0) >= FETCH_CAPS.get(family, FAMILY_FETCH_CAP):
            return None
        if self.deadline is not None and time.monotonic() > self.deadline:
            if not self.deadline_hit:
                self.deadline_hit = True
                self.errors.append({"url": url, "error": "company web budget reached; this and later pages not fetched"})
            return None
        if registered_domain(url) != self.domain:
            return None
        self.budget[family] = self.budget.get(family, 0) + 1
        self.cache[url] = None
        try:
            from .website import assert_public_url  # late import: website imports this module

            assert_public_url(url)  # same domain, but a subdomain may still resolve to a private address
            if not robots_allowed(url, self.timeout):
                self.errors.append({"url": url, "error": "robots.txt disallows page"})
                return None
            host = urllib.parse.urlparse(url).netloc.lower()
            _throttle(host)
            started = time.monotonic()
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
            self.requests += 1
            with _opener().open(request, timeout=self.timeout) as response:
                raw = response.read(self.max_bytes + 1)
                retrieved_at = _utc_now()
                final_url = response.geturl()
                content_type = response.headers.get("content-type", "").lower()
            self.latencies_ms.append(int((time.monotonic() - started) * 1000))
            self.bytes += len(raw)
            if len(raw) > self.max_bytes or registered_domain(final_url) != self.domain:
                return None
            page = {
                "url": final_url,
                "requested_url": url,
                "raw": raw,
                "content_type": content_type,
                "content_sha256": hashlib.sha256(raw).hexdigest(),
                "retrieved_at": retrieved_at,
            }
            self.cache[url] = page
            return page
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                RATE_LIMITED["count"] += 1
                if not getattr(self, "_retried_429", False):
                    # One polite retry after the site's Retry-After (capped), then give up on it.
                    self._retried_429 = True
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    time.sleep(min(5.0, float(retry_after)) if retry_after and retry_after.isdigit() else 3.0)
                    self.cache.pop(url, None)
                    self.budget[family] = self.budget.get(family, 1) - 1
                    return self.get(url, family, accept=accept)
            self.errors.append({"url": url, "error": f"HTTP {exc.code}"})
        except Exception as exc:  # network, TLS, decode
            self.errors.append({"url": url, "error": f"{type(exc).__name__}: {str(exc)[:100]}"})
        return None


# ---------------------------------------------------------------- dates

def _valid_date(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if value.year < 2000 or value > now + timedelta(days=2):
        return None
    return value.date().isoformat()


def parse_iso(text: str | None) -> str | None:
    text = str(text or "").strip()
    match = re.match(r"(20\d{2})-(\d{2})-(\d{2})", text)
    if not match:
        return None
    try:
        return _valid_date(datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))))
    except ValueError:
        return None


def parse_rfc822(text: str | None) -> str | None:
    try:
        return _valid_date(parsedate_to_datetime(str(text or "").strip()))
    except (TypeError, ValueError, IndexError):
        return parse_iso(text)


def published_at(raw: str | None, iso_date: str) -> str:
    """The source's own publication timestamp as ISO 8601 with its UTC offset, or the date when the
    source states only a date. Builderr keys dated news as "title (timestamp)"."""
    text = str(raw or "").strip()
    if re.match(r"20\d{2}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}", text):
        # ISO timestamps are kept exactly as the page states them (Builderr's key is that string).
        try:
            value = datetime.fromisoformat(text.replace(" ", "T", 1))
            if value.date().isoformat() == iso_date:
                return text
        except ValueError:
            pass
    elif re.search(r"\d{1,2}:\d{2}", text) and not re.match(r"20\d{2}-", text):
        try:  # RFC 822 feed dates, e.g. "Mon, 22 Sep 2025 20:00:00 +0200"
            value = parsedate_to_datetime(text)
            if value.date().isoformat() == iso_date:
                return value.isoformat()
        except (TypeError, ValueError, IndexError):
            pass
    return iso_date


def parse_norwegian_text_date(text: str) -> tuple[str, str] | None:
    """Return (iso_date, quoted_text) for the first Norwegian or numeric date in text."""
    match = NO_DATE_TEXT.search(text)
    if match:
        quoted = match.group(0)
        try:
            import dateparser

            parsed = dateparser.parse(quoted, languages=["nb"], settings={"STRICT_PARSING": True, "REQUIRE_PARTS": ["day", "month", "year"]})
        except Exception:
            parsed = None
        if parsed is None:
            try:
                parsed = datetime(int(match.group(3)), NO_MONTHS[match.group(2).lower().rstrip(".")], int(match.group(1)))
            except (KeyError, ValueError):
                parsed = None
        iso = _valid_date(parsed)
        if iso:
            return iso, quoted
    for pattern, order in ((NUMERIC_DATE_TEXT, (3, 2, 1)), (ISO_DATE_TEXT, (1, 2, 3))):
        match = pattern.search(text)
        if match:
            try:
                iso = _valid_date(datetime(int(match.group(order[0])), int(match.group(order[1])), int(match.group(order[2]))))
            except ValueError:
                iso = None
            if iso:
                return iso, match.group(0)
    return None


def url_date(url: str) -> tuple[str, str] | None:
    match = URL_DATE.search(urllib.parse.urlparse(url).path)
    if not match:
        return None
    try:
        iso = _valid_date(datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))))
    except ValueError:
        return None
    return (iso, match.group(0).strip("/-")) if iso else None


def _jsonld_nodes(soup: BeautifulSoup) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            nodes.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(script.string or script.get_text() or ""))
        except (ValueError, TypeError):
            continue
    return nodes


def _types(node: dict[str, Any]) -> set[str]:
    kind = node.get("@type")
    return {str(k) for k in (kind if isinstance(kind, list) else [kind]) if k}


def article_date(soup: BeautifulSoup, url: str) -> tuple[str, str, str] | None:
    """(iso_date, quoted_source_text, method) for an individual article page."""
    meta = soup.select_one('meta[property="article:published_time"], meta[itemprop="datePublished"], meta[name="date"], meta[name="publish-date"]')
    if meta and parse_iso(meta.get("content")):
        return parse_iso(meta.get("content")), str(meta.get("content")), "meta_published_time"
    nodes = _jsonld_nodes(soup)
    article_types = {"Article", "NewsArticle", "BlogPosting", "Report", "PressRelease", "WebPage"}
    for node in sorted(nodes, key=lambda n: 0 if _types(n) & {"Article", "NewsArticle", "BlogPosting"} else 1):
        if _types(node) & article_types and parse_iso(node.get("datePublished")):
            return parse_iso(node.get("datePublished")), str(node.get("datePublished")), "jsonld_datePublished"
    scope = soup.select_one("article") or soup.select_one("main") or soup
    for node in scope.select("time[datetime]"):
        if parse_iso(node.get("datetime")):
            return parse_iso(node.get("datetime")), str(node.get("datetime")), "time_datetime"
    head = " ".join((scope.get_text(" ", strip=True) or "").split())[:1500]
    found = parse_norwegian_text_date(head)
    if found:
        return found[0], found[1], "page_text_date"
    found = url_date(url)
    if found:
        return found[0], found[1], "url_date"
    return None


def _title(soup: BeautifulSoup) -> str:
    for selector in ("article h1", "main h1", "h1", 'meta[property="og:title"]'):
        node = soup.select_one(selector)
        if node is not None:
            text = node.get("content") if node.name == "meta" else node.get_text(" ", strip=True)
            text = " ".join(str(text or "").split())
            if len(text) >= 4:
                return text[:300]
    return " ".join((soup.title.get_text(" ", strip=True) if soup.title else "").split())[:300]


def verbatim_window(text: str, parts: list[str], limit: int = 480) -> str | None:
    """Shortest contiguous stretch of ``text`` containing every part (case-insensitive), widened to
    word boundaries. ``text`` must already be whitespace-normalized page text."""
    spans = []
    folded = text.casefold()
    for part in parts:
        part = " ".join(str(part or "").split())
        index = folded.find(part.casefold()) if part else -1
        if index < 0:
            return None
        spans.append((index, index + len(part)))
    start, end = min(a for a, _ in spans), max(b for _, b in spans)
    start = text.rfind(" ", 0, start) + 1 if start > 0 and text[start - 1] != " " else start
    stop = text.find(" ", end)
    window = text[start:stop if stop != -1 else len(text)].strip()
    return window if 0 < len(window) <= limit else None


def article_item(page: dict[str, Any], soup: BeautifulSoup) -> dict[str, Any] | None:
    """A dated news item read from the article's own page: its heading and its own publication date."""
    found = article_date(soup, page["url"])
    title = _title(soup)
    if not found or not title:
        return None
    return {
        "title": title,
        "url": page["url"],
        "published_date": found[0],
        "published_at": published_at(found[1], found[0]),
        "date_source": found[2],
        "source_page": page["url"],
        "content_sha256": page["content_sha256"],
        "retrieved_at": page["retrieved_at"],
        "claim_span": title,
        "date_span": found[1],
        "extraction_method": f"article_page:{found[2]}",
    }


def _soup(page: dict[str, Any]) -> BeautifulSoup:
    return BeautifulSoup(page["raw"].decode("utf-8", errors="replace"), "lxml")


def _is_html(page: dict[str, Any] | None) -> bool:
    return bool(page) and "html" in page.get("content_type", "")


def _segments(url: str) -> list[str]:
    return [s for s in urllib.parse.urlparse(url).path.casefold().split("/") if s]


def _same_site_links(base_url: str, soup: BeautifulSoup, domain: str) -> list[tuple[str, str]]:
    links: dict[str, str] = {}
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        url = urllib.parse.urldefrag(urllib.parse.urljoin(base_url, href))[0]
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or registered_domain(url) != domain:
            continue
        links.setdefault(url, " ".join(anchor.get_text(" ", strip=True).split())[:200])
    return list(links.items())


def _feed_links(base_url: str, soup: BeautifulSoup) -> list[str]:
    feeds = []
    for node in soup.select('link[rel~="alternate"][href]'):
        kind = str(node.get("type") or "").lower()
        href = urllib.parse.urljoin(base_url, str(node.get("href")))
        if ("rss" in kind or "atom" in kind) and "comment" not in href.lower() and "kommentar" not in href.lower():
            feeds.append(href)
    return list(dict.fromkeys(feeds))


# ---------------------------------------------------------------- news

NEWS_TOKENS = {"aktuelt", "nyheter", "nyhet", "nyheiter", "news", "blogg", "blog", "presse", "pressemeldinger", "artikler", "nytt", "innsikt"}


def _news_index(segments: list[str]) -> int | None:
    for index, segment in enumerate(segments):
        if segment in NEWS_SEGMENTS or (set(re.split(r"[-_]", segment)) & NEWS_TOKENS and "nyhetsbrev" not in segment):
            return index
    return None


def is_news_listing(url: str) -> bool:
    segments = _segments(url)
    index = _news_index(segments)
    return index is not None and index == len(segments) - 1


def is_news_article(url: str) -> bool:
    segments = _segments(url)
    index = _news_index(segments)
    if index is None or index == len(segments) - 1:
        return False
    rest = segments[index + 1:]
    if rest[0] in NEWS_SKIP_SEGMENTS or (rest[0].isdigit() and len(rest) == 1 and len(rest[0]) < 4):
        return False
    return bool(re.search(r"[a-z]", rest[-1])) or url_date(url) is not None


def parse_feed(page: dict[str, Any], domain: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(page["raw"])
    except ET.ParseError:
        return []
    items: list[dict[str, Any]] = []
    atom = "{http://www.w3.org/2005/Atom}"
    entries = root.findall(".//item") or root.findall(f".//{atom}entry")
    for entry in entries:
        if entry.tag == "item":
            title = (entry.findtext("title") or "").strip()
            link = (entry.findtext("link") or "").strip()
            raw_date = (entry.findtext("pubDate") or entry.findtext("{http://purl.org/dc/elements/1.1/}date") or "").strip()
            iso, method = parse_rfc822(raw_date), "rss_pubDate"
        else:
            title = (entry.findtext(f"{atom}title") or "").strip()
            link_node = entry.find(f"{atom}link[@rel='alternate']") or entry.find(f"{atom}link")
            link = (link_node.get("href") if link_node is not None else "") or ""
            raw_date = (entry.findtext(f"{atom}published") or entry.findtext(f"{atom}updated") or "").strip()
            iso, method = parse_iso(raw_date), "atom_published" if entry.findtext(f"{atom}published") else "atom_updated"
        link = urllib.parse.urljoin(page["url"], link)
        if not (title and link and iso) or registered_domain(link) != domain:
            continue
        items.append({
            "title": " ".join(title.split())[:300],
            "url": link,
            "published_date": iso,
            "published_at": published_at(raw_date, iso),
            "date_source": method,
            "source_page": page["url"],
            "content_sha256": page["content_sha256"],
            "retrieved_at": page["retrieved_at"],
            "claim_span": " ".join(title.split())[:300],
            "date_span": raw_date,
            "extraction_method": f"feed:{method}",
        })
    return items


def _listing_inline_items(listing: dict[str, Any], soup: BeautifulSoup, domain: str) -> list[dict[str, Any]]:
    """Dated teasers on a listing page: an article link whose small container shows a date."""
    items: dict[str, dict[str, Any]] = {}
    for anchor in soup.select("a[href]"):
        url = urllib.parse.urldefrag(urllib.parse.urljoin(listing["url"], str(anchor.get("href"))))[0]
        if registered_domain(url) != domain or not is_news_article(url) or url in items:
            continue
        container = anchor
        for _ in range(4):
            parent = container.parent
            if parent is None or len(parent.get_text(" ", strip=True)) > 700 or len(parent.select("a[href]")) > 6:
                break
            container = parent
        found = None
        time_node = container.select_one("time[datetime]")
        if time_node is not None and parse_iso(time_node.get("datetime")):
            found = (parse_iso(time_node.get("datetime")), str(time_node.get("datetime")), "listing_time_datetime")
        else:
            text_date = parse_norwegian_text_date(" ".join(container.get_text(" ", strip=True).split()))
            if text_date:
                found = (text_date[0], text_date[1], "listing_text_date")
        if not found:
            continue
        heading = container.select_one("h1, h2, h3, h4")
        title = " ".join((heading.get_text(" ", strip=True) if heading else anchor.get_text(" ", strip=True)).split())[:300]
        if len(title) < 4:
            continue
        container_text = " ".join(container.get_text(" ", strip=True).split())
        visible_date = found[1] if found[2] == "listing_text_date" else (time_node.get_text(" ", strip=True) if time_node is not None else "")
        window = verbatim_window(container_text, [title, visible_date]) if visible_date else None
        items[url] = {
            "title": title,
            "url": url,
            "published_date": found[0],
            "published_at": published_at(found[1], found[0]),
            "date_source": found[2],
            "source_page": listing["url"],
            "content_sha256": listing["content_sha256"],
            "retrieved_at": listing["retrieved_at"],
            "claim_span": window or title,
            "date_span": None if window else found[1],
            "extraction_method": f"news_listing:{found[2]}",
        }
    return list(items.values())


def _jsonld_article_items(page: dict[str, Any], soup: BeautifulSoup, domain: str) -> list[dict[str, Any]]:
    """Articles listed in JSON-LD (ItemList / Blog / NewsArticle nodes) with their own datePublished."""
    items = []
    for node in _jsonld_nodes(soup):
        if not _types(node) & {"NewsArticle", "BlogPosting", "Article", "PressRelease"}:
            continue
        url = node.get("url") or node.get("@id") or (node.get("mainEntityOfPage") if isinstance(node.get("mainEntityOfPage"), str) else None)
        title = " ".join(str(node.get("headline") or node.get("name") or "").split())[:300]
        published = parse_iso(node.get("datePublished"))
        if not (url and title and published):
            continue
        url = urllib.parse.urldefrag(urllib.parse.urljoin(page["url"], str(url)))[0]
        if registered_domain(url) != domain or url.rstrip("/") == page["url"].rstrip("/"):
            continue  # the page's own date belongs to the page, not to a listed item
        items.append({
            "title": title, "url": url, "published_date": published, "published_at": published_at(node.get("datePublished"), published),
            "date_source": "jsonld_list_datePublished",
            "source_page": page["url"], "content_sha256": page["content_sha256"], "retrieved_at": page["retrieved_at"],
            "claim_span": title, "date_span": str(node.get("datePublished")), "extraction_method": "news_listing:jsonld_datePublished",
        })
    return items


def _wordpress_posts(fetcher: SiteFetcher, home: dict[str, Any], domain: str) -> list[dict[str, Any]]:
    """WordPress REST API: posts carry their real publication date."""
    url = urllib.parse.urljoin(home["url"], "/wp-json/wp/v2/posts?per_page=10&_fields=date,link,title")
    page = fetcher.get(url, "news", accept="application/json")
    if not page or "json" not in page.get("content_type", ""):
        return []
    try:
        posts = json.loads(page["raw"])
    except ValueError:
        return []
    items = []
    for post in posts if isinstance(posts, list) else []:
        title = BeautifulSoup(str((post.get("title") or {}).get("rendered") or ""), "lxml").get_text(" ", strip=True)[:300]
        link = str(post.get("link") or "")
        published = parse_iso(post.get("date"))
        if title and link and published and registered_domain(link) == domain:
            items.append({
                "title": title, "url": link, "published_date": published, "published_at": published_at(post.get("date"), published),
                "date_source": "wordpress_rest_date",
                "source_page": page["url"], "content_sha256": page["content_sha256"], "retrieved_at": page["retrieved_at"],
                "claim_span": title, "date_span": str(post.get("date")), "extraction_method": "wordpress_rest:date",
            })
    return items


def _sitemap_article_urls(fetcher: SiteFetcher, home_url: str) -> tuple[list[dict[str, Any]], list[str]]:
    """News sitemaps give real publication dates; plain sitemaps only give article URLs."""
    origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(home_url))
    page = fetcher.get(origin + "/sitemap.xml", "news", accept="application/xml,text/xml")
    if not page:
        return [], []
    try:
        root = ET.fromstring(page["raw"])
    except ET.ParseError:
        return [], []
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "n": "http://www.google.com/schemas/sitemap-news/0.9"}
    children = [loc.text.strip() for loc in root.findall("s:sitemap/s:loc", ns) if loc.text]
    if children:
        preferred = [c for c in children if re.search(r"post|news|nyhet|aktuelt|artik|blog", c, re.I)]
        if not preferred:
            return [], []
        page = fetcher.get(preferred[0], "news", accept="application/xml,text/xml")
        if not page:
            return [], []
        try:
            root = ET.fromstring(page["raw"])
        except ET.ParseError:
            return [], []
    dated: list[dict[str, Any]] = []
    urls: list[tuple[str, str]] = []
    for node in root.findall("s:url", ns):
        loc = (node.findtext("s:loc", default="", namespaces=ns) or "").strip()
        pub = node.findtext("n:news/n:publication_date", default="", namespaces=ns)
        title = node.findtext("n:news/n:title", default="", namespaces=ns)
        if loc and pub and title and parse_iso(pub):
            dated.append({
                "title": " ".join(title.split())[:300], "url": loc, "published_date": parse_iso(pub), "published_at": published_at(pub, parse_iso(pub)),
                "date_source": "news_sitemap_publication_date", "source_page": page["url"],
                "content_sha256": page["content_sha256"], "retrieved_at": page["retrieved_at"],
                "claim_span": " ".join(title.split())[:300], "date_span": pub.strip(), "extraction_method": "news_sitemap:publication_date",
            })
        elif loc and is_news_article(loc):
            urls.append((node.findtext("s:lastmod", default="", namespaces=ns) or "", loc))
    # Most recently changed articles first (lastmod is not a publication date; each article page is
    # still fetched for its own date).
    return dated, [loc for _, loc in sorted(urls, reverse=True)]


def _sitemap_page_urls(fetcher: SiteFetcher, home_url: str, limit: int = 2000) -> list[str]:
    """Same-site page URLs from /sitemap.xml (and its first page-type child sitemap)."""
    origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(home_url))
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    page = fetcher.get(origin + "/sitemap.xml", "sitemap", accept="application/xml,text/xml")
    try:
        root = ET.fromstring(page["raw"]) if page else None
    except ET.ParseError:
        root = None
    if root is None:
        return []
    children = [loc.text.strip() for loc in root.findall("s:sitemap/s:loc", ns) if loc.text]
    if children:
        pages = [c for c in children if re.search(r"page|side", c, re.I)] or children[:1]
        page = fetcher.get(pages[0], "sitemap", accept="application/xml,text/xml")
        try:
            root = ET.fromstring(page["raw"]) if page else None
        except ET.ParseError:
            root = None
        if root is None:
            return []
    urls = [(loc.text or "").strip() for loc in root.findall("s:url/s:loc", ns)][:limit]
    return [u for u in urls if u and registered_domain(u) == fetcher.domain]


def discover_news(fetcher: SiteFetcher, home: dict[str, Any], home_soup: BeautifulSoup, extra_links: list[tuple[str, str]]) -> dict[str, Any]:
    domain = fetcher.domain
    links = _same_site_links(home["url"], home_soup, domain) + extra_links
    feeds = _feed_links(home["url"], home_soup)
    listings = [url for url, _ in links if is_news_listing(url)]
    articles = [url for url, _ in links if is_news_article(url)]
    checked: list[dict[str, Any]] = []
    items: dict[str, dict[str, Any]] = {}

    # Dated teasers already on the homepage cost no extra fetch.
    for item in _listing_inline_items(home, home_soup, domain) + _jsonld_article_items(home, home_soup, domain):
        items.setdefault(item["url"], item)

    listing_page = None
    listing_has_articles = False
    for url in listings[:2]:
        listing_page = fetcher.get(url, "news")
        if _is_html(listing_page):
            break
        listing_page = None
    if listing_page is None and not articles and not feeds:
        for path in NEWS_PROBE_PATHS:
            probe = fetcher.get(urllib.parse.urljoin(home["url"], path), "news_probe")
            if _is_html(probe) and _news_index(_segments(probe["url"])) is not None:
                listing_page = probe
                break
    if listing_page is not None:
        soup = _soup(listing_page)
        feeds.extend(f for f in _feed_links(listing_page["url"], soup) if f not in feeds)
        listing_links = _same_site_links(listing_page["url"], soup, domain)
        listing_articles = [u for u, _ in listing_links if is_news_article(u)]
        if not listing_articles:
            # Landing page that only links onward to the real archive (one hop).
            onward = [u for u, _ in listing_links if is_news_listing(u) and u.rstrip("/") != listing_page["url"].rstrip("/") and u not in listings]
            for url in onward[:1]:
                archive = fetcher.get(url, "news")
                if _is_html(archive):
                    listing_page, soup = archive, _soup(archive)
                    listing_links = _same_site_links(archive["url"], soup, domain)
                    listing_articles = [u for u, _ in listing_links if is_news_article(u)]
        articles = list(dict.fromkeys(listing_articles + articles))
        listing_has_articles = bool(listing_articles)
        for item in _listing_inline_items(listing_page, soup, domain) + _jsonld_article_items(listing_page, soup, domain):
            items.setdefault(item["url"], item)
        text = " ".join(soup.get_text(" ", strip=True).split())
        checked.append({**_page_ref(listing_page), "claim_span": (_title(soup) or "news page") + " | " + text[:160]})

    if len(items) < MAX_NEWS_ITEMS:
        raw_home = home["raw"]
        wordpress = b"wp-content" in raw_home or b"wp-json" in raw_home
        if not feeds:
            # Conventional feed locations, cheapest platform-specific guess first.
            if wordpress:
                feeds.append(urllib.parse.urljoin(home["url"], "/feed/"))
            elif b"wix.com" in raw_home or b"wixstatic" in raw_home:
                feeds.append(urllib.parse.urljoin(home["url"], "/blog-feed.xml"))
            elif listing_page is not None and b"squarespace" in raw_home:
                feeds.append(listing_page["url"].rstrip("/") + "?format=rss")
            else:
                feeds.extend(urllib.parse.urljoin(home["url"], p) for p in ("/rss.xml", "/feed"))
        feed_found = False
        for feed_url in feeds[:2]:
            feed = fetcher.get(feed_url, "news", accept="application/rss+xml,application/atom+xml,application/xml,text/xml")
            if not feed or _is_html(feed):
                continue
            feed_items = parse_feed(feed, domain)
            for item in feed_items:
                items.setdefault(item["url"], item)
            if feed_items:
                feed_found = True
                break
        if not feed_found and wordpress and len(items) < MAX_NEWS_ITEMS:
            for item in _wordpress_posts(fetcher, home, domain):
                items.setdefault(item["url"], item)

    # The sitemap finds articles that a JavaScript-rendered listing does not link statically,
    # including nested news sections (e.g. /fag-og-forskning/.../nyheter-rkr/...).
    if not items and not listing_has_articles:
        dated, sitemap_urls = _sitemap_article_urls(fetcher, home["url"])
        for item in dated:
            items.setdefault(item["url"], item)
        articles = list(dict.fromkeys(sitemap_urls[:MAX_NEWS_ITEMS] + articles))

    for url in articles:
        if len(items) >= MAX_NEWS_ITEMS:
            break
        if url in items:
            continue
        page = fetcher.get(url, "news_article")
        if page is None:
            if fetcher.budget.get("news_article", 0) >= FETCH_CAPS["news_article"]:
                break
            continue
        if not _is_html(page):
            continue
        item = article_item(page, _soup(page))
        if item:
            items[url] = item

    # Each published item should cite its own article page ("the exact public page"); items seen
    # on a listing, feed or sitemap are re-read from the article when it can be fetched and dated.
    ordered = sorted(items.values(), key=lambda item: item["published_date"], reverse=True)[:MAX_NEWS_ITEMS]
    upgraded = []
    for item in ordered:
        if item["source_page"] != item["url"]:
            page = fetcher.get(item["url"], "news_article")
            article = article_item(page, _soup(page)) if _is_html(page) else None
            if article and article["url"] not in {i["url"] for i in upgraded}:
                item = article
        upgraded.append(item)
    upgraded.sort(key=lambda item: item["published_date"], reverse=True)
    return {"items": upgraded, "checked_pages": checked}


# ---------------------------------------------------------------- jobs

def _page_ref(page: dict[str, Any]) -> dict[str, Any]:
    return {"url": page["url"], "content_sha256": page["content_sha256"], "retrieved_at": page["retrieved_at"]}


def _platform_posting(url: str) -> str | None:
    host = (urllib.parse.urlparse(url).hostname or "").casefold()
    for domain, pattern in JOB_PLATFORMS.items():
        if (host == domain or host.endswith("." + domain)) and pattern.search(url):
            return domain
    return None


CAREERS_TEXT = re.compile(r"ledige?\s+stilling|stillinger|karriere|jobb|careers?\b|\bjobs?\b|rekrutter|vacanc|arbeide?\s+(hos|i|for)\s", re.I)


def careers_heading(soup: BeautifulSoup) -> str | None:
    """Verbatim heading or title that names the page as the company's careers/jobs page."""
    for node in [*soup.select("h1"), *soup.select("title"), *soup.select("h2")[:6]]:
        text = " ".join(node.get_text(" ", strip=True).split())
        if 3 <= len(text) <= 200 and CAREERS_TEXT.search(text):
            return text
    return None


def _is_careers_url(url: str, anchor_text: str = "") -> bool:
    segments = _segments(url)
    return any(s in JOB_SEGMENTS for s in segments) or bool(anchor_text and JOB_ANCHOR.search(anchor_text))


def _jobposting_items(page: dict[str, Any], soup: BeautifulSoup) -> list[dict[str, Any]]:
    postings = []
    for node in _jsonld_nodes(soup):
        if "JobPosting" not in _types(node):
            continue
        title = " ".join(str(node.get("title") or node.get("name") or "").split())[:300]
        if not title:
            continue
        posted = parse_iso(node.get("datePosted"))
        postings.append({
            "title": title,
            "url": urllib.parse.urljoin(page["url"], str(node.get("url") or page["url"])),
            "posted_date": posted,
            "valid_through": parse_iso(node.get("validThrough")),
            "platform": "company_site",
            "source_page": page["url"],
            "content_sha256": page["content_sha256"],
            "retrieved_at": page["retrieved_at"],
            "claim_span": title,
            "extraction_method": "jsonld_jobposting",
        })
    return postings


def _platform_links(page: dict[str, Any], soup: BeautifulSoup) -> list[dict[str, Any]]:
    postings = []
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        url = urllib.parse.urljoin(page["url"], href)
        platform = _platform_posting(url)
        if not platform:
            continue
        text = " ".join(anchor.get_text(" ", strip=True).split())[:300]
        if len(text) < 4 or re.search(r"\b(les mer|søk her|søk på|klikk her|apply|se stilling(en)?|mer info|finn\.no|webcruiter|ledige stillinger)\b", text, re.I):
            heading = anchor.find_previous(["h2", "h3", "h4"])
            text = " ".join(heading.get_text(" ", strip=True).split())[:300] if heading else ""
        if len(text) < 4 or re.search(r"\b(les mer|søk her|klikk her|ledige stillinger)\b", text, re.I):
            continue
        postings.append({
            "title": text,
            "url": url,
            "platform": platform,
            "source_page": page["url"],
            "content_sha256": page["content_sha256"],
            "retrieved_at": page["retrieved_at"],
            "claim_span": text,
            "extraction_method": "job_platform_link",
        })
    return postings


def discover_jobs(fetcher: SiteFetcher, home: dict[str, Any], home_soup: BeautifulSoup, extra_pages: list[dict[str, Any]]) -> dict[str, Any]:
    domain = fetcher.domain
    postings: dict[str, dict[str, Any]] = {}
    sources = [home, *extra_pages]
    candidates: list[str] = []
    for page in sources:
        if not _is_html(page):
            continue
        soup = home_soup if page is home else _soup(page)
        for item in _jobposting_items(page, soup) + _platform_links(page, soup):
            postings.setdefault(item["url"], item)
        for url, text in _same_site_links(page["url"], soup, domain):
            if _is_careers_url(url, text) and url.rstrip("/") != home["url"].rstrip("/"):
                candidates.append(url)
    candidates = list(dict.fromkeys(candidates))
    # Shallowest careers URL first: the index page, not an individual posting.
    candidates.sort(key=lambda u: (len(_segments(u)), u))

    # A careers page counts only when the page itself names careers/jobs in a heading or its title.
    careers_page, heading = None, None
    tried: set[str] = set()

    def try_candidates(urls: list[str], family: str, limit: int, probe: bool = False) -> tuple[dict[str, Any] | None, str | None]:
        for url in [u for u in urls if u not in tried][:limit]:
            tried.add(url)
            page = fetcher.get(url, family)
            # A blind probe must also land on a careers URL (not a redirect to the homepage).
            if _is_html(page) and (not probe or _is_careers_url(page["url"])) and (found := careers_heading(_soup(page))):
                return page, found
        return None, None

    careers_page, heading = try_candidates(candidates, "jobs", 3)
    if careers_page is None:
        # Depth 2: careers links often sit on an about/company page reached from the menu.
        fetched = {page["url"].rstrip("/") for page in sources if page}
        about = [u for u, _ in _same_site_links(home["url"], home_soup, domain)
                 if any(s in ABOUT_SEGMENTS for s in _segments(u)[:2]) and u.rstrip("/") not in fetched]
        about.sort(key=lambda u: (len(_segments(u)), u))
        deeper: list[str] = []
        for url in list(dict.fromkeys(about))[:2]:
            page = fetcher.get(url, "jobs_depth2")
            if _is_html(page):
                deeper += [u for u, text in _same_site_links(page["url"], _soup(page), domain)
                           if _is_careers_url(u, text) and u.rstrip("/") != home["url"].rstrip("/")]
        deeper = sorted(dict.fromkeys(deeper), key=lambda u: (len(_segments(u)), u))
        careers_page, heading = try_candidates(deeper, "jobs", 2)
        candidates += deeper
    if careers_page is None:
        # The site's own sitemap lists careers pages that no menu links statically.
        mapped = [u for u in _sitemap_page_urls(fetcher, home["url"]) if any(s in JOB_SEGMENTS for s in _segments(u)[:2])]
        mapped.sort(key=lambda u: (len(_segments(u)), u))
        careers_page, heading = try_candidates(mapped, "jobs", 2)
        candidates += mapped
    if careers_page is None and not candidates:
        careers_page, heading = try_candidates([urllib.parse.urljoin(home["url"], path) for path in JOB_PROBE_PATHS], "jobs_probe", len(JOB_PROBE_PATHS), probe=True)

    careers_ref = None
    if careers_page is not None:
        soup = _soup(careers_page)
        for item in _jobposting_items(careers_page, soup) + _platform_links(careers_page, soup):
            postings.setdefault(item["url"], item)
        careers_segments = _segments(careers_page["url"])
        deeper = [
            (url, text) for url, text in _same_site_links(careers_page["url"], soup, domain)
            if _segments(url)[:len(careers_segments)] == careers_segments and len(_segments(url)) > len(careers_segments)
            and _segments(url)[-1] not in NEWS_SKIP_SEGMENTS
        ]
        for url, _text in deeper[:8]:
            if len(postings) >= MAX_JOB_POSTINGS or fetcher.budget.get("jobs", 0) >= FAMILY_FETCH_CAP:
                break
            page = fetcher.get(url, "jobs")
            if not _is_html(page):
                continue
            page_soup = _soup(page)
            structured = _jobposting_items(page, page_soup)
            if structured:
                for item in structured:
                    postings.setdefault(item["url"], item)
                continue
            text = " ".join(page_soup.get_text(" ", strip=True).split())
            marker = APPLY_MARKERS.search(text)
            title = _title(page_soup)
            if marker and title:
                postings.setdefault(page["url"], {
                    "title": title,
                    "url": page["url"],
                    "platform": "company_site",
                    "source_page": page["url"],
                    "content_sha256": page["content_sha256"],
                    "retrieved_at": page["retrieved_at"],
                    "claim_span": title,
                    "extraction_method": "careers_subpage_apply_marker",
                })
        text = " ".join(soup.get_text(" ", strip=True).split())
        no_openings = NO_OPENINGS.search(text)
        careers_ref = {
            **_page_ref(careers_page),
            "claim_span": heading,
            "explicit_no_openings": bool(no_openings),
            "no_openings_span": no_openings.group(0).strip() if no_openings else None,
        }

    return {"postings": list(postings.values())[:MAX_JOB_POSTINGS], "careers_page": careers_ref}


# ---------------------------------------------------------------- entry point

def crawl_web_claims(website_value: dict[str, Any], *, timeout: float = 10.0, deadline: float | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Crawl a verified site for dated news and job postings within per-family fetch budgets."""
    home_url = website_value.get("final_url")
    domain = website_value.get("registered_domain") or registered_domain(home_url or "")
    fetcher = SiteFetcher(domain, timeout=timeout, deadline=deadline)
    empty = {"news": {"items": [], "checked_pages": []}, "jobs": {"postings": [], "careers_page": None}}
    if not home_url:
        return empty, fetcher.metrics()
    # Re-use the homepage bytes already fetched by fetch_website (same hash/time).
    home = website_value.get("_homepage")
    if not home:
        home = fetcher.get(home_url, "home")
    if not _is_html(home):
        return empty, fetcher.metrics()
    home_soup = _soup(home)
    extra_pages = [p for p in website_value.get("_subpages") or [] if p]
    extra_links: list[tuple[str, str]] = []
    for page in extra_pages:
        if _is_html(page):
            extra_links.extend(_same_site_links(page["url"], _soup(page), domain))
    # Careers first: it costs a few requests and decides a whole company's hiring coverage, while a
    # budget cut during news only drops some of up to ten articles.
    jobs = discover_jobs(fetcher, home, home_soup, extra_pages)
    news = discover_news(fetcher, home, home_soup, extra_links)
    # crawl_complete is false when the company's web budget cut the crawl short: absence of an item is
    # then not evidence that it is gone (refresh relies on this to avoid false changes).
    claims = {"news": news, "jobs": jobs, "crawl_errors": fetcher.errors[:50], "crawl_complete": not fetcher.deadline_hit}
    return claims, fetcher.metrics()
