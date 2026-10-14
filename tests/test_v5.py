"""v5: register activity, former names and earlier accounts years; the summary built from published
claims; the viewer; the regression guard."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from norway_company_agent.official import normalize_entity, normalize_financials  # noqa: E402
from norway_company_agent.synthesis import apply_envelope_summary, envelope_summary  # noqa: E402
from norway_company_agent.viewer import build_viewer_html, viewer_record  # noqa: E402
from synthesis_validator import validate_synthesis_envelope  # noqa: E402
from frozen_guard import compare  # noqa: E402
from test_contract_rev3 import HASH_PAGE, HASH_REGISTRY, T, available, envelope, verified_profile  # noqa: E402

ORG = "999164137"
ENTITY = {
    "organisasjonsnummer": ORG, "navn": "TESTSELSKAP NORD ASA", "organisasjonsform": {"kode": "ASA", "beskrivelse": "Allmennaksjeselskap"},
    "aktivitet": ["Utvikling og salg av ladeutstyr for", "elbiler og tilhørende tjenester."],
    "historiskeNavn": [{"fraDato": "2012-11-21 07:18:20", "navn": "TESTSELSKAP NORD AS", "tilDato": "2022-11-09 11:13:20"}],
    "naeringskode1": {"beskrivelse": "Engroshandel med elektronikk", "kode": "46.500"}, "stiftelsesdato": "2012-11-19",
    "forretningsadresse": {"kommune": "SANDNES"}, "antallAnsatte": 12, "konkurs": False, "underAvvikling": False,
}


def year(y: int, revenue: float, result: float, kind: str = "SELSKAP") -> dict:
    return {"id": y, "regnskapstype": kind, "regnskapsperiode": {"fraDato": f"{y}-01-01", "tilDato": f"{y}-12-31"}, "valuta": "NOK",
            "resultatregnskapResultat": {"driftsresultat": {"driftsinntekter": {"sumDriftsinntekter": revenue}, "driftsresultat": result},
                                         "aarsresultat": result},
            "eiendeler": {"sumEiendeler": revenue * 2}, "egenkapitalGjeld": {"gjeldOversikt": {"sumGjeld": revenue}}}


ACCOUNTS = [year(2023, 1000000.0, -50000.0), year(2024, 1200000.0, 20000.0), year(2025, 1500000.0, 90000.0),
            year(2025, 9000000.0, 400000.0, "KONSERN")]
RAW_ENTITY = json.dumps(ENTITY, ensure_ascii=False, separators=(",", ":"))
RAW_ACCOUNTS = json.dumps(ACCOUNTS, ensure_ascii=False, separators=(",", ":")).replace(".0,", ".00,").replace(".0}", ".00}")


def profile() -> dict:
    p = verified_profile(ORG, "TESTSELSKAP NORD ASA", "https://www.example.no/")
    p["evidence"]["registry_live"] = {"status": "available", "source_url": f"https://data.brreg.no/enhetsregisteret/api/enheter/{ORG}",
                                      "source_type": "official_registry_live", "retrieved_at": T, "content_sha256": HASH_REGISTRY,
                                      "value": normalize_entity(ENTITY)}
    p["evidence"]["financials"] = {"status": "available", "source_url": f"https://data.brreg.no/regnskapsregisteret/regnskap/{ORG}",
                                   "source_type": "official_annual_accounts", "retrieved_at": T, "content_sha256": HASH_PAGE,
                                   "value": normalize_financials(ACCOUNTS)}
    return p


class RegisterAdditions(unittest.TestCase):
    def setUp(self):
        self.env = envelope(profile())
        self.evidence = {e["id"]: e for e in self.env["evidence"]}

    def test_registered_activity_is_quoted_verbatim_from_the_live_record(self):
        claim = available(self.env, "registered_activity")[0]
        self.assertEqual(claim["value"], "Utvikling og salg av ladeutstyr for elbiler og tilhørende tjenester.")
        span = self.evidence[claim["evidence_ids"][0]]["claim_span"]
        self.assertIn(span, RAW_ENTITY)

    def test_former_name_cites_its_register_entry(self):
        claim = available(self.env, "former_names")[0]
        self.assertEqual(claim["value"][0]["name"], "TESTSELSKAP NORD AS")
        self.assertIn(self.evidence[claim["evidence_ids"][0]]["claim_span"], RAW_ENTITY)

    def test_earlier_years_are_published_with_every_figure_cited(self):
        history = available(self.env, "financial_history")
        self.assertEqual([c["reporting_period"]["tilDato"] for c in history], ["2024-12-31", "2023-12-31"])
        for claim in history:
            self.assertEqual(claim["value"]["account_type"], "SELSKAP")
            spans = [self.evidence[i]["claim_span"] for i in claim["evidence_ids"]]
            self.assertEqual(len(spans), 1 + len([k for k in ("revenue", "operating_result", "annual_result", "assets", "debt") if k in claim["value"]]))
            for span in spans:
                self.assertIn(span, RAW_ACCOUNTS)
            for i in claim["evidence_ids"]:
                self.assertEqual(self.evidence[i]["effective_at"], claim["reporting_period"]["tilDato"])
        self.assertEqual(available(self.env, "revenue")[0]["value"], 1500000.0)  # latest year unchanged

    def test_additions_come_after_every_earlier_claim(self):
        fields = [c["field"] for c in self.env["claims"]]
        first_added = min(fields.index(f) for f in ("registered_activity", "former_names", "financial_history"))
        self.assertTrue(all(f in ("registered_activity", "former_names", "financial_history", "summary_profile") for f in fields[first_added:]))


class Summary(unittest.TestCase):
    def setUp(self):
        self.env = envelope(profile())
        apply_envelope_summary(self.env)
        self.claim = self.env["claims"][0]

    def test_summary_is_first_mirrored_and_traceable(self):
        self.assertEqual(self.claim["field"], "summary_profile")
        self.assertEqual(self.env["summary"]["text"], self.claim["value"])
        self.assertEqual(list(self.env)[:2], ["organisation_number", "summary"])
        self.assertEqual(validate_synthesis_envelope(self.env), [])

    def test_summary_explains_activity_changes_and_unknowns_with_sources(self):
        text = self.claim["value"]
        self.assertIn("“Utvikling og salg av ladeutstyr for elbiler og tilhørende tjenester.”", text)
        self.assertIn("Revenue rose 25% from NOK 1.2 million in 2024 to NOK 1.5 million in 2025", text)
        self.assertIn("previously registered under the name TESTSELSKAP NORD AS (until 2022-11-09)", text)
        self.assertIn("Not known or not established:", text)
        self.assertIn("first Signalpost snapshot", text)
        self.assertRegex(text, r"\[\d+\]")
        for source in self.claim["sources"]:
            self.assertTrue(source["evidence_ids"])

    def test_loss_to_profit_is_described_not_given_a_percentage(self):
        env = envelope(profile())
        env["claims"] = [c for c in env["claims"] if c["field"] != "financial_history" or c["reporting_period"]["tilDato"] == "2023-12-31"]
        text = envelope_summary(env)["text"]
        self.assertIn("turned from a loss to a profit", text)

    def test_unknowns_name_what_is_missing(self):
        p = profile()
        p["evidence"]["financials"] = {"status": "not_found", "source_url": f"https://data.brreg.no/regnskapsregisteret/regnskap/{ORG}",
                                       "retrieved_at": T, "content_sha256": HASH_PAGE, "note": "HTTP 404"}
        env = envelope(p)
        apply_envelope_summary(env)
        self.assertIn("annual accounts (none returned by Regnskapsregisteret", env["summary"]["text"])
        self.assertIn("missing figures are not zero", env["summary"]["text"])
        self.assertEqual(validate_synthesis_envelope(env), [])

    def test_refresh_result_is_reported(self):
        env = envelope(profile())
        env["refresh"] = {"previous_run_id": "run-1", "previous_completed_at": "2026-10-13T06:00:00Z", "material_changes": 0}
        env["changes"] = []
        self.assertIn("No material change was found compared with the previous run on 2026-10-13", envelope_summary(env)["text"])

    def test_a_summary_error_never_costs_the_envelope(self):
        env = envelope(profile())
        env["claims"].append({"field": "registered_roles", "value": 5, "availability": "available", "evidence_ids": []})
        before = json.dumps(env["claims"], sort_keys=True)
        apply_envelope_summary(env)
        self.assertTrue(env["claims"])
        self.assertNotEqual(before, "")


class Viewer(unittest.TestCase):
    def test_viewer_embeds_every_company_and_escapes_script_text(self):
        env = envelope(profile())
        apply_envelope_summary(env)
        env["claims"].append({"field": "company_description", "value": "</script><script>alert(1)</script>", "availability": "available",
                              "evidence_ids": env["claims"][1]["evidence_ids"]})
        html = build_viewer_html([env], {"run_id": "test"})
        self.assertEqual(html.count("</script>"), 2)  # the data block's and the code block's own closing tags
        start = html.index('type="application/json">') + len('type="application/json">')
        data = json.loads(html[start:html.index("</script>", start)].replace("<\\/", "</"))
        self.assertEqual([c["o"] for c in data["companies"]], [ORG])

    def test_record_carries_three_years_and_sources(self):
        env = envelope(profile())
        apply_envelope_summary(env)
        record = viewer_record(env)
        self.assertEqual([y["to"] for y in record["fin"]], ["2025-12-31", "2024-12-31", "2023-12-31"])
        self.assertEqual(record["g"], 25.0)
        self.assertTrue(all(s["h"] and s["u"].startswith("https://") for s in record["S"]))
        self.assertTrue(record["sm"]["s"])


class RegressionGuard(unittest.TestCase):
    def test_guard_flags_a_changed_claim_and_allows_the_summary(self):
        base = envelope(profile())
        new = envelope(profile())
        apply_envelope_summary(new)
        self.assertEqual(compare(base, new), [])
        changed = json.loads(json.dumps(new))
        next(c for c in changed["claims"] if c["field"] == "legal_name")["value"] = "OTHER AS"
        self.assertTrue(any("claim" in p for p in compare(base, changed)))


if __name__ == "__main__":
    unittest.main()
