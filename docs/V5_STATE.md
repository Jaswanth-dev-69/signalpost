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

## Status at cut-off (14 Oct ~20:00 IST)

- **Pushed:** WS-A at `e8f86b1` (origin/main, fast-forward from `pre-v5`), full push gate above.
- **Not pushed:** WS-B code in the working tree (also saved as `.work/patches/wsb-v5c.patch` and
  `.work/patches/test_v5b.py`): H1 org number, H2 kit-profile listing pages, H3 article citations,
  H4 news paths, H5 titles (slug-matched, section pages dropped, repeated titles dropped; template
  posts kept as claims), H6 tracking parameters stripped, plus the article-`<h1>`-inside-teaser
  title. 184 unit tests pass. The last two refinements and H6 have **not** had a live run yet.
- **Next, in order:** (1) summary/viewer fixes from the blind review (filter template posts from the
  narrative); (2) WS-B live runs on the three sets + determinism pair + push gate, then push;
  (3) WS-C forced-deadline test (`--hard-deadline 70` on proxy-200: 200 envelopes, schema 0,
  summaries, viewer written); (4) cold-cache clone of the final hash, regenerate `docs/smoke-test/`
  for v5 (include the smoke viewer), email draft with placeholders; never send.
