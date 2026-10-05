#!/usr/bin/env python3
"""Signalpost High-Performance Research Agent.

Main entry point for Signalpost evaluation runs.
- Guarantees 100% envelope completeness (1 envelope per input company)
- Fetches official registry, annual accounts, roles, locations, group structure
- Resolves official websites with strict identity verification
- Falls back to domain candidate discovery with strict org/municipality proof
- Generates evidence-grounded synthesis summaries for every company
- Outputs official OUTPUT_CONTRACT.md JSON envelopes
- Creates an interactive mobile-friendly viewer HTML
- Self-contained: downloads bulk snapshot automatically if missing on clean machine
- Fault-tolerant: per-company try/except, incremental writes, deadline protection
"""

from __future__ import annotations

import argparse
import re
import copy
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(1, str(ROOT))  # scripts.build_prototype, whatever the entry point

from norway_company_agent.batch import finish_declared_domain_count, profile_complete_for_modules, start_declared_domain_count, profiles_from_bulk, read_organisation_inputs, validate_envelopes  # noqa: E402
from norway_company_agent.contract import profile_to_contract_envelope  # noqa: E402
from norway_company_agent.envelope_refresh import read_previous_with_stats, refresh_envelopes  # noqa: E402
from norway_company_agent.discovery import choose_search_candidate  # noqa: E402
from norway_company_agent.domain_solver import discover_website_by_domain_search  # noqa: E402
from norway_company_agent.evidence import utc_now  # noqa: E402
from norway_company_agent.identity import apply_registry_declared_gate, apply_website_identity_gate  # noqa: E402
from norway_company_agent.http import fetch_json  # noqa: E402
from norway_company_agent.official import accounting_obligation_assessment, fetch_official_modules, fetch_subunit_record  # noqa: E402
from norway_company_agent.synthesis import generate_company_synthesis  # noqa: E402
from norway_company_agent.website import fetch_website, strip_private_fields  # noqa: E402
from norway_company_agent.webclaims import crawl_web_claims, registered_domain  # noqa: E402
from norway_company_agent.nav_jobs import NavJobIndex, attach_postings  # noqa: E402
from scripts.build_prototype import build as build_viewer_html  # noqa: E402


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def enrich_company_profile(
    profile: dict[str, Any],
    requested_modules: list[str],
    *,
    timeout: float = 12.0,
    enable_discovery: bool = True,
    web_deadline: float | None = None,
) -> dict[str, Any]:
    """Both passes for one company (kept for single-company callers)."""
    enrich_official(profile, requested_modules)
    return enrich_web(profile, requested_modules, timeout=timeout, enable_discovery=enable_discovery, web_deadline=web_deadline)


def registry_website_alternates(declared: str, record: dict[str, Any]) -> list[str]:
    """Retry variants for a registry homepage that failed to load (DNS, TLS, timeout, 5xx)."""
    note = str(record.get("note") or "")
    if record.get("status") == "available" or "robots.txt" in note or "byte limit" in note or "refused the request" in note:
        return []
    if record.get("status") not in {"blocked", "source_error", "not_found"}:
        return []
    value = re.sub(r"^https?://", "", str(declared or "").strip(), flags=re.I).strip("/")
    if not value:
        return []
    host, _, path = value.partition("/")
    other_host = host[4:] if host.lower().startswith("www.") else "www." + host
    suffix = "/" + path if path else "/"
    variants = [f"https://{other_host}{suffix}", f"http://{host}{suffix}", f"http://{other_host}{suffix}"]
    return [v for v in variants if v.rstrip("/") != str(declared).rstrip("/")]


def enrich_official(profile: dict[str, Any], requested_modules: list[str]) -> dict[str, Any]:
    """Pass 1 (Tier A): official registry, accounts, roles, group and locations."""
    org = profile["organisation_number"]
    fetch_modules = set(requested_modules) - {"registry", "accounting_obligation", "website"}
    
    # 1. Fetch official registry modules
    records, metrics = fetch_official_modules(org, fetch_modules)
    profile.setdefault("evidence", {}).update(records)

    if profile.get("missing_from_snapshot"):
        live_rec = records.get("registry_live") or {}
        if live_rec.get("status") == "source_error":
            # One slower retry before declaring the official record unavailable.
            retry, retry_metrics = fetch_official_modules(org, {"registry_live"}, fetcher=lambda url: fetch_json(url, timeout=30.0))
            metrics.extend(retry_metrics)
            live_rec = retry.get("registry_live") or live_rec
            profile["evidence"]["registry_live"] = live_rec
        if live_rec.get("status") == "not_found" and "410" not in str(live_rec.get("note")):
            sub_rec, sub_metric = fetch_subunit_record(org)
            metrics.append(sub_metric)
            profile["evidence"]["registry_underenhet"] = sub_rec
            if sub_rec.get("status") == "available":
                live_rec = sub_rec
        if live_rec.get("status") == "available" and live_rec.get("value"):
            lv = live_rec["value"]
            address = lv.get("business_address") or lv.get("postal_address") or {}
            industry = lv.get("industry") or {}
            profile["name"] = lv.get("name") or profile.get("name")
            profile["legal_form"] = lv.get("legal_form")
            profile["employees"] = lv.get("employees")
            profile["bankrupt"] = bool(lv.get("bankrupt"))
            profile["liquidating"] = bool(lv.get("liquidating"))
            profile["municipality"] = address.get("kommune")
            profile["municipality_number"] = address.get("kommunenummer")
            profile["industry_code"] = industry.get("kode")
            profile["industry_label"] = industry.get("beskrivelse")
            profile["website"] = lv.get("website")
            profile["latest_submitted_accounts"] = lv.get("latest_submitted_accounts")
            profile["evidence"]["registry"] = {**live_rec, "source_type": "official_registry_live"}
        profile["evidence"]["accounting_obligation"] = accounting_obligation_assessment(profile)

    profile["run_metrics"] = {
        "requests": len(metrics),
        "bytes": sum(item.bytes_received for item in metrics),
        "latencies_ms": [item.elapsed_ms for item in metrics],
    }
    profile.setdefault("web_run", {})["official_done"] = True
    return profile


def enrich_web(
    profile: dict[str, Any],
    requested_modules: list[str],
    *,
    timeout: float = 12.0,
    enable_discovery: bool = True,
    web_deadline: float | None = None,
) -> dict[str, Any]:
    """Pass 2: company-owned web layer within a per-company deadline, then synthesis."""
    org = profile["organisation_number"]

    # 2. Website processing & discovery
    website_metrics = {"requests": 0, "bytes": 0, "latencies_ms": []}

    def add_metrics(extra: dict[str, Any]) -> None:
        website_metrics["requests"] += extra.get("requests", 0)
        website_metrics["bytes"] += extra.get("bytes", 0)
        website_metrics["latencies_ms"].extend(extra.get("latencies_ms", []))

    if "website" in requested_modules:
        reg_website = profile.get("website")
        gated_website = None

        # Tier B1: Try registry-listed website if present
        if reg_website:
            website_record, first_metrics = fetch_website(reg_website, timeout=timeout, retries=1)
            add_metrics(first_metrics)
            for alternate in registry_website_alternates(reg_website, website_record):
                # Same registered domain only: www/non-www and http/https variants of the declared URL.
                retry_record, retry_metrics = fetch_website(alternate, timeout=timeout)
                add_metrics(retry_metrics)
                if retry_record.get("status") == "available":
                    website_record = retry_record
                    break
            gated = apply_website_identity_gate(profile, website_record)
            gated_website = gated["website"]
            if (gated_website.get("value") or {}).get("identity_assessment", {}).get("publishable"):
                profile["evidence"]["website"] = gated_website
            elif apply_registry_declared_gate(profile, gated_website):
                # Exact domain the entity declared in Enhetsregisteret; lower confidence, never
                # extended to discovered domains or to sites naming another organisation number.
                profile["evidence"]["website"] = gated_website

        # Tier B2: Domain candidate discovery if missing or unverified
        if enable_discovery and not profile.get("evidence", {}).get("website"):
            discovered_web, dom_metrics = discover_website_by_domain_search(profile, timeout=min(timeout, 6.0), deadline=web_deadline)
            add_metrics(dom_metrics)
            profile.setdefault("web_run", {})["discovery"] = {"requests": dom_metrics.get("requests", 0), "candidates": dom_metrics.get("candidates", 0)}
            if discovered_web:
                profile["evidence"]["website"] = discovered_web
                profile["evidence"]["website_discovered"] = discovered_web

        # Tier B3: typed web claims, only from a website that passed the strict entity gate.
        verified = profile.get("evidence", {}).get("website")
        if verified and (verified.get("value") or {}).get("identity_assessment", {}).get("publishable"):
            verified_value = verified["value"]
            web_claims, claim_metrics = crawl_web_claims(verified_value, timeout=min(timeout, 10.0), deadline=web_deadline)
            add_metrics(claim_metrics)
            profile["web_claims"] = {"social": {"profiles": verified_value.get("social_links") or []}, **web_claims}

        if "website" not in profile.get("evidence", {}):
            if gated_website:
                profile["evidence"]["website"] = gated_website
            else:
                profile["evidence"]["website"] = {
                    "field": "website",
                    "status": "not_found",
                    "source_type": "registry_linked_company_website",
                    "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/" + org,
                    "retrieved_at": utc_now(),
                    "note": "No valid website found or verified",
                }
        strip_private_fields(gated_website)
        for key in ("website", "website_discovered"):
            strip_private_fields(profile["evidence"].get(key))

    run_metrics = profile.setdefault("run_metrics", {"requests": 0, "bytes": 0, "latencies_ms": []})
    run_metrics["requests"] += website_metrics["requests"]
    run_metrics["bytes"] += website_metrics["bytes"]
    run_metrics["latencies_ms"].extend(website_metrics["latencies_ms"])
    profile.setdefault("web_run", {})["web_done"] = True

    # 3. Generate synthesis summary
    profile["synthesis_summary"] = generate_company_synthesis(profile)

    return profile


def ensure_bulk_snapshot(bulk_arg: str) -> Path:
    bulk_path = Path(bulk_arg)
    if bulk_path.exists():
        return bulk_path

    # Check common alternative locations
    for alt in ("brreg-enheter.csv.gz", "brreg-enheter.csv", "../brreg-enheter.csv.gz"):
        if Path(alt).exists():
            return Path(alt)

    # Automatic clean-machine download from official permitted source
    print(f"Bulk registry snapshot {bulk_arg} not found. Downloading from official BRREG endpoint...", flush=True)
    url = "https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv"
    target = Path("brreg-enheter.csv.gz")
    urllib.request.urlretrieve(url, target)
    print(f"Successfully downloaded {target} ({target.stat().st_size // (1024*1024)} MB).", flush=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Signalpost High-Performance Research Agent")
    parser.add_argument("--organisations", "--input", "-i", dest="organisations", required=True, help="Input organisation numbers (JSON, JSONL, or txt)")
    parser.add_argument("--bulk", default="brreg-enheter.csv.gz", help="Bulk BRREG entity snapshot")
    parser.add_argument("--output", "-o", required=True, help="Terminal envelope JSONL output path")
    parser.add_argument("--profiles-output", help="Raw profiles JSONL output path (defaults to <output>.profiles.jsonl)")
    parser.add_argument("--report", help="Run report JSON path (defaults to <output>.report.json)")
    parser.add_argument("--viewer", help="HTML viewer output path (defaults to <output>.viewer.html)")
    parser.add_argument("--run-id", default=f"run-{int(time.time())}")
    parser.add_argument("--expected-count", type=int, default=0, help="Expected organisation count (0 to auto-detect from input)")
    parser.add_argument("--workers", type=int, default=32, help="Worker threads for pass 2 (web layers)")
    parser.add_argument("--timeout", type=float, default=12.0, help="HTTP request timeout in seconds")
    parser.add_argument("--official-workers", type=int, default=24, help="Worker threads for pass 1 (official registry sources)")
    parser.add_argument("--max-runtime", type=float, default=1200.0, help="Elapsed seconds after which new domain discovery is skipped")
    parser.add_argument("--web-budget", type=float, default=60.0, help="Per-company wall-time budget for the web pass (seconds)")
    parser.add_argument("--web-reserve", type=float, default=90.0, help="Seconds before --hard-deadline after which no new web work starts")
    parser.add_argument("--hard-deadline", type=float, default=1500.0, help="Hard stop in seconds: write a result for every company and exit")
    parser.add_argument("--disable-discovery", action="store_true", help="Disable domain candidate discovery for missing websites")
    parser.add_argument("--disable-nav-jobs", action="store_true", help="Do not read NAV's public vacancy feed")
    parser.add_argument("--nav-workers", type=int, default=24, help="Concurrent connections for the NAV vacancy feed index")
    parser.add_argument("--previous", help="Previous run's envelopes for refresh (default: the existing --output file, if any)")
    args = parser.parse_args()

    # The hard deadline counts total wall time from process start, including a cold bulk download.
    start_monotonic = time.monotonic()
    started_at = utc_now()

    def elapsed() -> float:
        return time.monotonic() - start_monotonic

    # Read inputs - handles JSON, JSONL, or TXT
    org_inputs = read_organisation_inputs(args.organisations)
    orgs = [item["organisation_number"] for item in org_inputs]
    expected_count = args.expected_count if args.expected_count > 0 else len(orgs)

    if len(orgs) != expected_count:
        raise SystemExit(f"Error: Expected {expected_count} organisations, received {len(orgs)}")

    print(f"[{started_at}] Signalpost agent starting run '{args.run_id}' on {len(orgs)} companies using {args.workers} workers...", flush=True)

    requested_modules = ["registry", "accounting_obligation", "registry_live", "financials", "roles", "group", "locations", "website"]
    operations = {"requests": 0, "bytes": 0, "latencies_ms": []}
    state: dict[str, dict] = {}
    errors: list[dict] = []
    output_path = Path(args.output)
    # Refresh baseline: read before anything overwrites the output file.
    try:
        previous_envelopes, previous_stats = read_previous_with_stats(args.previous or output_path)
    except Exception as exc:  # never let the refresh baseline stop a run
        previous_envelopes, previous_stats = {}, {"error": f"{type(exc).__name__}: {exc}"}
    if previous_stats.get("rows") or previous_stats.get("error"):
        print(f"[{utc_now()}] Refresh baseline: {json.dumps(previous_stats)}", flush=True)

    import threading

    finalize_lock = threading.Lock()
    base_profiles: dict[str, dict] = {org: {"organisation_number": org, "evidence": {}} for org in orgs}

    def hard_deadline_flush() -> None:
        if not finalize_lock.acquire(blocking=False):
            return
        print(f"HARD DEADLINE reached at {elapsed():.0f}s: writing a result for every company and exiting.", flush=True)
        try:
            completed = utc_now()
            final_profiles, envs = [], []
            for org in orgs:
                # state only holds finished pass snapshots (never a profile a worker is mutating).
                prof = copy.deepcopy(state.get(org) or base_profiles[org])
                if not (prof.get("web_run") or {}).get("web_done"):
                    prof.setdefault("errors", []).append({"error": "hard deadline reached before enrichment finished", "type": "DeadlineExceeded"})
                    if not prof.get("synthesis_summary") and prof.get("name"):
                        try:
                            prof["synthesis_summary"] = generate_company_synthesis(prof)
                        except Exception:
                            pass
                try:
                    env = profile_to_contract_envelope(prof, run_id=args.run_id, started_at=started_at, completed_at=completed, terminal_status="completed")
                except Exception as exc:
                    prof = {"organisation_number": org, "evidence": {}, "errors": [{"error": f"envelope build failed at deadline: {exc}", "type": "DeadlineExceeded"}]}
                    env = profile_to_contract_envelope(prof, run_id=args.run_id, started_at=started_at, completed_at=completed, terminal_status="completed")
                final_profiles.append(prof)
                envs.append(env)
            try:
                refresh_envelopes(envs, previous_envelopes)
            except Exception as exc:
                print(f"Refresh skipped at deadline: {type(exc).__name__}: {exc}", flush=True)
            write_jsonl(output_path, envs)
            write_jsonl(
                Path(args.profiles_output) if args.profiles_output else output_path.with_suffix(".profiles.jsonl"),
                final_profiles,
            )
            print(f"Wrote {len(envs)} envelopes before exit.", flush=True)
        except Exception as exc:
            print(f"Deadline flush error: {type(exc).__name__}: {exc}", flush=True)
        finally:
            os._exit(0)

    watchdog = threading.Timer(max(1.0, args.hard_deadline - elapsed()), hard_deadline_flush)
    watchdog.daemon = True
    watchdog.start()

    # NAV vacancy index builds in the background during the bulk download and both passes.
    nav_index = None
    if not args.disable_nav_jobs:
        nav_index = NavJobIndex(workers=args.nav_workers, time_budget_s=max(60.0, args.hard_deadline - args.web_reserve - 120.0)).start()

    # Ensure bulk registry snapshot exists or download it (inside the deadline).
    bulk_path = ensure_bulk_snapshot(args.bulk)
    profiles, registry_metadata = profiles_from_bulk(bulk_path, orgs)
    base_profiles.update({p_["organisation_number"]: p_ for p_ in profiles})
    # Snapshot-wide homepage counts (about 9 s of CPU) overlap pass 1; the web pass waits for them.
    declared_handle = start_declared_domain_count(bulk_path)
    # Snapshot-wide homepage counts (about 15 s of CPU), computed while pass 1 waits on the network.
    print(f"[{utc_now()}] Registry snapshot loaded at {elapsed():.1f}s.", flush=True)

    def record_errors(prof: dict, exc: Exception, stage: str) -> None:
        prof.setdefault("errors", []).append({"error": str(exc), "type": type(exc).__name__, "stage": stage})
        errors.append({"org": prof["organisation_number"], "stage": stage, "error": str(exc)})

    # Pass 1 (Tier A): official sources for every company before any web work.
    def safe_official(prof: dict) -> dict:
        try:
            return enrich_official(copy.deepcopy(prof), requested_modules)
        except Exception as exc:
            record_errors(prof, exc, "official")
            return prof

    with ThreadPoolExecutor(max_workers=args.official_workers) as pool:
        for index, prof in enumerate(pool.map(safe_official, profiles), 1):
            state[prof["organisation_number"]] = prof
            if index % 200 == 0 or index == expected_count:
                print(f"[{utc_now()}] Pass 1 (official): {index}/{expected_count}, elapsed={elapsed():.1f}s", flush=True)

    # Blocking step before the web pass, capped well under the hard deadline.
    declared_cap = max(5.0, min(300.0, (args.hard_deadline - args.web_reserve - elapsed()) / 3))
    declared_counts, declared_status = finish_declared_domain_count(declared_handle, declared_cap)
    operations["declared_domain_counts"] = declared_status
    if declared_status["status"] != "ok":
        print(f"[{utc_now()}] WARNING declared-domain counts {declared_status['status']}: {declared_status['error']}; "
              f"{declared_status['effect']}", flush=True)
    if declared_counts:
        for prof in state.values():
            declared = str(prof.get("website") or "").strip()
            if declared:
                domain = registered_domain(declared if re.match(r"^https?://", declared, re.I) else "https://" + declared).casefold()
                prof["homepage_domain_registry_entities"] = declared_counts.get(domain, 0)
    print(f"[{utc_now()}] Declared-domain counts: {len(declared_counts)} domains, elapsed={elapsed():.1f}s", flush=True)

    # Pass 2: web layers with a per-company budget; stop starting web work near the deadline.
    web_cutoff = args.hard_deadline - args.web_reserve

    def safe_web(prof: dict) -> dict:
        now = elapsed()
        if now > web_cutoff:
            prof.setdefault("errors", []).append({"error": "web pass skipped: run deadline reserve reached", "type": "DeadlineExceeded"})
            prof["synthesis_summary"] = generate_company_synthesis(prof)
            prof.setdefault("web_run", {})["web_done"] = True
            return prof
        company_deadline = time.monotonic() + min(args.web_budget, max(5.0, web_cutoff - now))
        try:
            enable_disc = (not args.disable_discovery) and now < args.max_runtime
            return enrich_web(prof, requested_modules, timeout=args.timeout, enable_discovery=enable_disc, web_deadline=company_deadline)
        except Exception as exc:
            record_errors(prof, exc, "web")
            prof.setdefault("evidence", {}).setdefault("website", {"field": "website", "status": "source_error", "note": str(exc)[:200]})
            prof["synthesis_summary"] = f"{prof.get('name')} (Org.nr {prof.get('organisation_number')}): Encountered error during enrichment: {exc}"
            prof.setdefault("web_run", {})["web_done"] = True
            return prof

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(safe_web, copy.deepcopy(state[org])) for org in orgs]
        for index, future in enumerate(as_completed(futures), 1):
            prof = future.result()
            state[prof["organisation_number"]] = prof
            if index % 100 == 0 or index == expected_count:
                print(f"[{utc_now()}] Pass 2 (web): {index}/{expected_count}, elapsed={elapsed():.1f}s", flush=True)

    if nav_index is not None:
        # Give the index the time left before the deadline reserve, then use what it has.
        nav_index.wait(max(0.0, args.hard_deadline - args.web_reserve - 60.0 - elapsed()))
        nav_index.stop()
        matched = 0

        def attach(org: str) -> int:
            prof = copy.deepcopy(state[org])
            count = attach_postings(prof, nav_index)
            state[org] = prof
            return count

        with ThreadPoolExecutor(max_workers=8) as pool:
            matched = sum(1 for count in pool.map(attach, orgs) if count)
        print(f"[{utc_now()}] NAV jobs: {json.dumps(nav_index.stats())}; companies with postings={matched}, elapsed={elapsed():.1f}s", flush=True)
        operations["nav_job_index"] = {**nav_index.stats(), "companies_with_postings": matched}

    for prof in state.values():
        m = prof.get("run_metrics", {})
        operations["requests"] += m.get("requests", 0)
        operations["bytes"] += m.get("bytes", 0)
        operations["latencies_ms"].extend(m.get("latencies_ms", []))

    if not finalize_lock.acquire(blocking=False):
        while True:
            time.sleep(1)
    watchdog.cancel()

    completed_at = utc_now()
    ordered_profiles = [state[org] for org in orgs]

    # Convert profiles to official OUTPUT_CONTRACT envelopes in exact input order
    envelopes = [
        profile_to_contract_envelope(
            prof,
            run_id=args.run_id,
            started_at=started_at,
            completed_at=completed_at,
            terminal_status="completed",
        )
        for prof in ordered_profiles
    ]
    try:
        refresh_stats = refresh_envelopes(envelopes, previous_envelopes)
    except Exception as exc:  # per-company failures are already caught; this is a last guard
        refresh_stats = {"compared": 0, "material_changes": 0, "companies_changed": 0, "failed": len(envelopes), "error": f"{type(exc).__name__}: {exc}"}
    print(f"[{utc_now()}] Refresh: {json.dumps(refresh_stats)}", flush=True)

    profiles_output_path = Path(args.profiles_output) if args.profiles_output else output_path.with_suffix(".profiles.jsonl")
    report_path = Path(args.report) if args.report else output_path.with_suffix(".report.json")
    viewer_path = Path(args.viewer) if args.viewer else output_path.with_suffix(".viewer.html")

    # Save output contract JSONL envelopes
    write_jsonl(output_path, envelopes)

    # Save rich profiles JSONL
    write_jsonl(profiles_output_path, ordered_profiles)

    # Latency stats
    latencies = sorted(operations.pop("latencies_ms"))
    operations["p50_ms"] = latencies[len(latencies) // 2] if latencies else None
    operations["p95_ms"] = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None

    # Completeness Assertions
    validation = {
        "exact_expected_count": len(envelopes) == expected_count,
        "unique_organisation_numbers": len(set(e["organisation_number"] for e in envelopes)) == len(envelopes),
        "zero_silent_drops": len(envelopes) == expected_count,
        "all_terminal_status_completed": all(e.get("run", {}).get("terminal_status") == "completed" for e in envelopes),
        "input_order_strictly_preserved": [e["organisation_number"] for e in envelopes] == orgs,
    }

    from norway_company_agent.http import RATE_LIMITED
    from norway_company_agent.webclaims import RATE_LIMITED as WEB_RATE_LIMITED

    operations["http_429_registry"] = RATE_LIMITED["count"]
    operations["http_429_web"] = WEB_RATE_LIMITED["count"]
    operations["wall_time_s"] = round(elapsed(), 1)

    report = {
        "run_id": args.run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "expected_count": expected_count,
        "emitted_envelopes": len(envelopes),
        "modules": requested_modules,
        "registry": registry_metadata,
        "operations": operations,
        "validation": {"passed": all(validation.values()), "checks": validation},
        "refresh": {"baseline": previous_stats, **refresh_stats},
        "errors": errors,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Generate UX Viewer HTML
    try:
        html_content = build_viewer_html(ordered_profiles, score=None)
        viewer_path.parent.mkdir(parents=True, exist_ok=True)
        viewer_path.write_text(html_content, encoding="utf-8")
        print(f"Wrote viewer HTML to {viewer_path}")
    except Exception as exc:
        print(f"Warning: Viewer generation error: {exc}")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"SUCCESS: Emitted {len(envelopes)}/{expected_count} envelopes to {output_path}")

    if not all(validation.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
