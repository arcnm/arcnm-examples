# Connect an agent to ARCNM

ARCNM ships an MCP server generated from the REST API, so an agent can quote
parts, rank cost drivers and read process plans as typed tools.

```
https://api.arcnm.io/mcp-server/mcp        streamable HTTP
io.arcnm/arcnm                              MCP Registry
```

## Credentials

The server accepts **either** credential in the `Authorization: Bearer …`
header:

- an **API key** (`ak_live_…` / `ak_test_…`) — long-lived, revocable, scoped.
  Best for an agent you run yourself. Mint one at arcnm.io → Settings → API
  keys.
- an **OAuth token** — interactive clients can sign in instead: ARCNM runs
  OAuth 2.1 with dynamic client registration and a consent screen where you
  pick the org and the scopes (read-only by default). Nothing to copy.

Both resolve to the same tenancy and scope checks.

```bash
export ARCNM_MCP_TOKEN="ak_live_…"
```

## Claude Code

```bash
claude mcp add -t http arcnm https://api.arcnm.io/mcp-server/mcp \
  --header "Authorization: Bearer $ARCNM_MCP_TOKEN"
```

## Cursor

`~/.cursor/mcp.json`, or project-scoped `.cursor/mcp.json` — see
[`cursor.json`](cursor.json) here:

```json
{
  "mcpServers": {
    "arcnm": {
      "transport": {
        "type": "http",
        "url": "https://api.arcnm.io/mcp-server/mcp",
        "headers": { "Authorization": "Bearer ${ARCNM_MCP_TOKEN}" }
      }
    }
  }
}
```

## Anything else that speaks MCP

```json
{ "mcpServers": { "arcnm": { "url": "https://api.arcnm.io/mcp-server/mcp" } } }
```

Clients that support OAuth will discover the flow from
[protected-resource metadata](https://api.arcnm.io/.well-known/oauth-protected-resource/mcp-server/mcp)
(RFC 9728 — the resource path is appended to the well-known prefix) and prompt you to sign in.

## Worth asking it

Once connected, these work as plain requests — the agent picks the tools:

- *"Quote part BRACKET-001 at lot sizes 1, 10 and 100, and tell me where the
  cost goes."*
- *"Which three features drive the most cost on this calculation?"*
- *"Compare this part across my costing environments and rank them."*
- *"Read the process plan and tell me which operation dominates cycle time."*

Full reference: [arcnm.io/docs/mcp](https://arcnm.io/docs/mcp)

> Tools are annotated with `readOnlyHint` and `destructiveHint`, so a
> well-behaved client knows which calls only look and which ones change
> something. Uploading files and starting calculations happens over the REST
> API — see [`../quickstart/`](../quickstart/).
