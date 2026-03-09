"""
build.py — run this to produce a standalone executable.

Works on both Linux (produces dist/primordial) and Windows (produces
dist/primordial.exe + dist/primordial.scr).

The output binary is fully self-contained: no Python installation required on the target machine.

Usage:
    python build.py

Expected output size: ~30–50 MB (pygame + numpy bundled together).
After the first run PyInstaller writes primordial.spec — commit that file for
reproducible builds via:  pyinstaller primordial.spec
"""

import os
import platform
import shutil
from pathlib import Path

import PyInstaller.__main__

# ---------------------------------------------------------------------------
# Clean previous build artifacts so we always get a fresh build
# ---------------------------------------------------------------------------

for _dir in ("build", "dist"):
    if Path(_dir).exists():
        shutil.rmtree(_dir)
        print(f"Cleaned {_dir}/")

# ---------------------------------------------------------------------------
# Build arguments
# ---------------------------------------------------------------------------

args = [
    "main.py",                  # Top-level entry point (project root)
    "--name=primordial",
    "--onefile",                # Single portable binary
    "--noconsole",              # No terminal window (screensaver / GUI app)
    "--clean",                  # Remove PyInstaller cache before building
    "--distpath=dist",
]

# Include assets directory if it exists (for future icon/font additions)
# Format: source<sep>dest  — os.pathsep is ':' on Linux/Mac, ';' on Windows
_assets = Path("primordial") / "assets"
if _assets.exists():
    args.append(f"--add-data={_assets}{os.pathsep}primordial/assets")

_canonical_defaults = Path("primordial") / "config" / "defaults.toml"
if _canonical_defaults.exists():
    args.append(
        f"--add-data={_canonical_defaults}{os.pathsep}primordial/config"
    )

# Windows-specific build options
if platform.system() == "Windows":
    # Icon (optional — only applied if the file exists)
    _icon = Path("assets") / "icon.ico"
    if _icon.exists():
        args.append(f"--icon={_icon}")

    # Version file (optional — adds Windows file properties metadata)
    _version = Path("version.txt")
    if _version.exists():
        args.append(f"--version-file={_version}")

# ---------------------------------------------------------------------------
# Run PyInstaller
# ---------------------------------------------------------------------------

print("Running PyInstaller…")
PyInstaller.__main__.run(args)

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

_ext = ".exe" if platform.system() == "Windows" else ""
_out = Path("dist") / f"primordial{_ext}"
if _out.exists():
    size_mb = _out.stat().st_size / (1024 * 1024)
    print(f"\nBuild complete: {_out}  ({size_mb:.1f} MB)")

    # On Windows, copy the .exe to .scr so it can be right-click installed
    # as a screensaver from the dist/ directory.
    if platform.system() == "Windows":
        _scr = Path("dist") / "primordial.scr"
        shutil.copy(_out, _scr)
        print(f"Screensaver:    {_scr}")
else:
    print("\nBuild may have failed — check output above.")
