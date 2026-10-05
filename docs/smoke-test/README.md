# 100-company smoke test (rev3)

Clean-clone run on 2026-10-05: a fresh `git clone` at commit c052186, an empty virtualenv, `uv sync`,
then the one command. There was no local registry file, so the agent downloaded the BRREG snapshot
itself.

```bash
uv sync
uv run python select_entry_batch.py --universe <public universe> --count 100 --output smoke-companies.jsonl
uv run signalpost --organisations smoke-companies.jsonl --output out/smoke-envelopes.jsonl --run-id smoke-rev3
```

| Check | Result |
|---|---|
| Envelopes | 100/100, unique, in input order; schema validator 0 errors |
| Entity states | 100 `complete`; module states all terminal (website: 10 complete, 89 not_found, 1 blocked_policy) |
| Claims | 1,887 available, 617 not_available, 15 ambiguous, 5 blocked; 0 non-available claims carrying a value |
| Wall time | 469 s, of which about 390 s was the 147 MB snapshot download; 77 s for the 100 companies once loaded |
| Requests | 800; p50 317 ms, p95 2,251 ms; 0 HTTP 429; third-party cost 0 |
| NAV index | complete (12,856 active ads) |

The batch is the random seeded sample from `select_entry_batch.py`, so it is web-sparse: 89/100
companies have no registry homepage. Files: `smoke-companies.jsonl`, `smoke-report.json` (the run
report) and `smoke-envelopes.jsonl.gz`.
