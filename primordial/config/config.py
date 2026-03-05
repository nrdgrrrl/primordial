"""Persistent TOML-backed configuration for Primordial."""

from __future__ import annotations

import logging
import platform
import shutil
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python <3.11
    import tomli as tomllib  # type: ignore

logger = logging.getLogger(__name__)


class Config:
    """Typed runtime configuration with load/save/reset support."""

    VALID_SIM_MODES = ["energy", "predator_prey", "boids", "drift"]
    VALID_VISUAL_THEMES = ["ocean", "petri", "geometric", "chaotic"]

    def __init__(self) -> None:
        self._apply_defaults()
        self.config_path = get_config_path()
        self._load_or_create()

    def _apply_defaults(self) -> None:
        self.sim_mode = "energy"
        self.visual_theme = "ocean"

        self.initial_population = 80
        self.max_population = 220
        self.food_spawn_rate = 0.6
        self.food_max_particles = 300
        self.food_cycle_period = 1800
        self.food_cycle_enabled = True
        self.energy_to_reproduce = 0.80
        self.creature_speed_base = 1.5

        self.fullscreen = True
        self.target_fps = 60
        self.show_hud = True

        self.mutation_rate = 0.06
        self.cosmic_ray_rate = 0.0003
        self.zone_count = 5
        self.zone_strength = 0.8

        self.glyph_size_base = 48
        self.kin_line_max_distance = 120.0
        self.kin_line_min_group = 3
        self.territory_top_n = 3
        self.territory_shimmer_lerp = 0.05
        self.territory_fade_seconds = 2.0
        self.death_animation_frames = 40
        self.birth_animation_frames = 30
        self.death_particle_count = 5

    def _load_or_create(self) -> None:
        if not self.config_path.exists():
            self.save()
            return

        try:
            with self.config_path.open("rb") as f:
                data = tomllib.load(f)
        except Exception as exc:
            logger.warning("Config is unreadable; backing up and resetting: %s", exc)
            backup_path = self.config_path.with_suffix(".toml.bak")
            shutil.copy2(self.config_path, backup_path)
            self._apply_defaults()
            self.save()
            return

        self._merge_from_dict(data)
        self._validate()

    def _merge_from_dict(self, data: dict[str, Any]) -> None:
        simulation = data.get("simulation", {})
        creature = data.get("creature", {})
        display = data.get("display", {})
        evolution = data.get("evolution", {})

        self.sim_mode = simulation.get("mode", self.sim_mode)
        self.initial_population = int(simulation.get("initial_population", self.initial_population))
        self.max_population = int(simulation.get("max_population", self.max_population))
        self.food_spawn_rate = float(simulation.get("food_spawn_rate", self.food_spawn_rate))
        self.food_cycle_enabled = bool(simulation.get("food_cycle_enabled", self.food_cycle_enabled))
        self.food_cycle_period = int(simulation.get("food_cycle_period", self.food_cycle_period))
        self.creature_speed_base = float(simulation.get("creature_speed_base", self.creature_speed_base))
        self.zone_count = int(simulation.get("zone_count", self.zone_count))
        self.zone_strength = float(simulation.get("zone_strength", self.zone_strength))

        self.energy_to_reproduce = float(creature.get("energy_to_reproduce", self.energy_to_reproduce))

        self.visual_theme = display.get("visual_theme", self.visual_theme)
        self.fullscreen = bool(display.get("fullscreen", self.fullscreen))
        self.target_fps = int(display.get("target_fps", self.target_fps))
        self.show_hud = bool(display.get("show_hud", self.show_hud))

        self.mutation_rate = float(evolution.get("mutation_rate", self.mutation_rate))
        self.cosmic_ray_rate = float(evolution.get("cosmic_ray_rate", self.cosmic_ray_rate))
        self.food_cycle_enabled = bool(evolution.get("food_cycle_enabled", self.food_cycle_enabled))
        self.food_cycle_period = int(evolution.get("food_cycle_period", self.food_cycle_period))
        self.zone_count = int(evolution.get("zone_count", self.zone_count))
        self.zone_strength = float(evolution.get("zone_strength", self.zone_strength))

    def _validate(self) -> None:
        if self.sim_mode not in self.VALID_SIM_MODES:
            self.sim_mode = "energy"
        if self.visual_theme not in self.VALID_VISUAL_THEMES:
            self.visual_theme = "ocean"

        self.initial_population = max(0, self.initial_population)
        self.max_population = max(1, self.max_population)
        self.food_spawn_rate = max(0.0, self.food_spawn_rate)
        self.food_cycle_period = max(1, self.food_cycle_period)
        self.mutation_rate = max(0.0, min(1.0, self.mutation_rate))
        self.cosmic_ray_rate = max(0.0, min(1.0, self.cosmic_ray_rate))
        self.energy_to_reproduce = max(0.05, min(1.0, self.energy_to_reproduce))
        self.creature_speed_base = max(0.1, self.creature_speed_base)
        self.zone_count = max(0, self.zone_count)
        self.zone_strength = max(0.0, min(1.0, self.zone_strength))
        self.target_fps = max(1, self.target_fps)
        self.food_max_particles = max(1, self.food_max_particles)

    def reset_to_defaults(self) -> None:
        self._apply_defaults()
        self.save()

    def save(self) -> None:
        self._validate()
        self.config_path.write_text(self.to_toml(), encoding="utf-8")

    def to_toml(self) -> str:
        return f"""# Primordial configuration file
# Edit by hand or press S in-app to change settings.

[simulation]
mode = \"{self.sim_mode}\"           # energy | predator_prey | boids | drift
initial_population = {self.initial_population}
max_population = {self.max_population}
food_spawn_rate = {self.food_spawn_rate:.4f}
food_cycle_enabled = {str(self.food_cycle_enabled).lower()}
food_cycle_period = {self.food_cycle_period}
mutation_rate = {self.mutation_rate:.4f}
cosmic_ray_rate = {self.cosmic_ray_rate:.6f}
energy_to_reproduce = {self.energy_to_reproduce:.4f}
creature_speed_base = {self.creature_speed_base:.4f}
zone_count = {self.zone_count}
zone_strength = {self.zone_strength:.4f}

[creature]
energy_to_reproduce = {self.energy_to_reproduce:.4f}

[display]
visual_theme = \"{self.visual_theme}\"    # ocean | petri | geometric | chaotic
fullscreen = {str(self.fullscreen).lower()}
target_fps = {self.target_fps}
show_hud = {str(self.show_hud).lower()}

[evolution]
mutation_rate = {self.mutation_rate:.4f}
cosmic_ray_rate = {self.cosmic_ray_rate:.6f}
food_cycle_enabled = {str(self.food_cycle_enabled).lower()}
food_cycle_period = {self.food_cycle_period}
zone_count = {self.zone_count}
zone_strength = {self.zone_strength:.4f}
"""


def get_config_path() -> Path:
    """Return platform-appropriate config file path."""
    if platform.system() == "Windows":
        base = Path.home() / "AppData" / "Roaming" / "Primordial"
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "Primordial"
    else:
        base = Path.home() / ".config" / "primordial"
    base.mkdir(parents=True, exist_ok=True)
    return base / "config.toml"
