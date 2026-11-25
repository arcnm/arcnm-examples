#!/usr/bin/env -S node --experimental-strip-types
/**
 * Price a part with no account, then pay for its cost in USDC, over HTTP.
 * The same as pay.py, in TypeScript.
 *
 *   npm install --prefix pay-per-call
 *   node --experimental-strip-types pay-per-call/pay.ts [path/to/part.step] [--env DE-BY,CN-SH]
 *   ARCNM_PAY_WALLET_KEY=0x… node --experimental-strip-types pay-per-call/pay.ts --pay [--max-usdc 1.00]
 *
 * Node 22.6+. The payment is signed with the x402 v2 client (@x402/core,
 * @x402/evm) and a viem account.
 */
import { readFile } from "node:fs/promises"
import { basename, join } from "node:path"
import { parseArgs } from "node:util"
import { x402Client, x402HTTPClient } from "@x402/core/client"
import { ExactEvmScheme } from "@x402/evm/exact/client"
import { privateKeyToAccount } from "viem/accounts"

const PRICE = "https://api.arcnm.io/api/v1/pay/price"
const BASE = "eip155:8453" // Base mainnet, where the USDC is

type Offer = {
  offer_id: string
  units: { total: number | null }
  units_max: number | null
  environments: { id: string }[]
  price: { total_gross_cents: number; usdc: string }
  expires_at: string
  hint: string
  terms: { url: string; statements: string[] }
}
type Answer = {
  status: string
  purchase_id: string
  result_url: string
  result_token?: string | null
  retry_after?: number
  progress?: { cells_done: number; cells_total: number } | null
  reason?: string | null
  price?: { usdc: string }
  items?: {
    filename: string
    cells: {
      environment: string
      status: string
      currency: string | null
      error: { message: string } | null
      lots: { lot_size: number; unit_cost: number | null }[]
    }[]
  }[]
  receipt?: { units: number; price_gross_cents: number; transaction: string; network: string } | null
}

function exit(message: string): never {
  console.error(message)
  process.exit(1)
}

// Exit with the API's error. Branch on error.code, never on the message.
async function refuse(r: Response): Promise<never> {
  const body = (await r.json().catch(() => ({}))) as {
    error?: { code?: string; message?: string }
    request_id?: string
  }
  const wait = r.headers.get("Retry-After")
  exit(
    `HTTP ${r.status} ${body.error?.code ?? ""}: ${body.error?.message ?? ""}` +
      (wait ? `\n  send it again in ${wait} s` : "") +
      `\n  request_id: ${body.request_id ?? "—"}`,
  )
}

const { values: opts, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    env: { type: "string" },
    pay: { type: "boolean", default: false },
    "max-usdc": { type: "string", default: "1.00" },
  },
})
// Checked before anything is sent. The key comes from the environment only.
const key = process.env.ARCNM_PAY_WALLET_KEY
if (opts.pay && !key) exit("--pay needs ARCNM_PAY_WALLET_KEY: the private key of a wallet with USDC on Base")
const maxUsdc = Number(opts["max-usdc"])
const cad = positionals[0] ?? join(import.meta.dirname, "..", "parts", "shaft_thread.step")
const file = await readFile(cad).catch(() => exit(`no such file: ${cad}`))

// The price check: the file as the raw body. 402 is the answer, with the offer.
const query = new URLSearchParams({ filename: basename(cad), ...(opts.env ? { environments: opts.env } : {}) })
let r = await fetch(`${PRICE}?${query}`, { method: "POST", headers: { "Content-Type": "model/step" }, body: file })
for (let i = 0; r.status === 202 && i < 10; i++) {
  // 202 "pricing": the file is still being read
  await new Promise((done) => setTimeout(done, 1000 * Number(r.headers.get("Retry-After") ?? 5)))
  r = await fetch(`${PRICE}?${query}`, { method: "POST", headers: { "Content-Type": "model/step" }, body: file })
}
if (r.status !== 402) await refuse(r)
const offer = (await r.json()) as Offer
console.log(`offer ${offer.offer_id}`)
console.log(`  ${offer.units.total ?? `at most ${offer.units_max}`} calculation(s) in ${offer.environments.map((e) => e.id).join(", ")}`)
console.log(`  price    EUR ${(offer.price.total_gross_cents / 100).toFixed(2)} incl. VAT = ${offer.price.usdc} USDC`)
console.log(`  expires  ${offer.expires_at}`)
console.log(`  to pay   ${offer.hint}`)
if (!opts.pay) {
  console.log("\nNothing paid. To buy it: ARCNM_PAY_WALLET_KEY=0x… node --experimental-strip-types pay-per-call/pay.ts --pay")
  process.exit(0)
}

const usdc = Number(offer.price.usdc)
if (usdc > maxUsdc) exit(`the offer is ${usdc} USDC, above --max-usdc ${maxUsdc}: nothing paid`)
// A key with or without its 0x prefix, as pay.py takes it.
const account = privateKeyToAccount(`0x${key!.replace(/^0x/, "")}`)
const client = new x402HTTPClient(
  new x402Client().register(BASE, new ExactEvmScheme(account)).setSpendControls({ maxAmountPerPayment: `$${maxUsdc}` }),
)
const offerHeaders = r.headers
const payload = await client.createPaymentPayload(client.getPaymentRequiredResponse((h) => offerHeaders.get(h), offer))
console.log(`\npaying accepts ${offer.terms.url}:`)
for (const line of offer.terms.statements) console.log(`  ${line}`)
console.log(`→ paying ${offer.price.usdc} USDC from ${account.address}`)
// Pay the offer by its id: the file is not sent again. A body-less POST
// carries Content-Length: 0.
r = await fetch(`${PRICE}?offer_id=${offer.offer_id}`, {
  method: "POST",
  headers: { ...client.encodePaymentSignatureHeader(payload), Prefer: "wait=25" },
})
if (r.status === 402) {
  // A fresh offer: the payment was not taken, and why.
  const fresh = r.headers
  const why = client.getPaymentRequiredResponse((h) => fresh.get(h), await r.json()).error
  exit(`the payment was not taken: ${why}. Ask for a new price and pay that.`)
}
if (r.status !== 200 && r.status !== 202) await refuse(r)

let result = (await r.json()) as Answer
const token = result.result_token
console.log(`  purchase ${result.purchase_id}\n  result token, reads it for 30 days: ${token}`)
// 202: still running or settling. Read the result URL until it answers 200.
const deadline = Date.now() + 2_400_000
while (r.status === 202 && Date.now() < deadline) {
  const counts = result.progress ? ` ${result.progress.cells_done}/${result.progress.cells_total}` : ""
  process.stdout.write(`  ${result.status}${counts}…\r`)
  await new Promise((done) => setTimeout(done, 1000 * (result.retry_after || 5)))
  r = await fetch(result.result_url, { headers: { Authorization: `Bearer ${token}` } })
  if (![200, 202, 402].includes(r.status)) await refuse(r) // e.g. 422 calculation_failed: nothing was charged
  result = (await r.json()) as Answer
}
if (r.status === 202) exit(`\nstill ${result.status}: read it later at ${result.result_url} with Authorization: Bearer <result token>`)
if (r.status === 402) {
  // Delivered, but the payment's authorisation ran out first.
  exit(
    `\nthe payment was not settled in time (${result.reason}). The result waits at ${result.result_url} ` +
      `for ${result.price?.usdc} USDC: send it a GET with the result token and a new PAYMENT-SIGNATURE.`,
  )
}

for (const item of result.items ?? []) {
  for (const cell of item.cells) {
    console.log(`\n${item.filename} in ${cell.environment}: ${cell.status}`)
    if (cell.error) console.log(`  ${cell.error.message}`)
    for (const lot of cell.lots) {
      const cost = lot.unit_cost === null ? "—" : lot.unit_cost.toFixed(2)
      console.log(`  lot ${String(lot.lot_size).padStart(5)}   unit cost ${cost.padStart(10)} ${cell.currency}`)
    }
  }
}
const receipt = result.receipt
if (!receipt) {
  console.log("\nno receipt: nothing was charged")
  process.exit(0)
}
console.log(`\nreceipt  EUR ${(receipt.price_gross_cents / 100).toFixed(2)} for ${receipt.units} calculation(s)`)
console.log(`  transaction ${receipt.transaction} on ${receipt.network}`)
