"""Tutorial/onboarding models and user-state helpers."""

from .persistence import (
    TUTORIAL_SEEN_VERSION,
    TutorialUserState,
    load_tutorial_user_state,
    save_tutorial_user_state,
    should_auto_start_tutorial,
    tutorial_user_state_path,
)
from .state import TutorialState
from .steps import HighlightTarget, TutorialStep, build_default_tutorial_steps

__all__ = [
    "HighlightTarget",
    "TutorialStep",
    "TutorialState",
    "TutorialUserState",
    "TUTORIAL_SEEN_VERSION",
    "build_default_tutorial_steps",
    "load_tutorial_user_state",
    "save_tutorial_user_state",
    "should_auto_start_tutorial",
    "tutorial_user_state_path",
]
