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

        def claim(org: str, field: str) -> dict:
            return next(c for c in rows[org]["claims"] if c["field"] == field)

        def check_evidence(org: str, item: dict) -> None:
            evidence = {e["id"]: e for e in rows[org]["evidence"]}
            assert item["evidence_ids"], item
            for eid in item["evidence_ids"]:
                ev = evidence[eid]
                assert len(ev["content_sha256"]) == 64 and ev["claim_span"].strip() and ev["retrieved_at"], ev

        # 811730912: Facebook and Instagram linked from its own verified website.
        social = claim("811730912", "social_profiles")
        social_urls = {item["url"] for item in (social["value"] or [])}
        assert social["availability"] == "available", social
        assert any("facebook.com" in url for url in social_urls), social_urls
        assert any("instagram.com" in url for url in social_urls), social_urls
        check_evidence("811730912", social)

        # 813396092: registry-declared bori.no; dated items from the bori.no/aktuelt news section.
        news = claim("813396092", "dated_news")
        assert news["availability"] == "available", news
        assert news.get("verification_method") == "registry_declared_domain", news
        dated = [i for i in news["value"] if i.get("published_date") and i.get("url") and i.get("title")]
        assert dated, news
        assert any("bori.no" in i["url"] and "/aktuelt" in i["url"] for i in dated), news
        check_evidence("813396092", news)
        site = claim("813396092", "official_website")
        site_sources = {e["id"]: e["source_url"] for e in rows["813396092"]["evidence"]}
        assert any("data.brreg.no" in site_sources[e] for e in site["evidence_ids"]), site

        # 838797172: postings, or an explicit not_available backed by granne.no/ledige-stillinger.
        jobs = claim("838797172", "job_postings")
        if jobs["availability"] == "available":
            assert any(item.get("title") and item.get("url") for item in jobs["value"]), jobs
        else:
            assert jobs["availability"] == "not_available", jobs
            evidence = {item["id"]: item for item in rows["838797172"]["evidence"]}
            assert any("granne.no/ledige-stillinger" in evidence[eid]["source_url"] for eid in jobs["evidence_ids"]), jobs
        check_evidence("838797172", jobs)

        print("web_claims_check: PASS")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
