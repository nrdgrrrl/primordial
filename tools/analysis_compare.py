#!/usr/bin/env python3
"""Run a same-scenario seeded comparison and emit a structured report."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primordial.analysis import (
    generate_history_artifact,
    write_comparison_report,
)
from primordial.scenarios import list_scenarios


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        required=True,
        choices=list_scenarios(),
        help="Seeded scenario identifier.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        required=True,
        help="Seed to use for both comparison runs.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=180,
        help="Number of simulation steps per run.",
    )
    parser.add_argument(
        "--sample-every",
        type=int,
        default=30,
        help="Sampling interval in simulation steps.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the comparison report JSON file.",
    )
    args = parser.parse_args()

    left = generate_history_artifact(
        args.scenario,
        steps=args.steps,
        sample_every=args.sample_every,
        seed=args.seed,
    )
    right = generate_history_artifact(
        args.scenario,
        steps=args.steps,
        sample_every=args.sample_every,
        seed=args.seed,
    )
    write_comparison_report(left, right, output_path=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
