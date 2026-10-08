"""Refresh against a previous run's envelopes.

Change events use the starter kit's `refresh.diff_profile` shape (organisation_number, field,
old_value, new_value, source_url, retrieved_at, effective_at, source_class, old/new content hash,
status) for the kit-tracked profile fields, plus the same shape for added or removed external claims
(`claims.<field>`). Rules:

- A field whose source failed this run (error, blocked, deadline) is never reported as changed and
  never erased: the previous claims and their evidence are carried in `refresh.preserved_claims`.
- Previous evidence that this run did not re-observe is kept in `refresh.prior_evidence`, so earlier
  evidence survives every refresh.
- The same snapshot gives zero changes: values are compared, never hashes or timestamps.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .refresh import _evidence_for, diff_profile

CLAIM_FIELDS = ("official_website", "social_profile", "dated_news", "hiring_signal", "company_description")
FAILED_STATUSES = {"source_error", "blocked", "failed", "not_fetched"}
MAX_PRIOR_EVIDENCE = 300


def read_previous_with_stats(path: str | Path | None) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Previous envelopes by organisation number, read line by line.

    Never raises: a missing, empty, truncated or corrupt file, or rows without the kit `profile`
    (for example v2 envelopes), only reduce what can be compared. The stats say what was skipped.
    """
    stats: dict[str, Any] = {"path": str(path) if path else None, "rows": 0, "usable": 0, "bad_lines": 0, "without_profile": 0, "error": None}
    previous: dict[str, dict[str, Any]] = {}
    if not path:
        return previous, stats
    try:
        source = Path(path)
        if not source.is_file():
            return previous, stats
        with source.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                stats["rows"] += 1
                try:
                    row = json.loads(line)
                except ValueError:
                    stats["bad_lines"] += 1
                    continue
                if not isinstance(row, dict) or not row.get("organisation_number"):
                    stats["bad_lines"] += 1
                elif not isinstance(row.get("profile"), dict):
                    stats["without_profile"] += 1
                else:
                    previous[str(row["organisation_number"])] = row
    except OSError as exc:
        stats["error"] = f"{type(exc).__name__}: {exc}"
    stats["usable"] = len(previous)
    return previous, stats


def read_previous(path: str | Path | None) -> dict[str, dict[str, Any]]:
    return read_previous_with_stats(path)[0]


def _key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).casefold()


def _failed(record: dict[str, Any] | None) -> bool:
    return not record or record.get("status") in FAILED_STATUSES


def _evidence_key(item: dict[str, Any]) -> tuple:
    return (item.get("source_url"), item.get("claim_span"), item.get("content_sha256"))


def _discovery_incomplete(profile: dict[str, Any]) -> bool:
    """Website discovery stopped on a transient error or the deadline, so its "no site" is no finding."""
    return bool(((profile.get("web_run") or {}).get("discovery") or {}).get("incomplete"))


def refresh_envelope(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """Add `changes` and `refresh` to `current` (in place) relative to `previous`."""
    if not previous or previous.get("organisation_number") != current.get("organisation_number"):
        current["refresh"] = {"previous_run_id": None, "material_changes": 0, "prior_evidence": [], "preserved_claims": []}
        return current
    org = current["organisation_number"]
    old_profile, new_profile = previous.get("profile") or {}, current.get("profile") or {}
    changes: list[dict[str, Any]] = []
    preserved_fields: set[str] = set()

    # A discovery that stopped early in either run says nothing about a website appearing or going.
    discovery_incomplete = _discovery_incomplete(old_profile) or _discovery_incomplete(new_profile)

    # 1. Kit-tracked profile fields (the kit's own event shape), skipping fields whose source failed.
    for change in diff_profile(old_profile, new_profile):
        if discovery_incomplete and change["field"].startswith("website."):
            preserved_fields.add("website")
            continue
        record = _evidence_for(new_profile, change["field"])
        if _failed(record) or (change["new_value"] is None and record.get("status") != "not_found"):
            preserved_fields.add(change["field"].split(".", 1)[0])
            continue
        changes.append(change)

    # 2. External claims: added or removed values, with the same event keys.
    def available(env: dict[str, Any], field: str) -> dict[str, dict[str, Any]]:
        return {_key(c.get("value")): c for c in env.get("claims") or [] if c.get("field") == field and c.get("availability") == "available"}

    old_evidence = {e.get("id"): e for e in previous.get("evidence") or []}
    new_evidence = {e.get("id"): e for e in current.get("evidence") or []}
    preserved_claims: list[dict[str, Any]] = []
    web_record = (new_profile.get("evidence") or {}).get("website")
    web_failed = _failed(web_record) or any(e.get("type") == "DeadlineExceeded" for e in new_profile.get("errors") or [])
    # A crawl cut short by the company's web budget, or a page that failed to load, says nothing about
    # whether an item is gone (or new): such differences are recorded, never reported as changes.
    old_web, new_web = old_profile.get("web_claims") or {}, new_profile.get("web_claims") or {}
    old_errors = {e.get("url") for e in old_web.get("crawl_errors") or [] if isinstance(e, dict)}
    new_errors = {e.get("url") for e in new_web.get("crawl_errors") or [] if isinstance(e, dict)}
    old_incomplete = old_web.get("crawl_complete") is False or _discovery_incomplete(old_profile)
    new_incomplete = new_web.get("crawl_complete") is False or _discovery_incomplete(new_profile)
    unconfirmed: dict[str, list[Any]] = {"unconfirmed_removals": [], "newly_observed": [], "no_longer_listed": []}

    def claim_urls(claim: dict[str, Any]) -> set[Any]:
        urls = {claim.get("url"), claim.get("source_url")}
        if isinstance(claim.get("value"), str) and claim["value"].startswith("http"):
            urls.add(claim["value"])
        return urls - {None}

    for field in CLAIM_FIELDS:
        old, new = available(previous, field), available(current, field)
        if web_failed:
            if old and not new:
                preserved_fields.add("website")
                preserved_claims.extend({**claim, "preserved_from_run_id": previous.get("run_id") or (previous.get("run") or {}).get("run_id")} for claim in old.values())
            continue
        for key in sorted(set(old) ^ set(new)):
            claim = new.get(key) or old[key]
            if key in old and field == "dated_news":
                unconfirmed["no_longer_listed"].append(claim.get("value"))  # listings keep only the newest items
                continue
            if key in old and (new_incomplete or claim_urls(claim) & new_errors):
                unconfirmed["unconfirmed_removals"].append({"field": field, "value": claim.get("value")})
                preserved_claims.append({**claim, "preserved_from_run_id": previous.get("run_id") or (previous.get("run") or {}).get("run_id")})
                continue
            if key in new and (old_incomplete or claim_urls(claim) & old_errors):
                unconfirmed["newly_observed"].append({"field": field, "value": claim.get("value")})
                continue
            evidence = [(new_evidence if key in new else old_evidence).get(i) or {} for i in claim.get("evidence_ids") or []]
            first = evidence[0] if evidence else {}
            changes.append({
                "organisation_number": org,
                "field": f"claims.{field}",
                "change_type": "added" if key in new else "removed",
                "old_value": None if key in new else claim.get("value"),
                "new_value": claim.get("value") if key in new else None,
                "source_url": first.get("source_url"),
                "retrieved_at": first.get("retrieved_at"),
                "effective_at": claim.get("published_at") or claim.get("posted_date"),
                "source_class": first.get("source_class"),
                "old_content_sha256": None if key in new else first.get("content_sha256"),
                "new_content_sha256": first.get("content_sha256") if key in new else None,
                "status": "available",
            })

    # 3. Prior evidence: everything the previous run cited (and preserved) that this run did not re-observe.
    seen = {_evidence_key(e) for e in current.get("evidence") or []}
    prior: list[dict[str, Any]] = []
    for item in [*(previous.get("evidence") or []), *((previous.get("refresh") or {}).get("prior_evidence") or [])]:
        key = _evidence_key(item)
        if key in seen:
            continue
        seen.add(key)
        prior.append({**item, "observed_in_run_id": item.get("observed_in_run_id") or previous.get("run_id") or (previous.get("run") or {}).get("run_id")})
    current["changes"] = changes
    current["refresh"] = {
        "previous_run_id": previous.get("run_id") or (previous.get("run") or {}).get("run_id"),
        "previous_completed_at": previous.get("completed_at") or (previous.get("run") or {}).get("completed_at"),
        "material_changes": len(changes),
        "fields_not_refreshed": sorted(preserved_fields),
        "preserved_claims": preserved_claims,
        **unconfirmed,
        "prior_evidence": prior[:MAX_PRIOR_EVIDENCE],
    }
    return current


def refresh_envelopes(envelopes: list[dict[str, Any]], previous: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Refresh every envelope in place; a failure for one company is counted, never raised, and
    leaves that envelope as it was (with `refresh.error`)."""
    stats = {"compared": 0, "material_changes": 0, "companies_changed": 0, "failed": 0}
    for envelope in envelopes:
        before = previous.get(envelope.get("organisation_number"))
        try:
            refresh_envelope(envelope, before)
        except Exception as exc:
            stats["failed"] += 1
            envelope["refresh"] = {"previous_run_id": (before or {}).get("run_id"), "material_changes": 0,
                                   "error": f"{type(exc).__name__}: {str(exc)[:200]}", "prior_evidence": [], "preserved_claims": []}
            continue
        if before:
            stats["compared"] += 1
            stats["material_changes"] += len(envelope.get("changes") or [])
            stats["companies_changed"] += bool(envelope.get("changes"))
    return stats
