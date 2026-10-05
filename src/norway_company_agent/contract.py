from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from typing import Any

from .batch import evidence_terminal_state
from .nav_jobs import company_orgnrs

BULK_URL = "https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv"
# The starter kit's module list; its envelope (run_id, state, modules, profile) is embedded as-is.
KIT_MODULES = ("registry", "accounting_obligation", "registry_live", "financials", "roles", "group", "locations", "website")
WEB_FIELDS = ("official_website", "company_description", "social_profile", "dated_news", "hiring_signal")
FINANCIAL_FIELDS = (
    ("revenue", "revenue", "sumDriftsinntekter"),
    ("operating_result", "operating_result", "driftsresultat"),
    ("annual_result", "annual_result", "aarsresultat"),
    ("assets", "assets", "sumEiendeler"),
    ("debt", "debt", "sumGjeld"),
)


def social_profile_value(url: str) -> str:
    """Canonical profile URL in the form Builderr matches (``facebook.com/handle``): https, no www,
    no trailing slash, handle lowercased. Handles are case-insensitive on these platforms; YouTube
    channel ids are not, so they keep their case."""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    if not (host.endswith("youtube.com") and path.lower().startswith("/channel/")):
        path = path.lower()
    return f"https://{host}{path}"


def news_value(title: str, stamp: str) -> str:
    """Dated news fact in Builderr's key form: "title (publication timestamp)"."""
    return f"{' '.join(str(title).split())} ({stamp})"


# Source policy: every claim records its extraction method. Evidence keys map to the method used.
EXTRACTION_METHODS = (
    ("registry_absent", "registry_lookup_not_found"),
    ("registry_", "registry_record_field"),
    ("financials", "annual_accounts_record"),
    ("roles", "roles_record"),
    ("locations", "subunits_record"),
    ("website_identity", "identity_page_text"),
    ("website_quarantined", "homepage_title"),
    ("website", "homepage_text"),
    ("description", "company_description_text"),
    ("social_", "html_link_href"),
    ("careers_page", "careers_page_heading"),
    ("news_checked", "news_page_text"),
    ("nav_sitemap", "nav_sitemap_index"),
)


def _extraction_method(key_hint: str) -> str:
    return next((method for prefix, method in EXTRACTION_METHODS if key_hint.startswith(prefix)), "page_text")


def _evidence_id(source_url: str, field_name: str, index: int) -> str:
    raw = f"{source_url}:{field_name}:{index}"
    return "ev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _span_value(value: Any) -> str:
    if value is None:
        return "(not registered)"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _period_text(period: Any) -> str:
    if isinstance(period, dict):
        return f"{period.get('fraDato') or '?'} - {period.get('tilDato') or '?'}"
    return _span_value(period)


def _word_bounded(text: str, start: int, end: int) -> str:
    """text[start:end] widened so it neither starts nor ends mid-word."""
    if start > 0 and not text[start - 1].isspace():
        start = text.rfind(" ", 0, start) + 1
    if end < len(text) and not text[end].isspace():
        stop = text.find(" ", end)
        end = stop if stop != -1 else len(text)
    return " ".join(text[start:end].split())


def _snippet(text: str, needle: str, width: int = 90) -> str | None:
    if not text or not needle:
        return None
    index = text.casefold().find(needle.casefold())
    if index < 0:
        return None
    return _word_bounded(text, max(0, index - width), index + len(needle) + width)


def _org_number_snippet(text: str, org: str) -> str | None:
    if not text or len(org) != 9:
        return None
    pattern = r"\s?".join(org[:3]) + r"\s?" + r"\s?".join(org[3:6]) + r"\s?" + r"\s?".join(org[6:])
    match = re.search(r"(?<!\d)" + pattern + r"(?!\d)", text)
    if not match:
        return None
    return _word_bounded(text, max(0, match.start() - 90), match.end() + 90)


def _live_registry_values(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("value") or {}
    address = value.get("business_address") or value.get("postal_address") or {}
    industry = value.get("industry") or {}
    return {
        "legal_name": value.get("name"),
        "legal_form": value.get("legal_form"),
        "municipality": address.get("kommune"),
        "industry_code": industry.get("kode"),
        "industry_label": industry.get("beskrivelse"),
        "registry_employees": value.get("employees"),
        "status_bankrupt": bool(value.get("bankrupt")),
        "status_liquidating": bool(value.get("liquidating")),
        "founded_date": value.get("founded_date"),
        "homepage": value.get("website") or None,
    }


def _bulk_registry_values(profile: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    raw = record.get("value") or {}
    return {
        "legal_name": profile.get("name"),
        "legal_form": profile.get("legal_form"),
        "municipality": profile.get("municipality"),
        "industry_code": profile.get("industry_code"),
        "industry_label": profile.get("industry_label"),
        "registry_employees": profile.get("employees"),
        "status_bankrupt": bool(profile.get("bankrupt")),
        "status_liquidating": bool(profile.get("liquidating")),
        "founded_date": (raw.get("stiftelsesdato") or None) if isinstance(raw, dict) else None,
        "homepage": profile.get("website") or None,
    }


LIVE_JSON_KEYS = {
    "legal_name": "navn",
    "legal_form": "kode",
    "municipality": "kommune",
    "industry_code": "kode",
    "industry_label": "beskrivelse",
    "registry_employees": "antallAnsatte",
    "status_bankrupt": "konkurs",
    "status_liquidating": "underAvvikling",
    "founded_date": "stiftelsesdato",
    "homepage": "hjemmeside",
}


def _csv_cell(value: Any) -> str:
    return '"' + str(value if value is not None else "").replace('"', '""') + '"'


def _bulk_span(raw: Any, column: str) -> str | None:
    """Two adjacent quoted cells of the bulk CSV row, exactly as the file writes them: the cell
    before the field and the field itself (for 'navn' that is the organisation number and name)."""
    if not isinstance(raw, dict) or column not in raw:
        return None
    keys = list(raw)
    index = keys.index(column)
    window = keys[index - 1:index + 1] if index > 0 else keys[:2]
    return ",".join(_csv_cell(raw[key]) for key in window)


def _role_holder_literal(role: dict[str, Any]) -> str | None:
    """One verbatim fragment of the roles API JSON naming the role holder."""
    if role.get("last_name") and role.get("first_name"):
        return f'"etternavn":{json.dumps(role["last_name"], ensure_ascii=False)},"fornavn":{json.dumps(role["first_name"], ensure_ascii=False)}'
    if role.get("organisation_number"):
        return f'"organisasjonsnummer":"{role["organisation_number"]}"'
    return None


def _role_literal(role: dict[str, Any]) -> str:
    """Literal fragments of the roles API JSON: role description plus the holder's name fields."""
    parts = [f'"beskrivelse":{json.dumps(role.get("role"), ensure_ascii=False)}'] if role.get("role") else []
    if role.get("first_name") or role.get("last_name"):
        if role.get("first_name"):
            parts.append(f'"fornavn":{json.dumps(role["first_name"], ensure_ascii=False)}')
        if role.get("last_name"):
            parts.append(f'"etternavn":{json.dumps(role["last_name"], ensure_ascii=False)}')
    elif role.get("name"):
        parts.append(f'"navn":{json.dumps(role["name"], ensure_ascii=False)}')
    return " | ".join(parts)


def _period_literal(period: Any) -> str:
    if isinstance(period, dict) and period.get("fraDato") and period.get("tilDato"):
        return f'"fraDato":"{period["fraDato"]}" | "tilDato":"{period["tilDato"]}"'
    return f"regnskapsperiode: {_period_text(period)}"


REGISTRY_KEYS = {
    "legal_name": "navn",
    "legal_form": "organisasjonsform.kode",
    "municipality": "forretningsadresse.kommune",
    "industry_code": "naeringskode1.kode",
    "industry_label": "naeringskode1.beskrivelse",
    "registry_employees": "antallAnsatte",
    "status_bankrupt": "konkurs",
    "status_liquidating": "underAvvikling",
    "founded_date": "stiftelsesdato",
    "homepage": "hjemmeside",
}


def profile_to_contract_envelope(
    profile: dict[str, Any],
    *,
    run_id: str,
    started_at: str,
    completed_at: str,
    terminal_status: str = "completed",  # OUTPUT_CONTRACT.md terminal value
    third_party_cost_usd: float = 0.0,
    modules: tuple[str, ...] | list[str] = KIT_MODULES,
) -> dict[str, Any]:
    """Transform an enriched company profile into the official Signalpost output contract.

    The envelope carries both shapes: the OUTPUT_CONTRACT.md claims/evidence lists and the starter
    kit's batch envelope (run_id, state, started_at, completed_at, modules, profile), whose profile
    holds the source records and snapshots the claims were built from.

    Every evidence item carries the sha256 of bytes that were actually fetched (or of the
    bulk snapshot file the row came from), the fetch time and a span quoting the value.
    Every contract field is emitted with an explicit availability state.
    """
    org = profile["organisation_number"]
    evidence_map: dict[str, dict[str, Any]] = {}
    evidence_id_by_key: dict[tuple[str, str], str] = {}
    claims: list[dict[str, Any]] = []
    errors = list(profile.get("errors") or [])
    deadline_hit = any(e.get("type") == "DeadlineExceeded" for e in errors)

    records = profile.get("evidence", {})
    run_metrics = profile.get("run_metrics", {})
    total_requests = run_metrics.get("requests", 0)
    latencies = run_metrics.get("latencies_ms", [])
    runtime_ms = sum(latencies) if latencies else 0

    def add_evidence(
        source_url: str | None,
        source_class: str,
        retrieved_at: str | None,
        content_sha256: str | None,
        claim_span: str | None,
        key_hint: str,
        method: str | None = None,
    ) -> str | None:
        # Evidence is only emitted for content that was really fetched: a real
        # sha256 of the bytes, the true fetch time and a non-empty supporting span.
        span = " ".join(str(claim_span or "").split())[:500]
        if not source_url or not retrieved_at or not _valid_hash(content_sha256) or not span:
            return None
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
            "content_sha256": content_sha256,
            "claim_span": span,
            "extraction_method": method or _extraction_method(key_hint),
        }
        return ev_id

    def evidence_from(record: dict[str, Any], span: str, key_hint: str, default_class: str) -> str | None:
        return add_evidence(
            record.get("source_url"),
            record.get("source_class") or record.get("source_type") or default_class,
            record.get("retrieved_at"),
            record.get("content_sha256"),
            span,
            key_hint,
        )

    def add_claim(field: str, value: Any, availability: str, confidence: float, ev_ids: list[str | None]) -> dict[str, Any]:
        ids = list(dict.fromkeys(e for e in ev_ids if e))
        if availability == "available" and not ids:
            # A value without fetched, hashed content behind it is not publishable.
            availability, value, confidence = "failed", None, 0.0
            errors.append({"field": field, "type": "EvidenceMissing", "error": "no fetched content hash for claim"})
        claim = {
            "field": field,
            "value": value if availability == "available" else None,
            "availability": availability,
            "confidence": round(confidence, 3),
            "evidence_ids": ids,
        }
        claims.append(claim)
        return claim

    def fetch_state(record: dict[str, Any] | None) -> str:
        status = (record or {}).get("status")
        if status == "not_found":
            return "not_available"
        if status == "blocked":
            return "blocked"
        return "failed"

    # 1. Official registry record (live API preferred, bulk snapshot row otherwise)
    live = records.get("registry_live") or {}
    bulk = records.get("registry") or {}
    live_ok = live.get("status") == "available" and _valid_hash(live.get("content_sha256"))
    bulk_ok = bulk.get("status") == "available" and _valid_hash(bulk.get("content_sha256"))
    if bulk_ok and bulk.get("source_type") == "official_registry_live":
        # Company absent from the bulk file; its registry record was resolved live.
        live, live_ok, bulk_ok = bulk, True, False
    live_values = _live_registry_values(live) if live_ok else {}
    bulk_values = _bulk_registry_values(profile, bulk) if bulk_ok else {}
    registry_ok = live_ok or bulk_ok
    profile_values = bulk_values or live_values

    def registry_evidence(field: str, value: Any) -> str | None:
        span = f"{org} {REGISTRY_KEYS.get(field, field)}: {_span_value(value)}"
        if live_ok and (not bulk_ok or live_values.get(field) == value):
            # Literal fragments of the API's compact JSON, so the quote can be found verbatim.
            # One verbatim fragment of the API's compact JSON (the URL carries the org number);
            # an unregistered field cannot be quoted, so the entity's own literal is cited.
            live_span = (
                f'"{LIVE_JSON_KEYS[field]}":{json.dumps(value, ensure_ascii=False)}'
                if value not in (None, "") and field in LIVE_JSON_KEYS
                else f'"organisasjonsnummer":"{org}"'
            )
            return evidence_from(live, live_span, f"registry_{field}", "official_registry_live")
        if bulk_ok:
            raw = bulk.get("value") or {}
            bulk_span = _bulk_span(raw, REGISTRY_KEYS.get(field, field)) or _bulk_span(raw, "navn") or span
            return evidence_from(bulk, bulk_span, f"registry_{field}", "official_registry_bulk")
        return None

    # Evidence that identifies the entity, reused for fields whose own source is unavailable.
    entity_ev = None
    if registry_ok:
        entity_ev = registry_evidence("legal_name", profile_values.get("legal_name"))
    absence_records = [r for r in (live, records.get("registry_underenhet") or {}, records.get("registry_bulk_absent") or {}) if r]
    absence_ev = None
    for record in absence_records:
        if record.get("status") == "not_found":
            note = record.get("note") or "not found"
            absence_ev = absence_ev or evidence_from(record, f"organisation number {org}: {note}", "registry_absent", "official_registry_live")
    entity_ev = entity_ev or absence_ev

    if registry_ok:
        add_claim("organisation_number", org, "available", 1.0, [registry_evidence("legal_name", profile_values.get("legal_name"))])
        for field in ("legal_name", "legal_form", "municipality", "industry_code", "industry_label", "registry_employees", "founded_date"):
            value = profile_values.get(field)
            ev = registry_evidence(field, value)
            add_claim(field, value, "available" if value not in (None, "") else "not_available", 1.0, [ev])
        for field in ("status_bankrupt", "status_liquidating"):
            value = profile_values.get(field)
            add_claim(field, value, "available", 1.0, [registry_evidence(field, value)])
    else:
        # Not in the bulk snapshot and the live registry did not return an entity.
        reg_state = "not_available" if absence_ev and live.get("status") == "not_found" else "failed"
        if reg_state == "failed":
            errors.append({"field": "registry", "type": "RegistryUnavailable", "error": live.get("note") or "live registry lookup failed"})
        add_claim("organisation_number", org, "available" if absence_ev else "failed", 1.0 if absence_ev else 0.0, [absence_ev])
        for field in ("legal_name", "legal_form", "municipality", "industry_code", "industry_label", "registry_employees", "founded_date", "status_bankrupt", "status_liquidating"):
            add_claim(field, None, reg_state, 0.9, [absence_ev])

    # 2. Accounting obligation (rule interpretation over the registry record)
    acc_ob = records.get("accounting_obligation") or {}
    acc_value = acc_ob.get("value") or {}
    if registry_ok and acc_ob:
        form_ev = registry_evidence("legal_form", profile_values.get("legal_form"))
        filing_ev = None
        if bulk_ok and acc_value.get("latest_submitted_accounts"):
            filing_span = _bulk_span(bulk.get("value"), "sisteInnsendteAarsregnskap") or f"{org} sisteInnsendteAarsregnskap: {acc_value.get('latest_submitted_accounts')}"
            filing_ev = evidence_from(bulk, filing_span, "registry_latest_accounts", "official_registry_bulk")
        add_claim("accounting_obligation", acc_value, acc_ob.get("status", "available") if acc_ob.get("status") != "not_found" else "not_available", 1.0, [filing_ev, form_ev])
    else:
        add_claim("accounting_obligation", None, "failed" if not absence_ev or live.get("status") != "not_found" else "not_available", 0.5, [entity_ev])

    # 3. Annual accounts
    fin_rec = records.get("financials") or {}
    fin_status = fin_rec.get("status")
    fin_records = (fin_rec.get("value") or {}).get("records") or [] if fin_status == "available" else []
    if fin_status == "available" and fin_records:
        latest = fin_records[0]
        period = latest.get("period")
        # Each span is one verbatim fragment of the API's compact JSON: the period object, and
        # for every figure its own key and value; a claim cites both.
        period_span = f'"regnskapsperiode":{json.dumps(period, ensure_ascii=False, separators=(",", ":"))}' if isinstance(period, dict) else _period_literal(period)
        period_ev = evidence_from(fin_rec, period_span, "financials_period", "official_annual_accounts")
        if period_ev and isinstance(period, dict):
            evidence_map[period_ev]["effective_at"] = period.get("tilDato")
        for field, key, label in FINANCIAL_FIELDS:
            value = latest.get(key)
            ev = evidence_from(fin_rec, f'"{label}":{value:.2f}', f"financials_{field}", "official_annual_accounts") if isinstance(value, (int, float)) else None
            if ev and isinstance(period, dict):
                evidence_map[ev]["effective_at"] = period.get("tilDato")
            claim = add_claim(field, value, "available" if value is not None else "not_available", 1.0, [ev, period_ev])
            claim["reporting_period"] = period
        add_claim("reporting_period", period, "available" if period is not None else "not_available", 1.0, [period_ev])
    else:
        if fin_status == "available":
            state, ev = "not_available", evidence_from(fin_rec, "[]", "financials_empty", "official_annual_accounts")
        elif fin_status == "not_found":
            state, ev = "not_available", evidence_from(fin_rec, f"regnskap {org}: {fin_rec.get('note') or 'HTTP 404'} (no annual accounts registered)", "financials_absent", "official_annual_accounts")
        else:
            state, ev = fetch_state(fin_rec if fin_rec else None), entity_ev
        if state == "not_available" and acc_value.get("classification") == "not_required":
            state = "not_applicable"
        for field in ("revenue", "operating_result", "annual_result", "assets", "debt", "reporting_period"):
            add_claim(field, None, state, 0.9, [ev or entity_ev])

    # 4. Roles
    roles_rec = records.get("roles") or {}
    if roles_rec.get("status") == "available":
        role_items = (roles_rec.get("value") or {}).get("roles") or []
        active_roles = [r for r in role_items if not r.get("inactive")]
        span = next((lit for lit in (_role_holder_literal(r) for r in active_roles) if lit), None) or '"rollegrupper":[]'
        ev = evidence_from(roles_rec, span, "roles", "official_roles")
        add_claim("registered_roles", active_roles, "available" if active_roles else "not_available", 1.0, [ev])
    elif roles_rec.get("status") == "not_found":
        ev = evidence_from(roles_rec, f"roller {org}: {roles_rec.get('note') or 'HTTP 404'}", "roles_absent", "official_roles")
        add_claim("registered_roles", None, "not_available", 0.9, [ev or entity_ev])
    else:
        add_claim("registered_roles", None, fetch_state(roles_rec or None), 0.0, [entity_ev])

    # 5. Locations / subunits
    loc_rec = records.get("locations") or {}
    if loc_rec.get("status") == "available":
        subunits = (loc_rec.get("value") or {}).get("locations") or []
        span = f'"organisasjonsnummer":"{subunits[0].get("organisation_number")}"' if subunits else '"totalElements":0'
        ev = evidence_from(loc_rec, span, "locations", "official_subunits")
        add_claim("registered_subunits", subunits, "available" if subunits else "not_available", 1.0, [ev])
    elif loc_rec.get("status") == "not_found":
        ev = evidence_from(loc_rec, f"underenheter overordnetEnhet={org}: {loc_rec.get('note') or 'HTTP 404'}", "locations_absent", "official_subunits")
        add_claim("registered_subunits", None, "not_available", 0.9, [ev or entity_ev])
    else:
        add_claim("registered_subunits", None, fetch_state(loc_rec or None), 0.0, [entity_ev])

    # 6. Company-owned web layer
    _web_claims(profile, records, add_evidence, add_claim, registry_evidence if registry_ok else None, entity_ev, deadline_hit)

    # 7. Summary profile (synthesis)
    summary_text = profile.get("synthesis_summary")
    if summary_text:
        add_claim("summary_profile", summary_text, "available", 0.95, list(evidence_map.keys()))

    module_states = {}
    for module in modules:
        record = records.get(module)
        state = evidence_terminal_state(record)
        if not record:
            state = "budget_exhausted" if deadline_hit else "submission_error"
        module_states[module] = {
            "state": state,
            "retry_count": int((record or {}).get("retry_count") or 0),
            "final_timestamp": (record or {}).get("retrieved_at") or completed_at,
        }
    entity_state = "submission_error" if any(item["state"] == "submission_error" for item in module_states.values()) else "complete"

    # Builderr's sample-site `external.handles`: "approved" handles there are exactly the social links
    # of a verified company site. Ours are the same gated links; nothing here is read from the
    # platforms themselves, so there is no `linkedin` block and nothing is "experimental".
    web_value = (records.get("website") or {}).get("value") or {}
    handles = [
        {"platform": item["platform"], "url": item["url"], "rightsStatus": "approved",
         "source_url": item.get("found_on_page") or web_value.get("final_url")}
        for item in (web_value.get("social_links") or [])
        if (web_value.get("identity_assessment") or {}).get("publishable") and (records.get("website") or {}).get("status") == "available"
    ]

    return {
        "organisation_number": org,
        "run_id": run_id,
        "state": entity_state,
        "started_at": started_at,
        "completed_at": completed_at,
        "modules": module_states,
        "run": {
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "terminal_status": terminal_status,
        },
        "claims": claims,
        "evidence": list(evidence_map.values()),
        "changes": profile.get("change_history") or [],
        "errors": errors,
        "operations": {
            "requests": total_requests,
            "runtime_ms": runtime_ms,
            "third_party_cost_usd": third_party_cost_usd,
        },
        "external": {"handles": handles},
        "profile": profile,
    }

BOILERPLATE = re.compile(r"cookie|informasjonskapsl|javascript|personvern|privacy|logg inn|log in|handlekurv|nettleser|browser", re.I)
ABOUT_PATH = re.compile(r"om-oss|om_oss|omoss|about|selskapet|firma", re.I)


def _first_paragraph(text: str, min_chars: int = 80, max_chars: int = 600) -> str | None:
    for paragraph in re.split(r"\n\s*\n|\n", text or ""):
        paragraph = " ".join(paragraph.split())
        if len(paragraph) < min_chars or BOILERPLATE.search(paragraph) or paragraph.count(" ") < 8:
            continue
        if len(paragraph) <= max_chars:
            return paragraph
        cut = paragraph[:max_chars]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        return cut[: end + 1] if end >= min_chars else cut.rsplit(" ", 1)[0]
    return None


def _company_description(web_val: dict[str, Any], web_url: str) -> tuple[str | None, str | None]:
    """Company-authored description: meta/og description, JSON-LD Organization description,
    then the first substantive paragraph of the about page or the homepage."""
    meta = " ".join(str(web_val.get("description") or "").split())
    if len(meta) >= 20:
        return meta, web_url
    for org in web_val.get("structured_organisations") or []:
        text = " ".join(str(org.get("description") or "").split()) if isinstance(org, dict) else ""
        if len(text) >= 40 and not BOILERPLATE.search(text):
            return text[:600], web_url
    pages = web_val.get("pages") or []
    for page in pages[1:]:
        if ABOUT_PATH.search(str(page.get("url") or "")):
            text = _first_paragraph(page.get("main_text_excerpt") or "")
            if text:
                return text, page.get("url")
    text = _first_paragraph(web_val.get("main_text_excerpt") or "")
    if text:
        return text, web_url
    return None, None


def _web_claims(profile, records, add_evidence, add_claim, registry_evidence, entity_ev, deadline_hit) -> None:
    org = profile["organisation_number"]
    web_rec = records.get("website") or {}
    web_status = web_rec.get("status")
    web_val = web_rec.get("value") or {}
    publishable = (web_val.get("identity_assessment") or {}).get("publishable", False)
    # The registry 'hjemmeside' value (or its absence) is the evidence for non-available web states.
    hjemmeside_ev = registry_evidence("homepage", profile.get("website") or None) if registry_evidence else None

    # Hiring from NAV's public vacancy feed: exact employer organisation-number matches.
    nav = profile.get("nav_jobs") or {}
    nav_postings = []
    for item in nav.get("postings") or []:
        page = item.get("page_evidence") or {}
        if page:
            ev = add_evidence(page.get("url"), "official_job_register", page.get("retrieved_at"), page.get("content_sha256"), page.get("claim_span"), f"nav_{item['uuid']}", "nav_ad_page_title")
            org_ev = add_evidence(page.get("url"), "official_job_register", page.get("retrieved_at"), page.get("content_sha256"), page.get("orgnr_span"), f"nav_org_{item['uuid']}", "nav_ad_page_employer_orgnr")
        else:
            ev = add_evidence(item.get("entry_url"), "official_job_register", item.get("entry_retrieved_at"), item.get("entry_sha256"), item.get("entry_title_span"), f"nav_{item['uuid']}", "nav_ad_json_title")
            org_ev = add_evidence(item.get("entry_url"), "official_job_register", item.get("entry_retrieved_at"), item.get("entry_sha256"), item.get("entry_span"), f"nav_org_{item['uuid']}", "nav_ad_json_employer_orgnr")
        if ev:
            nav_postings.append((item["url"], [ev, org_ev], {
                "kind": "job_posting",
                "title": item["title"],
                "posted_date": item.get("published"),
                "valid_through": item.get("expires"),
                "platform": "arbeidsplassen.nav.no",
                "employer_orgnr": item["employer_orgnr"],
                "source_url": page.get("url") or item.get("entry_url"),
                "verification_method": "nav_employer_orgnr",
            }))
    sitemap = nav.get("sitemap") or {}
    nav_checked_ev = None
    if nav.get("index_complete") and sitemap:
        nav_checked_ev = add_evidence(
            sitemap.get("url"), "official_job_register", sitemap.get("retrieved_at"), sitemap.get("content_sha256"),
            f"{sitemap.get('active_ads')} active ads listed; employer organisation numbers checked: {', '.join(sorted(company_orgnrs(profile))[:5])}",
            "nav_sitemap",
        )

    base_add_claim = add_claim

    def add_hiring(careers: tuple | None, site_postings: list, fallback_state: str, fallback_confidence: float, fallback_evs: list, site_method: str | None, scale: float) -> None:
        """One hiring_signal claim per fact: the careers page itself, then each posting."""
        emitted: set[str] = set()
        if careers:
            url, evs, attrs = careers
            claim = base_add_claim("hiring_signal", url, "available", round(0.9 * scale, 3), evs)
            claim.update({**attrs, "verification_method": site_method})
            emitted.add(url.rstrip("/").casefold())
        site_confidence = round(0.9 * scale, 3)
        for url, evs, attrs in [*site_postings, *nav_postings]:
            key = url.rstrip("/").casefold()
            if key in emitted:
                continue
            emitted.add(key)
            nav_item = attrs.get("platform") == "arbeidsplassen.nav.no"
            claim = base_add_claim("hiring_signal", url, "available", 0.95 if nav_item else site_confidence, evs)
            claim.update(attrs if nav_item else {**attrs, "verification_method": site_method})
        if not emitted:
            states_with_check = fallback_evs + ([nav_checked_ev] if nav_checked_ev and fallback_state == "not_available" else [])
            claim = base_add_claim("hiring_signal", None, fallback_state, fallback_confidence, states_with_check)
            if site_method:
                claim["verification_method"] = site_method

    method = (web_val.get("identity_assessment") or {}).get("method")
    declared = method == "registry_declared_domain"
    if declared and not hjemmeside_ev:
        publishable = False  # the registry declaration itself must be evidenced
    if web_status == "available" and publishable:
        # Registry-declared domains (no on-page entity proof) carry lower confidence.
        scale = 0.8 if declared else 1.0
        verification = "registry_declared_domain" if declared else "on_page_entity_match"

        def add_claim(field, value, availability, confidence, ev_ids):  # noqa: F811
            claim = base_add_claim(field, value, availability, round(confidence * scale, 3), ev_ids)
            claim["verification_method"] = verification
            return claim

        web_url = web_val.get("final_url") or web_rec.get("source_url")
        pages = {p.get("url"): p for p in web_val.get("pages") or [] if p.get("url")}
        home_hash = web_val.get("content_sha256") or web_rec.get("content_sha256")
        home_time = web_rec.get("retrieved_at")
        # Quote one contiguous field (never text joined across title/description/body).
        fields = [str(web_val.get(k) or "") for k in ("title", "description", "main_text_excerpt")]
        name_core = re.sub(r"\s+(AS|ASA|ANS|DA|ENK|SA|NUF)$", "", str(profile.get("name") or "").strip(), flags=re.I)
        span = (
            next((snip for snip in (_org_number_snippet(f, org) for f in fields) if snip), None)
            or next((snip for snip in (_snippet(f, name_core, 60) for f in fields) if snip), None)
            or web_val.get("title")
            or web_url
        )
        web_ev = add_evidence(web_url, "company_owned", home_time, home_hash, span, "website")
        # The identity proof may sit on a subpage (e.g. /kontakt with the org number).
        proof_page = web_val.get("identity_proof_page") or {}
        proof_ev = add_evidence(proof_page.get("url"), "company_owned", proof_page.get("retrieved_at"), proof_page.get("content_sha256"), proof_page.get("claim_span"), "website_identity") if proof_page else None
        add_claim("official_website", web_url, "available", 0.98, [hjemmeside_ev, web_ev] if declared else [web_ev, proof_ev])

        desc, desc_page = _company_description(web_val, web_url)
        if desc:
            page_ref = pages.get(desc_page) or {}
            desc_hash = page_ref.get("content_sha256") or (home_hash if desc_page == web_url else None)
            desc_time = page_ref.get("retrieved_at") or (home_time if desc_page == web_url else None)
            add_claim("company_description", desc, "available", 0.95 if desc_page == web_url else 0.9, [add_evidence(desc_page, "company_owned", desc_time, desc_hash, desc[:400], "description")])
        else:
            add_claim("company_description", None, "not_available", 0.6, [web_ev])

        # Social profiles: one claim per profile, linked from a page of the verified site.
        web_claims = profile.get("web_claims") or {}
        socials = (web_claims.get("social") or {}).get("profiles") or web_val.get("social_links") or []
        social_seen: set[str] = set()
        for item in socials:
            value = social_profile_value(item["url"])
            if value in social_seen:
                continue
            page = pages.get(item.get("found_on_page")) or {}
            source = item.get("found_on_page") or web_url
            page_hash = page.get("content_sha256") or (home_hash if source == web_url else None)
            page_time = page.get("retrieved_at") or (home_time if source == web_url else None)
            ev = add_evidence(source, "company_owned", page_time, page_hash, f"{item.get('href') or item['url']}", f"social_{value}")
            if ev:
                social_seen.add(value)
                add_claim("social_profile", value, "available", 0.95, [ev]).update({"platform": item["platform"], "source_url": source})
        if not social_seen:
            add_claim("social_profile", None, "not_available", 0.6, [web_ev])

        # Dated news: one claim per article, keyed "title (publication timestamp)".
        news = web_claims.get("news") or {}
        news_count = 0
        news_seen: set[str] = set()
        for item in (news.get("items") or [])[:10]:
            stamp = item.get("published_at") or item.get("published_date")
            value = news_value(item["title"], stamp)
            if value in news_seen:
                # Two pages with the same title and timestamp give one fact, not duplicate records.
                continue
            source, method = item.get("source_page"), item.get("extraction_method") or "news_page_text"
            ev = add_evidence(source, "company_owned", item.get("retrieved_at"), item.get("content_sha256"), item.get("claim_span"), f"news_{item.get('url')}", method)
            date_ev = add_evidence(source, "company_owned", item.get("retrieved_at"), item.get("content_sha256"), item.get("date_span"), f"news_date_{item.get('url')}", method) if item.get("date_span") else None
            if ev:
                news_seen.add(value)
                claim = add_claim("dated_news", value, "available", 0.9, [ev, date_ev])
                claim.update({"title": item["title"], "published_at": stamp, "url": item.get("url"), "date_source": item.get("date_source"), "source_url": item.get("source_page")})
                news_count += 1
        if not news_count:
            checked = [add_evidence(p.get("url"), "company_owned", p.get("retrieved_at"), p.get("content_sha256"), p.get("claim_span"), "news_checked") for p in news.get("checked_pages") or []]
            add_claim("dated_news", None, "failed" if deadline_hit else "not_available", 0.6, [*checked[:3], web_ev])

        # Hiring signal: the careers page on the verified site, then each posting found there or on NAV.
        jobs = web_claims.get("jobs") or {}
        site_postings = []
        for item in (jobs.get("postings") or [])[:25]:
            ev = add_evidence(item.get("source_page"), "company_owned", item.get("retrieved_at"), item.get("content_sha256"), item.get("claim_span"), f"job_{item.get('url')}", item.get("extraction_method") or "job_posting_text")
            if ev:
                attrs = {k: item.get(k) for k in ("title", "posted_date", "valid_through", "platform") if item.get(k)}
                site_postings.append((item["url"], [ev], {"kind": "job_posting", **attrs, "source_url": item.get("source_page")}))
        careers = jobs.get("careers_page") if isinstance(jobs.get("careers_page"), dict) else {}
        careers_ev = add_evidence(careers.get("url"), "company_owned", careers.get("retrieved_at"), careers.get("content_sha256"), careers.get("claim_span"), "careers_page") if careers else None
        careers_fact = (careers["url"], [careers_ev], {"kind": "careers_page", "source_url": careers["url"], "openings_listed": not careers.get("explicit_no_openings")}) if careers_ev else None
        add_hiring(careers_fact, site_postings, "failed" if deadline_hit else "not_available", round(0.6 * scale, 3), [web_ev], verification, scale)
        return

    if web_status == "available":
        # Website fetched but the strict entity gate did not pass: publish nothing from it.
        web_url = web_val.get("final_url") or web_rec.get("source_url")
        span = web_val.get("title") or web_url
        ev = add_evidence(web_url, "company_owned", web_rec.get("retrieved_at"), web_val.get("content_sha256") or web_rec.get("content_sha256"), f"{span} (exact legal entity not established)", "website_quarantined")
        state, evs = "ambiguous", [ev, hjemmeside_ev]
    elif deadline_hit and not web_status:
        state, evs = "failed", [hjemmeside_ev or entity_ev]
    elif web_status == "blocked":
        state, evs = "blocked", [hjemmeside_ev or entity_ev]
    elif web_status in ("source_error", "failed"):
        state, evs = "failed", [hjemmeside_ev or entity_ev]
    else:
        state, evs = "not_available", [hjemmeside_ev or entity_ev]
    for field in WEB_FIELDS:
        if field == "hiring_signal":
            add_hiring(None, [], state, 0.3 if state == "ambiguous" else 0.0, evs, None, 1.0)
            continue
        add_claim(field, None, state, 0.3 if state == "ambiguous" else 0.0, evs)
