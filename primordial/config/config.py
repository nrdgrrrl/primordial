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

_MISSING = object()
_CANONICAL_DEFAULTS_FILENAME = "defaults.toml"

_SECTION_FIELDS: dict[str, dict[str, tuple[str, str]]] = {
    "simulation": {
        "mode": ("sim_mode", "str"),
        "initial_population": ("initial_population", "int"),
        "max_population": ("max_population", "int"),
        "food_spawn_rate": ("food_spawn_rate", "float"),
        "food_max_particles": ("food_max_particles", "int"),
        "food_cycle_enabled": ("food_cycle_enabled", "bool"),
        "food_cycle_period": ("food_cycle_period", "int"),
        "mutation_rate": ("mutation_rate", "float"),
        "cosmic_ray_rate": ("cosmic_ray_rate", "float"),
        "energy_to_reproduce": ("energy_to_reproduce", "float"),
        "creature_speed_base": ("creature_speed_base", "float"),
        "zone_count": ("zone_count", "int"),
        "zone_strength": ("zone_strength", "float"),
    },
    "display": {
        "visual_theme": ("visual_theme", "str"),
        "fullscreen": ("fullscreen", "bool"),
        "target_fps": ("target_fps", "int"),
        "show_hud": ("show_hud", "bool"),
    },
    "rendering": {
        "glyph_size_base": ("glyph_size_base", "int"),
        "kin_line_max_distance": ("kin_line_max_distance", "float"),
        "kin_line_min_group": ("kin_line_min_group", "int"),
        "territory_top_n": ("territory_top_n", "int"),
        "territory_shimmer_lerp": ("territory_shimmer_lerp", "float"),
        "territory_fade_seconds": ("territory_fade_seconds", "float"),
        "death_animation_frames": ("death_animation_frames", "int"),
        "birth_animation_frames": ("birth_animation_frames", "int"),
        "death_particle_count": ("death_particle_count", "int"),
        "zone_background_intensity": ("zone_background_intensity", "float"),
        "predator_highlight_alpha": ("predator_highlight_alpha", "int"),
        "predator_highlight_radius_scale": ("predator_highlight_radius_scale", "float"),
        "predator_highlight_pulse_seconds": ("predator_highlight_pulse_seconds", "float"),
    },
}

_EVOLUTION_COMPAT_FIELDS: dict[str, tuple[str, str]] = {
    "mutation_rate": ("mutation_rate", "float"),
    "cosmic_ray_rate": ("cosmic_ray_rate", "float"),
    "food_cycle_enabled": ("food_cycle_enabled", "bool"),
    "food_cycle_period": ("food_cycle_period", "int"),
    "zone_count": ("zone_count", "int"),
    "zone_strength": ("zone_strength", "float"),
}

_CANONICAL_MODE_KEYS: dict[str, tuple[str, ...]] = {
    "predator_prey": (
        "initial_population",
        "predator_fraction",
        "food_spawn_rate",
        "mutation_rate",
        "energy_to_reproduce",
        "prey_energy_to_reproduce",
        "predator_energy_to_reproduce",
        "predator_kill_energy_gain_cap",
        "predator_hunt_sense_multiplier",
        "predator_hunt_speed_multiplier",
        "predator_contact_kill_distance_scale",
        "prey_flee_sense_multiplier",
        "predator_prey_scarcity_penalty_multiplier",
        "food_cycle_amplitude",
        "stability_history_size",
        "adaptive_step_escalation_runs",
        "adaptive_step_escalation_percent",
        "adaptive_trial_seed_count",
        "adaptive_max_consecutive_retry_trials",
        "adaptive_survival_deadband",
        "adaptive_near_extinction_predator_floor",
        "adaptive_near_extinction_prey_floor",
    ),
    "boids": (
        "initial_population",
        "max_population",
        "mutation_rate",
        "energy_to_reproduce",
        "food_cycle_enabled",
        "zone_strength",
    ),
    "drift": (
        "initial_population",
        "max_population",
        "mutation_rate",
        "cosmic_ray_rate",
        "energy_to_reproduce",
        "food_cycle_enabled",
        "zone_strength",
        "target_fps",
    ),
}

_MODE_PARAM_RULES: dict[str, tuple[str, float | int | None, float | int | None]] = {
    "initial_population": ("int", 0, None),
    "max_population": ("int", 1, None),
    "predator_fraction": ("float", 0.0, 1.0),
    "food_spawn_rate": ("float", 0.0, None),
    "mutation_rate": ("float", 0.0, 1.0),
    "energy_to_reproduce": ("float", 0.05, 1.0),
    "prey_energy_to_reproduce": ("float", 0.05, 1.0),
    "predator_energy_to_reproduce": ("float", 0.05, 1.0),
    "predator_kill_energy_gain_cap": ("float", 0.0, 1.0),
    "predator_hunt_sense_multiplier": ("float", 0.1, 5.0),
    "predator_hunt_speed_multiplier": ("float", 0.1, 5.0),
    "predator_contact_kill_distance_scale": ("float", 0.1, 5.0),
    "prey_flee_sense_multiplier": ("float", 0.1, 5.0),
    "predator_prey_scarcity_penalty_multiplier": ("float", 0.1, 5.0),
    "food_cycle_amplitude": ("float", 0.0, 1.0),
    "stability_history_size": ("int", 1, None),
    "adaptive_step_escalation_runs": ("int", 1, None),
    "adaptive_step_escalation_percent": ("float", 0.0, None),
    "adaptive_trial_seed_count": ("int", 1, None),
    "adaptive_max_consecutive_retry_trials": ("int", 0, None),
    "adaptive_survival_deadband": ("int", 0, None),
    "adaptive_near_extinction_predator_floor": ("int", 0, None),
    "adaptive_near_extinction_prey_floor": ("int", 0, None),
    "food_cycle_enabled": ("bool", None, None),
    "zone_strength": ("float", 0.0, 1.0),
    "target_fps": ("int", 1, None),
    "cosmic_ray_rate": ("float", 0.0, 1.0),
}

_BASE_ATTRS = tuple(
    attr_name
    for section_fields in _SECTION_FIELDS.values()
    for attr_name, _kind in section_fields.values()
)


class Config:
    """Typed runtime configuration with load/save/reset support."""

    VALID_SIM_MODES = ["energy", "predator_prey", "boids", "drift"]
    VALID_VISUAL_THEMES = ["ocean", "petri", "geometric", "chaotic"]

    def __init__(self) -> None:
        self.config_path = get_config_path()
        self._initialize_state()
        self._load_canonical_defaults()
        self._load_or_create()

    @property
    def DEFAULT_MODE_PARAMS(self) -> dict[str, dict[str, Any]]:
        """Backward-compatible alias for canonical mode defaults."""
        return deepcopy(self.default_mode_params)

    def _initialize_state(self) -> None:
        for attr_name in _BASE_ATTRS:
            setattr(self, attr_name, _MISSING)
        self.mode_params = {mode_name: {} for mode_name in _CANONICAL_MODE_KEYS}
        self.default_mode_params = deepcopy(self.mode_params)

    def _load_canonical_defaults(self) -> None:
        defaults_path = get_canonical_defaults_path()
        try:
            with defaults_path.open("rb") as f:
                data = tomllib.load(f)
        except Exception as exc:  # pragma: no cover - canonical file must exist in package
            raise RuntimeError(
                f"Canonical config defaults are unreadable: {defaults_path}"
            ) from exc

        self._initialize_state()
        self._merge_from_dict(data)
        self._ensure_canonical_defaults_complete(defaults_path)
        self.default_mode_params = deepcopy(self.mode_params)
        self._validate()

    def _ensure_canonical_defaults_complete(self, defaults_path: Path) -> None:
        missing_attrs = [
            attr_name for attr_name in _BASE_ATTRS if getattr(self, attr_name) is _MISSING
        ]
        if missing_attrs:
            missing_list = ", ".join(sorted(missing_attrs))
            raise RuntimeError(
                f"Canonical config defaults are missing required keys in {defaults_path}: "
                f"{missing_list}"
            )

        missing_mode_keys: list[str] = []
        for mode_name, required_keys in _CANONICAL_MODE_KEYS.items():
            mode_values = self.mode_params.get(mode_name, {})
            for key in required_keys:
                if key not in mode_values:
                    missing_mode_keys.append(f"[modes.{mode_name}].{key}")
        if missing_mode_keys:
            missing_list = ", ".join(missing_mode_keys)
            raise RuntimeError(
                f"Canonical config defaults are missing required mode keys in "
                f"{defaults_path}: {missing_list}"
            )

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
            self._load_canonical_defaults()
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

        self._warn_unknown_keys("simulation", simulation, set(_SECTION_FIELDS["simulation"]))
        if creature:
            logger.warning(
                "Deprecated [creature] config section ignored; "
                "use [simulation].energy_to_reproduce instead."
            )
        self._warn_unknown_keys("display", display, set(_SECTION_FIELDS["display"]))
        self._warn_unknown_keys("evolution", evolution, set(_EVOLUTION_COMPAT_FIELDS))
        self._warn_unknown_keys("rendering", rendering, set(_SECTION_FIELDS["rendering"]))

        self._merge_section_values(simulation, _SECTION_FIELDS["simulation"])
        self._merge_section_values(display, _SECTION_FIELDS["display"])
        self._merge_section_values(rendering, _SECTION_FIELDS["rendering"])

        # Backward-compatible values from [evolution]
        self._merge_section_values(evolution, _EVOLUTION_COMPAT_FIELDS)

        self._merge_mode_params(data.get("modes", {}))

    def _merge_section_values(
        self,
        section: dict[str, Any],
        field_map: dict[str, tuple[str, str]],
    ) -> None:
        for key, (attr_name, kind) in field_map.items():
            current = getattr(self, attr_name)
            if kind == "str":
                value = self._coerce_str(section, key, current)
            elif kind == "int":
                value = self._coerce_int(section, key, current)
            elif kind == "float":
                value = self._coerce_float(section, key, current)
            else:
                value = self._coerce_bool(section, key, current)
            setattr(self, attr_name, value)

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
        self.zone_background_intensity = max(0.1, self.zone_background_intensity)
        self.predator_highlight_alpha = max(32, min(255, self.predator_highlight_alpha))
        self.predator_highlight_radius_scale = max(
            1.0, self.predator_highlight_radius_scale
        )
        self.predator_highlight_pulse_seconds = max(
            0.1, self.predator_highlight_pulse_seconds
        )
        self._validate_mode_params()

    def reset_to_defaults(self) -> None:
        self._load_canonical_defaults()
        self.save()

    def save(self) -> None:
        self._validate()
        self.config_path.write_text(self.to_toml(), encoding="utf-8")

    def to_toml(self) -> str:
        def _fmt(val: Any) -> str:
            if isinstance(val, bool):
                return str(val).lower()
            if isinstance(val, float):
                return f"{val:.6f}" if abs(val) < 0.01 else f"{val:.4f}"
            return str(val)

        lines = [f"""# Primordial user configuration
# Overrides the canonical defaults committed at primordial/config/{_CANONICAL_DEFAULTS_FILENAME}.
# Edit by hand or press S in-app to change settings.

[simulation]
mode = "{self.sim_mode}"           # energy | predator_prey | boids | drift
initial_population = {self.initial_population}
max_population = {self.max_population}
food_spawn_rate = {self.food_spawn_rate:.4f}
food_max_particles = {self.food_max_particles}
food_cycle_enabled = {str(self.food_cycle_enabled).lower()}
food_cycle_period = {self.food_cycle_period}    # total cycle length in sim frames (1800 ~= 30s)
mutation_rate = {self.mutation_rate:.4f}
cosmic_ray_rate = {self.cosmic_ray_rate:.6f}
energy_to_reproduce = {self.energy_to_reproduce:.4f}
creature_speed_base = {self.creature_speed_base:.4f}
zone_count = {self.zone_count}
zone_strength = {self.zone_strength:.4f}

[display]
visual_theme = "{self.visual_theme}"    # ocean | petri | geometric | chaotic
fullscreen = {str(self.fullscreen).lower()}
target_fps = {self.target_fps}
show_hud = {str(self.show_hud).lower()}

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
zone_background_intensity = {self.zone_background_intensity:.2f}
predator_highlight_alpha = {self.predator_highlight_alpha}
predator_highlight_radius_scale = {self.predator_highlight_radius_scale:.2f}
predator_highlight_pulse_seconds = {self.predator_highlight_pulse_seconds:.2f}

# Per-mode parameter overrides — these override the base [simulation] values
# when that mode is active. Edit to tune each mode independently.
"""]

        mode_params = deepcopy(self.mode_params)
        for mode_name in ("predator_prey", "boids", "drift"):
            lines.append(f"[modes.{mode_name}]")
            mode_values = mode_params.get(mode_name, {})
            default_keys = tuple(self.default_mode_params.get(mode_name, {}))
            for key in default_keys:
                if key in mode_values:
                    lines.append(f"{key} = {_fmt(mode_values[key])}")
            for key, value in mode_values.items():
                if key not in default_keys:
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

    def _coerce_str(self, section: dict[str, Any], key: str, default: Any) -> str:
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

    def _coerce_int(self, section: dict[str, Any], key: str, default: Any) -> int:
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

    def _coerce_float(self, section: dict[str, Any], key: str, default: Any) -> float:
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

    def _coerce_bool(self, section: dict[str, Any], key: str, default: Any) -> bool:
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
        if not modes_data:
            return
        if not isinstance(modes_data, dict):
            logger.warning("Section [modes] must be a table; ignoring invalid value.")
            return

        for mode_name, raw_mode_data in modes_data.items():
            if mode_name not in self.mode_params:
                logger.warning("Unknown [modes.%s] section ignored.", mode_name)
                continue
            if not isinstance(raw_mode_data, dict):
                logger.warning("Section [modes.%s] must be a table; ignored.", mode_name)
                continue

            for key, value in raw_mode_data.items():
                if key not in _MODE_PARAM_RULES:
                    logger.warning(
                        "Unknown config key [modes.%s].%s ignored.", mode_name, key
                    )
                    continue
                kind, min_value, max_value = _MODE_PARAM_RULES[key]
                current = self.mode_params[mode_name].get(key, _MISSING)
                if kind == "bool":
                    parsed = self._coerce_bool({key: value}, key, current)
                elif kind == "int":
                    parsed = self._coerce_int({key: value}, key, current)
                    if min_value is not None:
                        parsed = max(int(min_value), parsed)
                    if max_value is not None:
                        parsed = min(int(max_value), parsed)
                else:
                    parsed = self._coerce_float({key: value}, key, current)
                    if min_value is not None:
                        parsed = max(float(min_value), parsed)
                    if max_value is not None:
                        parsed = min(float(max_value), parsed)

                self.mode_params[mode_name][key] = parsed

    def _validate_mode_params(self) -> None:
        mode_params = deepcopy(self.default_mode_params)
        for mode_name, values in self.mode_params.items():
            if mode_name not in mode_params:
                continue
            for key, val in values.items():
                mode_params[mode_name][key] = val
        self.mode_params = mode_params


def get_canonical_defaults_path() -> Path:
    """Return the committed canonical defaults file path."""
    return Path(__file__).with_name(_CANONICAL_DEFAULTS_FILENAME)


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
