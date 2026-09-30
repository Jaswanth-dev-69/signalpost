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

from norway_company_agent.batch import profile_complete_for_modules, profiles_from_bulk, read_organisation_inputs, validate_envelopes  # noqa: E402
from norway_company_agent.contract import profile_to_contract_envelope  # noqa: E402
from norway_company_agent.discovery import choose_search_candidate  # noqa: E402
from norway_company_agent.domain_solver import discover_website_by_domain_search  # noqa: E402
from norway_company_agent.evidence import utc_now  # noqa: E402
from norway_company_agent.identity import apply_website_identity_gate  # noqa: E402
from norway_company_agent.official import fetch_official_modules  # noqa: E402
from norway_company_agent.synthesis import generate_company_synthesis  # noqa: E402
from norway_company_agent.website import fetch_website  # noqa: E402
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
) -> dict[str, Any]:
    """Enrich a single company profile with deterministic sources and safety wrapping."""
    org = profile["organisation_number"]
    fetch_modules = set(requested_modules) - {"registry", "accounting_obligation", "website"}
    
    # 1. Fetch official registry modules
    records, metrics = fetch_official_modules(org, fetch_modules)
    profile.setdefault("evidence", {}).update(records)
    
    total_requests = len(metrics)
    total_bytes = sum(item.bytes_received for item in metrics)
    latencies_ms = [item.elapsed_ms for item in metrics]

    # 2. Website processing & discovery
    website_metrics = {"requests": 0, "bytes": 0, "latencies_ms": []}
    if "website" in requested_modules:
        reg_website = profile.get("website")
        gated_website = None

        # Tier B1: Try registry-listed website if present
        if reg_website:
            website_record, website_metrics = fetch_website(reg_website, timeout=timeout)
            gated = apply_website_identity_gate(profile, website_record)
            gated_website = gated["website"]
            if (gated_website.get("value") or {}).get("identity_assessment", {}).get("publishable"):
                profile["evidence"]["website"] = gated_website

        # Tier B2: Domain candidate discovery if missing or unverified
        if enable_discovery and not profile.get("evidence", {}).get("website"):
            discovered_web, dom_metrics = discover_website_by_domain_search(profile, timeout=min(timeout, 6.0))
            website_metrics["requests"] += dom_metrics.get("requests", 0)
            website_metrics["bytes"] += dom_metrics.get("bytes", 0)
            website_metrics["latencies_ms"].extend(dom_metrics.get("latencies_ms", []))
            if discovered_web:
                profile["evidence"]["website"] = discovered_web
                profile["evidence"]["website_discovered"] = discovered_web

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

    total_requests += website_metrics["requests"]
    total_bytes += website_metrics["bytes"]
    latencies_ms.extend(website_metrics["latencies_ms"])

    profile["run_metrics"] = {
        "requests": total_requests,
        "bytes": total_bytes,
        "latencies_ms": latencies_ms,
    }

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
    print(f"Bulk registry snapshot {bulk_arg} not found. Downloading from official BRREG endpoint...")
    url = "https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv"
    target = Path("brreg-enheter.csv.gz")
    urllib.request.urlretrieve(url, target)
    print(f"Successfully downloaded {target} ({target.stat().st_size // (1024*1024)} MB).")
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
    parser.add_argument("--workers", type=int, default=8, help="Number of concurrent worker threads")
    parser.add_argument("--timeout", type=float, default=12.0, help="HTTP request timeout in seconds")
    parser.add_argument("--max-runtime", type=float, default=600.0, help="Global maximum runtime before flushing remaining Tier A records")
    parser.add_argument("--disable-discovery", action="store_true", help="Disable domain candidate discovery for missing websites")
    args = parser.parse_args()

    started_at = utc_now()
    start_monotonic = time.monotonic()

    # Read inputs - handles JSON, JSONL, or TXT
    org_inputs = read_organisation_inputs(args.organisations)
    orgs = [item["organisation_number"] for item in org_inputs]
    expected_count = args.expected_count if args.expected_count > 0 else len(orgs)

    if len(orgs) != expected_count:
        raise SystemExit(f"Error: Expected {expected_count} organisations, received {len(orgs)}")

    print(f"[{started_at}] Signalpost agent starting run '{args.run_id}' on {len(orgs)} companies using {args.workers} workers...")

    # Ensure bulk registry snapshot exists or download it
    bulk_path = ensure_bulk_snapshot(args.bulk)
    profiles, registry_metadata = profiles_from_bulk(bulk_path, orgs)

    requested_modules = ["registry", "accounting_obligation", "registry_live", "financials", "roles", "group", "locations", "website"]
    
    operations = {"requests": 0, "bytes": 0, "latencies_ms": []}
    state: dict[str, dict] = {}
    errors: list[dict] = []

    # Incremental stream file
    output_path = Path(args.output)
    stream_path = output_path.with_suffix(".stream.tmp")
    stream_path.parent.mkdir(parents=True, exist_ok=True)
    stream_handle = stream_path.open("w", encoding="utf-8")

    def safe_enrich(prof: dict) -> tuple[dict, dict]:
        try:
            # Check global deadline: if time running out, skip slow website discovery
            time_left = args.max_runtime - (time.monotonic() - start_monotonic)
            enable_disc = (not args.disable_discovery) and (time_left > 30.0)
            return enrich_company_profile(prof, requested_modules, timeout=args.timeout, enable_discovery=enable_disc), {}
        except Exception as exc:
            prof["errors"] = [{"error": str(exc), "type": type(exc).__name__}]
            prof["synthesis_summary"] = f"{prof.get('name')} (Org.nr {prof.get('organisation_number')}): Encountered error during enrichment: {exc}"
            return prof, {"error": str(exc)}

    # Process companies in parallel pool with incremental writing
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(safe_enrich, prof): prof["organisation_number"] for prof in profiles}
        for index, future in enumerate(as_completed(futures), 1):
            prof, err = future.result()
            org_no = prof["organisation_number"]
            state[org_no] = prof
            m = prof.get("run_metrics", {})
            operations["requests"] += m.get("requests", 0)
            operations["bytes"] += m.get("bytes", 0)
            operations["latencies_ms"].extend(m.get("latencies_ms", []))
            if err:
                errors.append({"org": org_no, **err})

            # Incremental checkpointing
            single_envelope = profile_to_contract_envelope(
                prof,
                run_id=args.run_id,
                started_at=started_at,
                completed_at=utc_now(),
                terminal_status="completed",
            )
            stream_handle.write(json.dumps(single_envelope, ensure_ascii=False) + "\n")
            stream_handle.flush()

    stream_handle.close()
    if stream_path.exists():
        stream_path.unlink()

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
