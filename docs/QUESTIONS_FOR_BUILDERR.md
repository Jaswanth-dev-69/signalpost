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

## E. Sample-site shape

13. **`external.handles`.** In your `/signalpost` sample, every `approved` handle is a social link
    from the company's own verified site, and `experimental` marks LinkedIn pages read from LinkedIn.
    Since rev3 our envelope carries `external: {"handles": [{platform, url, rightsStatus: "approved",
    source_url}]}` built only from site-linked, identity-gated links. We never read LinkedIn, so there
    is no `linkedin` block. Does the scorer read `external.handles`, and is the envelope's top level the
    right place (or inside `profile`)?

## F. Group sites and shared domains (rev4 calibration)

14. **How are group-site websites scored, and may we publish them with a relationship label?** Your
    v2 feedback lists `elopak.com` as ELOPAK ASA's website. In Enhetsregisteret that domain is the
    declared homepage of 2 entities, and the homepage is a JavaScript shell, so on-page identity cannot
    be shown. v3 withholds a registry-declared domain declared by 2 or more entities (labelled
    `shared_group_brand_or_provider_site`), because some are provider sites (one domain declared by
    663 housing entities) or franchise sites. In your sample, 16 websites sit on such shared domains.
    Your crawler and v3 agree on all 13 your gate marks exact, except 3 we miss for unrelated reasons
    (timeout, no registry homepage, a single-token name). The shared rule decides only 3 cases, all of
    which your own gate marks non-exact. Should a shared or group domain count for (a) the group's top
    entity only, (b) every declarant, or (c) none, and is publishing it with `relationship:
    group_site` acceptable?
