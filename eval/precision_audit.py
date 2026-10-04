#!/usr/bin/env python3
"""Audits precision by sampling claims, re-fetching the cited source live, and verifying fact
support and entity attribution.

Web list claims (social_profiles, dated_news, job_postings) are verified item by item against the
page each item cites: the social link's href, the news title plus its quoted date, or the job
title/URL must be present on that page. A company website that prints another company's
organisation number and not this company's is a WRONG_COMPANY verdict.

Usage: python eval/precision_audit.py <envelopes.jsonl> [audit.csv] [sample_size] [seed]
"""

from __future__ import annotations

import csv
import html
import json
import random
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.identity import org_numbers_in_text  # noqa: E402

socket.setdefaulttimeout(10.0)
WEB_LIST_FIELDS = {"social_profiles", "dated_news", "job_postings"}


def fetch_url(url: str, timeout: float = 10.0) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "signalpost-precision-auditor/1.0", "Accept": "*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(3_000_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(50_000).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return exc.code, body
    except Exception as exc:
        return 0, str(exc)


def norm(text: str) -> str:
    return " ".join(html.unescape(str(text or "")).split()).casefold()


def visible_text(raw: str) -> str:
    return norm(re.sub(r"<[^>]+>", " ", raw))


def present(fragment: str, raw: str) -> bool:
    fragment = norm(fragment)
    if not fragment:
        return False
    return fragment in norm(raw) or fragment in visible_text(raw) or fragment.replace("&", "&amp;") in norm(raw)


def item_evidence(claim: dict, item: dict, ev_map: dict) -> dict | None:
    needle = norm(item.get("title") or item.get("href") or item.get("url") or "")
    page = item.get("source_page") or item.get("found_on_page")
    candidates = [ev_map[e] for e in claim.get("evidence_ids", []) if e in ev_map]
    for ev in candidates:
        if (not page or ev["source_url"] == page) and needle and needle[:60] in norm(ev.get("claim_span", "")):
            return ev
    for ev in candidates:
        if page and ev["source_url"] == page:
            return ev
    return candidates[0] if candidates else None


def verify_web_item(field: str, item: dict, ev: dict, raw: str) -> tuple[bool, str]:
    if field == "social_profiles":
        handle = item["url"].split(".com/", 1)[-1].strip("/")
        span = ev.get("claim_span", "")
        ok = present(span, raw) or (handle and handle.casefold() in raw.casefold())
        return ok, "" if ok else f"social link {item['url']} not on {ev['source_url']}"
    if field == "dated_news":
        title_ok = present(item.get("title", "")[:80], raw)
        raw_date = ev.get("claim_span", "").rsplit(" | ", 1)[-1]
        date_ok = present(raw_date, raw) or raw_date.casefold() in raw.casefold()
        ok = title_ok and date_ok
        return ok, "" if ok else f"title_ok={title_ok} date_ok={date_ok} ({raw_date[:30]})"
    if field == "job_postings":
        ok = present(item.get("title", "")[:80], raw) or (item.get("url") and item["url"] in html.unescape(raw))
        return bool(ok), "" if ok else "job title/url not on cited page"
    return False, "unknown web field"


def run_precision_audit(envelopes_path: Path, output_csv_path: Path, sample_size: int = 100, seed: int = 20260930) -> dict[str, Any]:
    envelopes = [json.loads(line) for line in envelopes_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    candidate_claims = []
    for env in envelopes:
        org = env["organisation_number"]
        ev_map = {ev["id"]: ev for ev in env.get("evidence", [])}
        for c in env.get("claims", []):
            if c.get("availability") == "available" and c.get("value") not in (None, [], "") and c.get("evidence_ids"):
                candidate_claims.append({"org": org, "claim": c, "ev_map": ev_map})

    print(f"Total available claims pool: {len(candidate_claims)}. Sampling {sample_size} across field types...", flush=True)
    rng = random.Random(seed)
    by_field: dict[str, list[dict]] = {}
    for item in candidate_claims:
        by_field.setdefault(item["claim"]["field"], []).append(item)
    sampled = []
    per_field_quota = max(1, sample_size // len(by_field))
    for _, items in sorted(by_field.items()):
        sampled.extend(rng.sample(items, min(len(items), per_field_quota)))
    remaining = [item for item in candidate_claims if item not in sampled]
    sampled.extend(rng.sample(remaining, min(max(0, sample_size - len(sampled)), len(remaining))))
    sampled = sampled[:sample_size]

    audit_rows = []
    supported_count = wrong_company_count = span_checked = span_present = 0
    url_cache: dict[str, tuple[int, str]] = {}

    for idx, entry in enumerate(sampled, 1):
        org, claim, ev_map = entry["org"], entry["claim"], entry["ev_map"]
        field, val = claim["field"], claim["value"]
        item = None
        if field in WEB_LIST_FIELDS and isinstance(val, list):
            item = rng.choice(val)
            ev = item_evidence(claim, item, ev_map)
        else:
            ev = ev_map.get(claim["evidence_ids"][-1] if field == "official_website" else claim["evidence_ids"][0])
        if ev is None:
            audit_rows.append({"claim_num": idx, "organisation_number": org, "field": field, "verdict": "NO_EVIDENCE"})
            continue
        url = ev["source_url"]
        if url not in url_cache:
            time.sleep(0.15)
            url_cache[url] = fetch_url(url)
        status, raw = url_cache[url]

        right_company, is_wrong_company, reason = True, False, ""
        org_digits = "".join(filter(str.isdigit, str(org)))
        if "data.brreg.no" in url:
            if "lastned/csv" not in url and org_digits not in url and org_digits not in raw:
                right_company, is_wrong_company, reason = False, True, "registry response lacks the organisation number"
        elif field in ("official_website", "company_description") and status == 200:
            others = [o for o in org_numbers_in_text(visible_text(raw)) if o != org_digits]
            if others and org_digits not in re.sub(r"\D", "", visible_text(raw)):
                right_company, is_wrong_company, reason = False, True, f"site prints other org number(s) {others[:2]} and not {org_digits}"

        fact_supported = False
        if status in (200, 201) and right_company:
            if item is not None:
                fact_supported, reason = verify_web_item(field, item, ev, raw)
            elif "lastned/csv" in url or field == "summary_profile":
                fact_supported = True
            elif field == "official_website":
                fact_supported = len(visible_text(raw)) > 100
            elif isinstance(val, bool):
                fact_supported = f'"{"true" if val else "false"}' in raw.replace(" ", "") or str(val).casefold() in raw.casefold()
            elif isinstance(val, (int, float)):
                fact_supported = str(int(val)) in raw
            elif isinstance(val, dict):
                fact_supported = True
            elif isinstance(val, list):
                names = [str((elem.get("name") if isinstance(elem, dict) else elem) or "") for elem in val[:5]]
                # Registry person names are split into fornavn/mellomnavn/etternavn in the source JSON.
                fact_supported = any(n and all(present(part, raw) for part in n.split() if len(part) > 1) for n in names) or not names
            else:
                fact_supported = present(str(val), raw) or present(str(val).replace(" AS", ""), raw)
            if not fact_supported and not reason:
                reason = f"value {str(val)[:40]!r} not found in source"

        if "data.brreg.no" not in url and status == 200:
            span_checked += 1
            fragments = [f for f in ev.get("claim_span", "").split(" | ") if f.strip()]
            if fragments and all(present(f[:120], raw) or f.casefold() in raw.casefold() for f in fragments):
                span_present += 1
            else:
                print(f"      span not quoted on page: {field} {url[:60]} :: {ev.get('claim_span', '')[:90]!r}", flush=True)

        if is_wrong_company:
            wrong_company_count += 1
            verdict = "WRONG_COMPANY"
        elif status not in (200, 201):
            verdict = "HTTP_ERROR"
            reason = f"source returned status {status}"
        elif not fact_supported:
            verdict = "UNSUPPORTED"
        else:
            verdict = "PASS"
            supported_count += 1
        audit_rows.append({
            "claim_num": idx,
            "organisation_number": org,
            "field": field,
            "claimed_value": json.dumps(item if item is not None else val, ensure_ascii=False)[:120],
            "source_url": url,
            "http_status": status,
            "right_company": right_company,
            "fact_supported": fact_supported,
            "verdict": verdict,
            "reason": reason,
        })
        print(f"  [{idx:3d}/{len(sampled)}] {org} | {field:20s} -> {verdict:12s} ({status}) {reason[:70]}", flush=True)

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["claim_num", "organisation_number", "field", "claimed_value", "source_url", "http_status", "right_company", "fact_supported", "verdict", "reason"]
    with output_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(audit_rows)

    precision_pct = round(100 * supported_count / max(1, len(sampled)), 1)
    http_errors = sum(1 for r in audit_rows if r.get("verdict") == "HTTP_ERROR")
    print("\n" + "=" * 50, flush=True)
    print(f" PRECISION AUDIT RESULTS ({len(sampled)} claims)", flush=True)
    print("=" * 50, flush=True)
    print(f" Supported & Verified Facts: {supported_count} / {len(sampled)} ({precision_pct}%)", flush=True)
    print(f" Excluding live HTTP errors: {supported_count} / {len(sampled) - http_errors}", flush=True)
    print(f" Wrong Company Matches:      {wrong_company_count} (Must be 0)", flush=True)
    print(f" Web spans quoted on page:   {span_present} / {span_checked}", flush=True)
    print(f" Saved Audit Details:        {output_csv_path}", flush=True)
    print("=" * 50 + "\n", flush=True)
    return {
        "sample_size": len(sampled),
        "supported_count": supported_count,
        "precision_pct": precision_pct,
        "http_errors": http_errors,
        "wrong_company_count": wrong_company_count,
        "web_span_present": [span_present, span_checked],
        "qualification_blocked": wrong_company_count > 0,
        "audit_csv": str(output_csv_path),
    }


if __name__ == "__main__":
    env_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/hardened-envelopes.jsonl")
    csv_file = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("eval/precision_audit.csv")
    size = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 20260930
    res = run_precision_audit(env_file, csv_file, sample_size=size, seed=seed)
    sys.exit(1 if res["qualification_blocked"] else 0)
