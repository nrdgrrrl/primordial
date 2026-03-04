"""Top-level entry point for PyInstaller and direct execution.

This file lives at the project root so PyInstaller can use it as the build
target with a simple 'python main.py' or 'pyinstaller main.py' invocation.
It simply delegates to the real entry point inside the primordial package.

Usage (from source):
    python main.py           # normal mode
    python main.py /s        # screensaver mode
    python main.py /p HWND   # preview mode
    python main.py /c        # config mode

Usage (build):
    python build.py   →  dist/primordial or dist/primordial.exe + dist/primordial.scr
"""

from primordial.utils.screensaver import parse_screensaver_args

scr_args = parse_screensaver_args()

# Preview mode: SDL_WINDOWID must be set before pygame.init() which happens
# inside primordial.main.main(). Set it now, before the package is imported.
if scr_args.mode == "preview" and scr_args.preview_hwnd:
    import os
    os.environ["SDL_WINDOWID"] = str(scr_args.preview_hwnd)

from primordial.main import main

if __name__ == "__main__":
    main(scr_args)
