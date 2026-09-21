# Recipes

Each one is a single script you can run against the part in this repo, or your
own. They mirror the prose recipes at
[arcnm.io/docs](https://arcnm.io/docs/recipes/quote-a-part) — the difference
is that these execute.

| | |
|---|---|
| [`quote-a-part/breakdown.py`](quote-a-part/breakdown.py) | One part, its full cost breakdown, and what the audit blob carries |
| [`bulk-rfq-triage/triage.py`](bulk-rfq-triage/triage.py) | A folder of parts, priced concurrently and ranked by unit cost, to `triage.csv` |

Both need:

```bash
export ARCNM_API_KEY="…"     # arcnm.io → Settings → API keys
export ARCNM_ENV_ID="…"      # arcnm.io → Environments
pip install requests
```

## On pacing

`triage.py` submits four at a time and honours `Retry-After` on a 429 rather
than inventing its own backoff. That matters at 200 parts: a rejected call
costs nothing, but a client that retries impatiently turns one 429 into
several. The reasoning is in
[bulk upload pacing](https://arcnm.io/docs/recipes/bulk-upload-pacing).

## Not here yet

The prose docs also cover [ERP
integration](https://arcnm.io/docs/recipes/erp-integration) and [teaching an
environment from your
actuals](https://arcnm.io/docs/recipes/teach-from-actuals). Both are worth
converting — open an issue if you want one next, or send a PR.
