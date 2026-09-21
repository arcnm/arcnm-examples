#!/usr/bin/env python3
"""Every URL this repo sends people to must still resolve.

A dead link in an examples repo is worse than in a blog post: the reader is
already unsure whether the fault is theirs.

    python .github/check_links.py

Codes that count as alive, and why:
  200/301/302  fine
  401/403      the endpoint exists and wants credentials — that is the point
  405          exists, wrong method (the MCP endpoint is POST-only)
Anything else, including a timeout, fails.
"""

from __future__ import annotations

import pathlib
import re
import sys
import urllib.error
import urllib.request

ALIVE = {200, 301, 302, 401, 403, 405}
UA = "arcnm-examples-linkcheck/1.0"
SUFFIXES = {".md", ".py", ".ts", ".sh", ".json", ".yml"}

# The API base is a prefix the scripts build paths from, not a page.
SKIP = {"https://api.arcnm.io/api/v1"}

root = pathlib.Path(__file__).resolve().parent.parent
urls: dict[str, set[str]] = {}
for path in sorted(root.rglob("*")):
    # Skip .github/: these checkers contain the URL-matching regex itself, and
    # scanning them makes the pattern literal look like a malformed URL.
    if path.suffix not in SUFFIXES or ".git" in path.parts or ".github" in path.parts:
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    for url in re.findall(r"https://[^\s\"'`)\]<>]+", text):
        # `}` closes a shell default like ${VAR:-https://…/api/v1}; `\` ends a
        # line-continued curl argument. Neither is part of the URL.
        url = url.rstrip(".,;:}\\")
        if url in SKIP:
            continue
        urls.setdefault(url, set()).add(str(path.relative_to(root)))

print(f"checking {len(urls)} distinct URLs\n")
dead: list[str] = []
for url in sorted(urls):
    try:
        # Request() itself parses the URL and can raise, so build it in here:
        # a malformed link must be reported, never crash the run.
        request = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
        with urllib.request.urlopen(request, timeout=30) as response:
            code = response.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except Exception as exc:
        code, note = 0, str(exc)[:60]
        print(f"  DEAD {url}\n       {note}")
        dead.append(f"{url} ({note}) — in {', '.join(sorted(urls[url]))}")
        continue
    if code in ALIVE:
        print(f"  {code}  {url}")
    else:
        print(f"  DEAD {code} {url}")
        dead.append(f"{url} (HTTP {code}) — in {', '.join(sorted(urls[url]))}")

if dead:
    print(f"\n{len(dead)} dead link(s):")
    for item in dead:
        print(f"  - {item}")
    sys.exit(1)

print(f"\nall {len(urls)} links alive")
