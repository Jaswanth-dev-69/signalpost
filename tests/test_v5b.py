"""v5 WS-B: news items carry their own article page, organisation number and real title."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bs4 import BeautifulSoup  # noqa: E402
from norway_company_agent.webclaims import _section_page, _title, _title_node, clean_news_items  # noqa: E402
from test_contract_rev3 import HASH_PAGE, T, available, envelope, verified_profile  # noqa: E402

ORG = "923609016"


def page(url: str, html: str) -> dict:
    return {"url": url, "raw": html.encode(), "content_sha256": HASH_PAGE, "retrieved_at": T, "content_type": "text/html"}


class Titles(unittest.TestCase):
    def test_logo_h1_is_not_taken_for_the_article_title(self):
        html = ('<html><head><meta property="og:title" content="Vinnarna i rebusen är korade"></head><body>'
                '<h1>Nordicon</h1><article><h2>x</h2></article></body></html>')
        soup = BeautifulSoup(html, "lxml")
        self.assertEqual(_title(soup, "https://www.nordic-on.com/vinnarna-i-rebusen-ar-korade/"), "Vinnarna i rebusen är korade")
        self.assertEqual(_title(soup), "Nordicon")  # listing pages keep their first heading

    def test_matching_first_heading_is_kept(self):
        soup = BeautifulSoup('<h1>Ny avtale signert</h1><meta property="og:title" content="Ny avtale signert | Firma AS">', "lxml")
        self.assertEqual(_title(soup, "https://www.example.no/nyheter/ny-avtale-signert"), "Ny avtale signert")

    def test_title_node_needs_one_text_node(self):
        soup = BeautifulSoup("<title>Ny avtale</title><h1><span>Ny</span> avtale</h1>", "lxml")
        self.assertEqual(_title_node(soup, "ny  avtale"), "Ny avtale")
        self.assertIsNone(_title_node(BeautifulSoup("<h1><span>Ny</span> avtale</h1>", "lxml"), "Ny avtale"))

    def test_placeholders_and_repeated_titles_are_dropped(self):
        items = [{"title": t, "url": f"https://x.no/{i}"} for i, t in enumerate(["Hei, verden!", "Nordicon", "Nordicon", "NORDICON", "Ny avtale"])]
        self.assertEqual([i["title"] for i in clean_news_items(items)], ["Hei, verden!", "Ny avtale"])

    def test_article_heading_inside_a_long_teaser_becomes_the_title(self):
        from norway_company_agent.webclaims import _heading_inside
        soup = BeautifulSoup("<h1>Singer - Songwriter, et aktivt halvår</h1>", "lxml")
        teaser = "19.4.2026 Singer - Songwriter, et aktivt halvår Mens opptaket for neste skoleår er i full gang"
        self.assertEqual(_heading_inside(soup, teaser), "Singer - Songwriter, et aktivt halvår")
        self.assertIsNone(_heading_inside(BeautifulSoup("<h1>Annet</h1>", "lxml"), teaser))


class NewsPaths(unittest.TestCase):
    def test_extension_archive_and_shop_blog_paths(self):
        from norway_company_agent.webclaims import is_news_article, is_news_listing
        self.assertTrue(is_news_listing("https://www.example.no/nyheter.html"))
        self.assertTrue(is_news_listing("https://www.example.no/Innhold/Aktueltarkiv"))
        self.assertTrue(is_news_listing("https://shop.example.no/blogs/journal"))
        self.assertTrue(is_news_article("https://shop.example.no/blogs/journal/ny-kolleksjon-host"))
        self.assertFalse(is_news_article("https://shop.example.no/blogs/journal"))
        self.assertTrue(is_news_article("https://www.example.no/blogger/knallbra-fellesuke"))
        self.assertFalse(is_news_listing("https://www.example.no/kontakt/nyhetsbrev"))


class CleanUrls(unittest.TestCase):
    def test_tracking_parameters_are_dropped_and_others_kept(self):
        from norway_company_agent.webclaims import clean_url
        self.assertEqual(clean_url("https://x.no/2026/09/14/ny/?utm_source=rss&utm_medium=rss&utm_campaign=ny#top"), "https://x.no/2026/09/14/ny/")
        self.assertEqual(clean_url("https://x.no/artikkel?id=12&fbclid=abc"), "https://x.no/artikkel?id=12")
        self.assertEqual(clean_url("https://x.no/a"), "https://x.no/a")


class SectionPages(unittest.TestCase):
    def test_category_page_listing_itself_is_a_section(self):
        html = '<ul><li><a href="/blog/news">Nyheter</a> <span>11. mai 2026</span></li></ul>'
        self.assertTrue(_section_page(page("https://www.example.no/blog/news", html), BeautifulSoup(html, "lxml"), "example.no", "Siste nytt fra oss"))

    def test_two_word_label_without_article_date_is_a_section(self):
        html = "<h1>Produktnyheter</h1><p>Se våre produkter.</p>"
        self.assertTrue(_section_page(page("https://www.example.no/blog/product_news", html), BeautifulSoup(html, "lxml"), "example.no", "Produktnyheter"))

    def test_undated_article_is_not_a_section(self):
        html = "<h1>Vi åpner nytt verksted i Bodø</h1><p>Tekst.</p>"
        self.assertFalse(_section_page(page("https://www.example.no/nyheter/nytt-verksted", html), BeautifulSoup(html, "lxml"), "example.no", "Vi åpner nytt verksted i Bodø"))


class NewsShape(unittest.TestCase):
    def item(self, **extra) -> dict:
        url = "https://www.example.no/nyheter/ny-avtale"
        base = {"title": "Ny avtale signert", "url": url, "published_date": "2025-09-22", "published_at": "2025-09-22T20:00:00+02:00",
                "source_page": url, "content_sha256": HASH_PAGE, "retrieved_at": T, "claim_span": "Ny avtale signert",
                "date_span": "Mon, 22 Sep 2025 20:00:00 +0200", "extraction_method": "article_page:title"}
        return {**base, **extra}

    def test_title_from_article_and_date_from_feed(self):
        feed = "https://www.example.no/feed/"
        env = envelope(verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/", news=[self.item(
            date_source_page=feed, date_content_sha256="d" * 64, date_retrieved_at=T, date_extraction_method="feed:rss_pubDate")]))
        claim = available(env, "dated_news")[0]
        evidence = {e["id"]: e for e in env["evidence"]}
        title_ev, date_ev = (evidence[i] for i in claim["evidence_ids"])
        self.assertEqual((title_ev["source_url"], date_ev["source_url"]), ("https://www.example.no/nyheter/ny-avtale", feed))
        self.assertEqual(date_ev["extraction_method"], "feed:rss_pubDate")
        self.assertEqual(claim["source_url"], claim["url"])

    def test_items_carry_the_organisation_number_everywhere(self):
        careers = {"url": "https://www.example.no/jobb", "content_sha256": HASH_PAGE, "retrieved_at": T, "claim_span": "Ledige stillinger"}
        env = envelope(verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/", news=[self.item()], careers=careers))
        for field in ("dated_news", "hiring_signal"):
            self.assertEqual({c["organisation_number"] for c in available(env, field)}, {ORG})
        site = env["external"]["company_site"]
        self.assertEqual({p["organisation_number"] for p in site["posts"] + site["jobs"]}, {ORG})
        self.assertEqual({o["organisation_number"] for o in env["external"]["observations"]}, {ORG})

    def test_news_listing_page_joins_the_kit_profile_pages(self):
        profile = verified_profile(ORG, "TESTSELSKAP NORD AS", "https://www.example.no/", news=[self.item()])
        profile["web_claims"]["news"]["checked_pages"] = [{"url": "https://www.example.no/nyheter", "content_sha256": HASH_PAGE,
                                                           "retrieved_at": T, "claim_span": "Nyheter"},
                                                          {"url": "https://www.example.no/feed/", "content_sha256": HASH_PAGE,
                                                           "retrieved_at": T, "claim_span": "feed"}]
        env = envelope(profile)
        pages = env["profile"]["evidence"]["website"]["value"]["pages"]
        self.assertEqual([p["url"] for p in pages if p.get("page_role") == "news_listing"], ["https://www.example.no/nyheter"])


if __name__ == "__main__":
    unittest.main()
