# v5 state (final revision)

Started 14 Oct 2026 18:31 IST from `main` = `956f53be` (tag `pre-v5`, pushed). Deadline for the
final push and report: 17 Oct 18:00 IST. Evidence (30.00) is the invariant: identity gate
unchanged, 0 wrong-company, red team 0/35, every span verbatim, every fact with evidence.

Scoring context (user): C300 directional estimate Recall 14.34, Evidence 30.00, Synthesis 7.20,
UX 2.67 (54.21). Board (5 Oct): v2 Synthesis 12 and UX 8. Board grades are multiples of 2.4
(Synthesis, five levels) and 1.6 (UX); 7.20 is level 3 of 5. Soham: "No dated-news item matched the
verified pool. Capture title, direct URL, publication date and exact company match."

Rubric wording (re-fetched 14 Oct, unchanged): Synthesis "explain what the company does, what
changed and what remains unknown, with sources for its conclusions" / "explain the company, changes
and unknowns without making unsupported claims". UX "find, compare and verify company information
on desktop and mobile".

Sets: `sample-100` (Builderr public sample), `proxy-200` (seed 20261004), `set-300` (new,
`fixture_proxy` seed 20261014; 2 overlaps with proxy-1200).

## WS-A Synthesis and UX

### Forensics (v2 `0ded711`, v3 `6074351`, main `956f53b`, same companies, same day)

| Finding | Data |
|---|---|
| Summary code unchanged v2 → main | `synthesis.py` identical; summary text identical for 90/100 sample companies (the 10 differ by data only) |
| (a) v3 withdrew websites/socials, so summaries carry fewer facts | verified websites v2 → main: proxy-200 53 → 44, set-300 100 → 85; social links shown in the viewer: proxy-200 79 → 41. These were precision fixes (Evidence 24.99 → 30.00) and stay withdrawn |
| Envelope grew; summary buried | 17 KB (v2) → 58 KB (main) per company; `summary_profile` was the last claim, after up to 20 news claims and the embedded kit profile |
| (b) viewer built from raw profiles | news, hiring and the summary never reached the viewer; header and tiles hard-coded "100-company showcase · 22 exact LinkedIn profiles", "0 exact LinkedIn profiles", "0 public posts + jobs"; lab wording ("POC diagnostic", slices); no compare view; on a phone the hero filled the first screen |
| (d)/(e) summary content | one templated paragraph: no "what changed", no per-sentence sources (the claim cited all evidence ids), Norwegian labels unexplained, sparse companies got a registry-only paragraph |

### Changes

- `synthesis.py`: `envelope_summary` builds the summary from the envelope's own published claims
  after refresh: Company, What it does (register industry and activity text, verified site's own
  description), Size and finances, **What changed** (movements between the reported years, latest
  role updates, former names, newest dated item, refresh result or "first snapshot"), Leadership and
  locations, Online presence, Hiring, Recent activity, **Not known or not established**, Sources.
  Numbered markers per sentence; each source lists its evidence ids. The claim moves to the front of
  `claims`, is mirrored in a top-level `summary` and `profile.synthesis_summary`; the profile-level
  summary remains the fallback (deadline flush, errors).
- Deliberate contract additions (same fetched records, no extra requests, appended after all earlier
  claims so earlier evidence ids do not move): `registered_activity` (register `aktivitet` text),
  `former_names` (`historiskeNavn`), `financial_history` (earlier years of the accounts response;
  every figure cited by a value-literal span with the year's end date as `effective_at`).
- `viewer.py` (new; `scripts/build_prototype.py` stays the kit's lab viewer): built from envelopes.
  Search (name, org number, place, industry, activity, role holder), filter tiles and filters, sort
  by revenue/growth/employees/news, saved searches, compare up to four (table, CSV, share link), deep
  links `#org=`, summary with linked sources, three-year financials with change, leadership,
  locations, web/social, hiring, news, changes, quick questions, evidence table (span, URL, fetch
  time, SHA-256), export JSON. Mobile: list → profile → back; tables scroll inside their box.
- `eval/frozen_guard.py` is now the regression guard: same saved profiles built with `pre-v5` and
  the working tree; only the summary and the listed additions may differ.
- `eval/synthesis_validator.py`: every date, amount, employee count, URL and quote in a summary must
  match an available claim; markers must resolve to sources whose evidence ids exist.

### Push gate for WS-A (code `7974893`; live runs `v5a` of 14 Oct, same code apart from the summary's evidence-id list)

| Check | Result |
|---|---|
| Unit tests | 171 pass (157 + 14 new) |
| Schema validator | 0 errors on sample-100, proxy-200, set-300 |
| Claim audit | 0 issues (all three sets) |
| Summary traceability (`eval/synthesis_validator.py`) | 100/100, 200/200, 300/300 |
| Regression guard on live profiles (`--new 7974893 --base pre-v5`) | clean on 600 companies; additions only: `registered_activity` 599, `financial_history` 1,094, `former_names` 200 |
| precision_audit (100 claims, sample-100) | 99/100 supported, **0 wrong-company**, 17/17 web spans on the page (the 1: homepage that does not print its own URL, as in v4) |
| evidence_audit (100 claims, 163 items) | 99.4% spans verbatim (1 dated-news time string no longer on a live blog page) |
| Span census of the new evidence (live re-fetch) | `registered_activity` 100/100, `former_names` 90/90, `financial_history` 1,123/1,123 (raw, node, visible); accounts spans 4,089/4,089 also under a browser-style Accept (XML). Only failures: frozen bulk-snapshot rows compared with today's dump (pre-existing) |
| Red team | 0/35 false positives |
| Determinism pair (proxy-200 twice into one file) | 0 duplicates, 0 change events, refresh 200 compared / 0 material; non-summary claims identical for 200/200; the second run's summaries say "No material change was found compared with the previous run on 2026-10-14" |
| Viewer, headless Chrome | 0 errors; ready 0.24 s (100) and 0.61 s (1,500 replicated, 20.6 MB); compare, deep link, mobile list → profile → back, no page-level horizontal scroll |
| Runtime, 1,500 projection (summed latency scaled from v3's measured 990 s) | v5a 1,154 s (proxy-200), 1,171 s (set-300), 1,198 s (sample-100); main 1,135 / 1,141 / 1,210 s. Below the 1,300 s reject line |

Coverage of external families is unchanged by WS-A (same profiles give the same claims; between two
live runs an hour apart the families move by ±2 companies per 300, which is the crawl noise floor).

| Run (companies / facts) | website | social | news | hiring |
|---|---|---|---|---|
| v2 sample-100 | 72/72 | 42/104 | 34/217 | 3/4 |
| v3 sample-100 | 63/63 | 33/72 | 30/206 | 15/19 |
| main sample-100 | 71/71 | 40/84 | 35/391 | 20/24 |
| v5a sample-100 | 71/71 | 40/84 | 35/391 | 20/24 |
| v2 proxy-200 | 53/53 | 31/79 | 28/193 | 3/5 |
| main proxy-200 | 44/44 | 21/41 | 22/276 | 16/17 |
| v5a proxy-200 | 44/44 | 21/41 | 21/256 | 16/17 |
| v2 set-300 | 100/100 | 60/120 | 33/208 | 6/27 |
| main set-300 | 85/85 | 47/90 | 29/310 | 17/43 |
| v5a set-300 | 83/83 | 45/86 | 29/310 | 15/41 |

### Checks during development (offline, saved profiles of 14 Oct runs)

| Check | Result |
|---|---|
| Regression guard vs `pre-v5` | clean on sample-100 and proxy-200 (300 profiles) |
| Summary traceability | 300/300 |
| Unit tests | 157 + 13 new pass |
| Headless browser, 100 companies | 0 console/page errors, ready 0.24 s, profile < 70 ms, compare/deep link/mobile flow pass |
| Headless browser, 1,500 companies | 20.6 MB (rich sample replicated), ready 0.61 s desktop / 0.50 s mobile emulation, all checks pass; random population 9.5 KB/company |
