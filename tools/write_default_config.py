#!/usr/bin/env python3
"""Overwrite local user config.toml with current canonical defaults.

Usage:
    tools/write_default_config.py --print-path
    tools/write_default_config.py --dry-run
    tools/write_default_config.py --backup --force
    tools/write_default_config.py --force
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primordial.config import Config, get_config_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-path",
        action="store_true",
        help="Print resolved config path and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print target path and config text that would be written without writing",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Back up existing config.toml before overwriting (requires --force)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing config.toml (required if file exists)",
    )
    args = parser.parse_args()

    config_path = get_config_path()

    if args.print_path:
        print(config_path)
        return 0

    if args.dry_run:
        print(f"Target: {config_path}")
        print("---")
        print(Config.canonical_toml())
        return 0

    if config_path.exists() and not args.force:
        print(
            f"Refusing to overwrite {config_path} — file exists. Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    if args.backup and config_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = config_path.with_name(f"config.toml.bak.{timestamp}")
        shutil.copy2(config_path, backup_path)
        print(f"Backed up existing config to {backup_path}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(Config.canonical_toml(), encoding="utf-8")
    print(f"Wrote canonical defaults to {config_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
