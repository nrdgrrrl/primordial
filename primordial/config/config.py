"""Persistent TOML-backed configuration for Primordial."""

from __future__ import annotations

from copy import deepcopy
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
    DEFAULT_MODE_PARAMS: dict[str, dict[str, Any]] = {
        "predator_prey": {
            "initial_population": 120,
            "predator_fraction": 0.30,
            "food_spawn_rate": 0.5000,
            "mutation_rate": 0.0800,
            "energy_to_reproduce": 0.7000,
        },
        "boids": {
            "initial_population": 150,
            "max_population": 300,
            "mutation_rate": 0.0700,
            "energy_to_reproduce": 0.7200,
            "food_cycle_enabled": False,
            "zone_strength": 0.5000,
        },
        "drift": {
            "initial_population": 60,
            "max_population": 200,
            "mutation_rate": 0.0400,
            "cosmic_ray_rate": 0.000600,
            "energy_to_reproduce": 0.9500,
            "food_cycle_enabled": False,
            "zone_strength": 0.6000,
            "target_fps": 60,
        },
    }

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

        # Per-mode parameter overrides loaded from [modes.*] TOML sections
        self.mode_params: dict[str, dict[str, Any]] = deepcopy(self.DEFAULT_MODE_PARAMS)

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
        if not isinstance(data, dict):
            logger.warning("Config root must be a TOML table; keeping defaults.")
            return

        root_known = {"simulation", "creature", "display", "evolution", "rendering", "modes"}
        self._warn_unknown_keys("root", data, root_known)

        simulation = self._read_section(data, "simulation")
        creature = self._read_section(data, "creature")
        display = self._read_section(data, "display")
        evolution = self._read_section(data, "evolution")
        rendering = self._read_section(data, "rendering")

        self._warn_unknown_keys(
            "simulation",
            simulation,
            {
                "mode",
                "initial_population",
                "max_population",
                "food_spawn_rate",
                "food_max_particles",
                "food_cycle_enabled",
                "food_cycle_period",
                "mutation_rate",
                "cosmic_ray_rate",
                "energy_to_reproduce",
                "creature_speed_base",
                "zone_count",
                "zone_strength",
            },
        )
        self._warn_unknown_keys("creature", creature, {"energy_to_reproduce"})
        self._warn_unknown_keys(
            "display",
            display,
            {"visual_theme", "fullscreen", "target_fps", "show_hud"},
        )
        self._warn_unknown_keys(
            "evolution",
            evolution,
            {
                "mutation_rate",
                "cosmic_ray_rate",
                "food_cycle_enabled",
                "food_cycle_period",
                "zone_count",
                "zone_strength",
            },
        )
        self._warn_unknown_keys(
            "rendering",
            rendering,
            {
                "glyph_size_base",
                "kin_line_max_distance",
                "kin_line_min_group",
                "territory_top_n",
                "territory_shimmer_lerp",
                "territory_fade_seconds",
                "death_animation_frames",
                "birth_animation_frames",
                "death_particle_count",
            },
        )

        self.sim_mode = self._coerce_str(simulation, "mode", self.sim_mode)
        self.initial_population = self._coerce_int(
            simulation, "initial_population", self.initial_population
        )
        self.max_population = self._coerce_int(
            simulation, "max_population", self.max_population
        )
        self.food_spawn_rate = self._coerce_float(
            simulation, "food_spawn_rate", self.food_spawn_rate
        )
        self.food_max_particles = self._coerce_int(
            simulation, "food_max_particles", self.food_max_particles
        )
        self.food_cycle_enabled = self._coerce_bool(
            simulation, "food_cycle_enabled", self.food_cycle_enabled
        )
        self.food_cycle_period = self._coerce_int(
            simulation, "food_cycle_period", self.food_cycle_period
        )
        self.creature_speed_base = self._coerce_float(
            simulation, "creature_speed_base", self.creature_speed_base
        )
        self.zone_count = self._coerce_int(simulation, "zone_count", self.zone_count)
        self.zone_strength = self._coerce_float(
            simulation, "zone_strength", self.zone_strength
        )
        self.mutation_rate = self._coerce_float(
            simulation, "mutation_rate", self.mutation_rate
        )
        self.cosmic_ray_rate = self._coerce_float(
            simulation, "cosmic_ray_rate", self.cosmic_ray_rate
        )
        self.energy_to_reproduce = self._coerce_float(
            simulation, "energy_to_reproduce", self.energy_to_reproduce
        )

        self.energy_to_reproduce = self._coerce_float(
            creature, "energy_to_reproduce", self.energy_to_reproduce
        )

        self.visual_theme = self._coerce_str(display, "visual_theme", self.visual_theme)
        self.fullscreen = self._coerce_bool(display, "fullscreen", self.fullscreen)
        self.target_fps = self._coerce_int(display, "target_fps", self.target_fps)
        self.show_hud = self._coerce_bool(display, "show_hud", self.show_hud)

        # Backward-compatible values from [evolution]
        self.mutation_rate = self._coerce_float(
            evolution, "mutation_rate", self.mutation_rate
        )
        self.cosmic_ray_rate = self._coerce_float(
            evolution, "cosmic_ray_rate", self.cosmic_ray_rate
        )
        self.food_cycle_enabled = self._coerce_bool(
            evolution, "food_cycle_enabled", self.food_cycle_enabled
        )
        self.food_cycle_period = self._coerce_int(
            evolution, "food_cycle_period", self.food_cycle_period
        )
        self.zone_count = self._coerce_int(evolution, "zone_count", self.zone_count)
        self.zone_strength = self._coerce_float(
            evolution, "zone_strength", self.zone_strength
        )

        self.glyph_size_base = self._coerce_int(
            rendering, "glyph_size_base", self.glyph_size_base
        )
        self.kin_line_max_distance = self._coerce_float(
            rendering, "kin_line_max_distance", self.kin_line_max_distance
        )
        self.kin_line_min_group = self._coerce_int(
            rendering, "kin_line_min_group", self.kin_line_min_group
        )
        self.territory_top_n = self._coerce_int(
            rendering, "territory_top_n", self.territory_top_n
        )
        self.territory_shimmer_lerp = self._coerce_float(
            rendering, "territory_shimmer_lerp", self.territory_shimmer_lerp
        )
        self.territory_fade_seconds = self._coerce_float(
            rendering, "territory_fade_seconds", self.territory_fade_seconds
        )
        self.death_animation_frames = self._coerce_int(
            rendering, "death_animation_frames", self.death_animation_frames
        )
        self.birth_animation_frames = self._coerce_int(
            rendering, "birth_animation_frames", self.birth_animation_frames
        )
        self.death_particle_count = self._coerce_int(
            rendering, "death_particle_count", self.death_particle_count
        )

        self._merge_mode_params(data.get("modes", {}))

    def _validate(self) -> None:
        if self.sim_mode not in self.VALID_SIM_MODES:
            logger.warning("Invalid sim_mode '%s'; falling back to energy.", self.sim_mode)
            self.sim_mode = "energy"
        if self.visual_theme not in self.VALID_VISUAL_THEMES:
            logger.warning("Invalid visual_theme '%s'; falling back to ocean.", self.visual_theme)
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
        self.glyph_size_base = max(8, self.glyph_size_base)
        self.kin_line_max_distance = max(1.0, self.kin_line_max_distance)
        self.kin_line_min_group = max(2, self.kin_line_min_group)
        self.territory_top_n = max(1, self.territory_top_n)
        self.territory_shimmer_lerp = max(0.001, min(1.0, self.territory_shimmer_lerp))
        self.territory_fade_seconds = max(0.1, self.territory_fade_seconds)
        self.death_animation_frames = max(1, self.death_animation_frames)
        self.birth_animation_frames = max(1, self.birth_animation_frames)
        self.death_particle_count = max(0, self.death_particle_count)
        self._validate_mode_params()

    def reset_to_defaults(self) -> None:
        self._apply_defaults()
        self.save()

    def save(self) -> None:
        self._validate()
        self.config_path.write_text(self.to_toml(), encoding="utf-8")

    def to_toml(self) -> str:
        mode_params = deepcopy(self.DEFAULT_MODE_PARAMS)
        for mode_name, overrides in self.mode_params.items():
            if mode_name not in mode_params:
                continue
            mode_params[mode_name].update(overrides)

        def _fmt(val: Any) -> str:
            if isinstance(val, bool):
                return str(val).lower()
            if isinstance(val, float):
                return f"{val:.6f}" if abs(val) < 0.01 else f"{val:.4f}"
            return str(val)

        lines = ["""# Primordial configuration file
# Edit by hand or press S in-app to change settings.

[simulation]
mode = \"{self.sim_mode}\"           # energy | predator_prey | boids | drift
initial_population = {self.initial_population}
max_population = {self.max_population}
food_spawn_rate = {self.food_spawn_rate:.4f}
food_max_particles = {self.food_max_particles}
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

[rendering]
glyph_size_base = {self.glyph_size_base}
kin_line_max_distance = {self.kin_line_max_distance:.1f}
kin_line_min_group = {self.kin_line_min_group}
territory_top_n = {self.territory_top_n}
territory_shimmer_lerp = {self.territory_shimmer_lerp:.4f}
territory_fade_seconds = {self.territory_fade_seconds:.2f}
death_animation_frames = {self.death_animation_frames}
birth_animation_frames = {self.birth_animation_frames}
death_particle_count = {self.death_particle_count}

# Per-mode parameter overrides — these override the base [simulation] values
# when that mode is active. Edit to tune each mode independently.
""".format(self=self)]

        for mode_name in ("predator_prey", "boids", "drift"):
            lines.append(f"[modes.{mode_name}]")
            for key, value in mode_params[mode_name].items():
                lines.append(f"{key} = {_fmt(value)}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _read_section(self, data: dict[str, Any], section: str) -> dict[str, Any]:
        raw = data.get(section, {})
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            logger.warning("Section [%s] must be a table; ignoring invalid value.", section)
            return {}
        return raw

    def _warn_unknown_keys(
        self, section_name: str, section: dict[str, Any], known_keys: set[str]
    ) -> None:
        for key in section:
            if key not in known_keys:
                logger.warning("Unknown config key [%s].%s ignored.", section_name, key)

    def _coerce_str(self, section: dict[str, Any], key: str, default: str) -> str:
        if key not in section:
            return default
        value = section[key]
        if isinstance(value, str):
            return value
        logger.warning(
            "Config key %s expects string; got %s. Keeping %r.",
            key,
            type(value).__name__,
            default,
        )
        return default

    def _coerce_int(self, section: dict[str, Any], key: str, default: int) -> int:
        if key not in section:
            return default
        value = section[key]
        try:
            if isinstance(value, bool):
                raise ValueError
            return int(value)
        except (TypeError, ValueError):
            logger.warning(
                "Config key %s expects integer; got %r. Keeping %r.", key, value, default
            )
            return default

    def _coerce_float(self, section: dict[str, Any], key: str, default: float) -> float:
        if key not in section:
            return default
        value = section[key]
        try:
            if isinstance(value, bool):
                raise ValueError
            return float(value)
        except (TypeError, ValueError):
            logger.warning(
                "Config key %s expects float; got %r. Keeping %r.", key, value, default
            )
            return default

    def _coerce_bool(self, section: dict[str, Any], key: str, default: bool) -> bool:
        if key not in section:
            return default
        value = section[key]
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value in (0, 1):
                return bool(value)
            logger.warning(
                "Config key %s expects bool-like value 0/1; got %r. Keeping %r.",
                key,
                value,
                default,
            )
            return default
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        logger.warning(
            "Config key %s expects boolean; got %r. Keeping %r.", key, value, default
        )
        return default

    def _merge_mode_params(self, modes_data: Any) -> None:
        self.mode_params = deepcopy(self.DEFAULT_MODE_PARAMS)
        if not modes_data:
            return
        if not isinstance(modes_data, dict):
            logger.warning("Section [modes] must be a table; ignoring invalid value.")
            return

        valid_keys: dict[str, tuple[str, float | int | None, float | int | None]] = {
            "initial_population": ("int", 0, None),
            "max_population": ("int", 1, None),
            "predator_fraction": ("float", 0.0, 1.0),
            "food_spawn_rate": ("float", 0.0, None),
            "mutation_rate": ("float", 0.0, 1.0),
            "energy_to_reproduce": ("float", 0.05, 1.0),
            "food_cycle_enabled": ("bool", None, None),
            "zone_strength": ("float", 0.0, 1.0),
            "target_fps": ("int", 1, None),
            "cosmic_ray_rate": ("float", 0.0, 1.0),
        }

        for mode_name, raw_mode_data in modes_data.items():
            if mode_name not in self.DEFAULT_MODE_PARAMS:
                logger.warning("Unknown [modes.%s] section ignored.", mode_name)
                continue
            if not isinstance(raw_mode_data, dict):
                logger.warning("Section [modes.%s] must be a table; ignored.", mode_name)
                continue

            for key, value in raw_mode_data.items():
                if key not in valid_keys:
                    logger.warning(
                        "Unknown config key [modes.%s].%s ignored.", mode_name, key
                    )
                    continue
                kind, min_value, max_value = valid_keys[key]
                parsed: Any
                if kind == "bool":
                    parsed = self._coerce_bool({key: value}, key, self.mode_params[mode_name].get(key, False))
                elif kind == "int":
                    parsed = self._coerce_int({key: value}, key, int(self.mode_params[mode_name].get(key, 0)))
                    if min_value is not None:
                        parsed = max(int(min_value), parsed)
                    if max_value is not None:
                        parsed = min(int(max_value), parsed)
                else:
                    parsed = self._coerce_float(
                        {key: value},
                        key,
                        float(self.mode_params[mode_name].get(key, 0.0)),
                    )
                    if min_value is not None:
                        parsed = max(float(min_value), parsed)
                    if max_value is not None:
                        parsed = min(float(max_value), parsed)

                self.mode_params[mode_name][key] = parsed

    def _validate_mode_params(self) -> None:
        # Ensure mode params always exist and remain type-safe for runtime lookups.
        mode_params = deepcopy(self.DEFAULT_MODE_PARAMS)
        for mode_name, values in self.mode_params.items():
            if mode_name not in mode_params:
                continue
            for key, val in values.items():
                mode_params[mode_name][key] = val
        self.mode_params = mode_params


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
