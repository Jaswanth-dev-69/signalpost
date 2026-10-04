#!/usr/bin/env python3
"""Seeded, website-heavier proxy for Builderr's fixture.

Builderr reported that 27.2% of its fixture companies had a verified website opportunity. In a
plain random sample of the public company list only ~11% have a registry homepage and our
pipeline verifies ~9.7% of companies. Observed verification rates are ~56% for companies with a
registry homepage and ~5% for the rest, so a mix with ~43% registry-homepage companies yields a
~27% verified-website share. The rest of the proxy is drawn at random from companies without a
registry homepage. Use it as the primary web-family benchmark and a plain random sample as the
lower bound.

Usage: python eval/fixture_proxy.py <universe.jsonl> <out.txt> [--count 1200] [--homepage-share 0.43] [--seed 20261004]
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("universe")
    parser.add_argument("output")
    parser.add_argument("--count", type=int, default=1200)
    parser.add_argument("--homepage-share", type=float, default=0.43)
    parser.add_argument("--seed", type=int, default=20261004)
    args = parser.parse_args()

    with_site, without_site = [], []
    with open(args.universe, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            (with_site if str(row.get("website") or "").strip() else without_site).append(row["organisation_number"])
    rng = random.Random(args.seed)
    n_site = round(args.count * args.homepage_share)
    chosen = rng.sample(with_site, n_site) + rng.sample(without_site, args.count - n_site)
    rng.shuffle(chosen)
    Path(args.output).write_text("\n".join(chosen) + "\n", encoding="utf-8")
    meta = {
        "count": len(chosen),
        "registry_homepage": n_site,
        "registry_homepage_share": round(n_site / len(chosen), 3),
        "universe_homepage_share": round(len(with_site) / (len(with_site) + len(without_site)), 3),
        "seed": args.seed,
    }
    Path(args.output).with_suffix(".meta.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(meta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
