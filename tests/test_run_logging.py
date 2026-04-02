from __future__ import annotations

import csv
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from primordial.run_logging import PredatorPreyCSVRunLogger
from primordial.settings import Settings
from primordial.simulation import Simulation
from primordial.utils.cli import parse_runtime_args


class RunLoggingTests(unittest.TestCase):
    def _build_settings(self, *, trial_count: int = 1) -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = "predator_prey"
        settings.initial_population = 0
        settings.max_population = 64
        settings.food_max_particles = 32
        settings.zone_count = 0
        settings.mode_params["predator_prey"]["initial_population"] = 0
        settings.mode_params["predator_prey"]["adaptive_tuning_enabled"] = True
        settings.mode_params["predator_prey"]["adaptive_trial_seed_count"] = trial_count
        return settings

    def _build_simulation(self, *, trial_count: int = 1) -> Simulation:
        simulation = Simulation(1000, 1000, self._build_settings(trial_count=trial_count))
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
        tuning.post_run_trial_decision = "trial_started"
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
        self.assertEqual(completed["trial_role"], "candidate")
        self.assertEqual(completed["run_evaluation_role"], "candidate")
        self.assertEqual(completed["verification_seed"], "111")
        self.assertEqual(completed["verification_seed_count_configured"], "1")
        self.assertEqual(completed["candidate_eval_index"], "1")
        self.assertEqual(completed["baseline_eval_index"], "")
        self.assertEqual(completed["total_candidate_evals_expected"], "1")
        self.assertEqual(completed["total_baseline_evals_expected"], "1")
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
        tuning.post_run_trial_decision = "trial_started"
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
        self.assertEqual(decision["run_was_trial"], "False")
        self.assertEqual(decision["trial_role"], "")
        self.assertEqual(decision["run_evaluation_role"], "")
        self.assertEqual(decision["verification_seed"], "")
        self.assertEqual(decision["verification_seed_count_configured"], "1")
        self.assertEqual(decision["candidate_eval_index"], "1")
        self.assertEqual(decision["baseline_eval_index"], "1")
        self.assertEqual(decision["total_candidate_evals_expected"], "1")
        self.assertEqual(decision["total_baseline_evals_expected"], "1")
        self.assertEqual(decision["decision_basis"], "near_extinction_tiebreak")
        self.assertEqual(decision["keep_revert_outcome"], "keep")
        self.assertEqual(decision["trial_id"], "9")
        self.assertEqual(decision["survival_median_candidate"], "110.0")
        self.assertEqual(decision["survival_median_baseline"], "100.0")
        self.assertEqual(decision["near_extinction_candidate"], "4.0")
        self.assertEqual(decision["near_extinction_baseline"], "10.0")

    def test_csv_logger_records_k2_trial_structure_and_exact_tie_revert(self) -> None:
        simulation = self._build_simulation(trial_count=2)
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with (
            patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None),
            patch.object(
                simulation,
                "_generate_predator_prey_seed",
                side_effect=[111, 222],
            ),
        ):
            simulation._finalize_predator_prey_run(50)

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "run_logs" / "predator_prey_runs.csv"
            simulation.set_predator_prey_run_logger(PredatorPreyCSVRunLogger(csv_path))

            simulation._predator_prey_state.survival_ticks = 120
            simulation._enter_predator_prey_game_over(
                "Predators collapsed",
                predator_count=0,
                prey_count=3,
                now_seconds=10.0,
            )
            simulation.restart_predator_prey_run()

            simulation._predator_prey_state.survival_ticks = 120
            simulation._enter_predator_prey_game_over(
                "Predators collapsed",
                predator_count=0,
                prey_count=3,
                now_seconds=11.0,
            )
            simulation.restart_predator_prey_run()

            simulation._predator_prey_state.survival_ticks = 110
            simulation._enter_predator_prey_game_over(
                "Predators collapsed",
                predator_count=0,
                prey_count=3,
                now_seconds=12.0,
            )
            simulation.restart_predator_prey_run()

            simulation._predator_prey_state.survival_ticks = 110
            simulation._enter_predator_prey_game_over(
                "Predators collapsed",
                predator_count=0,
                prey_count=3,
                now_seconds=13.0,
            )

            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 5)
        run_rows = rows[:4]
        decision_row = rows[4]

        self.assertEqual(
            [row["trial_role"] for row in run_rows],
            ["candidate", "baseline", "candidate", "baseline"],
        )
        self.assertEqual(
            [row["verification_seed"] for row in run_rows if row["trial_role"] == "candidate"],
            ["111", "222"],
        )
        self.assertEqual(
            [row["verification_seed"] for row in run_rows if row["trial_role"] == "baseline"],
            ["111", "222"],
        )
        self.assertEqual(
            [row["candidate_eval_index"] for row in run_rows if row["trial_role"] == "candidate"],
            ["1", "2"],
        )
        self.assertEqual(
            [row["baseline_eval_index"] for row in run_rows if row["trial_role"] == "baseline"],
            ["1", "2"],
        )
        self.assertTrue(
            all(row["verification_seed_count_configured"] == "2" for row in run_rows)
        )
        self.assertTrue(
            all(row["total_candidate_evals_expected"] == "2" for row in run_rows)
        )
        self.assertTrue(
            all(row["total_baseline_evals_expected"] == "2" for row in run_rows)
        )

        final_baseline = run_rows[-1]
        self.assertEqual(final_baseline["decision_basis"], "exact_tie_revert_candidate")
        self.assertEqual(final_baseline["keep_revert_outcome"], "revert")
        self.assertEqual(final_baseline["survival_median_candidate"], "115.0")
        self.assertEqual(final_baseline["survival_median_baseline"], "115.0")

        self.assertEqual(decision_row["event_type"], "trial_decision")
        self.assertEqual(decision_row["run_was_trial"], "False")
        self.assertEqual(decision_row["verification_seed"], "")
        self.assertEqual(decision_row["verification_seed_count_configured"], "2")
        self.assertEqual(decision_row["candidate_eval_index"], "2")
        self.assertEqual(decision_row["baseline_eval_index"], "2")
        self.assertEqual(decision_row["decision_basis"], "exact_tie_revert_candidate")
        self.assertEqual(decision_row["keep_revert_outcome"], "revert")

    def test_csv_logger_records_immediate_retry_and_retry_cap_fields(self) -> None:
        simulation = self._build_simulation(trial_count=1)
        simulation.settings.mode_params["predator_prey"][
            "adaptive_max_consecutive_retry_trials"
        ] = 2
        simulation._predator_prey_state.run_history.extend([100, 100, 100])

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "run_logs" / "predator_prey_runs.csv"
            simulation.set_predator_prey_run_logger(PredatorPreyCSVRunLogger(csv_path))

            with patch("primordial.simulation.simulation.random.shuffle", side_effect=lambda seq: None):
                for index, survival_ticks in enumerate((50, 80, 90, 70, 100, 60, 110, 40)):
                    simulation._predator_prey_state.survival_ticks = survival_ticks
                    simulation._enter_predator_prey_game_over(
                        "Predators collapsed",
                        predator_count=0,
                        prey_count=3,
                        now_seconds=10.0 + index,
                    )
                    if index < 7:
                        simulation.restart_predator_prey_run()

            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        first_retry_revert = rows[2]
        self.assertEqual(first_retry_revert["trial_role"], "baseline")
        self.assertEqual(first_retry_revert["post_run_trial_decision"], "reverted")
        self.assertEqual(first_retry_revert["next_trial_active"], "True")
        self.assertEqual(
            first_retry_revert["next_trial_trigger_reason"],
            "immediate_retry_after_revert",
        )
        self.assertEqual(first_retry_revert["consecutive_immediate_retry_trials"], "1")
        self.assertEqual(first_retry_revert["immediate_retry_trial_cap"], "2")
        self.assertEqual(first_retry_revert["trial_launch_blocked_by_retry_cap"], "False")

        cap_blocked_revert = rows[8]
        self.assertEqual(cap_blocked_revert["trial_role"], "baseline")
        self.assertEqual(cap_blocked_revert["post_run_trial_decision"], "reverted")
        self.assertEqual(cap_blocked_revert["next_trial_active"], "False")
        self.assertEqual(cap_blocked_revert["next_trial_trigger_reason"], "")
        self.assertEqual(cap_blocked_revert["consecutive_immediate_retry_trials"], "2")
        self.assertEqual(cap_blocked_revert["immediate_retry_trial_cap"], "2")
        self.assertEqual(cap_blocked_revert["trial_launch_blocked_by_retry_cap"], "True")

        forced_ordinary = rows[10]
        self.assertEqual(forced_ordinary["trial_role"], "ordinary")
        self.assertEqual(forced_ordinary["post_run_trial_decision"], "trial_started")
        self.assertEqual(forced_ordinary["next_trial_active"], "True")
        self.assertEqual(
            forced_ordinary["next_trial_trigger_reason"],
            "blocked_by_retry_cap_then_waited_for_ordinary_run",
        )
        self.assertEqual(forced_ordinary["consecutive_immediate_retry_trials"], "0")
        self.assertEqual(forced_ordinary["immediate_retry_trial_cap"], "2")


if __name__ == "__main__":
    unittest.main()
