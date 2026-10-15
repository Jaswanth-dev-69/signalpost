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
        self.assertEqual(claim["value"], ["Utvikling og salg av ladeutstyr for", "elbiler og tilhørende tjenester."])
        for line in claim["value"]:
            self.assertIn(line, RAW_ENTITY)
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
        self.assertTrue(all(f in ("registered_activity", "former_names", "financial_history", "group_accounts", "group_financials", "summary_profile") for f in fields[first_added:]))

    def test_group_figures_are_published_with_every_figure_cited(self):
        claims = available(self.env, "group_financials")
        self.assertEqual([c["reporting_period"]["tilDato"] for c in claims], ["2025-12-31"])
        self.assertEqual(claims[0]["value"]["revenue"], 9000000.0)
        for i in claims[0]["evidence_ids"]:
            self.assertIn(self.evidence[i]["claim_span"], RAW_ACCOUNTS)

    def test_group_accounts_are_flagged_with_a_verbatim_span(self):
        claim = available(self.env, "group_accounts")[0]
        self.assertEqual(claim["value"], ["2025-12-31"])
        self.assertEqual(self.evidence[claim["evidence_ids"][0]]["claim_span"], "KONSERN")
        self.assertIn("KONSERN", RAW_ACCOUNTS)


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
        self.assertIn("In its own (parent-company) accounts, revenue rose 25% from NOK 1.2 million in 2024 to NOK 1.5 million in 2025", text)
        self.assertIn("Earlier names in the register: TESTSELSKAP NORD AS (until 2022-11-09)", text)
        self.assertIn("Not known or not established:", text)
        self.assertNotIn("Signalpost snapshot", text)
        self.assertIn("The group (konsern) accounts for 2025 report revenue of NOK 9.0 million", text)
        self.assertTrue(text.startswith("In brief: TESTSELSKAP NORD ASA is a public limited company (ASA)"))
        self.assertRegex(text, r"\[\d+\]")
        for source in self.claim["sources"]:
            self.assertTrue(source["evidence_ids"])

    def test_loss_to_profit_is_described_not_given_a_percentage(self):
        env = envelope(profile())
        env["claims"] = [c for c in env["claims"] if c["field"] != "financial_history" or c["reporting_period"]["tilDato"] == "2023-12-31"]
        text = envelope_summary(env)["text"]
        self.assertIn("turned from a loss of NOK 50 thousand in 2023 to a profit of NOK 90 thousand in 2025", text)

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
        self.assertIn("No material change was found compared with the previous check on 2026-10-13", envelope_summary(env)["text"])

    def test_refresh_changes_are_named_with_examples(self):
        env = envelope(profile())
        env["refresh"] = {"previous_run_id": "run-1", "previous_completed_at": "2026-10-13T06:00:00Z", "material_changes": 1}
        env["changes"] = [{"field": "claims.dated_news", "change_type": "added", "old_value": None, "new_value": "Ny avtale (2026-10-12)",
                           "source_url": "https://www.example.no/nyheter/ny-avtale"}]
        apply_envelope_summary(env)
        self.assertIn("1 material change was found (dated news), for example added dated news “Ny avtale (2026-10-12)”", env["summary"]["text"])
        self.assertEqual(validate_synthesis_envelope(env), [])

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


class ViewerScript(unittest.TestCase):
    @unittest.skipUnless(__import__("shutil").which("node"), "node is not installed")
    def test_viewer_script_parses(self):
        import subprocess
        import tempfile
        env = envelope(profile())
        apply_envelope_summary(env)
        html = build_viewer_html([env], {"run_id": "test"})
        script = html[html.rindex("<script>") + len("<script>"):html.rindex("</script>")]
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
            handle.write(script)
        result = subprocess.run(["node", "--check", handle.name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr[:500])


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


class SummaryRules(unittest.TestCase):
    """Round-2 review rules: ranked role changes, first registrations, comparable periods, junk posts."""

    def env_with(self, *claims: dict) -> dict:
        env = envelope(profile())
        ev = env["claims"][0]["evidence_ids"]
        for claim in claims:
            env["claims"].append({"availability": "available", "evidence_ids": ev, **claim})
        return env

    def role(self, name: str, code: str, group: str, stamp: str) -> dict:
        groups = {"DAGL": ("DAGL", "Daglig leder"), "LEDE": ("STYR", "Styre"), "REGN": ("REGN", "Regnskapsfører")}
        return {"name": name, "role_code": code, "role": {"DAGL": "Daglig leder", "LEDE": "Styrets leder", "REGN": "Regnskapsfører"}[code],
                "group_code": groups[code][0], "group": groups[code][1], "last_changed": stamp, "inactive": False}

    def test_a_new_chief_executive_outranks_a_newer_accountant_change(self):
        roles = [self.role("Kari Nordmann", "DAGL", "DAGL", "2025-06-01"), self.role("Regnskap AS", "REGN", "REGN", "2026-09-01"),
                 self.role("Ola Nordmann", "LEDE", "STYR", "2026-08-01")]
        text = envelope_summary(self.env_with({"field": "registered_roles", "value": roles}))["text"]
        changes = next(line for line in text.split("\n") if line.startswith("What changed"))
        self.assertIn("changes to the chief executive (daglig leder) on 2025-06-01 (now Kari Nordmann) and the board (styre) on 2026-08-01", changes)
        self.assertNotIn("Regnskap AS", changes)

    def test_roles_set_at_registration_are_not_changes(self):
        env = self.env_with({"field": "founded_date", "value": "2012-11-19"},
                            {"field": "registered_roles", "value": [self.role("Kari Nordmann", "DAGL", "DAGL", "2012-12-01")]})
        self.assertIn("The registered roles have not changed since the company was founded in 2012", envelope_summary(env)["text"])

    def test_part_year_periods_are_not_compared(self):
        env = envelope(profile())
        for claim in env["claims"]:
            if claim["field"] == "financial_history" and claim["reporting_period"]["tilDato"] == "2024-12-31":
                claim["value"]["period"] = {"fraDato": "2024-11-02", "tilDato": "2024-12-31"}
        text = envelope_summary(env)["text"]
        self.assertIn("The latest accounts (2025) and the previous ones (the 2-month period 2024-11-02 to 2024-12-31) cover periods of different length, so they are not compared", text)
        self.assertNotIn("rose 25%", text)

    def test_template_posts_stay_claims_but_not_news(self):
        post = {"field": "dated_news", "value": "Hello world! (2021-07-28)", "title": "Hello world!", "published_at": "2021-07-28", "url": "https://www.example.no/hello-world"}
        text = envelope_summary(self.env_with(post))["text"]
        self.assertNotIn("Hello world!”", text.split("Sources:")[0].replace("only template or test posts", ""))
        self.assertIn("its website shows only template or test posts", text)

    def test_careers_page_is_not_said_to_list_openings(self):
        page = {"field": "hiring_signal", "value": "https://www.example.no/jobb", "kind": "careers_page", "openings_listed": True}
        text = envelope_summary(self.env_with(page))["text"]
        self.assertIn("It has a careers page, https://www.example.no/jobb", text)
        self.assertNotIn("lists open positions", text)

    def test_activity_text_is_glossed_in_english(self):
        env = self.env_with({"field": "registered_activity", "value": ["Drift av barnehage og tilhørende virksomhet, herunder", "deltakelse i andre selskaper."]})
        env["claims"] = [c for c in env["claims"] if c["field"] != "registered_activity" or "barnehage" in str(c.get("value"))]
        text = envelope_summary(env)["text"]
        self.assertIn("in English, this text mentions kindergarten and owning shares in other companies", text)


def custom_year(y: int, revenue: float, operating: float, result: float, assets: float, debt: float) -> dict:
    return {"id": y, "regnskapstype": "SELSKAP", "regnskapsperiode": {"fraDato": f"{y}-01-01", "tilDato": f"{y}-12-31"}, "valuta": "NOK",
            "resultatregnskapResultat": {"driftsresultat": {"driftsinntekter": {"sumDriftsinntekter": revenue}, "driftsresultat": operating},
                                         "aarsresultat": result},
            "eiendeler": {"sumEiendeler": assets}, "egenkapitalGjeld": {"gjeldOversikt": {"sumGjeld": debt}}}


class SummaryRound5(unittest.TestCase):
    """Round-5 review rules: result wording, the brief's priorities, stale news, holding and
    pass-through companies, and how a website's identity is stated."""

    def env_for(self, accounts: list[dict], completed: str = "2026-10-14T00:00:00Z") -> dict:
        p = profile()
        p["evidence"]["financials"]["value"] = normalize_financials(accounts)
        env = envelope(p)
        env.setdefault("run", {})["completed_at"] = completed
        return env

    def test_losses_narrow_or_widen_and_profits_rise_or_fall(self):
        from norway_company_agent.synthesis import _result_move
        self.assertEqual(_result_move("Its", -100000, -40000, "2024"), "Its annual loss narrowed sharply from 2024")
        self.assertEqual(_result_move("Its", -100000, -350000, "2024"), "Its annual loss more than tripled from 2024")
        self.assertEqual(_result_move("Its", 100000, 250000, "2024"), "Its annual profit more than doubled from 2024")
        self.assertEqual(_result_move("Its", 100000, 300000, "2024"), "Its annual profit more than doubled from 2024")  # exactly tripled
        self.assertEqual(_result_move("The group's", 400000, 150000, "2024"), "The group's annual profit fell sharply from 2024")

    def test_brief_names_the_top_change_and_still_flags_negative_equity(self):
        env = self.env_for([custom_year(2024, 1000000.0, -200000.0, -200000.0, 900000.0, 800000.0),
                            custom_year(2025, 1100000.0, 150000.0, 150000.0, 500000.0, 800000.0)])
        brief = envelope_summary(env)["text"].split("\n")[0]
        self.assertIn("It swung from a loss in 2024 to a profit in 2025", brief)
        self.assertIn("Its equity is negative", brief)
        self.assertLess(brief.index("It swung"), brief.index("Its equity is negative"))

    def test_financial_items_name_the_year_and_partnerships_pay_no_entity_tax(self):
        env = self.env_for([custom_year(2024, 1000000.0, 100000.0, 80000.0, 900000.0, 400000.0),
                            custom_year(2025, 1100000.0, 150000.0, -60000.0, 900000.0, 400000.0)])
        text = envelope_summary(env)["text"]
        self.assertIn("In 2025, financial costs and tax of NOK 210 thousand turned an operating profit", text)
        next(c for c in env["claims"] if c["field"] == "legal_form")["value"] = "DA"
        text = envelope_summary(env)["text"]
        self.assertIn("In 2025, net financial costs of NOK 210 thousand turned an operating profit", text)
        self.assertNotIn("tax", text.split("Not known")[0].split("Size and finances")[1])

    def test_news_older_than_a_year_is_not_a_change_and_is_called_old(self):
        env = envelope(profile())
        env.setdefault("run", {})["completed_at"] = "2026-10-14T00:00:00Z"
        ev = env["claims"][0]["evidence_ids"]
        env["claims"].append({"field": "dated_news", "availability": "available", "evidence_ids": ev, "value": "Ny kontrakt med kommunen (2024-03-01)",
                              "title": "Ny kontrakt med kommunen", "published_at": "2024-03-01", "url": "https://www.example.no/nyheter/kontrakt"})
        text = envelope_summary(env)["text"]
        changed = next(line for line in text.split("\n") if line.startswith("What changed"))
        self.assertNotIn("Ny kontrakt", changed)
        self.assertIn("none is from the last twelve months", text)

    def test_a_zero_result_is_not_called_a_profit(self):
        env = self.env_for([custom_year(2024, 0.0, -16000.0, -16000.0, 20000.0, 5000.0), custom_year(2025, 0.0, 0.0, 0.0, 9500.0, 0.0)])
        text = envelope_summary(env)["text"]
        self.assertIn("Its latest accounts (2025) show an annual result of NOK 0 and no revenue", text)
        self.assertIn("an operating result of NOK 0 and an annual result of NOK 0", text)
        self.assertNotIn("profit of NOK 0", text)
        self.assertNotIn("swung", text)

    def test_event_posts_are_not_business_news(self):
        from norway_company_agent.synthesis import SEASONAL_NEWS
        for title in ("Møt oss på konferansen i Bergen", "Webinar: nye regler", "Investor Day 2026", "Velkommen til messe på Lillestrøm"):
            self.assertTrue(SEASONAL_NEWS.search(title), title)
        self.assertFalse(SEASONAL_NEWS.search("Ny kontrakt med Statens vegvesen"))

    def test_holding_company_names_the_unknown_shareholdings(self):
        env = envelope(profile())
        next(c for c in env["claims"] if c["field"] == "registered_activity")["value"] = ["Holdingselskap. Eie og forvalte aksjer i andre selskaper."]
        self.assertIn("which companies it holds shares in (shareholdings are not among the sources checked)", envelope_summary(env)["text"])

    def test_website_identity_is_stated_only_from_real_proof(self):
        env = envelope(profile())
        site = next(c for c in env["claims"] if c["field"] == "official_website")
        evidence = {e["id"]: e for e in env["evidence"]}
        for i in site["evidence_ids"]:
            evidence[i]["claim_span"] = "Hjemmeside"  # a menu label, not the register's homepage field
        online = next(line for line in envelope_summary(env)["text"].split("\n") if line.startswith("Online presence"))
        self.assertNotIn("homepage listed in the register", online)
        self.assertNotIn("names the company", online)
        evidence[site["evidence_ids"][0]]["claim_span"] = '"hjemmeside":"www.example.no"'
        online = next(line for line in envelope_summary(env)["text"].split("\n") if line.startswith("Online presence"))
        self.assertIn("it is the homepage listed in the register", online)


class ViewerRound5(unittest.TestCase):
    def test_search_covers_the_english_activity_terms(self):
        env = envelope(profile())
        next(c for c in env["claims"] if c["field"] == "registered_activity")["value"] = ["Drift av barnehage og tilhørende virksomhet, herunder", "deltakelse i andre selskaper."]
        apply_envelope_summary(env)
        self.assertEqual(viewer_record(env)["ag"], ["kindergarten", "owning shares in other companies"])
        html = build_viewer_html([env], {"run_id": "test"})
        self.assertIn("(x.ag||[]).join(' ')", html)

    def test_section_links_scroll_without_leaving_the_profile(self):
        html = build_viewer_html([envelope(profile())], {"run_id": "test"})
        self.assertIn("closest('a[href^=\"#s-\"],a.skip')", html)
        self.assertIn("if(/^#(s-[a-z]+|q)$/.test(location.hash))return;", html)


class FirstAccounts(unittest.TestCase):
    def env_for(self, founded: str, first: dict) -> dict:
        p = profile()
        p["evidence"]["financials"]["value"] = normalize_financials([first, year(2025, 1500000.0, 90000.0)])
        env = envelope(p)
        ev = env["claims"][0]["evidence_ids"]
        env["claims"] = [c for c in env["claims"] if c["field"] != "founded_date"]
        env["claims"].append({"field": "founded_date", "value": founded, "availability": "available", "evidence_ids": ev})
        return env

    def first_period(self, start: str, end: str) -> dict:
        y = year(2024, 300000.0, -20000.0)
        y["regnskapsperiode"] = {"fraDato": start, "tilDato": end}
        return y

    def test_first_accounts_starting_on_the_founding_day(self):
        text = envelope_summary(self.env_for("2024-09-16", self.first_period("2024-09-16", "2024-12-31")))["text"]
        self.assertIn("2025 was its first full accounting year; its first accounts covered only the 4-month period 2024-09-16 to 2024-12-31", text)

    def test_a_long_first_period_is_not_called_short(self):
        text = envelope_summary(self.env_for("2023-10-17", self.first_period("2023-10-17", "2024-12-31")))["text"]
        self.assertIn("2025 was its first twelve-month accounting year; its first accounts covered the 15-month period 2023-10-17 to 2024-12-31", text)

    def test_an_old_company_with_a_short_period_is_not_called_new(self):
        text = envelope_summary(self.env_for("2001-05-02", self.first_period("2024-07-01", "2024-12-31")))["text"]
        self.assertNotIn("first full accounting year", text)
        self.assertIn("cover periods of different length, so they are not compared", text)
