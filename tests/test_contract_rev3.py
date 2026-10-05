"""Claim shape and normalization for the external families, built from the four facts Builderr
reported as missed in its v2 feedback. The organisations here are test cases only."""
from __future__ import annotations

import sys
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bs4 import BeautifulSoup  # noqa: E402

from norway_company_agent.contract import BULK_URL, WEB_FIELDS, profile_to_contract_envelope, social_profile_value  # noqa: E402
from norway_company_agent.webclaims import careers_heading, published_at  # noqa: E402

T = "2026-10-05T12:00:00Z"
HASH_REGISTRY, HASH_HOME, HASH_PAGE = "a" * 64, "b" * 64, "c" * 64


def builderr_url_key(value: str) -> str:
    """The form of Builderr's examples: no scheme, no www, lowercase, no trailing slash."""
    parsed = urllib.parse.urlparse(value)
    return ((parsed.hostname or "").removeprefix("www.") + parsed.path.rstrip("/")).lower()


def verified_profile(org: str, name: str, home: str, *, social=(), news=(), careers=None, postings=()) -> dict:
    return {
        "organisation_number": org,
        "name": name,
        "legal_form": "ASA",
        "website": urllib.parse.urlparse(home).hostname,
        "errors": [],
        "run_metrics": {},
        "evidence": {
            "registry": {"status": "available", "source_url": BULK_URL, "source_type": "official_registry_bulk",
                         "retrieved_at": T, "content_sha256": HASH_REGISTRY, "value": {}},
            "website": {"status": "available", "source_url": home, "retrieved_at": T, "content_sha256": HASH_HOME, "value": {
                "final_url": home, "title": f"{name} | home", "description": "", "main_text_excerpt": f"{name} org.nr {org}",
                "content_sha256": HASH_HOME, "pages": [], "social_links": list(social),
                "identity_assessment": {"publishable": True, "method": "deterministic_name_org_evidence_v2"},
            }},
        },
        "web_claims": {"social": {"profiles": list(social)}, "news": {"items": list(news), "checked_pages": []},
                       "jobs": {"postings": list(postings), "careers_page": careers}},
    }


def envelope(profile: dict) -> dict:
    return profile_to_contract_envelope(profile, run_id="test", started_at=T, completed_at=T)


def available(env: dict, field: str) -> list[dict]:
    return [c for c in env["claims"] if c["field"] == field and c["availability"] == "available"]


class NamedExampleShapes(unittest.TestCase):
    def test_social_profile_mtm_skogservice(self):
        social = [
            {"platform": "facebook", "url": "https://facebook.com/MtmSkogservice", "href": "https://www.facebook.com/MtmSkogservice/?fref=ts", "found_on_page": "https://www.mtm-skogservice.no/"},
            {"platform": "instagram", "url": "https://instagram.com/mtmskogservice", "href": "https://www.instagram.com/mtmskogservice/", "found_on_page": "https://www.mtm-skogservice.no/"},
        ]
        env = envelope(verified_profile("811730912", "MTM SKOGSERVICE AS", "https://www.mtm-skogservice.no/", social=social))
        claims = available(env, "social_profile")
        self.assertEqual(len(claims), 2)
        self.assertIn("facebook.com/mtmskogservice", {builderr_url_key(c["value"]) for c in claims})
        evidence = {e["id"]: e for e in env["evidence"]}
        for claim in claims:
            self.assertIsInstance(claim["value"], str)
            self.assertEqual(len(claim["evidence_ids"]), 1)
            ev = evidence[claim["evidence_ids"][0]]
            self.assertEqual(ev["source_url"], "https://www.mtm-skogservice.no/")
            self.assertEqual(claim["source_url"], ev["source_url"])

    def test_hiring_signal_equinor_careers_page_without_postings(self):
        careers = {"url": "https://www.equinor.com/careers", "content_sha256": HASH_PAGE, "retrieved_at": T,
                   "claim_span": "Careers in Equinor", "explicit_no_openings": False}
        env = envelope(verified_profile("923609016", "EQUINOR ASA", "https://www.equinor.com/", careers=careers))
        claims = available(env, "hiring_signal")
        self.assertEqual([c["value"] for c in claims], ["https://www.equinor.com/careers"])
        self.assertEqual(claims[0]["kind"], "careers_page")
        ev = {e["id"]: e for e in env["evidence"]}[claims[0]["evidence_ids"][0]]
        self.assertEqual(ev["source_url"], "https://www.equinor.com/careers")

    def test_hiring_signal_adds_each_posting_after_the_careers_page(self):
        careers = {"url": "https://www.equinor.com/careers", "content_sha256": HASH_PAGE, "retrieved_at": T, "claim_span": "Careers in Equinor"}
        posting = {"title": "Process engineer", "url": "https://www.equinor.com/careers/jobs/123", "platform": "company_site",
                   "source_page": "https://www.equinor.com/careers", "content_sha256": HASH_PAGE, "retrieved_at": T, "claim_span": "Process engineer"}
        env = envelope(verified_profile("923609016", "EQUINOR ASA", "https://www.equinor.com/", careers=careers, postings=[posting]))
        claims = available(env, "hiring_signal")
        self.assertEqual([c["kind"] for c in claims], ["careers_page", "job_posting"])
        self.assertEqual(claims[1]["value"], "https://www.equinor.com/careers/jobs/123")
        self.assertEqual(claims[1]["title"], "Process engineer")

    def test_dated_news_sunnaas_title_and_timestamp(self):
        url = ("https://www.sunnaas.no/fag-og-forskning/kompetansesentre-og-tjenester/regional-kompetansetjeneste-for-"
               "rehabilitering-rkr/nyheter-rkr/bedre-sosial-funksjon-etter-hjerneskade/")
        item = {"title": "Bedre sosial funksjon etter hjerneskade", "url": url, "published_date": "2025-09-22",
                "published_at": "2025-09-22T20:00:00+02:00", "date_source": "meta_published_time", "source_page": url,
                "content_sha256": HASH_PAGE, "retrieved_at": T, "claim_span": "Bedre sosial funksjon etter hjerneskade"}
        env = envelope(verified_profile("883971752", "SUNNAAS SYKEHUS HF", "https://www.sunnaas.no/", news=[item]))
        claims = available(env, "dated_news")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["value"].lower(), "bedre sosial funksjon etter hjerneskade (2025-09-22t20:00:00+02:00)")
        self.assertEqual((claims[0]["url"], claims[0]["source_url"]), (url, url))

    def test_official_website_elopak_domain(self):
        env = envelope(verified_profile("811413682", "ELOPAK ASA", "https://www.elopak.com/"))
        claims = available(env, "official_website")
        self.assertEqual(len(claims), 1)
        self.assertEqual(urllib.parse.urlparse(claims[0]["value"]).hostname.removeprefix("www."), "elopak.com")

    def test_every_family_has_an_explicit_state_without_a_website(self):
        profile = verified_profile("811413682", "ELOPAK ASA", "https://www.elopak.com/")
        profile["evidence"]["website"] = {"status": "not_found", "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/811413682", "retrieved_at": T}
        profile["web_claims"] = {}
        env = envelope(profile)
        for field in WEB_FIELDS:
            states = [c["availability"] for c in env["claims"] if c["field"] == field]
            self.assertEqual(states, ["not_available"], field)


class Normalization(unittest.TestCase):
    def test_social_value_lowercases_handles_but_not_youtube_channel_ids(self):
        self.assertEqual(social_profile_value("https://facebook.com/MtmSkogservice/"), "https://facebook.com/mtmskogservice")
        self.assertEqual(social_profile_value("https://www.linkedin.com/company/AF-Gruppen"), "https://linkedin.com/company/af-gruppen")
        self.assertEqual(social_profile_value("https://youtube.com/channel/UCWQ6axV2SNSqhA0JVoTZk-w"), "https://youtube.com/channel/UCWQ6axV2SNSqhA0JVoTZk-w")

    def test_published_at_keeps_the_source_timestamp(self):
        self.assertEqual(published_at("2025-09-22T20:00:00+02:00", "2025-09-22"), "2025-09-22T20:00:00+02:00")
        self.assertEqual(published_at("Mon, 22 Sep 2025 20:00:00 +0200", "2025-09-22"), "2025-09-22T20:00:00+02:00")
        self.assertEqual(published_at("2025-09-22T18:00:00.069Z", "2025-09-22"), "2025-09-22T18:00:00.069Z")
        self.assertEqual(published_at("22. september 2025", "2025-09-22"), "2025-09-22")
        self.assertEqual(published_at("2025-09-23T01:00:00+02:00", "2025-09-22"), "2025-09-22")

    def test_careers_heading_needs_careers_words(self):
        self.assertEqual(careers_heading(BeautifulSoup("<title>x</title><h1>Careers in Equinor</h1>", "lxml")), "Careers in Equinor")
        self.assertEqual(careers_heading(BeautifulSoup("<title>Ledige stillinger - Granne</title><h1>Om oss</h1>", "lxml")), "Ledige stillinger - Granne")
        self.assertIsNone(careers_heading(BeautifulSoup("<title>Prosjekter</title><h1>Våre prosjekter</h1>", "lxml")))


if __name__ == "__main__":
    unittest.main()
