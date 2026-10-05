"""`signalpost` project script: runs the repository's `run_agent.py` with the given arguments."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path


def _agent_path() -> Path:
    for base in (Path(__file__).resolve().parents[2], Path.cwd()):
        candidate = base / "run_agent.py"
        if candidate.exists():
            return candidate
    raise SystemExit("run_agent.py not found: run `signalpost` from the repository checkout")


def main() -> None:
    agent = _agent_path()
    sys.argv = [str(agent), *sys.argv[1:]]
    runpy.run_path(str(agent), run_name="__main__")
