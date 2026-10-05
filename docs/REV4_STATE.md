# Revision 4 state

Branch `rev4`, cut from `main` = v3 = `6074351476c4a005aed246f5f6eb7c7adb28244d` (submitted; never
touched). Goal: more Recall and Evidence on top of v3, using only permitted, exact-company methods.
Output shape is **frozen** until Builderr's feedback on v3: no renamed claim fields and no changes to
the kit profile, `external.handles` or evidence fields. Coverage is added only in shapes v3 already
emits.

Keep rule per experiment: company coverage rises, wrong-company count stays 0, and wall time stays
within +15% of v3 on proxy-200 (v3 259–263 s, so at most about 300 s).

Order (the user's 2026-10-06 instruction): E5, E4, E7, E6; stop and report; then E1–E3.

## Baselines (v3 code, worktree at 6074351)

| Set | Wall | Website exact | Description | Social | News | Hiring |
|---|---|---|---|---|---|---|
| proxy-200 (seed 20261004) | 261 s | 44 | 41 | 22 (45) | 23 (164) | 16 (18) |
| large-60 (seeded 20261006: ASA/HF/SF or 500+ staff; 34 have no registry homepage) | 285 s | 24 | 24 | 17 (41) | 14 (113) | 25 (84; NAV postings reach companies without a site) |
| sample-100 (Builderr's /signalpost DATA) | 263 s | 71 | 66 | 39 (83) | 34 (251) | 18 (21) |

Tool: `eval/compare_runs.py BASE NEW` gives per-family companies, gained, lost, facts and facts per
company.

## E4 Third-party careers/newsroom links from the verified site (measured, not implemented)

- Off-site links scanned on the homepage and careers page of every verified site in the three sets
  (v3 output). Careers links to ATS hosts: Teamtailor (5 companies), FINN employer pages (3), and one
  each of Workday, Oracle Cloud and ApplicantPro. Newsrooms: 1 Mynewsdesk and 1 IR site. Also seen and
  correctly excluded: sister companies' careers pages (hotel groups) and social share buttons.
- Every company with an ATS careers link **already has a hiring signal** in v3 (its own careers
  page). Company coverage gain is **0**; at most about 6 extra link facts across 360 companies, at the
  cost of a new third-party dependency. Fails the keep rule, so nothing is committed.

## Shared-domain calibration (the Elopak lead; v3 rule kept)

- In Builderr's sample-100, 16 websites sit on domains declared by 2 or more registry entities (13
  of them identity-exact by Builderr's own gate). Builderr assigns the site to the sample company in
  every case, including non-top entities (Storebrand Bank on storebrand.no, Peab Bygg on peab.no) and
  3 companies that are not declarants at all. Builderr follows on-page identity, not declarant counts.
- v3 agrees on 10/16. 3 misses have other causes (timeout; no registry homepage; a single-token name).
  The other 3 (two vestbo.no, one kitchn.no) are decided by the shared rule, and Builderr's own gate
  marks all three non-exact. On Builderr-exact cases the shared rule cost **0**.
- The proposed narrower rule (top entity or name-matching declarant, labelled `group_site`) would
  decide only those 3 sample cases plus Elopak: far below 30 comparable cases. Not implemented. The
  evidence is Q14 in `QUESTIONS_FOR_BUILDERR.md`.

## E1 OpenStreetMap (measured, skipped)

- One Overpass query (`ref:NO:orgnr`, Norway, tags only): 11,154 features in 22 s; 5,068 org numbers
  with a website, almost all **subunits** (outlets). Only 117 are main entities. Against registry
  homepages: **60.7% agreement on 28 comparable**; disagreements are chain brands, franchises and
  municipal sites.
- On our 360 companies, matching via their registered subunits: 2 agree, 0 disagree, **2 beyond**
  (one blocked by robots.txt). ODbL share-alike for a derived database is unclear for our use.
  Skipped under the rules (failed calibration, unclear terms, near-zero yield).

## E2 Wikidata (measured, candidate-only; not implemented)

- The property was found through `wbsearchentities` (type=property): **P2333**, Norwegian
  organisation number. The licence is CC0.
- Bulk SPARQL (P2333 + P856, one query, 2 s): 7,342 organisations with a website. Against registry
  homepages: **88.8% agreement on 4,319 comparable** (483 disagree, mostly rebrands or alternate
  domains, some wrong, e.g. wordpress.com). Fails the 98% bar, so candidate-only.
- On our 360: 36 have a Wikidata website, 18/18 agree where we have a verified site, 18 are beyond it.
  Under the unchanged strict proof for discovered domains, **2 pass** (Aprila Bank, Peppes Pizza; org
  number on site). 10 large companies (Jotun, Wilson, TGS, Instabank, Sporveien, Spar Kjøp, Magnora,
  Statkraft, …) pass the kit's on-page name gate but not our strict proof. Publishing them would need a
  new gate rule, which is not allowed. Yield +2/360 is below what is worth a new runtime dependency,
  so it is not implemented.
