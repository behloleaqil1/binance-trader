#!/usr/bin/env python3
"""Keep the research decision store lean without losing anything.

When research/decisions.jsonl grows past TRIGGER entries, the oldest are moved
into a gzip-compressed archive under research/archive/ and the active file is
trimmed to the most recent KEEP entries. Archives are permanent (committed);
the active file stays small so the agent reads it cheaply every run.

Idempotent + safe to run on every research run.
"""
from __future__ import annotations

import gzip
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEC = os.path.join(ROOT, "research", "decisions.jsonl")
ARCH = os.path.join(ROOT, "research", "archive")

KEEP = 120       # recent entries to keep active
TRIGGER = 250    # rotate once the active file exceeds this many entries


def _date(line: str) -> str:
    try:
        return json.loads(line).get("date", "unknown")
    except Exception:
        return "unknown"


def main() -> None:
    if not os.path.exists(DEC):
        print("no decisions.jsonl yet; nothing to rotate")
        return
    with open(DEC) as f:
        lines = [ln for ln in f if ln.strip()]
    if len(lines) <= TRIGGER:
        print(f"decisions.jsonl: {len(lines)} entries (<= {TRIGGER}) — no rotation needed")
        return

    os.makedirs(ARCH, exist_ok=True)
    old, keep = lines[:-KEEP], lines[-KEEP:]
    frm, to = _date(old[0]), _date(old[-1])
    base = f"decisions-{frm}_to_{to}"
    path = os.path.join(ARCH, base + ".jsonl.gz")
    n = 1
    while os.path.exists(path):
        path = os.path.join(ARCH, f"{base}-{n}.jsonl.gz")
        n += 1

    with gzip.open(path, "wt") as g:
        g.writelines(old)
    with open(DEC, "w") as f:
        f.writelines(keep)

    print(f"archived {len(old)} old entries -> {os.path.relpath(path, ROOT)} (gzip); "
          f"kept {len(keep)} active. Nothing lost.")


if __name__ == "__main__":
    main()
