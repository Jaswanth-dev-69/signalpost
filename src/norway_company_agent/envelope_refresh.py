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


def read_previous(path: str | Path | None) -> dict[str, dict[str, Any]]:
    """Previous envelopes by organisation number; unreadable or kit-less files give nothing."""
    if not path or not Path(path).exists():
        return {}
    previous: dict[str, dict[str, Any]] = {}
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict) and row.get("organisation_number") and isinstance(row.get("profile"), dict):
                    previous[row["organisation_number"]] = row
    except (OSError, ValueError):
        return {}
    return previous


def _key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).casefold()


def _failed(record: dict[str, Any] | None) -> bool:
    return not record or record.get("status") in FAILED_STATUSES


def _evidence_key(item: dict[str, Any]) -> tuple:
    return (item.get("source_url"), item.get("claim_span"), item.get("content_sha256"))


def refresh_envelope(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """Add `changes` and `refresh` to `current` (in place) relative to `previous`."""
    if not previous or previous.get("organisation_number") != current.get("organisation_number"):
        current["refresh"] = {"previous_run_id": None, "material_changes": 0, "prior_evidence": [], "preserved_claims": []}
        return current
    org = current["organisation_number"]
    old_profile, new_profile = previous.get("profile") or {}, current.get("profile") or {}
    changes: list[dict[str, Any]] = []
    preserved_fields: set[str] = set()

    # 1. Kit-tracked profile fields (the kit's own event shape), skipping fields whose source failed.
    for change in diff_profile(old_profile, new_profile):
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
    for field in CLAIM_FIELDS:
        old, new = available(previous, field), available(current, field)
        if web_failed:
            if old and not new:
                preserved_fields.add("website")
                preserved_claims.extend({**claim, "preserved_from_run_id": previous.get("run_id") or (previous.get("run") or {}).get("run_id")} for claim in old.values())
            continue
        for key in sorted(set(old) ^ set(new)):
            claim = new.get(key) or old[key]
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
        "prior_evidence": prior[:MAX_PRIOR_EVIDENCE],
    }
    return current


def refresh_envelopes(envelopes: list[dict[str, Any]], previous: dict[str, dict[str, Any]]) -> dict[str, int]:
    stats = {"compared": 0, "material_changes": 0, "companies_changed": 0}
    for envelope in envelopes:
        before = previous.get(envelope.get("organisation_number"))
        refresh_envelope(envelope, before)
        if before:
            stats["compared"] += 1
            stats["material_changes"] += len(envelope["changes"])
            stats["companies_changed"] += bool(envelope["changes"])
    return stats
