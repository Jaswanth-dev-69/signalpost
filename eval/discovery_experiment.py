#!/usr/bin/env python3
"""Re-run website discovery on stored profiles (companies without a registry homepage) to measure
a candidate-generation change without a full pipeline run. Prints every accepted site with its
proof so new name-based matches can be audited by hand.

Usage: python eval/discovery_experiment.py <profiles.jsonl> [workers] [limit]
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.domain_solver import discover_website_by_domain_search  # noqa: E402
from norway_company_agent.website import strip_private_fields  # noqa: E402


def main() -> int:
    path = Path(sys.argv[1])
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    profiles = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    targets = [p for p in profiles if not p.get("website")]
    if limit:
        targets = targets[:limit]
    started = time.monotonic()

    def run(profile):
        record, metrics = discover_website_by_domain_search(profile, timeout=6.0)
        strip_private_fields(record)
        return profile, record, metrics

    found, requests, candidates = [], 0, 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for profile, record, metrics in pool.map(run, targets):
            requests += metrics.get("requests", 0)
            candidates += metrics.get("candidates", 0)
            if record:
                value = record["value"]
                found.append({
                    "org": profile["organisation_number"],
                    "name": profile.get("name"),
                    "municipality": profile.get("municipality"),
                    "url": value.get("final_url"),
                    "method": value.get("discovery_method"),
                    "proof": (value.get("identity_assessment") or {}).get("reasons", [""])[0],
                    "title": (value.get("title") or "")[:80],
                })
    for item in found:
        print(f"  {item['org']} {item['name'][:32]:32s} {str(item['municipality'])[:12]:12s} {item['url'][:45]:45s} {item['proof'][:28]} | {item['title'][:50]}")
    summary = {
        "targets": len(targets),
        "found": len(found),
        "found_pct_of_targets": round(100 * len(found) / max(1, len(targets)), 2),
        "by_method": dict(Counter(i["method"] for i in found)),
        "by_proof": dict(Counter(i["proof"][:30] for i in found)),
        "requests_per_target": round(requests / max(1, len(targets)), 2),
        "candidates_per_target": round(candidates / max(1, len(targets)), 2),
        "seconds": round(time.monotonic() - started, 1),
    }
    print(json.dumps(summary))
    Path(str(path) + ".discovery.json").write_text(json.dumps({"summary": summary, "found": found}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
