"""Runtime persistence paths and sidecar state helpers."""

from __future__ import annotations

import json
import logging
import sys
import webbrowser
from pathlib import Path
from typing import Any

import pygame

from primordial.display.mode import _force_windowed_mode
from primordial.milestone_logging import PredatorPreyMilestoneLogger
from primordial.rendering import Renderer
from primordial.run_logging import PredatorPreyCSVRunLogger
from primordial.settings import Settings
from primordial.simulation import Simulation
from primordial.utils.cli import RuntimeArgs
from primordial.utils.paths import get_base_path

logger = logging.getLogger(__name__)

PREDATOR_PREY_TUNING_STATE_VERSION = 1
PREDATOR_PREY_TUNING_STATE_KIND = "primordial.predator_prey_tuning_state"


def _default_snapshot_path(settings: Settings) -> Path:
    """Return the bounded default snapshot path used by in-app save/load."""
    return Path(settings.config_path).parent / "world_snapshot.json"


def _predator_prey_tuning_state_path(settings: Settings) -> Path:
    """Return the persisted predator-prey tuning state file path."""
    return Path(settings.config_path).parent / "predator_prey_tuning_state.json"


def _run_log_directory(settings: Settings) -> Path:
    """Return the directory that stores optional CSV run logs."""
    if getattr(sys, "frozen", False):
        return Path(settings.config_path).parent / "run_logs"
    return get_base_path() / "run_logs"


def _run_log_csv_path(settings: Settings) -> Path:
    """Return the predator-prey stability CSV path."""
    return _run_log_directory(settings) / "predator_prey_runs.csv"


def _create_run_logger(
    settings: Settings,
    runtime_args: RuntimeArgs,
) -> PredatorPreyCSVRunLogger | None:
    """Create the optional CSV run logger when requested at launch."""
    if runtime_args.log != "csv":
        return None
    csv_path = _run_log_csv_path(settings)
    run_logger = PredatorPreyCSVRunLogger(csv_path)
    logger.info("CSV run logging enabled: %s", csv_path)
    return run_logger


def _create_milestone_logger(
    settings: Settings,
    runtime_args: RuntimeArgs,
) -> PredatorPreyMilestoneLogger | None:
    """Create the optional milestone logger when requested at launch."""
    if not runtime_args.milestone_log:
        return None
    yaml_path = _run_log_directory(settings) / runtime_args.milestone_log
    ml = PredatorPreyMilestoneLogger(yaml_path)
    return ml


def _load_predator_prey_tuning_state(settings: Settings) -> dict[str, Any] | None:
    path = _predator_prey_tuning_state_path(settings)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unable to read predator-prey tuning state from %s: %s", path, exc)
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != PREDATOR_PREY_TUNING_STATE_VERSION:
        return None
    if payload.get("kind") != PREDATOR_PREY_TUNING_STATE_KIND:
        return None
    state = payload.get("state")
    return state if isinstance(state, dict) else None


def _save_predator_prey_tuning_state(settings: Settings, simulation: Simulation) -> Path | None:
    if settings.sim_mode != "predator_prey":
        return None
    path = _predator_prey_tuning_state_path(settings)
    payload = {
        "version": PREDATOR_PREY_TUNING_STATE_VERSION,
        "kind": PREDATOR_PREY_TUNING_STATE_KIND,
        "state": simulation.export_predator_prey_tuning_state(),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        logger.warning("Unable to save predator-prey tuning state to %s: %s", path, exc)
        return None
    return path


def _resolve_snapshot_path(
    settings: Settings,
    active_snapshot_path: str | Path | None,
) -> Path:
    """Reuse the active session path when present, otherwise use the default path."""
    if active_snapshot_path is None:
        return _default_snapshot_path(settings)
    return Path(active_snapshot_path)


def _predator_prey_help_path() -> Path:
    """Resolve the bundled quick start help path for browser launch."""
    return get_base_path() / "docs" / "help_quick_start.md"


def _open_predator_prey_help(
    settings: Settings,
    simulation: Simulation,
    renderer: Renderer,
) -> tuple[bool, str]:
    """Open the Primordial guide in the user's browser, exiting fullscreen first."""
    help_path = _predator_prey_help_path()
    if not help_path.exists():
        return False, f"Help file missing: {help_path.name}"

    if settings.fullscreen or bool(renderer.screen.get_flags() & pygame.FULLSCREEN):
        _force_windowed_mode(settings, simulation, renderer)

    try:
        opened = webbrowser.open_new_tab(help_path.resolve().as_uri())
    except (OSError, webbrowser.Error) as exc:
        logger.warning("Help launch failed for %s: %s", help_path, exc)
        return False, f"Help launch failed: {exc}"

    if not opened:
        logger.warning("Browser reported failure opening help file: %s", help_path)
        return False, f"Help launch failed for {help_path.name}"

    logger.info("Opened Primordial guide in browser: %s", help_path)
    return True, f"Opened {help_path.name} in browser"
