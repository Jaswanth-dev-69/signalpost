#!/usr/bin/env python3
"""Wrong-company audit for websites accepted only as a registry-declared domain.

For every company whose website passed via `registry_declared_domain`, re-fetch the site's
homepage plus contact/about/privacy pages and flag a WRONG_COMPANY hit when any page prints
a (mod-11 valid) organisation number other than the company's own. Also reports, as a risk
metric (not a hit), how many other registry entities declare the same domain.

Usage: python eval/declared_domain_audit.py <profiles.jsonl> [bulk.csv.gz] [report.json]
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.identity import _tokens, org_numbers_in_text  # noqa: E402
from norway_company_agent.sampling import iter_bulk  # noqa: E402
from norway_company_agent.webclaims import SiteFetcher, registered_domain  # noqa: E402
from norway_company_agent.website import _identity_links  # noqa: E402

EXTRA_PATHS = ("/kontakt", "/kontakt-oss", "/om-oss", "/personvern", "/contact", "/about")


def page_text(page: dict) -> str:
    return " ".join(BeautifulSoup(page["raw"].decode("utf-8", errors="replace"), "lxml").get_text(" ", strip=True).split())


def audit_site(url: str) -> tuple[list[str], list[str], str]:
    fetcher = SiteFetcher(registered_domain(url), timeout=10.0)
    home = fetcher.get(url, "audit")
    if not home:
        return [], [], ""
    soup = BeautifulSoup(home["raw"].decode("utf-8", errors="replace"), "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    urls = _identity_links(home["url"], soup, limit=3) + [urllib.parse.urljoin(home["url"], p) for p in EXTRA_PATHS]
    pages, found = [home["url"]], org_numbers_in_text(page_text(home))
    for candidate in dict.fromkeys(urls):
        page = fetcher.get(candidate, "audit")
        if page and "html" in page["content_type"]:
            pages.append(page["url"])
            found.extend(o for o in org_numbers_in_text(page_text(page)) if o not in found)
    return found, pages, title


def main() -> int:
    profiles_path = Path(sys.argv[1])
    bulk_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "brreg-enheter.csv.gz"
    report_path = Path(sys.argv[3]) if len(sys.argv) > 3 else profiles_path.with_suffix(".declared_audit.json")
    declared = []
    for line in profiles_path.read_text(encoding="utf-8").splitlines():
        profile = json.loads(line)
        value = ((profile.get("evidence") or {}).get("website") or {}).get("value") or {}
        if (value.get("identity_assessment") or {}).get("method") == "registry_declared_domain":
            declared.append((profile, value))
    domains = {registered_domain(v.get("final_url") or "") for _, v in declared}
    declarers: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in iter_bulk(bulk_path):
        if row.get("website"):
            site = row["website"] if "://" in row["website"] else "https://" + row["website"]
            domain = registered_domain(site)
            if domain in domains:
                declarers[domain].append((row["organisation_number"], row["name"]))

    hits, rows = [], []
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        audited = list(pool.map(lambda pv: audit_site(pv[1].get("final_url")), declared))
    for (profile, value), (found, pages, title) in zip(declared, audited):
        org, url = profile["organisation_number"], value.get("final_url")
        others = [o for o in found if o != org]
        domain = registered_domain(url)
        co_declarers = [d for d in declarers.get(domain, []) if d[0] != org]
        title_tokens = set(_tokens(title))
        names_other = [n for o, n in co_declarers if _tokens(n) and set(_tokens(n)) <= title_tokens]
        row = {
            "organisation_number": org,
            "name": profile.get("name"),
            "url": url,
            "pages_checked": len(pages),
            "other_org_numbers_on_site": others,
            "other_registry_entities_declaring_domain": len(co_declarers),
            "site_title": title[:120],
            "title_names_other_declarer": names_other[:3],
            "verdict": "WRONG_COMPANY" if others else "OK",
        }
        rows.append(row)
        if others:
            hits.append(row)
        print(f"  {row['verdict']:13s} {org} {str(profile.get('name'))[:40]:40s} {url} co-declarers={len(co_declarers)} other_orgs={others}", flush=True)
    report = {
        "declared_domain_sites": len(declared),
        "wrong_company_hits": len(hits),
        "shared_domain_sites": sum(1 for r in rows if r["other_registry_entities_declaring_domain"] > 0),
        "site_title_names_other_declarer": sum(1 for r in rows if r["title_names_other_declarer"]),
        "hits": hits,
        "rows": rows,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("rows", "hits")}))
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
