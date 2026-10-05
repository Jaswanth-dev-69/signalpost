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

## Noise floor (frozen v3, same inputs)

| Set | Runs | Spread (companies) | Spread (facts) |
|---|---|---|---|
| proxy-200 | 4 (261, 263, 257, 261 s) | **0 in every family** | **0 in every family** |
| large-60 | 3 (285, 277, 277 s) | 1 in every family (one website the first run missed) | social 6, news 7, hiring 1 |

So on proxy-200 any difference is real; on large-60, ±1 company is noise.

## E5, E5b, E7, E6 (measured, all kept)

| Experiment | proxy-200 | large-60 | sample-100 | Wall proxy-200 | Verdict |
|---|---|---|---|---|---|
| E5 careers depth 2 + sitemap + wider probes; full news probe set | hiring +1 / −1 (the −1 was a budget cut) | +1 everywhere (noise) | hiring **+2** | 270 s | Keep (with E5b) |
| E5b careers before news | hiring **+1, −0** vs v3 (Scanmast via sitemap/depth 2; Eltele no longer cut) | noise | — | 261 s | Keep (gain above noise; robustness) |
| E7 406 → `Accept: */*`; one homepage retry on timeout/429/5xx; 401/403 → `blocked` | no coverage change (the 500s still fail on retry) | Statkraft, Tomra, Jula now `blocked` (were `failed`) | no change | 260 s | Keep (robustness, honest states, no downside) |
| E6 news cap 10 → 20 (same sources, own article page each) | news facts 163 → **196** (+20%; 7.09 → 8.52 per covered company), companies unchanged | 120 → 137 (+14%, above spread 7) | 251 → **312** (+24%) | 264 s (+1.5% vs E7) | Keep (cost well under +5%) |

Wrong-company hits: none seen in any run (audits on the candidate are below).

## E2 and E3 finished (candidate-only; not implemented, per "no new sources")

- **E2 Wikidata**, under the unchanged strict proof for discovered domains: 58 candidates tested (18
  from our sets, 40 from the registry-comparable pool). **14 pass, 0 wrong-company.** 5 passes are on a
  domain other than the registry homepage, and each is the same organisation's current or alternate
  site printing its own org number (nsf.no for Norsk Sykepleierforbund, bufdir.no for Bufdir, ...). On
  our 360 companies only 2 would be added. Bulk agreement with registry homepages is 88.8%, so
  Wikidata cannot serve as an anchor.
- **E3 NAV employer homepage** (`ad_content.employer.homepage`, already read by v3 and unused).
  Employers are **subunits**, so they were mapped to the parent with the BRREG subunit API. Against the
  parent's registry homepage: **81.8% agreement on 132 comparable** (the field is free text:
  teamtailor.com, google.com, staffing agencies, kirken.no, politiet.no). Candidate-only. 168/300
  sampled employers point beyond the registry homepage. Of 40 such candidates (ATS, generic and shared
  hosts excluded), 37 load and **15 pass the strict proof, 0 wrong-company** (synsam.no, inn.no,
  musti.no, haugalandmuseet.no, ...). This is the most promising lead for raising website coverage
  without a new source: it uses data we already read, with the gate unchanged. Not implemented now.

## Summary (stopped here; v4 not packaged)

Candidate branch `rev4-candidate` (code = commit b454207, all kept changes; v3 = 6074351 untouched).

| Experiment | proxy-200 before → after (companies; facts) | Noise floor (proxy / large) | Wrong-company | Wall vs v3 | Verdict |
|---|---|---|---|---|---|
| E5 careers depth 2, sitemap, probes; news probes | hiring 16 → 17 (with E5b); sample-100 hiring 18 → 20 | 0 / ±1 | 0 | +0–3% | **Kept** |
| E5b careers before news | removes budget-cut careers losses | 0 / ±1 | 0 | 0% | **Kept** (robustness) |
| E7 406 fallback, homepage retry, 403 → `blocked` | no coverage change; 3 large companies now honestly `blocked` | 0 / ±1 | 0 | 0% | **Kept** (robustness) |
| E6 news cap 20 | news facts 164 → 196 (7.13 → 8.52 per covered company); large-60 +14%, sample-100 +24% | facts 0 / ±7 | 0 | +1.5% | **Kept** |
| E4 ATS/newsroom links | 0 companies gained | — | — | — | Not implemented |
| E7 JS-shell sitemap liveness | 0 qualifying sites | — | — | — | Not implemented |
| Shared-domain narrower rule | decides 3 sample cases (+Elopak), below 30 | — | — | — | Not implemented → Q14 |
| E1 OSM | 60.7% agreement, +2 candidates, unclear ODbL use | — | — | — | Skipped |
| E2 Wikidata | 88.8% agreement; 14/58 pass strict proof, 0 wrong; +2 on our 360 | — | 0 | — | Candidate-only, not implemented |
| E3 NAV employer homepage | 81.8% agreement; 15/37 candidates pass strict proof, 0 wrong | — | 0 | — | Candidate-only, not implemented (best lead) |

Candidate checks (proxy-200, run twice into one output): **263 s** both runs (v3 average 261 s, so
+0.8%); 139 unit tests pass; schema 0 errors; determinism 173/200 identical (the rest are page-byte
hashes), 0 duplicates, **0 change events**; refresh 200 compared, 0 material changes;
precision_audit **100/100, 0 wrong-company**; evidence_audit 164/164 URLs load, 99.4% spans verbatim.
Output shape unchanged (no new fields, same claim names, same profile and `external`).

Net effect vs v3: same company coverage in every family except hiring (+1 on proxy-200, +2 on
sample-100), and about +20% dated-news facts. Expected score impact is small: hiring company recall
up about 1 point of that family, news fact recall up within news's 30% fact weight.

Questions still waiting on Builderr (`docs/QUESTIONS_FOR_BUILDERR.md`): Q1 which command produced our
scored run; Q2/Q3 claim names and envelope paths read for news, hiring and social; Q4 value
normalization; Q5 which families count toward Recall; Q7 which evidence checks cost points; Q10/Q11
time budget and whether `--bulk` is supplied; Q13 whether `external.handles` is read and where; Q14
how shared or group-site websites are scored (Elopak) and whether a `group_site` label is acceptable;
plus whether a search-API key can be provided.

Next step, if approved: E3 as a discovery candidate source (NAV employer homepage → unchanged strict
proof), measured with the same keep rule. It uses data v3 already reads; no new source.
