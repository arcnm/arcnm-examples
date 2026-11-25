#!/usr/bin/env bash
# What would ARCNM charge to cost this part? Free: no account, no wallet.
#
#   ./pay-per-call/price_check.sh [path/to/part.step] [DE-BY,CN-SH]
#
# Needs curl and jq. Nothing runs and nothing is charged: the answer is
# 402 Payment Required, carrying a binding offer that stands for 24 hours.
set -euo pipefail

PRICE="https://api.arcnm.io/api/v1/pay/price"
CAD="${1:-$(dirname "$0")/../parts/shaft_thread.step}"
ENVS="${2:-}" # empty: the service's default environment
[ -f "$CAD" ] || { echo "no such file: $CAD" >&2; exit 1; }

# The file is the raw body. A 202 "pricing" means it is still being read:
# ask again after retry_after.
for _ in 1 2 3 4 5; do
  ANSWER=$(curl -sS -X POST "$PRICE${ENVS:+?environments=$ENVS}" \
    -H "Content-Type: model/step" --data-binary "@$CAD" -w '\n%{http_code}')
  CODE=${ANSWER##*$'\n'}
  OFFER=${ANSWER%$'\n'*}
  [ "$CODE" = 202 ] || break
  sleep "$(jq -r '.retry_after // 5' <<<"$OFFER")"
done

if [ "$CODE" != 402 ]; then
  # Errors carry a stable error.code and a request_id. https://arcnm.io/docs/errors
  jq -r '"HTTP '"$CODE"' \(.error.code // "error"): \(.error.message // .)\nrequest_id: \(.request_id // "—")"' \
    <<<"$OFFER" >&2
  exit 1
fi

jq -r 'def eur: "\(. / 100 | floor).\(. % 100 | tostring | if length < 2 then "0" + . else . end)";
"offer \(.offer_id)
  \(.units.total // "at most \(.units_max)") calculation(s) in \([.environments[].id] | join(", "))
  price    EUR \(.price.total_gross_cents | eur) incl. VAT = \(.price.usdc) USDC
  expires  \(.expires_at)
  to pay   \(.hint)
  terms    \(.terms.url)"' <<<"$OFFER"

echo
echo "To buy it:  ARCNM_PAY_WALLET_KEY=0x… python pay-per-call/pay.py --pay   (asks again, then pays)"
