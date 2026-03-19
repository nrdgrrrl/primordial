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

    def _build_settings(
        self,
        *,
        history_size: int = 20,
        escalation_runs: int = 5,
        escalation_percent: float = 25.0,
        trial_count: int = 2,
        max_consecutive_retry_trials: int = 2,
        survival_deadband: int = 50,
        predator_floor: int = 5,
        prey_floor: int = 5,
        adaptive_tuning_enabled: bool = True,
        extinction_grace_ticks: int = 1800,
    ) -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = "predator_prey"
        settings.initial_population = 0
        settings.max_population = 64
        settings.food_max_particles = 32
        settings.zone_count = 0
        predator_prey = settings.mode_params["predator_prey"]
        predator_prey["initial_population"] = 0
        predator_prey["stability_history_size"] = history_size
        predator_prey["adaptive_step_escalation_runs"] = escalation_runs
        predator_prey["adaptive_step_escalation_percent"] = escalation_percent
        predator_prey["adaptive_trial_seed_count"] = trial_count
        predator_prey["adaptive_max_consecutive_retry_trials"] = (
            max_consecutive_retry_trials
        )
        predator_prey["adaptive_survival_deadband"] = survival_deadband
        predator_prey["adaptive_near_extinction_predator_floor"] = predator_floor
        predator_prey["adaptive_near_extinction_prey_floor"] = prey_floor
        predator_prey["adaptive_tuning_enabled"] = adaptive_tuning_enabled
        predator_prey["extinction_grace_ticks"] = extinction_grace_ticks
        return settings

    def _build_simulation(self, **settings_kwargs: float | int | bool) -> Simulation:
        simulation = Simulation(1000, 1000, self._build_settings(**settings_kwargs))
        simulation.creatures.clear()
        simulation.food_manager.clear()
        simulation.zone_manager.zones = []
        return simulation

    def _finalize_run_with_metrics(
        self,
        simulation: Simulation,
        *,
        survival_ticks: int,
        predator_low_ticks: int = 0,
        prey_low_ticks: int = 0,
    ) -> None:
        state = simulation._predator_prey_state
        state.survival_ticks = survival_ticks
        state.predator_low_ticks = predator_low_ticks
        state.prey_low_ticks = prey_low_ticks
        simulation._finalize_predator_prey_run(survival_ticks)

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

    def test_extinction_enters_grace_window_before_game_over(self) -> None:
        simulation = self._build_simulation(extinction_grace_ticks=3)
        simulation.creatures = [self._creature("prey", x=200.0, y=200.0)]

        simulation.step()

        stats = simulation.get_predator_prey_stability_stats()
        self.assertFalse(simulation.predator_prey_game_over_active)
        self.assertTrue(stats["extinction_grace_active"])
        self.assertEqual(stats["extinction_grace_role"], "predators")
        self.assertEqual(stats["predator_zero_ticks"], 1)
        self.assertEqual(stats["predator_grace_remaining_ticks"], 2)

    def test_sustained_extinction_after_grace_window_triggers_game_over(self) -> None:
        simulation = self._build_simulation(extinction_grace_ticks=3)
        simulation.creatures = [self._creature("prey", x=200.0, y=200.0)]

        simulation.step()
        simulation.step()
        simulation.step()

        stats = simulation.get_predator_prey_stability_stats()
        self.assertTrue(simulation.predator_prey_game_over_active)
        self.assertEqual(stats["collapse_cause"], "Predators collapsed")
        self.assertEqual(stats["collapse_predators"], 0)
        self.assertEqual(stats["collapse_prey"], 1)

    def test_recovery_inside_grace_window_clears_zero_tick_counter(self) -> None:
        simulation = self._build_simulation(extinction_grace_ticks=5)
        simulation.creatures = [self._creature("prey", x=200.0, y=200.0)]

        simulation.step()
        predator = self._creature("predator", x=220.0, y=220.0, energy=0.4)
        simulation.creatures.append(predator)

        simulation.step()

        stats = simulation.get_predator_prey_stability_stats()
        self.assertFalse(stats["extinction_grace_active"])
        self.assertEqual(stats["predator_zero_ticks"], 0)

    def test_predator_prey_adaptive_tuning_is_disabled_by_default(self) -> None:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = "predator_prey"
        simulation = Simulation(400, 300, settings)

        self.assertFalse(
            settings.mode_params["predator_prey"]["adaptive_tuning_enabled"]
        )
        self.assertFalse(simulation._predator_prey_adaptive_tuning_enabled)

    def test_predator_can_eat_food_without_unlocking_reproduction(self) -> None:
        simulation = self._build_simulation(extinction_grace_ticks=10)
        simulation.settings.mode_params["predator_prey"]["predator_food_efficiency_multiplier"] = 1.0
        simulation.settings.mode_params["predator_prey"]["predator_energy_to_reproduce"] = 0.55
        simulation.settings.mode_params["predator_prey"][
            "predator_recent_animal_energy_required"
        ] = 0.35
        simulation.settings.mode_params["predator_prey"]["food_spawn_rate"] = 0.0
        predator = self._creature("predator", x=200.0, y=200.0, energy=0.54)
        predator.depth_band = 1
        simulation.creatures = [predator]
        food = simulation.food_manager.spawn(x=200.0, y=200.0, depth_band=1)

        simulation.step()

        predator_count, prey_count = simulation.get_species_counts()
        self.assertEqual(predator_count, 1)
        self.assertEqual(prey_count, 0)
        self.assertGreater(predator.energy, 0.55)
        self.assertEqual(predator.recent_animal_energy, 0.0)
        self.assertLess(
            predator.recent_animal_energy,
            simulation.settings.mode_params["predator_prey"][
                "predator_recent_animal_energy_required"
            ],
        )
        self.assertNotIn(food, simulation.food_manager.particles)

    def test_lone_predator_gets_no_hunt_bonus_from_interference_logic(self) -> None:
        simulation = self._build_simulation()
        predator = self._creature("predator", x=200.0, y=200.0)
        bucket = simulation._build_creature_bucket()

        self.assertEqual(
            simulation._predator_interference_factor(predator, bucket),
            1.0,
        )

    def test_game_over_auto_restart_after_ten_seconds(self) -> None:
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
            self.assertFalse(simulation.update_predator_prey_runtime(now_seconds=19.9))
            self.assertTrue(simulation.update_predator_prey_runtime(now_seconds=20.0))

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

    def test_configured_history_window_limits_rolling_average(self) -> None:
        simulation = self._build_simulation(history_size=3)

        simulation._finalize_predator_prey_run(100)
        simulation._finalize_predator_prey_run(200)
        simulation._finalize_predator_prey_run(300)
        simulation._finalize_predator_prey_run(400)

        stats = simulation.get_predator_prey_stability_stats()
        self.assertEqual(stats["history_window_size"], 3)
        self.assertEqual(simulation.predator_prey_best_recent_ticks, 400)
        self.assertEqual(simulation.predator_prey_rolling_average, 300.0)

    def test_rolling_survival_baseline_uses_median(self) -> None:
        simulation = self._build_simulation()

        simulation._finalize_predator_prey_run(100)
        simulation._finalize_predator_prey_run(100)
        simulation._finalize_predator_prey_run(100)
        simulation._finalize_predator_prey_run(1000)

        self.assertEqual(simulation.predator_prey_rolling_average, 100.0)

    def test_trial_dial_change_applies_and_can_revert(self) -> None:
        simulation = self._build_simulation(
            trial_count=1,
            max_consecutive_retry_trials=0,
        )
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
        self.assertTrue(tuning.trial_active)
        self.assertEqual(tuning.trial_phase, "baseline")
        self.assertEqual(
            tuning.current_values["predator_contact_kill_distance_scale"],
            baseline,
        )

        simulation._finalize_predator_prey_run(90)
        tuning = simulation._predator_prey_state.adaptive_tuning
        self.assertFalse(tuning.trial_active)
        self.assertEqual(tuning.last_decision, "reverted")
        self.assertEqual(
            tuning.current_values["predator_contact_kill_distance_scale"],
            baseline,
        )

    def test_accepted_trial_dial_change_persists(self) -> None:
        simulation = self._build_simulation(trial_count=1)
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
        self.assertTrue(simulation._predator_prey_state.adaptive_tuning.trial_active)
        simulation._finalize_predator_prey_run(90)

        tuning = simulation._predator_prey_state.adaptive_tuning
        self.assertFalse(tuning.trial_active)
        self.assertEqual(tuning.last_decision, "kept")
        self.assertEqual(
            tuning.current_values["predator_contact_kill_distance_scale"],
            trial_value,
        )
        self.assertNotEqual(trial_value, baseline)

    def test_failed_trial_can_launch_immediate_retry_without_ordinary_run(self) -> None:
        simulation = self._build_simulation(
            trial_count=2,
            max_consecutive_retry_trials=2,
            survival_deadband=10,
        )
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with (
            patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None),
            patch.object(
                simulation,
                "_generate_predator_prey_seed",
                side_effect=[111, 222, 333, 444],
            ),
        ):
            simulation._finalize_predator_prey_run(50)
            self._finalize_run_with_metrics(simulation, survival_ticks=90, predator_low_ticks=1)
            self._finalize_run_with_metrics(simulation, survival_ticks=160, predator_low_ticks=1)
            self._finalize_run_with_metrics(simulation, survival_ticks=100, predator_low_ticks=2)
            self._finalize_run_with_metrics(simulation, survival_ticks=150, predator_low_ticks=2)

        tuning = simulation._predator_prey_state.adaptive_tuning
        stats = simulation.get_predator_prey_stability_stats()
        self.assertTrue(tuning.trial_active)
        self.assertEqual(tuning.last_decision, "reverted")
        self.assertEqual(tuning.post_run_trial_decision, "reverted")
        self.assertEqual(tuning.trial_id, 2)
        self.assertEqual(stats["trial_trigger_reason"], "immediate_retry_after_revert")
        self.assertEqual(tuning.trial_seeds, [333, 444])
        self.assertEqual(tuning.trial_candidate_results, [])
        self.assertEqual(tuning.trial_baseline_results, [])
        self.assertEqual(tuning.trial_candidate_pressures, [])
        self.assertEqual(tuning.trial_baseline_pressures, [])
        self.assertEqual(tuning.consecutive_immediate_retry_trials, 1)
        self.assertFalse(tuning.last_trial_launch_blocked_by_retry_cap)
        self.assertEqual(len(simulation._predator_prey_state.run_history), 8)

    def test_retry_cap_requires_ordinary_run_before_next_trial(self) -> None:
        simulation = self._build_simulation(
            trial_count=1,
            max_consecutive_retry_trials=2,
        )
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)
            simulation._finalize_predator_prey_run(80)
            simulation._finalize_predator_prey_run(90)
            simulation._finalize_predator_prey_run(70)
            simulation._finalize_predator_prey_run(100)
            simulation._finalize_predator_prey_run(60)
            simulation._finalize_predator_prey_run(110)

        tuning = simulation._predator_prey_state.adaptive_tuning
        self.assertFalse(tuning.trial_active)
        self.assertEqual(tuning.last_decision, "reverted")
        self.assertEqual(tuning.post_run_trial_decision, "reverted")
        self.assertEqual(tuning.consecutive_immediate_retry_trials, 2)
        self.assertTrue(tuning.last_trial_launch_blocked_by_retry_cap)

        simulation._finalize_predator_prey_run(40)

        tuning = simulation._predator_prey_state.adaptive_tuning
        stats = simulation.get_predator_prey_stability_stats()
        self.assertTrue(tuning.trial_active)
        self.assertEqual(
            stats["trial_trigger_reason"],
            "blocked_by_retry_cap_then_waited_for_ordinary_run",
        )
        self.assertEqual(tuning.consecutive_immediate_retry_trials, 0)
        self.assertFalse(tuning.last_trial_launch_blocked_by_retry_cap)

    def test_kept_trial_resets_immediate_retry_counter(self) -> None:
        simulation = self._build_simulation(
            trial_count=1,
            max_consecutive_retry_trials=2,
        )
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)
            simulation._finalize_predator_prey_run(80)
            simulation._finalize_predator_prey_run(90)
            simulation._finalize_predator_prey_run(130)
            simulation._finalize_predator_prey_run(90)

        tuning = simulation._predator_prey_state.adaptive_tuning
        self.assertFalse(tuning.trial_active)
        self.assertEqual(tuning.last_decision, "kept")
        self.assertEqual(tuning.post_run_trial_decision, "kept")
        self.assertEqual(tuning.consecutive_immediate_retry_trials, 0)
        self.assertFalse(tuning.retry_cap_waiting_for_ordinary_run)

    def test_below_rolling_median_trigger_reason_still_starts_trial(self) -> None:
        simulation = self._build_simulation(trial_count=1)
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)

        stats = simulation.get_predator_prey_stability_stats()
        self.assertTrue(simulation._predator_prey_state.adaptive_tuning.trial_active)
        self.assertEqual(stats["trial_trigger_reason"], "below_rolling_median")
        self.assertEqual(stats["post_run_trial_decision"], "trial_started")

    def test_adjustment_step_multiplier_scales_after_non_improving_streak(self) -> None:
        simulation = self._build_simulation(
            escalation_runs=2,
            escalation_percent=25.0,
            trial_count=1,
        )
        simulation._predator_prey_state.run_history.extend([100, 100, 100])
        baseline = simulation._predator_prey_state.adaptive_tuning.current_values[
            "predator_contact_kill_distance_scale"
        ]

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)
            simulation._finalize_predator_prey_run(80)
            simulation._finalize_predator_prey_run(70)
            simulation._finalize_predator_prey_run(60)

        tuning = simulation._predator_prey_state.adaptive_tuning
        self.assertTrue(tuning.trial_active)
        self.assertEqual(tuning.non_improving_run_streak, 4)
        self.assertAlmostEqual(
            tuning.current_values["predator_contact_kill_distance_scale"],
            max(0.80, baseline - 0.075),
            places=4,
        )
        self.assertAlmostEqual(
            simulation.predator_prey_adjustment_step_multiplier,
            1.5,
        )

    def test_k2_trial_reuses_same_two_seeds_and_decides_by_medians(self) -> None:
        simulation = self._build_simulation(
            trial_count=2,
            max_consecutive_retry_trials=0,
            survival_deadband=10,
        )
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with (
            patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None),
            patch.object(
                simulation,
                "_generate_predator_prey_seed",
                side_effect=[111, 222],
            ) as generate_seed,
        ):
            simulation._finalize_predator_prey_run(50)

        tuning = simulation._predator_prey_state.adaptive_tuning
        self.assertEqual(generate_seed.call_count, 2)
        self.assertEqual(tuning.trial_seeds, [111, 222])
        self.assertEqual(
            simulation.get_predator_prey_stability_stats()[
                "verification_seed_count_configured"
            ],
            2,
        )

        simulation.restart_predator_prey_run()
        self.assertEqual(simulation.get_predator_prey_stability_stats()["current_seed"], 111)

        simulation._finalize_predator_prey_run(120)
        simulation.restart_predator_prey_run()
        self.assertEqual(simulation.get_predator_prey_stability_stats()["current_seed"], 111)

        simulation._finalize_predator_prey_run(90)
        simulation.restart_predator_prey_run()
        self.assertEqual(simulation.get_predator_prey_stability_stats()["current_seed"], 222)

        simulation._finalize_predator_prey_run(140)
        simulation.restart_predator_prey_run()
        self.assertEqual(simulation.get_predator_prey_stability_stats()["current_seed"], 222)

        simulation._finalize_predator_prey_run(100)

        stats = simulation.get_predator_prey_stability_stats()
        self.assertFalse(tuning.trial_active)
        self.assertEqual(tuning.last_decision, "kept")
        self.assertEqual(stats["trial_last_survival_median_candidate"], 130.0)
        self.assertEqual(stats["trial_last_survival_median_baseline"], 95.0)
        self.assertEqual(stats["trial_last_decision_basis"], "survival")

    def test_survival_outside_deadband_keeps_candidate(self) -> None:
        simulation = self._build_simulation(trial_count=2, survival_deadband=10)
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)

        self._finalize_run_with_metrics(simulation, survival_ticks=200, predator_low_ticks=6)
        self._finalize_run_with_metrics(simulation, survival_ticks=100, predator_low_ticks=1)
        self._finalize_run_with_metrics(simulation, survival_ticks=160, predator_low_ticks=8)
        self._finalize_run_with_metrics(simulation, survival_ticks=90, predator_low_ticks=2)

        tuning = simulation._predator_prey_state.adaptive_tuning
        stats = simulation.get_predator_prey_stability_stats()
        self.assertFalse(tuning.trial_active)
        self.assertEqual(tuning.last_decision, "kept")
        self.assertEqual(stats["trial_last_decision_basis"], "survival")

    def test_survival_outside_deadband_reverts_candidate(self) -> None:
        simulation = self._build_simulation(
            trial_count=2,
            max_consecutive_retry_trials=0,
            survival_deadband=10,
        )
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)

        self._finalize_run_with_metrics(simulation, survival_ticks=90, predator_low_ticks=1)
        self._finalize_run_with_metrics(simulation, survival_ticks=160, predator_low_ticks=1)
        self._finalize_run_with_metrics(simulation, survival_ticks=100, predator_low_ticks=2)
        self._finalize_run_with_metrics(simulation, survival_ticks=150, predator_low_ticks=2)

        tuning = simulation._predator_prey_state.adaptive_tuning
        stats = simulation.get_predator_prey_stability_stats()
        self.assertFalse(tuning.trial_active)
        self.assertEqual(tuning.last_decision, "reverted")
        self.assertEqual(stats["trial_last_decision_basis"], "survival")

    def test_near_extinction_tiebreak_keeps_candidate_inside_deadband(self) -> None:
        simulation = self._build_simulation(
            trial_count=2,
            max_consecutive_retry_trials=0,
            survival_deadband=50,
        )
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)

        self._finalize_run_with_metrics(simulation, survival_ticks=130, predator_low_ticks=1)
        self._finalize_run_with_metrics(simulation, survival_ticks=120, predator_low_ticks=12)
        self._finalize_run_with_metrics(simulation, survival_ticks=110, predator_low_ticks=1)
        self._finalize_run_with_metrics(simulation, survival_ticks=100, predator_low_ticks=10)

        tuning = simulation._predator_prey_state.adaptive_tuning
        stats = simulation.get_predator_prey_stability_stats()
        self.assertEqual(tuning.last_decision, "kept")
        self.assertEqual(stats["trial_last_decision_basis"], "near_extinction_tiebreak")
        self.assertEqual(stats["trial_last_near_extinction_candidate"], 1.0)
        self.assertEqual(stats["trial_last_near_extinction_baseline"], 11.0)

    def test_near_extinction_tiebreak_reverts_candidate_inside_deadband(self) -> None:
        simulation = self._build_simulation(
            trial_count=2,
            max_consecutive_retry_trials=0,
            survival_deadband=50,
        )
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)

        self._finalize_run_with_metrics(simulation, survival_ticks=130, predator_low_ticks=12)
        self._finalize_run_with_metrics(simulation, survival_ticks=120, predator_low_ticks=1)
        self._finalize_run_with_metrics(simulation, survival_ticks=110, predator_low_ticks=10)
        self._finalize_run_with_metrics(simulation, survival_ticks=100, predator_low_ticks=1)

        tuning = simulation._predator_prey_state.adaptive_tuning
        stats = simulation.get_predator_prey_stability_stats()
        self.assertEqual(tuning.last_decision, "reverted")
        self.assertEqual(stats["trial_last_decision_basis"], "near_extinction_tiebreak")
        self.assertEqual(stats["trial_last_near_extinction_candidate"], 11.0)
        self.assertEqual(stats["trial_last_near_extinction_baseline"], 1.0)

    def test_exact_tie_reverts_candidate_on_equal_survival_and_pressure(self) -> None:
        simulation = self._build_simulation(
            trial_count=2,
            max_consecutive_retry_trials=0,
            survival_deadband=50,
        )
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)

        self._finalize_run_with_metrics(simulation, survival_ticks=120, predator_low_ticks=5)
        self._finalize_run_with_metrics(simulation, survival_ticks=120, predator_low_ticks=5)
        self._finalize_run_with_metrics(simulation, survival_ticks=110, predator_low_ticks=5)
        self._finalize_run_with_metrics(simulation, survival_ticks=110, predator_low_ticks=5)

        tuning = simulation._predator_prey_state.adaptive_tuning
        stats = simulation.get_predator_prey_stability_stats()
        self.assertEqual(tuning.last_decision, "reverted")
        self.assertEqual(stats["trial_last_decision_basis"], "exact_tie_revert_candidate")

    def test_equal_pressure_inside_deadband_keeps_higher_survival_candidate(self) -> None:
        simulation = self._build_simulation(trial_count=2, survival_deadband=50)
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)

        self._finalize_run_with_metrics(simulation, survival_ticks=120, predator_low_ticks=5)
        self._finalize_run_with_metrics(simulation, survival_ticks=110, predator_low_ticks=5)
        self._finalize_run_with_metrics(simulation, survival_ticks=110, predator_low_ticks=5)
        self._finalize_run_with_metrics(simulation, survival_ticks=100, predator_low_ticks=5)

        tuning = simulation._predator_prey_state.adaptive_tuning
        stats = simulation.get_predator_prey_stability_stats()
        self.assertEqual(tuning.last_decision, "kept")
        self.assertEqual(stats["trial_last_decision_basis"], "survival")

    def test_equal_pressure_inside_deadband_reverts_lower_survival_candidate(self) -> None:
        simulation = self._build_simulation(trial_count=2, survival_deadband=50)
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
            simulation._finalize_predator_prey_run(50)

        self._finalize_run_with_metrics(simulation, survival_ticks=90, predator_low_ticks=5)
        self._finalize_run_with_metrics(simulation, survival_ticks=100, predator_low_ticks=5)
        self._finalize_run_with_metrics(simulation, survival_ticks=80, predator_low_ticks=5)
        self._finalize_run_with_metrics(simulation, survival_ticks=95, predator_low_ticks=5)

        tuning = simulation._predator_prey_state.adaptive_tuning
        stats = simulation.get_predator_prey_stability_stats()
        self.assertEqual(tuning.last_decision, "reverted")
        self.assertEqual(stats["trial_last_decision_basis"], "survival")

    def test_non_improving_streak_resets_when_run_beats_average(self) -> None:
        simulation = self._build_simulation()
        simulation._predator_prey_state.run_history.extend([100, 100, 100])
        simulation._predator_prey_state.adaptive_tuning.non_improving_run_streak = 4

        simulation._finalize_predator_prey_run(120)

        self.assertEqual(
            simulation._predator_prey_state.adaptive_tuning.non_improving_run_streak,
            0,
        )

    def test_game_over_preserves_trial_dial_delta_for_overlay(self) -> None:
        simulation = self._build_simulation()
        simulation._predator_prey_state.run_history.extend([100, 100, 100])
        simulation._predator_prey_state.survival_ticks = 90
        simulation._predator_prey_state.highest_survival_ticks = 120
        tuning = simulation._predator_prey_state.adaptive_tuning
        tuning.previous_values["predator_contact_kill_distance_scale"] = 1.00
        tuning.current_values["predator_contact_kill_distance_scale"] = 0.97
        tuning.trial_active = True
        tuning.trial_dial = "predator_contact_kill_distance_scale"
        tuning.trial_direction = -1
        tuning.trial_baseline_average = 100.0
        tuning.last_decision = "trial_started"
        simulation._apply_predator_prey_tuning_values(tuning.current_values)

        simulation._enter_predator_prey_game_over(
            "Predators collapsed",
            predator_count=0,
            prey_count=3,
            now_seconds=10.0,
        )

        stats = simulation.get_predator_prey_stability_stats()
        self.assertEqual(
            stats["collapse_dial_values"]["predator_contact_kill_distance_scale"],
            0.97,
        )
        self.assertEqual(
            stats["collapse_trial_dial"],
            "predator_contact_kill_distance_scale",
        )
        self.assertAlmostEqual(stats["collapse_trial_delta"], -0.03, places=4)
        self.assertEqual(stats["collapse_trial_direction"], "-")
        self.assertEqual(stats["collapse_trial_value"], 0.97)
        self.assertEqual(stats["collapse_rolling_average"], 100.0)
        self.assertFalse(stats["collapse_beat_average"])
        self.assertFalse(stats["collapse_was_new_highest"])
        self.assertEqual(
            simulation._predator_prey_state.adaptive_tuning.current_values[
                "predator_contact_kill_distance_scale"
            ],
            1.00,
        )

    def test_game_over_marks_new_highest_survival_record(self) -> None:
        simulation = self._build_simulation()
        simulation._predator_prey_state.run_history.extend([100, 100, 100])
        simulation._predator_prey_state.survival_ticks = 150
        simulation._predator_prey_state.highest_survival_ticks = 120

        simulation._enter_predator_prey_game_over(
            "Prey collapsed",
            predator_count=2,
            prey_count=0,
            now_seconds=10.0,
        )

        stats = simulation.get_predator_prey_stability_stats()
        self.assertEqual(stats["highest_survival_ticks"], 150)
        self.assertTrue(stats["collapse_beat_average"])
        self.assertTrue(stats["collapse_was_new_highest"])

    def test_reset_predator_prey_adaptive_tuning_restores_baseline_and_clears_history(self) -> None:
        simulation = self._build_simulation()
        state = simulation._predator_prey_state
        baseline = dict(state.adaptive_tuning.baseline_values)
        state.run_history.extend([50, 75, 100])
        state.highest_survival_ticks = 100
        state.adaptive_tuning.current_values["predator_hunt_sense_multiplier"] = 2.15
        state.adaptive_tuning.previous_values["predator_hunt_sense_multiplier"] = 2.10
        state.adaptive_tuning.trial_candidate_values = dict(
            state.adaptive_tuning.current_values
        )
        state.adaptive_tuning.trial_active = True
        state.adaptive_tuning.trial_phase = "baseline"
        state.adaptive_tuning.trial_dial = "predator_hunt_sense_multiplier"
        state.adaptive_tuning.trial_direction = 1
        state.adaptive_tuning.trial_baseline_average = 80.0
        state.adaptive_tuning.trial_seeds = [111, 222, 333]
        state.adaptive_tuning.trial_seed_index = 1
        state.adaptive_tuning.trial_candidate_results = [70]
        state.adaptive_tuning.trial_baseline_results = [90]
        state.adaptive_tuning.non_improving_run_streak = 4
        simulation._apply_predator_prey_tuning_values(state.adaptive_tuning.current_values)

        simulation.reset_predator_prey_adaptive_tuning()

        self.assertEqual(state.adaptive_tuning.current_values, baseline)
        self.assertEqual(state.adaptive_tuning.previous_values, baseline)
        self.assertEqual(state.adaptive_tuning.trial_candidate_values, {})
        self.assertFalse(state.adaptive_tuning.trial_active)
        self.assertEqual(state.adaptive_tuning.last_decision, "reset_to_baseline")
        self.assertEqual(state.adaptive_tuning.non_improving_run_streak, 0)
        self.assertEqual(list(state.run_history), [])
        self.assertEqual(state.highest_survival_ticks, 0)

    def test_snapshot_round_trip_preserves_adaptive_tuning_state(self) -> None:
        simulation = self._build_simulation()
        simulation._predator_prey_state.current_seed = 424242
        simulation._predator_prey_state.sim_ticks = 123
        simulation._predator_prey_state.survival_ticks = 123
        simulation._predator_prey_state.run_history.extend([40, 60, 80])
        simulation._predator_prey_state.highest_survival_ticks = 123
        tuning = simulation._predator_prey_state.adaptive_tuning
        tuning.current_values["predator_hunt_sense_multiplier"] = 2.10
        tuning.previous_values["predator_hunt_sense_multiplier"] = 2.05
        tuning.trial_candidate_values = dict(tuning.current_values)
        tuning.trial_active = True
        tuning.trial_phase = "baseline"
        tuning.trial_dial = "predator_hunt_sense_multiplier"
        tuning.trial_direction = 1
        tuning.trial_baseline_average = 75.0
        tuning.trial_seeds = [101, 202, 303]
        tuning.trial_seed_index = 1
        tuning.trial_candidate_results = [90]
        tuning.trial_baseline_results = [75]
        tuning.last_decision = "trial_started"
        tuning.non_improving_run_streak = 3
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

    def test_hud_uses_configured_history_window_label(self) -> None:
        simulation = self._build_simulation(history_size=40)
        hud = HUD()

        lines = hud._lines_predator_prey(simulation)

        joined = "\n".join(lines)
        self.assertIn("Med40:", joined)
        self.assertIn("Best40:", joined)

    def test_hud_shows_extinction_grace_warning(self) -> None:
        simulation = self._build_simulation(extinction_grace_ticks=5)
        simulation._predator_prey_state.predator_zero_ticks = 2
        hud = HUD()

        lines = hud._lines_predator_prey(simulation)

        self.assertIn("Danger: predators zero (3t grace)", "\n".join(lines))

    def test_game_over_summary_lines_include_adjustment_modifier(self) -> None:
        simulation = self._build_simulation()
        simulation._predator_prey_state.current_seed = 222
        simulation._predator_prey_state.survival_ticks = 90
        simulation._predator_prey_state.run_history.extend([100, 100, 100])
        simulation._predator_prey_state.adaptive_tuning.non_improving_run_streak = 5
        simulation._enter_predator_prey_game_over(
            "Predators collapsed",
            predator_count=0,
            prey_count=3,
            now_seconds=10.0,
        )
        renderer = Renderer(pygame.display.set_mode((640, 360)), simulation.settings)

        lines = renderer._build_predator_prey_game_over_summary_lines(
            simulation.get_predator_prey_stability_stats()
        )
        joined = "\n".join(line for line, _color in lines)
        self.assertIn("Adjustment step: 1.25x (+25%)", joined)
        self.assertIn("Rolling median: 100", joined)

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
        simulation._predator_prey_state.highest_survival_ticks = 75
        tuning = simulation._predator_prey_state.adaptive_tuning
        tuning.current_values["predator_hunt_sense_multiplier"] = 2.15
        tuning.previous_values["predator_hunt_sense_multiplier"] = 2.10
        tuning.trial_candidate_values = dict(tuning.current_values)
        tuning.trial_active = True
        tuning.trial_phase = "baseline"
        tuning.trial_dial = "predator_hunt_sense_multiplier"
        tuning.trial_direction = 1
        tuning.trial_baseline_average = 60.0
        tuning.trial_seeds = [111, 222, 333]
        tuning.trial_seed_index = 1
        tuning.trial_candidate_results = [80]
        tuning.trial_baseline_results = [70]
        tuning.last_decision = "trial_started"
        tuning.non_improving_run_streak = 2
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
