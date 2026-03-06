"""Runtime CLI parsing for non-screensaver flags."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class RuntimeArgs:
    """Application runtime flags passed via normal CLI options."""

    debug: bool = False
    profile: bool = False
    mode: str | None = None
    theme: str | None = None
    load: str | None = None
    save: str | None = None


def parse_runtime_args(argv: Sequence[str] | None = None) -> RuntimeArgs:
    """
    Parse regular CLI args while ignoring unknown/screen-saver-style args.

    This parser is intentionally tolerant so `/s`, `/p`, `/c` screensaver args
    and future unknown flags do not crash normal startup.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--mode", type=str)
    parser.add_argument("--theme", type=str)
    parser.add_argument("--load", type=str)
    parser.add_argument("--save", type=str)
    ns, _unknown = parser.parse_known_args(list(argv) if argv is not None else None)
    return RuntimeArgs(
        debug=bool(ns.debug),
        profile=bool(ns.profile),
        mode=ns.mode.lower() if ns.mode else None,
        theme=ns.theme.lower() if ns.theme else None,
        load=ns.load,
        save=ns.save,
    )
