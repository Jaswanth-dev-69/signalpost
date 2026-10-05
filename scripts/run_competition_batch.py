#!/usr/bin/env python3
"""The starter kit's documented batch command, kept as a thin wrapper around `run_agent.py`.

Accepts the kit's arguments and runs the same agent, so `scripts/run_competition_batch.py`,
`run_agent.py` and the `signalpost` project script all produce the same envelopes. Kit options that
the agent does not use (`--checkpoint-every`, `--resume`, `--modules`) are accepted and ignored: the
agent always runs every module and writes one terminal envelope per input.
"""
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def agent_argv(argv: list[str]) -> list[str]:
    parser = argparse.ArgumentParser(description="Signalpost batch command (wrapper around run_agent.py)")
    parser.add_argument("--organisations", required=True, help="JSON, JSONL, or text organisation-number list")
    parser.add_argument("--bulk", help="Frozen Brreg entity snapshot (gzip or plain CSV)")
    parser.add_argument("--output", required=True, help="Terminal envelope JSONL")
    parser.add_argument("--profiles-output")
    parser.add_argument("--report")
    parser.add_argument("--run-id")
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--checkpoint-every", type=int, help="accepted for compatibility; ignored")
    parser.add_argument("--resume", action="store_true", help="accepted for compatibility; ignored")
    parser.add_argument("--modules", help="accepted for compatibility; every module always runs")
    args, extra = parser.parse_known_args(argv)
    forwarded = ["--organisations", args.organisations, "--output", args.output]
    for flag, value in (("--bulk", args.bulk), ("--profiles-output", args.profiles_output), ("--report", args.report),
                        ("--run-id", args.run_id), ("--expected-count", args.expected_count), ("--workers", args.workers)):
        if value is not None:
            forwarded += [flag, str(value)]
    return forwarded + extra


def main() -> None:
    sys.argv = [str(ROOT / "run_agent.py"), *agent_argv(sys.argv[1:])]
    runpy.run_path(str(ROOT / "run_agent.py"), run_name="__main__")


if __name__ == "__main__":
    main()
