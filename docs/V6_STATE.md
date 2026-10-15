# v6 state

Started Thu 15 Oct 2026 18:27 IST from `main` = `51bdc07` (the v5 submission commit; agent code
`c9f2049`). Tag `pre-v6` pushed at `51bdc07`. Hard decision point: Sat 17 Oct 15:00 IST; revisions
close 18 Oct. v5 stays the fallback submission.

Goal: raise official Recall as far as honest measurement supports while Evidence stays 30.00 (strict
identity gate, 0 wrong-company, every span verbatim) and Synthesis/UX output stays as it is.

## Contract, challenge page and board (re-fetched 15 Oct 18:35 IST)

Every page is byte-identical to the 14 Oct copies (`.work/web/d1014` vs `.work/web/d1015`): challenge
page with the board, evaluation contract, guidelines, sample site, the four starter briefs and the
kit tarball (`Last-Modified` 12 Oct). The board is still the one reviewed on 5 Oct.

| Question | Answer (source) |
|---|---|
| 411,160 | The **public universe** of eligible organisation numbers ("Public universe: all 411,160 eligible organisation numbers"; page: "Get all 411,160"), unchanged. It is not a batch. |
| Official batch size | Contract: "The current official input batch, supplied by Builderr (1,000 companies now; it may grow to 1,100)". Page: "Submit 1,000+ profiles"; the 5 Oct board recalculated every entry "against the same locked 1,500-company set" and "each scored entry ran twice". |
| Time limit | Not published: "A fixed time and resource budget supplied equally to every entrant"; "A timeout or missing result is not scored". |
| Bulk data | "Builderr provides the frozen official registry snapshot used for identity anchoring"; cached public-universe material is allowed if declared. |

The batch is at most about 1,500 companies, so the runtime design stands (1,500 projected
1,119–1,206 s on the v5 runs, hard deadline 1,500 s, forced deadline writes every envelope). No
re-derivation needed.

## 1. Forensics (offline; sample-100 run `vf2` of 15 Oct against Builderr's published sample facts)

Measured with `eval/scorer_mirror.py --sample .work/sets/sample100.json --no-pool` (kit read mode) and
the kit's own readers. Builderr's sample rows are Builderr's crawler output for the 100 sample
companies: websites, site-linked social profiles, LinkedIn posts and jobs (`experimental`), and the
website record's bounded `pages`.

| Family | Builderr's pool (sample) | We match | What we miss and why | Ceiling under the rules |
|---|---|---|---|---|
| Website | 97 companies | 74 | 8 sites Builderr's own gate rates non-exact; 11 with no homepage in the register (bulk or live) or the universe file (Builderr's own discovery; name-based guessing is ruled out); 1 dead register domain (`tgsnopec.com`); 1 verified under another domain (`studix.no` vs `studix.com`); 2 held back by the identity gate (a chain site, a managing agent's site) | about 74–75 |
| Social | 44 companies, 91 facts | 37 / 77 | all 14 missing facts belong to the 7 companies whose website we do not verify; inside covered companies 0 missed, 1 extra | tied to websites |
| News | LinkedIn posts for 17 companies (139) **and** the kit's company-site news fact for 16 companies | 0 LinkedIn; company-site 4 companies, 2 exact URLs | LinkedIn: not permitted (robots `Disallow: /`, sources brief). Company-site: the kit reader takes the deepest news-path page in the bounded `pages`; ours carry such a page only where a listing produced published items, so 3 companies with our dated news and 5 news-section pages we checked (`pervaco.no/nyheter`, `narvikgolf.no/nyheter`, `trondelag-betong.no/aktuelt/` …) are invisible to it | about 12–13 of 16 company-site companies |
| Hiring | LinkedIn jobs for 2 companies (8) | 0 | LinkedIn only; the kit has no company-site hiring reader | 0 in this sample; NAV and careers facts count only if Builderr's verifier accepts them |

What a news/hiring fact must look like (kit code re-read): `src/norway_company_agent/external_footprint.py`
validates an observation (`organisation_number`, `platform`, `signal_type`, `source_url`, `retrieved_at`,
64-hex `content_sha256`, `exact_entity`, `identity_proof`, `acquisition_mode` `permitted_public_page`,
`rights_status` `approved`, `evidence_span` for posts) and counts posts and jobs by unique
`source_url`. `scripts/extract_company_site_news.py` emits one `company_site`/`public_post`
observation per company: the deepest news-path page (`/news|press|aktuelt|nyheter|artikler|blog/`
segment) of a publishable website, with the page title as span. Builderr's v2 feedback keyed a news
fact as `title (datetime with offset)`, lowercased, from the article page. `scripts/score_competition_v3.py`
is an older proxy (identity, breadth, workforce, reviews, buzz, sentiment), not the current contract.

`eval/scorer_mirror.py --kit-news` (new) adds, on both sides, the kit reader's company-site news
fact. With it the v5 run scores 20.72 on Builderr's sample (news 2/29 companies) instead of 20.07.

## 2. Levers, sized before coding

### 2a. Norid (.no registry): **skipped, not permitted**

Norid's terms for its lookup service (updated 1 April 2025) allow lookups only to resolve technical
problems, find who is responsible for a domain, contact the subscriber or protect rights; "any and all
use of the lookup service beyond what is allowed in this document is forbidden", storing or
transferring significant parts of the data is forbidden "whether the purpose is for commercial use or
not", and lookups are rate-limited per IP. `rdap.norid.no/robots.txt` is `Disallow: /`, and
`www.norid.no/robots.txt` disallows the holder and organisation-number lookups. No query pattern for
verifying company domains is permitted, so it was not sized (`eval/discovery_labelled.py` not run).

### 2b. Other sources and angles (ranked by expected gain per effort)

| # | Hypothesis | Sizing | Verdict |
|---|---|---|---|
| L1a | Every news page the news pass checked on a verified site goes into the kit profile's bounded `pages`, also when it yields no dated items (today only with published items) | offline on the 15 Oct runs: kit-read news companies 11 → 18 (sample-100), 12 → 18 (proxy-200), 17 → 23 (set-300); vs Builderr's 16 kit news companies 4 → 7, exact URLs 2 → 5; mirror (`--kit-news`) 20.72 → 21.70 | build |
| L1b | When no such page is on the kit's news path, the newest published article that is | +5 / 0 / +1 companies; Builderr overlap 7 → 9, exact 5 → 7; mirror → 22.35 | build |
| L2 | When neither is, the homepage link the kit's own crawl would take (same host, kit term order, then URL) is read once and recorded as a checked news page (kept out of claims) | light live: homepages link such a page for 9 of 48 (sample-100), 4 of 26 (proxy-200), 2 of 57 (set-300) still-uncovered verified sites; 4 Builderr news companies, 2 exact URLs (sample-100) | build |
| H25 | Finanstilsynet's register of licensed firms (banks, insurers, accountants, agents) | `robots.txt` `Crawl-delay: 10`; one lookup per 10 s makes per-company lookups infeasible inside the run budget; register search page not reachable at the documented path | rejected |
| H26 | Oslo Børs Newsweb / Euronext company news for listed issuers | Newsweb is a JavaScript-only app (no-browser rule); listed issuers only | rejected |
| H27 | Arbeidstilsynet registers (cleaning, staffing, car care) | index redirects to an authorisations page; no website or news field, no open data found | not sized further (no field to read) |
| H28 | DiBK central approval register | no homepage field (v5 H24) | rejected |
| H29 | Brønnøysund announcements (kunngjøringer) as dated news | official events, not company news; nothing in Builderr's sample pool has that shape | rejected |
| H30 | Full datetime with offset instead of date-only news timestamps | date-only items 58 / 9 / 77; their pages print only a date (text, date-only `<time>`, listing or URL), so there is nothing richer to read | no gain |
| H31 | A second verified domain linked from the company's own site (`studix.no` → `studix.com`) | the one known case on sample-100; not sized further | not built (expected below the noise floor) |
| H32 | Careers page in the kit profile's `pages` | the kit has no company-site hiring reader | rejected |

### 2c. Fact depth on verified sites

Social: inside companies we cover we miss 0 of Builderr's social facts (1 extra). News: Builderr's
company-site fact is one page per company (kit reader), so more items per company add nothing to it;
the cap of 20 stays (cap 30 ruled out). Hiring: Builderr's sample has only LinkedIn jobs. No
measurable gain from more facts per covered company.

### 2d. Shapes

On the 15 Oct v5 runs every `dated_news` claim carries title, direct URL, ISO date and organisation
number (373/373, 271/271, 339/339), as do the observation records (one proxy record lacks a date
string) and `external.company_site.posts` (`title`, `url`, `date_published`, `organisation_number`);
every hiring claim, observation and `company_site.jobs` record carries the organisation number.
63 news items are still cited by a feed or listing rather than their own article page: live re-check
shows 32 whose article loads and prints title and date (slow sites that exhausted the per-company web
budget before the upgrade fetch, v5 H16), 25 not fetchable (robots, errors, off-domain) and 6 whose
article does not print the feed's title. Their key fields are already complete, so no recall change
is expected: sized only.

## 3. Built: L1 + L2 (commit `aba41ad`), live gate 15 Oct (runs `v6a`, `detv6`)

Code: `contract.py` 6c puts every news page the news pass checked on a verified site into the kit
profile's bounded `pages` (also without published items), and, when none lies on the kit reader's
news path, the newest published article that does (L1); `webclaims.discover_news` reads, when neither
a checked page nor a published article lies on that path, the homepage link the kit's crawl would
take (`kit_news_link`: same host, kit term order, then URL) and records it as a checked page that no
claim cites (L2). Only the kit profile changes; claims, evidence, summaries and the viewer do not.

| Measure | sample-100 | proxy-200 | set-300 |
|---|---|---|---|
| Kit-read company-site news companies, v5 → v6 (live) | 11 → **30** (+19, 0 lost) | 12 → **22** (+10, 0 lost) | 17 → **25** (+8, 0 lost) |
| Claims families, companies/facts v5 → v6 (website, social, news, hiring) | 71/71, 40/84, 32/373 → 32/374, 20/24: unchanged | 44/44, 21/41 → 21/40, 22/271 → 22/272, 16/17: unchanged | 83/83, 47/89, 31/339, 16/43: identical |
| Companies where L2 fired | 7 | 3 | 1 |

v5 baselines: `vf2` (sample-100, proxy-200) and `be92` (set-300), same day. Noise floor about 2
companies per family per 300.

Recall on Builderr's own sample facts (`eval/scorer_mirror.py --sample … --no-pool`, sample-100):

| Read assumption | v5 | v6 |
|---|---|---|
| kit profile, pool without kit company-site news | 20.07 | 20.07 |
| kit profile, pool with kit company-site news (`--kit-news`) | 20.72 (news 2/29) | **23.00** (news 9/29) |
| kit profile + claims, with kit news | 21.70 (news 5/29) | **23.33** (news 10/29) |

Of Builderr's 16 kit news facts, v6 matches 9 exactly; of the other 7, 3 are sites we do not verify
(atea, nordicdoor, st-olav), 3 are specific articles Builderr's crawl caught on its own crawl date
(prereg, kitron, bien) and 1 site gave no kit page in this run (avogpaa).

### Push gate (`aba41ad`)

| Check | Result |
|---|---|
| Unit tests | 220 pass (213 + 7 new in `tests/test_v6.py`) |
| Schema / claim audit / summary validator | 0 / 0 / 0 on sample-100, proxy-200, set-300 and set-1500 |
| Regression guard `c9f2049` → `aba41ad` on the live profiles (L2's pages removed, since base code would cite them) | clean on all three sets |
| L2 isolation (envelopes built with and without L2's page) | identical apart from the kit page and the crawl record that lists it: 7/7, 3/3, 1/1 |
| Summaries and viewer (offline, v5 vs v6 code on the same profiles) | summaries identical 600/600; viewer HTML byte-identical on all three sets |
| Added kit pages re-fetched (110 pages) | title verbatim 110/110 (one text node 107/110) |
| precision_audit (100 claims, sample-100) | 100/100 supported, **0 wrong-company**, web spans 17/17 |
| evidence_audit (100 claims, proxy-200) | 99.4%: the one miss is serit.no's company description, whose 166-character span joins "bedrifter" and "." across an inline tag (page text "bedrifter ."); identical claim and value in every v5 run, not touched by v6 (the description residual noted in the v4/v5 censuses) |
| External span census, set-300 (2,696 spans) | 99.3% one node, 99.7% visible (v5: 99.3% / 99.7%) |
| Red team | 0/35 |
| Determinism pair (`detv6`, proxy-200) | 0 duplicates, 0 change events, refresh 0 material; non-summary claims identical 198/200: serit.no serves titles with and without " - Serit" (as in v4/v5), and fodebagen.no's homepage led the news pass to a page-2 collection link in the second run (site variance in pre-existing code) |
| Runtime, 1,500 projection | 1,130 s (proxy-200), 1,223 s (sample-100), 1,224 s (set-300); +8, −13, +3 requests vs v5 |

## 4. Scale (`aba41ad`, live)

| Run | Result |
|---|---|
| set-1500 (`eval/fixture_proxy.py`, seed 20261015, 43% register homepages) | exit 0, **721 s wall** (pass 1 95 s, web pass ends 686 s), 1,500/1,500 envelopes, 0 tracebacks, 0 deadline notes, peak RSS **1.00 GB**; 18,936 requests, p50 208 ms, p95 2.5 s, HTTP 429 web 11, registry 0; schema 0, claim audit 0, summaries 1,500/1,500 traceable |
| Viewer, 1,500 companies | 16.7 MB; ready 0.65 s desktop, 0.54 s phone; all headless checks pass |
| Forced hard deadline (`--hard-deadline 75`, set-300) | exit 0 in 46 s, 300/300 envelopes, peak RSS 0.21 GB |

## Packaging (15 Oct 2026)

- Agent code of v6: `aba41ad` (pushed); main `0ca604247e4a8f941d2e6f0cb2f393d3b6c2b55d` = that code plus
  docs.
- Cold-cache fresh clone of **`0ca604247e4a8f941d2e6f0cb2f393d3b6c2b55d`** from GitHub into an empty
  directory with an empty `UV_CACHE_DIR` and no virtualenv: `uv sync` exit 0 (2 s), the one command on
  the 100-company smoke list **exit 0** in 262 s, **100/100 envelopes**, **schema validator 0 errors**,
  summaries 100/100 traceable, claim audit 0 issues, precision audit 100/100 with 0 wrong-company
  (web spans 12/12), headless viewer checks pass; same published facts as the v5 smoke run (website 8,
  social 2, dated news 3; web-sparse list), kit-read news companies 1 → 2. `docs/smoke-test/`
  regenerated from this run and cites v6 and this hash.
- Submission commit: the `main` commit that carries that smoke test (docs only on top of `0ca6042`).
  Nothing has been sent and no v6 tag exists.

## Status (15 Oct 2026, evening)

- Built: L1 + L2 (kit-read company-site news), gated on three sets and at 1,500 companies.
- Sized and rejected or not permitted: Norid, Finanstilsynet, Newsweb, Arbeidstilsynet, DiBK,
  announcements, datetime precision, second domains, careers pages in the kit profile, fact depth.
- Unchanged by design: websites, social profiles and every claim (identity gate untouched).
- Not established: which read path Builderr's scorer uses for news and hiring; v6 helps only if it
  includes kit-read company-site news, and is equal to v5 otherwise.

# v6 round 2 (started Thu 15 Oct 23:03 IST from `85a544c`, the fallback; hash decision 16 Oct 13:00 IST)

## Step 1. Evidence: single-node description spans (code `48dc33d`, built)

Where description spans are built: `contract._company_description` takes, in order, the meta
description, a JSON-LD Organization description, the first substantive paragraph of an about page,
then of the homepage; the evidence span is the first 400 characters. The two paragraph sources come
from extracted text that joins inline elements, so a paragraph can cross tags.

Fix: at crawl time (`website._lead_paragraph_fix`, homepage and identity pages) the paragraph the
contract would quote is checked against the page's own text nodes. When its span lies inside one node
nothing is recorded and the contract behaves exactly as before; otherwise the crawl records the whole
sentences (40+ characters) of the node where the paragraph starts, or nothing, and the contract uses
that or falls through to the next source (`contract._page_paragraph`).

Live census of every published description span (one text node or one attribute value of the live
page, the census's definition), same day:

| Set | before (`v6a`, code `aba41ad`) | after (`v7a`, code `48dc33d`) |
|---|---|---|
| sample-100 | 65 of 66 in one node | **66 of 66** |
| proxy-200 | 39 of 41 | **40 of 40 loaded** (41 published; 1 page did not load at census time) |
| set-300 | 79 of 82 | **81 of 81** |

Descriptions changed only for the 6 companies that failed before (identical for 99/100, 198/200,
297/300): brannkontrollnorge.no, p22.no, serit.no and ressurscompagniet.no now quote the homepage's
first paragraph (single node); bakkemaskin.no keeps its first two sentences, now single-node;
bjornebarstien.no publishes no description (no single-node paragraph). Their summaries change with
the description they quote; nothing else changes (envelopes built with and without the crawl's
replacement: identical apart from the description claim, its evidence and the summary, 13/13, 16/16,
27/27 by content). Schema 0, claim audit 0, summary validator 0 on all three sets; regression guard
(`--base 0ca6042 --new 48dc33d`, replacement removed from the live profiles) clean on all three.

Audits on `v7a`: precision audit (sample-100, 100 claims) 100/100 supported, **0 wrong-company**, web
spans 18/18 on the page; evidence audit (proxy-200, seed 20261020, 100 claims, 159 evidence items, all
loaded) span verbatim **100.0%** against 99.4% for `v6a` with the same seed re-run the same night (its
one miss: the serit.no description, fixed here); wrong-company red team (35 companies) 0 false
positives.

## Step 2A. Permitted discovery audit (text re-read 15 Oct; pages unchanged since 14 Oct)

| Method | Permitting text (quoted) | Sized | Verdict |
|---|---|---|---|
| Official registers (Enhetsregisteret, Regnskapsregisteret, roles, subunits) | Sources brief: "Brønnøysundregistrene Enhetsregisteret bulk data and entity API …", "Regnskapsregisteret API and annual-account copies …", "Official roles endpoints …", "Official subunit records …"; "Official data is the identity anchor. It does not, by itself, identify the public brand or website." | in use (register homepage; register e-mail domain and legal-name domains under the strict proof; subunit homepages sized in v5 H7: 4/295) | no new method |
| Company-owned sources | "Verified official website", "Sitemap, news, investor, careers, location and contact pages", "Structured data embedded by the company", "Social or video profiles linked by the verified company site, subject to the destination platform's access terms" | in use | no new method |
| Search APIs | Sources brief: "Search APIs used to discover candidates"; "Search results generate candidates; they are not claim evidence." Playbook: "Search/discovery providers for candidate generation only"; "Each run has a small external API budget, and if you need a model key for scoring, ask and we will supply one. What we cannot use is a credential tied to your own account on another service". Kit README: "lawful search providers"; kit `docs/external-connectors.md`: "Search is only for an entity whose registry website is absent, invalid, or dead. Recommended production path: a separately contracted Brave Search API connector …". Contract: "server-side secrets supplied through documented environment variables only". | upper bound below | **not buildable here**: needs a provider key; the text offers a model key on request and forbids personal credentials; no key is available and asking Builderr is an e-mail |
| Official or licensed platform APIs; licensed news/review/jobs/company-data feeds | Sources brief, "External sources" | — | need contracts or keys: not available |
| Public pages whose terms and robots permit the access (directories) | "Public pages whose terms and robots policy permit the submitted access pattern" | proff.no: CDN blocks this country (403); gulesider.no: bot challenge (bypass forbidden); 1881.no and purehelp.no: robots allow company pages, terms not confirmed | rejected (and bounded below) |

**Upper bound for any discovery source, measured.** For the 11 exact websites in Builderr's sample that
no register (bulk, live, universe file) lists and that we miss, we fetched Builderr's own domain as if
a perfect source had supplied it and applied the unchanged strict proof for discovered domains: **2 of
11 pass** (ts-vestfold.no and pe-gaarud.no print the organisation number). The other 9 print no
organisation number and no legal name with municipality (7), share their name tokens with another
entity in the municipality (nordicdoor.no) or print another organisation number (storebrand.no, the
group's). So the method the contract permits for those 11 (search APIs, candidates only) is capped at
+2 websites on sample-100 by our gate, which stays as is.

Same bound on a larger labelled population (`eval/discovery_labelled.py`, table rebuilt from the frozen
bulk snapshot: 1,176,492 entities, 78,960 domains declared by exactly one entity; 200 labelled
companies, strata none/5-19/20-99/100+ = 100/60/30/10, seed 20261016; each treated as declaring
nothing; challenger = an oracle returning the company's true domain, i.e. a perfect search result):
the current generator (register e-mail domain and legal-name domains) has a site accepted by the strict
proof for **58 of 200**; the oracle's true domain loads for 152 and passes the strict proof for
**64 of 200** (none 16/100, 5-19 33/60, 20-99 11/30, 100+ 4/10; failures: no organisation number and no
legal name plus municipality 85, another organisation number 4, homonyms 4). A perfect discovery source
would add **7 companies of 200** (and miss 1 the generator finds). The generator's 9 acceptances of a
domain other than the declared one are the company's own other sites: 6 print its organisation number
(retrade.eu, copyleft.no, arvalyd.no, arkivfinnmark.no, dittkontor.no, arbo.no), 3 show its full legal
name with the registered municipality (csbilnorge.no, sagahouseoslo.com, wenorwegians.no).

## Step 2B. Match-key audit (news and hiring)

Every verified Builderr fact we have: v1 feedback (`../TASK.md`): dated news missed `813396092 ->
https://www.bori.no/aktuelt` (a news listing page), jobs missed `838797172 ->
https://www.granne.no/ledige-stillinger` (a careers page); v2 feedback (`docs/SCORER_NOTES.md`):
`elopak.com`, `facebook.com/mtmskogservice`, `https://www.equinor.com/careers`,
`bedre sosial funksjon etter hjerneskade (2025-09-22t20:00:00+02:00)`; Soham: "Capture title, direct
URL, publication date, and exact company match"; Builderr's sample rows (LinkedIn posts: `source`,
`date_published` full ISO datetime; jobs: `job_url`, `date_posted`); the kit's observation schema
(`validate_observation`) and news reader (deepest news-path page, `source_url`, title span).

| Needed | Ours (v6 runs, three sets) | Result |
|---|---|---|
| News key `lowercase(title + " (" + datetime with offset + ")")` | `dated_news` value `Title (published_at)`, published_at as printed | same shape |
| Title, direct URL, publication date, organisation number | claim `title`, `url`, `published_at`, `organisation_number`: complete on every item | match |
| Full datetime where the page has one | 845 of 985 items carry a full datetime; for the 140 date-only items, 81 article pages loaded and none prints a full datetime for that day (meta, JSON-LD, `<time>`); 59 not fetched in the check | no mismatch |
| Same datetime in every shape | `external.company_site.posts.date_published` and the observation `published_at` equal the claim's for 320/320, 263/263, 262/262 datetime items | match |
| News listing page (v1 example) | in the kit profile's `pages` since v6 L1/L2 | match |
| Hiring = careers page URL (v1, v2 examples) | `hiring_signal` value = careers page URL; `company_site.jobs.job_url`; observation `source_url` | match |
| Observation schema | news and hiring observations pass the kit's `validate_observation` | match |

No mismatch found; nothing changed.

## Step 2C. How the verified pool is built (contract text only)

- "We combine independently checked findings from all submissions and Builderr's own crawlers into one
  reference collection. New verified findings update the collection, and every entrant is rescored
  against the same version. This is the checked information we have found, not a claim that we found
  everything online."
- "For every external field family, coverage is 70% company recall and 30% individual-claim recall
  against the independently verified union of discoveries from every submitted crawler and Builderr's
  own crawlers. The union is cumulative and versioned: each verified addition creates a new pool hash
  and every entrant is rescored against that same latest version. The final union freezes only after
  all eligible final submissions have been verified."
- "Completed runs add to a cumulative, locked checked reference set used when scores are updated."
- "Abstention is reported separately and cannot satisfy coverage."
- Which of our facts can enter: by the text, any published finding in an external field family that
  Builderr independently checks. The text does not list the families, the read path or the checking
  method.
