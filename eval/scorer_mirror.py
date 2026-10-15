#!/usr/bin/env python3
"""Scorer mirror (analysis only): the contract's recall formula applied to local runs.

For each external field family f: coverage_f = 0.7 * company recall + 0.3 * fact recall against a
collection; Recall = 50 * mean of coverage_f over the scored families. The collection stands in
for Builderr's verified union. It is Builderr's sample facts (when given) pooled with every run's
own facts, so a run that publishes a fact nobody else found still enlarges the pool, as in the
contract ("union of discoveries from every submitted crawler and Builderr's own crawlers").

Read modes (how the scorer is assumed to read an envelope):
  kit      profile.evidence.website: any `available` record counts as a website fact; social from
           value.social_links (the kit's shape). This is the only shape known to score.
  kit_exact  as kit, but a website counts only when identity_assessment.publishable is true.
  claims   OUTPUT_CONTRACT claims only (official_website, social_profile(s), dated_news,
           hiring_signal / job_postings), list values unpacked.
  scalar   claims, but only scalar values (a list-valued claim is not read).
  auto     kit if the envelope has a profile, else scalar (what v2's 0.0% social suggests).
  hedge    kit, plus news and hiring from external.observations (the kit's observation records).

--kit-news adds, on both sides, the one company-site news fact the kit's own reader
(`scripts/extract_company_site_news.py`) derives from a profile's bounded `pages`: the deepest
news-path page of a publishable website, keyed by its URL. Builderr's sample rows carry such pages
from Builderr's own crawler, so this models a pool that also holds kit-read company-site news.

Usage:
  python eval/scorer_mirror.py --anchors        (what the official anchors imply)
  python eval/scorer_mirror.py --orgs ORGS.txt --run kit=KIT.jsonl:kit --run v2=V2.jsonl:auto \
      [--sample DATA.json] [--families website,social,news,hiring] [--collection-website any|exact]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kit_parity import domain, read_jsonl, social_key  # noqa: E402

def _kit_news_reader():
    import importlib.util
    spec = importlib.util.spec_from_file_location("kit_site_news", Path(__file__).resolve().parents[1] / "scripts" / "extract_company_site_news.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.observation


def kit_news_fact(profile: dict | None, org: str) -> str | None:
    """The kit reader's company-site news fact for one profile (deepest news-path page URL)."""
    if not profile:
        return None
    item = _kit_news_reader()({"organisation_number": org, **profile})
    return str(item["source_url"]).rstrip("/").casefold() if item else None


FAMILY_KEYS = {"website": "website", "social": "social_profile", "news": "dated_news", "hiring": "hiring_signal",
               "description": "description"}


def facts_kit(envelope: dict, exact_only: bool = False) -> dict[str, set]:
    out: dict[str, set] = defaultdict(set)
    ev = (envelope.get("profile") or {}).get("evidence") or {}
    web = ev.get("website") or {}
    value = web.get("value") or {}
    publishable = bool((value.get("identity_assessment") or {}).get("publishable"))
    if web.get("status") == "available" and (publishable or not exact_only):
        site = domain(value.get("final_url") or web.get("source_url"))
        if site:
            out["website"].add(site)
            if publishable and str(value.get("description") or "").strip():
                out["description"].add("description")
    for link in value.get("social_links") or []:
        key = social_key(link.get("url"))
        if key:
            out["social_profile"].add(key)
    return out


def facts_claims(envelope: dict, scalar_only: bool = False) -> dict[str, set]:
    out: dict[str, set] = defaultdict(set)
    for claim in envelope.get("claims") or []:
        if claim.get("availability") != "available":
            continue
        field, value = claim.get("field"), claim.get("value")
        if scalar_only and isinstance(value, (list, dict)):
            continue
        items = value if isinstance(value, list) else [value]
        if field == "official_website":
            site = domain(value)
            if site:
                out["website"].add(site)
        elif field == "company_description":
            out["description"].add("description")
        elif field in ("social_profile", "social_profiles"):
            for item in items:
                url = item.get("url") if isinstance(item, dict) else item
                key = social_key(url if "://" in str(url) else f"https://{url}")
                if key:
                    out["social_profile"].add(key)
        elif field == "dated_news":
            for item in items:
                url = (item.get("url") if isinstance(item, dict) else None) or claim.get("url") or item
                out["dated_news"].add(str(url).rstrip("/").casefold())
        elif field in ("hiring_signal", "job_postings"):
            for item in items:
                url = item.get("url") if isinstance(item, dict) else item
                out["hiring_signal"].add(str(url).rstrip("/").casefold())
    return out


def facts_hedge(envelope: dict) -> dict[str, set]:
    out = facts_kit(envelope)
    for obs in (envelope.get("external") or {}).get("observations") or []:
        key = "dated_news" if obs.get("signal_type") == "public_post" else "hiring_signal" if obs.get("signal_type") == "job_posting" else None
        if key and obs.get("url"):
            out[key].add(str(obs["url"]).rstrip("/").casefold())
    return out


def read_facts(envelope: dict, mode: str) -> dict[str, set]:
    if mode == "kit":
        return facts_kit(envelope)
    if mode == "kit_exact":
        return facts_kit(envelope, exact_only=True)
    if mode == "claims":
        return facts_claims(envelope)
    if mode == "scalar":
        return facts_claims(envelope, scalar_only=True)
    if mode == "auto":
        return facts_kit(envelope) if envelope.get("profile") else facts_claims(envelope, scalar_only=True)
    if mode == "hedge":
        return facts_hedge(envelope)
    if mode == "both":
        merged = facts_kit(envelope)
        for key, values in facts_claims(envelope).items():
            merged[key] |= values
        return merged
    raise SystemExit(f"unknown read mode {mode}")


def sample_collection(rows: list[dict], website: str, kit_news: bool = False) -> dict[str, dict[str, set]]:
    out: dict[str, dict[str, set]] = {}
    for row in rows:
        facts: dict[str, set] = defaultdict(set)
        web = row.get("web") or {}
        value = web.get("value") or {}
        exact = bool((value.get("identity_assessment") or {}).get("publishable"))
        if web.get("status") == "available" and (exact or website == "any"):
            site = domain(value.get("final_url") or web.get("source"))
            if site:
                facts["website"].add(site)
                if exact and str(value.get("description") or "").strip():
                    facts["description"].add("description")
        handles = [h for h in (row.get("external") or {}).get("handles") or [] if h.get("rightsStatus") == "approved"]
        for link in [*(value.get("social_links") or []), *handles]:
            key = social_key(link.get("url"))
            if key:
                facts["social_profile"].add(key)
        linkedin = (row.get("external") or {}).get("linkedin") or {}
        for post in linkedin.get("posts") or []:
            facts["dated_news"].add(str(post.get("source")).rstrip("/").casefold())
        for job in linkedin.get("jobs") or []:
            facts["hiring_signal"].add(str(job.get("job_url")).rstrip("/").casefold())
        if kit_news:
            fact = kit_news_fact({"evidence": {"website": web}}, str(row["org"]))
            if fact:
                facts["dated_news"].add(fact)
        out[str(row["org"])] = facts
    return out


def score(orgs: list[str], run: dict, collection: dict, families: list[str]) -> dict:
    per_family = {}
    for family in families:
        key = FAMILY_KEYS[family]
        positive = [o for o in orgs if collection.get(o, {}).get(key)]
        total_facts = sum(len(collection[o][key]) for o in positive)
        covered = [o for o in positive if run.get(o, {}).get(key, set()) & collection[o][key]]
        found = sum(len(run.get(o, {}).get(key, set()) & collection[o][key]) for o in positive)
        cr = len(covered) / len(positive) if positive else 0.0
        fr = found / total_facts if total_facts else 0.0
        per_family[family] = {"positive_companies": len(positive), "collection_facts": total_facts,
                              "covered": len(covered), "facts_found": found,
                              "company_recall": round(cr, 4), "fact_recall": round(fr, 4),
                              "coverage": round(0.7 * cr + 0.3 * fr, 4)}
    recall = 50 * sum(f["coverage"] for f in per_family.values()) / len(families)
    return {"recall_points": round(recall, 2), "families": per_family}


# Official anchors (Recall points) and what they imply under the contract's formula with the four
# external families weighted equally: Recall = 50 * mean(coverage) = 12.5 * sum(coverage).
ANCHORS = {
    "v2 board (5 Oct)": 8.05,          # social read as 0.0% in Builderr's v2 feedback
    "kit-like entries (board)": 13.07,
    "C300 estimate (v3 or v4)": 14.34,  # Soham: no dated-news item matched the verified pool
}


def anchor_table() -> None:
    """What each anchor implies: the summed family coverage, and the per-family coverage if only
    website and social score (news and hiring 0)."""
    print(f"{'anchor':28}{'recall':>8}{'sum of coverages':>18}{'web=social if news=hiring=0':>30}")
    for name, recall in ANCHORS.items():
        total = recall / 12.5
        print(f"{name:28}{recall:>8.2f}{total:>18.3f}{100 * total / 2:>29.1f}%")


def main() -> int:
    if "--anchors" in sys.argv:
        anchor_table()
        return 0
    parser = argparse.ArgumentParser()
    parser.add_argument("--orgs", required=True)
    parser.add_argument("--run", action="append", required=True, help="name=path.jsonl:mode")
    parser.add_argument("--sample")
    parser.add_argument("--families", default="website,social,news,hiring")
    parser.add_argument("--collection-website", choices=["any", "exact"], default="any")
    parser.add_argument("--no-pool", action="store_true", help="collection = sample only")
    parser.add_argument("--json")
    parser.add_argument("--kit-news", action="store_true", help="add the kit reader's company-site news fact on both sides")
    args = parser.parse_args()
    orgs = [line.strip() for line in Path(args.orgs).read_text().splitlines() if line.strip()]
    families = args.families.split(",")
    runs = {}
    for spec in args.run:
        name, rest = spec.split("=", 1)
        path, mode = rest.rsplit(":", 1)
        runs[name] = {}
        for e in read_jsonl(path):
            org = str(e["organisation_number"])
            runs[name][org] = read_facts(e, mode)
            if args.kit_news:
                fact = kit_news_fact(e.get("profile"), org)
                if fact:
                    runs[name][org]["dated_news"].add(fact)
    collection: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    if args.sample:
        for org, facts in sample_collection(json.loads(Path(args.sample).read_text(encoding="utf-8")), args.collection_website, args.kit_news).items():
            for key, values in facts.items():
                collection[org][key] |= values
    if not args.no_pool:
        for run in runs.values():
            for org, facts in run.items():
                for key, values in facts.items():
                    collection[org][key] |= values
    results = {name: score(orgs, run, collection, families) for name, run in runs.items()}
    head = f"{'run':12}{'recall':>8}  " + "  ".join(f"{f:>22}" for f in families)
    print(head)
    for name, result in results.items():
        cells = "  ".join(f"{r['covered']:>3}/{r['positive_companies']:<3} {r['facts_found']:>4}/{r['collection_facts']:<4} {100*r['coverage']:5.1f}%"
                          for r in result["families"].values())
        print(f"{name:12}{result['recall_points']:>8.2f}  {cells}")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
