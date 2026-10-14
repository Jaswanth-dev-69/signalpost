# v5 submission email (draft)

Send to `submit@builderr.ai`. `<HASH>` is the commit on `main` that contains the v5 smoke test;
`<CONTACT EMAIL>` is filled in when sending and is left out of this public repository on purpose.
Nothing below has been sent.

---

**To:** submit@builderr.ai
**Subject:** Signalpost revision 5 (final) — Jaswanth — commit `<HASH>`

Hi,

Signalpost revision 5, the last of our five versions (v1 `31cf2983`, v2 `0ded7110`, v3 `6074351`,
v4 `956f53be`).

- **Agent name:** Signalpost research agent (board entry: Jaswanth)
- **Repository URL:** https://github.com/Jaswanth-dev-69/signalpost
- **Exact commit hash:** `<HASH>`
- **100-company smoke-test result:** `docs/smoke-test/` at that commit: README with the results, the run
  report, the 100 envelopes, the exact input list and the run's viewer (`smoke-viewer.html`, open it
  in any browser). Produced from a fresh clone of that commit into an empty directory with an empty
  package cache: install step only, then the one command.
- **One-command run instruction:**

  ```bash
  uv sync && uv run python run_agent.py --organisations <in> --output <out>
  ```

  Optional `--bulk <snapshot>` passes your frozen BRREG snapshot (gzip or plain CSV); without it the
  agent downloads the snapshot itself inside its time budget. `uv run signalpost` and the kit's
  `uv run python scripts/run_competition_batch.py` run the same agent and write the same envelopes.
  Next to `<out>` the agent writes `.profiles.jsonl`, `.report.json` and `.viewer.html` (the UI).
- **Models / APIs / licences:** no LLM and no model key, no paid or personal API credentials, no
  search engine, no LinkedIn/Meta/Glassdoor/Indeed/Google access. Sources: Brønnøysundregistrene
  Enhetsregisteret (bulk + API) and Regnskapsregisteret, NAV's public job-vacancy feed and ad pages
  (all NLOD open data), and each company's own website — robots.txt honoured per origin, honest
  identifying user agent, no browser emulation, no captcha or paywall bypass. Dependencies pinned in
  `uv.lock`. Details in `docs/SOURCES_AND_SAFETY.md`.
- **Expected cost per official run:** $0 third-party cost.
- **Contact for results:** <CONTACT EMAIL>

## What changed since v4

1. **A summary that explains the company, what changed and what is unknown.** Every envelope now
   opens with `summary` (also the first claim, `summary_profile`, and `profile.synthesis_summary`):
   *In brief*, what it does (register industry with its NACE division in English, the registered
   activity text, the verified website's own description), size and finances, **what changed**
   (movements between twelve-month accounting periods, role changes in the register ranked chief
   executive > board > others, name changes, the newest dated item on its website, and the comparison
   with the previous run), leadership and locations, web presence, hiring, dated activity, and
   **what is not known**. Numbered sources follow every sentence; each source lists the evidence ids
   it stands for. Every date, amount, quote, URL and name in a summary matches a published claim
   (`eval/synthesis_validator.py`; 600/600 on our test sets). Parent-only accounts, part-year periods,
   negative equity and template posts are labelled as such.
2. **A viewer for finding, comparing and verifying, on desktop and phone.** `<out>.viewer.html` is
   built from the envelopes: search by name, organisation number, place, industry (Norwegian or
   English), activity or person; filters and tiles (accounts, website, social, news, hiring, changed in
   the last 90 days); compare up to four companies (CSV, share link, cards on a phone); each profile
   with the brief, key metrics and a revenue trend, three years of accounts, a dated timeline, and an
   evidence table with the quoted span, fetch time and content hash for every claim. A 1,200-company
   viewer is 13 MB and opens in under a second.
3. **More register facts from the responses already fetched:** the registered business activity
   (the register's own lines), former names, the two earlier years of the accounts response
   (`financial_history`) and, for groups, the group (konsern) accounts (`group_financials`, with
   `group_accounts` listing the years). Every figure is quoted as a value literal that is verbatim in
   both the JSON and the XML representation of the accounts API.
4. **News and hiring items carry title, direct URL, publication date and organisation number** in the
   claim, the observation record and `external.company_site`. An item read from a feed or listing now
   cites its own article page when that page shows the title (the date stays quoted from the feed or
   listing). Tracking parameters are stripped from item URLs; category/section pages, site-name titles
   and pages stamped with the fetch time are no longer published as news; and the news listing pages
   that produced items also appear in the kit profile's bounded `pages`.

Checks on the submitted code: unit tests pass; schema validator 0 errors; claim audit 0 issues; a
100-claim precision audit 100/100 supported with **0 wrong-company publications**; evidence spans
verbatim on re-fetch (accounts 4,469/4,469 in both JSON and XML; external claims 99.9% one-node over
1,844 items); a 35-company wrong-company red team 0 false positives; the same batch run twice gives 0
duplicates and 0 change events; a forced hard deadline still writes every envelope, summary and the
viewer; a real 1,200-company run completed in 553 s with 0.9 GB peak memory.

One question, if you have a moment: which shape do you read for dated news and hiring (the claims,
`external.observations`, `external.company_site`, or the kit profile's `pages`)? Every shape carries
the same facts.

Thanks,
Jaswanth
