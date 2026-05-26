from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from primordial.config import Config, get_canonical_defaults_path
from primordial.simulation import Simulation

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _PROJECT_ROOT / "tools" / "write_default_config.py"


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
inspect_visual_quality = "performance"
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
        self.assertEqual(settings.inspect_visual_quality, "performance")

    def test_invalid_inspect_visual_quality_falls_back_to_balanced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[rendering]
inspect_visual_quality = "ultra"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

        self.assertEqual(settings.inspect_visual_quality, "balanced")

    def test_mode_specific_user_overrides_layer_on_top_of_canonical_mode_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[modes.drift]
target_fps = 30
mutation_rate = 0.1200

[modes.predator_prey]
target_fps = 30
simulation_tick_hz = 30
adaptive_tuning_enabled = true
predator_energy_to_reproduce = 0.7100
prey_flee_age_slowdown_enabled = false
prey_flee_low_energy_slowdown_enabled = false
prey_flee_low_energy_threshold = 0.4200
prey_flee_low_energy_min_mult = 0.6500
prey_flee_speed_multiplier = 1.5500
predator_kill_energy_gain_cap = 0.6500
predator_hunt_sense_multiplier = 2.3000
predator_hunt_speed_multiplier = 1.1500
predator_contact_kill_distance_scale = 1.2000
predator_near_contact_diagnostic_scale = 1.4000
predator_sustained_chase_min_frames = 28
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
        self.assertEqual(settings.mode_params["predator_prey"]["target_fps"], 30)
        self.assertEqual(
            settings.mode_params["predator_prey"]["simulation_tick_hz"],
            30,
        )
        self.assertEqual(settings.mode_params["predator_prey"]["food_spawn_rate"], 0.65)
        self.assertTrue(
            settings.mode_params["predator_prey"]["adaptive_tuning_enabled"]
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_energy_to_reproduce"],
            0.71,
        )
        self.assertFalse(
            settings.mode_params["predator_prey"]["prey_flee_age_slowdown_enabled"]
        )
        self.assertFalse(
            settings.mode_params["predator_prey"][
                "prey_flee_low_energy_slowdown_enabled"
            ]
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["prey_flee_low_energy_threshold"],
            0.42,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["prey_flee_low_energy_min_mult"],
            0.65,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["prey_flee_speed_multiplier"],
            1.55,
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
            settings.mode_params["predator_prey"][
                "predator_near_contact_diagnostic_scale"
            ],
            1.4,
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["predator_sustained_chase_min_frames"],
            28,
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

    def test_reset_to_defaults_restores_base_and_mode_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

            default_mode = settings.mode_params["predator_prey"]["food_spawn_rate"]
            settings.fullscreen = not settings.fullscreen
            settings.mode_params["predator_prey"]["food_spawn_rate"] = 0.13
            settings.save()

            settings.reset_to_defaults()

        self.assertEqual(
            settings.fullscreen,
            tomllib.loads(get_canonical_defaults_path().read_text(encoding="utf-8"))["display"]["fullscreen"],
        )
        self.assertEqual(
            settings.mode_params["predator_prey"]["food_spawn_rate"],
            default_mode,
        )

    def test_reset_to_defaults_keeps_mode_defaults_deep_copied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

            settings.reset_to_defaults()
            baseline = settings.DEFAULT_MODE_PARAMS["boids"]["max_population"]
            settings.mode_params["boids"]["max_population"] = baseline + 77

        self.assertEqual(settings.DEFAULT_MODE_PARAMS["boids"]["max_population"], baseline)

    def test_render_effect_zero_values_are_preserved_as_disable_switches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[rendering]
kin_line_max_distance = 0.0
territory_top_n = 0
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

        self.assertEqual(settings.kin_line_max_distance, 0.0)
        self.assertEqual(settings.territory_top_n, 0)
        self.assertTrue(settings.is_render_setting_explicit("kin_line_max_distance"))
        self.assertTrue(settings.is_render_setting_explicit("territory_top_n"))

    def test_legacy_render_defaults_are_migrated_to_disabled_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[rendering]
kin_line_max_distance = 120.0
territory_top_n = 3
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

            migrated = tomllib.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(settings.kin_line_max_distance, 0.0)
        self.assertEqual(settings.territory_top_n, 0)
        self.assertEqual(migrated["rendering"]["kin_line_max_distance"], 0.0)
        self.assertEqual(migrated["rendering"]["territory_top_n"], 0)
        self.assertTrue(settings.is_render_setting_explicit("kin_line_max_distance"))
        self.assertTrue(settings.is_render_setting_explicit("territory_top_n"))

    def test_canonical_defaults_do_not_count_as_explicit_render_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

        self.assertFalse(settings.is_render_setting_explicit("kin_line_max_distance"))


    def test_predation_kill_effect_settings_validate_and_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                """
[rendering]
predation_kill_effects_enabled = false
predation_kill_effect_intensity = 9.50
predation_kill_effect_max_active = -12
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Config()

            saved = tomllib.loads(settings.to_toml())

        self.assertFalse(settings.predation_kill_effects_enabled)
        self.assertEqual(settings.predation_kill_effect_intensity, 2.5)
        self.assertEqual(settings.predation_kill_effect_max_active, 1)
        self.assertFalse(saved["rendering"]["predation_kill_effects_enabled"])
        self.assertEqual(saved["rendering"]["predation_kill_effect_intensity"], 2.5)
        self.assertEqual(saved["rendering"]["predation_kill_effect_max_active"], 1)

    def test_adaptive_tuning_disabled_preserves_mode_params_on_sim_init(self) -> None:
        settings = Config()
        settings.sim_mode = "predator_prey"
        settings.mode_params["predator_prey"]["adaptive_tuning_enabled"] = False
        settings.mode_params["predator_prey"]["predator_kill_energy_gain_cap"] = 0.62
        settings.mode_params["predator_prey"]["predator_contact_kill_distance_scale"] = 1.18
        Simulation(400, 300, settings)
        pp = settings.mode_params["predator_prey"]
        self.assertEqual(pp["predator_kill_energy_gain_cap"], 0.62)
        self.assertEqual(pp["predator_contact_kill_distance_scale"], 1.18)

    def test_generated_toml_includes_full_predator_prey_comment_block(self) -> None:
        settings = Config()
        serialized = settings.to_toml()
        self.assertIn("# Enables predator quarry memory fallback targeting.", serialized)
        self.assertIn("# Enables predator committed depth-band tracking near contact.", serialized)
        self.assertIn("# Predator efficiency when eating food particles (higher = stronger omnivory fallback).", serialized)
        self.assertIn("# Enables low-predator-count rarity bonuses.", serialized)

    # ------------------------------------------------------------------ #
    #  canonical_toml() – pure canonical defaults without user overrides
    # ------------------------------------------------------------------ #

    def test_canonical_toml_does_not_contain_user_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                "[simulation]\nfood_spawn_rate = 0.1234\n",
                encoding="utf-8",
            )
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                Config()
            canonical = Config.canonical_toml()
        data = tomllib.loads(canonical)
        self.assertEqual(data["simulation"]["food_spawn_rate"], 0.8)

    def test_canonical_toml_includes_known_defaults_and_comments(self) -> None:
        canonical = Config.canonical_toml()
        data = tomllib.loads(canonical)
        self.assertEqual(data["simulation"]["mode"], "energy")
        self.assertEqual(data["display"]["visual_theme"], "ocean")
        self.assertEqual(data["simulation"]["initial_population"], 80)
        self.assertIn("# Primordial user configuration", canonical)
        self.assertIn("# Enables predator quarry memory fallback targeting.", canonical)

    # ------------------------------------------------------------------ #
    #  CLI script tests
    # ------------------------------------------------------------------ #

    def _run_script(self, *args: str, config_dir: str | Path) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PRIMORDIAL_CONFIG_DIR"] = str(config_dir)
        return subprocess.run(
            [sys.executable, str(_SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=str(_PROJECT_ROOT),
            env=env,
        )

    def test_print_path_resolves_to_config_toml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self._run_script("--print-path", config_dir=temp_dir)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue(result.stdout.strip().endswith("config.toml"))

    def test_dry_run_does_not_write_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self._run_script("--dry-run", config_dir=temp_dir)
            config_path = Path(temp_dir) / "config.toml"
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertFalse(config_path.exists())
            self.assertIn("mode =", result.stdout)
            self.assertIn("energy", result.stdout)

    def test_overwrite_refused_when_config_exists_and_no_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text("existing = true\n", encoding="utf-8")
            result = self._run_script(config_dir=temp_dir)
            self.assertEqual(result.returncode, 1, msg=result.stdout)
            self.assertIn("Refusing", result.stderr)
            self.assertEqual(config_path.read_text(encoding="utf-8"), "existing = true\n")

    def test_force_overwrites_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text("existing = true\n", encoding="utf-8")
            result = self._run_script("--force", config_dir=temp_dir)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(data["simulation"]["mode"], "energy")

    def test_backup_force_creates_timestamped_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text("existing = true\n", encoding="utf-8")
            result = self._run_script("--backup", "--force", config_dir=temp_dir)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            backups = sorted(Path(temp_dir).glob("config.toml.bak.*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "existing = true\n")
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(data["simulation"]["mode"], "energy")

    def test_force_without_backup_does_not_leave_backup_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text("existing = true\n", encoding="utf-8")
            result = self._run_script("--force", config_dir=temp_dir)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            backups = list(Path(temp_dir).glob("config.toml.bak*"))
            self.assertEqual(len(backups), 0)


if __name__ == "__main__":
    unittest.main()
