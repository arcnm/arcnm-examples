#!/usr/bin/env python3
"""Do the examples in this repo still match the live API?

Every script here makes the same promises: this endpoint, these fields to
send, these fields to read back. If the API renames one, nothing in this repo
fails — the Python still parses, the markdown still renders — and the first
person to find out is a reader whose first call 422s.

So assert the promises directly, against the spec the API actually serves.

    python .github/check_contract.py

Checks only what this repo uses. New endpoints and new fields are free.
"""

from __future__ import annotations

import json
import sys
import urllib.request

SPEC = "https://api.arcnm.io/api/v1/openapi-public.json"

QUOTE = "/api/v1/calculations/upload-and-quote"
DETAIL = "/api/v1/calculations/{calculation_id}"
ENVIRONMENTS = "/api/v1/environments/"

# What quickstart/ and recipes/ send.
SEND_REQUIRED = {"part_number", "cad_file"}
SEND_OPTIONAL = {"costing_environment_id", "lot_size", "annual_volume", "drawing_file"}

# What they read back and print.
READ = {"id", "status", "currency", "unit_cost", "total_cost", "setup_cost", "unit_time_s"}

# What the poll loops treat as terminal. A renamed state here is an infinite
# loop in somebody's script.
TERMINAL = {"succeeded", "failed", "cancelled", "timed_out"}


def schema_for(spec: dict, node: dict) -> dict:
    ref = node.get("$ref")
    if not ref:
        return node
    return spec.get("components", {}).get("schemas", {}).get(ref.rsplit("/", 1)[-1], {})


def main() -> int:
    try:
        with urllib.request.urlopen(SPEC, timeout=30) as response:
            spec = json.load(response)
    except Exception as exc:
        print(f"could not fetch {SPEC}: {exc}")
        return 1

    paths = spec.get("paths", {})
    problems: list[str] = []

    for path in (QUOTE, DETAIL, ENVIRONMENTS):
        if path not in paths:
            problems.append(f"{path} is gone — the examples call it")
    if problems:
        for problem in problems:
            print(f"  - {problem}")
        return 1

    body = paths[QUOTE]["post"].get("requestBody", {}).get("content", {})
    if "multipart/form-data" not in body:
        problems.append(f"{QUOTE} no longer takes multipart/form-data")
    else:
        sch = schema_for(spec, body["multipart/form-data"].get("schema", {}))
        props, required = set(sch.get("properties", {})), set(sch.get("required", []))
        for field in sorted(SEND_REQUIRED - required):
            problems.append(f"{QUOTE}: '{field}' is no longer required")
        for field in sorted((SEND_REQUIRED | SEND_OPTIONAL) - props):
            problems.append(f"{QUOTE}: field '{field}' is gone — the examples send it")

    ok = paths[DETAIL]["get"].get("responses", {}).get("200", {}).get("content", {})
    sch = schema_for(spec, ok.get("application/json", {}).get("schema", {}))
    props = set(sch.get("properties", {}))
    for field in sorted(READ - props):
        problems.append(f"{DETAIL}: response field '{field}' is gone — the examples print it")

    enum = set((sch.get("properties", {}).get("status", {}) or {}).get("enum") or [])
    if enum and (missing := TERMINAL - enum):
        problems.append(f"{DETAIL}: terminal status {sorted(missing)} gone — poll loops would hang")

    if problems:
        print(f"{len(problems)} break(s) against the live API:\n")
        for problem in problems:
            print(f"  - {problem}")
        print("\nUpdate the examples, or the API regressed. Either way somebody's")
        print("first five minutes with ARCNM is currently broken.")
        return 1

    print(f"contract holds: {len(paths)} paths served, every promise this repo makes is intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
