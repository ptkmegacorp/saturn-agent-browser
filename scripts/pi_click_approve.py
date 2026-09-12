#!/usr/bin/env python3
"""Click Saturn Pi Browser-auth Approve. Requires an exact request id."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Click Saturn Pi Approve")
    parser.add_argument("--request-id", required=True, help="Exact Auth request id")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    from saturn_agent_browser.pi_operator_click import click_browser_auth_approve

    clicked = click_browser_auth_approve(
        request_id=args.request_id,
        headless=not args.headed,
    )
    print(f"clicked_approve={clicked}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
