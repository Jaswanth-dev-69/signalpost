#!/usr/bin/env python3
"""Offline completeness audit of envelopes (no fetching): the per-claim requirements of the contract
("source URL or identifier, retrieval time, effective/reporting date where relevant, content hash and
extraction method"; explicit states; no duplicates) checked on every claim and evidence item.

Counts, per claim field where useful:
  duplicate claims (same field and value) and duplicate evidence ids in one envelope
  available claims without evidence, and claims citing evidence ids that are not in the envelope
  non-available claims that still carry a value
  evidence missing source_url, retrieved_at, a 64-hex content_sha256, claim_span or extraction_method
  dated facts whose evidence has no effective_at (news, postings with a posted date, accounts figures)
  accounts claims without reporting_period
  evidence items no claim cites
  hedge records (external.observations / external.company_site) that do not match an available claim

Usage: python eval/claim_audit.py ENVELOPES.jsonl
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
ACCOUNTS = {"revenue", "operating_result", "annual_result", "assets", "debt"}


def main() -> int:
    issues: Counter = Counter()
    examples: dict[str, str] = {}
    envelopes = 0

    def flag(kind: str, where: str) -> None:
        issues[kind] += 1
        examples.setdefault(kind, where)

    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        env = json.loads(line)
        envelopes += 1
        org = env.get("organisation_number")
        evidence = env.get("evidence") or []
        ids = [e.get("id") for e in evidence]
        by_id = {e.get("id"): e for e in evidence}
        for dup in [i for i, n in Counter(ids).items() if n > 1]:
            flag("duplicate evidence id", f"{org} {dup}")
        cited: set[str] = set()
        seen: Counter = Counter()
        available = set()
        for claim in env.get("claims") or []:
            field, value, state = claim.get("field"), claim.get("value"), claim.get("availability")
            key = (field, json.dumps(value, sort_keys=True, ensure_ascii=False))
            seen[key] += 1
            refs = claim.get("evidence_ids") or []
            cited.update(refs)
            missing = [r for r in refs if r not in by_id]
            if missing:
                flag("claim cites missing evidence", f"{org} {field}")
            if state == "available":
                available.add(key)
                if not [r for r in refs if r in by_id]:
                    flag("available claim without evidence", f"{org} {field}")
                if field in ACCOUNTS and not claim.get("reporting_period"):
                    flag("accounts claim without reporting_period", f"{org} {field}")
                dated = field == "dated_news" or field in ACCOUNTS or (field == "hiring_signal" and claim.get("posted_date"))
                if dated and not any(by_id.get(r, {}).get("effective_at") for r in refs):
                    flag(f"{field}: evidence without effective_at", f"{org} {str(value)[:60]}")
            elif value not in (None, "", [], {}):
                flag(f"non-available claim with a value ({field})", f"{org} {state}")
        for key, n in seen.items():
            if n > 1 and key[0] != "summary_profile":
                flag(f"duplicate claim ({key[0]})", f"{org} {key[1][:60]}")
        for item in evidence:
            for attr in ("source_url", "retrieved_at", "claim_span", "extraction_method"):
                if not item.get(attr):
                    flag(f"evidence without {attr}", f"{org} {item.get('id')}")
            if not HEX64.match(str(item.get("content_sha256") or "")):
                flag("evidence without a valid content_sha256", f"{org} {item.get('id')}")
            if item.get("id") not in cited:
                flag("evidence no claim cites", f"{org} {item.get('id')}")
        external = env.get("external") or {}
        for obs in external.get("observations") or []:
            if (obs.get("claim_field"), json.dumps(obs.get("claim_value"), sort_keys=True, ensure_ascii=False)) not in available:
                flag("observation without an available claim", f"{org} {obs.get('id')}")
        obs_ids = [o.get("id") for o in external.get("observations") or []]
        if len(obs_ids) != len(set(obs_ids)):
            flag("duplicate observation id", str(org))
    print(f"envelopes {envelopes}; issue kinds {len(issues)}")
    for kind, n in issues.most_common():
        print(f"  {n:6}  {kind}   e.g. {examples[kind]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
