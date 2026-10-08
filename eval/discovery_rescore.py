#!/usr/bin/env python3
"""Offline re-scoring of a discovery_labelled.py run (W1b/W1c).

For every loaded candidate the saved bytes are re-read and the organisation-number fields are
rebuilt with this checkout's detectors; the candidate is then judged by this checkout's
strict_discovered_proof. Each generator ("current" = the run's own code order, "challenger") is
simulated as the pipeline runs it: candidates in order, first proof wins. Reported per stratum and
reweighted to the target population (companies without a declared homepage):
  gate recall      first passing candidate is the declared domain
  other domain     first passing candidate is another domain (listed for hand review; one that
                   prints the company's own number is the same entity's alternate domain)
  seconds          sequential fetch time until the decision (all candidates when nothing passes)

Usage: python eval/discovery_rescore.py RUN_DIR [--weights none=0.877,5-19=0.091,20-99=0.027,100+=0.004]
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent import domain_solver as ds  # noqa: E402
from norway_company_agent.identity import org_numbers_anywhere, org_numbers_in_text  # noqa: E402

OLD_REASONS = ("exact organisation number on homepage", "full legal name on homepage")


def page_text(raw_b64: str) -> str:
    raw = base64.b64decode(raw_b64 or "")
    return " ".join(BeautifulSoup(raw.decode("utf-8", errors="replace"), "lxml").get_text(" ", strip=True).split()) if raw else ""


def rejudge(profile: dict, candidate: dict, saved: dict) -> tuple[bool, str]:
    value = dict(saved["value"])
    texts = [page_text(page.get("raw")) for page in saved["raw"]]
    labelled: list[str] = []
    printed: list[str] = []
    for text in texts:
        labelled.extend(o for o in org_numbers_in_text(text) if o not in labelled)
        printed.extend(o for o in org_numbers_anywhere(text) if o not in printed)
    value["org_numbers_on_site"] = labelled
    value["_org_numbers_anywhere"] = printed
    original = str(candidate.get("proof_reason") or "")
    # The name rule is unchanged; reuse the original homonym verdict instead of a live registry call.
    homonym_words = ("another entity", "too many", "identically", "names another", "homonym")
    conflict = original if any(word in original for word in homonym_words) else None
    saved_check = ds.name_homonym_conflict
    ds.name_homonym_conflict = lambda *args, **kwargs: conflict
    try:
        return ds.strict_discovered_proof(profile, value)
    finally:
        ds.name_homonym_conflict = saved_check


def simulate(order: list[dict], verdict_key: str) -> tuple[dict | None, float]:
    seconds = 0.0
    for candidate in order:
        seconds += float(candidate.get("seconds") or 0)
        if candidate.get(verdict_key):
            return candidate, seconds
    return None, seconds


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--weights", default="none=0.877,5-19=0.091,20-99=0.027,100+=0.004")
    args = parser.parse_args()
    run = Path(args.run_dir)
    weights = {k: float(v) for k, v in (item.split("=") for item in args.weights.split(","))}
    rows = [json.loads(line) for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    configs = [("current", "old"), ("current", "new"), ("challenger", "old"), ("challenger", "new")]
    tally: dict[tuple, dict[str, Counter]] = {c: defaultdict(Counter) for c in configs}
    secs: dict[tuple, dict[str, float]] = {c: defaultdict(float) for c in configs}
    reviews = []
    true_loaded = Counter()
    for row in rows:
        profile = ds_profile(row)
        raw_path = run / "raw" / f"{row['org']}.json.gz"
        saved_all = json.loads(gzip.open(raw_path, "rt", encoding="utf-8").read()) if raw_path.exists() else {}
        for candidate in row["candidates"]:
            candidate["old"] = bool(candidate.get("proof"))
            candidate["new"] = False
            if candidate.get("status") == "available" and candidate["key"] in saved_all:
                candidate["new"], candidate["new_reason"] = rejudge(profile, candidate, saved_all[candidate["key"]])
        true = [c for c in row["candidates"] if c.get("final_domain") == row["declared_domain"] or c["key"] == row["declared_domain"]]
        stratum = row["stratum"]
        true_loaded[(stratum, "companies")] += 1
        if any(c.get("status") == "available" and c.get("final_domain") == row["declared_domain"] for c in true):
            true_loaded[(stratum, "true site among candidates and loaded")] += 1
            if any(c["old"] for c in true):
                true_loaded[(stratum, "true site passes old proof")] += 1
            if any(c["new"] for c in true):
                true_loaded[(stratum, "true site passes new proof")] += 1
        for generator, proof in configs:
            order = sorted((c for c in row["candidates"] if generator in c["rank"]), key=lambda c: c["rank"][generator])
            winner, seconds = simulate(order, proof)
            secs[(generator, proof)][stratum] += seconds
            tally[(generator, proof)][stratum]["companies"] += 1
            if winner is None:
                continue
            if winner.get("final_domain") == row["declared_domain"]:
                tally[(generator, proof)][stratum]["gate_recall"] += 1
            else:
                tally[(generator, proof)][stratum]["other_domain"] += 1
                reviews.append({"config": f"{generator}/{proof}", "org": row["org"], "name": row["name"], "declared": row["declared_domain"],
                                "passed": winner.get("final_url"), "reason": winner.get("new_reason") if proof == "new" else winner.get("proof_reason"),
                                "orgs_on_site": winner.get("org_numbers_on_site"), "title": winner.get("title")})
    print("True site (declared domain) among a generator's candidates and loaded, and passing the proof:")
    for stratum in weights:
        n = true_loaded[(stratum, "companies")]
        if n:
            loaded = true_loaded[(stratum, "true site among candidates and loaded")]
            print(f"  {stratum:6} n={n:4}  loaded {loaded:4}  passes old {true_loaded[(stratum, 'true site passes old proof')]:4}  new {true_loaded[(stratum, 'true site passes new proof')]:4}")
    print("\nPipeline simulation (first passing candidate wins):")
    for config in configs:
        per = tally[config]
        weighted_recall = sum(weights[s] * per[s]["gate_recall"] / per[s]["companies"] for s in weights if per[s]["companies"])
        weighted_other = sum(weights[s] * per[s]["other_domain"] / per[s]["companies"] for s in weights if per[s]["companies"])
        weighted_secs = sum(weights[s] * secs[config][s] / per[s]["companies"] for s in weights if per[s]["companies"])
        cells = "  ".join(f"{s}:{per[s]['gate_recall']}/{per[s]['companies']}" for s in weights if per[s]["companies"])
        print(f"  {config[0]:10} {config[1]:3}  gate recall {cells}  | weighted {100 * weighted_recall:5.1f}%  other-domain weighted {100 * weighted_other:4.1f}% "
              f"(n={sum(per[s]['other_domain'] for s in per)})  seconds/company weighted {weighted_secs:5.1f}")
    (run / "rescore_reviews.json").write_text(json.dumps(reviews, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(reviews)} other-domain passes written to {run / 'rescore_reviews.json'}")
    return 0


def ds_profile(row: dict) -> dict:
    return {"organisation_number": row["org"], "name": row["name"], "legal_form": row["form"], "municipality": row.get("kommune") or None,
            "website": None, "evidence": {"registry": {"value": {"epostadresse": row.get("email") or ""}}}}


if __name__ == "__main__":
    raise SystemExit(main())
