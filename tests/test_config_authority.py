from __future__ import annotations

import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from primordial.config import Config, get_canonical_defaults_path


class ConfigAuthorityTests(unittest.TestCase):
    def test_first_run_creates_user_config_from_canonical_defaults(self) -> None:
        canonical_data = tomllib.loads(
            get_canonical_defaults_path().read_text(encoding="utf-8")
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

            self.assertTrue(config_path.exists())
            user_data = tomllib.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(user_data, canonical_data)
        self.assertEqual(settings.DEFAULT_MODE_PARAMS, settings.mode_params)

    def test_user_overrides_layer_on_top_of_canonical_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[simulation]
food_spawn_rate = 0.5500

[display]
fullscreen = false

[rendering]
glyph_size_base = 64
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

        self.assertEqual(settings.sim_mode, "energy")
        self.assertEqual(settings.food_max_particles, 300)
        self.assertEqual(settings.food_spawn_rate, 0.55)
        self.assertFalse(settings.fullscreen)
        self.assertEqual(settings.glyph_size_base, 64)

    def test_mode_specific_user_overrides_layer_on_top_of_canonical_mode_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[modes.drift]
target_fps = 30
mutation_rate = 0.1200

[modes.predator_prey]
predator_energy_to_reproduce = 0.7100
predator_kill_energy_gain_cap = 0.6500
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

        self.assertEqual(settings.mode_params["drift"]["target_fps"], 30)
        self.assertEqual(settings.mode_params["drift"]["mutation_rate"], 0.12)
        self.assertEqual(settings.mode_params["drift"]["zone_strength"], 0.6)
        self.assertEqual(settings.mode_params["predator_prey"]["food_spawn_rate"], 0.5)
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_energy_to_reproduce"],
            0.71,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_kill_energy_gain_cap"],
            0.65,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["prey_energy_to_reproduce"],
            0.8,
        )


if __name__ == "__main__":
    unittest.main()
