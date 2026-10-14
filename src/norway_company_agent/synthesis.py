from __future__ import annotations

import re
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


# ---------------------------------------------------------------------------------------------
# Envelope summary: built only from the envelope's own published claims.
#
# Every sentence below is assembled from claims with `availability: available` (their values and
# their evidence items) or, for the unknowns, from the explicit availability state of a claim.
# Nothing is inferred beyond arithmetic on published figures (changes between reported years).
# Markers like [2] point at the numbered source list; each source carries the evidence ids it
# stands for, so a reader can go from a sentence to the quoted span and the fetched page.
# ---------------------------------------------------------------------------------------------

LEGAL_FORMS = {
    "AS": "private limited company",
    "ASA": "public limited company",
    "ENK": "sole proprietorship",
    "NUF": "Norwegian-registered foreign enterprise",
    "ANS": "general partnership",
    "DA": "partnership with shared liability",
    "KS": "limited partnership",
    "SA": "cooperative",
    "BA": "company with limited liability",
    "STI": "foundation",
    "FLI": "association",
    "SPA": "savings bank",
    "GFS": "mutual insurance company",
    "BRL": "housing cooperative",
    "ESEK": "condominium owners' association",
    "IKS": "inter-municipal company",
    "KF": "municipal enterprise",
    "FKF": "county municipal enterprise",
    "HF": "health trust",
    "SF": "state enterprise",
    "PK": "pension fund",
    "SAM": "co-ownership",
    "KBO": "bankruptcy estate",
    "TVAM": "entity under compulsory dissolution",
    "PRE": "partnership company",
    "KOMM": "municipality",
    "FYLK": "county authority",
    "STAT": "state body",
    "ORGL": "organisational unit",
}
SOURCE_LABELS = {
    "official_registry_live": "Enhetsregisteret entity record (Brønnøysund Register Centre)",
    "official_registry_bulk": "Enhetsregisteret bulk register snapshot",
    "official_roles": "Enhetsregisteret roles record",
    "official_subunits": "Enhetsregisteret sub-unit records",
    "official_annual_accounts": "Regnskapsregisteret annual accounts",
    "official_job_register": "NAV public vacancy register",
    "company_owned": "company-owned website",
}
PLATFORM_NAMES = {"facebook": "Facebook", "instagram": "Instagram", "linkedin": "LinkedIn", "youtube": "YouTube",
                  "x": "X (Twitter)", "twitter": "X (Twitter)", "tiktok": "TikTok", "pinterest": "Pinterest",
                  "vimeo": "Vimeo", "github": "GitHub", "snapchat": "Snapchat", "threads": "Threads"}
CHANGE_NAMES = {"registry.name": "legal name", "registry.legal_form": "legal form", "registry.employees": "employee count",
                "registry.municipality": "municipality", "registry.website": "registered homepage",
                "registry.latest_submitted_accounts": "latest filed accounts year", "financials.records": "annual accounts",
                "financial_history.years": "filed accounts years", "roles.roles": "registered roles", "locations.locations": "sub-units",
                "website.title": "website title", "website.description": "website description", "website.social_links": "website social links",
                "claims.official_website": "official website", "claims.social_profile": "social profiles", "claims.dated_news": "dated news",
                "claims.hiring_signal": "hiring signals", "claims.company_description": "website description"}
MAX_QUOTE = 240
SUMMARY_FIELD = "summary_profile"


def _quote(text: Any, limit: int = MAX_QUOTE) -> str:
    text = " ".join(str(text or "").split())
    if len(text) > limit:
        cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.")
        text = cut + " …"
    return f"“{text}”"


def _place(name: Any) -> str:
    """BRREG prints municipalities in capitals ("NORD-FRON"); show them as names ("Nord-Fron")."""
    words = re.split(r"([ \-])", str(name or ""))
    return "".join(w if w in (" ", "-") else (w[:1].upper() + w[1:].lower()) for w in words)


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None and str(value).strip() not in ("", "None") else None
    except (TypeError, ValueError):
        return None


def _money(value: float, currency: str | None = "NOK") -> str:
    cur = currency or "NOK"
    size = abs(value)
    if size >= 1e9:
        text = f"{value / 1e9:.2f} billion"
    elif size >= 1e6:
        text = f"{value / 1e6:.1f} million"
    elif size >= 1e4:
        text = f"{value / 1e3:,.0f} thousand"
    else:
        text = f"{value:,.0f}"
    return f"{cur} {text}"


def _period_label(period: Any) -> str:
    if not isinstance(period, dict):
        return "the latest reported period"
    start, end = str(period.get("fraDato") or ""), str(period.get("tilDato") or "")
    if start[5:] == "01-01" and end[5:] == "12-31" and start[:4] == end[:4]:
        return end[:4]
    return f"{start} to {end}" if start and end else (end or "the latest reported period")


def _change(old: float, new: float, currency: str | None, noun: str, old_label: str, new_label: str, result: bool = False) -> str:
    """One sentence on how a published figure moved between two reported years."""
    span = f"from {_money(old, currency)} in {old_label} to {_money(new, currency)} in {new_label}"
    if old == new:
        return f"{noun} was unchanged at {_money(new, currency)} in {old_label} and {new_label}"
    if old > 0 and new > 0:
        pct = (new - old) / old * 100
        if abs(pct) < 0.5:
            return f"{noun} was essentially unchanged ({span})"
        return f"{noun} {'rose' if new > old else 'fell'} {abs(pct):.0f}% {span}"
    if result and old < 0 and new < 0:
        return f"{noun} was a loss in both years; the loss {'narrowed' if new > old else 'widened'} {span}"
    if result and old < 0 <= new:
        return f"{noun} turned from a loss to a profit ({span})"
    if result and new < 0 <= old:
        return f"{noun} turned from a profit to a loss ({span})"
    return f"{noun} moved {span}"


def _name(value: Any) -> str:
    """Role holders that are entities carry their name as a list of lines in the roles API."""
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value if v)
    return str(value or "")


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


class _Sources:
    """Numbered source list keyed by page URL; a marker names every source a sentence rests on."""

    def __init__(self, evidence: dict[str, dict[str, Any]]):
        self.evidence = evidence
        self.items: list[dict[str, Any]] = []
        self.by_url: dict[str, dict[str, Any]] = {}

    def cite(self, claims: list[dict[str, Any]] | dict[str, Any] | None) -> tuple[str, list[int], list[str]]:
        claims = [claims] if isinstance(claims, dict) else (claims or [])
        refs: list[int] = []
        ids: list[str] = []
        for claim in claims:
            for eid in claim.get("evidence_ids") or []:
                item = self.evidence.get(eid)
                if not item or not item.get("source_url"):
                    continue
                url = item["source_url"]
                source = self.by_url.get(url)
                if source is None:
                    source = {"n": len(self.items) + 1, "url": url,
                              "label": SOURCE_LABELS.get(item.get("source_class"), item.get("source_class") or "source"),
                              "source_class": item.get("source_class"), "retrieved_at": item.get("retrieved_at"),
                              "evidence_ids": []}
                    self.items.append(source)
                    self.by_url[url] = source
                if eid not in source["evidence_ids"]:
                    source["evidence_ids"].append(eid)
                if source["n"] not in refs:
                    refs.append(source["n"])
                if eid not in ids:
                    ids.append(eid)
        refs.sort()
        marker = f" [{', '.join(str(n) for n in refs)}]" if refs else ""
        return marker, refs, ids


def envelope_summary(envelope: dict[str, Any]) -> dict[str, Any]:
    """Summary sections, text and numbered sources for one envelope, from its published claims."""
    org = envelope.get("organisation_number") or ""
    claims = [c for c in envelope.get("claims") or [] if c.get("field") != SUMMARY_FIELD]
    evidence = {e.get("id"): e for e in envelope.get("evidence") or []}
    by_field: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        by_field.setdefault(str(claim.get("field")), []).append(claim)

    def first(field: str) -> dict[str, Any] | None:
        items = by_field.get(field) or []
        return items[0] if items else None

    def available(field: str) -> list[dict[str, Any]]:
        return [c for c in by_field.get(field) or [] if c.get("availability") == "available"]

    def value(field: str) -> Any:
        items = available(field)
        return items[0].get("value") if items else None

    def state(field: str) -> str | None:
        claim = first(field)
        return claim.get("availability") if claim else None

    sources = _Sources(evidence)
    sections: list[dict[str, Any]] = []

    def section(key: str, label: str, sentences: list[tuple[str, Any]]) -> None:
        texts, refs, ids = [], [], []
        for sentence, cited in sentences:
            if not sentence:
                continue
            marker, s_refs, s_ids = sources.cite(cited)
            texts.append(sentence.rstrip(".") + marker + ".")
            refs.extend(r for r in s_refs if r not in refs)
            ids.extend(i for i in s_ids if i not in ids)
        if texts:
            sections.append({"key": key, "label": label, "text": " ".join(texts), "refs": sorted(refs), "evidence_ids": ids})

    name = value("legal_name") or (envelope.get("profile") or {}).get("name") or f"Organisation {org}"
    unknowns: list[str] = []

    # 1. Identity: who the entity is, from the register.
    form = value("legal_form")
    form_text = f"a {LEGAL_FORMS[form]} ({form})" if form in LEGAL_FORMS else (f"an entity of legal form {form}" if form else "a registered entity")
    muni = value("municipality")
    founded = value("founded_date")
    identity = f"{name} (organisation number {org}) is {form_text}"
    identity += f" registered in {_place(muni)}" if muni else ""
    identity += f", founded on {founded}" if founded else ""
    identity_claims = [c for c in (first("organisation_number"), *(available("legal_form")), *(available("municipality")), *(available("founded_date"))) if c]
    status_sentences: list[tuple[str, Any]] = []
    if value("status_bankrupt") is True:
        status_sentences.append(("The register lists it as bankrupt (konkurs)", available("status_bankrupt")))
    if value("status_liquidating") is True:
        status_sentences.append(("The register lists it as being wound up (under avvikling)", available("status_liquidating")))
    section("identity", "Company", [(identity, identity_claims), *status_sentences])

    # 2. What it does: the register's industry and activity text, and the verified site's own words.
    does: list[tuple[str, Any]] = []
    code, label = value("industry_code"), value("industry_label")
    if code and str(code).startswith("00"):
        does.append((f"Its industry is not specified in the register (code {code} {_quote(label, 60)})", available("industry_code") + available("industry_label")))
    elif label:
        does.append((f"Its registered industry is {code + ' ' if code else ''}{_quote(label, 160)}", available("industry_code") + available("industry_label")))
    activity = value("registered_activity")
    if activity:
        does.append((f"Its registered business activity reads {_quote(activity)}", available("registered_activity")))
    description = value("company_description")
    if description:
        does.append((f"Its verified website describes it as {_quote(description)}", available("company_description")))
    if not activity and not description:
        unknowns.append("what the company does beyond its industry code (no registered activity text or verified website description)")
    section("activity", "What it does", does)

    # 3. Size and finances: register headcount and the latest filed accounts.
    money: list[tuple[str, Any]] = []
    employees = _number(value("registry_employees"))
    if employees is not None:
        money.append((f"The register reports {employees:,.0f} employee{'s' if employees != 1 else ''}", available("registry_employees")))
    else:
        unknowns.append("employee count (not reported to the register)")
    fin_fields = ("revenue", "operating_result", "annual_result", "assets", "debt")
    latest = {f: _number(value(f)) for f in fin_fields}
    period_claim = (available("reporting_period") or [None])[0]
    period = period_claim.get("value") if period_claim else None
    currency = None
    history = sorted((c for c in available("financial_history") if isinstance(c.get("value"), dict)),
                     key=lambda c: str(((c["value"].get("period") or {}).get("tilDato")) or ""), reverse=True)
    if history:
        currency = history[0]["value"].get("currency")
    if any(v is not None for v in latest.values()):
        latest_label = _period_label(period)
        parts = []
        if latest["revenue"] is not None:
            parts.append(f"revenue of {_money(latest['revenue'], currency)}")
        if latest["operating_result"] is not None:
            parts.append(f"an operating result of {_money(latest['operating_result'], currency)}")
        if latest["annual_result"] is not None:
            parts.append(f"an annual result of {_money(latest['annual_result'], currency)}")
        tail = []
        if latest["assets"] is not None:
            tail.append(f"total assets of {_money(latest['assets'], currency)}")
        if latest["debt"] is not None:
            tail.append(f"debt of {_money(latest['debt'], currency)}")
        sentence = f"Its latest filed annual accounts ({latest_label}) report {_join(parts)}" if parts else f"Its latest filed annual accounts ({latest_label})"
        if tail:
            sentence += f", with {_join(tail)}"
        money.append((sentence, [c for f in fin_fields for c in available(f)] + ([period_claim] if period_claim else [])))
    else:
        fin_state = state("revenue")
        obligation = value("accounting_obligation") or {}
        if fin_state == "not_applicable":
            unknowns.append("annual accounts (this legal form is not required to file them)")
        elif fin_state in ("failed", "blocked"):
            unknowns.append("annual accounts (the accounts register could not be read in this run)")
        else:
            reason = obligation.get("reason") if isinstance(obligation, dict) else None
            unknowns.append("annual accounts (none returned by Regnskapsregisteret" + (f"; {reason.rstrip('.')}" if reason else "") + "); missing figures are not zero")
    section("finances", "Size and finances", money)

    # 4. What changed: movements between reported years, role updates, dated activity, refresh.
    changed: list[tuple[str, Any]] = []
    if history and any(v is not None for v in latest.values()):
        prev = history[0]["value"]
        prev_label, new_label = _period_label(prev.get("period")), _period_label(period)
        cited = [history[0]] + ([period_claim] if period_claim else [])
        moves = []
        for field, noun in (("revenue", "Revenue"), ("annual_result", "the annual result")):
            old, new = _number(prev.get(field)), latest[field]
            if old is not None and new is not None:
                moves.append((_change(old, new, currency, noun, prev_label, new_label, result=field == "annual_result"), cited + available(field)))
        for text, cite in moves:
            changed.append((text[:1].upper() + text[1:], cite))
        if len(history) > 1:
            oldest = history[-1]["value"]
            old, new = _number(oldest.get("revenue")), latest["revenue"]
            if old is not None and new is not None and old > 0 and new > 0:
                pct = (new - old) / old * 100
                trend = "was essentially unchanged overall" if abs(pct) < 0.5 else f"{'grew' if new > old else 'declined'} {abs(pct):.0f}% in total"
                changed.append((f"Across the {len(history) + 1} reported years since {_period_label(oldest.get('period'))}, revenue {trend}",
                                [history[-1]] + available("revenue")))
    roles = [r for r in (value("registered_roles") or []) if isinstance(r, dict) and not r.get("inactive")]
    dated_groups: dict[str, str] = {}
    for role in roles:
        stamp = str(role.get("last_changed") or "")[:10]
        group = role.get("group") or role.get("role")
        if stamp and group and stamp > dated_groups.get(group, ""):
            dated_groups[group] = stamp
    if dated_groups:
        updates = []
        for group, stamp in sorted(dated_groups.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[:2]:
            current = [_name(r["name"]) for r in roles if (r.get("group") or r.get("role")) == group and r.get("name")]
            updates.append(f"{group} on {stamp}" + (f" (now {_join(current[:3])}{' and others' if len(current) > 3 else ''})" if current else ""))
        changed.append((f"The latest role updates in the register are {_join(updates)}", available("registered_roles")))
    former = [item for item in value("former_names") or [] if isinstance(item, dict) and item.get("name")]
    if former:
        until = str(former[0].get("until") or "")[:10]
        changed.append((f"It was previously registered under the name {former[0].get('name')}" + (f" (until {until})" if until else ""), available("former_names")))
    news = sorted((c for c in available("dated_news") if c.get("published_at")), key=lambda c: str(c.get("published_at")), reverse=True)
    if news:
        top = news[0]
        changed.append((f"The latest dated item on its website is {_quote(top.get('title') or top.get('value'), 140)} ({str(top.get('published_at'))[:10]})", [top]))
    refresh = envelope.get("refresh") or {}
    changes = envelope.get("changes") or []
    if refresh.get("previous_run_id"):
        when = str(refresh.get("previous_completed_at") or "")[:10]
        since = f"the previous run{' on ' + when if when else ''}"
        if changes:
            fields = sorted({CHANGE_NAMES.get(str(c.get("field")), str(c.get("field") or "").replace("claims.", "").replace("_", " ")) for c in changes})
            examples = []
            for change in changes:
                kind = change.get("change_type") or ("removed" if change.get("new_value") is None else "added" if change.get("old_value") is None else "changed")
                shown = change.get("new_value") if change.get("new_value") is not None else change.get("old_value")
                if isinstance(shown, str) and len(examples) < 3:
                    examples.append(f"{kind} {CHANGE_NAMES.get(str(change.get('field')), 'item')} {_quote(shown, 80)}")
            changed.append((f"Compared with {since}, {len(changes)} material change{'s were' if len(changes) != 1 else ' was'} found ({_join(fields[:6])})"
                            + (f", for example {_join(examples)}" if examples else "") + "; each is listed with its source under changes", None))
        else:
            changed.append((f"No material change was found compared with {since}", None))
    else:
        changed.append(("This is the first Signalpost snapshot of this company, so there is no earlier run to compare with", None))
    section("changes", "What changed", changed)

    # 5. Leadership and locations from the register.
    people: list[tuple[str, Any]] = []
    if roles:
        def role_holders(code: str) -> list[str]:
            return [_name(r["name"]) for r in roles if r.get("role_code") == code and r.get("name")]
        named = []
        ceo, chair = role_holders("DAGL"), role_holders("LEDE")
        if ceo and ceo[:1] == chair[:1] and len(ceo) == 1:
            named.append(f"{ceo[0]} is both chief executive (daglig leder) and chair of the board (styrets leder)")
        else:
            if ceo:
                named.append(f"chief executive (daglig leder) {_join(ceo[:2])}")
            if chair:
                named.append(f"chair of the board (styrets leder) {_join(chair[:2])}")
        board = role_holders("MEDL")
        if board:
            named.append(f"{len(board)} board member{'s' if len(board) != 1 else ''}")
        if not named:
            named.append(_join([f"{r.get('role') or r.get('group')} {_name(r.get('name'))}" for r in roles[:3] if r.get("name")]))
        people.append((f"The register lists {len(roles)} active role record{'s' if len(roles) != 1 else ''}: {_join(named)}", available("registered_roles")))
    elif state("registered_roles") == "available" or state("registered_roles") == "not_available":
        unknowns.append("leadership (no active role holders are registered)")
    else:
        unknowns.append("leadership (the roles register could not be read in this run)")
    subunits = value("registered_subunits") or []
    if subunits:
        places = []
        for unit in subunits:
            place = _place(((unit.get("address") or {}) if isinstance(unit, dict) else {}).get("kommune") or "")
            if place and place not in places:
                places.append(place)
        where = f" in {_join(places[:4])}" + (f" and {len(places) - 4} other municipalities" if len(places) > 4 else "") if places else ""
        people.append((f"It has {len(subunits)} registered sub-unit{'s' if len(subunits) != 1 else ''} (establishment{'s' if len(subunits) != 1 else ''}){where}", available("registered_subunits")))
    section("people", "Leadership and locations", people)

    # 6. Online presence: identity-gated website and the profiles that site links to.
    online: list[tuple[str, Any]] = []
    site = value("official_website")
    if site:
        online.append((f"Its website {site} was verified as this exact legal entity", available("official_website")))
        socials = available("social_profile")
        platforms = sorted({PLATFORM_NAMES.get(str(c.get("platform") or "").lower(), str(c.get("platform") or "other")) for c in socials})
        if socials:
            online.append((f"That site links to {len(socials)} company profile{'s' if len(socials) != 1 else ''} on {_join(platforms)}", socials))
        else:
            unknowns.append("social media profiles (the verified website links to none)")
    else:
        web_state = state("official_website")
        if web_state == "ambiguous":
            unknowns.append("the official website (a candidate site was found but could not be confirmed as this exact legal entity, so nothing from it is published)")
        elif web_state in ("blocked", "failed"):
            unknowns.append(f"the official website (the site could not be read in this run: {web_state})")
        else:
            unknowns.append("an official website (none is registered or could be verified)")
    section("online", "Online presence", online)

    # 7. Hiring: careers pages and individual postings (company site or NAV's register).
    hiring: list[tuple[str, Any]] = []
    signals = available("hiring_signal")
    pages = [c for c in signals if c.get("kind") == "careers_page"]
    postings = [c for c in signals if c.get("kind") == "job_posting"]
    if pages:
        listed = [c for c in pages if c.get("openings_listed")]
        hiring.append((f"Its careers page {pages[0].get('value')}" + (" lists open positions" if listed else " was found"), pages[:1]))
    if postings:
        dated = sorted(postings, key=lambda c: str(c.get("posted_date") or ""), reverse=True)
        top = dated[0]
        stamp = str(top.get("posted_date") or "")[:10]
        where = "NAV's vacancy register" if top.get("platform") == "arbeidsplassen.nav.no" else "its website"
        hiring.append((f"{len(postings)} job posting{'s were' if len(postings) != 1 else ' was'} found, most recently {_quote(top.get('title') or top.get('value'), 100)}" + (f" (posted {stamp})" if stamp else "") + f" on {where}", dated[:3]))
    if not signals:
        unknowns.append("hiring (no careers page or job posting was found on the checked pages or in NAV's vacancy register; this does not show that it is not hiring)")
    section("hiring", "Hiring", hiring)

    # 8. Dated public activity on the company's own site.
    activity_sentences: list[tuple[str, Any]] = []
    if news:
        stamps = [str(c.get("published_at"))[:10] for c in news]
        span_text = f" dated {stamps[-1]} to {stamps[0]}" if stamps[-1] != stamps[0] else f" dated {stamps[0]}"
        activity_sentences.append((f"Its website has {len(news)} dated news item{'s' if len(news) != 1 else ''}{span_text}", news[:1] + news[-1:]))
        if len(news) > 1:
            headlines = "; ".join(f"{_quote(c.get('title') or c.get('value'), 90)} ({str(c.get('published_at'))[:10]})" for c in news[1:3])
            activity_sentences.append((f"Earlier items include {headlines}", news[1:3]))
    elif site:
        unknowns.append("dated news (none found on the checked pages of its website)")
    section("activity_log", "Recent activity", activity_sentences)

    # 9. What is not known, stated as such.
    unknowns.append("reputation and sentiment (Signalpost does not read review sites, the press or LinkedIn)")
    sections.append({"key": "unknowns", "label": "Not known or not established", "text": "; ".join(u[:1].upper() + u[1:] if i == 0 else u for i, u in enumerate(unknowns)) + ".", "refs": [], "evidence_ids": []})

    lines = [f"{s['label']}: {s['text']}" for s in sections]
    if sources.items:
        lines.append("Sources: " + "; ".join(f"[{s['n']}] {s['label']}, {s['url']}" for s in sources.items) + ".")
    cited_ids = [eid for s in sources.items for eid in s["evidence_ids"]]
    return {"text": "\n".join(lines), "sections": sections, "sources": sources.items, "evidence_ids": cited_ids}


def apply_envelope_summary(envelope: dict[str, Any]) -> dict[str, Any]:
    """Replace the envelope's summary with one built from its published claims (in place).

    The summary claim moves to the front of `claims` and is mirrored in a top-level `summary` and in
    `profile.synthesis_summary`. Nothing else in the envelope changes. On any error the envelope keeps
    the summary it had, so a summary problem can never cost an envelope."""
    try:
        summary = envelope_summary(envelope)
    except Exception as exc:  # the profile-level summary stays in place
        envelope.setdefault("errors", []).append({"field": SUMMARY_FIELD, "type": "SummaryError", "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
        return envelope
    if not summary["evidence_ids"]:
        return envelope
    claims = [c for c in envelope.get("claims") or [] if c.get("field") != SUMMARY_FIELD]
    # Like every earlier version, the summary claim cites the envelope's whole evidence list (so every
    # item stays cited by a claim); `sources` and each section name the items a sentence rests on.
    every_id = [e.get("id") for e in envelope.get("evidence") or [] if e.get("id")]
    claim = {"field": SUMMARY_FIELD, "value": summary["text"], "availability": "available", "confidence": 0.95,
             "evidence_ids": every_id, "sections": summary["sections"], "sources": summary["sources"],
             "method": "template_over_published_claims"}
    envelope["claims"] = [claim, *claims]
    if isinstance(envelope.get("profile"), dict):
        envelope["profile"]["synthesis_summary"] = summary["text"]
    ordered = {"organisation_number": envelope.get("organisation_number"),
               "summary": {"text": summary["text"], "sections": [{k: s[k] for k in ("key", "label", "text", "refs")} for s in summary["sections"]],
                           "sources": [{k: s[k] for k in ("n", "label", "url")} for s in summary["sources"]]}}
    rest = {k: v for k, v in envelope.items() if k not in ordered}
    envelope.clear()
    envelope.update({**ordered, **rest})
    return envelope
