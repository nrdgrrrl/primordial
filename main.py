"""Top-level entry point for PyInstaller and direct execution.

This file lives at the project root so PyInstaller can use it as the build
target with a simple 'python main.py' or 'pyinstaller main.py' invocation.
The actual launcher logic lives in ``primordial.__main__`` so
``python main.py`` and ``python -m primordial`` stay aligned.
"""

from primordial.__main__ import run

if __name__ == "__main__":
    run()
