"""Declarative tutorial step content for Primordial onboarding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


HighlightTarget = Literal[
    "none",
    "world",
    "hud",
    "settings",
    "help",
    "creatures",
    "food",
    "predators",
    "lineages",
    "zones",
    "depth",
    "game_over",
]


@dataclass(frozen=True)
class TutorialStep:
    id: str
    phase: str
    title: str
    body: str
    highlight: HighlightTarget = "none"
    pause_simulation: bool = True


def build_default_tutorial_steps() -> tuple[TutorialStep, ...]:
    """Return the first-version linear onboarding flow."""
    return (
        TutorialStep(
            id="welcome",
            phase="App Basics",
            title="Welcome to Primordial",
            body=(
                "Primordial is a living simulation and screensaver. The glowing "
                "organisms are not just particles: they carry traits, spend "
                "energy, reproduce with mutation, and disappear when they fail "
                "to survive."
            ),
            highlight="none",
        ),
        TutorialStep(
            id="basic_controls",
            phase="App Basics",
            title="Basic Controls",
            body=(
                "Space pauses or resumes the simulation. F toggles fullscreen. "
                "R starts a fresh run. Esc or Q quits. This tutorial uses Next, "
                "Back, and Skip buttons, and the keyboard shortcuts shown below."
            ),
            highlight="none",
        ),
        TutorialStep(
            id="settings",
            phase="App Basics",
            title="Settings",
            body=(
                "Press S after the tutorial to open settings. The settings panel "
                "supports keyboard and mouse control, grouped categories, "
                "descriptions, and clear reset-required markers."
            ),
            highlight="none",
        ),
        TutorialStep(
            id="help_browser",
            phase="App Basics",
            title="Help Browser",
            body=(
                "Open Guide from the settings Actions category to use the "
                "searchable in-app documentation browser. Use it when you want "
                "deeper explanations than this quick tour provides."
            ),
            highlight="none",
        ),
        TutorialStep(
            id="hud",
            phase="App Basics",
            title="HUD",
            body=(
                "The HUD summarizes population, mode-specific state, food, and "
                "debug-friendly indicators. Press H during normal play to show "
                "or hide it."
            ),
            highlight="hud",
        ),
        TutorialStep(
            id="creatures",
            phase="Simulation Basics",
            title="Creatures",
            body=(
                "Each glowing creature has a genome. Its traits influence speed, "
                "size, sensing, energy use, lifespan, motion, color, and glyph "
                "shape. Related creatures tend to look related."
            ),
            highlight="creatures",
            pause_simulation=False,
        ),
        TutorialStep(
            id="food",
            phase="Simulation Basics",
            title="Food",
            body=(
                "Food particles are energy. Creatures that find food efficiently "
                "are more likely to reproduce. Scarcity creates pressure and can "
                "turn a stable-looking population into a crash."
            ),
            highlight="food",
            pause_simulation=False,
        ),
        TutorialStep(
            id="predators_prey",
            phase="Simulation Basics",
            title="Predators and Prey",
            body=(
                "In predator-prey mode, prey forage and flee while predators hunt "
                "prey on contact. Warm-tinted organisms are predators; cooler "
                "organisms are prey."
            ),
            highlight="predators",
            pause_simulation=False,
        ),
        TutorialStep(
            id="birth_death",
            phase="Simulation Basics",
            title="Birth, Death, and Mutation",
            body=(
                "When a creature reaches its reproduction energy threshold, it "
                "buds an offspring and both keep part of the energy. Offspring "
                "inherit a mutated genome. Death comes from age, energy loss, or "
                "predation depending on mode."
            ),
            highlight="creatures",
        ),
        TutorialStep(
            id="lineages",
            phase="Simulation Basics",
            title="Lineages and Kin Lines",
            body=(
                "Lineages are families of related creatures. Kin lines and "
                "territory shimmer help reveal which families are clustering, "
                "spreading, or vanishing."
            ),
            highlight="lineages",
            pause_simulation=False,
        ),
        TutorialStep(
            id="zones",
            phase="Simulation Basics",
            title="Zones",
            body=(
                "Soft environmental zones create local pressure. Some traits do "
                "better in some regions, which can slowly pull lineages toward "
                "different parts of the world."
            ),
            highlight="zones",
            pause_simulation=False,
        ),
        TutorialStep(
            id="depth",
            phase="Simulation Basics",
            title="Depth Bands",
            body=(
                "Predator-prey mode has surface, mid, and deep bands. Depth "
                "affects sensing, food access, escape, and cross-band hunting "
                "misses, even when the visual cue is subtle."
            ),
            highlight="none",
        ),
        TutorialStep(
            id="collapse",
            phase="Simulation Basics",
            title="Food Cycle and Collapse",
            body=(
                "Food abundance can rise and fall. If either predators or prey "
                "collapse long enough in predator-prey mode, the run freezes on "
                "a GAME OVER screen, records survival, then restarts."
            ),
            highlight="none",
        ),
        TutorialStep(
            id="evolution",
            phase="Simulation Basics",
            title="Evolution",
            body=(
                "Evolution here means trait sorting under pressure. This is not "
                "open-ended artificial life, but mutations that help creatures "
                "survive and reproduce can spread through future generations."
            ),
            highlight="none",
            pause_simulation=False,
        ),
        TutorialStep(
            id="finish",
            phase="Finish",
            title="You Are Ready",
            body=(
                "Let the simulation run, open settings when you want to tune it, "
                "and use the Guide for deeper explanations. You can replay this "
                "tutorial later with python main.py --tutorial."
            ),
            highlight="none",
        ),
    )
