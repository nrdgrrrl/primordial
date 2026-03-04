"""utils/paths.py — resource path resolution for dev and PyInstaller frozen builds.

When PyInstaller bundles the app with --onefile, all data files are extracted to
a temporary directory at runtime. sys._MEIPASS points to that directory.
When running from source, paths resolve relative to this file's parent package.

Usage:
    from primordial.utils.paths import get_base_path

    config_path = get_base_path() / "assets" / "icon.ico"
"""

from __future__ import annotations

import sys
from pathlib import Path


def get_base_path() -> Path:
    """Return the base resource path, handling both dev and PyInstaller frozen environments.

    In a frozen PyInstaller bundle (--onefile), sys._MEIPASS is set to the
    temporary extraction directory. At dev time, the base path is the project
    root (two levels above this file: primordial/utils/paths.py → project root).
    """
    if getattr(sys, "frozen", False):
        # Running inside a PyInstaller bundle
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # Running from source: project root is two levels up from this file
    return Path(__file__).parent.parent.parent
