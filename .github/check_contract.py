#!/usr/bin/env python3
"""Do the examples in this repo still match the live API?

Every script here makes the same promises: this endpoint, these fields to
send, these fields to read back. If the API renames one, nothing in this repo
fails — the Python still parses, the markdown still renders — and the first
person to find out is a reader whose first call 422s.

The promises are written down once, in `arcnm-contract.json` at the repo
root. This script holds them against the spec the API actually serves; ARCNM
holds the same file against every change to the API before it merges.

    python .github/check_contract.py

Checks only what this repo uses. New endpoints and new fields are free.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

SPEC = "https://api.arcnm.io/api/v1/openapi-public.json"
CONTRACT = Path(__file__).resolve().parent.parent / "arcnm-contract.json"


def resolve(spec: dict, node: dict) -> dict:
    while isinstance(node, dict) and "$ref" in node:
        node = spec.get("components", {}).get("schemas", {}).get(node["$ref"].rsplit("/", 1)[-1], {})
    return node if isinstance(node, dict) else {}


def properties(spec: dict, node: dict) -> tuple[set[str], set[str]]:
    """Field names and required names of a schema (array items, allOf, anyOf)."""
    node = resolve(spec, node)
    if node.get("type") == "array" and "items" in node:
        node = resolve(spec, node["items"])
    props, required = set(node.get("properties", {})), set(node.get("required", []))
    for key in ("allOf", "anyOf", "oneOf"):
        for member in node.get(key, []):
            p, r = properties(spec, member)
            props |= p
            if key == "allOf":
                required |= r
    return props, required


def check(spec: dict, contract: dict) -> list[str]:
    problems: list[str] = []
    for op in contract["operations"]:
        method, path = op["method"].lower(), op["path"]
        label = f"{method.upper()} {path}"
        operation = spec.get("paths", {}).get(path, {}).get(method)
        if operation is None:
            problems.append(f"{label} is gone — the examples call it")
            continue
        request = op.get("request")
        if request:
            ctype = request.get("content_type", "application/json")
            body = operation.get("requestBody", {}).get("content", {}).get(ctype)
            if body is None:
                problems.append(f"{label} no longer takes {ctype}")
            else:
                props, required = properties(spec, body.get("schema", {}))
                for name in sorted(set(request.get("required", [])) - required):
                    problems.append(f"{label}: '{name}' is no longer required")
                for name in sorted((set(request.get("required", [])) | set(request.get("fields", []))) - props):
                    problems.append(f"{label}: field '{name}' is gone — the examples send it")
        response = op.get("response")
        if response:
            status = str(response.get("status", "200"))
            body = operation.get("responses", {}).get(status, {}).get("content", {}).get("application/json")
            if body is None:
                problems.append(f"{label}: no JSON {status} response any more")
                continue
            props, _ = properties(spec, body.get("schema", {}))
            for name in sorted(set(response.get("fields", [])) - props):
                problems.append(f"{label}: response field '{name}' is gone — the examples read it")
    return problems


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    try:
        with urllib.request.urlopen(SPEC, timeout=30) as response:
            spec = json.load(response)
    except Exception as exc:
        print(f"could not fetch {SPEC}: {exc}")
        return 1

    problems = check(spec, contract)
    if problems:
        print(f"{len(problems)} break(s) against the live API:\n")
        for problem in problems:
            print(f"  - {problem}")
        print("\nUpdate the examples and arcnm-contract.json, or the API regressed.")
        print("Either way somebody's first five minutes with ARCNM is currently broken.")
        return 1

    print(f"contract holds: {len(contract['operations'])} operations, every promise this repo makes is intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
