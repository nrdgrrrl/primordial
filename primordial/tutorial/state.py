"""Runtime state for the in-game tutorial overlay."""

from __future__ import annotations

from dataclasses import dataclass

from .steps import TutorialStep, build_default_tutorial_steps


@dataclass
class TutorialState:
    """Track tutorial progression, hover/focus, and close state."""

    steps: tuple[TutorialStep, ...] = build_default_tutorial_steps()
    current_index: int = 0
    active: bool = False
    forced: bool = False
    completed: bool = False
    skipped: bool = False
    hover_action: str | None = None
    text_scroll: int = 0
    text_line_count: int = 0
    text_visible_lines: int = 1
    previous_paused: bool | None = None

    @property
    def current_step(self) -> TutorialStep:
        return self.steps[self.current_index]

    @property
    def is_first_step(self) -> bool:
        return self.current_index <= 0

    @property
    def is_last_step(self) -> bool:
        return self.current_index >= len(self.steps) - 1

    def start(self, *, forced: bool = False, previous_paused: bool | None = None) -> None:
        self.active = True
        self.forced = forced
        self.completed = False
        self.skipped = False
        self.current_index = 0
        self.hover_action = None
        self.text_scroll = 0
        self.previous_paused = previous_paused

    def next(self) -> str | None:
        if self.is_last_step:
            return self.finish()
        self.current_index += 1
        self.text_scroll = 0
        return None

    def back(self) -> None:
        self.current_index = max(0, self.current_index - 1)
        self.text_scroll = 0

    def skip(self) -> str:
        self.active = False
        self.skipped = True
        return "skip"

    def finish(self) -> str:
        self.active = False
        self.completed = True
        return "finish"

    def close(self) -> str:
        self.active = False
        self.skipped = True
        return "close"

    def set_text_bounds(self, *, line_count: int, visible_lines: int) -> None:
        self.text_line_count = max(0, line_count)
        self.text_visible_lines = max(1, visible_lines)
        self.clamp_text_scroll()

    def scroll_text(self, amount: int) -> None:
        self.text_scroll += amount
        self.clamp_text_scroll()

    def clamp_text_scroll(self) -> None:
        max_scroll = max(0, self.text_line_count - self.text_visible_lines)
        self.text_scroll = max(0, min(max_scroll, self.text_scroll))

    def paused_after_exit(self) -> bool:
        """Return the post-tutorial pause state for the first-version UX."""
        return False
