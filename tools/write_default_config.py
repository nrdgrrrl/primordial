#!/usr/bin/env python3
"""Write canonical defaults to the local user config.toml."""

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
        help="Print the resolved config.toml path and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the canonical defaults without writing config.toml.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing config.toml.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a timestamped backup before overwriting an existing config.toml.",
    )
    args = parser.parse_args()

    config_path = get_config_path()

    if args.print_path:
        print(config_path)
        return 0

    canonical_toml = Config.canonical_toml()

    if args.dry_run:
        print(f"Target: {config_path}")
        print("---")
        print(canonical_toml, end="")
        return 0

    if config_path.exists() and not args.force:
        print(
            f"Refusing to overwrite {config_path}; pass --force to replace it.",
            file=sys.stderr,
        )
        return 1

    if args.backup and config_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = config_path.with_name(f"config.toml.bak.{timestamp}")
        shutil.copy2(config_path, backup_path)
        print(f"Backed up existing config to {backup_path}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(canonical_toml, encoding="utf-8")
    print(f"Wrote canonical defaults to {config_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
