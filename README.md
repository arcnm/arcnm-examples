# ARCNM examples

Runnable examples for the [ARCNM](https://arcnm.io) API — manufacturing
should-cost from CAD and drawings.

Everything here runs against a real part committed to this repo
([`parts/shaft_thread.step`](parts/shaft_thread.step)), so you can clone and
run without finding a file first.

```bash
git clone https://github.com/arcnm/arcnm-examples
cd arcnm-examples
export ARCNM_API_KEY="…"        # Dashboard → Settings → API keys
export ARCNM_ENV_ID="…"          # Dashboard → Environments, or see below
python quickstart/main.py
```

You need your own API key — create one at
[arcnm.io](https://arcnm.io) under **Settings → API keys**. Nothing here ships
a shared key, and no example writes your key to disk.

> **Want to try the shape of the API without an account?**
> [`mock/`](mock/) runs a local mock server from the public OpenAPI spec. No
> key, no cost, no calculations — just the request and response shapes.

---

## What's here

| Path | What it does |
|---|---|
| [`quickstart/`](quickstart/) | One part → one price, in cURL, Python and TypeScript |
| [`recipes/quote-a-part/`](recipes/quote-a-part/) | A quote with its full cost breakdown and audit lineage |
| [`recipes/bulk-rfq-triage/`](recipes/bulk-rfq-triage/) | Many parts at once, ranked by unit cost |
| [`mcp/`](mcp/) | Connect Claude Code, Claude Desktop or Cursor to ARCNM |
| [`mock/`](mock/) | A local mock of the API, from the public spec |

Full documentation: **[arcnm.io/docs](https://arcnm.io/docs)** ·
API reference: **[arcnm.io/docs/api](https://arcnm.io/docs/api)**

---

## The two things you need

**An API key.** `X-API-Key` header on every REST call.
[Authentication →](https://arcnm.io/docs/authentication)

**A costing environment.** A calculation prices a part against an environment
— your machines, your rates. Create one in the dashboard, or list the ones you
have:

```bash
curl -s https://api.arcnm.io/api/v1/environments/ \
  -H "X-API-Key: $ARCNM_API_KEY" | jq '.data[] | {id, name}'
```

[Environments →](https://arcnm.io/docs/concepts/calibration-environments)

---

## The part

`parts/shaft_thread.step` is a threaded shaft — a real STEP file, not a
primitive. Small enough to read, complex enough that extraction has something
to find: turned features, a thread, and the tolerances that drive cost.

Bring your own by passing a path:

```bash
python quickstart/main.py path/to/your.step
```

---

## No SDK?

Not yet — and rather than ship one we can't maintain well, the OpenAPI spec is
public and typed clients generate from it in about thirty seconds:

```bash
npx @hey-api/openapi-ts \
  -i https://api.arcnm.io/api/v1/openapi-public.json \
  -o ./client
```

Any OpenAPI generator works — `openapi-generator`, `openapi-python-client`,
Kiota. [Details →](https://arcnm.io/docs/sdks)

---

## For agents

ARCNM is MCP-native. The server is listed in the
[MCP Registry](https://registry.modelcontextprotocol.io) as `io.arcnm/arcnm`:

```json
{ "mcpServers": { "arcnm": { "url": "https://api.arcnm.io/mcp-server/mcp" } } }
```

See [`mcp/`](mcp/) for per-client setup. Machine-readable indexes:
[`llms.txt`](https://arcnm.io/llms.txt) ·
[api-catalog](https://arcnm.io/.well-known/api-catalog)

---

## Issues

Something here not working? [Open an issue](https://github.com/arcnm/arcnm-examples/issues).
Questions about the API itself are better at
[hello@arcnm.io](mailto:hello@arcnm.io) or in the
[docs](https://arcnm.io/docs).

MIT licensed — copy anything you find useful.
