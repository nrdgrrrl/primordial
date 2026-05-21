"""Runtime CLI parsing for non-screensaver flags."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Sequence

from primordial.config.config import Config


@dataclass(frozen=True)
class RuntimeArgs:
    """Application runtime flags passed via normal CLI options."""

    debug: bool = False
    profile: bool = False
    mode: str | None = None
    theme: str | None = None
    load: str | None = None
    save: str | None = None
    log: str | None = None
    milestone_log: str | None = None
    tutorial: bool = False


def build_runtime_arg_parser(*, add_help: bool) -> argparse.ArgumentParser:
    """Build the runtime CLI parser used for tolerant parsing and help output."""
    parser = argparse.ArgumentParser(
        prog="primordial",
        description="Primordial evolutionary screensaver and simulation.",
        add_help=add_help,
        epilog=(
            "Windows screensaver arguments:\n"
            "  /s            run fullscreen screensaver mode\n"
            "  /p HWND       render preview into the provided window handle\n"
            "  /c            open config mode"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable debug HUD timing overlays and verbose runtime logging",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="run a 60-second profile capture, write reports, then exit",
    )
    parser.add_argument(
        "--mode",
        type=str,
        metavar="MODE",
        help=f"launch override: {', '.join(Config.VALID_SIM_MODES)}",
    )
    parser.add_argument(
        "--theme",
        type=str,
        metavar="THEME",
        help=f"visual theme override: {', '.join(Config.VALID_VISUAL_THEMES)}",
    )
    parser.add_argument(
        "--load",
        type=str,
        metavar="PATH",
        help="load a saved world snapshot from PATH",
    )
    parser.add_argument(
        "--save",
        type=str,
        metavar="PATH",
        help="save the current world snapshot to PATH on exit",
    )
    parser.add_argument(
        "--log",
        type=str,
        metavar="KIND",
        help="enable optional run logging; supported value: csv",
    )
    parser.add_argument(
        "--milestone-log",
        type=str,
        metavar="PATH",
        help="write predator-prey milestone YAML to PATH under the run-log directory",
    )
    parser.add_argument(
        "--tutorial",
        action="store_true",
        help="force the in-game onboarding tutorial for this run",
    )
    parser.add_argument(
        "--show-tutorial",
        action="store_true",
        help="alias for --tutorial",
    )
    return parser


def should_print_runtime_help(argv: Sequence[str] | None = None) -> bool:
    """Return True when the user requested standard CLI help."""
    args = list(argv) if argv is not None else None
    return bool(args) and any(arg in {"-h", "--help"} for arg in args)


def format_runtime_help() -> str:
    """Return standard runtime CLI help text."""
    return build_runtime_arg_parser(add_help=True).format_help()


def parse_runtime_args(argv: Sequence[str] | None = None) -> RuntimeArgs:
    """
    Parse regular CLI args while ignoring unknown/screen-saver-style args.

    This parser is intentionally tolerant so `/s`, `/p`, `/c` screensaver args
    and future unknown flags do not crash normal startup.
    """
    parser = build_runtime_arg_parser(add_help=False)
    ns, _unknown = parser.parse_known_args(list(argv) if argv is not None else None)
    return RuntimeArgs(
        debug=bool(ns.debug),
        profile=bool(ns.profile),
        mode=ns.mode.lower() if ns.mode else None,
        theme=ns.theme.lower() if ns.theme else None,
        load=ns.load,
        save=ns.save,
        log=ns.log.lower() if ns.log else None,
        milestone_log=ns.milestone_log,
        tutorial=bool(ns.tutorial or ns.show_tutorial),
    )
