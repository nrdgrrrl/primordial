#!/usr/bin/env python3
"""Run bounded Primordial benchmark scenarios and emit structured JSON."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primordial.benchmarking import list_scenarios, run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        required=True,
        choices=list_scenarios(),
        help="Benchmark scenario identifier.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=10.0,
        help="Requested bounded run duration in wall-clock seconds.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the JSON summary to write.",
    )
    args = parser.parse_args()

    run_benchmark(
        args.scenario,
        seconds=args.seconds,
        output_path=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
