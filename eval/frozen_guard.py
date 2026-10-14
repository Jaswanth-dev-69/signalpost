#!/usr/bin/env python3
"""Regression guard: summary (Synthesis) and viewer (UX) work must not change any other output.

Builds envelopes from the SAME saved profiles with the code at --base (exported from git) and with
the working tree, applies the working tree's summary step, and compares everything else. Allowed to
differ: the `summary_profile` claim, the top-level `summary`, `profile.synthesis_summary`, and the
claim fields listed in ADDED_FIELDS together with the evidence items only they cite (deliberate
contract additions, each listed here on purpose). Anything else that differs fails the guard:
another claim (field, value, availability, attributes or cited evidence), an evidence item, or any
other envelope field (state, modules, run, changes, refresh, errors, operations, external, profile).

Usage: python eval/frozen_guard.py --profiles RUN.profiles.jsonl [--base pre-v5]
"""
from __future__ import annotations

import argparse
import importlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_FIELD = "summary_profile"
# Claim fields added on purpose since pre-v5 (v5: what the register says the company does, its former
# names and the earlier years of the accounts response the agent already fetches).
ADDED_FIELDS = {"registered_activity", "former_names", "financial_history", "group_accounts"}
SUMMARY_KEYS = {"summary"}
T = "2026-10-14T00:00:00Z"


def load_contract(code_dir: Path):
    for name in [m for m in sys.modules if m == "norway_company_agent" or m.startswith("norway_company_agent.")]:
        del sys.modules[name]
    sys.path.insert(0, str(code_dir / "src"))
    try:
        contract = importlib.import_module("norway_company_agent.contract")
        synthesis = importlib.import_module("norway_company_agent.synthesis")
    finally:
        sys.path.pop(0)
    return contract.profile_to_contract_envelope, getattr(synthesis, "apply_envelope_summary", None)


def export_ref(ref: str, target: Path) -> None:
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", ref, "src"], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(target, filter="data")


def canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def claim_key(claim: dict[str, Any], evidence: dict[str, dict[str, Any]]) -> str:
    cited = [{k: v for k, v in (evidence.get(i) or {}).items() if k != "id"} for i in claim.get("evidence_ids") or []]
    return canon({**{k: v for k, v in claim.items() if k != "evidence_ids"}, "evidence": cited})


def compare(base_env: dict[str, Any], new_env: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    base_ev = {e["id"]: e for e in base_env.get("evidence") or []}
    new_ev = {e["id"]: e for e in new_env.get("evidence") or []}
    keep = lambda c: c.get("field") != SUMMARY_FIELD and c.get("field") not in ADDED_FIELDS  # noqa: E731
    base_claims = Counter(claim_key(c, base_ev) for c in base_env.get("claims") or [] if keep(c))
    new_claims = Counter(claim_key(c, new_ev) for c in new_env.get("claims") or [] if keep(c))
    for key in (base_claims - new_claims):
        problems.append(f"claim removed or changed: {key[:160]}")
    for key in (new_claims - base_claims):
        problems.append(f"claim added or changed: {key[:160]}")
    # Evidence: every base item unchanged; new items only if cited by added fields alone.
    for eid, item in base_ev.items():
        if canon(new_ev.get(eid)) != canon(item):
            problems.append(f"evidence changed: {eid} {canon(item)[:120]}")
    added_cites = {i for c in new_env.get("claims") or [] if c.get("field") in ADDED_FIELDS for i in c.get("evidence_ids") or []}
    other_cites = {i for c in new_env.get("claims") or [] if keep(c) for i in c.get("evidence_ids") or []}
    for eid in set(new_ev) - set(base_ev):
        if eid not in added_cites or eid in other_cites:
            problems.append(f"evidence added outside the allowed fields: {eid}")
    summary = [c for c in new_env.get("claims") or [] if c.get("field") == SUMMARY_FIELD]
    if not summary:
        problems.append("summary claim missing")
    elif any(i not in new_ev for i in summary[0].get("evidence_ids") or []):
        problems.append("summary cites evidence that is not in the envelope")
    # Every other envelope field.
    for key in sorted((set(base_env) | set(new_env)) - {"claims", "evidence", "profile"} - SUMMARY_KEYS):
        if canon(base_env.get(key)) != canon(new_env.get(key)):
            problems.append(f"envelope field changed: {key}")
    base_profile = {k: v for k, v in (base_env.get("profile") or {}).items() if k != "synthesis_summary"}
    new_profile = {k: v for k, v in (new_env.get("profile") or {}).items() if k != "synthesis_summary"}
    if canon(base_profile) != canon(new_profile):
        problems.append("embedded profile changed (other than synthesis_summary)")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", required=True, help="saved profiles (RUN.profiles.jsonl) to build both sides from")
    parser.add_argument("--base", default="pre-v5", help="git ref of the code before the S/U work")
    parser.add_argument("--new", default=None, help="git ref to build the new side from (default: the working tree)")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    profiles = [json.loads(line) for line in Path(args.profiles).read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        profiles = profiles[: args.limit]
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as tmp_new:
        export_ref(args.base, Path(tmp))
        base_build, _ = load_contract(Path(tmp))
        if args.new:
            export_ref(args.new, Path(tmp_new))
        new_build, new_summary = load_contract(Path(tmp_new) if args.new else ROOT)
        if new_summary is None:
            print("working tree has no apply_envelope_summary")
            return 1
        failures = Counter()
        examples: list[str] = []
        added = Counter()
        for profile in profiles:
            base_env = base_build(json.loads(json.dumps(profile)), run_id="guard", started_at=T, completed_at=T)
            new_env = new_build(json.loads(json.dumps(profile)), run_id="guard", started_at=T, completed_at=T)
            new_summary(new_env)
            for claim in new_env.get("claims") or []:
                if claim.get("field") in ADDED_FIELDS and claim.get("availability") == "available":
                    added[claim["field"]] += 1
            problems = compare(base_env, new_env)
            for problem in problems:
                failures[problem.split(":")[0]] += 1
            if problems and len(examples) < 8:
                examples.append(f"{profile.get('organisation_number')}: {problems[0]}")
    print(f"regression guard {args.new or 'working tree'} vs {args.base}: {len(profiles)} profiles; allowed additions (available claims): {dict(added)}")
    if failures:
        print("REGRESSION GUARD FAILED")
        for kind, count in failures.most_common():
            print(f"  {count:5} {kind}")
        print("\n".join(f"  e.g. {e}" for e in examples))
        return 1
    print("regression guard clean: no claim, evidence or other envelope field changed outside the summary and the listed additions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
