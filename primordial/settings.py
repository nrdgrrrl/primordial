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
    max_population: int = 300

    # Food settings
    food_spawn_rate: float = 0.4  # food particles per frame

    # Evolution settings
    mutation_rate: float = 0.05
    energy_to_reproduce: float = 0.8

    # Creature settings
    creature_speed_base: float = 1.5

    # Display settings
    fullscreen: bool = True
    target_fps: int = 60
    show_hud: bool = True

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
        # Filter to only valid field names
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
