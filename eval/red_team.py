#!/usr/bin/env python3
"""Wrong-company red team evaluation: tests high-risk disambiguation challenges."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.domain_solver import discover_website_by_domain_search
from norway_company_agent.identity import apply_website_identity_gate
from norway_company_agent.website import fetch_website


def select_red_team_companies(universe_path: Path, count: int = 35) -> list[dict[str, Any]]:
    generic_terms = {"BYGG", "EIENDOM", "INVEST", "HOLDING", "CONSULTING", "SERVICES", "SERVICE", "NORDIC", "GRUPPEN", "DRIFT"}
    candidates = []
    seen = set()

    with open(universe_path, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            name = row.get("name", "")
            words = name.replace("AS", "").replace("ASA", "").strip().split()
            # 1. Single short token (1-5 chars) - maximum ambiguity risk (e.g. DDB, DELA, SOM)
            if len(words) == 1 and 2 <= len(words[0]) <= 6:
                if name not in seen:
                    seen.add(name)
                    candidates.append({"type": "single_short_token", **row})
            # 2. Generic compound name (e.g. ARNESEN EIENDOM AS, BORGEN GRUPPEN AS)
            elif len(words) == 2 and any(w in generic_terms for w in words):
                if name not in seen and len(candidates) < count:
                    seen.add(name)
                    candidates.append({"type": "generic_compound", **row})
            if len(candidates) >= count:
                break
    return candidates


def run_red_team(universe_path: Path, output_report_path: Path, count: int = 35) -> dict[str, Any]:
    companies = select_red_team_companies(universe_path, count)
    print(f"Red-team testing {len(companies)} high-risk ambiguous entities...", flush=True)

    results = []
    false_positives = []
    safe_abstentions = 0
    exact_verified = 0

    for idx, c in enumerate(companies, 1):
        org = c["organisation_number"]
        name = c["name"]
        muni = c.get("municipality", "")
        c_type = c.get("type", "generic")

        print(f"  [{idx:2d}/{len(companies)}] Testing {org} | {name} ({muni})...", flush=True)

        # 1. Test domain discovery
        discovered_web, _ = discover_website_by_domain_search(c, timeout=6.0)

        # 2. Audit verdict
        is_false_positive = False
        verdict = "SAFE_ABSTAIN"
        matched_url = None
        evidence_found = []

        if discovered_web and (discovered_web.get("value") or {}).get("identity_assessment", {}).get("publishable"):
            matched_url = discovered_web.get("source_url")
            val = discovered_web.get("value", {})
            html_text = str(val.get("main_text_excerpt") or "") + " " + str(val.get("title") or "")
            
            # Audit: did the page REALLY belong to this company?
            has_org = org in html_text
            has_muni = muni.casefold() in html_text.casefold()
            
            if has_org:
                verdict = "VERIFIED_EXACT"
                exact_verified += 1
                evidence_found.append("org_number_on_page")
            elif has_muni and len(name.split()) >= 2:
                verdict = "VERIFIED_EXACT"
                exact_verified += 1
                evidence_found.append("legal_name_and_municipality_match")
            else:
                # FALSE POSITIVE: Page matched on a single generic word without org or municipality proof!
                verdict = "FALSE_POSITIVE_ATTRIBUTION"
                is_false_positive = True
                false_positives.append({
                    "organisation_number": org,
                    "name": name,
                    "municipality": muni,
                    "attributed_url": matched_url,
                    "title": val.get("title"),
                    "reason": "Matched domain without org number or municipality proof",
                })
        else:
            safe_abstentions += 1

        print(f"       -> Result: {verdict} ({matched_url or 'no site published'})", flush=True)
        results.append({
            "org": org,
            "name": name,
            "municipality": muni,
            "type": c_type,
            "verdict": verdict,
            "matched_url": matched_url,
            "evidence": evidence_found,
        })
        time.sleep(0.1)

    passed = len(false_positives) == 0

    report = {
        "passed": passed,
        "total_tested": len(companies),
        "exact_verified": exact_verified,
        "safe_abstentions": safe_abstentions,
        "false_positive_count": len(false_positives),
        "false_positives": false_positives,
        "details": results,
    }

    output_report_path.parent.mkdir(parents=True, exist_ok=True)
    output_report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 55, flush=True)
    print(" RED-TEAM DISAMBIGUATION AUDIT RESULTS", flush=True)
    print("=" * 55, flush=True)
    print(f" Companies Tested:       {len(companies)}", flush=True)
    print(f" Exact Verified Matches: {exact_verified}", flush=True)
    print(f" Safe Abstentions:       {safe_abstentions}", flush=True)
    print(f" False Positives:        {len(false_positives)} {'❌ (FAIL)' if not passed else '✅ (PASS)'}", flush=True)
    print(f" Report Saved:           {output_report_path}", flush=True)
    print("=" * 55 + "\n", flush=True)

    return report


if __name__ == "__main__":
    u_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/altf4/Desktop/signalpost/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl")
    rep_path = Path("eval/red_team_report.json")
    rep = run_red_team(u_path, rep_path, count=35)
    sys.exit(0 if rep["passed"] else 1)
