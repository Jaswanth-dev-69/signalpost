# Revision 3 state

Goal: find out why Builderr's scorer counted 0.0% for social profile, dated news and hiring signal in
v2 (0ded7110, 53.04 = Recall 8.05 + Evidence 24.99 + Synthesis 12 + UX 8), fix it, and resubmit
above 65. Branch `rev3`, cut from main at 0ded7110.

## Phase A: done (2026-10-05)

- All linked pages were fetched to `docs/briefs/web-*.md`. Findings, with quotes, are in
  `docs/SCORER_NOTES.md`.
- The official contract does **not** define field names, claim shapes, normalization, family
  weights, or the time budget. There is no public practice sample and no local scorer.
- Leaderboard of 5 Oct: the official batch is a **locked 1,500-company set**, and each entry ran
  **twice**. 16 of 28 entries (likely near-kit agents, whose envelope embeds `profile`) have
  Evidence 26.98 and Recall around 13.07, about 5 recall points above us.
- 65 needs Recall + Evidence ≥ 45. The best recall anyone has shown is 17.45.
- Leading hypothesis (to test in B): the scorer can't read our list-valued `social_profiles`,
  `dated_news` and `job_postings` claims, or can't verify their evidence. Social links come from the
  same homepage fetch as `official_website`, which does score, so a run-time cause can't produce
  exactly 0% social while website stays above 0.

## Phase B: done (2026-10-05)

- `eval/reconcile.py` (v2 code) recovers 1/4 named facts. Equinor careers found but unpublished;
  Sunnaas news sub-section missed; Elopak is a JS-shell declared homepage; MTM social recovered
  locally.
- Verdicts: H1 shape is the most likely cause of 0.0%, H2 contributes, H4 is confirmed for
  news/hiring, H3 is minor, H5 is not the cause at 1,500 companies. The table is in
  `SCORER_NOTES.md`.
- Baselines (v2): proxy-200 verified 26%, social 16%, news 14%, careers 9%. Large-60 58/45/45/32%.
  Proxy-200 wall time 272 s. Scratch outputs live in the session scratchpad (not committed).
- Benchmarks: `eval/fixture_proxy.py <universe> <out> --count 1200` (seed 20261004); first 200 =
  proxy-200. Universe: `~/Desktop/signalpost/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl`.
- Decision: Phase C order is C1 shape, C2 evidence, C4 discovery, C3 robustness, C5 runtime, C6
  precision.
- Open questions for Builderr are in `SCORER_NOTES.md` under UNKNOWN. Asked the user for the full
  per-family coverage table from the v2 email (website and description numbers would confirm H1).

## Phase C

- **C1 done.** One claim per fact: `social_profile` (canonical URL, handle lowercased except YouTube
  channel ids), `hiring_signal` (careers page `available` when its heading names careers, then each
  site or NAV posting), `dated_news` (`"Title (published_at)"` plus `title`/`published_at`/`url`).
  Every claim has its own evidence and a claim-level `source_url`. `published_at` keeps the
  source's own timestamp with its offset. Tests are in `tests/test_contract_rev3.py`. Reconcile 2/4
  (MTM, Equinor); `web_claims_check` passes.
  - Not done: a kit-style `profile` in the envelope. It is a duplicate representation and could
    make the scorer pick up unverified data, so I left it out pending Builderr's answer to
    UNKNOWN Q2.

- **C2 done** (commits 58f0d0b + this one).
  - Every evidence `claim_span` is a verbatim fragment of the cited page. There are no `" | "`
    composites; a live registry span is one compact-JSON fragment. Each evidence item records an
    `extraction_method`.
  - News items are re-read from their own article page (title span plus a separate raw date span).
    `published_at` is the page's own ISO string, kept as written; Sunnaas JSON-LD
    `2025-09-22T20:00:00+02:00` matches Builderr's key exactly.
  - JS-rendered listings fall back to `/sitemap.xml` news articles, newest lastmod first, fetched
    for their own dates. Sunnaas went from 0 to 10 items.
  - NAV postings: a title span plus a raw employer org-number span.
  - Viewer: a "Company news and hiring" section links every news item, careers page and NAV/site
    posting to its source page. The agent's hiring and activity answers use it when LinkedIn data
    is absent. Headless Chrome render checked.
  - Proxy-200 (C2): website 26.5%, social 16.0%, news 14.0%, hiring 9.5% (17 careers pages,
    8 postings), description 25.0%. Wall 255 s; pass 2 150 s, unchanged from v2.
  - Audits: `eval/precision_audit.py` 100/100 supported, 0 wrong-company.
    `eval/evidence_audit.py` (100 external claims, 153 evidence items): all URLs load, 99.3% of
    spans verbatim, 71% of hashes identical on re-fetch (dynamic pages).

## Next step

C4: discovery. Careers links in nav menus to depth 2, sitemap-driven careers and news URLs,
English paths. Then C3 (Accept header and HTTP 406; JS-shell declared homepages such as Elopak),
C5 and C6.

# Revision 3, phase 2 session (2026-10-05): kit baseline and parity

## Step 1.1 (in progress): kit baseline

- The original kit came from `https://builderr.ai/signalpost-starter-kit.tar.gz` (Last-Modified
  2026-10-05 12:05 GMT) and was unpacked in the session scratchpad, outside the repo. The repo's
  first commit is already modified, so it can't serve as the kit. `pyproject.toml` is identical.
- The kit has **no** `scripts/evaluate_agent.py`. That file is ours (commit 0dd1db7), so its family
  grouping is our own guess and not a Builderr hint.
- Kit envelope: `{run_id, organisation_number, state, started_at, completed_at, modules, profile}`.
  It has no `claims`, no `claim_span` and no `extraction_method`, and `effective_at` is null on
  every record. It still scores Evidence 26.98, against our 24.99 with spans and methods.
- In the kit, `profile.evidence.website.status` is `available` for **any** registry homepage that
  loads, whatever the identity verdict (`value.identity_assessment.publishable`). `social_links` is
  gated twice: the site must be exact **and** the handle must contain the legal-name tokens
  (`assess_social_identity`).
- Builderr's sample DATA (`/signalpost`, 100 rows; a copy is kept in the scratchpad) uses the same
  record shape (`web.value.social_links`, `identity_assessment`) plus `external.handles`
  (approved/experimental) and LinkedIn posts/jobs. It has **no** company-site news or careers shape.
  33 of its 97 websites have no registry homepage in today's BRREG (`scheduler: scrapy_resumable_v1`),
  so Builderr's own crawler discovers websites beyond the registry.
- Kit on proxy-200 (250 s wall, 8 workers): registry website loaded for 64 companies, identity-exact
  for 25, description 16, social 10 companies / 17 links, news 0, hiring 0.
- Kit on sample-100 (187 s): website 64 (exact 55), description 41, social 28/59. Builderr's
  sample: 97 (exact 84), description 60, social 44/91.
- Early read: our v2 measured **more** exact websites (26%) and social (16%) on proxy-200 than the
  kit (12.5% / 5%), yet scored about 5 recall points less. That points to the envelope shape (what
  the scorer can read) rather than discovery.
- New: `eval/kit_parity.py` (per-family companies/facts for kit, ours and the sample, with
  kit-only/ours-only companies) and `docs/QUESTIONS_FOR_BUILDERR.md`.

## Steps 1.2 to 1.5: parity, causes and fixes (done)

Runs are in the session scratchpad: `kit-*` is the unmodified kit, `v2-*` is the worktree at 0ded711, and
`rev3b-*` is this branch at 9bcfcb8. Tool: `eval/kit_parity.py`. "Claims" reads our
OUTPUT_CONTRACT claims. "Profile" reads our envelope the way the kit's is read
(`profile.evidence.website`).

Companies covered (facts in brackets):

| Family | Kit proxy-200 | v2 proxy-200 | rev3 claims proxy-200 | rev3 profile proxy-200 | Kit sample-100 | rev3 claims sample-100 | Builderr sample | Cause of any gap | Fix |
|---|---|---|---|---|---|---|---|---|---|
| Website, any loaded registry homepage | 64 | 53 | 44 | **74** | 64 | 71 | 97 | Kit shows non-exact homepages as `available` (with `publishable:false`); our claims say `ambiguous` | Kit envelope embedded: same records, same shape |
| Website, identity-exact | 25 | 53 | **44** | 44 | 55 | **71** | 84 | None (ours higher). 9 group/brand sites withdrawn, see below | — |
| Description | 16 | 50 | **41** | 29 | 41 | **66** | 60 | — | — |
| Social profile | 10 (17) | 32 (83) | **22 (45)** | 22 (45) | 28 (59) | **39 (83)** | 44 (91) | v2 read 0.0% officially: the list-valued claim was not read, and the kit-shape `social_links` was absent | Kit envelope embedded; kit handle gate |
| Dated news | 0 | 29 (195) | **23 (164)** | — | 0 | **34 (252)** | 17 (LinkedIn) | No kit shape exists | C1/C2 claims kept |
| Hiring signal | 0 | 4 (8) | **16 (18)** | — | 0 | **18 (21)** | 2 (LinkedIn) | No kit shape exists | C1 careers page + postings |
| Registry: identity / financial records / roles / subunits | 200 / 564 / 906 / 263 | | | 200 / 565 / 906 / 263 | | | | Claims carry only the latest accounts | Kit profile embedded: full parity |

Proxy-200 wall time: kit 250 s (8 workers), v2 261 s, rev3 267 s (+6 s from the shared-domain scan running during pass 1).

What changed, and why:

1. **Kit envelope embedded** (commit 2c6fc3b). Every envelope now also carries `run_id`, `state`,
   `started_at`, `completed_at`, `modules` and `profile`, exactly as the kit emits them. This is the
   only shape known to score (13.07 recall). The profile is the source-snapshot record the claims are
   built from, so it repeats the same values and does not publish competing ones. Missing modules after
   the deadline are `budget_exhausted`, not `submission_error`.
2. **Kit social handle gate** (2c6fc3b). v2 published every social link on a verified site. On
   sample-100, 26 of 102 failed the kit gate, among them another company's LinkedIn (Ragasco to
   `amexgas`), a photographer's personal pages for a gallery, and seven Facebook post ids. The gate is
   now kit-or-domain-label: the handle must contain the legal-name tokens or the verified site's domain
   label (at least 4 characters). Cost: sample 41→39 and proxy 26→22 companies, still 1.4–2.2× the kit.
3. **Verbatim registry spans** (9bcfcb8). 120 of 270 BRREG-API spans in v2/rev3 were `" | "`-joined
   composites that appear nowhere in the source. All financial, roles and subunit spans were affected,
   on every company. The kit has no spans at all, so it cannot fail this check. Now each span is one
   compact-JSON fragment, and bulk spans are two adjacent quoted CSV cells. Re-check: 443/443 API spans
   verbatim, and bulk spans are verbatim in the snapshot. Financial claims carry `reporting_period`, and
   their evidence carries `effective_at`.
4. **Shared declared domains** (9bcfcb8). The registry-declared rule (added in v2) published group,
   chain and provider sites: `klp.no` for a KLP fund (13 declarants), `eiendomsmegler1.no` (3),
   `AGR.com` for ABL Group Norway (3), `ulstein.com` (6) and `ringbo.no` (76, a cable provider). The
   contract says such relations are "labelled, not collapsed". A domain declared by 2 or more entities
   is now labelled `shared_group_brand_or_provider_site` and is not published. This withdrew 9
   proxy-200 websites, all reviewed by hand as group, brand or provider sites.

Evidence elements, kit vs rev3:

| Element | Kit | rev3 |
|---|---|---|
| Claim-level source URL | No claims; one record per module | Every claim cites evidence with its own URL |
| Retrieval time | Per module record | Per evidence item, plus the kit records |
| Reporting/effective period | `effective_at` null | `reporting_period` on financial claims and `effective_at` on their evidence |
| Content hash | Per module record (fetched bytes) | Per evidence item (fetched bytes), plus the kit records |
| Extraction method | None | Every evidence item |
| Span validity | No spans | Registry API 443/443; web 99.4% (evidence_audit, 163 items, all URLs reopen) |
| Availability state | Module states | Claim states plus kit module states |
| Refresh metadata | started/completed, per-module final_timestamp | Same, plus `run` and `changes` |
| Prior snapshots / refresh diff | None in the batch runner | None yet (Phase 2) |

Audits on rev3 proxy-200: schema validator 0 errors; `precision_audit` 100/100 supported, 0
wrong-company; `evidence_audit` 163/163 URLs load, 99.4% spans verbatim, 70.6% hashes identical on
re-fetch (dynamic pages; reported as measured); red team 35 high-risk companies, 0 false positives;
122 unit tests pass.

Verdicts on the inferences:

- **I1 (partly true).** The nine 13.07/26.98 entries fit the unmodified kit. But v2 was *not* below
  the kit in what it found: it was above it in every external family. The gap is in what the scorer
  could read (no kit `profile`, list-valued social claim) and probably in invalid spans (item 3) and
  group sites (item 4).
- **I2 (still unproven).** The C1 per-fact claims stay as the claims layer. Social now also sits in the
  kit's known location. News and hiring have no known shape; only Builderr can confirm them
  (QUESTIONS Q3/Q4).
- **I3 (not testable locally).** Registry families are at full parity through the embedded profile
  either way.

**Decision: ours, with the kit envelope as the base layer** (not a kit fork). Our output is ≥ the kit
in every external family and every evidence element on proxy-200 and the sample, the precision audit
is clean, and wall time matches v2. The Phase-1 gate is passed.

## Next step

Phase 2: run the same 50 companies twice back to back (determinism, false changes, duplicates). Add a
previous-envelopes input for refresh: preserve prior evidence and emit typed material changes with the
kit's `refresh.diff_profile` shape. Then walk the official-run checks one by one.
