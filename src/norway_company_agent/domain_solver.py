from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

from .identity import apply_website_identity_gate
from .website import fetch_website


def generate_candidate_domains(company_name: str) -> list[str]:
    """Generate candidate Norwegian domain names from a company's legal name."""
    # Remove Norwegian diacritics and normalize
    text = company_name.translate(str.maketrans({
        "ø": "o", "Ø": "O",
        "å": "a", "Å": "A",
        "æ": "ae", "Æ": "AE",
    }))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    
    # Generic corporate suffixes to remove
    suffixes = {"as", "asa", "ans", "da", "enk", "sa", "nuf", "norge", "norway", "group", "gruppen", "holdings", "holding"}
    tokens = [t for t in re.findall(r"[a-z0-9]+", text) if t not in suffixes and len(t) > 1]

    if not tokens:
        return []

    candidates: list[str] = []

    # 1. Full joined tokens: "jonvikoren.no"
    joined = "".join(tokens)
    if len(joined) >= 3:
        candidates.append(f"https://www.{joined}.no")
        candidates.append(f"https://{joined}.no")

    # 2. Hyphenated tokens: "jon-vikoren.no"
    if len(tokens) >= 2:
        hyphenated = "-".join(tokens)
        if len(hyphenated) >= 3:
            candidates.append(f"https://www.{hyphenated}.no")
            candidates.append(f"https://{hyphenated}.no")

    # 3. Main distinctive token (if last token is long): "vikoren.no"
    distinctive = [t for t in tokens if len(t) >= 4]
    for d in distinctive:
        if f"https://www.{d}.no" not in candidates:
            candidates.append(f"https://www.{d}.no")

    # Deduplicate preserving order
    seen = set()
    result = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            result.append(url)

    return result[:5]


def discover_website_by_domain_search(
    profile: dict[str, Any],
    *,
    timeout: float = 8.0,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Attempt deterministic candidate domain discovery and return verified website evidence if exact identity passes."""
    name = profile.get("name") or ""
    candidates = generate_candidate_domains(name)
    total_metrics = {"requests": 0, "bytes": 0, "latencies_ms": []}

    for candidate_url in candidates:
        website_record, metrics = fetch_website(candidate_url, timeout=timeout)
        total_metrics["requests"] += metrics.get("requests", 0)
        total_metrics["bytes"] += metrics.get("bytes", 0)
        total_metrics["latencies_ms"].extend(metrics.get("latencies_ms", []))

        if website_record.get("status") == "available":
            gated = apply_website_identity_gate(profile, website_record)
            gated_website = gated["website"]
            assessment = gated["assessment"] or {}

            if assessment.get("publishable"):
                # Candidate domain discovery requires HIGHER proof than registry-declared URLs:
                # 1) Exact 9-digit organisation number on page, OR
                # 2) Full core name (>= 2 tokens) AND municipality match on page
                val = gated_website.get("value") or {}
                text = str(val.get("main_text_excerpt") or "") + " " + str(val.get("title") or "")
                org = str(profile.get("organisation_number") or "")
                muni = str(profile.get("municipality") or "").casefold()
                core_tokens = assessment.get("legal_name_tokens") or []

                has_org = bool(org and org in text)
                has_muni_and_name = bool(
                    muni and muni in text.casefold()
                    and len(core_tokens) >= 2
                    and all(t in text.casefold() for t in core_tokens)
                )

                if has_org or has_muni_and_name:
                    val["discovery_method"] = "deterministic_domain_candidate"
                    gated_website["value"] = val
                    return gated_website, total_metrics

    return None, total_metrics
