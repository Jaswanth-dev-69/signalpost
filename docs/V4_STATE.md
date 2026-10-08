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

v1 anchor (7.79, older 1,200 fixture) is weaker: v1 proxy-200 run done, sample-100 pending.

## Next step

W1(b): labelled discovery run (400 companies, frozen v4-dev code) is in progress; then
`eval/discovery_rescore.py` for the W1(c) detection change (uncommitted in the working tree:
`identity.py` org-number detectors, `website.py` in-memory `_org_numbers_anywhere`, `domain_solver.py`
new proof branch).
