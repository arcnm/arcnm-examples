# Mock the ARCNM API locally

Try the shape of the API with **no account, no key and no cost**. Useful for
wiring up an integration before you have credentials, for CI, and for
demonstrating a flow offline.

```bash
docker run --rm -p 4010:4010 stoplight/prism:5 \
  mock -h 0.0.0.0 https://api.arcnm.io/api/v1/openapi-public.json
```

Then point any example at it:

```bash
export ARCNM_API_BASE="http://127.0.0.1:4010/api/v1"
export ARCNM_API_KEY="mock"        # not validated by the mock
export ARCNM_ENV_ID="00000000-0000-0000-0000-000000000000"
python ../quickstart/main.py
```

Or with the compose file here:

```bash
docker compose up
```

## What you get, and what you don't

The mock serves the **real, current** OpenAPI spec — every endpoint, with
correct paths, parameters, status codes and response shapes. It is generated
from the running API, so it cannot drift from it.

It returns **example data, not calculated data**. No geometry is read, no
process is planned, no cost is computed. A `unit_cost` from the mock is a
placeholder from the schema, not a price.

So it answers *"what does this request look like, and what comes back"* —
which is most of an integration — and nothing about whether a number is right.
For that you need a key.

## Validating your requests

Prism validates incoming requests against the spec, which makes it a decent
linter for your client:

```bash
docker run --rm -p 4010:4010 stoplight/prism:5 \
  mock --errors -h 0.0.0.0 https://api.arcnm.io/api/v1/openapi-public.json
```

With `--errors`, a request that violates the schema gets a 422 describing what
is wrong, instead of a cheerful example response. Point your integration tests
at that and you will find a missing required field before production does.

## Pinning the spec

The command above fetches the live spec each start, so your mock tracks the
API. To pin a version instead, save it and mount it:

```bash
curl -o openapi.json https://api.arcnm.io/api/v1/openapi-public.json
docker run --rm -p 4010:4010 -v "$PWD:/spec" stoplight/prism:5 \
  mock -h 0.0.0.0 /spec/openapi.json
```

Pinning is the right call for CI — a spec change should break a deliberate
update, not a random Tuesday.
