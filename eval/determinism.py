#!/usr/bin/env python3
"""Compare two envelope files (same batch) after dropping volatile keys: timestamps, run ids,
latencies and request/byte counters. Reports, per company, every differing path, and checks for
duplicate evidence ids, duplicate claims and duplicate change events.

Usage: python eval/determinism.py A.jsonl B.jsonl [--show 20] [--json report.json]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

VOLATILE = {
    "retrieved_at", "started_at", "completed_at", "final_timestamp", "run_id", "runtime_ms", "latencies_ms",
    "elapsed_ms", "requests", "bytes", "p50_ms", "p95_ms", "run_metrics", "web_run", "refresh",
}


def strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def diff(a: Any, b: Any, path: str = "") -> list[str]:
    if type(a) is not type(b):
        return [path or "/"]
    if isinstance(a, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append(f"{path}/{key}")
            else:
                out.extend(diff(a[key], b[key], f"{path}/{key}"))
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}[len {len(a)}!={len(b)}]"]
        out = []
        for index, (x, y) in enumerate(zip(a, b)):
            out.extend(diff(x, y, f"{path}[{index}]"))
        return out
    return [] if a == b else [path]


def duplicates(env: dict) -> dict[str, int]:
    ev_ids = Counter(e.get("id") for e in env.get("evidence") or [])
    claims = Counter(json.dumps([c.get("field"), c.get("value"), c.get("availability")], sort_keys=True, ensure_ascii=False) for c in env.get("claims") or [])
    changes = Counter(json.dumps(strip(c), sort_keys=True, ensure_ascii=False) for c in env.get("changes") or [])
    return {
        "evidence_ids": sum(n - 1 for n in ev_ids.values() if n > 1),
        "claims": sum(n - 1 for n in claims.values() if n > 1),
        "changes": sum(n - 1 for n in changes.values() if n > 1),
    }


def read(path: str) -> dict[str, dict]:
    return {row["organisation_number"]: row for row in (json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("a")
    parser.add_argument("b")
    parser.add_argument("--show", type=int, default=20)
    parser.add_argument("--json")
    args = parser.parse_args()
    a, b = read(args.a), read(args.b)
    report: dict[str, Any] = {"companies_a": len(a), "companies_b": len(b), "same_membership": set(a) == set(b), "identical": 0, "differing": {}, "path_kinds": Counter(), "duplicates": Counter(), "changes_in_b": 0}
    for org in sorted(set(a) & set(b)):
        paths = diff(strip(a[org]), strip(b[org]))
        for kind, count in duplicates(b[org]).items():
            report["duplicates"][kind] += count
        report["changes_in_b"] += len(b[org].get("changes") or [])
        if not paths:
            report["identical"] += 1
            continue
        report["differing"][org] = paths
        for path in paths:
            parts = [p.split("[")[0] for p in path.split("/") if p]
            report["path_kinds"]["/".join(parts[:4])] += 1
    print(f"companies {len(a)}/{len(b)}  same membership: {report['same_membership']}  identical after stripping volatile keys: {report['identical']}  differing: {len(report['differing'])}")
    print(f"duplicates in B: {dict(report['duplicates'])}  change events in B: {report['changes_in_b']}")
    for kind, count in report["path_kinds"].most_common(args.show):
        print(f"  {count:5}  {kind}")
    if args.json:
        Path(args.json).write_text(json.dumps({**report, "path_kinds": dict(report["path_kinds"]), "duplicates": dict(report["duplicates"])}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
