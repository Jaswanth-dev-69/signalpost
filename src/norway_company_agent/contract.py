from __future__ import annotations

import hashlib
from typing import Any


def _evidence_id(source_url: str, field_name: str, index: int) -> str:
    raw = f"{source_url}:{field_name}:{index}"
    return "ev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def profile_to_contract_envelope(
    profile: dict[str, Any],
    *,
    run_id: str,
    started_at: str,
    completed_at: str,
    terminal_status: str = "completed",
    third_party_cost_usd: float = 0.0,
) -> dict[str, Any]:
    """Transform an enriched company profile into the official Signalpost output contract."""
    org = profile["organisation_number"]
    evidence_map: dict[str, dict[str, Any]] = {}
    evidence_id_by_key: dict[tuple[str, str], str] = {}
    claims: list[dict[str, Any]] = []

    records = profile.get("evidence", {})
    run_metrics = profile.get("run_metrics", {})
    total_requests = run_metrics.get("requests", 0)
    latencies = run_metrics.get("latencies_ms", [])
    runtime_ms = sum(latencies) if latencies else 0

    def add_evidence(
        source_url: str,
        source_class: str,
        retrieved_at: str,
        content_sha256: str | None = None,
        claim_span: str | None = None,
        key_hint: str = "",
    ) -> str:
        key = (source_url, key_hint)
        if key in evidence_id_by_key:
            return evidence_id_by_key[key]
        ev_id = _evidence_id(source_url, key_hint, len(evidence_map))
        evidence_id_by_key[key] = ev_id
        evidence_map[ev_id] = {
            "id": ev_id,
            "source_url": source_url,
            "source_class": source_class,
            "retrieved_at": retrieved_at,
            "content_sha256": content_sha256 or hashlib.sha256(source_url.encode()).hexdigest(),
            "claim_span": claim_span or "",
        }
        return ev_id

    def add_claim(
        field: str,
        value: Any,
        availability: str,
        confidence: float,
        ev_ids: list[str],
    ) -> None:
        claims.append({
            "field": field,
            "value": value,
            "availability": availability,
            "confidence": round(confidence, 3),
            "evidence_ids": ev_ids,
        })

    # 1. Registry identity claims
    reg_rec = records.get("registry_live", {}) or records.get("registry", {})
    reg_url = f"https://data.brreg.no/enhetsregisteret/api/enheter/{org}"
    reg_class = "official_registry_live" if "registry_live" in records else (reg_rec.get("source_class") or "official_registry_bulk")
    reg_time = reg_rec.get("retrieved_at") or started_at
    reg_hash = reg_rec.get("content_sha256")

    reg_ev_id = add_evidence(
        reg_url,
        reg_class,
        reg_time,
        content_sha256=reg_hash,
        claim_span=f"Legal entity {profile.get('name')} ({org})",
        key_hint="registry",
    )

    add_claim("legal_name", profile.get("name"), "available" if profile.get("name") else "not_available", 1.0, [reg_ev_id])
    add_claim("organisation_number", org, "available", 1.0, [reg_ev_id])
    add_claim("legal_form", profile.get("legal_form"), "available" if profile.get("legal_form") else "not_available", 1.0, [reg_ev_id])
    add_claim("municipality", profile.get("municipality"), "available" if profile.get("municipality") else "not_available", 1.0, [reg_ev_id])
    add_claim("industry_code", profile.get("industry_code"), "available" if profile.get("industry_code") else "not_available", 1.0, [reg_ev_id])
    add_claim("industry_label", profile.get("industry_label"), "available" if profile.get("industry_label") else "not_available", 1.0, [reg_ev_id])

    emp_val = profile.get("employees")
    add_claim("registry_employees", emp_val, "available" if emp_val is not None else "not_available", 1.0, [reg_ev_id])
    add_claim("status_bankrupt", bool(profile.get("bankrupt")), "available", 1.0, [reg_ev_id])
    add_claim("status_liquidating", bool(profile.get("liquidating")), "available", 1.0, [reg_ev_id])

    # 2. Accounting obligation
    acc_ob = records.get("accounting_obligation", {})
    if acc_ob:
        ob_ev_id = add_evidence(
            acc_ob.get("source_url") or reg_url,
            acc_ob.get("source_class") or "official_rule_interpretation",
            acc_ob.get("retrieved_at") or started_at,
            content_sha256=acc_ob.get("content_sha256"),
            claim_span=str(acc_ob.get("value") or {}),
            key_hint="accounting_obligation",
        )
        add_claim("accounting_obligation", acc_ob.get("value"), acc_ob.get("status", "available"), 1.0, [ob_ev_id])

    # 3. Annual Accounts / Financials
    fin_rec = records.get("financials", {})
    fin_status = fin_rec.get("status")
    if fin_status == "available" and fin_rec.get("value"):
        fin_url = fin_rec.get("source_url") or f"https://data.brreg.no/regnskapsregisteret/regnskap/{org}"
        fin_ev_id = add_evidence(
            fin_url,
            fin_rec.get("source_class") or "official_annual_accounts",
            fin_rec.get("retrieved_at") or started_at,
            content_sha256=fin_rec.get("content_sha256"),
            claim_span="Normalized annual accounts",
            key_hint="financials",
        )
        recs = (fin_rec.get("value") or {}).get("records") or []
        if recs:
            latest = recs[0]
            add_claim("revenue", latest.get("revenue"), "available" if latest.get("revenue") is not None else "not_available", 1.0, [fin_ev_id])
            add_claim("operating_result", latest.get("operating_result"), "available" if latest.get("operating_result") is not None else "not_available", 1.0, [fin_ev_id])
            add_claim("annual_result", latest.get("annual_result"), "available" if latest.get("annual_result") is not None else "not_available", 1.0, [fin_ev_id])
            add_claim("assets", latest.get("assets"), "available" if latest.get("assets") is not None else "not_available", 1.0, [fin_ev_id])
            add_claim("debt", latest.get("debt"), "available" if latest.get("debt") is not None else "not_available", 1.0, [fin_ev_id])
            add_claim("reporting_period", latest.get("period"), "available" if latest.get("period") is not None else "not_available", 1.0, [fin_ev_id])
        else:
            for f in ("revenue", "operating_result", "annual_result", "assets", "debt", "reporting_period"):
                add_claim(f, None, "not_available", 1.0, [fin_ev_id])
    else:
        st = "not_applicable" if acc_ob.get("value", {}).get("classification") == "not_required" else "not_available" if fin_status == "not_found" else "failed" if fin_status in ("source_error", "failed") else "not_available"
        for f in ("revenue", "operating_result", "annual_result", "assets", "debt", "reporting_period"):
            add_claim(f, None, st, 0.9, [reg_ev_id])

    # 4. Roles
    roles_rec = records.get("roles", {})
    roles_status = roles_rec.get("status")
    if roles_status == "available" and roles_rec.get("value"):
        roles_url = roles_rec.get("source_url") or f"https://data.brreg.no/enhetsregisteret/api/enheter/{org}/roller"
        roles_ev_id = add_evidence(
            roles_url,
            roles_rec.get("source_class") or "official_roles",
            roles_rec.get("retrieved_at") or started_at,
            content_sha256=roles_rec.get("content_sha256"),
            claim_span="Registered role holders",
            key_hint="roles",
        )
        role_items = (roles_rec.get("value") or {}).get("roles") or []
        active_roles = [r for r in role_items if not r.get("inactive")]
        add_claim("registered_roles", active_roles, "available" if active_roles else "not_available", 1.0, [roles_ev_id])
    else:
        add_claim("registered_roles", None, "not_available" if roles_status == "not_found" else "failed", 0.9, [reg_ev_id])

    # 5. Locations / Subunits
    loc_rec = records.get("locations", {})
    loc_status = loc_rec.get("status")
    if loc_status == "available" and loc_rec.get("value"):
        loc_url = loc_rec.get("source_url") or f"https://data.brreg.no/enhetsregisteret/api/underenheter?overordnetEnhet={org}"
        loc_ev_id = add_evidence(
            loc_url,
            loc_rec.get("source_class") or "official_subunits",
            loc_rec.get("retrieved_at") or started_at,
            content_sha256=loc_rec.get("content_sha256"),
            claim_span="Registered subunits",
            key_hint="locations",
        )
        subunits = (loc_rec.get("value") or {}).get("locations") or []
        add_claim("registered_subunits", subunits, "available" if subunits else "not_available", 1.0, [loc_ev_id])
    else:
        add_claim("registered_subunits", None, "not_available" if loc_status == "not_found" else "failed", 0.9, [reg_ev_id])

    # 6. Website & Social Links
    web_rec = records.get("website", {}) or records.get("website_discovered", {})
    web_status = web_rec.get("status")
    web_val = web_rec.get("value") or {}
    identity_assessment = web_val.get("identity_assessment") or {}
    publishable = identity_assessment.get("publishable", False)

    if web_status == "available" and publishable:
        web_url = web_rec.get("source_url") or web_val.get("final_url") or "https://example.no"
        web_ev_id = add_evidence(
            web_url,
            web_rec.get("source_class") or "company_owned",
            web_rec.get("retrieved_at") or started_at,
            content_sha256=web_rec.get("content_sha256"),
            claim_span=web_val.get("main_text_excerpt") or web_val.get("title"),
            key_hint="website",
        )
        add_claim("official_website", web_url, "available", 0.98, [web_ev_id])
        if web_val.get("description"):
            add_claim("company_description", web_val.get("description"), "available", 0.95, [web_ev_id])
        socials = web_val.get("social_links") or []
        add_claim("social_profiles", socials, "available" if socials else "not_available", 0.95, [web_ev_id])
    elif web_status == "available" and not publishable:
        web_url = web_rec.get("source_url") or "https://example.no"
        web_ev_id = add_evidence(
            web_url,
            web_rec.get("source_class") or "company_owned",
            web_rec.get("retrieved_at") or started_at,
            content_sha256=web_rec.get("content_sha256"),
            claim_span="Quarantined registry link - exact legal entity identity not established",
            key_hint="website_quarantined",
        )
        add_claim("official_website", None, "ambiguous", 0.3, [web_ev_id])
        add_claim("company_description", None, "ambiguous", 0.3, [web_ev_id])
        add_claim("social_profiles", None, "ambiguous", 0.3, [web_ev_id])
    elif web_status == "blocked":
        add_claim("official_website", None, "blocked", 0.0, [reg_ev_id])
        add_claim("company_description", None, "blocked", 0.0, [reg_ev_id])
        add_claim("social_profiles", None, "blocked", 0.0, [reg_ev_id])
    else:
        add_claim("official_website", None, "not_available", 0.0, [reg_ev_id])
        add_claim("company_description", None, "not_available", 0.0, [reg_ev_id])
        add_claim("social_profiles", None, "not_available", 0.0, [reg_ev_id])

    # 7. Summary Profile (Synthesis)
    summary_text = profile.get("synthesis_summary")
    if summary_text:
        sum_ev_ids = list(evidence_map.keys())
        add_claim("summary_profile", summary_text, "available", 0.95, sum_ev_ids)

    return {
        "organisation_number": org,
        "run": {
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "terminal_status": terminal_status,
        },
        "claims": claims,
        "evidence": list(evidence_map.values()),
        "changes": profile.get("change_history") or [],
        "errors": profile.get("errors") or [],
        "operations": {
            "requests": total_requests,
            "runtime_ms": runtime_ms,
            "third_party_cost_usd": third_party_cost_usd,
        },
    }
