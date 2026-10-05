#!/usr/bin/env python3
"""Live audit of external-claim evidence: re-open each cited page and check that it loads, that every
claim_span is verbatim on it, and whether its bytes still hash to content_sha256.

Usage: python eval/evidence_audit.py <envelopes.jsonl> [sample_size] [seed]
"""
from __future__ import annotations

import hashlib
import html
import json
import random
import re
import sys
import time
import urllib.request
from collections import Counter

EXTERNAL = ("official_website", "company_description", "social_profile", "dated_news", "hiring_signal")
UA = "signalpost-evidence-auditor/1.0 (+https://builderr.ai)"


def norm(text: str) -> str:
    return " ".join(html.unescape(text).split()).casefold()


def visible(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    return norm(re.sub(r"<[^>]+>", " ", raw))


def fetch(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml,*/*"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read(3_000_000)
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except Exception:
        return 0, b""


def main() -> int:
    path = sys.argv[1]
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    rng = random.Random(int(sys.argv[3]) if len(sys.argv) > 3 else 20261005)
    pool = []
    for line in open(path, encoding="utf-8"):
        env = json.loads(line)
        evidence = {e["id"]: e for e in env["evidence"]}
        for claim in env["claims"]:
            if claim["field"] in EXTERNAL and claim["availability"] == "available":
                pool.append((env["organisation_number"], claim, [evidence[i] for i in claim["evidence_ids"] if i in evidence]))
    sample = rng.sample(pool, min(size, len(pool)))
    cache: dict[str, tuple[int, bytes]] = {}
    stats, fails = Counter(), []
    for org, claim, evs in sample:
        stats[f"field:{claim['field']}"] += 1
        for ev in evs:
            url = ev["source_url"]
            if url not in cache:
                time.sleep(0.2)
                cache[url] = fetch(url)
            status, raw = cache[url]
            stats["evidence"] += 1
            if status != 200:
                stats["url_not_200"] += 1
                fails.append((org, claim["field"], f"HTTP {status}", url))
                continue
            stats["url_loads"] += 1
            text = raw.decode("utf-8", errors="replace")
            span = norm(ev["claim_span"])
            if span in norm(text) or span in visible(text):
                stats["span_verbatim"] += 1
            else:
                fails.append((org, claim["field"], f"span not on page: {ev['claim_span'][:70]!r}", url))
            if hashlib.sha256(raw).hexdigest() == ev["content_sha256"]:
                stats["hash_identical"] += 1
    loaded = stats["url_loads"] or 1
    print(json.dumps({
        "claims": len(sample), "evidence_items": stats["evidence"], "url_loads": stats["url_loads"],
        "span_verbatim_pct_of_loaded": round(100 * stats["span_verbatim"] / loaded, 1),
        "hash_identical_pct_of_loaded": round(100 * stats["hash_identical"] / loaded, 1),
        "fields": {k[6:]: v for k, v in stats.items() if k.startswith("field:")},
    }))
    for row in fails[:15]:
        print("FAIL", *row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
