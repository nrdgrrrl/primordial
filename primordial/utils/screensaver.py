from dataclasses import dataclass
from typing import Optional
import sys

@dataclass
class ScreensaverArgs:
    mode: str          # "screensaver" | "preview" | "config" | "normal"
    preview_hwnd: Optional[int] = None

def parse_screensaver_args() -> ScreensaverArgs:
    """
    Parse Windows screensaver command-line arguments.
    /s or /S       → run as screensaver (fullscreen, quit on input)
    /p HWND        → render preview into provided window handle
    /c or /c:HWND  → show config dialog
    No args        → normal app mode (dev/Linux)
    """
    args = [a.lower() for a in sys.argv[1:]]

    if not args:
        return ScreensaverArgs(mode="normal")

    if args[0] in ("/s", "-s"):
        return ScreensaverArgs(mode="screensaver")

    if args[0] in ("/p", "-p") and len(args) > 1:
        try:
            hwnd = int(args[1])
            if hwnd <= 0:
                return ScreensaverArgs(mode="normal")
            return ScreensaverArgs(mode="preview", preview_hwnd=hwnd)
        except ValueError:
            return ScreensaverArgs(mode="normal")

    if args[0].startswith("/c") or args[0].startswith("-c"):
        return ScreensaverArgs(mode="config")

    return ScreensaverArgs(mode="normal")
