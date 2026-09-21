#!/usr/bin/env python3
"""Quote one part and print where the cost actually goes.

The quickstart gives you a number. This gives you the number plus the reason
for it — which is the part you can take to a supplier.

    export ARCNM_API_KEY="…"
    export ARCNM_ENV_ID="…"
    python recipes/quote-a-part/breakdown.py [path/to/part.step] [--lot 50]

    pip install requests
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

API = os.environ.get("ARCNM_API_BASE", "https://api.arcnm.io/api/v1")
TERMINAL = {"succeeded", "failed", "cancelled", "timed_out"}
REPO = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cad", nargs="?", type=Path, default=REPO / "parts" / "shaft_thread.step")
    ap.add_argument("--lot", type=int, default=50)
    ap.add_argument("--json", action="store_true", help="dump the full calculation and exit")
    args = ap.parse_args()

    key, env_id = os.environ.get("ARCNM_API_KEY"), os.environ.get("ARCNM_ENV_ID")
    if not key or not env_id:
        sys.exit("set ARCNM_API_KEY and ARCNM_ENV_ID (arcnm.io → Settings / Environments)")
    headers = {"X-API-Key": key}

    if not args.cad.is_file():
        sys.exit(f"no such file: {args.cad}")

    with args.cad.open("rb") as handle:
        r = requests.post(
            f"{API}/calculations/upload-and-quote",
            headers=headers,
            data={
                "costing_environment_id": env_id,
                "part_number": args.cad.stem.upper(),
                "lot_size": args.lot,
                "annual_volume": args.lot * 10,
            },
            files={"cad_file": (args.cad.name, handle, "application/step")},
            timeout=180,
        )
    if not r.ok:
        body = r.json() if "json" in r.headers.get("content-type", "") else {}
        sys.exit(f"HTTP {r.status_code} {body.get('error', {}).get('code', '')}: {body.get('error', {}).get('message', r.text[:200])}")

    calc = r.json()
    print(f"→ {args.cad.name}  ({calc['id']})")
    deadline = time.monotonic() + 900
    while calc["status"] not in TERMINAL:
        if time.monotonic() > deadline:
            sys.exit("timed out after 15 minutes")
        time.sleep(2)
        calc = requests.get(f"{API}/calculations/{calc['id']}", headers=headers, timeout=30).json()
        print(f"  {calc['status']}…", end="\r", flush=True)
    print(" " * 40, end="\r")

    if calc["status"] != "succeeded":
        sys.exit(f"calculation {calc['status']}")

    if args.json:
        print(json.dumps(calc, indent=2))
        return

    cur = calc.get("currency", "EUR")
    print(f"\n{args.cad.name} — lot of {args.lot}\n")
    print(f"  unit cost        {calc['unit_cost']:>12.2f} {cur}")
    print(f"  total            {calc['total_cost']:>12.2f} {cur}")
    print(f"  setup            {calc.get('setup_cost', 0):>12.2f} {cur}")
    print(f"  unit time        {calc.get('unit_time_s', 0):>12.1f} s")
    print(f"  total time       {calc.get('total_time_s', 0):>12.1f} s")

    # `analytics` is the audit blob: the cost decomposition, the ranked
    # drivers, the machine chosen and why. Its exact shape is documented at
    # https://arcnm.io/docs/concepts/audit-provenance — here we just show what
    # came back, so the example keeps working as the blob grows.
    analytics = calc.get("analytics") or {}
    if analytics:
        print("\n  analytics keys:")
        for k in sorted(analytics)[:12]:
            v = analytics[k]
            kind = type(v).__name__
            size = f"[{len(v)}]" if isinstance(v, (list, dict)) else ""
            print(f"    {k:28} {kind}{size}")
        print("\n  Re-run with --json to see all of it.")
    else:
        print("\n  (no analytics blob on this calculation)")

    print("\nAudit & provenance: https://arcnm.io/docs/concepts/audit-provenance")
    print(f"Lot-size economics:  https://arcnm.io/docs/concepts/cost-and-lot-size")


if __name__ == "__main__":
    main()
