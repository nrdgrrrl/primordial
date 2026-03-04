"""Top-level entry point for PyInstaller and direct execution.

This file lives at the project root so PyInstaller can use it as the build
target with a simple 'python main.py' or 'pyinstaller main.py' invocation.
It simply delegates to the real entry point inside the primordial package.

Usage (from source):
    python main.py

Usage (build):
    python build.py   →  dist/primordial or dist/primordial.exe
"""

from primordial.main import main

if __name__ == "__main__":
    main()
