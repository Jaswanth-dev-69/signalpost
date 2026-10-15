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


class BlindReviewRound7(unittest.TestCase):
    """Deterministic fixes from the round-7 blind review: faithful activity terms, legal-form names, the
    parent's year next to group figures, only quoted hiring facts, reader wording, no repeats."""

    def env_with(self, *claims: dict, accounts: list[dict] | None = None) -> dict:
        from test_v5 import profile
        from norway_company_agent.official import normalize_financials
        p = profile()
        if accounts is not None:
            p["evidence"]["financials"]["value"] = normalize_financials(accounts)
        env = envelope(p)
        env.setdefault("run", {})["completed_at"] = "2026-10-14T00:00:00Z"
        fields = {c["field"] for c in claims}
        env["claims"] = [c for c in env["claims"] if c["field"] not in fields]
        ev = env["claims"][0]["evidence_ids"]
        env["claims"] += [{"availability": "available", "evidence_ids": ev, **c} for c in claims]
        return env

    def text(self, env: dict) -> str:
        from norway_company_agent.synthesis import envelope_summary
        return envelope_summary(env)["text"]

    def test_investment_terms_follow_what_is_invested_in(self):
        from norway_company_agent.synthesis import activity_terms
        self.assertEqual(activity_terms("Investeringstjenestevirksomhet, samt slik virksomhet som lovlig kan drives i tilknytning til dette."), ["investment services"])
        self.assertEqual(activity_terms("Investeringer i fast eiendom."), ["real estate"])
        self.assertEqual(activity_terms("Investering i aksjer og verdipapirer."), ["owning shares in other companies"])
        self.assertEqual(activity_terms("Investering i verdipapirer og andre selskap og fast eiendom."), ["owning shares in other companies", "real estate"])
        self.assertEqual(activity_terms("Investeringsvirksomhet og rådgivningsvirksomhet."), ["investment", "consulting"])
        self.assertEqual(activity_terms("Salg av datatbehandlingstjenester, salg av data- utstyr, systemer og hva dermed står i forbindelse, "
                                        "samt delta i andre selskaper med økonomisk formål."), ["IT"])

    def test_fund_bank_and_management_texts_get_english_terms(self):
        from norway_company_agent.synthesis import activity_terms
        self.assertEqual(activity_terms("Kombinasjonsfond."), ["securities fund"])
        self.assertEqual(activity_terms("Sparebank."), ["banking"])
        self.assertEqual(activity_terms("Banken kan utføre alle forretninger som det er vanlig at banker utfører."), ["banking"])
        self.assertEqual(activity_terms("Forvaltning."), ["management"])
        self.assertEqual(activity_terms("Forvaltning av fast eiendom."), ["real estate"])
        self.assertEqual(activity_terms("Kapitalforvaltning."), ["asset management"])
        self.assertEqual(activity_terms("Agent for tekniske hjelpemidler til funksjonshemmede."), ["assistive devices"])

    def test_investment_services_raise_no_shareholding_unknown(self):
        text = self.text(self.env_with({"field": "registered_activity", "value": ["Investeringstjenestevirksomhet."]}))
        self.assertIn("in English, this text mentions investment services", text)
        self.assertNotIn("owning shares", text)
        self.assertNotIn("holds shares", text)

    def test_legal_forms_are_named_with_the_right_article(self):
        from norway_company_agent.synthesis import LEGAL_FORMS
        self.assertEqual(LEGAL_FORMS["VPFO"], "securities fund")
        self.assertIn("is a securities fund (VPFO)", self.text(self.env_with({"field": "legal_form", "value": "VPFO"})))
        self.assertIn("is an association (FLI)", self.text(self.env_with({"field": "legal_form", "value": "FLI"})))

    def test_parent_revenue_names_its_year_when_the_group_year_differs(self):
        from test_v5 import year
        accounts = [year(2023, 1000000.0, -50000.0), year(2024, 1200000.0, 20000.0), year(2025, 1500000.0, 90000.0),
                    year(2024, 9000000.0, 400000.0, "KONSERN")]
        brief = self.text(self.env_with(accounts=accounts)).split("\n")[0]
        self.assertIn("The group (konsern) had revenue of NOK 9.0 million in 2024", brief)
        self.assertIn("the parent company's own revenue was NOK 1.5 million in 2025", brief)
        same = self.text(self.env_with()).split("\n")[0]
        self.assertIn("the parent company's own revenue was NOK 1.5 million [", same)

    def test_no_openings_are_not_asserted_without_a_quoted_span(self):
        page = {"field": "hiring_signal", "value": "https://www.example.no/jobb", "kind": "careers_page", "openings_listed": False}
        text = self.text(self.env_with(page))
        self.assertIn("It has a careers page, https://www.example.no/jobb [", text)
        self.assertNotIn("no open positions", text)

    def test_unreadable_sources_are_described_in_reader_terms(self):
        env = self.env_with()
        for claim in env["claims"]:
            if claim["field"] in ("revenue", "operating_result", "annual_result", "assets", "debt", "reporting_period",
                                  "financial_history", "group_accounts", "group_financials"):
                claim.update(availability="failed", value=None)
        text = self.text(env)
        self.assertIn("annual accounts (the accounts register did not return them when this profile was compiled)", text)
        self.assertNotIn("in this run", text)

    def test_subunits_are_named_by_registered_employees(self):
        units = [{"name": f"AVD {n}", "address": {"kommune": n}, "employees": e}
                 for n, e in (("ASKER", 5), ("BODØ", 30), ("KINN", 0), ("OSLO", 12), ("TROMSØ", 209), ("BERGEN", 1))]
        text = self.text(self.env_with({"field": "registered_subunits", "value": units}))
        self.assertIn("It has 6 registered sub-units (establishments) in Tromsø, Bodø, Oslo and Asker and 2 other municipalities "
                      "(named by registered employees, largest first)", text)

    def test_no_role_holders_is_stated_as_a_fact(self):
        env = self.env_with()
        roles = next(c for c in env["claims"] if c["field"] == "registered_roles")
        roles.update(availability="not_available", value=None)
        text = self.text(env)
        leadership = next(line for line in text.split("\n") if line.startswith("Leadership and locations"))
        self.assertIn("The register lists no active role holders for it: no chief executive (daglig leder) and no board", leadership)
        self.assertNotIn("leadership (no active role holders are registered)", text)

    def test_a_recent_rename_is_told_once_outside_the_brief(self):
        env = self.env_with({"field": "former_names", "value": [{"name": "TESTSELSKAP SØR AS", "until": "2025-11-05"}]})
        text = self.text(env)
        self.assertNotIn("Earlier names in the register", text)
        changed = next(line for line in text.split("\n") if line.startswith("What changed"))
        self.assertIn("It changed its name on 2025-11-05; it was previously registered as TESTSELSKAP SØR AS", changed)

    def test_launches_and_appointments_are_business_news(self):
        from norway_company_agent.synthesis import MATERIAL_NEWS
        self.assertTrue(MATERIAL_NEWS.search("Hjelpemiddelspesialisten introduserer Sensiva.no"))
        self.assertTrue(MATERIAL_NEWS.search("Jan-Inge Christensen ny finansdirektør"))
        self.assertTrue(MATERIAL_NEWS.search("Nina Skjersåker – ny leder i Stiftelsen Guts"))
        self.assertFalse(MATERIAL_NEWS.search("Ny lederstil i hverdagen"))

    def test_viewer_wording_and_tile_arrows(self):
        from test_v5 import profile
        from norway_company_agent.synthesis import apply_envelope_summary
        from norway_company_agent.viewer import build_viewer_html
        env = envelope(profile())
        apply_envelope_summary(env)
        html = build_viewer_html([env], {"run_id": "run-1", "started_at": T, "completed_at": T})
        self.assertIn("function glue(t,l)", html)
        self.assertIn(".metric>span{", html)
        self.assertIn("Identity proof, quoted from its source", html)
        for jargon in ("' companies · run '", "no earlier run", "in this run", "no openings stated", "since last run"):
            self.assertNotIn(jargon, html)
