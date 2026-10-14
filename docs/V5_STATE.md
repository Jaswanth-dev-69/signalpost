# v5 state (final revision)

Started 14 Oct 2026 18:31 IST from `main` = `956f53be` (tag `pre-v5`, pushed). Deadline for the
final push and report: 17 Oct 18:00 IST. Evidence (30.00) is the invariant: identity gate
unchanged, 0 wrong-company, red team 0/35, every span verbatim, every fact with evidence.

Scoring context (user): C300 directional estimate Recall 14.34, Evidence 30.00, Synthesis 7.20,
UX 2.67 (54.21). Board (5 Oct): v2 Synthesis 12 and UX 8. Board grades are multiples of 2.4
(Synthesis, five levels) and 1.6 (UX); 7.20 is level 3 of 5. Soham: "No dated-news item matched the
verified pool. Capture title, direct URL, publication date and exact company match."

Rubric wording (re-fetched 14 Oct, unchanged): Synthesis "explain what the company does, what
changed and what remains unknown, with sources for its conclusions" / "explain the company, changes
and unknowns without making unsupported claims". UX "find, compare and verify company information
on desktop and mobile".

Sets: `sample-100` (Builderr public sample), `proxy-200` (seed 20261004), `set-300` (new,
`fixture_proxy` seed 20261014; 2 overlaps with proxy-1200).

## WS-A Synthesis and UX

### Forensics (v2 `0ded711`, v3 `6074351`, main `956f53b`, same companies, same day)

| Finding | Data |
|---|---|
| Summary code unchanged v2 → main | `synthesis.py` identical; summary text identical for 90/100 sample companies (the 10 differ by data only) |
| (a) v3 withdrew websites/socials, so summaries carry fewer facts | verified websites v2 → main: proxy-200 53 → 44, set-300 100 → 85; social links shown in the viewer: proxy-200 79 → 41. These were precision fixes (Evidence 24.99 → 30.00) and stay withdrawn |
| Envelope grew; summary buried | 17 KB (v2) → 58 KB (main) per company; `summary_profile` was the last claim, after up to 20 news claims and the embedded kit profile |
| (b) viewer built from raw profiles | news, hiring and the summary never reached the viewer; header and tiles hard-coded "100-company showcase · 22 exact LinkedIn profiles", "0 exact LinkedIn profiles", "0 public posts + jobs"; lab wording ("POC diagnostic", slices); no compare view; on a phone the hero filled the first screen |
| (d)/(e) summary content | one templated paragraph: no "what changed", no per-sentence sources (the claim cited all evidence ids), Norwegian labels unexplained, sparse companies got a registry-only paragraph |

### Changes

- `synthesis.py`: `envelope_summary` builds the summary from the envelope's own published claims
  after refresh: Company, What it does (register industry and activity text, verified site's own
  description), Size and finances, **What changed** (movements between the reported years, latest
  role updates, former names, newest dated item, refresh result or "first snapshot"), Leadership and
  locations, Online presence, Hiring, Recent activity, **Not known or not established**, Sources.
  Numbered markers per sentence; each source lists its evidence ids. The claim moves to the front of
  `claims`, is mirrored in a top-level `summary` and `profile.synthesis_summary`; the profile-level
  summary remains the fallback (deadline flush, errors).
- Deliberate contract additions (same fetched records, no extra requests, appended after all earlier
  claims so earlier evidence ids do not move): `registered_activity` (register `aktivitet` text),
  `former_names` (`historiskeNavn`), `financial_history` (earlier years of the accounts response;
  every figure cited by a value-literal span with the year's end date as `effective_at`).
- `viewer.py` (new; `scripts/build_prototype.py` stays the kit's lab viewer): built from envelopes.
  Search (name, org number, place, industry, activity, role holder), filter tiles and filters, sort
  by revenue/growth/employees/news, saved searches, compare up to four (table, CSV, share link), deep
  links `#org=`, summary with linked sources, three-year financials with change, leadership,
  locations, web/social, hiring, news, changes, quick questions, evidence table (span, URL, fetch
  time, SHA-256), export JSON. Mobile: list → profile → back; tables scroll inside their box.
- `eval/frozen_guard.py` is now the regression guard: same saved profiles built with `pre-v5` and
  the working tree; only the summary and the listed additions may differ.
- `eval/synthesis_validator.py`: every date, amount, employee count, URL and quote in a summary must
  match an available claim; markers must resolve to sources whose evidence ids exist.

### Checks so far (offline, saved profiles of 14 Oct runs)

| Check | Result |
|---|---|
| Regression guard vs `pre-v5` | clean on sample-100 and proxy-200 (300 profiles) |
| Summary traceability | 300/300 |
| Unit tests | 157 + 13 new pass |
| Headless browser, 100 companies | 0 console/page errors, ready 0.24 s, profile < 70 ms, compare/deep link/mobile flow pass |
| Headless browser, 1,500 companies | 20.6 MB (rich sample replicated), ready 0.61 s desktop / 0.50 s mobile emulation, all checks pass; random population 9.5 KB/company |
