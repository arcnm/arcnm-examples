#!/usr/bin/env python3
"""Price a part with no account, then pay for its cost in USDC, over HTTP.

    python pay-per-call/pay.py [path/to/part.step] [--env DE-BY,CN-SH]
    ARCNM_PAY_WALLET_KEY=0x… python pay-per-call/pay.py --pay [--max-usdc 1.00]

Without --pay it asks for the price and stops: free, no wallet. With --pay it
signs the offer's USDC payment on Base (x402 v2), waits for the result and
prints the unit cost per lot and the receipt's transaction.

    pip install -r pay-per-call/requirements.txt
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

import httpx

PRICE = "https://api.arcnm.io/api/v1/pay/price"
BASE = "eip155:8453"  # Base mainnet, where the USDC is
PART = Path(__file__).resolve().parent.parent / "parts" / "shaft_thread.step"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("cad", nargs="?", type=Path, default=PART, help="a STEP file")
    p.add_argument("--env", help="environments, comma separated (default: the service's)")
    p.add_argument("--pay", action="store_true", help="pay the offer from ARCNM_PAY_WALLET_KEY")
    p.add_argument("--max-usdc", type=Decimal, default=Decimal("1.00"), help="refuse a dearer offer")
    args = p.parse_args()
    # Checked before anything is sent. The key comes from the environment only.
    if args.pay and not os.environ.get("ARCNM_PAY_WALLET_KEY"):
        sys.exit("--pay needs ARCNM_PAY_WALLET_KEY: the private key of a wallet with USDC on Base")
    if not args.cad.is_file():
        sys.exit(f"no such file: {args.cad}")
    return args


def wallet(max_usdc: Decimal):
    """An x402 client that signs USDC payments on Base, capped at max_usdc each."""
    from eth_account import Account
    from x402 import x402Client
    from x402.mechanisms.evm.exact import ExactEvmScheme

    account = Account.from_key(os.environ["ARCNM_PAY_WALLET_KEY"])
    client = x402Client().register(BASE, ExactEvmScheme(signer=account))
    return client.set_spend_controls({"max_amount_per_payment": f"${max_usdc}"}), account.address


def show_offer(offer: dict) -> None:
    units = offer["units"]["total"] or f"at most {offer['units_max']}"  # a ceiling
    envs = ", ".join(e["id"] for e in offer["environments"])
    print(f"offer {offer['offer_id']}")
    print(f"  {units} calculation(s) in {envs}")
    print(f"  price    EUR {offer['price']['total_gross_cents'] / 100:.2f} incl. VAT"
          f" = {offer['price']['usdc']} USDC")
    print(f"  expires  {offer['expires_at']}")
    print(f"  to pay   {offer['hint']}")


def show_result(result: dict) -> None:
    for item in result["items"]:
        for cell in item["cells"]:
            print(f"\n{item['filename']} in {cell['environment']}: {cell['status']}")
            if cell.get("error"):
                print(f"  {cell['error']['message']}")
            for lot in cell["lots"]:
                cost = "—" if lot["unit_cost"] is None else f"{lot['unit_cost']:.2f}"
                print(f"  lot {lot['lot_size']:>5}   unit cost {cost:>10} {cell['currency']}")
    receipt = result.get("receipt")
    if not receipt:
        print("\nno receipt: nothing was charged")
        return
    print(f"\nreceipt  EUR {receipt['price_gross_cents'] / 100:.2f} for {receipt['units']} calculation(s)")
    print(f"  transaction {receipt['transaction']} on {receipt['network']}")


def refuse(r: httpx.Response) -> None:
    """Exit with the API's error. Branch on error.code, never on the message."""
    try:
        body = r.json()
    except ValueError:
        body = {}
    error = body.get("error") or {}
    wait = r.headers.get("Retry-After")
    sys.exit(f"HTTP {r.status_code} {error.get('code', '')}: {error.get('message', r.text[:200])}"
             + (f"\n  send it again in {wait} s" if wait else "")
             + f"\n  request_id: {body.get('request_id', '—')}")


async def main() -> None:
    args = parse_args()
    params = {"filename": args.cad.name} | ({"environments": args.env} if args.env else {})
    async with httpx.AsyncClient(timeout=60) as http:
        # The price check: the file as the raw body. 402 is the answer, with the offer.
        for _ in range(10):
            r = await http.post(PRICE, params=params, content=args.cad.read_bytes(),
                                headers={"Content-Type": "model/step"})
            if r.status_code != 202:  # 202 "pricing": the file is still being read
                break
            await asyncio.sleep(int(r.headers.get("Retry-After", "5")))
        if r.status_code != 402:
            refuse(r)
        offer = r.json()
        show_offer(offer)
        if not args.pay:
            print("\nNothing paid. To buy it: ARCNM_PAY_WALLET_KEY=0x… python pay-per-call/pay.py --pay")
            return

        usdc = Decimal(offer["price"]["usdc"])
        if usdc > args.max_usdc:
            sys.exit(f"the offer is {usdc} USDC, above --max-usdc {args.max_usdc}: nothing paid")
        from x402.http.x402_http_client import x402HTTPClient

        signer, address = wallet(args.max_usdc)
        client = x402HTTPClient(signer)
        payload = await client.create_payment_payload(
            client.get_payment_required_response(r.headers.get, offer))
        print("\npaying accepts " + offer["terms"]["url"] + ":")
        for line in offer["terms"]["statements"]:
            print(f"  {line}")
        print(f"→ paying {usdc} USDC from {address}")
        # Pay the offer by its id: the file is not sent again.
        r = await http.post(PRICE, params={"offer_id": offer["offer_id"]}, headers={
            **client.encode_payment_signature_header(payload),
            "Prefer": "wait=25", "Content-Length": "0"})
        if r.status_code == 402:  # a fresh offer: the payment was not taken, and why
            why = client.get_payment_required_response(r.headers.get, r.json()).error
            sys.exit(f"the payment was not taken: {why}. Ask for a new price and pay that.")
        if r.status_code not in (200, 202):
            refuse(r)

        result = r.json()
        token = result.get("result_token")
        print(f"  purchase {result['purchase_id']}\n  result token, reads it for 30 days: {token}")
        # 202: still running or settling. Read the result URL until it answers 200.
        deadline = asyncio.get_running_loop().time() + 2400
        while r.status_code == 202 and asyncio.get_running_loop().time() < deadline:
            done = result.get("progress")
            counts = f" {done['cells_done']}/{done['cells_total']}" if done else ""
            print(f"  {result['status']}{counts}…", end="\r", flush=True)
            await asyncio.sleep(result.get("retry_after") or 5)
            r = await http.get(result["result_url"], headers={"Authorization": f"Bearer {token}"})
            if r.status_code not in (200, 202, 402):
                refuse(r)  # e.g. 422 calculation_failed: nothing was charged
            result = r.json()
        if r.status_code == 202:
            sys.exit(f"\nstill {result['status']}: read it later at {result['result_url']}"
                     " with Authorization: Bearer <result token>")
        if r.status_code == 402:  # delivered, but the payment's authorisation ran out first
            sys.exit(f"\nthe payment was not settled in time ({result.get('reason')}). The result "
                     f"waits at {result['result_url']} for {result['price']['usdc']} USDC: send it "
                     "a GET with the result token and a new PAYMENT-SIGNATURE.")
        show_result(result)


if __name__ == "__main__":
    asyncio.run(main())
