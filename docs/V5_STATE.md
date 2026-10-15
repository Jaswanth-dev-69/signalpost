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

## WS-B Recall

### Where the 14.34 comes from (`eval/scorer_mirror.py --anchors`)

With the four external families weighted equally, Recall = 12.5 × (sum of family coverages):

| Anchor | Recall | Sum of coverages | Website = social if news = hiring = 0 |
|---|---|---|---|
| v2 board (5 Oct) | 8.05 | 0.644 | 32.2% (v2's social was read as 0.0%, so website ≈ 64%) |
| kit-like entries (board) | 13.07 | 1.046 | 52.3% |
| C300 estimate (v3 or v4) | 14.34 | 1.147 | 57.4% |

So the C300 figure is explained by website and social alone at about 57% each, with news and
hiring scoring 0, which matches Soham's hint. Recall 20 needs the sum to reach 1.6: news or hiring
must start to match.

### Read path (kit code, our envelopes)

- The kit's company-site news extractor (`scripts/extract_company_site_news.py`) reads news only from
  the website record's bounded `pages` whose path has a `/news|press|aktuelt|nyheter|artikler|blog/`
  segment, one observation per company (deepest such page), `platform: company_site`,
  `signal_type: public_post`. Our profile `pages` held **0 news pages for every company** (0 of 35
  sample companies with news claims): our news comes from listings, feeds and articles fetched
  separately. Builderr's v1 feedback example of a dated-news fact was such a page
  (`https://www.bori.no/aktuelt`); the v2 example was a title + timestamp key.
- Builderr's own sample keeps posts and jobs under `external.linkedin` (we never label site items
  as LinkedIn). Our `external.observations` records pass the kit's `validate_observation`.
- Hiring: the kit has no company-site hiring reader; our careers pages and postings are claims,
  observations and `company_site.jobs`.

### Hypotheses (sized before coding; expected points are for the unknown read path)

| # | Hypothesis | Sizing (offline or light live sample) | Effort | Verdict |
|---|---|---|---|---|
| H1 | Organisation number on every news/hiring claim and `company_site` record ("exact company match") | shape only; all items | XS | build |
| H2 | News listing pages that produced published items added to the kit profile's `pages` (what the kit's reader sees) | 24/100 sample and 19/200 proxy companies; 14 and 12 on a kit news path | S | build |
| H3 | Items cited by a feed/listing cite their own article page when it shows the title verbatim (date stays quoted from the feed/listing) | 107/977 items cite a feed (83) or listing (24); 93 articles load and show the title in one node; no extra requests (the upgrade step already fetches them) | S | build |
| H4 | News path vocabulary: `nyheter.html`, `Aktueltarkiv`, Shopify `/blogs/<blog>`, `/blogger/` | 77 verified-site companies without news: 17 advertise a feed (13 of 14 checked are empty WordPress feeds), about 6 have a missed news section | XS | build |
| H5 | Title quality: first `<h1>` is often the site logo ("Nordicon" ×20), category pages taken as items ("Nyheter", "Inspirasjon"), template titles ("Hei, verden!") | short titles 72/391, 32/276, 52/310 items; repeated titles 37 items | S | build |
| H6 | Tracking parameters in item URLs (`?utm_source=rss…`) | 20 items in proxy-200 (one WordPress feed) | XS | build |
| H7 | Registry sub-unit homepages for companies without one | 4 of 295 companies without a registered homepage have one (live `underenheter`) | S | **rejected** (≤ 0.05 points) |
| H8 | Individual postings from Norwegian ATS linked from careers pages | already captured (`JOB_PLATFORMS`); 10 companies with site postings, 23 NAV postings in 600 | — | already in |
| H9 | RSS/Atom autodiscovery | WordPress feeds already tried; checked feeds empty | — | no gain |
| H10 | Headless rendering of JavaScript news listings | runtime and declared no-browser policy | L | rejected |
| H11 | News cap 20 → 30 | ruled out earlier (v4) | — | rejected |
| H12 | Norid registrant lookup as domain proof | forbidden by Norid's terms (earlier finding) | — | rejected |
| H13 | OSM / Wikidata P2333 / NAV employer homepage / ATS links for company coverage / generator challenger / org-number proof widening | ruled out in earlier sessions | — | rejected |
| H14 | Website URL normalisation (ports, deep paths) | 1/150 final URLs carries a port, 10 deep paths (kept: they are the verified addresses) | XS | no change |
| H15 | Social URL normalisation | 1/125 odd form (`facebook.com/pages/...`) | XS | no change |
| H16 | Per-company web budget spent on 404 careers probes before news upgrades | 4 companies in proxy-200 left 34 items feed-cited because the budget ran out | M | open (runtime trade-off) |
| H17 | Identity proof on unread legal/contact pages for websites held back as ambiguous | 77 held-back sites (500 + 100 companies), 16 typical pages each (privacy, terms, contact, about): organisation number found on **0** | S | **rejected** (the gate is not missing existing proof; the sites are managers', franchises' or groups') |
| H18 | Social profiles declared only in a page's JSON configuration (`"facebookLink":"…"`), read by key and quoted as printed, same identity check | 61 verified sites without a published profile: 10 contain profile URLs, of which ~2 are the company's own and invisible to the anchor-based extractor (the rest are platform links or fail the identity check, correctly) | XS | build |
| H19 | Retry registered homepages that failed with transient errors | 14 failures; 2 load now, both unusable (empty document, text/plain) | S | **rejected** |

### v5b measurement (WS-B code as of 14 Oct 19:40; live, same day)

| Set | news companies/items v5a → v5b | other families | requests | 1,500 projection |
|---|---|---|---|---|
| proxy-200 | 22/276 (det5) → 22/271 | unchanged | +6 | 1,043 s |
| sample-100 | 35/391 → 32/377 (the 3 lost had only "Hei, verden!", "Hello world!" or blog-category items) | unchanged | +10 | 1,191 s |
| set-300 | 29/310 → 31/336 (+2 from the new news paths) | hiring 15 → 16 | −6 | 1,141 s |

Org number now on every news/hiring claim and `company_site` record; repeated-title items 37 → 0;
listing pages in the kit profile for 12/12/17 companies. 34 proxy items stay feed-cited because 4
slow sites exhausted the per-company web budget before the upgrade fetch (H16).

### Blind review (fresh-context subagent, 40 companies: 20 sample-100 + 20 set-300, labels randomized)

- Summaries: new style won **40/40**; mean overall level **3.98 vs 1.85** (v2 style). Per criterion
  (new vs v2): does 3.40 vs 2.15, changed 3.92 vs 1.00, unknowns 3.92 vs 1.85, sources 4.90 vs 2.00,
  no unsupported claims 3.73 vs 3.40, useful 3.88 vs 1.85. None reached level 5.
- Viewer: new **4** vs v2 **2** overall; find desktop 5 vs 3, find mobile 4 vs 2, compare desktop 5
  vs 1, compare mobile 3 vs 1, verify desktop 4 vs 2, verify mobile 3 vs 2.
- Main fixes it asked for (summaries): an "In brief" opening; English glosses (NACE division, role
  names); "What changed" without junk posts, with recent role changes only (else "no change since
  …"), partial first periods labelled, no percentages on tiny or equal-rounded amounts; caveats for
  parent-only accounts, debt above assets, accounts that predate a rename; "the 20 most recent" for
  capped news; role records broken down by type; human-readable register links. Viewer: readable
  evidence (no raw dict/JSON values, hashes behind a toggle), mobile compare as stacked cards, wider
  mobile tables and tap targets, multi-year rows in compare, a short top block, a dated
  "What changed" timeline and a recent-changes filter.

### S/U round 2 (after the blind review; commit `a23df29`, WS-B under it at `6aed2a2`)

Summary (`synthesis.py`):
- Opens with **In brief**: legal form, place, NACE division in English, register headcount; latest
  revenue with the change on the previous full year and the annual result; website, social
  profiles, hiring and dated news in one line.
- English glosses: NACE division title after the Norwegian industry label; role and role-group
  names in English with the Norwegian name in brackets; registered activity marked "in Norwegian".
- What changed: role updates only if within two years of the run (otherwise "no role in the
  register was updated in the last two years; the latest update was to … on …"); part-year periods
  labelled and not compared; no percentage when either amount is under NOK 50 thousand or both
  round to the same figure; caveats for debt above total assets (negative equity), latest accounts
  that predate a name change, and parent-only figures when the register also holds group accounts;
  former names identical to the current one skipped; template posts ("Hello world!") kept as claims
  but never presented as news.
- Leadership as roles by type, single holders named ("chief executive (daglig leder) …; 7 board
  members (styremedlem); auditor (revisor) …"); partners named; correct plurals.
- Honest artefacts: "the 20 most recent dated news items (the agent reads at most 20)"; social
  profiles described as "profile pages only; links to single posts or videos are not listed";
  hiring unknown worded for companies without a website; readable register page linked after the
  sources (`https://virksomhet.brreg.no/nb/oppslag/enheter/<org>`).
- New claim `group_accounts` (periods of the register's KONSERN accounts in the response already
  fetched; span the literal `KONSERN`, verbatim in both the JSON and the XML representation).

Viewer (`viewer.py`): an "In brief" block with six key metrics and a revenue-trend bar chart at the
top of each profile; register page link; NACE division in English; roles in English; dated
"What changed" timeline (accounts periods, role updates, name changes, news, refresh changes) with
the last 90 days highlighted; a "changed in the last 90 days" tile, filter and list badge;
readable evidence values (no raw dict/JSON), hashes behind a toggle; compare with earlier revenue
years, equity, group accounts, recent changes and the best value marked; on phones compare is shown
as one card per metric, financial tables use compact numbers and citation links are larger.

### Push gate for WS-B + S/U round 2 (code `a23df29`; live runs `v5c` of 14 Oct ~23:30 IST)

| Check | Result |
|---|---|
| Unit tests | 185 pass at `a23df29`; 184 at `6aed2a2` (WS-B alone) |
| Schema / claim audit / summary traceability | 0 errors / 0 issues / 100%, 200 and 300 of 100, 200, 300 |
| Regression guard, S/U commit vs WS-B commit, live profiles | clean on 600 companies; only allowed additions (`group_accounts` 3, 10 and 1 companies) |
| precision_audit (100 claims, proxy-200) | **100/100 supported, 0 wrong-company**, 16/16 web spans on the page |
| evidence_audit (100 claims, 165 items) | **100% spans verbatim** |
| Census of external evidence (proxy-200, 1,844 items, live re-fetch) | 99.9% one-node; the 2 misses are company descriptions (as in v4); every news title/date span passes, including article-page titles with feed/listing dates |
| Red team | 0/35 false positives |
| Determinism pair (proxy-200 twice) | 0 duplicates, 0 change events, refresh 200 compared / 0 material; non-summary claims identical for 199/200 (980155889's site serves other event titles under the same timestamps, as in v4) |
| Forced hard deadline (`--hard-deadline 75`, proxy-200) | exit 0 at 76 s; 200/200 envelopes, schema 0, 200/200 summaries traceable and first, viewer written; 47 websites `budget_exhausted`; peak RSS 515 MB |
| Viewer, headless Chrome | 0 errors; all find/compare/verify/mobile checks pass; compare 26 rows |
| Runtime, 1,500 projection | 1,136 s (proxy-200), 1,193 s (sample-100), 1,134 s (set-300) |

Coverage (companies/facts) v5a → v5c: proxy-200 news 21/256 → 22/271; sample-100 website 71 → 70
(noise), news 35/391 → 33/376 (removed: one company whose only items were blog-category pages, one
whose only item was a "Hello world!" feed post: a two-word title on an undated article page is treated
like a section page, which errs toward precision); set-300 news 29/310 → 31/339 (two companies from the
new news paths), hiring 15/41 → 16/42. Other families unchanged.

### Blind review round 2 (fresh reviewer, absolute grading, 20 companies from `v5c`)

- ~150 facts in 10 summaries spot-checked against the embedded claims: all correct.
- Summaries mean level **3.80/5**: does 3.30, changed 3.80, unknowns 3.70, sources 4.10, no
  unsupported claims 4.00, useful 3.75. Viewer **4/5** overall (find 4/4, compare 4/4, verify 4/3).
- What kept summaries below 5: process jargon ("first Signalpost snapshot", "the agent reads at most
  20"), product boilerplate as unknowns (reputation; hiring for housing co-ops), Norwegian-only
  activity text, misleading division glosses (housing co-ops under division 97), role updates
  ranked by date (an accountant change outranking a new CEO; first registrations shown as changes),
  old renames under "What changed", percentages on small bases and non-comparable (part-year,
  17-month) periods, parent-only figures headlined, junk "news" (Lorem Ipsum, test posts, archive
  pages, page-stamped dates), and "careers page lists open positions" (the flag only means the page
  did not say there are none: an overclaim, now fixed).

### S/U round 3 (after review round 2)

Summary: process jargon and boilerplate removed; unknowns specific and cited (the check that was
made), hiring unknown only where relevant, ownership and group composition named as unknown;
holding/investment and real-estate activity texts glossed in English ("this text refers to …");
broad NACE gloss suppressed for housing co-ops; role changes ranked chief executive > board >
others, first registrations (within 120 days of founding) not reported as changes; renames older
than two years moved to the Company line; only 11–13-month periods compared, others labelled "the
N-month period …" with "result for the period"; no percentage on small bases (results under 2% of
revenue) or beyond 10×, a multiple between 2× and 10×; exact "NOK 0 in both"; a note when the
annual result differs from the operating result by net financial items and tax; parent-only figures
labelled everywhere; junk and page-stamped news kept as claims but never presented as news; the
most material change (recent rename, CEO or board change, negative equity) in "In brief".

Viewer: junk news excluded from counts, badges and the news sort; "parent accounts" badge; change
column only between twelve-month periods (multiples above 2×, debt neutral, correct signs);
English industry in search plus industry and municipality filters; source links on the brief cards
and more compare cells; plain-language accounting states; de-duplicated former names; a floating
Compare button and larger tap targets on phones; honest header/help/compare wording.

Checks: 190 unit tests; regression guard vs `a23df29` clean on 600 live profiles; 600/600 summaries
traceable; claim audit 0; headless checks pass.

## WS-C Scale

| Run | Result |
|---|---|
| Real 1,200-company run (`proxy-1200`, code `a23df29`) | exit 0, **553 s wall** (pass 1 67 s, web pass ends 544 s), 1,200/1,200 envelopes, viewer 13.2 MB, **peak RSS 0.91 GB** |
| Full 300-company run | 289 s, peak RSS 0.70 GB |
| Forced hard deadline (proxy-200, 75 s) | exit 0 at 76 s, 200/200 envelopes, schema 0, summaries and viewer written |
| 1,500 projection (summed request latency, scaled from v3's measured 990 s) | 1,134–1,193 s; the real 1,200 run scales to about 700 s |

### Blind review round 3 (absolute grading, 20 companies, output of `8dad2bb`)

Summaries mean level **3.90/5** (does 3.40, changed 3.90, unknowns 3.70, sources 4.85, no unsupported
claims 3.95, useful 3.55); viewer **4/5**. All spot-checked facts correct. Its prompt added one
fairness sentence (do not mark down for information the stated sources cannot contain), so it is not
strictly comparable with round 2 (3.80).

### S/U rounds 4 and 5 (after review round 3; `2456ff1`, `7eebddd`, `e7a339c`, `5f688f9`)

- English glossary for the registered activity text (key terms in order of appearance, e.g.
  "barnehage" → kindergarten; holding and property as terms, never replacing the main activity):
  509 of 600 briefs now say in English what the company does.
- Results in words (a profit/loss of NOK X), direction always stated, the financial-items amount,
  thin equity, first full accounting year, news chosen by business relevance (contracts, launches,
  results, appointments) with greetings and seasonal posts left out, analytical unknowns (what a
  holding company owns, what caused a loss), candidate-website sources labelled as such.
- **Group (konsern) figures** (`group_financials`, one claim per group year from the accounts
  response already fetched, every figure a value-literal span): group companies lead with group
  revenue and result, parent figures labelled; the viewer shows a group accounts table, group revenue
  in badges, sort and compare. Census of all accounts spans on the live API: 4,469/4,469 verbatim in
  both JSON and XML.
- `registered_activity` published as the register's own lines (each verbatim in the source; a
  precision audit that looks for the value now finds it: 96/100 → 100/100).
- News from a site that stamps every page with the fetch time is not published as dated news
  (1 company of 600: lorem-ipsum pages).
- Viewer: register changes only in the 90-day filter; hiring excludes pages that state no openings;
  junk news filtered everywhere; website identity proof shown; compare legend, group rows, accounts
  period; "registered at the start" in the timeline; collapsible filters and sticky search on phones;
  evidence as stacked cards on phones; a unit test parses the viewer script with node.

### Push gate (code `5f688f9`)

| Check | Result |
|---|---|
| Unit tests | 194 pass (on a `git archive` of the commit) |
| Live runs `v5g` (code `7eebddd`) and offline rebuilds with `5f688f9` from their profiles | schema 0, claim audit 0, summaries 600/600 traceable on sample-100, proxy-200, set-300 |
| Regression guard (`--base 6aed2a2 --new 7eebddd`) on live profiles | clean; only listed additions (`group_financials` 30 claims for 10 group companies on sample-100) |
| Accounts span census (live, JSON and browser-style XML) | 4,469/4,469 verbatim |
| precision_audit (100 claims, sample-100, `5f688f9`) | 100/100 supported, **0 wrong-company**; web spans 16/17 (homepage that does not print its own URL) |
| evidence_audit (v5g sample-100) | 99.3% (the one miss was a page-stamped news date, no longer published in `5f688f9`) |
| Red team | 0/35 |
| Determinism pair (`det7`, proxy-200) | 0 duplicates, 0 change events, refresh 0 material, non-summary claims identical 200/200 |
| Viewer headless | 0 errors; all find/compare/verify/mobile checks pass |
| Runtime, 1,500 projection | 1,111 s (proxy-200), 1,175 s (sample-100), 1,123 s (set-300) |

Coverage (companies/facts) on the final live runs: sample-100 website 71/71, social 40/84, news
33/376, hiring 20/24; proxy-200 44/44, 21/41, 21/251, 16/17; set-300 83/83, 45/86, 31/339, 16/38
(within ±2 companies of the earlier v5 runs; the crawl noise floor).

### Blind review rounds 4 and 5 (absolute grading, 20 companies each)

- Round 4 (code `5f688f9`): summaries **4.05/5**, viewer **4/5**; compare on desktop 3/5 because group
  and parent figures were mixed in one column and amounts carried no currency.
- Round 5 (code `e292fcd`): summaries **3.85/5**, viewer **4/5** (about 9/12 and 6–6.5/8 if graded
  that strictly). Remaining points: the brief named a weaker change before a stronger one, "rose
  sharply" for a smaller loss, unknowns that repeat what the accounts cannot say, stale news shown as
  a change, event posts as news, "names the company" for a menu label, compare amounts hard to read,
  search missing English terms, and the mobile section bar.

### S/U round 6 (`9b589dd`, after review round 5)

- Brief: the most material change by priority (rename > result swing > large result move > revenue
  move ≥ 30% > chief executive > board), and negative equity is always flagged next to it.
- Results: a loss narrows or widens and a profit rises or falls ("more than doubled/tripled" only when
  strictly true); financial items carry their year; partnerships (DA, ANS, KS) and sole proprietors
  are not said to pay tax; first accounts that start on the founding day are recognised (a 0-day gap
  was read as unknown before) and a 15-month first period is not called "only".
- What changed: news older than twelve months is not a change and Recent activity says none is from
  the last twelve months; conference, fair, webinar, seminar and investor-day posts are not business
  news; parent-company movements are kept unless the group has its own year-on-year figures.
- Unknowns: holding companies name the unknown shareholdings; an operating-result fall or the
  financial-cost total is named instead of a generic "what caused the loss"; the hiring unknown only
  for employers or companies with a website.
- Website identity is stated only from the register's homepage field, the organisation number or a
  distinctive part of the company's own name on the page.
- Viewer: search also covers the English activity terms and digit-only industry codes, terms of up to
  three letters match at word starts; compare starts with what the company does and the finances,
  amounts shortened with the currency (full figure on hover and in the CSV), a second Close at the
  bottom; on phones the section links are one scrolling row, only the search box stays on screen, and
  a section link scrolls within the profile (it used to change the address and return to the list);
  old news is noted.
- Checks (offline from the `vf` profiles, 600 companies): schema 0, claim audit 0, summaries 600/600
  traceable, regression guard clean against `e292fcd`; headless viewer checks pass on all three sets
  and on a 1,200-company build (13.4 MB, ready in 0.6 s desktop / 0.45 s phone).

### Evidence fix (`a336bf8`)

The external-span census of the `e292fcd` gate (set-300, 2,689 spans re-fetched) found 24 spans not in
one node of the live page (99.1%; 99.5% visible). Most were pages that changed between the run and the
re-fetch or listing spans that cross nodes, but four social-profile spans were the normalised URL
(`https://linkedin.com/company/forsvarer`) where the page prints `https://www.linkedin.com/company/forsvarer`:
links named only in a page's structured data (`sameAs`) took the normalised URL as their span since
Phase 2 (4 Oct). They are now quoted exactly as printed (plain or with JSON-escaped slashes), and a
link the page does not print verbatim is not published. Live check on the three affected companies:
8/8 social spans and 51/51 spans verbatim on re-fetch; claim values unchanged.

### Final blind review (fresh reviewer, v2 vs new, 40 companies: 20 sample-100 + 20 set-300, labels randomized; code `9b589dd` on the 15 Oct live profiles)

| | v2 style (single paragraph) | new style (labelled sections) |
|---|---|---|
| does / changed / unknowns / sources / no unsupported claims / useful | 2.08 / 1.00 / 1.85 / 2.00 / 3.25 / 1.85 | 4.05 / 4.92 / 4.55 / 5.00 / 4.47 / 4.47 |
| overall level (1–5) | 1.85 | **4.70** (28 fives, 12 fours) |
| preferred | 0 | **40 of 40** |

Viewer: new **5/5** (find desktop 5, find mobile 5, compare desktop 5, compare mobile 4, verify desktop 5,
verify mobile 5); v2 viewer 2/5 (no compare). New is at least as good as v2 on every criterion.

### S/U round 7 (`c9f2049`, the reviewer's flagged sentences)

What changed names only business news (contracts, launches, results, appointments) and says so;
event invitations are not news; losses deepen or narrow (not "reduced" when the costs deepened a
loss); the unknown explains the larger movement (financial costs of NOK 5.4 million rather than a
NOK 33 thousand operating move); owners named on the company's own site are not listed as unknown;
slider buttons ("Forrige Neste") trimmed from the site's text, which is quoted as what the site
says rather than as a description; glossary fixed where it misread the text (import ≠ import/export,
arbeidstrening ≠ sports, medical equipment ≠ medical services, surveillance products ≠ security
services; printing, commercial property, food products, supplements, batteries and EV charging
added); "at least 20 dated news items" instead of "publishes news regularly"; no second sentence with
the same figures; a former name that ends before the founding date is explained; a twelve-month
year that is not a calendar year is a financial year, a 352-day first year is a period. Also: a zero
result is a result of NOK 0, never a profit, and a swing needs a real change of sign; the brief's
group figures use the group's currency; phone compare cards show full amounts.

### Final push gate (code `a336bf8`; summary and viewer changes to `c9f2049`)

| Check | Result |
|---|---|
| Unit tests | 213 pass on a clean `git archive` of `c9f2049` |
| Live runs `vf2` (code `a336bf8`, 15 Oct) on sample-100, proxy-200, set-300 | exit 0; schema 0, claim audit 0, summaries 600/600 traceable |
| Offline rebuild of those 600 profiles with `c9f2049` | schema 0, claim audit 0, summaries 600/600 traceable; regression guard clean against `a336bf8` (no claim, evidence or other field changed) |
| Regression guard `e292fcd` → `a336bf8` on the live profiles | clean |
| precision_audit (100 claims, sample-100) | 100/100 supported, **0 wrong-company**, web spans 18/18 |
| evidence_audit (100 claims, proxy-200) | spans 100% verbatim of loaded pages |
| External span census, set-300 (2,694 spans re-fetched) | 99.3% in one node, 99.7% visible (99.1% / 99.5% before the `sameAs` fix); social spans 84/84 on sample-100 |
| Red team | 0/35 |
| Determinism pair (`detf2`, proxy-200) | 0 duplicates, 0 change events, refresh 0 material, non-summary claims identical 200/200 |
| Viewer, headless Chrome | 0 errors, all find/compare/verify/mobile checks pass on the three sets and on a 1,200-company build (13.4 MB; ready in 0.6 s desktop, 0.45 s phone) |
| Runtime, 1,500 projection | 1,119 s (proxy-200), 1,185 s (sample-100), 1,165 s (set-300); hard deadline 1,500 s |

Coverage (companies/facts) on `vf2`: sample-100 website 71/71, social 40/84, news 32/373, hiring 20/24;
proxy-200 44/44, 21/41, 22/271, 16/17; set-300 81/81, 46/88, 31/339, 15/37. Against the run four
hours earlier (`vf`, code `e292fcd`) sample-100 and proxy-200 are identical; set-300 lost two websites
to the live web (one site failed to load, one site's contact page did not show the organisation
number this time, so the identity gate withheld it), within the ±2 noise floor. For companies verified
in both runs: 213 social profiles the same, 0 lost, 0 gained, 6 spans now quoted as printed.

Known residual (unchanged since earlier versions): a homepage that prints no text at all (a script-
rendered site whose register-listed domain carries the legal name) has its URL as the website span;
1 of 71 verified websites on sample-100.

## Packaging (15 Oct 2026, final)

- Agent code of v5: `c9f2049e25dd7ed3e6d64f6ae5ad2e31e081378e` (pushed; `5f688f9` was the previous
  packaged code, `bea4bcb` its smoke-test commit).
- Cold-cache fresh clone of `c9f2049` from GitHub into an empty directory with an empty
  `UV_CACHE_DIR` and no virtualenv: `uv sync` exit 0 (3 s), the one command on the 100-company smoke
  list exit 0 in 251 s, 100/100 envelopes, schema validator 0 errors, summaries 100/100 traceable,
  claim audit 0 issues, precision audit 100/100 with 0 wrong-company (web spans 13/13), headless viewer
  checks pass. Same published facts as the `5f688f9` smoke run (website 8, social 2, dated news 3; the
  list is web-sparse). `docs/smoke-test/` regenerated from that run (README, envelopes, report, input
  list and `smoke-viewer.html`).
- Submission commit: the `main` commit that carries that smoke test (docs only on top of `c9f2049`).
  Email draft `docs/V5_EMAIL.md` (hash and contact as placeholders); a filled copy is kept outside the
  repository. Nothing has been sent.

## Status (15 Oct 2026, final)

- WS-A, WS-B, seven S/U rounds, the evidence fix and WS-C are on `main` with their gates. Final blind
  review: summaries 4.70/5 against v2's 1.85 (preferred 40/40), viewer 5/5 against 2/5.
- Not established: whether our news and hiring items now match Builderr's verified pool (only their
  scorer can show it). Website and social coverage are unchanged by design (identity gate untouched).
