"""v6: company-site news pages in the kit profile, as the kit's own news reader reads them."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from bs4 import BeautifulSoup  # noqa: E402
from norway_company_agent.webclaims import kit_news_link  # noqa: E402
from test_contract_rev3 import HASH_PAGE, T, envelope, verified_profile  # noqa: E402

ORG = "923609016"
spec = importlib.util.spec_from_file_location("kit_site_news", ROOT / "scripts" / "extract_company_site_news.py")
kit_site_news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit_site_news)


def news_item(url: str, published: str = "2025-09-22T20:00:00+02:00", title: str = "Ny avtale signert") -> dict:
    return {"title": title, "url": url, "published_date": published[:10], "published_at": published, "source_page": url,
            "content_sha256": HASH_PAGE, "retrieved_at": T, "claim_span": title, "date_span": published,
            "extraction_method": "article_page:meta_published_time"}


def kit_news_url(env: dict) -> str | None:
    item = kit_site_news.observation({"organisation_number": env["organisation_number"], **env["profile"]})
    return item["source_url"] if item else None


class KitNewsPages(unittest.TestCase):
    def test_a_checked_news_section_reaches_the_kit_reader_without_dated_items(self):
        profile = verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/")
        profile["web_claims"]["news"]["checked_pages"] = [{"url": "https://www.example.no/nyheter", "content_sha256": HASH_PAGE,
                                                           "retrieved_at": T, "claim_span": "Nyheter"}]
        env = envelope(profile)
        self.assertEqual([c for c in env["claims"] if c["field"] == "dated_news" and c["availability"] == "available"], [])
        self.assertEqual(kit_news_url(env), "https://www.example.no/nyheter")

    def test_newest_published_article_on_a_news_path_when_no_section_page_is(self):
        items = [news_item("https://www.example.no/aktuelt/eldre-sak", "2025-03-01T10:00:00+01:00", "Eldre sak"),
                 news_item("https://www.example.no/aktuelt/ny-avtale"),
                 news_item("https://www.example.no/prosjekter/bro", "2025-10-01T10:00:00+02:00", "Ny bro")]
        env = envelope(verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/", news=items))
        self.assertEqual(kit_news_url(env), "https://www.example.no/aktuelt/ny-avtale")
        page = next(p for p in env["profile"]["evidence"]["website"]["value"]["pages"] if p.get("page_role") == "news_article")
        self.assertEqual((page["title"], page["content_sha256"]), ("Ny avtale signert", HASH_PAGE))

    def test_no_article_is_added_when_a_section_page_is_on_a_news_path(self):
        profile = verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/", news=[news_item("https://www.example.no/aktuelt/ny-avtale")])
        profile["web_claims"]["news"]["checked_pages"] = [{"url": "https://www.example.no/aktuelt/", "content_sha256": HASH_PAGE,
                                                           "retrieved_at": T, "claim_span": "Aktuelt"}]
        env = envelope(profile)
        roles = [p.get("page_role") for p in env["profile"]["evidence"]["website"]["value"]["pages"]]
        self.assertNotIn("news_article", roles)
        self.assertEqual(kit_news_url(env), "https://www.example.no/aktuelt/")

    def test_unverified_sites_get_no_news_pages(self):
        profile = verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/")
        profile["evidence"]["website"]["value"]["identity_assessment"]["publishable"] = False
        profile["web_claims"]["news"]["checked_pages"] = [{"url": "https://www.example.no/nyheter", "content_sha256": HASH_PAGE,
                                                           "retrieved_at": T, "claim_span": "Nyheter"}]
        self.assertIsNone(kit_news_url(envelope(profile)))


class KitNewsLink(unittest.TestCase):
    def test_kit_ranking_same_host_news_path(self):
        html = ('<a href="/om-oss">Om oss</a><a href="https://annet.no/news/x">Ekstern</a>'
                '<a href="/aktuelt/b-sak">B</a><a href="/aktuelt/a-sak?utm=1">A</a><a href="/nyheter/">Nyheter</a>'
                '<a href="/presse-og-media">Presse</a>')
        link = kit_news_link("https://www.example.no/", BeautifulSoup(html, "lxml"))
        self.assertEqual(link, "https://www.example.no/aktuelt/a-sak")  # "aktuelt" outranks "nyheter"; then by URL; query dropped

    def test_news_term_outranks_aktuelt_and_paths_off_the_news_reader_are_skipped(self):
        html = '<a href="/aktuelt/sak">Sak</a><a href="/news/launch">Launch</a><a href="/news-and-projects/">News</a>'
        self.assertEqual(kit_news_link("https://www.example.no/", BeautifulSoup(html, "lxml")), "https://www.example.no/news/launch")
        self.assertIsNone(kit_news_link("https://www.example.no/", BeautifulSoup('<a href="/blogs/omega-3">Blogg</a>', "lxml")))


if __name__ == "__main__":
    unittest.main()


class KitNewsLinkIsNotEvidence(unittest.TestCase):
    def test_the_kit_link_page_is_not_cited_by_the_no_news_claim(self):
        profile = verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/")
        profile["web_claims"]["news"]["checked_pages"] = [{"url": "https://www.example.no/aktuelt/sak", "content_sha256": HASH_PAGE,
                                                           "retrieved_at": T, "claim_span": "Sak", "page_role": "kit_news_link"}]
        env = envelope(profile)
        claim = next(c for c in env["claims"] if c["field"] == "dated_news")
        sources = {e["source_url"] for e in env["evidence"] if e["id"] in claim["evidence_ids"]}
        self.assertNotIn("https://www.example.no/aktuelt/sak", sources)
        self.assertEqual(kit_news_url(env), "https://www.example.no/aktuelt/sak")


class SingleNodeDescriptions(unittest.TestCase):
    """A description quoted from a page's paragraph must sit inside one text node of that page."""

    def soup(self, body: str):
        return BeautifulSoup(f"<html><body>{body}</body></html>", "lxml")

    def test_a_paragraph_inside_one_node_is_left_as_it_is(self):
        from norway_company_agent.website import _lead_paragraph_fix
        text = "Testselskap Nord leverer ladeutstyr for elbiler til borettslag, bedrifter og kommuner over hele landet."
        self.assertIsNone(_lead_paragraph_fix(text, self.soup(f"<p>{text}</p>")))

    def test_a_paragraph_across_an_inline_tag_keeps_the_whole_sentences_of_its_first_node(self):
        from norway_company_agent.website import _lead_paragraph_fix
        html = ("<p>Serit er en nasjonal leverandør, med kompetanse lokalt. Med tydelig tilstedeværelse gjør vi IT til et "
                "konkurransefortrinn for alle typer <strong>bedrifter</strong>. Vi har 27 kontorer.</p>")
        text = ("Serit er en nasjonal leverandør, med kompetanse lokalt. Med tydelig tilstedeværelse gjør vi IT til et "
                "konkurransefortrinn for alle typer bedrifter. Vi har 27 kontorer.")
        lead = _lead_paragraph_fix(text, self.soup(html))
        self.assertEqual(lead, "Serit er en nasjonal leverandør, med kompetanse lokalt.")
        self.assertTrue(any(lead in " ".join(str(n).split()) for n in self.soup(html).find_all(string=True)))

    def test_no_whole_sentence_in_the_first_node_means_no_paragraph(self):
        from norway_company_agent.website import _lead_paragraph_fix
        html = "<p>Vi leverer <a href='/x'>maskiner</a> til skog og hage over hele landet, med service og deler i egen verkstedhall.</p>"
        text = "Vi leverer maskiner til skog og hage over hele landet, med service og deler i egen verkstedhall."
        self.assertEqual(_lead_paragraph_fix(text, self.soup(html)), "")

    def test_the_contract_uses_the_single_node_text_or_falls_through(self):
        from norway_company_agent.contract import _company_description
        about = {"url": "https://www.example.no/om-oss", "main_text_excerpt": "x " * 60}
        home = {"main_text_excerpt": ("Testselskap Nord leverer ladeutstyr for elbiler til borettslag, bedrifter og kommuner "
                                      "over hele landet, med egen montørstab.")}
        web_val = {**home, "pages": [{"url": "https://www.example.no/"}, {**about, "lead_paragraph": "Serit er en nasjonal leverandør, med kompetanse lokalt."}]}
        self.assertEqual(_company_description(web_val, "https://www.example.no/"),
                         ("Serit er en nasjonal leverandør, med kompetanse lokalt.", "https://www.example.no/om-oss"))
        web_val["pages"][1]["lead_paragraph"] = ""
        self.assertEqual(_company_description(web_val, "https://www.example.no/")[1], "https://www.example.no/")
        web_val["lead_paragraph"] = ""
        self.assertEqual(_company_description(web_val, "https://www.example.no/"), (None, None))
