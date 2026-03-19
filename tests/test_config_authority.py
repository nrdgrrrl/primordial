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
adaptive_tuning_enabled = true
predator_energy_to_reproduce = 0.7100
predator_kill_energy_gain_cap = 0.6500
predator_hunt_sense_multiplier = 2.3000
predator_hunt_speed_multiplier = 1.1500
predator_contact_kill_distance_scale = 1.2000
predator_food_efficiency_multiplier = 0.2500
predator_forage_cost_multiplier = 0.6000
predator_recent_animal_energy_required = 0.3000
predator_recent_animal_energy_decay_per_tick = 0.001000
predator_satiety_ticks = 90
predator_interference_strength = 0.2000
predator_target_prey_per_predator = 3.5000
predator_low_prey_hunt_floor = 0.4000
prey_to_predator_aggression_threshold = 0.5800
predator_to_prey_aggression_threshold = 0.4200
extinction_grace_ticks = 1800
stability_history_size = 40
adaptive_step_escalation_runs = 7
adaptive_step_escalation_percent = 40.0
adaptive_trial_seed_count = 5
adaptive_max_consecutive_retry_trials = 3
adaptive_survival_deadband = 25
adaptive_near_extinction_predator_floor = 3
adaptive_near_extinction_prey_floor = 7
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

        self.assertEqual(settings.mode_params["drift"]["target_fps"], 30)
        self.assertEqual(settings.mode_params["drift"]["mutation_rate"], 0.12)
        self.assertEqual(settings.mode_params["drift"]["zone_strength"], 0.6)
        self.assertEqual(settings.mode_params["predator_prey"]["food_spawn_rate"], 0.65)
        self.assertTrue(
            settings.mode_params["predator_prey"]["adaptive_tuning_enabled"]
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_energy_to_reproduce"],
            0.71,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_kill_energy_gain_cap"],
            0.65,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_hunt_sense_multiplier"],
            2.3,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_hunt_speed_multiplier"],
            1.15,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_contact_kill_distance_scale"],
            1.2,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_food_efficiency_multiplier"],
            0.25,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_forage_cost_multiplier"],
            0.6,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_target_prey_per_predator"],
            3.5,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_low_prey_hunt_floor"],
            0.4,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["stability_history_size"],
            40,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["adaptive_step_escalation_runs"],
            7,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["adaptive_step_escalation_percent"],
            40.0,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["adaptive_trial_seed_count"],
            5,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"][
                "adaptive_max_consecutive_retry_trials"
            ],
            3,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["adaptive_survival_deadband"],
            25,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"][
                "adaptive_near_extinction_predator_floor"
            ],
            3,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["adaptive_near_extinction_prey_floor"],
            7,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["prey_energy_to_reproduce"],
            0.76,
        )

    def test_legacy_predator_prey_mode_block_is_reset_to_canonical_defaults(self) -> None:
        canonical_data = tomllib.loads(
            get_canonical_defaults_path().read_text(encoding="utf-8")
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[modes.predator_prey]
predator_fraction = 0.2500
food_spawn_rate = 0.5000
predator_hunt_speed_multiplier = 1.0000
predator_contact_kill_distance_scale = 1.0300
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

            user_data = tomllib.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(
            settings.mode_params["predator_prey"],
            canonical_data["modes"]["predator_prey"],
        )
        self.assertEqual(
            user_data["modes"]["predator_prey"],
            canonical_data["modes"]["predator_prey"],
        )

    def test_legacy_solitude_bonus_key_is_ignored_and_removed_on_save(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[modes.predator_prey]
adaptive_tuning_enabled = false
predator_food_efficiency_multiplier = 0.8500
predator_forage_cost_multiplier = 0.7200
predator_recent_animal_energy_required = 0.0400
predator_recent_animal_energy_decay_per_tick = 0.000100
predator_satiety_ticks = 360
predator_interference_strength = 0.3000
predator_target_prey_per_predator = 4.0000
predator_low_prey_hunt_floor = 0.3500
prey_to_predator_aggression_threshold = 0.3000
predator_to_prey_aggression_threshold = 0.2000
extinction_grace_ticks = 7200
predator_solitude_hunt_bonus = 0.4500
predator_energy_to_reproduce = 0.7100
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

            user_data = tomllib.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_energy_to_reproduce"],
            0.71,
        )
        self.assertNotIn(
            "predator_solitude_hunt_bonus",
            settings.mode_params["predator_prey"],
        )
        self.assertNotIn(
            "predator_solitude_hunt_bonus",
            user_data["modes"]["predator_prey"],
        )


if __name__ == "__main__":
    unittest.main()
