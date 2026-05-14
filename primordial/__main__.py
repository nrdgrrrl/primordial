"""Package entry point for ``python -m primordial``."""

from __future__ import annotations

import os

from primordial.utils.cli import parse_runtime_args
from primordial.utils.screensaver import parse_screensaver_args


def run() -> None:
    """Launch Primordial from the installed package/module name."""
    scr_args = parse_screensaver_args()
    runtime_args = parse_runtime_args()

    # Preview mode requires SDL_WINDOWID before pygame initializes.
    if scr_args.mode == "preview" and scr_args.preview_hwnd:
        os.environ["SDL_WINDOWID"] = str(scr_args.preview_hwnd)

    from primordial.main import main

    main(scr_args, runtime_args)


if __name__ == "__main__":
    run()
