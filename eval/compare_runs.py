#!/usr/bin/env python3
"""Compare two runs of our envelopes per external family: companies covered, facts, gained and
lost companies, and facts per covered company. Reads published claims only (availability available).

Usage: python eval/compare_runs.py BASE.jsonl NEW.jsonl [--show-lost]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kit_parity import our_facts  # noqa: E402

FAMILIES = ["website_exact", "description", "social_profile", "dated_news", "hiring_signal"]


def load(path: str) -> dict[str, dict[str, set]]:
    rows = (json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip())
    return {row["organisation_number"]: our_facts(row) for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("new")
    parser.add_argument("--show-lost", action="store_true")
    args = parser.parse_args()
    base, new = load(args.base), load(args.new)
    orgs = sorted(set(base) & set(new))
    print(f"n={len(orgs)}  {'family':14}{'base co':>8}{'new co':>8}{'gained':>8}{'lost':>6}{'base facts':>12}{'new facts':>11}{'facts/co base':>15}{'new':>6}")
    for family in FAMILIES:
        b = {o for o in orgs if base[o].get(family)}
        n = {o for o in orgs if new[o].get(family)}
        bf = sum(len(base[o].get(family, ())) for o in orgs)
        nf = sum(len(new[o].get(family, ())) for o in orgs)
        print(f"{'':8}{family:14}{len(b):>8}{len(n):>8}{len(n - b):>8}{len(b - n):>6}{bf:>12}{nf:>11}{bf / max(1, len(b)):>15.2f}{nf / max(1, len(n)):>6.2f}")
        if args.show_lost and b - n:
            print(f"{'':10}lost: {sorted(b - n)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
