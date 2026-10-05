#!/usr/bin/env python3
"""Per-family parity between the starter-kit reference agent, our agent and Builderr's sample.

For each family it prints companies covered and facts found, plus how many of the kit's facts we
also emit (overlap) and how many we miss. Families are grouped as in the evaluation contract:
"external" families (company-owned web layer) feed Recall; registry families are listed for
comparison only.

Reads three envelope shapes:
  kit    : {run_id, organisation_number, state, modules, profile: {evidence: {...}}}
  ours   : {organisation_number, claims: [...], evidence: [...]} (optionally also a kit-style
           `profile`, which is read by the kit extractor when --ours-as-kit is given)
  sample : Builderr's /signalpost DATA array (JSON list)

Usage:
  python eval/kit_parity.py --orgs ORGS.txt --kit KIT.jsonl --ours OURS.jsonl [--sample DATA.json] [--json OUT.json]
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any

import tldextract

EXTERNAL = ["website", "website_exact", "description", "social_profile", "dated_news", "hiring_signal"]
REGISTRY = ["identity", "financials", "roles", "subunits"]
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())


def domain(url: Any) -> str | None:
    host = urllib.parse.urlparse(str(url or "")).hostname or ""
    return (_EXTRACT(host).top_domain_under_public_suffix.casefold() or None) if host else None


def social_key(url: Any) -> str | None:
    parsed = urllib.parse.urlparse(str(url or ""))
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if not host:
        return None
    return f"{host}{parsed.path.rstrip('/')}".casefold()


def read_jsonl(path: str | None) -> list[dict]:
    if not path:
        return []
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def kit_facts(envelope: dict) -> dict[str, set]:
    """Facts as the kit's envelope exposes them (profile.evidence records)."""
    ev = (envelope.get("profile") or {}).get("evidence") or {}
    out: dict[str, set] = defaultdict(set)
    web = ev.get("website") or {}
    value = web.get("value") or {}
    if web.get("status") == "available":
        site = domain(value.get("final_url") or web.get("source_url"))
        if site:
            out["website"].add(site)
            if (value.get("identity_assessment") or {}).get("publishable"):
                out["website_exact"].add(site)
                if str(value.get("description") or "").strip():
                    out["description"].add(site)
    for link in value.get("social_links") or []:
        key = social_key(link.get("url"))
        if key:
            out["social_profile"].add(key)
    for item in value.get("news") or []:
        out["dated_news"].add(str(item.get("url") or item.get("title")).casefold())
    for item in value.get("jobs") or []:
        out["hiring_signal"].add(str(item.get("url") or item.get("title")).casefold())
    reg = ev.get("registry") or {}
    if reg.get("status") == "available":
        out["identity"].add("registry")
    fin = ev.get("financials") or {}
    for rec in (fin.get("value") or {}).get("records") or [] if fin.get("status") == "available" else []:
        out["financials"].add(json.dumps(rec.get("period"), sort_keys=True))
    roles = ev.get("roles") or {}
    for role in (roles.get("value") or {}).get("roles") or [] if roles.get("status") == "available" else []:
        out["roles"].add(f"{role.get('name') or role.get('organisation_number')}|{role.get('role_code')}")
    loc = ev.get("locations") or {}
    for item in (loc.get("value") or {}).get("locations") or [] if loc.get("status") == "available" else []:
        out["subunits"].add(str(item.get("organisation_number")))
    return out


def our_facts(envelope: dict) -> dict[str, set]:
    """Facts as published claims (availability == available) in the OUTPUT_CONTRACT shape."""
    out: dict[str, set] = defaultdict(set)
    for claim in envelope.get("claims") or []:
        if claim.get("availability") != "available":
            continue
        field, value = claim.get("field"), claim.get("value")
        if field == "official_website":
            site = domain(value)
            if site:
                out["website"].add(site)
                out["website_exact"].add(site)
        elif field == "company_description":
            out["description"].add("description")
        elif field in ("social_profile", "social_profiles"):
            for item in value if isinstance(value, list) else [value]:
                url = item.get("url") if isinstance(item, dict) else item
                key = social_key(url if "://" in str(url) else f"https://{url}")
                if key:
                    out["social_profile"].add(key)
        elif field == "dated_news":
            for item in value if isinstance(value, list) else [claim]:
                out["dated_news"].add(str(item.get("url") or item.get("title") or item.get("value")).casefold())
        elif field in ("hiring_signal", "job_postings"):
            for item in value if isinstance(value, list) else [value]:
                url = item.get("url") if isinstance(item, dict) else item
                out["hiring_signal"].add(str(url).rstrip("/").casefold())
        elif field == "legal_name":
            out["identity"].add("registry")
        elif field == "reporting_period":
            out["financials"].add(json.dumps(value, sort_keys=True))
        elif field == "registered_roles":
            for role in value or []:
                out["roles"].add(f"{role.get('name') or role.get('organisation_number')}|{role.get('role_code')}")
        elif field == "registered_subunits":
            for item in value or []:
                out["subunits"].add(str(item.get("organisation_number")))
    return out


def sample_facts(row: dict) -> dict[str, set]:
    """Builderr's sample-site profile, read like the kit's website record plus approved handles."""
    out: dict[str, set] = defaultdict(set)
    web = row.get("web") or {}
    value = web.get("value") or {}
    if web.get("status") == "available":
        site = domain(value.get("final_url") or web.get("source"))
        if site:
            out["website"].add(site)
            if (value.get("identity_assessment") or {}).get("publishable"):
                out["website_exact"].add(site)
                if str(value.get("description") or "").strip():
                    out["description"].add(site)
    handles = [h for h in (row.get("external") or {}).get("handles") or [] if h.get("rightsStatus") == "approved"]
    for link in [*(value.get("social_links") or []), *handles]:
        key = social_key(link.get("url"))
        if key:
            out["social_profile"].add(key)
    linkedin = (row.get("external") or {}).get("linkedin") or {}
    for post in linkedin.get("posts") or []:
        out["dated_news"].add(str(post.get("source")).casefold())
    for job in linkedin.get("jobs") or []:
        out["hiring_signal"].add(str(job.get("job_url")).casefold())
    if (row.get("registry") or {}).get("status") == "available":
        out["identity"].add("registry")
    for rec in (row.get("financial") or {}).get("records") or []:
        out["financials"].add(json.dumps(rec.get("period"), sort_keys=True))
    for role in (row.get("roles") or {}).get("items") or []:
        out["roles"].add(f"{role.get('name') or role.get('organisation_number')}|{role.get('role_code')}")
    for item in (row.get("locations") or {}).get("items") or []:
        out["subunits"].add(str(item.get("organisation_number")))
    return out


def by_org(rows: list[dict], extractor, key: str = "organisation_number") -> dict[str, dict[str, set]]:
    return {str(row.get(key)): extractor(row) for row in rows}


def compare(orgs: list[str], kit: dict, ours: dict, sample: dict) -> dict[str, dict]:
    table = {}
    for family in [*EXTERNAL, *REGISTRY]:
        row: dict[str, Any] = {}
        for label, source in (("kit", kit), ("ours", ours), ("sample", sample)):
            if not source:
                continue
            covered = [org for org in orgs if source.get(org, {}).get(family)]
            row[f"{label}_companies"] = len(covered)
            row[f"{label}_facts"] = sum(len(source.get(org, {}).get(family, ())) for org in orgs)
        if kit and ours:
            row["kit_only_companies"] = sorted(org for org in orgs if kit.get(org, {}).get(family) and not ours.get(org, {}).get(family))
            row["ours_only_companies"] = sorted(org for org in orgs if ours.get(org, {}).get(family) and not kit.get(org, {}).get(family))
            row["kit_facts_we_miss"] = sum(len(kit.get(org, {}).get(family, set()) - ours.get(org, {}).get(family, set())) for org in orgs)
        table[family] = row
    return table


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--orgs", required=True)
    parser.add_argument("--kit")
    parser.add_argument("--ours")
    parser.add_argument("--ours-as-kit", action="store_true", help="read our envelopes' kit-style profile instead of claims")
    parser.add_argument("--sample")
    parser.add_argument("--json")
    args = parser.parse_args()
    orgs = [line.strip() for line in Path(args.orgs).read_text().splitlines() if line.strip()]
    kit = by_org(read_jsonl(args.kit), kit_facts)
    ours = by_org(read_jsonl(args.ours), kit_facts if args.ours_as_kit else our_facts)
    sample = {}
    if args.sample:
        sample = {str(row["org"]): sample_facts(row) for row in json.loads(Path(args.sample).read_text(encoding="utf-8"))}
        sample = {org: facts for org, facts in sample.items() if org in set(orgs)}
    table = compare(orgs, kit, ours, sample)
    labels = [label for label, source in (("kit", kit), ("ours", ours), ("sample", sample)) if source]
    header = f"{'family':16}" + "".join(f"{label + ' co/facts':>18}" for label in labels) + (f"{'kit-only co':>13}{'ours-only co':>14}{'kit facts missed':>18}" if kit and ours else "")
    print(f"n={len(orgs)}")
    print(header)
    for family, row in table.items():
        if family == REGISTRY[0]:
            print("-- registry families (comparison only) --")
        line = f"{family:16}" + "".join(f"{row[label + '_companies']:>10}/{row[label + '_facts']:<7}" for label in labels)
        if kit and ours:
            line += f"{len(row['kit_only_companies']):>13}{len(row['ours_only_companies']):>14}{row['kit_facts_we_miss']:>18}"
        print(line)
    if args.json:
        Path(args.json).write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
