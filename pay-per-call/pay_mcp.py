#!/usr/bin/env python3
"""The same as pay.py, over the pay MCP server: no account, no OAuth.

    python pay-per-call/pay_mcp.py [path/to/part.step] [--env DE-BY,CN-SH]
    ARCNM_PAY_WALLET_KEY=0x… python pay-per-call/pay_mcp.py --pay [--max-usdc 1.00]

An unpaid price_parts call answers with the offer as the x402 payment
requirement. x402MCPClient signs it and calls the tool again with the payment
in _meta["x402/payment"]. The arguments, the offer and the result print as in
pay.py, which this file imports.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from decimal import Decimal

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from pay import parse_args, show_offer, show_result, wallet

MCP = "https://api.arcnm.io/mcp-server/pay/mcp"


def answer(result) -> dict:
    """A tool's answer: its structured content, or exit with the API's error."""
    if result.structured_content is not None:
        return result.structured_content
    text = result.content[0].text if result.content else ""
    try:
        error = json.loads(text).get("error", {})
        sys.exit(f"{error.get('code')}: {error.get('message')}")
    except (ValueError, AttributeError):
        sys.exit(text or "no answer")


class Calls:  # x402MCPClient calls call_tool({name, arguments, _meta})
    def __init__(self, session: ClientSession):
        self.session = session

    async def call_tool(self, params, **_):
        return await self.session.call_tool(
            params["name"], params["arguments"], meta=params.get("_meta"))


async def main() -> None:
    args = parse_args()
    call = {"file_base64": base64.b64encode(args.cad.read_bytes()).decode(),
            "filename": args.cad.name}
    if args.env:
        call["environments"] = args.env.split(",")

    async with streamable_http_client(MCP) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        try:
            await run(session, args, call)
            stop = None
        except SystemExit as exit_:
            stop = exit_.code
    # Exit outside the session: inside it, the exit surfaces wrapped in a task group.
    sys.exit(stop)


async def run(session: ClientSession, args, call: dict) -> None:
    for _ in range(10):
        unpaid = answer(await session.call_tool("price_parts", call))
        if unpaid.get("status") != "pricing":  # "pricing": the file is still being read
            break
        await asyncio.sleep(unpaid.get("retry_after", 5))
    offer = unpaid["offer"]
    show_offer(offer)
    print(f"  or over HTTP at {unpaid['pay_url']}")
    if not args.pay:
        print("\nNothing paid. To buy it: ARCNM_PAY_WALLET_KEY=0x… python pay-per-call/pay_mcp.py --pay")
        return

    from x402.mcp import PaymentRequiredError, x402MCPClient

    signer, address = wallet(args.max_usdc)

    def approve(context) -> bool:
        # The requirement about to be signed: USDC has 6 decimals.
        usdc = Decimal(context.payment_required.accepts[0].amount) / 10**6
        if usdc > args.max_usdc:
            print(f"the offer is {usdc} USDC, above --max-usdc {args.max_usdc}: nothing paid")
            return False
        print(f"\npaying accepts {offer['terms']['url']}:")
        for line in offer["terms"]["statements"]:
            print(f"  {line}")
        print(f"→ paying {usdc} USDC from {address}")
        return True

    payer = x402MCPClient(Calls(session), signer, on_payment_requested=approve)
    try:
        paid = await payer.call_tool("price_parts", call)
    except PaymentRequiredError as exc:  # declined above: nothing was signed
        sys.exit(f"nothing paid: {exc}")
    if paid.raw_result is None:  # the tool asked for no payment this time
        sys.exit(f"no payment was asked for: {paid.content}")
    result = answer(paid.raw_result)
    if "offer" in result:  # a fresh requirement: the payment was not taken, and why
        sys.exit(f"the payment was not taken: {result.get('error')}. Ask for a new price.")

    token = result.get("result_token")
    print(f"  purchase {result['purchase_id']}\n  result token, reads it for 30 days: {token}")
    # Running or settling: read it with get_result until it carries the items.
    deadline = asyncio.get_running_loop().time() + 2400
    while "items" not in result and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(result.get("retry_after") or 5)
        result = answer(await session.call_tool(
            "get_result", {"purchase_id": result["purchase_id"], "result_token": token}))
        if "offer" in result:  # delivered, but the payment's authorisation ran out first
            sys.exit(f"the payment was not settled in time ({result['offer'].get('reason')}). "
                     f"Pay the {result['offer']['price']['usdc']} USDC it asks at {result['pay_url']}.")
    if "items" not in result:
        sys.exit(f"still {result['status']}: read it later with get_result and the result token")
    show_result(result)


if __name__ == "__main__":
    asyncio.run(main())
