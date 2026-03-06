#!/usr/bin/env python3
"""Run a bounded offline analysis history capture and emit structured JSON."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primordial.analysis import write_history_artifact
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
        "--steps",
        type=int,
        default=180,
        help="Number of simulation steps to execute.",
    )
    parser.add_argument(
        "--sample-every",
        type=int,
        default=30,
        help="Sampling interval in simulation steps.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Optional explicit seed override for the scenario.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the JSON history artifact.",
    )
    args = parser.parse_args()

    write_history_artifact(
        args.scenario,
        steps=args.steps,
        sample_every=args.sample_every,
        seed=args.seed,
        output_path=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
