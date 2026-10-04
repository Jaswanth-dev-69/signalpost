from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

from .identity import DECLARED_DOMAIN_REJECT, _structured_names, _tokens, apply_website_identity_gate
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
MAX_NAME_CANDIDATES = 6


def _slug_tokens(company_name: str) -> list[str]:
    text = company_name.translate(str.maketrans({"ø": "o", "Ø": "O", "å": "aa", "Å": "AA", "æ": "ae", "Æ": "AE"}))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return [t for t in re.findall(r"[a-z0-9]+", text) if t not in LEGAL_SUFFIXES]


def generate_candidate_domains(company_name: str) -> list[str]:
    """Candidate homepages from the legal name: joined, hyphenated, aa->a variants; .no before .com."""
    tokens = _slug_tokens(company_name)
    if not tokens:
        return []
    stems: list[str] = []
    joined = "".join(tokens)
    if len(joined) >= 4:
        stems.append(joined)
    if len(tokens) >= 2:
        stems.append("-".join(tokens))
    for stem in list(stems):
        if "aa" in stem:
            stems.append(stem.replace("aa", "a"))
    stems = list(dict.fromkeys(stems))
    candidates = [f"{stem}.no" for stem in stems] + [f"{stem}.com" for stem in stems[:1]]
    return [f"https://www.{c}" for c in candidates][:MAX_NAME_CANDIDATES]


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
    core = _tokens(profile.get("name"))
    muni = set(_tokens(profile.get("municipality") or ""))
    page_tokens = set(_tokens(identity_text))
    all_tokens = set(_tokens(all_text))
    if len(core) >= 2 and set(core) <= page_tokens and muni and muni <= all_tokens:
        return True, "full legal name on homepage and registered municipality on site"
    return False, "no organisation number and no legal name plus municipality"


def discover_website_by_domain_search(
    profile: dict[str, Any],
    *,
    timeout: float = 8.0,
    deadline: float | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Deterministic candidate-domain discovery. Only strict on-page proof is accepted; the
    registry_declared_domain rule never applies here."""
    total_metrics = {"requests": 0, "bytes": 0, "latencies_ms": [], "candidates": 0}
    candidates: list[tuple[str, str]] = []
    domain = email_domain(profile)
    if domain:
        candidates.append((f"www.{domain}", "registry_email_domain"))
    candidates.extend((url, "legal_name_slug") for url in generate_candidate_domains(profile.get("name") or ""))
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
        value["social_links"] = [
            {k: item[k] for k in ("platform", "url", "found_on_page", "href") if item.get(k)}
            for item in value.get("discovered_social_links") or []
        ]
        gated_website["value"] = value
        return gated_website, total_metrics
    return None, total_metrics
