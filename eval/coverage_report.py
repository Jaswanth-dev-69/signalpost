#!/usr/bin/env python3
"""Coverage and state summary for an envelopes file (plus its .profiles.jsonl when present).

Usage: python eval/coverage_report.py <envelopes.jsonl>
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

WEB = ("official_website", "social_profiles", "dated_news", "job_postings", "company_description")


def main() -> int:
    path = Path(sys.argv[1])
    envelopes = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    states: dict[str, Counter] = defaultdict(Counter)
    methods: Counter = Counter()
    facts: Counter = Counter()
    for env in envelopes:
        for claim in env["claims"]:
            states[claim["field"]][claim["availability"]] += 1
            if claim["field"] == "official_website" and claim["availability"] == "available":
                methods[claim.get("verification_method", "?")] += 1
            if claim["field"] in ("social_profiles", "dated_news", "job_postings") and claim["availability"] == "available":
                facts[claim["field"]] += len(claim["value"] or [])
    n = len(envelopes)
    out = {
        "companies": n,
        "coverage_pct": {f: round(100 * states[f]["available"] / n, 1) for f in WEB},
        "website_verification_methods": dict(methods),
        "facts_published": dict(facts),
        "requests_per_company": round(sum(e["operations"]["requests"] for e in envelopes) / n, 1),
        "envelopes_with_errors": sum(1 for e in envelopes if e["errors"]),
        "states": {f: dict(c) for f, c in sorted(states.items())},
    }
    profiles_path = path.with_suffix(".profiles.jsonl")
    if profiles_path.exists():
        discovery = Counter()
        disc_requests = []
        for line in profiles_path.read_text(encoding="utf-8").splitlines():
            profile = json.loads(line)
            value = ((profile.get("evidence") or {}).get("website") or {}).get("value") or {}
            if value.get("discovery_method") and (value.get("identity_assessment") or {}).get("publishable"):
                discovery[value["discovery_method"]] += 1
            if "discovery" in (profile.get("web_run") or {}):
                disc_requests.append(profile["web_run"]["discovery"].get("requests", 0))
        out["discovered_websites"] = dict(discovery)
        if disc_requests:
            out["discovery_requests_per_attempted_company"] = round(sum(disc_requests) / len(disc_requests), 1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
