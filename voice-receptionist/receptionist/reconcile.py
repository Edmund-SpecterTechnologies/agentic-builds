"""Daily check that every ended Vapi call actually reached GHL.

The webhook can be misconfigured, the server can be down when Vapi posts, and a sync can be stuck. None
of those raise an error anyone sees. This compares Vapi's own call list with the ledger and reports:

    missing      ended calls Vapi has that the ledger never received
    unfinished   received calls whose sync is pending, failed, dead, or needs a person
    unclear      writes whose outcome is unknown (an owner text or booking that timed out)

A list endpoint that returns exactly `limit` rows may have more behind it, so a full page is reported as
TRUNCATED and the check refuses to call the window clean.

Usage:
    python -m receptionist.reconcile --calls vapi_calls.json        # offline, from an exported list
    python -m receptionist.reconcile --since 2026-11-18T00:00:00Z   # live, needs VAPI_API_KEY
Exit codes: 0 clean, 1 gaps found, 2 the check could not see the whole window.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

from .store import Store

VAPI_CALLS_URL = "https://api.vapi.ai/call"


def fetch_calls(since_iso: str, limit: int = 1000, transport: httpx.BaseTransport | None = None) -> list[dict]:
    key = os.environ.get("VAPI_API_KEY", "")
    if not key:
        raise SystemExit("VAPI_API_KEY is not set")
    with httpx.Client(timeout=30, transport=transport) as client:
        r = client.get(VAPI_CALLS_URL, params={"createdAtGt": since_iso, "limit": limit},
                       headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        return r.json()


def reconcile(store: Store, calls: list[dict], limit: int | None = None) -> dict:
    ended = [c for c in calls if c.get("status") == "ended" and c.get("id")]
    known = store.known_call_ids()
    return {
        "truncated": limit is not None and len(calls) >= limit,
        "vapi_ended_calls": len(ended),
        "missing": sorted(c["id"] for c in ended if c["id"] not in known),
        "unfinished": [{"call_id": e["call_id"], "status": e["status"], "error": e["last_error"]}
                       for e in store.events("pending", "failed", "dead", "needs_check")],
        "unclear": store.steps_with_status("sending"),
    }


def exit_code(report: dict) -> int:
    if report["truncated"]:
        return 2
    return 1 if (report["missing"] or report["unfinished"] or report["unclear"]) else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--calls", help="JSON file holding Vapi's call list")
    src.add_argument("--since", help="ISO time; fetch calls created after it from the Vapi API")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--db", default=os.environ.get("RECEPTIONIST_DB", "receptionist.db"))
    a = p.parse_args(argv)

    if a.calls:
        with open(a.calls, encoding="utf-8") as f:
            calls, limit = json.load(f), None
    else:
        calls, limit = fetch_calls(a.since, a.limit), a.limit
    report = reconcile(Store(a.db), calls, limit)
    print(json.dumps(report, indent=2))
    code = exit_code(report)
    if code == 2:
        print("TRUNCATED: Vapi returned a full page. Narrow --since and run again before trusting this.",
              file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
