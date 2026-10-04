from __future__ import annotations

import re
import unicodedata
import urllib.parse
from typing import Any


LEGAL_AND_GENERIC = {
    "as", "asa", "ans", "da", "enk", "iks", "sa", "sam", "sti", "stiftelsen",
    "nuf", "ab", "b", "v", "limited", "ltd", "inc", "plc", "the", "og", "and",
}


def _tokens(value: Any) -> list[str]:
    text = str(value or "").translate(str.maketrans({"ø": "o", "Ø": "O", "å": "a", "Å": "A", "æ": "ae", "Æ": "AE"}))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return [token for token in re.findall(r"[a-z0-9]+", text) if token not in LEGAL_AND_GENERIC and len(token) > 1]


def _structured_names(value: Any) -> list[str]:
    names: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"name", "legalName", "alternateName"} and isinstance(child, str):
                names.append(child)
            else:
                names.extend(_structured_names(child))
    elif isinstance(value, list):
        for child in value:
            names.extend(_structured_names(child))
    return names


def assess_website_identity(profile: dict[str, Any]) -> dict[str, Any]:
    website = profile.get("evidence", {}).get("website", {})
    value = website.get("value") or {}
    core = _tokens(profile.get("name"))
    hostname = urllib.parse.urlparse(value.get("final_url") or website.get("source_url") or "").hostname or ""
    structured_names = _structured_names(value.get("structured_organisations") or [])
    rendered = value.get("js_fallback") or {}
    homepage_identity_parts = [
        value.get("title"), value.get("description"), value.get("identity_text_excerpt"), hostname, *structured_names,
        rendered.get("title"),
    ]
    candidate_parts = [
        *homepage_identity_parts, value.get("main_text_excerpt"),
        *[page.get("title") for page in value.get("pages", [])],
        *[page.get("main_text_excerpt") for page in value.get("pages", [])],
        *[page.get("identity_text_excerpt") for page in value.get("pages", [])],
    ]
    candidate_parts.append(rendered.get("main_text_excerpt"))
    candidate_text = " ".join(str(part or "") for part in candidate_parts)
    homepage_candidate_text = " ".join(str(part or "") for part in [*homepage_identity_parts, value.get("main_text_excerpt"), rendered.get("main_text_excerpt")])
    normalized_candidate_text = " ".join(_tokens(candidate_text))
    candidate_tokens = set(_tokens(candidate_text))
    org_digits = re.sub(r"\D", "", str(profile.get("organisation_number") or ""))
    compact_candidate = re.sub(r"\D", "", candidate_text)
    compact_homepage_candidate = re.sub(r"\D", "", homepage_candidate_text)
    overlap = sorted(set(core) & candidate_tokens)
    ratio = len(overlap) / len(set(core)) if core else 0.0
    reasons = []
    parked_markers = (
        "domain is for sale", "domain for sale", "hugedomains", "parked at", "miss hosting",
        "her flytter snart en ny gjest", "has been informing visitors", "fruits.co/en/domain",
        "find the best information and most relevant links on all topics related to",
        "dan.com", "sedo.com", "afternic.com", "kjøp dette domenet", "domenet er til salgs",
    )
    normalized_raw = unicodedata.normalize("NFKD", candidate_text).encode("ascii", "ignore").decode().casefold()
    homepage_token_sets = [set(_tokens(part)) for part in homepage_identity_parts if part]
    exact_homepage_name = bool(core and any(set(core).issubset(tokens) for tokens in homepage_token_sets))
    substantive_homepage = len(str(value.get("main_text_excerpt") or "").strip()) >= 100
    is_business_sports_club = bool(re.search(r"(?:^|\s)B\.?\s*I\.?\s*L\.?(?:\s|$)", str(profile.get("name") or ""), re.I))
    muni_tokens = set(_tokens(str(profile.get("municipality") or "")))
    muni_match = bool(muni_tokens and muni_tokens.issubset(candidate_tokens))

    if any(marker in normalized_raw for marker in parked_markers):
        score = 0.1
        reasons.append("captured page is a parked, for-sale, or generic hosting placeholder")
    elif is_business_sports_club and "bedriftsidrett" not in normalized_candidate_text and "b i l" not in normalized_candidate_text:
        score = 0.3
        reasons.append("business sports-club entity points to the operating company's site without club evidence")
    elif org_digits and org_digits in compact_homepage_candidate:
        score = 1.0
        reasons.append("exact organisation number appears in homepage identity evidence")
    elif len(core) >= 2 and exact_homepage_name:
        score = 0.95
        reasons.append("all normalized legal-name tokens appear together in homepage identity evidence")
    elif len(core) == 1 and exact_homepage_name and muni_match and substantive_homepage:
        score = 0.95
        reasons.append("single distinctive legal-name token appears with matching municipality in homepage identity evidence")
    elif len(core) == 1 and exact_homepage_name:
        score = 0.70
        reasons.append("single legal-name token without organisation number or municipality corroboration")
    elif ratio >= 0.75 and len(overlap) >= 2:
        score = 0.85
        reasons.append("most legal-name tokens appear, but exact identity is incomplete")
    elif ratio >= 0.5 and len(overlap) >= 2:
        score = 0.65
        reasons.append("partial legal-name overlap only")
    else:
        score = 0.3
        reasons.append("registry-linked URL lacks strong exact-entity identity evidence")
    status = "exact" if score >= 0.9 else "review" if score >= 0.8 else "related_or_uncertain"
    return {
        "status": status,
        "score": score,
        "publishable": status == "exact",
        "legal_name_tokens": core,
        "matched_tokens": overlap,
        "reasons": reasons,
        "method": "deterministic_name_org_evidence_v2",
    }


def assess_social_identity(profile: dict[str, Any], link: dict[str, str]) -> dict[str, Any]:
    core = _tokens(profile.get("name"))
    parsed = urllib.parse.urlparse(link.get("url") or "")
    handle_text = urllib.parse.unquote(parsed.path)
    handle_compact = "".join(_tokens(handle_text))
    matched = [token for token in core if token in handle_compact]
    core_compact = "".join(core)
    ratio = len(set(matched)) / len(set(core)) if core else 0.0
    if core_compact and core_compact in handle_compact:
        score = 0.98
        reason = "normalized legal-name sequence appears in the social handle"
    elif len(core) == 1 and matched:
        score = 0.95
        reason = "single distinctive legal-name token appears in the social handle"
    elif ratio >= 0.75 and len(set(matched)) >= 2:
        score = 0.9
        reason = "most legal-name tokens appear in the social handle"
    else:
        score = 0.3
        reason = "social handle lacks strong exact-entity name evidence"
    return {
        **link,
        "identity_score": score,
        "publishable": score >= 0.9,
        "matched_tokens": matched,
        "reason": reason,
        "method": "deterministic_social_handle_identity_v1",
    }


def apply_website_identity_gate(profile: dict[str, Any], website: dict[str, Any]) -> dict[str, Any]:
    if website.get("status") != "available":
        return {"website": website, "assessment": None, "quarantined_social_links": 0}
    temporary_profile = {**profile, "evidence": {**profile.get("evidence", {}), "website": website}}
    value = website.get("value") or {}
    assessment = assess_website_identity(temporary_profile)
    value["identity_assessment"] = assessment
    original = list(value.get("discovered_social_links") or value.get("social_links") or [])
    value["discovered_social_links"] = original
    social_assessments = [assess_social_identity(profile, link) for link in original]
    value["social_link_assessments"] = social_assessments
    # Links published from the company's own strictly verified website are
    # company-owned claims. An unverified or ambiguous website publishes none.
    value["social_links"] = [
        {key: item[key] for key in ("platform", "url", "found_on_page", "href") if item.get(key)}
        for item in original
    ] if assessment["publishable"] else []
    website["value"] = value
    return {
        "website": website,
        "assessment": assessment,
        "quarantined_social_links": len(original) - len(value["social_links"]),
    }


# Registry-declared domain verification ---------------------------------------------------
# A site the legal entity itself declared as "hjemmeside" in Enhetsregisteret is accepted
# for that exact registered domain only, with lower confidence than on-page proof, and never
# when the site names a different organisation number.

DECLARED_DOMAIN_REJECT = {
    "facebook.com", "instagram.com", "linkedin.com", "google.com", "google.no", "goo.gl", "youtube.com",
    "x.com", "twitter.com", "tiktok.com", "snapchat.com", "pinterest.com", "wix.com", "wixsite.com",
    "squarespace.com", "wordpress.com", "blogspot.com", "weebly.com", "webnode.com", "webnode.no",
    "jimdo.com", "jimdofree.com", "site123.me", "godaddysites.com", "business.site", "linktr.ee",
    "finn.no", "1881.no", "gulesider.no", "proff.no", "purehelp.no", "brreg.no", "altinn.no",
    "mittanbud.no", "hoopla.no", "bedriftsoversikten.no", "enirodk.no", "yelp.com", "tripadvisor.com",
    "booking.com", "airbnb.com", "vipps.no", "shopify.com", "myshopify.com", "github.io",
    # Wrong-company hit in declared_domain_audit (national church site shared by 666 parishes).
    "kirken.no",
}
ORG_NUMBER_IN_CONTEXT = re.compile(
    r"(?:org(?:anisasjons)?\.?\s*-?\s*(?:nr|nummer|no|number)\.?|foretaksregisteret|business\s+reg(?:istration)?\.?\s*(?:no|number)\.?|\bNO)"
    r"\s*[:.]?\s*(\d{3}\s?\d{3}\s?\d{3})(?!\d)",
    re.I,
)


def valid_org_number(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 9:
        return False
    total = sum(int(d) * w for d, w in zip(digits[:8], (3, 2, 7, 6, 5, 4, 3, 2)))
    check = 11 - total % 11
    check = 0 if check == 11 else check
    return check != 10 and check == int(digits[8])


def org_numbers_in_text(text: str) -> list[str]:
    found = []
    for match in ORG_NUMBER_IN_CONTEXT.finditer(text or ""):
        digits = re.sub(r"\D", "", match.group(1))
        if valid_org_number(digits) and digits not in found:
            found.append(digits)
    return found


def registry_declared_assessment(profile: dict[str, Any], website: dict[str, Any]) -> dict[str, Any]:
    """Decide whether a registry-declared homepage that failed on-page identity may still be used."""
    from .webclaims import registered_domain

    value = website.get("value") or {}
    strict = value.get("identity_assessment") or {}
    declared = str(profile.get("website") or "").strip()
    if declared and not re.match(r"^https?://", declared, re.I):
        declared = "https://" + declared
    declared_domain = registered_domain(declared) if declared else ""
    final_domain = registered_domain(value.get("final_url") or website.get("source_url") or "")
    other_orgs = [o for o in value.get("org_numbers_on_site") or [] if o != profile.get("organisation_number")]
    content = len(str(value.get("main_text_excerpt") or "").strip()) + len(str(value.get("title") or "").strip())
    reasons = []
    if website.get("status") != "available":
        reasons.append("registry website did not load")
    if not declared_domain:
        reasons.append("no registry hjemmeside")
    elif final_domain != declared_domain:
        reasons.append(f"site resolved to {final_domain}, not the declared domain {declared_domain}")
    declared_path = urllib.parse.urlparse(declared).path.strip("/") if declared else ""
    if declared_path:
        reasons.append(f"declared homepage is a section ({declared_path}) of a site, not a domain of its own")
    if declared_domain in DECLARED_DOMAIN_REJECT or final_domain in DECLARED_DOMAIN_REJECT:
        reasons.append("declared website is a social, directory or hosting platform domain")
    if strict.get("score", 0) <= 0.3 and any("parked" in r or "sports-club" in r for r in strict.get("reasons") or []):
        reasons.append("strict gate flagged parked page or sports-club mismatch")
    if other_orgs:
        reasons.append(f"site names a different organisation number: {', '.join(other_orgs[:3])}")
    if content < 40:
        reasons.append("page has no substantive content")
    return {
        "publishable": not reasons,
        "status": "registry_declared" if not reasons else strict.get("status", "related_or_uncertain"),
        "score": 0.75 if not reasons else strict.get("score", 0.0),
        "method": "registry_declared_domain",
        "declared_domain": declared_domain,
        "rejection_reasons": reasons,
        "strict_assessment": strict,
    }


def apply_registry_declared_gate(profile: dict[str, Any], website: dict[str, Any]) -> bool:
    value = website.get("value") or {}
    if (value.get("identity_assessment") or {}).get("publishable"):
        return False
    assessment = registry_declared_assessment(profile, website)
    value["registry_declared_assessment"] = assessment
    if not assessment["publishable"]:
        return False
    value["identity_assessment"] = {
        **assessment,
        "reasons": ["entity declared this exact domain as hjemmeside in Enhetsregisteret"],
    }
    value["social_links"] = [
        {key: item[key] for key in ("platform", "url", "found_on_page", "href") if item.get(key)}
        for item in value.get("discovered_social_links") or []
    ]
    website["value"] = value
    return True
