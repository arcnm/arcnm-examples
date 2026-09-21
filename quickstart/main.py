#!/usr/bin/env python3
"""One part in, one price out.

    export ARCNM_API_KEY="…"      # arcnm.io → Settings → API keys
    export ARCNM_ENV_ID="…"       # arcnm.io → Environments
    python quickstart/main.py [path/to/part.step]

Defaults to parts/shaft_thread.step, committed in this repo.

Only dependency is `requests`:  pip install requests
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests

API = os.environ.get("ARCNM_API_BASE", "https://api.arcnm.io/api/v1")
TERMINAL = {"succeeded", "failed", "cancelled", "timed_out"}
REPO = Path(__file__).resolve().parent.parent


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(
            f"{name} is not set.\n"
            "  API key:     arcnm.io → Settings → API keys\n"
            "  Environment: arcnm.io → Environments, or\n"
            "    curl -s $ARCNM_API_BASE/environments/ -H \"X-API-Key: $ARCNM_API_KEY\""
        )
    return value


def main() -> None:
    headers = {"X-API-Key": env("ARCNM_API_KEY")}
    cad = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "parts" / "shaft_thread.step"
    if not cad.is_file():
        sys.exit(f"no such file: {cad}")

    print(f"→ quoting {cad.name}")
    with cad.open("rb") as handle:
        response = requests.post(
            f"{API}/calculations/upload-and-quote",
            headers=headers,
            data={
                "costing_environment_id": env("ARCNM_ENV_ID"),
                "part_number": cad.stem.upper(),
                "lot_size": 50,
                "annual_volume": 500,
            },
            files={"cad_file": (cad.name, handle, "application/step")},
            timeout=120,
        )

    # Every ARCNM error carries a stable `error.code` and a `request_id`;
    # branch on the code, never on the message. https://arcnm.io/docs/errors
    if not response.ok:
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        error = body.get("error", {})
        sys.exit(
            f"HTTP {response.status_code} {error.get('code', '')}: "
            f"{error.get('message', response.text[:200])}\n"
            f"request_id: {body.get('request_id', '—')}"
        )

    calculation = response.json()
    print(f"  queued: {calculation['id']}")

    # Typical milled parts finish in seconds. Poll until the status is
    # terminal; back off politely rather than hammering.
    # https://arcnm.io/docs/rate-limits
    started = time.monotonic()
    while calculation["status"] not in TERMINAL:
        if time.monotonic() - started > 600:
            sys.exit("timed out waiting for the calculation after 10 minutes")
        time.sleep(2)
        calculation = requests.get(
            f"{API}/calculations/{calculation['id']}", headers=headers, timeout=30
        ).json()
        print(f"  {calculation['status']}…", end="\r", flush=True)

    print(" " * 40, end="\r")
    if calculation["status"] != "succeeded":
        sys.exit(f"calculation {calculation['status']}")

    currency = calculation.get("currency", "EUR")
    print(f"\n{calculation['status']}  ({cad.name})")
    print(f"  unit cost   {calculation['unit_cost']:>10.2f} {currency}")
    print(f"  total       {calculation['total_cost']:>10.2f} {currency}   (lot of 50)")
    print(f"  setup       {calculation['setup_cost']:>10.2f} {currency}")
    print(f"  unit time   {calculation['unit_time_s']:>10.1f} s")
    print("\nThe `analytics` blob carries the audit trail — every figure traced")
    print("to what produced it: https://arcnm.io/docs/concepts/audit-provenance")


if __name__ == "__main__":
    main()
