#!/usr/bin/env python3
"""Is this supplier quote fair? Compare it with ARCNM's should-cost, line by line.

A supplier quoted a unit price for a lot. This prices the same part at the same
lot from the physics (material, setup, machine and labour time, tooling,
finishing), shows the gap, and shows which cost lines the gap could sit in.
With --brief, an agent turns that into a short negotiation brief.

    export ARCNM_API_KEY="…"                       # arcnm.io → Settings → API keys
    pip install requests

    # price the part in this repo (uses one calculation), then compare
    python recipes/quote-fairness/fairness.py --quote 310 --lot 50

    # or reuse a calculation you already have (free)
    python recipes/quote-fairness/fairness.py --calculation <id> --quote 310 --lot 50

    # add a negotiation brief written by an agent
    pip install langchain-arcnm langchain langchain-anthropic
    export ANTHROPIC_API_KEY="…"
    python recipes/quote-fairness/fairness.py --calculation <id> --quote 310 --lot 50 --brief

The arithmetic happens here, in code. The agent only explains numbers it is
given, so it cannot get the gap wrong.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests

API = os.environ.get("ARCNM_API_BASE", "https://api.arcnm.io/api/v1")
TERMINAL = {"succeeded", "failed", "cancelled", "timed_out", "blocked"}
REPO = Path(__file__).resolve().parents[2]


def fail(response: requests.Response) -> None:
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    error = body.get("error", {})
    sys.exit(
        f"HTTP {response.status_code} {error.get('code', '')}: {error.get('message', response.text[:200])}\n"
        f"request_id: {body.get('request_id', '—')}"
    )


def get(path: str, headers: dict, **params) -> dict:
    response = requests.get(f"{API}{path}", headers=headers, params=params, timeout=60)
    if not response.ok:
        fail(response)
    return response.json()


def quote_file(cad: Path, lot: int, headers: dict) -> str:
    """Upload and price the part. Uses one calculation from the plan."""
    data = {"part_number": cad.stem.upper(), "lot_size": lot}
    if os.environ.get("ARCNM_ENV_ID"):
        data["costing_environment_id"] = os.environ["ARCNM_ENV_ID"]
    with cad.open("rb") as handle:
        response = requests.post(
            f"{API}/calculations/upload-and-quote",
            headers=headers,
            data=data,
            files={"cad_file": (cad.name, handle, "application/step")},
            timeout=180,
        )
    if not response.ok:
        fail(response)
    calculation = response.json()
    started = time.monotonic()
    while calculation["status"] not in TERMINAL:
        if time.monotonic() - started > 600:
            sys.exit(f"still running after 10 minutes: {calculation['id']}")
        time.sleep(2)
        calculation = get(f"/calculations/{calculation['id']}", headers)
    if calculation["status"] != "succeeded":
        sys.exit(f"calculation {calculation['status']}: {calculation['id']}")
    return calculation["id"]


def compare(calculation_id: str, quoted: float, lot: int, headers: dict) -> dict:
    calculation = get(f"/calculations/{calculation_id}", headers)
    if calculation["status"] != "succeeded":
        sys.exit(f"calculation {calculation_id} is {calculation['status']}, not succeeded")
    # The cost sheet answers for any lot size from the figures recorded while
    # pricing, so the supplier's lot needs no new calculation.
    sheet = get(f"/calculations/{calculation_id}/cost-sheet", headers, quantity=lot)
    point, lines = sheet["point"], sheet["cost_sheet"]["lines"]
    should = point["offer_price"] or point["unit_cost"]
    return {
        "calculation_id": calculation_id,
        "part_number": calculation.get("part_number"),
        "currency": sheet["cost_sheet"]["currency"],
        "lot": lot,
        "quoted_unit": quoted,
        "should_cost_unit": round(point["unit_cost"], 2),
        "should_price_unit": round(should, 2),
        "gap_unit": round(quoted - should, 2),
        "gap_pct": round((quoted - should) / should * 100, 1),
        "gap_lot": round((quoted - should) * lot, 2),
        "lines": sorted(
            (
                {
                    "bucket": line["bucket"],
                    "amount": line["amount"],
                    "time_s": line.get("time_s"),
                    # per_part, per_lot (spread over the lot) or per_setup
                    "time_basis": line.get("time_basis"),
                }
                for line in lines
            ),
            key=lambda line: -line["amount"],
        ),
    }


def report(facts: dict) -> None:
    c = facts["currency"]
    print(f"\n{facts['part_number'] or facts['calculation_id']}  ·  lot {facts['lot']}")
    print(f"  supplier quote      {facts['quoted_unit']:>10.2f} {c} / unit")
    print(f"  ARCNM should-cost   {facts['should_cost_unit']:>10.2f} {c} / unit")
    if facts["should_price_unit"] != facts["should_cost_unit"]:
        print(f"  with your margin    {facts['should_price_unit']:>10.2f} {c} / unit")
    sign = "above" if facts["gap_unit"] >= 0 else "below"
    print(
        f"  gap                 {facts['gap_unit']:>+10.2f} {c} / unit "
        f"({facts['gap_pct']:+.1f} %, {facts['gap_lot']:+.2f} {c} for the lot), quote {sign} should-cost\n"
    )
    print("  where the should-cost goes, per unit:")
    total = sum(line["amount"] for line in facts["lines"]) or 1
    for line in facts["lines"]:
        basis = {"per_part": "/ unit", "per_lot": "/ lot", "per_setup": "/ setup"}.get(line["time_basis"], "")
        minutes = f"{line['time_s'] / 60:7.1f} min {basis}" if line["time_s"] else ""
        print(f"    {line['bucket']:<14} {line['amount']:>9.2f} {c}  {line['amount'] / total:5.0%}  {minutes}")
    print(
        "\n  A gap is not a margin: it also holds the supplier's risk, freight, payment terms,"
        "\n  and any difference between their machines and rates and your costing environment."
    )


def brief(facts: dict) -> None:
    """A negotiation brief, written by an agent from the facts above."""
    from langchain.agents import create_agent
    from langchain_arcnm import ArcnmToolkit

    tools = ArcnmToolkit(read_only=True).get_tools()
    agent = create_agent(
        "anthropic:claude-sonnet-5-5",
        tools=tools,
        system_prompt=(
            "You prepare a buyer for a price conversation with a supplier. You are given a supplier's "
            "unit quote and ARCNM's physics-based should-cost for the same part and lot, with its cost "
            "lines. Use only these figures and what the ARCNM tools return; never compute a new total. "
            "Do not call the gap overpayment or margin padding: a gap also holds risk, freight, terms "
            "and differences in machines and rates. Write at most 150 words: the gap in one sentence, "
            "the two or three cost lines worth asking the supplier about and why, and one question per "
            "line. If the quote is below should-cost, say which lines make that surprising. You may call "
            "get_cost_sheet at other quantities to show how the unit cost moves with the lot size."
        ),
    )
    result = agent.invoke({"messages": [{"role": "user", "content": f"Facts: {facts}"}]})
    print("\nNegotiation brief\n" + result["messages"][-1].content)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cad", nargs="?", type=Path, default=REPO / "parts" / "shaft_thread.step")
    ap.add_argument("--quote", type=float, required=True, help="the supplier's unit price")
    ap.add_argument("--lot", type=int, required=True, help="the lot size the quote is for")
    ap.add_argument("--calculation", help="reuse a succeeded calculation instead of pricing the file")
    ap.add_argument("--brief", action="store_true", help="add a negotiation brief written by an agent")
    args = ap.parse_args()

    key = os.environ.get("ARCNM_API_KEY")
    if not key:
        sys.exit("ARCNM_API_KEY is not set (arcnm.io → Settings → API keys)")
    headers = {"X-API-Key": key}

    calculation_id = args.calculation
    if calculation_id is None:
        if not args.cad.is_file():
            sys.exit(f"no such file: {args.cad}")
        print(f"→ pricing {args.cad.name} at lot {args.lot} (uses one calculation)")
        calculation_id = quote_file(args.cad, args.lot, headers)

    facts = compare(calculation_id, args.quote, args.lot, headers)
    report(facts)
    if args.brief:
        brief(facts)


if __name__ == "__main__":
    main()
