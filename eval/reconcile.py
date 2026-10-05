#!/usr/bin/env python3
"""Reconcile our envelopes against the facts Builderr reported as missed (revision 3, Phase B1).

For each expected fact, print what we emitted for that family (claim, state, evidence) and why it
does not match under the normalizations suggested by Builderr's examples. The expected facts are
test cases only; nothing in the agent may depend on them.

    uv run python eval/reconcile.py                      # run the agent on the cases, then reconcile
    uv run python eval/reconcile.py --envelopes out.jsonl  # reconcile an existing output
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (family, org, name, expected value, expected source) from Builderr's v2 feedback.
EXPECTED = [
    ("website", "811413682", "ELOPAK ASA", "elopak.com", "https://www.elopak.com/"),
    ("social", "811730912", "MTM SKOGSERVICE AS", "facebook.com/mtmskogservice", "https://www.mtm-skogservice.no"),
    ("hiring", "923609016", "EQUINOR ASA", "https://www.equinor.com/careers", "https://www.equinor.com/careers"),
    ("news", "883971752", "SUNNAAS SYKEHUS HF", "bedre sosial funksjon etter hjerneskade (2025-09-22t20:00:00+02:00)",
     "https://www.sunnaas.no/fag-og-forskning/kompetansesentre-og-tjenester/regional-kompetansetjeneste-for-rehabilitering-rkr/nyheter-rkr/bedre-sosial-funksjon-etter-hjerneskade/"),
]
# Field names that may carry each family (ours and plausible scorer names).
FAMILY_FIELDS = {
    "website": ("official_website", "website", "company_website"),
    "social": ("social_profiles", "social_profile", "social_links"),
    "hiring": ("job_postings", "hiring_signal", "careers_page", "jobs"),
    "news": ("dated_news", "news"),
}


def url_key(url: str) -> str:
    """Scheme-less, www-less, lowercase, no trailing slash (the form of Builderr's social example)."""
    parsed = urllib.parse.urlparse(url.strip() if "://" in url else "https://" + url.strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    return f"{host}{path}".lower()


def domain_key(url: str) -> str:
    host = urllib.parse.urlparse(url if "://" in url else "https://" + url).hostname or ""
    return host.lower().removeprefix("www.")


def news_key(title: str, published: str) -> str:
    return f"{' '.join(str(title).split())} ({published})".lower()


def item_values(claim: dict) -> list:
    value = claim.get("value")
    return value if isinstance(value, list) else ([] if value is None else [value])


def candidate_keys(family: str, item) -> set[str]:
    """Every plausible normalized key a scorer could derive from one emitted item."""
    keys: set[str] = set()
    if isinstance(item, str):
        keys |= {item.lower(), url_key(item)} if "." in item else {item.lower()}
        if family == "website":
            keys.add(domain_key(item))
        return keys
    if isinstance(item, dict):
        for k in ("url", "source_page", "careers_url"):
            if item.get(k):
                keys.add(url_key(item[k]))
        if family == "news" and item.get("title"):
            for k in ("published_at", "published_date", "date"):
                if item.get(k):
                    keys.add(news_key(item["title"], item[k]))
            keys.add(" ".join(str(item["title"]).split()).lower())
    return keys


def expected_keys(family: str, value: str) -> set[str]:
    if family == "website":
        return {domain_key(value)}
    if family == "news":
        title = re.sub(r"\s*\([^)]*\)\s*$", "", value)
        return {value.lower(), title.lower()}
    return {url_key(value)}


def run_agent(orgs: list[str], work: Path) -> Path:
    inputs, output = work / "inputs.jsonl", work / "envelopes.jsonl"
    inputs.write_text("".join(json.dumps({"organisation_number": o}) + "\n" for o in orgs), encoding="utf-8")
    command = [sys.executable, str(ROOT / "run_agent.py"), "--organisations", str(inputs), "--output", str(output),
               "--workers", "4", "--max-runtime", "240", "--hard-deadline", "300"]
    subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelopes", help="Existing envelope JSONL (skips the agent run)")
    parser.add_argument("--keep", help="Copy the fresh envelopes and profiles to this path prefix")
    args = parser.parse_args()
    orgs = list(dict.fromkeys(org for _, org, *_ in EXPECTED))
    with tempfile.TemporaryDirectory(prefix="signalpost-reconcile-") as tmp:
        path = Path(args.envelopes) if args.envelopes else run_agent(orgs, Path(tmp))
        rows = {json.loads(l)["organisation_number"]: json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()}
        profiles_path = path.with_suffix(".profiles.jsonl")
        profiles = {json.loads(l)["organisation_number"]: json.loads(l) for l in profiles_path.read_text(encoding="utf-8").splitlines()} if profiles_path.exists() else {}
        if args.keep and not args.envelopes:
            Path(args.keep + ".jsonl").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            if profiles_path.exists():
                Path(args.keep + ".profiles.jsonl").write_text(profiles_path.read_text(encoding="utf-8"), encoding="utf-8")
    matched = 0
    for family, org, name, value, source in EXPECTED:
        env = rows.get(org)
        print(f"\n=== {family}: {name} ({org}) expects {value!r}")
        if not env:
            print("  NO ENVELOPE")
            continue
        evidence = {e["id"]: e for e in env.get("evidence", [])}
        claims = [c for c in env.get("claims", []) if c.get("field") in FAMILY_FIELDS[family]]
        if not claims:
            print(f"  no claim with field in {FAMILY_FIELDS[family]}")
        want = expected_keys(family, value)
        hit = False
        for c in claims:
            items = item_values(c)
            shape = "list" if isinstance(c.get("value"), list) else type(c.get("value")).__name__
            print(f"  claim field={c['field']} availability={c['availability']} shape={shape} items={len(items)} confidence={c.get('confidence')}")
            for item in items[:6]:
                keys = candidate_keys(family, item)
                ok = bool(keys & want)
                hit |= ok
                print(f"    {'MATCH ' if ok else 'differ'} {json.dumps(item, ensure_ascii=False)[:180]}")
            for eid in c.get("evidence_ids", [])[:4]:
                ev = evidence.get(eid, {})
                print(f"    ev {ev.get('source_class')} {ev.get('source_url')} at={ev.get('retrieved_at')} span={str(ev.get('claim_span'))[:90]!r}")
        if not hit:
            web = ((profiles.get(org) or {}).get("evidence") or {}).get("website") or {}
            val = web.get("value") or {}
            ia = val.get("identity_assessment") or {}
            print(f"  WHY: website status={web.get('status')} url={val.get('final_url') or web.get('source_url')} "
                  f"identity={ia.get('status')}/{ia.get('method')} publishable={ia.get('publishable')} note={web.get('note')}")
            wc = (profiles.get(org) or {}).get("web_claims") or {}
            if wc:
                print(f"  web_claims keys={sorted(wc)} news_checked={[p.get('url') for p in (wc.get('news') or {}).get('checked_pages') or []][:4]} "
                      f"careers={((wc.get('jobs') or {}).get('careers_page') or {}).get('url')}")
            errs = [e for e in env.get("errors", []) if e.get("type") != "EvidenceMissing"][:3]
            if errs:
                print(f"  errors: {json.dumps(errs, ensure_ascii=False)[:300]}")
        matched += hit
        print(f"  RESULT: {'recovered' if hit else 'MISSED'} (expected source {source})")
    print(f"\nrecovered {matched}/{len(EXPECTED)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
