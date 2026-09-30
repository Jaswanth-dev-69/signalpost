#!/usr/bin/env python3
"""Builds an independent reference ground truth dataset for recall evaluation."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def fetch_raw_json(url: str, timeout: float = 10.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "signalpost-eval-auditor/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    return None


def build_ground_truth(input_companies_path: Path, output_ref_path: Path, sample_deep_count: int = 20) -> dict[str, Any]:
    lines = [json.loads(line) for line in input_companies_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    
    reference: dict[str, Any] = {
        "metadata": {
            "total_companies": len(lines),
            "deep_audited_count": min(sample_deep_count, len(lines)),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "companies": {},
    }

    print(f"Building independent reference set for {len(lines)} companies ({sample_deep_count} deep-audited)...")

    # Pick systematic sample for deep audit (every N-th company)
    step = max(1, len(lines) // sample_deep_count)
    deep_indices = set(range(0, len(lines), step))

    for idx, row in enumerate(lines):
        org = row["organisation_number"]
        is_deep = idx in deep_indices and len(reference["companies"]) < sample_deep_count

        company_ref: dict[str, Any] = {
            "organisation_number": org,
            "legal_name": row.get("name"),
            "legal_form": row.get("legal_form"),
            "municipality": row.get("municipality"),
            "industry_code": row.get("industry_code"),
            "industry_label": row.get("industry_label"),
            "registry_employees": row.get("employees"),
            "bankrupt": bool(row.get("bankrupt")),
            "liquidating": bool(row.get("liquidating")),
            "registry_website": row.get("website") or None,
            "latest_submitted_accounts": row.get("latest_submitted_accounts"),
            "deep_audit": is_deep,
        }

        if is_deep:
            print(f"  [{len([c for c in reference['companies'].values() if c.get('deep_audit')]) + 1}/{sample_deep_count}] Deep checking org {org} ({row.get('name')})...")
            # Fetch raw roles directly from BRREG
            roles_data = fetch_raw_json(f"https://data.brreg.no/enhetsregisteret/api/enheter/{org}/roller")
            true_roles = []
            if roles_data:
                for group in roles_data.get("rollegrupper", []):
                    for item in group.get("roller", []):
                        if not item.get("avregistrert"):
                            p = item.get("person", {}).get("navn", {})
                            name = " ".join(filter(None, [p.get("fornavn"), p.get("mellomnavn"), p.get("etternavn")]))
                            role = item.get("type", {}).get("beskrivelse") or item.get("type", {}).get("kode")
                            if name:
                                true_roles.append({"name": name, "role": role})
            company_ref["true_roles"] = true_roles

            # Fetch raw accounts directly from Regnskapsregisteret
            acc_data = fetch_raw_json(f"https://data.brreg.no/regnskapsregisteret/regnskap/{org}")
            true_financials = None
            if acc_data and isinstance(acc_data, list) and len(acc_data) > 0:
                first = acc_data[0]
                dr = first.get("resultatregnskapResultat", {}).get("driftsresultat", {})
                true_financials = {
                    "revenue": dr.get("driftsinntekter", {}).get("sumDriftsinntekter"),
                    "operating_result": dr.get("driftsresultat"),
                    "annual_result": first.get("resultatregnskapResultat", {}).get("aarsresultat"),
                    "assets": first.get("eiendeler", {}).get("sumEiendeler"),
                    "debt": first.get("egenkapitalGjeld", {}).get("gjeldOversikt", {}).get("sumGjeld"),
                    "period_from": first.get("regnskapsperiode", {}).get("fraDato"),
                    "period_to": first.get("regnskapsperiode", {}).get("tilDato"),
                }
            company_ref["true_financials"] = true_financials

            # Fetch subunits
            sub_data = fetch_raw_json(f"https://data.brreg.no/enhetsregisteret/api/underenheter?overordnetEnhet={org}")
            true_subunits = []
            if sub_data and "_embedded" in sub_data:
                for item in sub_data["_embedded"].get("underenheter", []):
                    true_subunits.append({
                        "name": item.get("navn"),
                        "org": item.get("organisasjonsnummer"),
                    })
            company_ref["true_subunits"] = true_subunits

            # Delay to stay well within BRREG rate limits
            time.sleep(0.3)

        reference["companies"][org] = company_ref

    output_ref_path.parent.mkdir(parents=True, exist_ok=True)
    output_ref_path.write_text(json.dumps(reference, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved independent reference set with {len(reference['companies'])} companies to {output_ref_path}")
    return reference


if __name__ == "__main__":
    in_p = Path("entry-companies.jsonl")
    out_p = Path("eval/ground_truth_reference.json")
    build_ground_truth(in_p, out_p, sample_deep_count=20)
