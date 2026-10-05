# Sources, secrets and outbound URL policy

What the agent reads, under which terms, and how it keeps requests safe. This is the "source rights,
secrets and outbound URL policy" item of the evaluation contract's official-run checks.

## Sources read

| Source | What for | Access and terms |
|---|---|---|
| Brønnøysundregistrene Enhetsregisteret bulk CSV (`data.brreg.no/enhetsregisteret/api/enheter/lastned/csv`) | Identity anchor, registry fields, declared homepage | Open data (NLOD). Builderr's frozen snapshot via `--bulk`, or downloaded once when absent |
| Enhetsregisteret API (`/enheter/{org}`, `/roller`, `/underenheter`, `/konsernstruktur`) | Live registry record, roles, subunits, group links | Open public API, no key |
| Regnskapsregisteret API (`data.brreg.no/regnskapsregisteret/regnskap/{org}`) | Latest filed annual accounts | Open public API, no key |
| NAV job-vacancy feed (`pam-stilling-feed.nav.no`) and public ad pages (`arbeidsplassen.nav.no`) | Hiring: postings whose employer organisation number is the company's or its subunits' | Open data (NLOD). The feed's published public token is fetched at run time from NAV's own endpoint; nothing is stored or configured |
| The company's own website: the registry-declared homepage, or a domain proven by the organisation number on the site | Website, description, social links, dated news, careers page and postings | Company-owned public pages; `robots.txt` honoured per origin |

Social and video profiles are recorded only as **links found on the verified company site**. The
agent never fetches LinkedIn, Facebook, Instagram, X, YouTube or TikTok pages. No search engine,
paid API, licensed feed, LLM or personal account is used. Third-party cost per run: 0.

## Secrets and configuration

- No secrets, API keys or environment variables are required or read.
- The one command is `uv run signalpost --organisations <batch> --output <envelopes.jsonl> [--bulk <snapshot>]`.
  Dependencies are pinned in `uv.lock`.
- The only cache is the local registry snapshot passed with `--bulk` (or downloaded to
  `brreg-enheter.csv.gz`). Every published claim is fetched during the run and carries its own
  retrieval time and content hash.

## Outbound requests

- Honest, identifying user agent: `builderr-signalpost-poc/0.1 (+https://builderr.ai)` (the starter kit's).
- Only public `http(s)` URLs. Every homepage, subpage and site-claims request, and every redirect,
  is resolved first: `localhost`, `.local`, and private, loopback, link-local, multicast or reserved
  addresses are refused (`website.assert_public_url`, `SafeRedirectHandler`).
- Pages beyond the homepage stay on the verified site's registered domain. Redirects off that
  domain are not followed for claims.
- `robots.txt` is checked per origin before page fetches. A disallowed page is recorded as
  `robots.txt disallows page`, and a disallowed homepage gives the state `blocked`.
- Politeness: at most one request per host every 0.35 s, per-family page budgets per site, timeouts,
  and byte limits (2 MB homepage, 1.5 MB other pages).
- No captcha, paywall or login bypass, no browser emulation, and no spoofed user agent. Content
  behind JavaScript or a login is reported as missing, never guessed.

## Publication rules applied

- Facts are published only for the exact legal entity: an organisation number on the site, the full
  legal name with the municipality, or the homepage the entity itself declared in the registry when
  no other entity declares the same domain.
- Group, brand, chain and provider sites (a domain declared by two or more entities) are labelled
  `shared_group_brand_or_provider_site` with `publishable:false`, never published as one company's
  website.
- Missing, blocked, ambiguous and failed are explicit states. Missing values are never written as
  zero.
