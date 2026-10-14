#!/usr/bin/env python3
"""Quote a folder of CAD files and rank them by unit cost.

The RFQ-inbox problem: 50-500 parts arrive, quoting each by hand takes a week,
and you only need to know which ones matter before you reply.

    export ARCNM_API_KEY="…"
    export ARCNM_ENV_ID="…"
    python recipes/bulk-rfq-triage/triage.py ./parts            # a folder
    python recipes/bulk-rfq-triage/triage.py ./parts --lot 100

Writes triage.csv next to the folder, sorted by unit cost descending.

    pip install requests
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

API = os.environ.get("ARCNM_API_BASE", "https://api.arcnm.io/api/v1")
# `blocked`: created but parked, because the organization has no included
# calculations left. It will not start on its own, so stop polling.
TERMINAL = {"succeeded", "failed", "cancelled", "timed_out", "blocked"}
CAD_SUFFIXES = {".step", ".stp"}

# Submit-side etiquette. Four in flight is polite for a batch of this size and
# keeps you clear of the per-key rate limit; if you get a 429 the response
# carries Retry-After and the rejected call costs nothing.
# https://arcnm.io/docs/rate-limits  ·  https://arcnm.io/docs/recipes/bulk-upload-pacing
CONCURRENCY = 4


def session() -> requests.Session:
    key = os.environ.get("ARCNM_API_KEY")
    env_id = os.environ.get("ARCNM_ENV_ID")
    if not key or not env_id:
        sys.exit("set ARCNM_API_KEY and ARCNM_ENV_ID (arcnm.io → Settings / Environments)")
    s = requests.Session()
    s.headers["X-API-Key"] = key
    return s


def submit(s: requests.Session, cad: Path, lot: int) -> dict:
    with cad.open("rb") as handle:
        r = s.post(
            f"{API}/calculations/upload-and-quote",
            data={
                "costing_environment_id": os.environ["ARCNM_ENV_ID"],
                "part_number": cad.stem.upper()[:64],
                "lot_size": lot,
            },
            files={"cad_file": (cad.name, handle, "application/step")},
            timeout=180,
        )
    if r.status_code == 429:
        # Honour the server's own backoff rather than inventing one.
        wait = int(r.headers.get("Retry-After", "5"))
        time.sleep(wait)
        return submit(s, cad, lot)
    if not r.ok:
        body = r.json() if "json" in r.headers.get("content-type", "") else {}
        return {"file": cad.name, "error": f"{r.status_code} {body.get('error', {}).get('code', '')}"}
    return {"file": cad.name, "id": r.json()["id"]}


def await_result(s: requests.Session, row: dict) -> dict:
    if "id" not in row:
        return row
    deadline = time.monotonic() + 900
    while True:
        calc = s.get(f"{API}/calculations/{row['id']}", timeout=30).json()
        if calc.get("status") in TERMINAL:
            break
        if time.monotonic() > deadline:
            return {**row, "error": "timeout"}
        time.sleep(3)
    if calc["status"] != "succeeded":
        reason = (calc.get("coverage") or {}).get("reason")
        return {**row, "error": f"{calc['status']} ({reason})" if reason else calc["status"]}
    return {
        **row,
        "unit_cost": calc.get("unit_cost"),
        "total_cost": calc.get("total_cost"),
        "currency": calc.get("currency", "EUR"),
        "unit_time_s": calc.get("unit_time_s"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--lot", type=int, default=50)
    args = ap.parse_args()

    files = sorted(p for p in args.folder.iterdir() if p.suffix.lower() in CAD_SUFFIXES)
    if not files:
        sys.exit(f"no .step/.stp files in {args.folder}")
    print(f"→ {len(files)} parts, lot size {args.lot}, {CONCURRENCY} in flight")

    s = session()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        submitted = list(pool.map(lambda f: submit(s, f, args.lot), files))
        print(f"  submitted {sum('id' in r for r in submitted)}/{len(files)}, waiting…")
        rows = list(pool.map(lambda r: await_result(s, r), submitted))

    priced = sorted(
        (r for r in rows if r.get("unit_cost") is not None),
        key=lambda r: r["unit_cost"],
        reverse=True,
    )
    failed = [r for r in rows if r.get("error")]

    out = args.folder / "triage.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "unit_cost", "total_cost", "currency", "unit_time_s", "id"])
        w.writeheader()
        for r in priced:
            w.writerow({k: r.get(k) for k in w.fieldnames})

    print(f"\n{'part':32} {'unit':>10} {'total':>12}")
    for r in priced[:10]:
        print(f"  {r['file'][:30]:32} {r['unit_cost']:>10.2f} {r['total_cost']:>12.2f} {r['currency']}")
    if len(priced) > 10:
        print(f"  … and {len(priced) - 10} more")
    if failed:
        print(f"\n{len(failed)} did not price:")
        for r in failed[:5]:
            print(f"  {r['file']}: {r['error']}")

    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
