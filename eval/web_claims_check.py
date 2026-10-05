#!/usr/bin/env python3
"""End-to-end checks for the three Builderr web-claim reference companies."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = ("811730912", "813396092", "838797172")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="signalpost-web-claims-") as directory:
        work = Path(directory)
        inputs = work / "inputs.jsonl"
        output = work / "envelopes.jsonl"
        inputs.write_text(
            "".join(json.dumps({"organisation_number": org}) + "\n" for org in CASES),
            encoding="utf-8",
        )
        command = [
            sys.executable,
            str(ROOT / "run_agent.py"),
            "--organisations",
            str(inputs),
            "--output",
            str(output),
            "--workers",
            "3",
            "--max-runtime",
            "240",
            "--hard-deadline",
            "300",
        ]
        subprocess.run(command, cwd=ROOT, check=True)
        rows = {json.loads(line)["organisation_number"]: json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()}
        assert set(rows) == set(CASES), f"expected exactly {CASES}, got {sorted(rows)}"

        def claims(org: str, field: str) -> list[dict]:
            found = [c for c in rows[org]["claims"] if c["field"] == field]
            assert found, (org, field)
            return found

        def claim(org: str, field: str) -> dict:
            return claims(org, field)[0]

        def check_evidence(org: str, item: dict) -> None:
            evidence = {e["id"]: e for e in rows[org]["evidence"]}
            assert item["evidence_ids"], item
            for eid in item["evidence_ids"]:
                ev = evidence[eid]
                assert len(ev["content_sha256"]) == 64 and ev["claim_span"].strip() and ev["retrieved_at"], ev

        # One claim per fact; every available claim has a scalar value and its own evidence.
        for org in CASES:
            for c in rows[org]["claims"]:
                if c["field"] in ("social_profile", "dated_news", "hiring_signal") and c["availability"] == "available":
                    assert isinstance(c["value"], str) and c["value"], c
                    check_evidence(org, c)

        # 811730912: Facebook and Instagram linked from its own verified website.
        social = [c for c in claims("811730912", "social_profile") if c["availability"] == "available"]
        social_urls = {c["value"] for c in social}
        assert "https://facebook.com/mtmskogservice" in social_urls, social_urls
        assert any("instagram.com" in url for url in social_urls), social_urls
        assert all(c.get("source_url") for c in social), social

        # 813396092: registry-declared bori.no; dated items from the bori.no/aktuelt news section.
        news = [c for c in claims("813396092", "dated_news") if c["availability"] == "available"]
        assert news, claims("813396092", "dated_news")
        assert all(c.get("verification_method") == "registry_declared_domain" for c in news), news
        assert all(c["value"] == f"{c['title']} ({c['published_at']})" and c.get("url") for c in news), news
        assert any("bori.no" in c["url"] and "/aktuelt" in c["url"] for c in news), news
        site = claim("813396092", "official_website")
        site_sources = {e["id"]: e["source_url"] for e in rows["813396092"]["evidence"]}
        assert any("data.brreg.no" in site_sources[e] for e in site["evidence_ids"]), site

        # 838797172: the granne.no careers page is itself the hiring signal, plus any postings.
        hiring = [c for c in claims("838797172", "hiring_signal") if c["availability"] == "available"]
        careers = [c for c in hiring if c.get("kind") == "careers_page"]
        assert careers and "granne.no/ledige-stillinger" in careers[0]["value"], claims("838797172", "hiring_signal")
        assert all(c.get("title") for c in hiring if c.get("kind") == "job_posting"), hiring

        print("web_claims_check: PASS")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
