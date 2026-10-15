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
