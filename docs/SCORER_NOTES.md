# Scorer notes (revision 3)

What Builderr's official scorer is known to do, with sources. Everything was fetched on
2026-10-05 into `docs/briefs/web-*.md`:

| Page | Saved as |
|---|---|
| https://builderr.ai/challenges/signalpost (page, #scoring, leaderboard) | `web-challenge-page.md` |
| Full evaluation contract `/docs/signalpost-evaluation-harness.md` | `web-evaluation-contract.md` |
| Permitted sources `/starter-briefs/signalpost-sources.md` | `web-permitted-sources.md` |
| Test and improve your crawler `/starter-briefs/signalpost-learning-harness.md` | `web-test-and-improve.md` (= local `test and improve.md`) |
| Company research guide `/starter-briefs/signalpost-agent-playbook.md` | `web-company-research-guide.md` (= local copy) |
| Full brief `/starter-briefs/signalpost.md` | `web-full-brief.md` (= local `full brief.md`) |
| Rules `/guidelines` | `web-rules.md` |
| Winning agents `/winning-agents` | `web-winning-agents.md` (no Signalpost content) |
| Agent basics, loops and outcomes `/start#agent-resources` | `web-agent-basics.md` (no scoring content) |
| Sample site `/signalpost` (100 profiles embedded as `const DATA=[…]`) | `web-sample-site.md` (text only; the data was analysed below and not committed) |

The starter kit tarball (Last-Modified 2026-10-05) matches what this repository started from. Neither
the kit nor the repo contains a public practice sample with expected facts, or a local scorer (A2).
None of the four named organisation numbers appears anywhere except 811730912 in
`eval/web_claims_check.py`; 923609016 appears only as a synthetic test fixture. The contract's
"Local checks" (`npm run check:signalpost*`) are Builderr-internal and not published.

## 1. Field families, weights, recall formula

- Formula (contract): "For every external field family, coverage is 70% company recall and 30%
  individual-claim recall against the independently verified union of discoveries from every
  submitted crawler and Builderr's own crawlers." Example: 70% × 75% + 30% × 60% = 70.5% "for that
  information type. This feeds the 50 recall and coverage points".
- Family list: **not published**. Names that appear in Builderr's v2 feedback: *Company website*,
  *Social profile*, *Hiring signal*, *Dated news*. The brief's required sections cover "4. Verified
  official website and company-owned profiles" and "5. Hiring and dated public activity from
  permitted sources". *Description* and *foundation record* are unconfirmed. The sample site's
  coverage dimensions are company / financials / people_places / website / footprint, which is a UI
  grouping, not the scorer's.
- How the families combine into the 50 points (equal weights or not): **not published**.
- "Companies covered" = company recall: share of the pool's companies with ≥1 fact in that family
  for which we have ≥1 accepted fact. Inferred from the job-postings example; the exact definition
  is not published.
- "Abstention is reported separately and cannot satisfy coverage." `not_available`, `ambiguous` and
  similar states earn nothing.
- Sparse batches: "fewer than 15 positive company-field opportunities across at least three external
  field families" means recall is reported as not measured.
- "Material" is only used as in "material wrong-company publication … can put an entire website,
  brand and set of facts under the wrong profile". It has no numeric definition.

## 2. Claim shape

- `OUTPUT_CONTRACT.md` (kit, minimal) shows one claim object
  `{field, value, availability, confidence, evidence_ids}` plus evidence
  `{id, source_url, source_class, retrieved_at, content_sha256, claim_span}`. Its only example field
  is `official_website` with a scalar URL value. It does not say whether a field may repeat, what
  other field names are recognised, or whether list values are allowed.
- Official contract: "Envelopes must contain legal identity, claims, evidence references,
  availability states, source snapshots, refresh metadata and errors."
- The kit's reference runner `scripts/run_competition_batch.py` describes itself as the
  "Evaluator-owned Signalpost batch contract". It emits a *different* envelope:
  `{run_id, organisation_number, state, started_at, completed_at, modules, profile}`, where `profile`
  holds the full evidence records. Social links sit in
  `profile.evidence.website.value.social_links = [{platform, url}]`, the same structure as Builderr's
  own sample-site data. Our envelope has no `profile`, and therefore no source snapshots.
- Our v2 publishes `social_profiles`, `dated_news` and `job_postings` as one claim each, with a
  **list of objects** as the value and several `evidence_ids` that are not tied to individual items.
  `official_website` and `company_description` are scalar.

## 3. Value normalization used for matching

Not published. Indirect evidence:

- The feedback example values are `elopak.com` (website as registered domain),
  `facebook.com/mtmskogservice` (no scheme, no www), `https://www.equinor.com/careers` (hiring signal =
  careers page URL) and `bedre sosial funksjon etter hjerneskade (2025-09-22t20:00:00+02:00)` (news =
  title + ISO datetime with offset). The `t` is lowercase, which suggests the whole key string is
  lowercased rather than the date being parsed.
- Kit `normalize_social_url` and Builderr's sample data use `https://facebook.com/<handle>`: www
  stripped, canonical host, path case kept, share/plugin URLs rejected. Ours is a fork of the same
  function, so our social URLs are already in that form.
- Whether news is matched by title + datetime, by URL, or by date only is **unknown**. If the datetime
  string must match exactly, date-only values (`2025-09-22`) would never match.

## 4. Source URL, claim_span, content_sha256, "reopenable"

- Source policy: "Every claim records source URL or source identifier, retrieval time,
  effective/reporting date where relevant, content hash and extraction method." We emit no
  extraction method per evidence item.
- Playbook: "Every published claim should point to a snapshot plus a selector, character span, table
  cell or PDF page."
- v2 feedback: "For every external claim, retain the exact public page, retrieval date and the text
  that supports the claim, and make that evidence reopenable from the result."
- The source URLs in the examples are the homepage (website), the company homepage that carries the
  link (social), **the careers page itself** (hiring) and **the article page itself** (news, not a
  listing page).
- How `claim_span` and `content_sha256` are verified (re-fetch and substring? visible text or raw
  HTML?) is **not published**. Our social `claim_span` is the link's href, which is in the raw HTML
  but not in the visible text. Our news evidence points at the listing page where the item was seen.

## 5. Precision and evidence (30 points)

- Page: "We check that each fact belongs to the right company and has a valid source and date. Wrong
  or unsupported facts lose points." Contract measurement list: exact-company precision,
  wrong-company publications, per-field precision, evidence-span validity, crawl completion, refresh
  correctness, false-change rate.
- Leaderboard of 5 Oct: evidence scores sit on near-integer steps (29.00, 28.99, 28.14, 26.98,
  26.92, 24.99, 23.99, 22.98, 21.00, 20.68, 8.00), which suggests roughly one point per failed check.
  We have 24.99, so about 5 checks or deductions. Which ones is **unknown**. Candidates to test:
  synthetic registry spans that are not verbatim in the source, no extraction method, list claims
  whose evidence does not support individual items, refresh or false changes ("Each scored entry ran
  twice"), and reporting period missing on some claims.

## 6. Run environment

- Batch: the contract says "1,000 companies now; it may grow to 1,100". **The leaderboard reviewed on
  5 Oct says "the same locked 1,500-company set" and "Each scored entry ran twice."**
- Budget: "A fixed time and resource budget supplied equally to every entrant". The value is
  **unknown**. "A timeout or missing result is not scored."
- Secrets: "server-side secrets supplied through documented environment variables only". No time
  budget variable or flag is published.
- Registry: "Builderr provides the frozen official registry snapshot used for identity anchoring." How
  it is handed to the agent (path, flag, env var) is **unknown**. Our agent downloads the BRREG bulk
  file if it is absent.
- Network policy: "the same … network policy … for everyone". Details are **unknown**.
- LLM: "Each run has a small external API budget, and if you need a model key for scoring, ask and we
  will supply one." Credentials tied to the entrant's own account are not usable.

## 7. Permitted sources

- "Public pages whose terms and robots policy permit the submitted access pattern"; "Search results
  generate candidates; they are not claim evidence"; "A profile or domain must resolve to the exact
  legal entity before its facts are published"; "Social or video profiles linked by the verified
  company site, subject to the destination platform's access terms".
- No user-agent rule and no rate limit are published. An honest, identifying bot UA is consistent
  with the policy, and nothing requires a browser UA.

## Leaderboard facts (5 Oct 2026, 28 assessed, 0 qualified)

- Ours: Recall 8.05, Evidence 24.99, Synthesis 12, UX 8, total 53.04.
- 16 of 28 entries share Evidence 26.98, and 9 of those have exactly Recall 13.07 (the other 7 sit
  between 12.97 and 13.99). This looks like near-kit agents, which suggests the scorer reads the
  kit's envelope (profile with `social_links`) well. All of them out-recall us by about 5 points.
- Best recall is 17.45 (with Evidence 26.92). Best evidence is 29.00.
- **Arithmetic: 65 needs Recall + Evidence ≥ 45** with Synthesis 12 and UX 8, i.e. Recall ≥ 20.0 at
  our current 24.99, or ≥ 16.0 at 29.0. No entry has ever shown Recall ≥ 16 together with
  Evidence ≥ 29.

## Phase B findings (v2 code, run locally on 2026-10-05)

B1 `eval/reconcile.py` on the four named facts recovers **1/4**:

| Family | Company | What v2 emits | Why it misses |
|---|---|---|---|
| Website | Elopak (811413682) | `official_website` = `ambiguous` | Registry declares `www.elopak.com` and it loads, but the homepage and its sub-pages are JS shells (15 visible chars). The declared-domain gate rejects it for "page has no substantive content". The only static signal is a sitemap with 1,454 same-domain URLs. |
| Social | MTM (811730912) | `social_profiles` list with `https://facebook.com/MtmSkogservice` | Recovered locally (case-insensitive). The official 0.0% must come from how the claim is read (list of objects, mixed-case path) or verified (span = raw href). |
| Hiring | Equinor (923609016) | `job_postings` = `not_available` with careers-page evidence | We found `https://www.equinor.com/careers` but publish nothing when it lists no postings. Builderr's fact *is* that careers URL. |
| News | Sunnaas (883971752) | `dated_news` = `not_available` | Only `/om-oss/nyheter/` was checked and it yielded no dated items. The expected article sits in a sub-section (`/fag-og-forskning/…/nyheter-rkr/…`), and its fact needs the article's own datetime with offset. |

B2 hypotheses:

| # | Hypothesis | Test and evidence | Verdict |
|---|---|---|---|
| H1 | Claim shape: list of objects per field is not read | MTM is recovered locally, yet social is 0.0% officially. Social links come from the **same homepage fetch** as `official_website`, which does score. 16 kit-format entrants (envelope embeds `profile` with `social_links`) out-recall us by about 5 points. v1 to v2 added news and NAV hiring and recall moved only +0.26. | **Most likely cause** (indirect; only Builderr can confirm) |
| H2 | Normalization | Social path case is kept (`MtmSkogservice` vs `mtmskogservice`). The hiring value form (careers URL) is never emitted. News dates are date-only while the key carries the full datetime with offset. | **Contributes** (hiring and news certainly) |
| H3 | Large-entity fetch | 60 sampled ASA/HF/SF or 500+ staff, our UA. Blocked 1 (2%), source_error 3 (5%), HTTP 406 on 3 sub-pages, 3 JS shells (5%). 35/60 verified sites, and of those 27 have social, 27 news, 19 a careers page. | **Minor** (JS-shell homepages; 406 on missing Accept) |
| H4 | Discovery | Equinor's careers page was found but not published. The Sunnaas news sub-section was not discovered. Site job postings appear for 1-5% of companies. | **Confirmed** for hiring and news |
| H5 | Environment and scale | Proxy-200: pass 1 ≈ 0.1 s/company, pass 2 ≈ 0.57 s/company wall at 32 workers, NAV index about 250 s fixed (in parallel). Estimated wall: 1,500 ≈ 17 min (under the 25-min deadline), 3,000 ≈ 33 min (deadline fires, about a third of web passes become `failed`), 5,000 and 10,000 mostly `failed`. A flush still publishes social for processed companies, so it cannot produce 0.0% social while website stays above 0. | **Not the cause** at 1,500. Scaling risk above about 2,500 |

Local baselines (v2, our UA). Proxy-200: verified website 26%, social 16%, dated news 14%, careers page
9%, site postings 1%, NAV postings 1%. Large-60: 58 / 45 / 45 / 32 / 5 / 18%.

**Decision (Phase C order):**

1. C1: shape and normalization. One claim per fact: `social_profile` (canonical URL, case-insensitive
   handles lowercased), `hiring_signal` (careers-page URL, `available`, plus one claim per posting),
   `dated_news` (`"Title (published datetime)"` with `title`, `published_at` and `url` keys). Each claim
   gets its own exact-page evidence. (A kit-compatible `profile` block was considered and left out.
   It would duplicate every claim and could expose unverified data. It needs Builderr's answer to
   UNKNOWN Q2 first.)
2. C2: evidence. News evidence moves to the article page; datetime from meta, JSON-LD or `<time>`;
   extraction method recorded.
3. C4: discovery. Sitemap and nav menus for news and careers, sub-sections, English paths.
4. C3: robustness. Accept headers (406), JS-shell declared homepages via a sitemap liveness signal
   (identity rule unchanged).
5. C5: runtime ordering and a time budget that scales with batch size.
6. C6: precision checks.

## UNKNOWN (ask Builderr)

1. Which external field families are scored, with what weights, and do *description* and
   *foundation record* count?
2. Which claim `field` names (or envelope paths) does the scorer read for social profile, hiring
   signal and dated news? Are list-valued claims read, or must each fact be its own claim, and may a
   field repeat?
3. Is matching against the union by normalized value (e.g. `facebook.com/handle`,
   `title (datetime)`, careers URL), and is a company "covered" by any accepted fact or only by a
   matching one?
4. How are `claim_span` and `content_sha256` verified (raw HTML or visible text, live re-fetch), and
   what does "reopenable from the result" require beyond `source_url`?
5. Which checks cost our run the missing 5.01 evidence points?
6. What are the time and resource budget and the exact invocation for the 1,500-company batch: is
   the frozen registry snapshot passed (how?), and is there a flag or env var for the budget?
7. Is the "public practice sample" with expected facts published anywhere?
