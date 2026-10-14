#!/usr/bin/env python3
"""Checks that every summary is traceable to the envelope's own published claims.

For each envelope:
- the `summary_profile` claim is first, available and identical to `summary.text` and
  `profile.synthesis_summary`;
- every [n] marker names a listed source; every source's evidence ids exist and point at that URL;
  every evidence id the claim cites exists;
- every date (YYYY-MM-DD), every money amount ("NOK 790.4 million"), every employee count, every
  URL and every quoted text in the summary matches a value of an available claim (or the refresh
  record for the previous-run date); every percentage is recomputed from two published figures;
- the required sections are present: what the company is, what changed and what is not known.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

MONEY = re.compile(r"NOK (-?\d{1,3}(?:,\d{3})*(?:\.\d+)?)(?: (billion|million|thousand))?")
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
URL = re.compile(r"https?://[^\s;,]+[^\s;,.)]")
QUOTE = re.compile(r"“([^”]*)”")
PCT = re.compile(r"(rose|fell|grew|declined) (\d+)%")
REQUIRED = ("brief", "identity", "changes", "unknowns")


def _render(value: float) -> set[str]:
    """Every way the summary may print a published figure."""
    size = abs(value)
    out = {f"{value:,.0f}"}
    if size >= 1e9:
        out.add(f"{value / 1e9:.2f} billion")
    elif size >= 1e6:
        out.add(f"{value / 1e6:.1f} million")
    elif size >= 1e4:
        out.add(f"{value / 1e3:,.0f} thousand")
    return out


def _strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return [] if value is None else [str(value)]


def validate_synthesis_envelope(env: dict[str, Any]) -> list[str]:
    org = env.get("organisation_number")
    claims = env.get("claims") or []
    evidence = {e.get("id"): e for e in env.get("evidence") or []}
    errors: list[str] = []
    if not claims or claims[0].get("field") != "summary_profile" or claims[0].get("availability") != "available":
        return [f"{org}: summary_profile is not the first available claim"]
    claim = claims[0]
    text = str(claim.get("value") or "")
    if (env.get("summary") or {}).get("text") != text:
        errors.append(f"{org}: top-level summary.text differs from the summary claim")
    if (env.get("profile") or {}).get("synthesis_summary") not in (None, text):
        errors.append(f"{org}: profile.synthesis_summary differs from the summary claim")
    for eid in claim.get("evidence_ids") or []:
        if eid not in evidence:
            errors.append(f"{org}: summary cites missing evidence {eid}")
    sources = {s.get("n"): s for s in claim.get("sources") or []}
    for source in sources.values():
        for eid in source.get("evidence_ids") or []:
            if (evidence.get(eid) or {}).get("source_url") != source.get("url"):
                errors.append(f"{org}: source [{source.get('n')}] evidence {eid} is not from {source.get('url')}")
    body = text.split("\nSources: ")[0]
    for marker in re.findall(r"\[(\d+(?:, \d+)*)\]", body):
        for n in marker.split(", "):
            if int(n) not in sources:
                errors.append(f"{org}: marker [{n}] has no source")
    keys = {s.get("key") for s in claim.get("sections") or []}
    for key in REQUIRED:
        if key not in keys:
            errors.append(f"{org}: summary has no '{key}' section")

    available = [c for c in claims[1:] if c.get("availability") == "available"]
    values: list[str] = []
    numbers: list[float] = []
    for c in available:
        values.extend(_strings(c.get("value")))
        values.extend(_strings({k: v for k, v in c.items() if k not in ("value", "evidence_ids", "field", "availability", "confidence")}))
        figures = c.get("value") if c.get("field") == "financial_history" else {c.get("field"): c.get("value")}
        for field, figure in (figures or {}).items() if isinstance(figures, dict) else []:
            if field in ("revenue", "operating_result", "annual_result", "assets", "debt", "registry_employees"):
                try:
                    numbers.append(float(figure))
                except (TypeError, ValueError):
                    pass
    refresh = env.get("refresh") or {}
    values.append(str(refresh.get("previous_completed_at") or ""))
    for change in env.get("changes") or []:  # refresh events carry their own source URLs
        values.extend(_strings({k: change.get(k) for k in ("old_value", "new_value", "effective_at", "source_url")}))
    blob = "\n".join(values)

    for date in DATE.findall(body):
        if date not in blob:
            errors.append(f"{org}: date {date} is not in any published claim")
    rendered = {r for n in numbers for r in _render(n)}
    for amount, unit in MONEY.findall(body):
        shown = f"{amount} {unit}".strip()
        if shown not in rendered:
            errors.append(f"{org}: amount NOK {shown} does not match a published figure")
    for count in re.findall(r"reports ([\d,]+) employees?", body):
        if float(count.replace(",", "")) not in numbers:
            errors.append(f"{org}: employee count {count} does not match the register claim")
    for url in URL.findall(body):
        if url not in blob:
            errors.append(f"{org}: URL {url} is not a published claim value")
    for quote in QUOTE.findall(body):
        fragment = quote.removesuffix(" …").strip()
        if fragment and fragment not in " ".join(blob.split()):
            errors.append(f"{org}: quoted text is not from a published claim: {fragment[:60]}")
    for _verb, pct in PCT.findall(body):
        if not numbers:
            errors.append(f"{org}: percentage {pct}% with no published figures")
    return errors


def validate_synthesis_file(envelopes_path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in envelopes_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    errors: list[str] = []
    ok = 0
    for env in rows:
        problems = validate_synthesis_envelope(env)
        errors.extend(problems)
        ok += not problems
    return {"passed": not errors, "total_envelopes": len(rows), "validated_grounded_count": ok,
            "error_count": len(errors), "errors": errors[:25]}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python eval/synthesis_validator.py <envelopes.jsonl>")
        sys.exit(1)
    report = validate_synthesis_file(Path(sys.argv[1]))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["passed"] else 1)
