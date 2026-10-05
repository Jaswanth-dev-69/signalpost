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


class KitEnvelopeLayer(unittest.TestCase):
    """The starter kit's batch envelope is embedded unchanged next to the claims."""

    def test_envelope_carries_kit_fields_and_profile(self):
        profile = verified_profile("811730912", "MTM SKOGSERVICE AS", "https://mtmskogservice.no/")
        env = envelope(profile)
        for key in ("run_id", "state", "started_at", "completed_at", "modules", "profile", "claims", "evidence"):
            self.assertIn(key, env)
        self.assertIs(env["profile"], profile)
        self.assertEqual(env["modules"]["website"]["state"], "complete")
        self.assertEqual(env["modules"]["registry"]["state"], "complete")

    def test_external_handles_are_the_verified_site_links_only(self):
        social = [{"platform": "facebook", "url": "https://facebook.com/MtmSkogservice", "found_on_page": "https://mtmskogservice.no/"}]
        env = envelope(verified_profile("811730912", "MTM SKOGSERVICE AS", "https://mtmskogservice.no/", social=social))
        self.assertEqual(env["external"], {"handles": [{"platform": "facebook", "url": "https://facebook.com/MtmSkogservice",
                                                        "rightsStatus": "approved", "source_url": "https://mtmskogservice.no/"}]})
        self.assertNotIn("linkedin", env["external"])
        unverified = verified_profile("811730912", "MTM SKOGSERVICE AS", "https://mtmskogservice.no/", social=social)
        unverified["evidence"]["website"]["value"]["identity_assessment"]["publishable"] = False
        self.assertEqual(envelope(unverified)["external"], {"handles": []})

    def test_missing_module_after_deadline_is_budget_exhausted(self):
        profile = verified_profile("811730912", "MTM SKOGSERVICE AS", "https://mtmskogservice.no/")
        del profile["evidence"]["website"]
        profile["errors"] = [{"type": "DeadlineExceeded", "error": "deadline"}]
        env = envelope(profile)
        self.assertEqual(env["modules"]["website"]["state"], "budget_exhausted")
        self.assertEqual(env["state"], "complete")


class SocialGate(unittest.TestCase):
    def setUp(self):
        from norway_company_agent.identity import publishable_social_links
        self.gate = publishable_social_links

    def links(self, name: str, domain: str, urls: list[str]) -> list[str]:
        value = {"registered_domain": domain, "final_url": f"https://{domain}/",
                 "discovered_social_links": [{"platform": "x", "url": u} for u in urls]}
        return [item["url"] for item in self.gate({"name": name}, value)]

    def test_kit_name_gate_keeps_handles_naming_the_entity(self):
        self.assertEqual(self.links("MTM SKOGSERVICE AS", "mtmskogservice.no", ["https://facebook.com/MtmSkogservice"]),
                         ["https://facebook.com/MtmSkogservice"])

    def test_site_domain_label_in_handle_is_kept(self):
        self.assertEqual(self.links("ROSENBORG MURHÅNDTVERK AS", "murhandtverk.no", ["https://instagram.com/murhandtverk"]),
                         ["https://instagram.com/murhandtverk"])

    def test_other_organisations_people_and_posts_are_dropped(self):
        urls = ["https://linkedin.com/company/amexgas", "https://facebook.com/599407360228640_1552122909951569",
                "https://instagram.com/orsolyahaarberg"]
        self.assertEqual(self.links("RAGASCO AS", "ragasco.com", urls), [])

    def test_short_domain_label_is_not_enough(self):
        self.assertEqual(self.links("NORDIC SUPPLY PARTNER AS", "nsp.no", ["https://instagram.com/nspnorge"]), [])


class SharedDeclaredDomain(unittest.TestCase):
    def assessment(self, declarants):
        from norway_company_agent.identity import registry_declared_assessment
        profile = {"organisation_number": "999999999", "name": "EXAMPLE FUND", "website": "www.group.no"}
        if declarants is not None:
            profile["homepage_domain_registry_entities"] = declarants
        website = {"status": "available", "source_url": "https://www.group.no/", "value": {
            "final_url": "https://www.group.no/", "title": "Group", "main_text_excerpt": "x" * 200}}
        return registry_declared_assessment(profile, website)

    def test_sole_declarant_is_accepted(self):
        self.assertTrue(self.assessment(1)["publishable"])

    def test_domain_declared_by_several_entities_is_labelled_not_published(self):
        result = self.assessment(13)
        self.assertFalse(result["publishable"])
        self.assertEqual(result["relationship"], "shared_group_brand_or_provider_site")

    def test_gate_labels_the_shared_site_in_the_identity_verdict(self):
        from norway_company_agent.identity import apply_registry_declared_gate
        profile = {"organisation_number": "999999999", "name": "EXAMPLE FUND", "website": "www.group.no",
                   "homepage_domain_registry_entities": 13}
        website = {"status": "available", "source_url": "https://www.group.no/", "value": {
            "final_url": "https://www.group.no/", "title": "Group", "main_text_excerpt": "x" * 200,
            "identity_assessment": {"status": "related_or_uncertain", "publishable": False}}}
        self.assertFalse(apply_registry_declared_gate(profile, website))
        verdict = website["value"]["identity_assessment"]
        self.assertEqual((verdict["publishable"], verdict["relationship"], verdict["status"]),
                         (False, "shared_group_brand_or_provider_site", "related_or_uncertain"))

    def test_unknown_count_is_not_published(self):
        self.assertFalse(self.assessment(None)["publishable"])


class Refresh(unittest.TestCase):
    def pair(self, mutate=None):
        import copy
        from norway_company_agent.envelope_refresh import refresh_envelope
        news = [{"title": "Ny avtale", "published_at": "2025-09-22T20:00:00+02:00", "url": "https://ex.no/nyheter/a",
                 "source_page": "https://ex.no/nyheter/a", "retrieved_at": T, "content_sha256": HASH_PAGE, "claim_span": "Ny avtale"}]
        before = verified_profile("923609016", "EXAMPLE ASA", "https://ex.no/", news=news)
        before["evidence"]["financials"] = {"status": "available", "source_url": "https://data.brreg.no/regnskapsregisteret/regnskap/923609016",
                                            "retrieved_at": T, "content_sha256": "d" * 64, "value": {"records": [{"revenue": 10.0, "period": {"fraDato": "2025-01-01", "tilDato": "2025-12-31"}}]}}
        after = copy.deepcopy(before)
        if mutate:
            mutate(after)
        old = profile_to_contract_envelope(before, run_id="run-1", started_at=T, completed_at=T)
        new = profile_to_contract_envelope(after, run_id="run-2", started_at=T, completed_at=T)
        return refresh_envelope(new, old)

    def test_same_snapshot_gives_no_changes_and_no_duplicates(self):
        env = self.pair()
        self.assertEqual(env["changes"], [])
        self.assertEqual(env["refresh"]["previous_run_id"], "run-1")
        self.assertEqual(env["refresh"]["prior_evidence"], [])

    def test_new_filing_is_one_kit_shaped_change_and_old_evidence_is_kept(self):
        def mutate(p):
            p["evidence"]["financials"]["value"]["records"][0]["revenue"] = 12.0
            p["evidence"]["financials"]["content_sha256"] = "e" * 64
        env = self.pair(mutate)
        fields = [c["field"] for c in env["changes"]]
        self.assertIn("financials.records", fields)
        change = next(c for c in env["changes"] if c["field"] == "financials.records")
        self.assertEqual((change["old_content_sha256"], change["new_content_sha256"]), ("d" * 64, "e" * 64))
        self.assertTrue(any(e["content_sha256"] == "d" * 64 for e in env["refresh"]["prior_evidence"]))

    def test_failed_website_fetch_is_preserved_not_reported_as_removed(self):
        def mutate(p):
            p["evidence"]["website"] = {"status": "source_error", "source_url": "https://ex.no/", "retrieved_at": T, "note": "timeout"}
            p["web_claims"] = {}
        env = self.pair(mutate)
        self.assertEqual(env["changes"], [])
        self.assertIn("website", env["refresh"]["fields_not_refreshed"])
        self.assertTrue(any(c["field"] == "official_website" for c in env["refresh"]["preserved_claims"]))

    def test_new_article_is_an_added_claim_event(self):
        def mutate(p):
            p["web_claims"]["news"]["items"].append({"title": "Nytt bygg", "published_at": "2025-10-01T09:00:00+02:00", "url": "https://ex.no/nyheter/b",
                                                     "source_page": "https://ex.no/nyheter/b", "retrieved_at": T, "content_sha256": HASH_PAGE, "claim_span": "Nytt bygg"})
        env = self.pair(mutate)
        added = [c for c in env["changes"] if c["field"] == "claims.dated_news"]
        self.assertEqual(len(added), 1)
        self.assertEqual((added[0]["change_type"], added[0]["effective_at"]), ("added", "2025-10-01T09:00:00+02:00"))


if __name__ == "__main__":
    unittest.main()
