# Questions for Builderr (Signalpost, revision 3)

Entry: Jaswanth, v2 commit `0ded7110aaeaa3d36bd586ff525f86be128741bf` (Recall 8.05, Evidence 24.99).
Each question names the exact choice it decides for us. A one-word answer is enough for most.

## A. How the envelope is read

1. **Which command did you run for our v2?** Our README still showed the kit's
   `scripts/run_competition_batch.py`; our submission email gave
   `uv run python run_agent.py --organisations <in> --output <out>`. Which one produced the scored run?
2. **Which part of the envelope does the scorer read for external facts?** (a) the `claims` list in the
   `OUTPUT_CONTRACT.md` shape (`field`, `value`, `availability`, `evidence_ids`), (b) the kit's
   `profile.evidence.website.value` record (`final_url`, `social_links`, `identity_assessment`), or
   (c) both. If both carry the same fact, is it counted once?
3. **Claim field names.** Which `field` values are recognised for: company website, social profile,
   dated news, hiring signal? Ours are `official_website`, `social_profile`, `dated_news`,
   `hiring_signal`. Is a repeated `field` (one claim per profile, article or posting) read, or must a
   family be one claim with a list `value`?
4. **Value normalization for matching.** Your v2 feedback showed `elopak.com`,
   `facebook.com/mtmskogservice`, `https://www.equinor.com/careers` and
   `bedre sosial funksjon etter hjerneskade (2025-09-22t20:00:00+02:00)`. Are values matched after
   lower-casing and stripping scheme/`www`? Is a news item matched on title + datetime, on the article
   URL, or on either? Is a careers page URL a hiring fact on its own (no posting needed)?

## B. Which families count

5. **List of external field families** that feed the 50 recall points, and their weights. Do
   *company description*, *leadership* (registry roles), *locations* (registry subunits) or
   *financials* count toward Recall, or only toward Evidence/precision?
6. **Company website when on-page identity is weak.** The kit reports the registry-linked homepage as
   `status: available` with `identity_assessment.publishable: false` when the name is not proven on
   the page (e.g. a JavaScript-only homepage). Does the scorer count such a record as a published
   website fact? If yes, is it counted against precision when it is correct?

## C. Evidence (30 points)

7. **Which checks cost our v2 the 5.01 evidence points** (or the 3.02 points between 26.98 and 30)?
   A list of check names would let us fix the right thing.
8. **Span and hash verification.** Is `claim_span` checked against the raw HTML or the visible text?
   Is `content_sha256` compared with a live re-fetch (dynamic pages change), or only required to be
   present and well-formed?
9. **"Source snapshots".** The contract lists source snapshots as an envelope element. Is a
   per-evidence `content_sha256` + `retrieved_at` enough, or do you expect the fetched page body (or
   a stored snapshot path) in the result?

## D. Run environment

10. **Time and resource budget** for the 1,500-company batch (wall seconds, CPU cores, memory), and
    is it exposed to the agent (flag or environment variable)?
11. **Frozen registry snapshot.** How is it handed to the agent (path, flag, env var)? Our agent
    downloads the BRREG bulk file when `--bulk` is absent; does that download count against the
    budget or get blocked by the network policy?
12. **Network policy.** Are company websites, `arbeidsplassen.nav.no` and `data.brreg.no` all
    reachable from the evaluator? Any rate limit or proxy?
