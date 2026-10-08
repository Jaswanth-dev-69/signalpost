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

## Next step

W0: scorer mirror. Run the unmodified kit, v2 (0ded711) and v4-dev on sample-100 and proxy-200, then
compute per-family 70/30 coverage against the collection proxy and test which hypothesis reproduces
13.07 and 8.05.
