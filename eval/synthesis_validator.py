#!/usr/bin/env python3
"""Validates that synthesis summaries are strictly grounded in verified evidence with valid citations."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


def validate_synthesis_envelope(env: dict[str, Any]) -> list[str]:
    errors = []
    org = env.get("organisation_number")
    claims_map = {c["field"]: c for c in env.get("claims", [])}
    evidence_ids = {ev["id"] for ev in env.get("evidence", [])}

    summary_claim = claims_map.get("summary_profile")
    if not summary_claim or summary_claim.get("availability") != "available":
        return [f"Org {org}: missing summary_profile claim"]

    summary_text = str(summary_claim.get("value") or "")
    if not summary_text:
        return [f"Org {org}: summary_profile is empty"]

    # 1. Check evidence_ids
    cited_ids = summary_claim.get("evidence_ids", [])
    if not cited_ids:
        errors.append(f"Org {org}: summary_profile has no cited evidence_ids")
    for eid in cited_ids:
        if eid not in evidence_ids:
            errors.append(f"Org {org}: cited evidence_id {eid!r} not in envelope evidence list")

    # 2. Check factual grounding of numbers in summary
    # Check revenue
    rev_claim = claims_map.get("revenue")
    if rev_claim and rev_claim.get("availability") == "available" and rev_claim.get("value") is not None:
        rev_val = int(rev_claim["value"])
        rev_str = f"{rev_val:,.0f}"
        if "revenue of" in summary_text and rev_str not in summary_text:
            errors.append(f"Org {org}: summary revenue statement does not match claim value {rev_val}")

    # Check employees
    emp_claim = claims_map.get("registry_employees")
    if emp_claim and emp_claim.get("availability") == "available" and emp_claim.get("value") is not None:
        emp_val = emp_claim["value"]
        if f"records {emp_val} employee" not in summary_text:
            errors.append(f"Org {org}: summary employee statement does not match claim value {emp_val}")

    # Check org number in text
    if org not in summary_text:
        errors.append(f"Org {org}: summary does not state correct organisation number")

    return errors


def validate_synthesis_file(envelopes_path: Path) -> dict[str, Any]:
    lines = [json.loads(line) for line in envelopes_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    all_errors = []
    validated_count = 0

    for idx, env in enumerate(lines, start=1):
        errs = validate_synthesis_envelope(env)
        if errs:
            all_errors.extend(errs)
        else:
            validated_count += 1

    passed = len(all_errors) == 0
    return {
        "passed": passed,
        "total_envelopes": len(lines),
        "validated_grounded_count": validated_count,
        "error_count": len(all_errors),
        "errors": all_errors[:20],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python synthesis_validator.py <envelopes.jsonl>")
        sys.exit(1)
    rep = validate_synthesis_file(Path(sys.argv[1]))
    print(json.dumps(rep, indent=2))
    sys.exit(0 if rep["passed"] else 1)
