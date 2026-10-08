"""v4: organisation-number detection (W1c). The entity's own number counts wherever the site prints
it, in any common format, but never on a page that also prints another organisation's number."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.domain_solver import strict_discovered_proof  # noqa: E402
from norway_company_agent.identity import (  # noqa: E402
    assess_website_identity,
    org_numbers_anywhere,
    org_numbers_in_text,
    own_org_number_printed,
    structured_org_numbers,
)
from norway_company_agent.website import strip_private_fields  # noqa: E402
from norway_company_agent.webclaims import _listing_inline_items, _next_listing_page  # noqa: E402
from test_contract_rev3 import HASH_PAGE, T, available, envelope, verified_profile  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

ORG, OTHER = "923609016", "916300484"


def profile(name: str = "TESTSELSKAP NORD AS") -> dict:
    return {"organisation_number": ORG, "name": name, "municipality": "OSLO"}


def site(printed: list[str], labelled: list[str] | None = None, structured: list | None = None) -> dict:
    return {"final_url": "https://www.example.no/", "title": "Forside", "description": "", "main_text_excerpt": "Velkommen",
            "pages": [], "org_numbers_on_site": labelled or [], "_org_numbers_anywhere": printed,
            "structured_organisations": structured or []}


class OrgNumberDetection(unittest.TestCase):
    def test_unlabelled_dotted_hyphenated_and_vat_forms_are_found(self):
        for text in ("Testselskap AS | 923 609 016 | Storgata 1", "923.609.016", "923-609-016", "NO923609016MVA", "org nr: 923 609 016"):
            self.assertEqual(org_numbers_anywhere(text), [ORG], text)

    def test_digits_inside_longer_numbers_are_not_org_numbers(self):
        for text in ("tel 1923609016", "konto 1.923.609.016", "9236090160"):
            self.assertEqual(org_numbers_anywhere(text), [], text)

    def test_more_labels_and_separators_are_read_as_labelled_numbers(self):
        for text in ("Foretaksnr 923 609 016", "Organization number: 923609016", "Company reg. no. 923.609.016", "Org.nr.923-609-016"):
            self.assertEqual(org_numbers_in_text(text), [ORG], text)

    def test_jsonld_identifiers(self):
        nodes = [{"@type": "Organization", "vatID": "NO923609016MVA"}, {"identifier": {"@type": "PropertyValue", "value": "923 609 016"}}, {"taxID": "12"}]
        self.assertEqual(structured_org_numbers(nodes), [ORG])

    def test_own_number_alone_is_proof(self):
        self.assertTrue(own_org_number_printed(profile(), site([ORG])))
        self.assertTrue(own_org_number_printed(profile(), site([], structured=[{"vatID": f"NO{ORG}MVA"}])))

    def test_page_printing_another_number_is_never_proof(self):
        self.assertFalse(own_org_number_printed(profile(), site([ORG, OTHER])))
        self.assertFalse(own_org_number_printed(profile(), site([ORG], labelled=[OTHER])))
        self.assertFalse(own_org_number_printed(profile(), site([])))

    def test_discovered_domain_accepts_own_unlabelled_number_only(self):
        accepted, reason = strict_discovered_proof(profile(), site([ORG]))
        self.assertTrue(accepted)
        self.assertIn("printed on the site", reason)
        self.assertFalse(strict_discovered_proof(profile(), site([ORG, OTHER]))[0])

    def test_registry_homepage_identity_uses_the_same_rule(self):
        value = site([ORG])
        verdict = assess_website_identity({**profile(), "evidence": {"website": {"value": value}}})
        self.assertEqual((verdict["status"], verdict["publishable"]), ("exact", True))
        value = site([ORG, OTHER])
        verdict = assess_website_identity({**profile(), "evidence": {"website": {"value": value}}})
        self.assertFalse(verdict["publishable"])

    def test_printed_numbers_are_never_serialized(self):
        record = {"value": site([ORG])}
        strip_private_fields(record)
        self.assertNotIn("_org_numbers_anywhere", record["value"])


class EvidenceSpans(unittest.TestCase):
    """W2: every span is a verbatim fragment of one node of the cited page; dated facts carry their date."""

    def evidence(self, env: dict) -> dict:
        return {e["id"]: e for e in env["evidence"]}

    def test_news_evidence_carries_the_article_timestamp_as_effective_date(self):
        url = "https://www.example.no/nyheter/ny-avtale"
        item = {"title": "Ny avtale", "url": url, "published_date": "2025-09-22", "published_at": "2025-09-22T20:00:00+02:00",
                "source_page": url, "content_sha256": HASH_PAGE, "retrieved_at": T, "claim_span": "Ny avtale",
                "date_span": "2025-09-22T20:00:00+02:00"}
        env = envelope(verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/", news=[item]))
        claim = available(env, "dated_news")[0]
        for ev_id in claim["evidence_ids"]:
            self.assertEqual(self.evidence(env)[ev_id]["effective_at"], "2025-09-22T20:00:00+02:00")

    def test_posting_evidence_carries_its_posted_date(self):
        posting = {"title": "Lagerarbeider", "url": "https://www.example.no/jobb/1", "posted_date": "2026-09-01", "platform": "company_site",
                   "source_page": "https://www.example.no/jobb", "content_sha256": HASH_PAGE, "retrieved_at": T, "claim_span": "Lagerarbeider"}
        env = envelope(verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/", postings=[posting]))
        claim = next(c for c in available(env, "hiring_signal") if c.get("kind") == "job_posting")
        self.assertEqual(self.evidence(env)[claim["evidence_ids"][0]]["effective_at"], "2026-09-01")

    def test_ambiguous_site_is_cited_by_its_title_alone(self):
        profile = verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/")
        profile["evidence"]["website"]["value"]["identity_assessment"] = {"publishable": False}
        profile["evidence"]["website"]["value"]["title"] = "Example kjeden"
        env = envelope(profile)
        claim = next(c for c in env["claims"] if c["field"] == "official_website")
        self.assertEqual(claim["availability"], "ambiguous")
        spans = [self.evidence(env)[i]["claim_span"] for i in claim["evidence_ids"] if i in self.evidence(env)]
        self.assertIn("Example kjeden", spans)
        self.assertFalse(any("not established" in span for span in spans))

    def test_nav_check_cites_a_sitemap_node(self):
        profile = verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/")
        profile["nav_jobs"] = {"postings": [], "index_complete": True, "matched_orgnrs": [], "sitemap": {
            "url": "https://arbeidsplassen.nav.no/stillinger/sitemap.xml", "content_sha256": HASH_PAGE, "retrieved_at": T,
            "active_ads": 2, "first_loc": "https://arbeidsplassen.nav.no/stillinger"}}
        env = envelope(profile)
        nav = [e for e in env["evidence"] if e["source_url"].endswith("sitemap.xml")]
        self.assertEqual([e["claim_span"] for e in nav], ["https://arbeidsplassen.nav.no/stillinger"])

    def test_website_proof_from_body_text_is_quoted_tightly(self):
        profile = verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/")
        value = profile["evidence"]["website"]["value"]
        value["title"] = "Forside"
        value["main_text_excerpt"] = "Velkommen til oss. Om oss Kontakt Testselskap Nord AS | Org.nr 923 609 016 | Storgata 1, 0150 Oslo"
        env = envelope(profile)
        claim = available(env, "official_website")[0]
        self.assertEqual(self.evidence(env)[claim["evidence_ids"][0]]["claim_span"], "923 609 016")

    def test_listing_teaser_title_and_date_are_separate_spans(self):
        html = ('<html><body><ul><li><a href="/nyheter/ny-avtale"><h3>Ny avtale signert</h3></a>'
                '<span class="dato">12. mars 2026</span></li></ul></body></html>')
        listing = {"url": "https://www.example.no/nyheter", "content_sha256": HASH_PAGE, "retrieved_at": T}
        items = _listing_inline_items(listing, BeautifulSoup(html, "lxml"), "example.no")
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]["claim_span"], items[0]["date_span"]), ("Ny avtale signert", "12. mars 2026"))



class NewsPagination(unittest.TestCase):
    """W3: a listing showing fewer items than the cap is followed to its own second page only."""

    def next_page(self, url: str, html: str) -> str | None:
        return _next_listing_page(url, BeautifulSoup(html, "lxml"), "example.no")

    def test_page_two_of_the_same_listing(self):
        self.assertEqual(self.next_page("https://example.no/nyheter/", '<a href="/nyheter/page/2/">2</a>'), "https://example.no/nyheter/page/2/")
        self.assertEqual(self.next_page("https://example.no/aktuelt", '<a href="/aktuelt?side=2">Neste</a>'), "https://example.no/aktuelt?side=2")

    def test_rel_next(self):
        self.assertEqual(self.next_page("https://example.no/nyheter", '<link rel="next" href="https://example.no/nyheter?page=2">'), "https://example.no/nyheter?page=2")

    def test_other_sections_and_other_sites_are_not_followed(self):
        self.assertIsNone(self.next_page("https://example.no/nyheter", '<a href="/produkter/page/2/">x</a>'))
        self.assertIsNone(self.next_page("https://example.no/nyheter", '<a href="https://other.no/nyheter/page/2">x</a>'))


if __name__ == "__main__":
    unittest.main()
