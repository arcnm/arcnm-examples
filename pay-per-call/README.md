# Pay per call

Price a part with no account and no API key. Send the CAD file and you get
a binding offer; pay it in USDC and you get the part's manufacturing cost.
Over HTTP or over MCP. The full contract is the guide:
[arcnm.io/docs/pay-per-call](https://arcnm.io/docs/pay-per-call).

## Two steps

1. **Ask the price. Free.** `POST /pay/price` with the file answers
   `402 Payment Required` with an offer: how many calculations, the price,
   and when the offer expires (it stands for 24 hours). Nothing runs and
   nothing is charged.
2. **Pay it.** Sign the offer's x402 payment requirement (USDC on Base) and
   send it back. The answer is the result, or a `202` with a `result_url`
   to read until the result is ready.

## What it costs

EUR 0.89 per calculation, VAT included. One calculation is one made part in
one environment; bought and catalogue parts are free. In USDC it is EUR 0.89
at the posted rate, 0.98 USDC when this was written. Every offer states its
own amount.

- **A failed calculation is never charged.**
- **Asking again costs nothing.** The same payer sending the same file with
  the same parameters within 24 hours gets the paid result again, with no
  new charge.
- Paying accepts the terms the offer names. The scripts print them before
  they pay: the service is offered to businesses only, and you confirm the
  file is not export-controlled.

## Run it

| File | What it does | Needs |
|---|---|---|
| [`price_check.sh`](price_check.sh) | The price check, nothing else | curl, jq |
| [`pay.py`](pay.py) | The offer; with `--pay`, pays over HTTP and prints the result | Python 3.10+, [`requirements.txt`](requirements.txt) |
| [`pay_mcp.py`](pay_mcp.py) | The same over the pay MCP server | as `pay.py` |
| [`pay.ts`](pay.ts) | `pay.py` in TypeScript | Node 22.6+, [`package.json`](package.json) |

Without `--pay`, every script only asks the price. Free, no wallet:

```bash
./pay-per-call/price_check.sh                    # parts/shaft_thread.step, default environment
./pay-per-call/price_check.sh my.step DE-BY,CN-SH

pip install -r pay-per-call/requirements.txt
python pay-per-call/pay.py
python pay-per-call/pay_mcp.py --env DE-BY,US-IL

npm install --prefix pay-per-call
node --experimental-strip-types pay-per-call/pay.ts
```

The environments you can price in, with every parameter and limit (free):

```bash
curl -s https://api.arcnm.io/api/v1/pay/environments | jq '.environments[] | {id, name}'
```

To buy, add `--pay`. The key is read from `ARCNM_PAY_WALLET_KEY` only, never
from a file or an argument. A script refuses an offer above `--max-usdc`
(default 1.00, which covers one calculation); raise it to price several
parts or environments in one payment.

```bash
export ARCNM_PAY_WALLET_KEY="0x…"   # the wallet's private key; never commit it
python pay-per-call/pay.py --pay
python pay-per-call/pay_mcp.py --pay --env DE-BY,CN-SH --max-usdc 2
node --experimental-strip-types pay-per-call/pay.ts --pay
```

It prints the amount and pays. Then it prints the purchase and its result
token, which reads the result for 30 days: keep it. Last come the unit cost
at each lot size for every part and environment, and the transaction on the
receipt. On the way:

- **Still running** (`202`): it reads `result_url` with the token until the
  answer is `200`, for up to 40 minutes, then says where to read it later.
- **Payment not taken** (a fresh `402`): it prints why, for example
  `insufficient_balance`. Ask for a new price.
- **The payment's authorisation ran out** before it settled (`402` at
  `result_url`): it prints the amount still due and where to pay it.
- **Refused** (`409 offer_taken`, `422 calculation_failed`, `429`, `451`,
  `503` with `Retry-After`): the API's `error.code` and message.

For an agent, the pay MCP server is `https://api.arcnm.io/mcp-server/pay/mcp`
(streamable HTTP, no OAuth), with the tools `price_parts`, `get_result` and
`preview_cost`.

## A wallet to pay from

Paying takes a wallet on Base (network `eip155:8453`) that holds USDC.
Use a dedicated wallet holding a few dollars, not the one you keep savings
in: its private key sits in an environment variable while the script runs.
Send USDC on the Base network to its address, from an exchange or a wallet
that supports Base.

A card pays too, from 6 calculations per payment and over HTTP only: see
[the guide](https://arcnm.io/docs/pay-per-call).
