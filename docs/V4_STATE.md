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

## W3 fix found during W5 (07d1a92)

The first final run (59a4178) showed news items moving between sections for one company: on
strongpoint.com the `/news/` page carries `<link rel="next">` pointing at another language section
(`/no/nyheter/page/2/`), and the first pagination rule followed any rel=next. Now rel=next must also
stay under the listing's own path (it picks `/news/page/2/` there). Second, pagination used the same
20-fetch article budget as the re-read of kept items from their own pages, so on 917790531 4 items
fell back from their article to a feed citation; the re-read now has its own budget
(`FETCH_CAPS["news_upgrade"]`). Feed-cited news claims were 25 → 60 of 195 → 294 (proxy-200, c1 → c2):
honest (company feed, verbatim title and date), but the article page is the better source.

Wall time on proxy-200 is set by the NAV index, not by the web pass: in that run pass 2 ended at 140.7 s
and NAV finished at 300.4 s (NAV took ~285 s, ~250 s earlier today). To apply the +15% rule fairly, v3
itself is re-timed today under the same NAV conditions.

## W5: gates (candidate 07d1a92 "fin2"; final 850993e differs only in a stricter page-2 path match)

| Gate | Result |
|---|---|
| Unit tests | 149 pass (139 rev4 + 10 new W2/W3 tests) |
| Schema validator | 0 errors, 200/200 (both proxy-200 runs) |
| Determinism (proxy-200 run 1 vs run 2, same output file) | 172/200 identical after volatile keys; differences are page bytes (171 hashes, excerpts) plus 6 news items that switched between feed and article citation; **1 company** differs in claim values (980155889, the site served other event titles under the same timestamp); **0 duplicates, 0 change events** |
| Refresh (run 2 on run 1) | 200 compared, **0 material changes**, 0 failed |
| precision_audit (100 claims) | **99/100 supported, 0 wrong-company**, 20/20 web spans on the page. The 1: the website claim for 960221001 (kvalitet-sikkerhet.no); the audit wants the URL printed on the page, this homepage only has relative links; right company confirmed |
| evidence_audit (100 claims, 163 items) | all URLs load, **100.0% spans verbatim** (rev3/rev4: 99.3–99.4%), 70.6% hashes identical on re-fetch (dynamic pages; reported as measured) |
| Red team (35 high-risk names) | **0 false positives**, 35 safe abstentions (report unchanged) |
| Coverage vs v4-dev (proxy-200) | website 44 = 44, description 41 = 41, social 21 → 22 (live, Flav), news 23 = 23 companies and 196 → **295 facts (+50.5%)**, hiring 16 = 16 |
| Coverage vs v4-dev (sample-100) | website 72, description 67, social 40 unchanged; news 34 → **35** companies, 312 → **412** facts (+32%); hiring 20 = 20 |
| Synthesis / viewer diff vs v4-dev | synthesis text differs for 1/200 (Flav: social links loaded in this run); viewer DATA differs only in live page content and news items of 3–4 companies. No synthesis or viewer code edited |
| Runtime | proxy-200 wall is NAV-bound: v3 re-timed today **288 s** (NAV done 286.8 s); fin2 327 s (overlapping the red team) and 306 s → +6% to +13.5% vs v3 today. Web pass (code-dependent): v3 84 s, v4-dev 87 s, fin2 101–102 s (tail: slow sites now use their full 60 s budget). Throughput (summed request latency, what a 1,500 run scales with): v3 1,227 s, v4-dev 1,342 s, fin2 1,364 s = **+11% vs v3, +1.6% vs v4-dev**. 1,500-company estimate ≈ 15 + 150 + 916 ≈ 1,080 s (v3 ≈ 990 s), under the 1,500 s hard deadline |
| Clean clone (850993e, from GitHub) | fresh clone, no venv before install, `uv sync` exit 0 (warm uv cache; rev3 covered a cold install), `uv run signalpost --organisations docs/smoke-test/smoke-companies.jsonl --output … --bulk …`: exit 0 in 268 s, **100/100 envelopes, schema 0 errors** |
| Parity of the final commit 850993e vs 07d1a92 | same companies in every family on both sets; news facts 295 → 293 (proxy-200, live noise), 412 = 412 (sample-100); schema 0 errors; wall 275 s on both sets (NAV faster) |
| Span census, final output (proxy-200, every evidence item, `Accept: */*`) | 11,579 items on 1,134 URLs. Live-checkable 11,171 loaded: **4 fail the one-node check (99.96%)**, 2 fail the visible-text check (p22.no `<strong>` paragraph and a serit.no live change, each counted twice via the summary claim). 400 bulk-CSV items cannot be re-fetched (150 MB file): 200/200 verbatim in their snapshot records offline. 8 items not loaded (one site down at census time). v4-dev: about 546 failing items (4.9%) |
| Budget-cut crawls (per-company 60 s web budget) | 1–2 → 4 (proxy-200), 2 → 5 (sample-100); each cut company gained 10 news items and lost nothing; cuts only set `web_claims.crawl_complete=false` (used by refresh to avoid false removals), never an envelope state |

## Summary (stopped here; nothing packaged)

Candidate: **850993e** on `v4-dev` (pushed; `main` = v3 = 6074351 untouched). Code changes vs v3:
rev4's kept E5/E5b/E6/E7, plus W2 (verbatim single-node spans, effective dates) and W3 (news
pagination with its two fixes). W1c is reverted; W1 generator not implemented; W4 not triggered.

| Workstream | proxy-200 before → after (companies; facts) | sample-100 | Noise floor | Wrong-company | Wall / cost | Verdict |
|---|---|---|---|---|---|---|
| W0 scorer mirror | analysis | analysis | — | — | — | Fits kit/v2 within ±0.5 after one scale (λ ≈ 1.18); description and registry families rejected; any `available` kit-profile website counts; v1 anchor not comparable |
| W1a/b generator challenger | labelled gate recall 22.3% → 22.9% (weighted) | — | — | **2 unsafe name-rule passes** | discovery +32% | Not implemented |
| W1c proof detection | website 44 → 44 | 72 → 72 | ±1 | 0 | 0 | Reverted (labelled +1/400 only) |
| W2 evidence | coverage unchanged; failing spans ~546 → 4 of ~11.2k; effective dates on news and dated postings | evidence_audit 100% verbatim | — | 0 | 0 | Kept |
| W3 news pagination (+ fixes) | news 23 → 23; 196 → 293–295 facts | news 34 → 35; 312 → 412 | ±1–2 facts, ±1 company | 0 | requests +3%, summed latency +1.6% vs v4-dev (+11% vs v3); wall NAV-bound 275–327 s vs v3 today 288 s | Kept |
| W3 social / hiring | unchanged | unchanged | — | — | — | At ceiling (site-level misses; ATS/JS postings) |
| W4 shape hedges | — | — | — | — | — | Not triggered; ranked and prepared |

Recall and Evidence estimate (v4 = 850993e; mirror on sample-100 scaled by λ):
- Recall, case A (scorer reads website and social from the kit profile, as for the kit, and does not
  read our per-fact news/hiring claims): **15–19** (point 17.4), v4 = v3.
- Recall, case B (per-fact `dated_news` / `hiring_signal` claims are read): **26–34** (upper bound
  35.7 when the pool is mostly our own facts), v4 = v3 + 0.5 to 1.0 (news facts +32–51%).
- Evidence: **26–29**. v4 removes the last ~5% non-verbatim spans and adds effective dates; how
  deductions are computed is unknown (Q7).
- Total with Synthesis 12 and UX 8: case A **61–68** (qualifying needs Recall + Evidence ≥ 45),
  case B **72–83**.

Recommendation: 850993e is ready to be v4 (strictly better evidence, +32–51% news facts, no coverage
loss, 0 wrong-company). Not packaged (needs the user's go-ahead). Because the v3 feedback should land
around 9–10 October and decides between case A and B, the safer path is to read it first and add a
W4 hedge to v4 if news/hiring are still 0%, keeping v5 as the correction slot; if no feedback by
10 October, submit 850993e as is.

Questions still waiting on Builderr (`docs/QUESTIONS_FOR_BUILDERR.md`): Q1 which command scored us;
Q2/Q3/Q17 which shapes are read for news, hiring and social; Q4 value normalisation; Q5 scored
families; Q7 which evidence checks cost points; Q10/Q11 time budget and snapshot hand-off; Q13
`external.handles`; Q14 group sites (Elopak); Q15 span format for the accounts API (JSON vs XML);
Q16 whether `publishable:false` website records count.

## Packaging checks (2026-10-08, nothing sent)

| Check | Result |
|---|---|
| `git diff --stat 850993e HEAD -- . ':!docs'` | **empty**: every commit after the candidate is docs-only |
| Remote state | `origin/v4-dev` = `3b20ac6` = local HEAD; `origin/main` = `6074351476c4a005aed246f5f6eb7c7adb28244d` (v3, untouched) |
| Fresh clone from GitHub, **cold package cache** | clone of `3b20ac6` into a new empty directory, `UV_CACHE_DIR` an empty dir (0 entries → 82 MB), no `.venv` before install. `uv sync` exit 0 in **4 s**; `uv run python run_agent.py --organisations docs/smoke-test/smoke-companies.jsonl --output <tmp> --bulk <snapshot>` exit 0 in **266 s** |
| Envelopes from that clone | **100/100**, unique, input order preserved, all terminal; schema validator **0 errors**; run errors none; NAV index complete; 848 requests, p50 291 ms, p95 2,070 ms; claims 1,902 available / 617 not_available / 15 ambiguous / 5 blocked, and **0 non-available claims carrying a value** |
| Unit tests | **149 pass** |
| Submission email | drafted in `docs/V4_EMAIL.md` with `<HASH>` and `<CONTACT EMAIL>` placeholders; questions 1–6 of `QUESTIONS_FOR_BUILDERR.md` included (Q16 folded into question 6) |

Housekeeping: the session scratchpad (worktrees, run outputs, tools) was wiped by temp cleanup
between sessions, so the nine stale git worktrees were pruned; only the main checkout remains. Run
outputs from the earlier W0–W5 work are gone, but every tool that produced them is committed in
`eval/`.

**Open packaging gap:** `docs/smoke-test/` is still the rev3 artifact (its README says "rev3" and
cites commit `c052186`). The fresh-clone run above is exactly the v4 equivalent, so the smoke test
should be regenerated from the submitted commit before the email goes out — a decision for the user,
since it replaces a submission artifact.

# Session 3 (2026-10-08 evening): v4 on main, then P1–P5

## Step 0: orientation

- V3 feedback: **not arrived**. Push policy: push `main` as soon as the push gate passes.
- Re-fetched: contract byte-identical; challenge page unchanged (board "Reviewed 5 October", same 28
  rows, closes 21 Oct, revisions before 18 Oct); kit tarball ETag `8dcd521f…` unchanged (only the
  Last-Modified moved again).
- Git: tags `v3-submitted` = 6074351 and `v2-submitted` = 0ded711 created and pushed. Checks passed
  (6074351 is an ancestor of origin/v4-dev; `git diff --stat 850993e origin/v4-dev -- . ':!docs'`
  empty), then local `main` fast-forwarded to origin/v4-dev = 2d71e1a. `main` is pushed only after
  the push gate below.
- Workspace: persistent, gitignored `.work/` (sets, frozen code snapshots via `git archive`, runs,
  tools). Universe: `~/Desktop/SIGNALPOST/signalpost/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl`.

### Frozen files (Synthesis 12/12, UX 8/8)

| What | Where |
|---|---|
| Summary text | `src/norway_company_agent/synthesis.py` (`generate_company_synthesis`) |
| Viewer HTML and its DATA | `scripts/build_prototype.py` (`build`, `compact`, `public_signals`) |
| Call sites | `run_agent.py` lines that call `generate_company_synthesis` / `build_viewer_html` |
| Summary claim | `contract.py` block that emits `summary_profile` |

Guard: `eval/frozen_guard.py [--base REF]` fails if a frozen file changes or if any added/removed line
in `src/`, `scripts/` or `run_agent.py` names `generate_company_synthesis`, `synthesis_summary`,
`build_viewer_html`, `build_prototype` or `summary_profile`. Clean vs `v3-submitted` and vs HEAD.
The viewer is built from raw profiles with `external_by_org` empty, so envelope-only additions cannot
change viewer DATA (still diffed every time).

### Hypotheses, ranked by expected points per effort (sized before coding)

| # | Hypothesis | Family | Expected effect | Cost / risk |
|---|---|---|---|---|
| H1 | Read-path hedge: kit observation records (`public_post`, `job_posting`) built from the gated claims; then a `external.company_site` block in the sample's `compact()` shape | news, hiring | 0 if claims are read already; up to +10–18 recall if only these shapes are read | low; duplicate representation |
| H2 | Registry facts cite the per-entity API record already fetched, not the 150 MB bulk CSV | evidence | 1 non-re-fetchable item per company → 0 | low |
| H3 | Accounts API: an Accept-independent URL, or spans valid in both JSON and XML | evidence | ~16 financial spans per company robust to the verifier's Accept | low |
| H4 | Evidence completeness: effective dates on every dated claim, no stray values on non-available claims, no duplicate claims/evidence | evidence | removes residual checks | low |
| H5 | News depth: cap 20 → 30 / page 3 for sites at the cap | news facts | fact recall on ~10% of covered companies | budget cuts, time |
| H6 | TLS hostname mismatch on `www.` → try the bare domain (fageraasskogsdrift.no) | website | a few loaded homepages | low |
| H7 | Embedded JSON (`__NEXT_DATA__`, `application/json` script data) for JS-rendered news listings | news | 3–8 of 21 newsless verified sites have a listing but no static items | medium |
| H8 | Content-hash stability (70.6% identical on re-fetch): nothing honest to change (pages are dynamic); document | evidence | 0 | — |
| H9 | Several JobPosting nodes / posting links per careers page | hiring facts | postings are rare (3–4 per 200) | low |
| H10 | JSON-LD `sameAs` / icon-only social links | social | already read (`structured_social_links`); at Builderr's ceiling | — |
| H11 | Declared homepage redirecting to another domain without proof | website | rejected: would loosen the gate | — |
| H12 | One-node span for `<strong>`-led description paragraphs | evidence | 1 item per 200 | needs DOM-level extraction (feeds synthesis) — skip |

## Baselines today (2026-10-08, `.work/runs`)

| Run | proxy-200 web / news / hiring (companies; facts) | sample-100 | Web pass | Summed request latency | 1,500 projection |
|---|---|---|---|---|---|
| v3 6074351 | 44 / 23; 164 / 15; 17 | 72 / 35; 253 / 18; 22 | 77.4 s / 92.7 s | 1,270 s / 1,239 s | 990 s |
| main 2d71e1a | 44 / 23; 295 / 16; 18 | 72 / 35; 412 / 20; 24 | 91.3 s / 118.4 s | 1,337 s (+5.2%) / 1,496 s (+20.7%) | 1,033 s / 1,161 s |

Social (22; 45 and 40; 84) and description (41 and 67) are equal in both. Noise floor today: main run 1 vs
run 2 on proxy-200 differ in **no family** (companies and facts identical). Proxy-200 wall time is
NAV-bound (274–279 s for every run). Main is already +20.7% vs v3 in summed latency on the
website-rich sample-100 (+5.2% on proxy-200), so cost-adding changes have no headroom there under
the +15% rule.

Mirror (sample-100, pool = Builderr's sample + these runs; λ = 1.18 from the earlier kit/v2
calibration, whose runs were lost with /tmp): case A (kit profile read) v3 = main = 20.52 raw →
**17.4**; case B (claims read too) v3 39.81 → 33.7, main 42.00 → **35.6**.

## P3 / P4 sizing (offline on the baselines; nothing implemented)

| Hypothesis | Size | Verdict |
|---|---|---|
| H5 news cap 20 → 30 | 10/23 (proxy-200) and 14/35 (sample-100) news companies sit at the cap: up to ~100–140 more facts, at +4–6% requests and more budget cuts | Rejected: breaks the +15%-of-v3 cost rule on sample-100 (already +20.7%); 0 in case A |
| H7 embedded JSON (`__NEXT_DATA__`, `__NUXT__`) on newsless verified sites | 0 of 21 checked pages; 2 carry one JSON-LD `datePublished` (the page's own), already parsed | Rejected (0) |
| H9 several postings per careers page | postings found: 0 (proxy-200), 1 (sample-100) | Rejected (0) |
| H10 JSON-LD `sameAs` / icon-only social links | already read (`structured_social_links`, all anchors) | No change |
| H6 / P4 TLS hostname mismatch → bare domain | registry homepages not loaded: proxy-200 dns 4, robots 2, HTTP 500 2, empty document 1, TLS mismatch 1; sample-100 timeout 1, HTTP 403 1. The TLS case fails on both `www.` and bare host (certificate for another host); the empty one is a 239-byte stub; registry homepages already retry www/bare and http | Rejected (0 recoverable) |
| P5 discovery | no new idea; no search API offered | Not started |

## Next step

1. When the v3 feedback arrives: map its per-family percentages to case A/B in the Summary. If news
   or hiring is still 0.0%, implement W4 hedge 1 (kit observation records) on `v4-dev` with the same
   gates, and keep v5 as the correction slot.
2. With the user's go-ahead: regenerate `docs/smoke-test/` from the v4 commit, fast-forward the
   default branch to the v4 commit, fill `<HASH>` and `<CONTACT EMAIL>` in `docs/V4_EMAIL.md`, and
   send. Nothing is merged, tagged or sent yet.
