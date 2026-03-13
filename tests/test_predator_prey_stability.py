from __future__ import annotations

from copy import deepcopy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from primordial.rendering.hud import HUD
from primordial.rendering.renderer import Renderer
from primordial.settings import Settings
from primordial.main import (
    _load_predator_prey_tuning_state,
    _predator_prey_tuning_state_path,
    _save_predator_prey_tuning_state,
    _create_fixed_step_loop_state,
    handle_keydown,
)
from primordial.simulation import Simulation, build_snapshot, load_snapshot_payload
from primordial.simulation.creature import Creature
from primordial.simulation.genome import Genome


class PredatorPreyStabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def _build_settings(self) -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = "predator_prey"
        settings.initial_population = 0
        settings.max_population = 64
        settings.food_max_particles = 32
        settings.zone_count = 0
        settings.mode_params["predator_prey"]["initial_population"] = 0
        return settings

    def _build_simulation(self) -> Simulation:
        simulation = Simulation(1000, 1000, self._build_settings())
        simulation.creatures.clear()
        simulation.food_manager.clear()
        simulation.zone_manager.zones = []
        return simulation

    def _creature(
        self,
        species: str,
        *,
        x: float,
        y: float,
        energy: float = 0.5,
        longevity: float = 0.0,
    ) -> Creature:
        creature = Creature(
            x=x,
            y=y,
            genome=Genome(longevity=longevity),
            lineage_id=1,
            species=species,
        )
        creature.energy = energy
        creature.vx = 0.0
        creature.vy = 0.0
        return creature

    def test_predator_dominance_makes_reproduction_harder(self) -> None:
        simulation = self._build_simulation()
        simulation.settings.mode_params["predator_prey"]["predator_energy_to_reproduce"] = 0.70

        predators = [
            self._creature("predator", x=50.0, y=50.0, energy=0.75),
            self._creature("predator", x=250.0, y=250.0, energy=0.75),
        ]
        prey = self._creature("prey", x=850.0, y=850.0, energy=0.20)
        simulation.creatures = predators + [prey]

        simulation.step()

        predator_count, prey_count = simulation.get_species_counts()
        self.assertEqual(predator_count, 2)
        self.assertEqual(prey_count, 1)

    def test_sim_ticks_increment_once_per_simulation_step(self) -> None:
        simulation = self._build_simulation()
        simulation.creatures = [
            self._creature("predator", x=100.0, y=100.0),
            self._creature("prey", x=800.0, y=800.0),
        ]

        simulation.step()
        simulation.step()

        stats = simulation.get_predator_prey_stability_stats()
        self.assertEqual(stats["sim_ticks"], 2)
        self.assertEqual(stats["survival_ticks"], 2)

    def test_extinction_triggers_game_over(self) -> None:
        simulation = self._build_simulation()
        simulation.creatures = [self._creature("prey", x=200.0, y=200.0)]

        simulation.step()

        stats = simulation.get_predator_prey_stability_stats()
        self.assertTrue(simulation.predator_prey_game_over_active)
        self.assertEqual(stats["collapse_cause"], "Predators collapsed")
        self.assertEqual(stats["collapse_predators"], 0)
        self.assertEqual(stats["collapse_prey"], 1)

    def test_game_over_auto_restart_after_thirty_seconds(self) -> None:
        simulation = self._build_simulation()
        simulation.settings.mode_params["predator_prey"]["initial_population"] = 6
        simulation._predator_prey_state.current_seed = 111
        simulation._enter_predator_prey_game_over(
            "Predators collapsed",
            predator_count=0,
            prey_count=4,
            now_seconds=10.0,
        )

        with patch.object(simulation, "_generate_predator_prey_seed", return_value=222):
            self.assertFalse(simulation.update_predator_prey_runtime(now_seconds=39.9))
            self.assertTrue(simulation.update_predator_prey_runtime(now_seconds=40.0))

        self.assertFalse(simulation.predator_prey_game_over_active)
        self.assertEqual(simulation.get_predator_prey_stability_stats()["current_seed"], 222)
        self.assertEqual(simulation.get_predator_prey_stability_stats()["sim_ticks"], 0)
        self.assertEqual(simulation.get_predator_prey_stability_stats()["survival_ticks"], 0)

    def test_rolling_survival_average_updates_from_completed_runs(self) -> None:
        simulation = self._build_simulation()

        simulation._finalize_predator_prey_run(100)
        simulation._finalize_predator_prey_run(200)
        simulation._finalize_predator_prey_run(300)

        self.assertEqual(simulation.predator_prey_best_recent_ticks, 300)
        self.assertEqual(simulation.predator_prey_rolling_average, 200.0)

    def test_trial_dial_change_applies_and_can_revert(self) -> None:
        simulation = self._build_simulation()
        simulation._predator_prey_state.run_history.extend([100, 100, 100])
        baseline = simulation._predator_prey_state.adaptive_tuning.current_values[
            "predator_contact_kill_distance_scale"
        ]

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)

        tuning = simulation._predator_prey_state.adaptive_tuning
        self.assertTrue(tuning.trial_active)
        self.assertEqual(tuning.trial_dial, "predator_contact_kill_distance_scale")
        self.assertLess(
            tuning.current_values["predator_contact_kill_distance_scale"],
            baseline,
        )

        simulation._finalize_predator_prey_run(80)

        tuning = simulation._predator_prey_state.adaptive_tuning
        self.assertFalse(tuning.trial_active)
        self.assertEqual(tuning.last_decision, "reverted")
        self.assertEqual(
            tuning.current_values["predator_contact_kill_distance_scale"],
            baseline,
        )

    def test_accepted_trial_dial_change_persists(self) -> None:
        simulation = self._build_simulation()
        simulation._predator_prey_state.run_history.extend([100, 100, 100])
        baseline = simulation._predator_prey_state.adaptive_tuning.current_values[
            "predator_contact_kill_distance_scale"
        ]

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)

        trial_value = simulation._predator_prey_state.adaptive_tuning.current_values[
            "predator_contact_kill_distance_scale"
        ]
        simulation._finalize_predator_prey_run(120)

        tuning = simulation._predator_prey_state.adaptive_tuning
        self.assertFalse(tuning.trial_active)
        self.assertEqual(tuning.last_decision, "kept")
        self.assertEqual(
            tuning.current_values["predator_contact_kill_distance_scale"],
            trial_value,
        )
        self.assertNotEqual(trial_value, baseline)

    def test_snapshot_round_trip_preserves_adaptive_tuning_state(self) -> None:
        simulation = self._build_simulation()
        simulation._predator_prey_state.current_seed = 424242
        simulation._predator_prey_state.sim_ticks = 123
        simulation._predator_prey_state.survival_ticks = 123
        simulation._predator_prey_state.run_history.extend([40, 60, 80])
        tuning = simulation._predator_prey_state.adaptive_tuning
        tuning.current_values["predator_hunt_sense_multiplier"] = 2.10
        tuning.previous_values["predator_hunt_sense_multiplier"] = 2.05
        tuning.trial_active = True
        tuning.trial_dial = "predator_hunt_sense_multiplier"
        tuning.trial_direction = 1
        tuning.trial_baseline_average = 75.0
        tuning.last_decision = "trial_started"
        simulation._apply_predator_prey_tuning_values(tuning.current_values)

        payload = build_snapshot(simulation)
        loaded = load_snapshot_payload(payload, settings=self._build_settings())

        self.assertEqual(
            simulation.export_predator_prey_runtime_state(),
            loaded.export_predator_prey_runtime_state(),
        )

    def test_hud_shows_seed_and_sim_ticks(self) -> None:
        simulation = self._build_simulation()
        simulation._predator_prey_state.current_seed = 98765
        simulation._predator_prey_state.sim_ticks = 42
        simulation._predator_prey_state.survival_ticks = 42
        hud = HUD()

        lines = hud._lines_predator_prey(simulation)

        joined = "\n".join(lines)
        self.assertIn("sim_ticks: 42", joined)
        self.assertIn("Seed: 98765", joined)

    def test_space_restarts_predator_prey_game_over_immediately(self) -> None:
        simulation = self._build_simulation()
        simulation._enter_predator_prey_game_over(
            "Predators collapsed",
            predator_count=0,
            prey_count=1,
            now_seconds=10.0,
        )
        renderer = Renderer(pygame.display.set_mode((640, 360)), simulation.settings)
        runtime_loop = _create_fixed_step_loop_state()

        with patch.object(simulation, "_generate_predator_prey_seed", return_value=777):
            keep_running = handle_keydown(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE),
                simulation,
                renderer,
                simulation.settings,
                renderer.screen,
                "normal",
                runtime_loop,
            )

        self.assertTrue(keep_running)
        self.assertFalse(simulation.predator_prey_game_over_active)
        self.assertEqual(simulation.get_predator_prey_stability_stats()["current_seed"], 777)

    def test_predator_prey_tuning_state_persists_across_launches(self) -> None:
        simulation = self._build_simulation()
        simulation._predator_prey_state.run_history.extend([25, 50, 75])
        tuning = simulation._predator_prey_state.adaptive_tuning
        tuning.current_values["predator_hunt_sense_multiplier"] = 2.15
        tuning.previous_values["predator_hunt_sense_multiplier"] = 2.10
        tuning.trial_active = True
        tuning.trial_dial = "predator_hunt_sense_multiplier"
        tuning.trial_direction = 1
        tuning.trial_baseline_average = 60.0
        tuning.last_decision = "trial_started"
        simulation._apply_predator_prey_tuning_values(tuning.current_values)

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch(
                "primordial.config.config.get_config_path",
                return_value=config_path,
            ):
                settings = Settings()
                settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
                settings.sim_mode = "predator_prey"
                settings.mode_params["predator_prey"]["initial_population"] = 0
                simulation.settings = settings
                saved_path = _save_predator_prey_tuning_state(settings, simulation)
                loaded_payload = _load_predator_prey_tuning_state(settings)

        self.assertIsNotNone(saved_path)
        self.assertEqual(saved_path, _predator_prey_tuning_state_path(settings))
        self.assertIsNotNone(loaded_payload)

        restored = Simulation(640, 360, settings)
        restored.restore_predator_prey_tuning_state(loaded_payload or {})

        self.assertEqual(
            simulation.export_predator_prey_tuning_state(),
            restored.export_predator_prey_tuning_state(),
        )


if __name__ == "__main__":
    unittest.main()
