#!/usr/bin/env python3
"""Validates envelopes against OUTPUT_CONTRACT.md schema and completeness rules."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ALLOWED_STATES = {"available", "not_available", "blocked", "not_applicable", "ambiguous", "failed"}


def validate_envelope(env: dict[str, Any], index: int) -> list[str]:
    errors = []
    org = env.get("organisation_number")
    if not org or not isinstance(org, str) or not org.isdigit() or len(org) != 9:
        errors.append(f"Row {index}: invalid organisation_number: {org!r}")

    run = env.get("run")
    if not isinstance(run, dict):
        errors.append(f"Row {index} ({org}): missing 'run' object")
    else:
        for k in ("run_id", "started_at", "completed_at", "terminal_status"):
            if not run.get(k):
                errors.append(f"Row {index} ({org}): run missing required key {k!r}")
        if run.get("terminal_status") and run.get("terminal_status") != "completed":
            # OUTPUT_CONTRACT.md: every input company gets one terminal envelope, "completed".
            errors.append(f"Row {index} ({org}): terminal_status {run.get('terminal_status')!r} must be 'completed'")

    claims = env.get("claims")
    if not isinstance(claims, list):
        errors.append(f"Row {index} ({org}): 'claims' must be a list")
    else:
        for c_idx, claim in enumerate(claims):
            if not isinstance(claim, dict):
                errors.append(f"Row {index} ({org}) claim {c_idx}: claim must be an object")
                continue
            field = claim.get("field")
            if not field or not isinstance(field, str):
                errors.append(f"Row {index} ({org}) claim {c_idx}: missing or non-string 'field'")
            
            avail = claim.get("availability")
            if avail not in ALLOWED_STATES:
                errors.append(f"Row {index} ({org}) claim '{field}': invalid availability {avail!r}. Must be one of {ALLOWED_STATES}")

            confidence = claim.get("confidence")
            if confidence is None or not (0.0 <= float(confidence) <= 1.0):
                errors.append(f"Row {index} ({org}) claim '{field}': confidence {confidence!r} not in [0.0, 1.0]")

            ev_ids = claim.get("evidence_ids")
            if not isinstance(ev_ids, list):
                errors.append(f"Row {index} ({org}) claim '{field}': 'evidence_ids' must be a list")

    evidence_list = env.get("evidence")
    if not isinstance(evidence_list, list):
        errors.append(f"Row {index} ({org}): 'evidence' must be a list")
    else:
        ev_ids_seen = set()
        for e_idx, ev in enumerate(evidence_list):
            if not isinstance(ev, dict):
                errors.append(f"Row {index} ({org}) evidence {e_idx}: evidence item must be an object")
                continue
            e_id = ev.get("id")
            if not e_id or not isinstance(e_id, str):
                errors.append(f"Row {index} ({org}) evidence {e_idx}: missing or non-string 'id'")
            else:
                ev_ids_seen.add(e_id)

            url = ev.get("source_url")
            if not url or not isinstance(url, str) or not re.match(r"^https?://", url):
                errors.append(f"Row {index} ({org}) evidence '{e_id}': invalid source_url: {url!r}")

            time_str = ev.get("retrieved_at")
            if not time_str or not isinstance(time_str, str):
                errors.append(f"Row {index} ({org}) evidence '{e_id}': missing or non-string 'retrieved_at'")

            h = ev.get("content_sha256")
            if not h or not isinstance(h, str) or len(h) != 64:
                errors.append(f"Row {index} ({org}) evidence '{e_id}': invalid content_sha256: {h!r}")

        # Check claim evidence_ids exist in evidence list
        if isinstance(claims, list):
            for claim in claims:
                for target_id in claim.get("evidence_ids", []):
                    if target_id not in ev_ids_seen:
                        errors.append(f"Row {index} ({org}) claim '{claim.get('field')}': evidence_id {target_id!r} not found in evidence[]")

    ops = env.get("operations")
    if not isinstance(ops, dict):
        errors.append(f"Row {index} ({org}): missing 'operations' object")
    else:
        for k in ("requests", "runtime_ms", "third_party_cost_usd"):
            if k not in ops:
                errors.append(f"Row {index} ({org}): operations missing key {k!r}")

    return errors


def validate_file(envelopes_path: Path, expected_orgs: list[str]) -> dict[str, Any]:
    lines = [line.strip() for line in envelopes_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    total_envelopes = len(lines)
    all_errors = []

    seen_orgs = []
    for idx, line in enumerate(lines, start=1):
        try:
            env = json.loads(line)
        except Exception as exc:
            all_errors.append(f"Row {idx}: invalid JSON - {exc}")
            continue
        org = env.get("organisation_number")
        seen_orgs.append(org)
        row_errors = validate_envelope(env, idx)
        all_errors.extend(row_errors)

    completeness_checks = {
        "exact_count_matches": total_envelopes == len(expected_orgs),
        "expected_count": len(expected_orgs),
        "emitted_count": total_envelopes,
        "unique_orgs": len(seen_orgs) == len(set(seen_orgs)),
        "matches_input_org_set": set(seen_orgs) == set(expected_orgs),
        "order_matches_input": seen_orgs == expected_orgs,
    }

    passed = (
        len(all_errors) == 0
        and completeness_checks["exact_count_matches"]
        and completeness_checks["unique_orgs"]
        and completeness_checks["matches_input_org_set"]
    )

    return {
        "passed": passed,
        "completeness": completeness_checks,
        "error_count": len(all_errors),
        "errors": all_errors[:20],
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python schema_validator.py <envelopes.jsonl> <input_organisations>")
        sys.exit(1)

    env_p = Path(sys.argv[1])
    orgs_p = Path(sys.argv[2])
    
    # Read input orgs
    raw_input = orgs_p.read_text(encoding="utf-8")
    if orgs_p.suffix == ".json":
        data = json.loads(raw_input)
        in_orgs = data if isinstance(data, list) else data.get("organisation_numbers", [])
    elif orgs_p.suffix == ".jsonl":
        in_orgs = [json.loads(line)["organisation_number"] for line in raw_input.splitlines() if line.strip()]
    else:
        in_orgs = [line.strip() for line in raw_input.splitlines() if line.strip()]

    report = validate_file(env_p, in_orgs)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["passed"] else 1)
