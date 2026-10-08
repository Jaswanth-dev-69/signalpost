# 100-company smoke test (v4)

Clean-clone run of **v4, commit `24fa82fb11654a5620139b13c01e33abc01ffb80`** (agent code identical to `ba77e4d`; later commits change only `docs/`), cloned from
https://github.com/Jaswanth-dev-69/signalpost into an empty directory with an empty package cache
(`UV_CACHE_DIR` pointing at a new empty directory) and no virtualenv. Only the declared install step,
then the one command:

```bash
uv sync
uv run python run_agent.py --organisations docs/smoke-test/smoke-companies.jsonl --output out/smoke-envelopes.jsonl --bulk brreg-enheter.csv.gz --run-id smoke-v4
```

`--bulk` pointed at a local copy of the Brønnøysundregistrene bulk snapshot; without it the agent
downloads the snapshot itself (about 150 MB). The input is the same seeded random 100-company batch as
the rev3 smoke test (`select_entry_batch.py`), so it is web-sparse: most companies have no registry
homepage.

| Check | Result |
|---|---|
| Install | `uv sync` exit 0 in 2 s with an empty cache |
| Run | exit 0 in 267 s wall (265.6 s inside the agent) |
| Envelopes | 100/100; unique True, input order preserved True, zero silent drops True, all terminal True; schema validator 0 errors |
| Website module states | {'not_found': 89, 'complete': 10, 'blocked_policy': 1} |
| Claims | 1,887 available, 618 not_available, 15 ambiguous, 5 blocked; 0 non-available claims carrying a value |
| Companies with a published fact | website 7, social 2, dated news 2, hiring 0 |
| Hedge records (`external.observations`) | 24 kit observation records, one per published news item, careers page or posting |
| Requests | 844; p50 301 ms, p95 1895 ms; HTTP 429 web 0, registry 0; third-party cost 0 |
| NAV vacancy index | complete True (13692 active ads) |

Files: `smoke-companies.jsonl` (input), `smoke-envelopes.jsonl.gz` (the 100 envelopes) and
`smoke-report.json` (the run report).
