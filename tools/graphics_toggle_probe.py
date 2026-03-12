#!/usr/bin/env python3
"""Run a small graphical fullscreen/windowed toggle probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primordial.graphics_probe import run_display_toggle_probe


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Launch the real pygame runtime, pause world evolution, toggle "
            "fullscreen/windowed mode, and capture screenshots plus a JSON report."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build") / "graphics-toggle-probe",
        help="Directory for screenshots and report.json",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=104729,
        help="Random seed used before creating the simulation world.",
    )
    parser.add_argument(
        "--toggle-count",
        type=int,
        default=4,
        help="Number of fullscreen/windowed transitions to perform.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="energy",
        help="Simulation mode to launch.",
    )
    parser.add_argument(
        "--theme",
        type=str,
        default="ocean",
        help="Visual theme to launch.",
    )
    parser.add_argument(
        "--start-windowed",
        action="store_true",
        help="Start in windowed mode instead of fullscreen.",
    )
    parser.add_argument(
        "--no-settings-overlay",
        action="store_true",
        help="Do not render the in-app settings overlay during the probe.",
    )
    parser.add_argument(
        "--settle-frames",
        type=int,
        default=2,
        help="Frames to render after each toggle before capturing.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = run_display_toggle_probe(
        args.output_dir,
        seed=args.seed,
        start_fullscreen=not args.start_windowed,
        toggle_count=max(1, args.toggle_count),
        mode=args.mode,
        theme=args.theme,
        open_settings_overlay=not args.no_settings_overlay,
        settle_frames=max(1, args.settle_frames),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["checks"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
