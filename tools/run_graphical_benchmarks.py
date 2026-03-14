#!/usr/bin/env python3
"""Run the full live graphical benchmark suite and package the outputs."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shlex
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primordial.graphical_benchmarking import run_graphical_benchmark_suite


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Top-level output directory. Defaults to benchmark_outputs/graphical_benchmark_<timestamp>/",
    )
    parser.add_argument(
        "--skip-profiles",
        action="store_true",
        help="Skip representative cProfile captures.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.output_root is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_root = REPO_ROOT / "benchmark_outputs" / f"graphical_benchmark_{stamp}"
    else:
        output_root = args.output_root
    command = shlex.join([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])
    run_graphical_benchmark_suite(
        output_root=output_root,
        command=command,
        collect_profiles=not args.skip_profiles,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
