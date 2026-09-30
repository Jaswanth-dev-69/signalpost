from __future__ import annotations

from typing import Any


def generate_company_synthesis(profile: dict[str, Any]) -> str:
    """Generate a concise, evidence-grounded profile summary for a Norwegian company.
    
    This function uses deterministic facts from verified evidence layers and explicitly
    highlights what is known, what is unknown, and what changed.
    """
    name = profile.get("name") or "Unknown Entity"
    org = profile.get("organisation_number") or ""
    form = profile.get("legal_form") or "Entity"
    muni = profile.get("municipality") or "Norway"
    ind = profile.get("industry_label") or "Unspecified sector"
    emp = profile.get("employees")

    # Header sentence
    parts = [f"{name} (Org.nr {org}) is a registered Norwegian {form} based in {muni}, operating within {ind}."]

    # Status / Employees
    if profile.get("bankrupt"):
        parts.append("The company is registered as bankrupt.")
    elif profile.get("liquidating"):
        parts.append("The company is currently in liquidation.")

    if emp is not None:
        parts.append(f"The official registry records {emp} employee(s).")
    else:
        parts.append("The registry record does not report employee count.")

    # Financials
    evidence = profile.get("evidence", {})
    fin = evidence.get("financials", {})
    fin_status = fin.get("status")
    acc_ob = evidence.get("accounting_obligation", {}).get("value", {})
    classification = acc_ob.get("classification")

    if fin_status == "available" and fin.get("value"):
        recs = (fin.get("value") or {}).get("records") or []
        if recs:
            latest = recs[0]
            rev = latest.get("revenue")
            res = latest.get("annual_result")
            cur = latest.get("currency") or "NOK"
            period = latest.get("period") or {}
            year = period.get("tilDato", "")[:4] if isinstance(period, dict) else ""
            year_str = f" for FY{year}" if year else ""

            fin_str = f"For the latest filed annual accounts{year_str}, the company reported "
            items = []
            if rev is not None:
                items.append(f"revenue of {rev:,.0f} {cur}")
            if res is not None:
                items.append(f"annual result of {res:,.0f} {cur}")
            if items:
                fin_str += ", ".join(items) + "."
                parts.append(fin_str)
            else:
                parts.append("Annual accounts were returned but numerical breakdown was omitted.")
        else:
            parts.append("Financial records endpoint returned an empty record set.")
    elif classification == "required_by_legal_form":
        parts.append("Financial filings are required by legal form but no normalized annual account was returned in this check.")
    elif classification == "threshold_or_activity_dependent":
        parts.append("Filing obligation is activity/threshold dependent; no public annual account was returned.")
    else:
        parts.append("No normalized annual accounts record was returned; missing filing is not interpreted as zero revenue.")

    # Roles & Locations
    roles = (evidence.get("roles", {}).get("value") or {}).get("roles") or []
    active_roles = [r for r in roles if not r.get("inactive")]
    if active_roles:
        key_people = [f"{r.get('name')} ({r.get('role') or r.get('group')})" for r in active_roles[:3] if r.get("name")]
        if key_people:
            parts.append(f"Key registered role holders include: {', '.join(key_people)}.")

    subunits = (evidence.get("locations", {}).get("value") or {}).get("locations") or []
    if len(subunits) > 1:
        parts.append(f"The company operates {len(subunits)} registered subunits/establishments.")
    elif len(subunits) == 1:
        parts.append("The company has 1 registered subunit.")

    # Website & Public Footprint
    web = evidence.get("website", {}) or evidence.get("website_discovered", {})
    web_status = web.get("status")
    web_val = web.get("value") or {}
    publishable = (web_val.get("identity_assessment") or {}).get("publishable", False)

    if web_status == "available" and publishable:
        final_url = web_val.get("final_url") or web.get("source_url")
        desc = web_val.get("description")
        parts.append(f"Official verified website: {final_url}.")
        if desc:
            parts.append(f"Site overview: \"{desc[:200]}\"")
        socials = web_val.get("social_links") or []
        if socials:
            platforms = sorted({s.get("platform") for s in socials if s.get("platform")})
            parts.append(f"Declared social profiles: {', '.join(platforms)}.")
    elif web_status == "available" and not publishable:
        parts.append("A registry-linked website was checked, but exact legal-entity identity could not be verified; website claims are quarantined.")
    else:
        parts.append("No verified official company website was available during this check.")

    # Summary of Unknowns
    unknowns = []
    if fin_status != "available":
        unknowns.append("annual financial metrics")
    if not active_roles:
        unknowns.append("public leadership registry entries")
    if not (web_status == "available" and publishable):
        unknowns.append("verified online web presence")

    if unknowns:
        parts.append(f"Currently unconfirmed or unavailable: {', '.join(unknowns)}.")

    return " ".join(parts)
