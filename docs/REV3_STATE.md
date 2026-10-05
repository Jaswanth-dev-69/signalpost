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

## Next step

C1: per-fact `social_profile` / `hiring_signal` / `dated_news` claims plus `legal_identity` and a
kit-compatible `profile`, with unit tests built from the four named examples.
