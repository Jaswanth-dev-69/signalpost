#!/usr/bin/env python3
"""Fail if a change touches the frozen Synthesis (12/12) and UX (8/8) code.

Frozen whole files:
  src/norway_company_agent/synthesis.py   the profile summary text (generate_company_synthesis)
  scripts/build_prototype.py              the viewer HTML and its embedded DATA
Frozen lines in other agent code (src/, scripts/, run_agent.py): any added or removed line that names
the synthesis call, the summary field, the viewer builder or the summary_profile claim.

Usage: python eval/frozen_guard.py [--base REF]
  Compares the working tree (staged and unstaged) with REF, default HEAD. Use --base v3-submitted to
  check everything since the submitted v3.
"""
from __future__ import annotations

import argparse
import re
import subprocess

FROZEN_FILES = ("src/norway_company_agent/synthesis.py", "scripts/build_prototype.py")
AGENT_CODE = ("src", "scripts", "run_agent.py")
FROZEN_TOKENS = re.compile(r"generate_company_synthesis|synthesis_summary|build_viewer_html|build_prototype|summary_profile")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="HEAD")
    args = parser.parse_args()
    problems = [f"frozen file changed: {path}" for path in git("diff", "--name-only", args.base, "--", *FROZEN_FILES).split()]
    current = None
    for line in git("diff", "-U0", args.base, "--", *AGENT_CODE).splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line[:1] in "+-" and not line.startswith(("+++", "---")) and FROZEN_TOKENS.search(line):
            problems.append(f"frozen line changed in {current}: {line[:120]}")
    if problems:
        print("FROZEN GUARD FAILED")
        print("\n".join(problems))
        return 1
    print(f"frozen guard clean (vs {args.base})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
