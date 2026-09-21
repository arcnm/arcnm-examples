#!/usr/bin/env -S node --experimental-strip-types
/**
 * One part in, one price out.
 *
 *   export ARCNM_API_KEY="…"     // arcnm.io → Settings → API keys
 *   export ARCNM_ENV_ID="…"      // arcnm.io → Environments
 *   node --experimental-strip-types quickstart/main.ts [path/to/part.step]
 *
 * No dependencies. Needs Node 22.6+ for --experimental-strip-types (it is
 * the default from Node 23); fetch, FormData and Blob are built in.
 * Prefer plain JS? Drop the types — the logic is identical.
 */
import { readFile } from "node:fs/promises"
import { basename, extname, join } from "node:path"

const API = process.env.ARCNM_API_BASE ?? "https://api.arcnm.io/api/v1"
const TERMINAL = new Set(["succeeded", "failed", "cancelled", "timed_out"])

function env(name: string): string {
  const value = process.env[name]
  if (!value) {
    console.error(
      `${name} is not set.\n` +
        "  API key:     arcnm.io → Settings → API keys\n" +
        "  Environment: arcnm.io → Environments",
    )
    process.exit(1)
  }
  return value
}

const headers = { "X-API-Key": env("ARCNM_API_KEY") }
const cad = process.argv[2] ?? join(import.meta.dirname, "..", "parts", "shaft_thread.step")
const name = basename(cad)

console.log(`→ quoting ${name}`)

const form = new FormData()
form.set("costing_environment_id", env("ARCNM_ENV_ID"))
form.set("part_number", basename(name, extname(name)).toUpperCase())
form.set("lot_size", "50")
form.set("annual_volume", "500")
form.set("cad_file", new Blob([await readFile(cad)], { type: "application/step" }), name)

const created = await fetch(`${API}/calculations/upload-and-quote`, {
  method: "POST",
  headers,
  body: form,
})

// Errors carry a stable error.code and a request_id — branch on the code,
// never the message. https://arcnm.io/docs/errors
if (!created.ok) {
  const body = await created.json().catch(() => ({}) as Record<string, never>)
  const error = (body as { error?: { code?: string; message?: string } }).error ?? {}
  console.error(
    `HTTP ${created.status} ${error.code ?? ""}: ${error.message ?? ""}\n` +
      `request_id: ${(body as { request_id?: string }).request_id ?? "—"}`,
  )
  process.exit(1)
}

let calc = (await created.json()) as {
  id: string
  status: string
  currency?: string
  unit_cost?: number
  total_cost?: number
  setup_cost?: number
  unit_time_s?: number
}
console.log(`  queued: ${calc.id}`)

// Poll until terminal — seconds for a typical milled part.
const deadline = Date.now() + 600_000
while (!TERMINAL.has(calc.status)) {
  if (Date.now() > deadline) {
    console.error("timed out waiting for the calculation after 10 minutes")
    process.exit(1)
  }
  await new Promise((r) => setTimeout(r, 2000))
  calc = await (await fetch(`${API}/calculations/${calc.id}`, { headers })).json()
  process.stdout.write(`  ${calc.status}…\r`)
}

process.stdout.write(`${" ".repeat(40)}\r`)
if (calc.status !== "succeeded") {
  console.error(`calculation ${calc.status}`)
  process.exit(1)
}

const cur = calc.currency ?? "EUR"
console.log(`\n${calc.status}  (${name})`)
console.log(`  unit cost   ${calc.unit_cost?.toFixed(2).padStart(10)} ${cur}`)
console.log(`  total       ${calc.total_cost?.toFixed(2).padStart(10)} ${cur}   (lot of 50)`)
console.log(`  setup       ${calc.setup_cost?.toFixed(2).padStart(10)} ${cur}`)
console.log(`  unit time   ${calc.unit_time_s?.toFixed(1).padStart(10)} s`)
console.log("\nThe `analytics` blob carries the audit trail:")
console.log("https://arcnm.io/docs/concepts/audit-provenance")
