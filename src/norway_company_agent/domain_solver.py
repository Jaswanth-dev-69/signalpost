from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

from .identity import DECLARED_DOMAIN_REJECT, _structured_names, _tokens, apply_website_identity_gate, own_org_number_printed, publishable_social_links
from .website import fetch_website

FREEMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.no", "outlook.com", "outlook.no", "live.no", "live.com",
    "msn.com", "yahoo.com", "yahoo.no", "icloud.com", "me.com", "mac.com", "online.no", "frisurf.no", "lyse.net",
    "getmail.no", "broadpark.no", "c2i.net", "start.no", "epost.no", "mail.com", "protonmail.com", "proton.me",
    "altibox.no", "telenor.no", "netcom.no", "chello.no", "bluezone.no", "tele2.no", "ebnett.no", "haugnett.no",
    "enivest.net", "tussa.com", "nordfjordnett.no", "neasonline.no", "kvinnherad.net", "sensewave.com", "ymail.com",
    "aol.com", "gmx.com", "gmx.net", "hotmail.se", "hotmail.co.uk", "yahoo.co.uk", "email.com", "post.com",
}
LEGAL_SUFFIXES = {"as", "asa", "ans", "da", "enk", "sa", "nuf", "ba", "bbl", "ks", "sf", "iks"}
# Words dropped for an extra "brand core" variant (e.g. "HANSEN BRØDRENE EIENDOM AS" -> hansenbrodrene.no).
GENERIC_WORDS = {
    "eiendom", "eiendommer", "eiendomsselskap", "holding", "holdings", "drift", "driftsselskap", "invest",
    "investering", "investment", "investments", "gruppen", "group", "norge", "norway", "og", "and", "co",
    "company", "consulting", "konsern",
}
# Entity types that rarely run their own website; their generic names also carry more risk.
SKIP_DISCOVERY_FORMS = {"ESEK", "BRL", "SAM", "BBL", "KIRK", "PERS", "TVAM", "FYLK", "KOMM", "STAT", "ORGL"}
MAX_NAME_CANDIDATES = 10


def _slug_tokens(company_name: str) -> list[str]:
    text = company_name.translate(str.maketrans({"ø": "o", "Ø": "O", "å": "aa", "Å": "AA", "æ": "ae", "Æ": "AE"}))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return [t for t in re.findall(r"[a-z0-9]+", text) if t not in LEGAL_SUFFIXES]


def _stems(tokens: list[str]) -> list[str]:
    stems: list[str] = []
    if not tokens:
        return stems
    joined = "".join(tokens)
    if len(joined) >= 4:
        stems.append(joined)
    if len(tokens) >= 2:
        stems.append("-".join(tokens))
    without_og = [t for t in tokens if t not in {"og", "and"}]
    if without_og != tokens and len("".join(without_og)) >= 4:
        stems.append("".join(without_og))
        if len(without_og) >= 2:
            stems.append("-".join(without_og))
    return stems


def generate_candidate_domains(company_name: str, extra_names: list[str] | None = None) -> list[str]:
    """Candidate homepages: legal name joined/hyphenated, without "og", without generic words,
    aa->a variants and sub-unit trade names; .no before .com."""
    tokens = _slug_tokens(company_name)
    if not tokens:
        return []
    stems = _stems(tokens)
    core = [t for t in tokens if t not in GENERIC_WORDS]
    # A one-word core needs at least 7 characters to be a distinctive brand (avoids "hansen.no").
    if core and core != tokens and (len(core) >= 2 or len(core[0]) >= 7):
        stems.extend(_stems(core))
    for name in extra_names or []:
        extra = [t for t in _slug_tokens(name) if t not in {"avd", "avdeling", "filial"}]
        if extra and extra != tokens and len("".join(extra)) >= 5:
            stems.append("".join(extra))
    for stem in list(stems):
        if "aa" in stem:
            stems.append(stem.replace("aa", "a"))
    stems = list(dict.fromkeys(stems))
    candidates = [f"{stem}.no" for stem in stems] + [f"{stem}.com" for stem in stems[:2]]
    return [f"https://www.{c}" for c in dict.fromkeys(candidates)][:MAX_NAME_CANDIDATES]


def subunit_names(profile: dict[str, Any], limit: int = 2) -> list[str]:
    locations = (((profile.get("evidence") or {}).get("locations") or {}).get("value") or {}).get("locations") or []
    names: list[str] = []
    for item in locations:
        name = str(item.get("name") or "").strip()
        if name and name.casefold() != str(profile.get("name") or "").casefold() and name not in names:
            names.append(name)
    return names[:limit]


def email_domain(profile: dict[str, Any]) -> str | None:
    record = (profile.get("evidence") or {}).get("registry") or {}
    value = record.get("value") or {}
    email = str(value.get("epostadresse") or value.get("email") or profile.get("email") or "").strip().casefold()
    if "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].strip(". ")
    domain = domain.removeprefix("www.")
    if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain) or domain in FREEMAIL_DOMAINS or domain in DECLARED_DOMAIN_REJECT:
        return None
    return domain


def _site_texts(value: dict[str, Any]) -> tuple[str, str]:
    """(homepage self-identification without hostname or body text, all captured page text).

    Body text is excluded from the name proof: group sites list sister companies there
    (e.g. arbor.no lists "Arbor AS Arbor-Eiendom AS Jarel AS").
    """
    identity = " ".join([
        *(str(value.get(k) or "") for k in ("title", "description")),
        *_structured_names(value.get("structured_organisations") or []),
    ])
    pages = " ".join(
        " ".join(str(page.get(k) or "") for k in ("title", "main_text_excerpt", "identity_text_excerpt"))
        for page in value.get("pages") or []
    )
    return identity, identity + " " + pages


def strict_discovered_proof(profile: dict[str, Any], value: dict[str, Any]) -> tuple[bool, str]:
    """Discovered (non-registry) domains need exact proof; the hostname itself never counts."""
    org = str(profile.get("organisation_number") or "")
    if re.search(r"wp-login|/login|/logg-inn|/signin", str(value.get("final_url") or ""), re.I):
        return False, "site resolves to a login wall"
    site_orgs = value.get("org_numbers_on_site") or []
    if any(other != org for other in site_orgs):
        return False, "site prints a different organisation number"
    identity_text, all_text = _site_texts(value)
    all_text = identity_text + " " + str(value.get("main_text_excerpt") or "") + " " + all_text
    exact = re.compile(r"(?<!\d)" + r"\s?".join([org[:3], org[3:6], org[6:]]) + r"(?!\d)") if len(org) == 9 else None
    if org in site_orgs or (exact and exact.search(all_text)):
        return True, "exact organisation number on homepage or contact/about/privacy page"
    if own_org_number_printed(profile, value):
        return True, "exact organisation number printed on the site (footer, structured data or identity page), no other organisation number"
    core = _tokens(profile.get("name"))
    muni = set(_tokens(profile.get("municipality") or ""))
    page_tokens = set(_tokens(identity_text))
    all_tokens = set(_tokens(all_text))
    if len(core) >= 2 and set(core) <= page_tokens and muni and muni <= all_tokens:
        conflict = name_homonym_conflict(profile, page_tokens, all_tokens)
        if conflict:
            return False, conflict
        return True, "full legal name on homepage and registered municipality on site"
    return False, "no organisation number and no legal name plus municipality"


BRREG_NAME_SEARCH = "https://data.brreg.no/enhetsregisteret/api/enheter?navn={query}&size=100"


def name_homonym_conflict(profile: dict[str, Any], page_tokens: set[str], all_tokens: set[str], fetcher: Any = None) -> str | None:
    """A legal name plus municipality only identifies the company when no other registered entity
    could own the same site. Checked against the registry's own name search (one request)."""
    import urllib.parse

    from .http import fetch_json

    core = set(_tokens(profile.get("name")))
    org = str(profile.get("organisation_number") or "")
    muni = str(profile.get("municipality") or "").casefold()
    result = (fetcher or fetch_json)(BRREG_NAME_SEARCH.format(query=urllib.parse.quote(" ".join(sorted(core)))))
    if result.status != 200 or not isinstance(result.body, dict):
        return "homonym check unavailable (registry name search failed)"
    entities = (result.body.get("_embedded") or {}).get("enheter") or []
    supersets = 0
    for entity in entities:
        other_org = str(entity.get("organisasjonsnummer") or "")
        other = set(_tokens(entity.get("navn")))
        if other_org == org or not core <= other:
            continue
        supersets += 1
        other_muni = str(((entity.get("forretningsadresse") or entity.get("postadresse") or {}).get("kommune")) or "").casefold()
        extra = other - core
        if other_muni and other_muni == muni:
            return f"another entity in the same municipality has the same name tokens: {other_org} {entity.get('navn')}"
        if extra and extra <= page_tokens:
            return f"site title names another registered entity: {other_org} {entity.get('navn')}"
        if not extra and set(_tokens(other_muni)) <= all_tokens:
            return f"identically named entity {other_org} in {other_muni}, which the site also mentions"
    if entities and supersets >= len(entities):
        return "too many registered entities share these name tokens"
    return None


def discover_website_by_domain_search(
    profile: dict[str, Any],
    *,
    timeout: float = 8.0,
    deadline: float | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Deterministic candidate-domain discovery. Only strict on-page proof is accepted; the
    registry_declared_domain rule never applies here."""
    total_metrics = {"requests": 0, "bytes": 0, "latencies_ms": [], "candidates": 0}
    if str(profile.get("legal_form") or "").upper() in SKIP_DISCOVERY_FORMS:
        return None, total_metrics
    candidates: list[tuple[str, str]] = []
    domain = email_domain(profile)
    if domain:
        candidates.append((f"www.{domain}", "registry_email_domain"))
    candidates.extend((url, "legal_name_slug") for url in generate_candidate_domains(profile.get("name") or "", subunit_names(profile)))
    seen: set[str] = set()
    for candidate_url, method in candidates:
        key = candidate_url.removeprefix("https://").removeprefix("www.")
        if key in seen:
            continue
        if deadline is not None and time.monotonic() > deadline:
            break
        seen.add(key)
        total_metrics["candidates"] += 1
        website_record, metrics = fetch_website(candidate_url, timeout=timeout)
        if website_record.get("status") == "blocked" and "did not resolve" in str(website_record.get("note") or ""):
            # Some sites only answer on the bare domain.
            website_record, apex_metrics = fetch_website("https://" + key, timeout=timeout)
            metrics = {
                "requests": metrics.get("requests", 0) + apex_metrics.get("requests", 0),
                "bytes": metrics.get("bytes", 0) + apex_metrics.get("bytes", 0),
                "latencies_ms": [*metrics.get("latencies_ms", []), *apex_metrics.get("latencies_ms", [])],
            }
        total_metrics["requests"] += metrics.get("requests", 0)
        total_metrics["bytes"] += metrics.get("bytes", 0)
        total_metrics["latencies_ms"].extend(metrics.get("latencies_ms", []))
        if website_record.get("status") != "available":
            continue
        gated = apply_website_identity_gate(profile, website_record)
        gated_website = gated["website"]
        value = gated_website.get("value") or {}
        accepted, reason = strict_discovered_proof(profile, value)
        if not accepted:
            continue
        assessment = value.get("identity_assessment") or {}
        value["identity_assessment"] = {
            **assessment,
            "status": "exact",
            "publishable": True,
            "score": max(assessment.get("score", 0), 0.95),
            "method": "discovered_domain_strict_proof",
            "reasons": [reason],
        }
        value["discovery_method"] = method
        value["social_links"] = publishable_social_links(profile, value)
        gated_website["value"] = value
        return gated_website, total_metrics
    return None, total_metrics
