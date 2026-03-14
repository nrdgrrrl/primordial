from __future__ import annotations

import csv
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from primordial.run_logging import PredatorPreyCSVRunLogger
from primordial.settings import Settings
from primordial.simulation import Simulation
from primordial.utils.cli import parse_runtime_args


class RunLoggingTests(unittest.TestCase):
    def _build_settings(self) -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = "predator_prey"
        settings.initial_population = 0
        settings.max_population = 64
        settings.food_max_particles = 32
        settings.zone_count = 0
        settings.mode_params["predator_prey"]["initial_population"] = 0
        settings.mode_params["predator_prey"]["adaptive_trial_seed_count"] = 1
        return settings

    def _build_simulation(self) -> Simulation:
        simulation = Simulation(1000, 1000, self._build_settings())
        simulation.creatures.clear()
        simulation.food_manager.clear()
        simulation.zone_manager.zones = []
        return simulation

    def test_parse_runtime_args_accepts_csv_run_logging(self) -> None:
        args = parse_runtime_args(["--log=csv", "--mode", "predator_prey"])

        self.assertEqual(args.log, "csv")
        self.assertEqual(args.mode, "predator_prey")

    def test_csv_logger_appends_completed_run_and_reset_rows(self) -> None:
        simulation = self._build_simulation()
        simulation._predator_prey_state.current_seed = 424242
        simulation._predator_prey_state.run_history.extend([100, 100, 100])
        simulation._predator_prey_state.survival_ticks = 90
        simulation._predator_prey_state.predator_low_ticks = 7
        simulation._predator_prey_state.prey_low_ticks = 3
        tuning = simulation._predator_prey_state.adaptive_tuning
        tuning.previous_values["predator_contact_kill_distance_scale"] = 1.00
        tuning.current_values["predator_contact_kill_distance_scale"] = 0.97
        tuning.trial_candidate_values["predator_contact_kill_distance_scale"] = 0.97
        tuning.trial_active = True
        tuning.trial_phase = "candidate"
        tuning.trial_dial = "predator_contact_kill_distance_scale"
        tuning.trial_direction = -1
        tuning.trial_baseline_average = 100.0
        tuning.trial_id = 7
        tuning.trial_seeds = [111]
        tuning.last_decision = "trial_started"
        simulation._apply_predator_prey_tuning_values(tuning.current_values)

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "run_logs" / "predator_prey_runs.csv"
            simulation.set_predator_prey_run_logger(PredatorPreyCSVRunLogger(csv_path))

            simulation._enter_predator_prey_game_over(
                "Predators collapsed",
                predator_count=0,
                prey_count=3,
                now_seconds=10.0,
            )
            simulation.reset_predator_prey_adaptive_tuning()

            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 2)

        completed = rows[0]
        self.assertEqual(completed["event_type"], "run_complete")
        self.assertEqual(completed["event_note"], "species_collapse")
        self.assertEqual(completed["seed"], "424242")
        self.assertEqual(completed["survival_ticks"], "90")
        self.assertEqual(completed["predator_low_ticks"], "7")
        self.assertEqual(completed["prey_low_ticks"], "3")
        self.assertEqual(completed["near_extinction_pressure"], "10")
        self.assertEqual(completed["collapse_cause"], "Predators collapsed")
        self.assertEqual(completed["run_trial_dial"], "predator_contact_kill_distance_scale")
        self.assertEqual(completed["run_trial_direction"], "-")
        self.assertEqual(completed["run_trial_delta"], "-0.03")
        self.assertEqual(completed["trial_id"], "7")
        self.assertEqual(completed["run_evaluation_role"], "candidate")
        self.assertEqual(completed["verification_seed"], "111")
        self.assertEqual(completed["survival_deadband"], "50.0")
        self.assertEqual(
            completed["run_dial_predator_contact_kill_distance_scale"],
            "0.97",
        )
        self.assertEqual(
            completed["current_dial_predator_contact_kill_distance_scale"],
            "1.0",
        )
        self.assertEqual(completed["post_run_trial_decision"], "trial_started")
        self.assertEqual(completed["next_trial_active"], "True")
        self.assertEqual(completed["run_history"], "100|100|100|90")

        reset = rows[1]
        self.assertEqual(reset["event_type"], "dial_reset")
        self.assertEqual(reset["event_note"], "manual_reset_to_baseline")
        self.assertEqual(
            reset["current_dial_predator_contact_kill_distance_scale"],
            "1.0",
        )
        self.assertEqual(
            reset["baseline_dial_predator_contact_kill_distance_scale"],
            "1.0",
        )
        self.assertEqual(reset["run_history"], "")

    def test_csv_logger_appends_trial_decision_row_with_decision_basis(self) -> None:
        simulation = self._build_simulation()
        simulation._predator_prey_state.current_seed = 111
        simulation._predator_prey_state.run_history.extend([100, 100, 100])
        simulation._predator_prey_state.survival_ticks = 100
        simulation._predator_prey_state.predator_low_ticks = 8
        simulation._predator_prey_state.prey_low_ticks = 2
        tuning = simulation._predator_prey_state.adaptive_tuning
        tuning.previous_values["predator_contact_kill_distance_scale"] = 1.00
        tuning.current_values["predator_contact_kill_distance_scale"] = 1.00
        tuning.trial_candidate_values["predator_contact_kill_distance_scale"] = 0.97
        tuning.trial_active = True
        tuning.trial_phase = "baseline"
        tuning.trial_dial = "predator_contact_kill_distance_scale"
        tuning.trial_direction = -1
        tuning.trial_baseline_average = 100.0
        tuning.trial_id = 9
        tuning.trial_seeds = [111]
        tuning.trial_seed_index = 0
        tuning.trial_candidate_results = [110]
        tuning.trial_candidate_pressures = [4]
        tuning.last_decision = "trial_started"
        simulation._apply_predator_prey_tuning_values(tuning.current_values)

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "run_logs" / "predator_prey_runs.csv"
            simulation.set_predator_prey_run_logger(PredatorPreyCSVRunLogger(csv_path))

            simulation._enter_predator_prey_game_over(
                "Predators collapsed",
                predator_count=0,
                prey_count=3,
                now_seconds=10.0,
            )

            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 2)
        decision = rows[1]
        self.assertEqual(decision["event_type"], "trial_decision")
        self.assertEqual(decision["event_note"], "adaptive_trial_complete")
        self.assertEqual(decision["decision_basis"], "near_extinction_tiebreak")
        self.assertEqual(decision["keep_revert_outcome"], "kept")
        self.assertEqual(decision["trial_id"], "9")
        self.assertEqual(decision["run_evaluation_role"], "baseline")
        self.assertEqual(decision["verification_seed"], "111")
        self.assertEqual(decision["survival_median_candidate"], "110.0")
        self.assertEqual(decision["survival_median_baseline"], "100.0")
        self.assertEqual(decision["near_extinction_candidate"], "4.0")
        self.assertEqual(decision["near_extinction_baseline"], "10.0")


if __name__ == "__main__":
    unittest.main()
