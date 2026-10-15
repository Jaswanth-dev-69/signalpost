# v6 state

Started Thu 15 Oct 2026 18:27 IST from `main` = `51bdc07` (the v5 submission commit; agent code
`c9f2049`). Tag `pre-v6` pushed at `51bdc07`. Hard decision point: Sat 17 Oct 15:00 IST; revisions
close 18 Oct. v5 stays the fallback submission.

Goal: raise official Recall as far as honest measurement supports while Evidence stays 30.00 (strict
identity gate, 0 wrong-company, every span verbatim) and Synthesis/UX output stays as it is.

## Contract, challenge page and board (re-fetched 15 Oct 18:35 IST)

Every page is byte-identical to the 14 Oct copies (`.work/web/d1014` vs `.work/web/d1015`): challenge
page with the board, evaluation contract, guidelines, sample site, the four starter briefs and the
kit tarball (`Last-Modified` 12 Oct). The board is still the one reviewed on 5 Oct.

| Question | Answer (source) |
|---|---|
| 411,160 | The **public universe** of eligible organisation numbers ("Public universe: all 411,160 eligible organisation numbers"; page: "Get all 411,160"), unchanged. It is not a batch. |
| Official batch size | Contract: "The current official input batch, supplied by Builderr (1,000 companies now; it may grow to 1,100)". Page: "Submit 1,000+ profiles"; the 5 Oct board recalculated every entry "against the same locked 1,500-company set" and "each scored entry ran twice". |
| Time limit | Not published: "A fixed time and resource budget supplied equally to every entrant"; "A timeout or missing result is not scored". |
| Bulk data | "Builderr provides the frozen official registry snapshot used for identity anchoring"; cached public-universe material is allowed if declared. |

The batch is at most about 1,500 companies, so the runtime design stands (1,500 projected
1,119–1,206 s on the v5 runs, hard deadline 1,500 s, forced deadline writes every envelope). No
re-derivation needed.

## 1. Forensics (offline; sample-100 run `vf2` of 15 Oct against Builderr's published sample facts)

Measured with `eval/scorer_mirror.py --sample .work/sets/sample100.json --no-pool` (kit read mode) and
the kit's own readers. Builderr's sample rows are Builderr's crawler output for the 100 sample
companies: websites, site-linked social profiles, LinkedIn posts and jobs (`experimental`), and the
website record's bounded `pages`.

| Family | Builderr's pool (sample) | We match | What we miss and why | Ceiling under the rules |
|---|---|---|---|---|
| Website | 97 companies | 74 | 8 sites Builderr's own gate rates non-exact; 11 with no homepage in the register (bulk or live) or the universe file (Builderr's own discovery; name-based guessing is ruled out); 1 dead register domain (`tgsnopec.com`); 1 verified under another domain (`studix.no` vs `studix.com`); 2 held back by the identity gate (a chain site, a managing agent's site) | about 74–75 |
| Social | 44 companies, 91 facts | 37 / 77 | all 14 missing facts belong to the 7 companies whose website we do not verify; inside covered companies 0 missed, 1 extra | tied to websites |
| News | LinkedIn posts for 17 companies (139) **and** the kit's company-site news fact for 16 companies | 0 LinkedIn; company-site 4 companies, 2 exact URLs | LinkedIn: not permitted (robots `Disallow: /`, sources brief). Company-site: the kit reader takes the deepest news-path page in the bounded `pages`; ours carry such a page only where a listing produced published items, so 3 companies with our dated news and 5 news-section pages we checked (`pervaco.no/nyheter`, `narvikgolf.no/nyheter`, `trondelag-betong.no/aktuelt/` …) are invisible to it | about 12–13 of 16 company-site companies |
| Hiring | LinkedIn jobs for 2 companies (8) | 0 | LinkedIn only; the kit has no company-site hiring reader | 0 in this sample; NAV and careers facts count only if Builderr's verifier accepts them |

What a news/hiring fact must look like (kit code re-read): `src/norway_company_agent/external_footprint.py`
validates an observation (`organisation_number`, `platform`, `signal_type`, `source_url`, `retrieved_at`,
64-hex `content_sha256`, `exact_entity`, `identity_proof`, `acquisition_mode` `permitted_public_page`,
`rights_status` `approved`, `evidence_span` for posts) and counts posts and jobs by unique
`source_url`. `scripts/extract_company_site_news.py` emits one `company_site`/`public_post`
observation per company: the deepest news-path page (`/news|press|aktuelt|nyheter|artikler|blog/`
segment) of a publishable website, with the page title as span. Builderr's v2 feedback keyed a news
fact as `title (datetime with offset)`, lowercased, from the article page. `scripts/score_competition_v3.py`
is an older proxy (identity, breadth, workforce, reviews, buzz, sentiment), not the current contract.

`eval/scorer_mirror.py --kit-news` (new) adds, on both sides, the kit reader's company-site news
fact. With it the v5 run scores 20.72 on Builderr's sample (news 2/29 companies) instead of 20.07.
