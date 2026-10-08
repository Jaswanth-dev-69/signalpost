#!/usr/bin/env python3
"""Website discovery measured on labelled companies (W1b).

Companies whose registry record declares a homepage on a domain no other entity declares are the
labels: the declared registered domain is the company's own site. Each sampled company is treated
as if it declared nothing. Every candidate from the current generator and from a challenger
generator is fetched (no early stop, so a wrong domain that would pass is always seen) and judged by
the unchanged strict proof for discovered domains. Raw homepage and identity-page bytes are kept
(gzip JSON per company) so proof-detection changes can be re-scored offline without re-fetching.

Usage:
  python eval/discovery_labelled.py --table universe_registry.jsonl --out DIR [--per-stratum none=200,5-19=120,20-99=60,100+=20]
         [--seed 20261008] [--workers 12] [--challenger module:function]
The table is one JSON object per company: org, name, form, domain, declarants, email, kommune, employees.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import importlib
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent import domain_solver as ds  # noqa: E402
from norway_company_agent.identity import DECLARED_DOMAIN_REJECT, apply_website_identity_gate  # noqa: E402
from norway_company_agent.webclaims import registered_domain  # noqa: E402
from norway_company_agent.website import fetch_website  # noqa: E402


def bucket(employees: Any) -> str:
    try:
        count = int(employees)
    except (TypeError, ValueError):
        return "none"
    return "none" if count <= 0 else "5-19" if count < 20 else "20-99" if count < 100 else "100+"


def profile_of(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "organisation_number": row["org"], "name": row["name"], "legal_form": row["form"],
        "municipality": row.get("kommune") or None, "website": None,
        "evidence": {"registry": {"value": {"epostadresse": row.get("email") or ""}}},
    }


def candidate_plan(profile: dict[str, Any], challenger) -> list[dict[str, Any]]:
    """Ordered candidates of both generators, each tagged with its rank in each list."""
    current: list[str] = []
    email = ds.email_domain(profile)
    if email:
        current.append(f"www.{email}")
    current.extend(u.removeprefix("https://") for u in ds.generate_candidate_domains(profile["name"]))
    new: list[str] = []
    if email:
        new.append(f"www.{email}")
    if challenger:
        new.extend(u.removeprefix("https://") for u in challenger(profile["name"]))
    plan: dict[str, dict[str, Any]] = {}
    for label, items in (("current", current), ("challenger", new)):
        seen: set[str] = set()
        rank = 0
        for item in items:
            key = item.removeprefix("www.")
            if key in seen:
                continue
            seen.add(key)
            plan.setdefault(key, {"key": key, "url": item, "rank": {}})["rank"][label] = rank
            rank += 1
    return list(plan.values())


def judge(profile: dict[str, Any], candidate: dict[str, Any], timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    record, metrics = fetch_website("https://" + candidate["url"], timeout=timeout)
    if record.get("status") == "blocked" and "did not resolve" in str(record.get("note") or ""):
        record, more = fetch_website("https://" + candidate["key"], timeout=timeout)
        metrics = {"requests": metrics.get("requests", 0) + more.get("requests", 0)}
    out = {**candidate, "status": record.get("status"), "note": str(record.get("note") or "")[:160],
           "requests": metrics.get("requests", 0), "seconds": round(time.monotonic() - started, 2)}
    if record.get("status") != "available":
        return out
    gated = apply_website_identity_gate(profile, record)["website"]
    value = gated.get("value") or {}
    accepted, reason = ds.strict_discovered_proof(profile, value)
    out.update({
        "final_url": value.get("final_url"), "final_domain": registered_domain(value.get("final_url") or ""),
        "org_numbers_on_site": value.get("org_numbers_on_site") or [], "proof": accepted, "proof_reason": reason,
        "identity_status": (value.get("identity_assessment") or {}).get("status"),
        "title": str(value.get("title") or "")[:160],
    })
    home = value.get("_homepage") or {}
    raw_pages = [{"url": home.get("url"), "raw": base64.b64encode(home.get("raw") or b"").decode()}]
    raw_pages += [{"url": p.get("url"), "raw": base64.b64encode(p.get("raw") or b"").decode()} for p in value.get("_subpages") or []]
    out["_raw"] = raw_pages
    out["_value"] = {k: v for k, v in value.items() if not k.startswith("_")}
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--per-stratum", default="none=200,5-19=120,20-99=60,100+=20")
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument("--challenger", help="module:function generating candidate URLs from a legal name")
    parser.add_argument("--challenger-path", help="directory to import the challenger module from")
    args = parser.parse_args()
    challenger = None
    if args.challenger:
        if args.challenger_path:
            sys.path.insert(0, args.challenger_path)
        module, function = args.challenger.split(":")
        challenger = getattr(importlib.import_module(module), function)
    rows = [json.loads(line) for line in Path(args.table).read_text(encoding="utf-8").splitlines() if line.strip()]
    labelled = [r for r in rows if r.get("domain") and r.get("declarants") == 1 and r["domain"] not in DECLARED_DOMAIN_REJECT
                and r.get("form") not in ds.SKIP_DISCOVERY_FORMS]
    rng = random.Random(args.seed)
    strata: dict[str, list[dict]] = {}
    for row in labelled:
        strata.setdefault(bucket(row.get("employees")), []).append(row)
    sample: list[dict] = []
    for spec in args.per_stratum.split(","):
        name, count = spec.split("=")
        sample.extend({**row, "stratum": name} for row in rng.sample(strata.get(name, []), min(int(count), len(strata.get(name, [])))))
    out = Path(args.out)
    (out / "raw").mkdir(parents=True, exist_ok=True)

    def run(row: dict[str, Any]) -> dict[str, Any]:
        profile = profile_of(row)
        results = [judge(profile, candidate, args.timeout) for candidate in candidate_plan(profile, challenger)]
        raw = {r["key"]: {"raw": r.pop("_raw"), "value": r.pop("_value")} for r in results if "_raw" in r}
        if raw:
            with gzip.open(out / "raw" / f"{row['org']}.json.gz", "wt", encoding="utf-8") as handle:
                json.dump(raw, handle, ensure_ascii=False)
        return {"org": row["org"], "name": row["name"], "form": row["form"], "kommune": row.get("kommune"),
                "stratum": row["stratum"], "declared_domain": row["domain"], "email": row.get("email"), "candidates": results}

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool, (out / "results.jsonl").open("w", encoding="utf-8") as handle:
        for done, result in enumerate(pool.map(run, sample), 1):
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            if done % 50 == 0:
                print(f"{done}/{len(sample)} {time.monotonic() - started:.0f}s", flush=True)
    print(f"done {len(sample)} companies in {time.monotonic() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
