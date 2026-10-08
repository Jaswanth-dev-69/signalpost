#!/usr/bin/env python3
"""Census of evidence-span validity at three strictness levels (live re-fetch).

Every evidence item of the selected envelopes is checked against a fresh fetch of its source_url
(each URL fetched once):
  raw      the span is an exact substring of the response body (UTF-8, no normalization)
  node     the span (whitespace-collapsed) lies inside ONE text node or ONE attribute value of the
           parsed page (HTML or XML), or inside the raw body for JSON sources
  visible  the span is in the tag-stripped, whitespace-collapsed, case-folded page text (the check
           eval/evidence_audit.py uses)
Items are grouped by the claim field and availability they support and by extraction_method, so a
failing extractor is named directly.

Usage: python eval/span_audit.py ENVELOPES.jsonl [--claims external|all] [--limit-urls N] [--workers 6] [--json OUT]
       [--url-filter TEXT] [--accept "*/*"]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bs4 import BeautifulSoup, Comment

EXTERNAL = ("official_website", "company_description", "social_profile", "dated_news", "hiring_signal")
UA = "signalpost-evidence-auditor/1.0 (+https://builderr.ai)"
ACCEPT = "*/*"
_host_lock = threading.Lock()
_host_next: dict[str, float] = {}


def collapse(text: str) -> str:
    return " ".join(str(text or "").split())


def fetch(url: str) -> tuple[int, bytes, str]:
    host = urllib.parse.urlparse(url).hostname or ""
    with _host_lock:
        wait = max(0.0, _host_next.get(host, 0.0) - time.monotonic())
        _host_next[host] = time.monotonic() + wait + 0.4
    if wait:
        time.sleep(wait)
    # "*/*" like most HTTP clients: the accounts API answers XML to a browser-style Accept and JSON otherwise.
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": ACCEPT})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read(3_000_000), response.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, b"", ""
    except Exception:
        return 0, b"", ""


def node_texts(raw: str, content_type: str) -> list[str]:
    """Whitespace-collapsed text nodes and attribute values of the page."""
    stripped = raw.lstrip()
    if "json" in content_type or stripped.startswith(("{", "[")):
        return [raw]
    parser = "xml" if ("xml" in content_type and "html" not in content_type) or stripped.startswith("<?xml") else "lxml"
    soup = BeautifulSoup(raw, parser)
    texts = [collapse(node) for node in soup.find_all(string=True) if not isinstance(node, Comment)]
    for tag in soup.find_all(True):
        for value in tag.attrs.values():
            if isinstance(value, str) and len(value) >= 3:
                texts.append(collapse(value))
    return [t for t in texts if t]


def visible(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    return collapse(html.unescape(re.sub(r"<[^>]+>", " ", raw))).casefold()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("envelopes")
    parser.add_argument("--claims", choices=["external", "all"], default="external")
    parser.add_argument("--limit-urls", type=int, default=0)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--json")
    parser.add_argument("--url-filter", help="only evidence whose source_url contains this text")
    parser.add_argument("--accept", default="*/*")
    args = parser.parse_args()
    global ACCEPT
    ACCEPT = args.accept
    items = []
    for line in Path(args.envelopes).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        env = json.loads(line)
        evidence = {e["id"]: e for e in env.get("evidence") or []}
        for claim in env.get("claims") or []:
            if args.claims == "external" and claim.get("field") not in EXTERNAL:
                continue
            for ev_id in claim.get("evidence_ids") or []:
                ev = evidence.get(ev_id)
                if ev and ev.get("claim_span") and str(ev.get("source_url") or "").startswith("http") and (not args.url_filter or args.url_filter in ev["source_url"]):
                    items.append((env["organisation_number"], claim.get("field"), claim.get("availability"), ev))
    urls = sorted({ev["source_url"] for *_, ev in items})
    if args.limit_urls:
        urls = urls[: args.limit_urls]
        items = [item for item in items if item[3]["source_url"] in set(urls)]
    pages: dict[str, tuple[int, bytes, str]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for url, result in zip(urls, pool.map(fetch, urls)):
            pages[url] = result
    parsed: dict[str, tuple[str, list[str], str]] = {}
    stats: dict[str, Counter] = defaultdict(Counter)
    failures = []
    for org, field, availability, ev in items:
        status, body, ctype = pages[ev["source_url"]]
        group = f"{field}|{availability}|{str(ev.get('extraction_method') or '')[:40]}"
        stats[group]["items"] += 1
        if status != 200:
            stats[group]["not_200"] += 1
            continue
        if ev["source_url"] not in parsed:
            text = body.decode("utf-8", errors="replace")
            parsed[ev["source_url"]] = (text, node_texts(text, ctype), visible(text))
        text, nodes, vis = parsed[ev["source_url"]]
        span = ev["claim_span"]
        raw_ok = span in text
        node_ok = raw_ok and ("json" in ctype or text.lstrip().startswith(("{", "["))) or any(collapse(span) in node for node in nodes)
        vis_ok = collapse(html.unescape(span)).casefold() in vis or collapse(span).casefold() in collapse(html.unescape(text)).casefold()
        stats[group]["loaded"] += 1
        stats[group]["raw"] += raw_ok
        stats[group]["node"] += node_ok
        stats[group]["visible"] += vis_ok
        if not node_ok:
            failures.append({"org": org, "field": field, "availability": availability, "method": ev.get("extraction_method"),
                             "url": ev["source_url"], "span": span[:160], "visible_ok": vis_ok})
    total = Counter()
    for counter in stats.values():
        total.update(counter)
    print(f"evidence items {total['items']}, urls {len(urls)}, loaded {total['loaded']}: raw {total['raw']}, "
          f"node {total['node']} ({100 * total['node'] / max(1, total['loaded']):.1f}%), visible {total['visible']} "
          f"({100 * total['visible'] / max(1, total['loaded']):.1f}%), not 200: {total['not_200']}")
    for group, counter in sorted(stats.items(), key=lambda kv: -(kv[1]["loaded"] - kv[1]["node"])):
        if counter["loaded"] and counter["node"] < counter["loaded"]:
            print(f"  {group:70} loaded {counter['loaded']:4}  node-fail {counter['loaded'] - counter['node']:4}  visible-fail {counter['loaded'] - counter['visible']:4}")
    if args.json:
        Path(args.json).write_text(json.dumps({"stats": {k: dict(v) for k, v in stats.items()}, "failures": failures}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
