# Connect an agent to ARCNM

ARCNM hosts an MCP server, so an agent can price a part, explain and compare
its cost, read the process plan and nest sheet-metal orders as typed tools.
The full guide, with every tool and prompt, is
**[arcnm/arcnm-mcp](https://github.com/arcnm/arcnm-mcp)**.

```
https://api.arcnm.io/mcp-server/mcp        Streamable HTTP
io.arcnm/arcnm                              MCP Registry
```

## Credentials

The server takes **either** credential, in the `Authorization: Bearer …`
header:

- **Sign-in (OAuth)** — clients that support MCP authorization open the ARCNM
  sign-in themselves. You pick the organization and untick any permission you
  don't want to grant. Nothing to copy.
- **An API key** (`ak_live_…` / `ak_test_…`) — long-lived, revocable, scoped.
  Best for an agent you run yourself. Create one at arcnm.io → Settings → API
  keys, with `parts:read` to read results and `parts:write` to price parts.

```bash
export ARCNM_MCP_TOKEN="ak_live_…"
```

## Claude Code

```bash
claude mcp add --transport http arcnm https://api.arcnm.io/mcp-server/mcp
```

Run `/mcp` to sign in, or pass the key instead:

```bash
claude mcp add --transport http arcnm https://api.arcnm.io/mcp-server/mcp \
  --header "Authorization: Bearer $ARCNM_MCP_TOKEN"
```

## Claude and Claude Desktop

Add ARCNM from the [Claude connector directory](https://claude.ai/directory/arcnm)
and sign in.

## Cursor

`~/.cursor/mcp.json`, or project-scoped `.cursor/mcp.json` — see
[`cursor.json`](cursor.json) here:

```json
{
  "mcpServers": {
    "arcnm": {
      "url": "https://api.arcnm.io/mcp-server/mcp",
      "headers": { "Authorization": "Bearer ${env:ARCNM_MCP_TOKEN}" }
    }
  }
}
```

Leave out `headers` to sign in instead.

## GitHub Copilot in VS Code

`.vscode/mcp.json`:

```json
{
  "servers": {
    "arcnm": { "type": "http", "url": "https://api.arcnm.io/mcp-server/mcp" }
  }
}
```

## Anything else that speaks MCP

Point a Streamable HTTP transport at `https://api.arcnm.io/mcp-server/mcp`.
Clients that support OAuth discover the sign-in from the
[protected-resource metadata](https://api.arcnm.io/.well-known/oauth-protected-resource/mcp-server/mcp)
(RFC 9728 — the resource path is appended to the well-known prefix).

## Worth asking it

Once connected, these work as plain requests — the agent picks the tools:

- *"Quote part BRACKET-001 at lot sizes 1, 10 and 100, and tell me where the
  cost goes."* (`quote_part`, `explain_cost`)
- *"Which three things drive the most cost on this calculation?"*
  (`explain_cost`)
- *"Price this part in my three costing environments and rank them."*
  (`quote_part`, `compare_calculations`)
- *"Read the process plan and tell me which operation dominates cycle time."*
  (`get_process_plan`)

A new part is priced in one call: `upload_and_quote` takes the STEP file (or
a DXF flat pattern) and an optional PDF drawing. For a file on your computer,
`get_upload_link` opens the ARCNM upload page instead. More tools (direct
uploads, parts, job nests, the materials catalog…) are listed when the client
sends the `X-MCP-Toolsets` header; see
[toolsets](https://arcnm.io/docs/mcp#toolsets).
Every tool carries `readOnlyHint` and `destructiveHint`, so a well-behaved
client asks before it changes anything.

Full reference: [arcnm.io/docs/mcp](https://arcnm.io/docs/mcp)
