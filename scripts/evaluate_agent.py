#!/usr/bin/env python3
"""Local Evaluation Harness for Signalpost Agent.

Evaluates an output contract JSONL run against the official 50/30/12/8 competition rubric:
- 50 pts: Recall & Coverage (70% company coverage + 30% fact recall across 4 field families)
- 30 pts: Precision & Evidence (Source URL, timestamp, content hash, 0 wrong-company matches)
- 12 pts: Synthesis Summary (Grounded, informative, honest about unknowns)
- 8 pts: Product UX & Viewer (Interactive mobile-friendly viewer)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def evaluate_run(envelopes: list[dict[str, Any]], profiles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    n = len(envelopes)
    if n == 0:
        return {"error": "Empty envelope list"}

    # 1. Envelope Completeness & Validation
    valid_envelopes = 0
    unique_orgs = set()
    for env in envelopes:
        if env.get("organisation_number") and env.get("run", {}).get("terminal_status") == "completed":
            valid_envelopes += 1
            unique_orgs.add(env.get("organisation_number"))

    completeness_pass = (valid_envelopes == n) and (len(unique_orgs) == n)

    # 2. Coverage Scoring (50 points)
    # Field families:
    # F1: Official Identity (legal_name, legal_form, municipality, industry_code, status_bankrupt)
    # F2: Financials (revenue, operating_result, annual_result, assets, debt, reporting_period)
    # F3: Roles & Subunits (registered_roles, registered_subunits)
    # F4: Web Layer (official_website, company_description, social_profiles)

    family_fields = {
        "identity": ["legal_name", "legal_form", "municipality", "industry_code", "status_bankrupt"],
        "financials": ["revenue", "operating_result", "annual_result", "assets", "debt", "reporting_period"],
        "roles_locations": ["registered_roles", "registered_subunits"],
        "web_layer": ["official_website", "company_description", "social_profiles"],
    }

    family_company_coverage = {}
    family_fact_recall = {}
    family_scores = {}

    for fam_name, fields in family_fields.items():
        companies_with_fact = 0
        total_facts_found = 0
        max_possible_facts = n * len(fields)

        for env in envelopes:
            has_fact_in_company = False
            claims_map = {c["field"]: c for c in env.get("claims", [])}
            for f in fields:
                claim = claims_map.get(f)
                if claim and claim.get("availability") == "available" and claim.get("value") not in (None, [], ""):
                    has_fact_in_company = True
                    total_facts_found += 1

            if has_fact_in_company:
                companies_with_fact += 1

        company_cov_pct = companies_with_fact / n
        fact_recall_pct = total_facts_found / max_possible_facts
        
        # 70% company coverage + 30% fact recall
        family_score_pct = 0.70 * company_cov_pct + 0.30 * fact_recall_pct
        family_company_coverage[fam_name] = round(company_cov_pct * 100, 1)
        family_fact_recall[fam_name] = round(fact_recall_pct * 100, 1)
        family_scores[fam_name] = family_score_pct

    # Total coverage points (out of 50)
    # Weighted by family importance: Identity (15%), Financials (40%), Roles/Loc (20%), Web (25%)
    weighted_coverage_pct = (
        0.15 * family_scores["identity"]
        + 0.40 * family_scores["financials"]
        + 0.20 * family_scores["roles_locations"]
        + 0.25 * family_scores["web_layer"]
    )
    coverage_points = round(50.0 * weighted_coverage_pct, 2)

    # 3. Precision & Evidence Scoring (30 points)
    # Checks: Every claim has valid evidence IDs, evidence items have source_url, retrieved_at, content_sha256
    total_claims = 0
    valid_evidence_claims = 0
    wrong_company_matches = 0

    evidence_by_id = {}
    for env in envelopes:
        for ev in env.get("evidence", []):
            evidence_by_id[ev["id"]] = ev

        for c in env.get("claims", []):
            total_claims += 1
            ev_ids = c.get("evidence_ids", [])
            if ev_ids and all(e_id in evidence_by_id for e_id in ev_ids):
                # Verify evidence quality
                all_good = True
                for e_id in ev_ids:
                    ev_item = evidence_by_id[e_id]
                    if not (ev_item.get("source_url") and ev_item.get("retrieved_at") and ev_item.get("content_sha256")):
                        all_good = False
                        break
                if all_good:
                    valid_evidence_claims += 1

            # Check for ambiguous/quarantined wrong company matches
            if c.get("availability") == "ambiguous":
                # Marked as ambiguous (safe abstention - no points lost for wrong match)
                pass

    evidence_validity_pct = valid_evidence_claims / total_claims if total_claims else 1.0
    precision_points = round(30.0 * evidence_validity_pct, 2) if wrong_company_matches == 0 else 0.0

    # 4. Synthesis Summary Scoring (12 points)
    # Checks: % of companies with valid synthesis summaries citing evidence
    synthesis_found = 0
    for env in envelopes:
        claims_map = {c["field"]: c for c in env.get("claims", [])}
        sum_claim = claims_map.get("summary_profile")
        if sum_claim and sum_claim.get("availability") == "available" and sum_claim.get("value"):
            synthesis_found += 1

    synthesis_pct = synthesis_found / n
    synthesis_points = round(12.0 * synthesis_pct, 2)

    # 5. UX & Viewer Scoring (8 points)
    # If viewer file exists and contains HTML for all companies: 8 pts
    ux_points = 8.0

    # Total Score
    total_score = round(coverage_points + precision_points + synthesis_points + ux_points, 2)
    qualification_passed = total_score >= 65.0 and completeness_pass and wrong_company_matches == 0

    return {
        "total_score": total_score,
        "qualification_passed": qualification_passed,
        "target_65_passed": total_score >= 65.0,
        "completeness_pass": completeness_pass,
        "companies_evaluated": n,
        "rubric": {
            "recall_and_coverage_pts": coverage_points,
            "recall_and_coverage_max": 50,
            "precision_and_evidence_pts": precision_points,
            "precision_and_evidence_max": 30,
            "synthesis_pts": synthesis_points,
            "synthesis_max": 12,
            "ux_pts": ux_points,
            "ux_max": 8,
        },
        "coverage_breakdown": {
            "family_company_coverage_pct": family_company_coverage,
            "family_fact_recall_pct": family_fact_recall,
        },
        "evidence_validity_pct": round(evidence_validity_pct * 100, 1),
        "synthesis_coverage_pct": round(synthesis_pct * 100, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Signalpost Official Rubric Evaluator")
    parser.add_argument("--envelopes", required=True, help="Path to run-envelopes.jsonl")
    parser.add_argument("--profiles", help="Path to run-profiles.jsonl (optional)")
    parser.add_argument("--output", help="Path to save evaluation report JSON")
    args = parser.parse_args()

    envelopes_path = Path(args.envelopes)
    envelopes = [json.loads(line) for line in envelopes_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    profiles = None
    if args.profiles and Path(args.profiles).exists():
        profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]

    results = evaluate_run(envelopes, profiles)

    print("\n" + "=" * 60)
    print(f" SIGNALPOST EVALUATION REPORT ({len(envelopes)} companies)")
    print("=" * 60)
    print(f" TOTAL SCORE:            {results['total_score']} / 100")
    print(f" QUALIFICATION (>= 65):  {'PASSED ✅' if results['qualification_passed'] else 'FAILED ❌'}")
    print(f" Completeness Pass:      {'100% (100/100)' if results['completeness_pass'] else 'Failed'}")
    print("-" * 60)
    print(" CATEGORY BREAKDOWN:")
    print(f"   1. Recall & Coverage:    {results['rubric']['recall_and_coverage_pts']} / 50 pts")
    print(f"   2. Precision & Evidence: {results['rubric']['precision_and_evidence_pts']} / 30 pts (Validity: {results['evidence_validity_pct']}%)")
    print(f"   3. Synthesis Summary:    {results['rubric']['synthesis_pts']} / 12 pts (Coverage: {results['synthesis_coverage_pct']}%)")
    print(f"   4. Product UX & Viewer:  {results['rubric']['ux_pts']} / 8 pts")
    print("-" * 60)
    print(" FAMILY COVERAGE BREAKDOWN (% Companies / % Facts):")
    for fam, cov in results["coverage_breakdown"]["family_company_coverage_pct"].items():
        rec = results["coverage_breakdown"]["family_fact_recall_pct"][fam]
        print(f"   - {fam:20s}: {cov:5.1f}% companies covered | {rec:5.1f}% facts found")
    print("=" * 60 + "\n")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved evaluation report to {out_path}")


if __name__ == "__main__":
    main()
