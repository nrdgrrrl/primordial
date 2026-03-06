#!/usr/bin/env python3
"""Print a concise human-readable summary for a history artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primordial.analysis import format_history_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history",
        required=True,
        help="Path to a history artifact JSON file.",
    )
    args = parser.parse_args()

    history_path = Path(args.history)
    payload = json.loads(history_path.read_text(encoding="utf-8"))
    print(format_history_summary(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
