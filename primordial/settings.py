"""Settings module - main configuration for the Primordial simulation."""

from dataclasses import dataclass, fields
from typing import ClassVar


@dataclass
class Settings:
    """
    Main configuration for the Primordial simulation.

    Controls simulation behavior, visual appearance, and performance parameters.
    All values can be overridden at runtime or by loading from a dict.
    """

    # Valid options for modes and themes
    VALID_SIM_MODES: ClassVar[list[str]] = ["energy", "predator_prey", "boids", "drift"]
    VALID_VISUAL_THEMES: ClassVar[list[str]] = ["ocean", "petri", "geometric", "chaotic"]

    # Simulation mode
    sim_mode: str = "energy"
    visual_theme: str = "ocean"

    # Population settings
    initial_population: int = 80
    max_population: int = 250

    # Food settings
    food_spawn_rate: float = 0.3  # food particles per frame (slightly reduced — scarcity matters)

    # Food cycle settings (boom/bust sinusoidal oscillation)
    food_cycle_period: int = 1800   # frames per cycle (~30s at 60fps)
    food_cycle_enabled: bool = True

    # Evolution settings
    mutation_rate: float = 0.06       # slightly increased for faster trait drift
    energy_to_reproduce: float = 0.75  # slightly easier to reproduce

    # Cosmic ray (spontaneous single-trait mutation) settings
    cosmic_ray_rate: float = 0.0003  # probability per creature per frame

    # Zone settings
    zone_count: int = 5
    zone_strength: float = 0.8  # global zone effect multiplier (0 = disabled)

    # Creature settings
    creature_speed_base: float = 1.5

    # Display settings
    fullscreen: bool = True
    target_fps: int = 60
    show_hud: bool = True

    # --- Glyph rendering ---
    # Base canvas size for glyph surface (px); actual size scales with creature radius
    glyph_size_base: int = 48

    # --- Kin connection lines ---
    # Max pixel distance between kin to draw connection line
    kin_line_max_distance: float = 120.0
    # Minimum lineage member count before kin lines are drawn
    kin_line_min_group: int = 3

    # --- Territory shimmer ---
    # Number of dominant lineages to render shimmer for
    territory_top_n: int = 3
    # Lerp speed for centroid drift (0=snap, 1=instant)
    territory_shimmer_lerp: float = 0.05
    # Shimmer fade-out duration in seconds when lineage drops out of top N
    territory_fade_seconds: float = 2.0

    # --- Animations ---
    # Frames for death dissolution animation
    death_animation_frames: int = 40
    # Frames for birth scale-up animation
    birth_animation_frames: int = 30
    # Number of scatter particles on death
    death_particle_count: int = 5

    def __post_init__(self) -> None:
        """Validate settings after initialization."""
        if self.sim_mode not in self.VALID_SIM_MODES:
            raise ValueError(f"sim_mode must be one of {self.VALID_SIM_MODES}")
        if self.visual_theme not in self.VALID_VISUAL_THEMES:
            raise ValueError(f"visual_theme must be one of {self.VALID_VISUAL_THEMES}")

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        """
        Create a Settings instance from a dictionary.

        Args:
            data: Dictionary containing settings values.

        Returns:
            A new Settings instance with values from the dict.
        """
        valid_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)

    def to_dict(self) -> dict:
        """
        Convert settings to a dictionary.

        Returns:
            Dictionary representation of all settings.
        """
        return {f.name: getattr(self, f.name) for f in fields(self)}
