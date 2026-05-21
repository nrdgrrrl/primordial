"""Persist narrow tutorial completion state outside simulation snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path

from primordial.settings import Settings

logger = logging.getLogger(__name__)

TUTORIAL_SEEN_VERSION = 1
TUTORIAL_STATE_KIND = "primordial.tutorial_user_state"


@dataclass(frozen=True)
class TutorialUserState:
    seen_version: int = 0
    skipped_version: int = 0

    @property
    def seen_current_version(self) -> bool:
        return max(self.seen_version, self.skipped_version) >= TUTORIAL_SEEN_VERSION


def tutorial_user_state_path(settings: Settings) -> Path:
    """Return the user-state sidecar path next to config.toml."""
    return Path(settings.config_path).parent / "tutorial_state.json"


def load_tutorial_user_state(settings: Settings) -> TutorialUserState:
    path = tutorial_user_state_path(settings)
    if not path.exists():
        return TutorialUserState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unable to read tutorial state from %s: %s", path, exc)
        return TutorialUserState()
    if not isinstance(payload, dict) or payload.get("kind") != TUTORIAL_STATE_KIND:
        return TutorialUserState()
    return TutorialUserState(
        seen_version=_coerce_int(payload.get("seen_version")),
        skipped_version=_coerce_int(payload.get("skipped_version")),
    )


def save_tutorial_user_state(
    settings: Settings,
    *,
    completed: bool = False,
    skipped: bool = False,
) -> Path | None:
    current = load_tutorial_user_state(settings)
    seen_version = current.seen_version
    skipped_version = current.skipped_version
    if completed:
        seen_version = max(seen_version, TUTORIAL_SEEN_VERSION)
    if skipped:
        skipped_version = max(skipped_version, TUTORIAL_SEEN_VERSION)
    path = tutorial_user_state_path(settings)
    payload = {
        "kind": TUTORIAL_STATE_KIND,
        "version": 1,
        "seen_version": seen_version,
        "skipped_version": skipped_version,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        logger.warning("Unable to save tutorial state to %s: %s", path, exc)
        return None
    return path


def should_auto_start_tutorial(
    settings: Settings,
    *,
    config_existed_before_startup: bool,
) -> bool:
    """Return whether onboarding should auto-run for this launch."""
    if config_existed_before_startup:
        return False
    return not load_tutorial_user_state(settings).seen_current_version


def _coerce_int(value: object) -> int:
    try:
        if isinstance(value, bool):
            return 0
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
