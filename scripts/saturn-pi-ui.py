#!/usr/bin/env python3
"""Deprecated path — use saturn-pi ui."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent / "saturn-pi" / "tools" / "ui-operator"
sys.path.insert(0, str(ROOT))

from saturn_pi_ui.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
