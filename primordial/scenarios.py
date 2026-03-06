"""Shared seeded scenario presets for benchmarks and analysis runs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .settings import Settings


@dataclass(frozen=True)
class ScenarioDefinition:
    """Static scenario definition shared across bounded tooling."""

    id: str
    mode: str
    seed: int
    width: int = 1280
    height: int = 720
    settings_overrides: dict[str, Any] = field(default_factory=dict)
    mode_overrides: dict[str, Any] = field(default_factory=dict)


SCENARIOS: dict[str, ScenarioDefinition] = {
    "energy_medium": ScenarioDefinition(
        id="energy_medium",
        mode="energy",
        seed=104729,
        settings_overrides={
            "visual_theme": "ocean",
            "fullscreen": False,
            "target_fps": 60,
            "show_hud": False,
            "initial_population": 100,
            "max_population": 130,
            "food_spawn_rate": 0.55,
            "food_max_particles": 220,
            "food_cycle_enabled": True,
            "food_cycle_period": 1800,
            "mutation_rate": 0.06,
            "cosmic_ray_rate": 0.0003,
            "energy_to_reproduce": 0.82,
            "zone_count": 5,
            "zone_strength": 0.8,
            "death_particle_count": 5,
        },
    ),
    "predator_prey_medium": ScenarioDefinition(
        id="predator_prey_medium",
        mode="predator_prey",
        seed=161803,
        settings_overrides={
            "visual_theme": "ocean",
            "fullscreen": False,
            "target_fps": 60,
            "show_hud": False,
            "food_max_particles": 260,
            "zone_count": 5,
            "zone_strength": 0.75,
            "death_particle_count": 5,
        },
        mode_overrides={
            "initial_population": 110,
            "predator_fraction": 0.28,
            "food_spawn_rate": 0.55,
            "mutation_rate": 0.06,
            "energy_to_reproduce": 0.72,
        },
    ),
    "boids_dense": ScenarioDefinition(
        id="boids_dense",
        mode="boids",
        seed=130363,
        settings_overrides={
            "visual_theme": "ocean",
            "fullscreen": False,
            "target_fps": 60,
            "show_hud": False,
            "zone_count": 5,
            "zone_strength": 0.5,
            "death_particle_count": 5,
        },
        mode_overrides={
            "initial_population": 100,
            "max_population": 120,
            "mutation_rate": 0.05,
            "energy_to_reproduce": 0.80,
            "food_cycle_enabled": False,
            "zone_strength": 0.5,
        },
    ),
}


def list_scenarios() -> list[str]:
    """Return supported seeded scenario identifiers."""
    return sorted(SCENARIOS)


def get_scenario(scenario_id: str) -> ScenarioDefinition:
    """Return a validated scenario definition."""
    try:
        return SCENARIOS[scenario_id]
    except KeyError as exc:
        valid = ", ".join(list_scenarios())
        raise ValueError(f"Unknown scenario '{scenario_id}'. Valid scenarios: {valid}") from exc


def build_settings_for_scenario(scenario_id: str) -> tuple[ScenarioDefinition, Settings]:
    """Build a fresh Settings instance for a shared scenario definition."""
    scenario = get_scenario(scenario_id)
    settings = Settings()
    apply_scenario_settings(settings, scenario)
    return scenario, settings


def apply_scenario_settings(settings: Settings, scenario: ScenarioDefinition) -> None:
    """Apply a scenario definition to a mutable Settings instance."""
    settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
    settings.sim_mode = scenario.mode
    for key, value in scenario.settings_overrides.items():
        setattr(settings, key, value)
    if scenario.mode in settings.mode_params:
        settings.mode_params[scenario.mode].update(scenario.mode_overrides)
