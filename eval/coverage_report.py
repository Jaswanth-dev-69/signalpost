#!/usr/bin/env python3
"""Coverage and state summary for an envelopes file (plus its .profiles.jsonl when present).

Usage: python eval/coverage_report.py <envelopes.jsonl>
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

WEB = ("official_website", "social_profile", "dated_news", "hiring_signal", "company_description")
PER_FACT = ("social_profile", "dated_news", "hiring_signal")


def main() -> int:
    path = Path(sys.argv[1])
    envelopes = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Per company and field: "available" when any claim of that field is available (fields with one
    # claim per fact repeat), otherwise the state of its single claim.
    states: dict[str, Counter] = defaultdict(Counter)
    methods: Counter = Counter()
    facts: Counter = Counter()
    kinds: Counter = Counter()
    for env in envelopes:
        company: dict[str, str] = {}
        for claim in env["claims"]:
            field, state = claim["field"], claim["availability"]
            if company.get(field) != "available":
                company[field] = state
            if field == "official_website" and state == "available":
                methods[claim.get("verification_method", "?")] += 1
            if field in PER_FACT and state == "available":
                facts[field] += 1
                if field == "hiring_signal":
                    kinds[claim.get("kind", "?")] += 1
        for field, state in company.items():
            states[field][state] += 1
    n = len(envelopes)
    out = {
        "companies": n,
        "coverage_pct": {f: round(100 * states[f]["available"] / n, 1) for f in WEB},
        "website_verification_methods": dict(methods),
        "facts_published": dict(facts),
        "hiring_signal_kinds": dict(kinds),
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
