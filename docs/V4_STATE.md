# v4/v5 state (Recall and Evidence only)

Branch `v4-dev`, cut from `rev4-candidate` (66ec4ed). v3 = `main` =
`6074351476c4a005aed246f5f6eb7c7adb28244d`, submitted and frozen: never touched. Synthesis (12/12)
and UX (8/8) code is not edited; every change is diffed against the synthesis and viewer output on
proxy-200. Commits are `Builderr Agent <agent@builderr.local>` with no trailers; only `v4-dev` is
pushed (backup). No submission is packaged without the user's go-ahead.

Keep rule: gain above the noise floor, 0 wrong-company, red team clean, wall time at most +15% of
v3 on proxy-200 (v3 259–263 s, so at most about 300 s).

## Step 0: orientation (2026-10-08)

- **Builderr v3 feedback: not arrived** (the master prompt's placeholder was left empty).
- Re-fetched https://builderr.ai/challenges/signalpost and
  https://builderr.ai/docs/signalpost-evaluation-harness.md. The contract is **byte-identical** to
  `docs/briefs/web-evaluation-contract.md`. The challenge page is unchanged: same scoring text
  (50/30/12/8, 70% company + 30% fact recall per family), closes 21 Oct, revisions before 18 Oct,
  board still "Reviewed 5 October 2026", 37 submissions, 28 assessed, 0 qualified, same 28 rows.
- The starter-kit tarball was re-published (Last-Modified 2026-10-08 12:25 GMT, was 10-05), but its
  content is unchanged: every file equals our first commit `0dd1db7`, except `identity.py`, which is
  our own tightening in that commit. Newest file inside is dated 2026-09-27.
- Builderr's sample DATA (`/signalpost`, 100 rows) re-extracted: 97 websites (84 identity-exact),
  44 companies with site social links (91 links; 87 `approved` handles), LinkedIn posts for 17
  companies (139), LinkedIn jobs for 2 (8). No company-site news or careers shape.
- Anchors for the scorer mirror (W0): kit-like 13.07 / 26.98; v2 (0ded711) 8.05 / 24.99 with social,
  news and hiring at 0.0%; v1 (31cf298) 7.79 / 24.95 on the earlier 1,200 fixture, with "27.2% of
  companies had a verified website" and no social, news or jobs claims
  (`~/Desktop/SIGNALPOST/signalpost/TASK.md`).
- Also ruled out (branch `rev4-e3`, commit 43afa3c, not merged): E3 NAV employer homepage as a
  discovery source, about 2–3 extra companies per 1,500, 0 passes in our 360 companies.
- Earlier session scratch data (kit runs, proxy sets, sample copy) was lost with /tmp; it is
  regenerated in this session's scratchpad.

## W0: scorer mirror (analysis only; `eval/scorer_mirror.py`)

Runs (this session, scratchpad): unmodified kit (tarball), v2 = 0ded711, v1 = 31cf298, v4-dev =
c719957 (code = rev4-candidate b454207), on sample-100 (Builderr's DATA orgs) and proxy-200
(`eval/fixture_proxy.py`, seed 20261004, first 200). Wall: kit 180/244 s, v2 272/274 s, v4-dev
276/274 s (sample/proxy), v1 203 s (proxy). v4-dev proxy-200 phases: pass 1 ends 34.6 s, pass 2
(web) 87 s, NAV index ends the run at about 272 s, so proxy-200 wall time is NAV-bound; runtime
changes are judged by pass-2 time.

Formula per family: 0.7 × company recall + 0.3 × fact recall against a collection; Recall = 50 × mean
over the scored families. Collection = Builderr's sample facts (website record, site social links,
approved handles, LinkedIn posts as news, LinkedIn jobs as hiring) pooled with every run's facts as
the scorer is assumed to read them. Read modes: `kit` = `profile.evidence.website` (any `available`
record is a website fact; social from `value.social_links`); `kit_exact` = only
`publishable:true`; `auto` = kit shape if a profile exists, else scalar claims only (a list-valued
claim is not read; this is what v2's 0.0% social/news/hiring implies).

| Hypothesis (sample-100 unless noted) | kit | v2 | kit/v2 | Official 13.07/8.05 = 1.62 |
|---|---|---|---|---|
| 4 families (website, social, news, hiring), kit read `kit`, v2 read `auto`; pool = sample+kit+v2+v4 | 15.67 | 9.35 | 1.68 | **fits**: one scale λ = 1.18 gives 13.28 / 7.92 (both within ±0.25) |
| same, pool = sample+kit+v2 | 16.20 | 9.35 | 1.73 | fits within ±0.5 with λ = 1.20 |
| + description as a 5th family | 18.15 | 16.09 | 1.13 | **rejected** |
| registry families counted | — | — | ≈1.1 | **rejected** (every entrant has full registry coverage) |
| proxy-200 (pool = our runs only), website = any `available` | 15.77 | 8.92 | 1.77 | fits the ratio within 9% |
| proxy-200, website = `publishable:true` only (`kit_exact`) | 9.21 | 8.92 | 1.03 | **rejected** |
| 2 families only (website, social) | 32.4 | 18.7 | 1.73 | ratio fits, but needs λ ≈ 2.5 (implausible); news and hiring are scored families |

Tolerance: ±0.5 recall points per anchor after one shared scale λ (the official union holds more
entrants' facts than any local pool). The mirror passes for the ratio, which is its only real test
(λ is fitted); it cannot pin the number of scored families beyond "about four", and it says nothing
about how news and hiring are read, because no anchor has news or hiring above 0.

Findings:
1. Registry families and company description do **not** count toward Recall (ratio test).
2. The scorer counts **any `available` website record in the kit profile**, `publishable:false`
   included (proxy-200 test). Our v3/v4 profile carries the same records (74 on proxy-200, vs 44
   exact `official_website` claims), so website coverage is already at or above the kit's.
3. **The kit-vs-v2 gap is the social layer.** Sample-100: kit social = 7.5 points, v2 social = 0;
   v2's website is 1.2 points better; scaled by λ the gap is 5.3 vs 5.02 official. On proxy-200 the
   kit also wins on website (64 loaded registry homepages vs v2's 53 published).
4. v4-dev predicted (sample-100, λ = 1.18): **17.4 if only its kit profile is read** (website 78.9%,
   social 85.3%); **up to 35 if its per-fact news and hiring claims are read too** (news 77.4%,
   hiring 92.5% of a pool that is mostly our own facts, so this is an upper bound). News and hiring
   are worth up to 12.5 points each; a realistic union (other entrants' site news/careers added)
   puts them at roughly 5–8 points each if read.
5. Consequence: whether Builderr reads the per-fact `dated_news` / `hiring_signal` claims is worth
   about 10–18 recall points, far more than any discovery gain. That is Q2/Q3, and W4 if the v3
   feedback shows 0.0%.

v1 anchor (7.79): **not comparable**. Today v1 (31cf298) publishes 24 websites on proxy-200 and 42 on
sample-100 (v2: 53 / 73; v1 had no registry-declared rule), and its ambiguous claims carry no value,
so the mirror puts v1 at 0.45–0.58 × v2 against 0.968 officially. v1 was scored on another batch (the
1,200 fixture) against an earlier, smaller union, so it cannot test the mirror.

## W1: website discovery on labelled data (no change kept)

Ground truth: the universe (410,638 in the 2026-10-04 snapshot) has 44,793 companies declaring a
homepage, 28,571 on a domain no other entity declares; 28,340 after excluding platform domains and
skip forms. Target population (no declared homepage, 365,845): only **9.2% have a company e-mail
domain** (vs 76% of declarants) and 88% have no registered employees.

(a) Offline recall@k of the generator against declared domains (`eval` scratch tools):

| Generator | Mean candidates (no-homepage companies) | @1 | @3 | @8 |
|---|---|---|---|---|
| current (`generate_candidate_domains`) | 3.94 | 37.5% | 47.6% | **48.5%** |
| challenger: + first distinctive token (.no/.com), names containing a domain, STIFTELSEN stripped, ø→oe, .as, last token; lone tokens only if they occur in ≤ 30 registry names | 5.52 | 38.5% | 53.9% | **58.6%** |

Misses that no name rule can reach: 42% (unrelated brand domains).

(b) Live, 400 labelled companies (stratified none/5-19/20-99/100+ = 200/120/60/20), homepage treated as
undeclared, every candidate of both generators fetched and judged by the **unchanged** strict proof
(`eval/discovery_labelled.py`, frozen v4-dev code, 472 s). True site loaded 232/400; passes the
proof 113/400. Pipeline simulation (first pass wins), weighted to the no-homepage population:

| Config | Gate recall | Other-domain passes | Seconds/company |
|---|---|---|---|
| current generator, current proof | 22.3% | 17 | 6.6 |
| current generator, W1c detection | 22.7% | 17 | 6.6 |
| challenger, W1c detection | 22.9% | 22 | 8.7 (+32%) |

All 17 other-domain passes of the current code were hand-checked: same entity (own number on an
alternate domain, or the obvious own site). The challenger adds 3 true sites (ostnes.no,
skottneset.no via org number; askeladdensteinerbarnehage.no via name) but also 2 unsafe passes via the
name rule: fasaderehabilitering.no for OSLO FASADEREHABILITERING AS (a generic SEO title, very likely
another company) and boasas.no/akershave-apartments/ (the managing company's page). **Challenger
rejected** (fails 0 false positives; even restricted to org-number proofs it is about +2–4 companies
per 1,500 for about +9% web-pass time).

(c) Proof detection without loosening (commit 23e64da, candidate): own number in any format
(dotted, hyphenated, no-break space, NO…MVA, unlabelled footer), more labels, JSON-LD
vatID/taxID/identifier, accepted only when no other valid number is printed. Result: +1/400
labelled, **0 companies on proxy-200 and sample-100** (identical coverage, same pass-2 time 153 s on
sample-100). **Reverted** (fa8607e): not above the noise floor.

Why sample-100 sites are missed (live diagnosis of 12 Builderr sites we lack): single-token legal
names cannot pass the name rule (Slipeteknikk, Solvang, TGS); the registered municipality is not on the
site (The MICE Guru, Starina, Lapsen); a same-municipality homonym (Nordic Door); a franchise chain
printing another org number (dolly.no, correctly rejected). With the gate unchanged, discovery is at
its ceiling; expected gain per 1,500 from any measured W1 change is 0–4 companies.

## W2: evidence

Census tool `eval/span_audit.py` (re-fetch every cited URL once; raw / one-node / visible checks).
v4-dev proxy-200, all 11,190 evidence items on 1,078 URLs:

| Source | Items | Verbatim before | Cause | Fix |
|---|---|---|---|---|
| Regnskapsregisteret API | 3,309 | 100% with `Accept: */*` | The API answers XML to a browser-style Accept; spans are compact JSON (what we fetched and hashed) | none (honest); asked as Q15 |
| Bulk CSV (Enhetsregisteret) | 400 | 100% in the full CSV record (multi-line records) | — | — |
| NAV sitemap check | 344 | **0%** | span was our own sentence ("13511 active ads listed; …") | first `<loc>` text node of the fetched sitemap |
| Ambiguous websites (5 fields + summary) | 180 | **0%** | `"<title> (exact legal entity not established)"` | the title alone |
| Checked news listings | 12 | **0%** | `"title | page text"` composite | the page's own heading/title |
| Web claims, other | ~1,500 | 99.4% | listing window across title and date; body-text snippets ±90 chars across nodes | title and date as separate spans; body text quoted tightly (number or name only) |

After the fix (candidate, proxy-200): web families **1,693/1,695 one-node (99.9%)**, NAV **356/356**.
Residual: 1 description paragraph that starts with a `<strong>` name (p22.no; passes the visible-text
check, a one-node span would need DOM-level description extraction, which feeds synthesis) and 1
live page change (serit.no). Also added: `effective_at` = the article's own timestamp on both news
evidence items, and the posted date on site JSON-LD and NAV posting evidence (platform-linked
postings carry no date on the page and get none).

## W3: fact breadth

- Social (sample-100): v4-dev misses 14 of Builderr's site-linked social facts; 13 are site-level (the
  website is not loaded or not verified, see W1) and 1 is a link we never saw on the site. On sites we
  verify, social is at Builderr's level. No change.
- Hiring: careers page only for 15 of 16 companies (proxy-200); postings sit in ATS iframes or on
  third-party platforms (E4: 0 companies gained). No change.
- News: 8 proxy-200 and 11 sample-100 companies stopped at exactly 10 items (one listing or feed page);
  only 2–4 reached the cap of 20. **Change (7069108, kept): a listing showing fewer items than the cap
  is followed to its own second page (rel=next or a page-2 link under the same listing path, one
  fetch); a WordPress feed to `?paged=2`; WordPress REST `per_page` 10 → 20.** Same verified site only,
  each item still re-read from its own article page.

| Run (c1 = W1c+W2, c2 = c1 + pagination) | News companies | News facts | Other families | Requests | Wall |
|---|---|---|---|---|---|
| proxy-200 c1 → c2 | 23 → 23 | 195 → **294 (+51%)** | unchanged | 2,299 → 2,375 (+3.3%) | 275 → 288 s |
| sample-100 c1 → c2 | 34 → **35** | 313 → **412 (+32%)** | unchanged | — | 281 → 272 s |

Noise: between v4-dev and c1 (same crawl code) news facts moved by 1 and social by 1 company; pass-2
time ranged 87–114 s for functionally identical code, so request count is the cost measure (+3.3%).
Wall time 288 s = +10% vs v3's 261 s (limit +15% ≈ 300 s); proxy-200 wall is NAV-bound.

Scope guard (v4-dev vs c2, proxy-200): synthesis text differs for 1/200 companies (919399023 gains
"Declared social profiles: facebook, instagram, linkedin." because its social links loaded in this
run: data, not code); viewer DATA differs only in live page content (logos, excerpts, one
identity-assessment detail) and in news items for 2 companies (the viewer shows the top items only).
No synthesis or viewer code was edited.

## W4: shape hedges (not triggered; prepared only)

W4 applies only if Builderr's v3 feedback shows news, hiring or social still read as 0.0%. The
feedback has not arrived, so nothing is implemented. Ranked candidates if it does (W0 says each of
news and hiring is worth up to 12.5 recall points if read, realistically 5–8):

1. **Kit observation records** (`src/norway_company_agent/external_footprint.py` schema, which the
   kit's own `extract_company_site_news.py` emits): one record per news item (`platform:
   company_site`, `signal_type: public_post`) and per careers page or posting (`signal_type:
   job_posting`), with `source_url`, `retrieved_at`, `content_sha256`, `exact_entity: true`,
   `identity_proof`, `acquisition_mode: permitted_public_page`, `rights_status: approved`,
   `evidence_span`. Built from the same identity-gated facts as the claims. Risks: a second copy of
   each fact (the contract says the union removes duplicate facts; within one envelope it is a second
   representation, not a duplicate record across reruns); `public_post` might be read as buzz rather
   than dated news (no precision harm). Cannot create a wrong-company publication (same gate).
2. **Sample object style**: a `external.company_site` block with `posts` / `jobs` arrays using the
   sample's keys (`date_published`, `text`, `source`, `retrievedAt`, `hash`, `rightsStatus`,
   `sourceClass`). Never under `external.linkedin` (that would misstate the platform). Risk: read only
   if the scorer generalises beyond `linkedin`.
3. `profile.evidence.website.value.news` / `.jobs` lists: changes the kit-shaped profile (frozen);
   lowest priority.

## Next step

Final candidate = 59a4178 (W2 + W3; W1c reverted). W5 gates are running: proxy-200 twice into one
output (determinism + refresh), sample-100, then schema validator, precision_audit, evidence_audit,
span census, red team, synthesis/viewer diff, clean clone.
