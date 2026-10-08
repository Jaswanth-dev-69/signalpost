# v4 submission email (draft)

Send to `submit@builderr.ai`. `<HASH>` is filled in during the final packaging step, after the v4
commit is on the repository's default branch; `<CONTACT EMAIL>` is left out of this public repo on
purpose. Nothing below has been sent.

---

**To:** submit@builderr.ai
**Subject:** Signalpost revision 4 — Jaswanth — commit `<HASH>`

Hi,

Signalpost revision 4 (version 4 of five; v1 `31cf2983`, v2 `0ded7110`, v3
`6074351476c4a005aed246f5f6eb7c7adb28244d`).

- **Agent name:** Signalpost research agent (board entry: Jaswanth)
- **Repository URL:** https://github.com/Jaswanth-dev-69/signalpost
- **Exact commit hash:** `<HASH>`
- **100-company smoke-test result:** `docs/smoke-test/` at that commit (run report, envelopes and the
  exact input list). Re-verified for this revision from a fresh clone of that commit into an empty
  directory with an empty package cache: install step only, then the one command — 100/100 terminal
  envelopes, exit 0, schema validator 0 errors.
- **One-command run instruction:**

  ```bash
  uv sync && uv run python run_agent.py --organisations <in> --output <out>
  ```

  Optional `--bulk <snapshot>` passes your frozen BRREG snapshot (gzip or plain CSV); without it the
  agent downloads the snapshot itself inside its time budget. `uv run signalpost` and the kit's
  `uv run python scripts/run_competition_batch.py` are wrappers around the same agent and write the
  same envelopes, so any of the three is safe to run (this is question 1 below).
- **Models / APIs / licences:** no LLM and no model key, no paid or personal API credentials, no
  search engine, no LinkedIn/Meta/Glassdoor/Indeed/Google access. Sources: Brønnøysundregistrene
  Enhetsregisteret (bulk + API) and Regnskapsregisteret, NAV's public job-vacancy feed and ad pages
  (all NLOD open data), and each company's own website — robots.txt honoured per origin, honest
  identifying user agent, no browser emulation, no captcha or paywall bypass. Dependencies pinned in
  `uv.lock`. Details in `docs/SOURCES_AND_SAFETY.md`.
- **Expected cost per official run:** $0 third-party cost.
- **Contact for results:** `<CONTACT EMAIL>`

## What changed since v3

1. **Verbatim single-node evidence spans.** Every `claim_span` is a verbatim fragment of one text
   node or attribute of the page it cites; spans we had composed ourselves (the NAV vacancy-index check,
   websites held back as `ambiguous`, checked news listings) are gone. Annual-accounts spans are now the
   value as printed (`288000.00`, `2024-12-31`), so they match whether a verifier gets the JSON
   (`Accept: */*`) or the XML (browser-style `Accept`) that the Regnskapsregisteret API negotiates, and
   the filing year cites the live Enhetsregisteret record instead of the 150 MB bulk file. Registry and
   accounts evidence re-found verbatim under a browser-style Accept: 61% → **100%** (9,903 items).
2. **Effective dates on news and postings.** Each dated-news evidence item carries the article's own
   published timestamp as `effective_at`; each job posting carries its posted date where the source
   states one, alongside the reporting periods on financial claims.
3. **News listing pagination.** A news listing that shows fewer items than our per-company cap is
   followed to its own second page (and a WordPress feed to its second page), each item still read
   from its own article page: dated-news facts **+80%** on our 200-company benchmark and **+63%** on the
   100 companies of your public product sample, with company coverage unchanged.
4. **The same news and hiring facts in your observation format.** Besides one `dated_news` /
   `hiring_signal` claim per fact, each envelope now carries `external.observations` — one record per
   news item (`signal_type: public_post`) and per careers page or posting (`job_posting`) in the
   starter kit's `external_footprint` schema (all pass its `validate_observation`) — and
   `external.company_site.{posts,jobs}` in the layout of your sample's `external.linkedin` block. These
   are the same identity-gated facts with the same evidence, not additional ones; please read whichever
   shape your scorer uses.
5. **Robustness and refresh correctness.** Careers pages crawled before news, careers discovery to
   depth 2 plus sitemap, `Accept: */*` retry on HTTP 406, one retry for homepage timeouts/429/5xx,
   401/403 reported as `blocked`, news cap 10 → 20. A website discovery that stopped on a transient
   error is now marked incomplete, so a later run never reports that site's facts as new or removed
   (this removed the only false changes we saw when running the same batch twice).
6. **No change to synthesis or UX.** Neither the synthesis nor the viewer code was touched (a guard
   script checks every commit); on 200 companies the summary text is identical to v3.

Checks on the submitted commit: unit tests pass; schema validator 0 errors; the same batch run twice
gives 0 duplicate records and 0 change events; a 100-claim precision audit is 99/100 supported with
**0 wrong-company publications** (the exception is an audit heuristic: the homepage does not print its
own URL; the company match is confirmed); evidence spans 100% verbatim on re-fetch; a 35-company
wrong-company red team 0 false positives; a 1,500-company run projects to about 1,020–1,160 s.

## Open questions

These are the choices we cannot settle from the published contract. A one-word answer is enough for
most, and each one decides something specific for us.

1. **Which command did you run for our v2?** Our README still showed the kit's
   `scripts/run_competition_batch.py`; our submission email gave
   `uv run python run_agent.py --organisations <in> --output <out>`. Which one produced the scored run?
2. **Which part of the envelope does the scorer read for external facts?** (a) the `claims` list in the
   `OUTPUT_CONTRACT.md` shape (`field`, `value`, `availability`, `evidence_ids`), (b) the kit's
   `profile.evidence.website.value` record (`final_url`, `social_links`, `identity_assessment`), or
   (c) both. If both carry the same fact, is it counted once?
3. **Claim field names.** Which `field` values are recognised for company website, social profile,
   dated news and hiring signal? Ours are `official_website`, `social_profile`, `dated_news` and
   `hiring_signal`. Is a repeated `field` (one claim per profile, article or posting) read, or must a
   family be one claim with a list `value`?
4. **Value normalization for matching.** Your v2 feedback showed `elopak.com`,
   `facebook.com/mtmskogservice`, `https://www.equinor.com/careers` and
   `bedre sosial funksjon etter hjerneskade (2025-09-22t20:00:00+02:00)`. Are values matched after
   lower-casing and stripping scheme and `www`? Is a news item matched on title + datetime, on the
   article URL, or on either? Is a careers-page URL a hiring fact on its own, with no posting needed?
5. **Which external field families feed the 50 recall points, and with what weights?** Do *company
   description*, *leadership* (registry roles), *locations* (registry subunits) or *financials* count
   toward Recall, or only toward Evidence and precision?
6. **Company website when on-page identity is weak.** The kit reports the registry-linked homepage as
   `status: available` with `identity_assessment.publishable: false` when the name is not proven on
   the page (for example a JavaScript-only homepage). Does the scorer count such a record as a
   published website fact? If yes, is it counted against precision when it is correct? Our own
   reconstruction of the board only reproduces the published kit and v2 scores when it does count,
   so the answer changes how we report those sites.

Thanks,
Jaswanth

---

## Not in the email (kept for the packaging step)

- `<HASH>`: the commit on `main` that contains the v4 smoke test (`docs/smoke-test/README.md` names
  the code commit it was run from; later commits differ from it only in `docs/`).
- `<CONTACT EMAIL>`: filled in when sending; deliberately not committed to this public repository.
- Questions 7–17 in `docs/QUESTIONS_FOR_BUILDERR.md` are not in this email. The most valuable
  omissions are Q7 (which evidence checks cost the missing points), Q15 (the accounts API answers XML
  to a browser-style `Accept` while our spans quote the JSON we fetched and hashed) and Q17 (whether
  our per-fact `dated_news` and `hiring_signal` claims are read at all, worth an estimated 10–18
  recall points). Q16 is folded into question 6 above.
