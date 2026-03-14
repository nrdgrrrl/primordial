"""CSV run logging for predator-prey stability analysis."""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

_DIAL_KEYS = (
    "predator_contact_kill_distance_scale",
    "predator_kill_energy_gain_cap",
    "predator_hunt_sense_multiplier",
    "prey_flee_sense_multiplier",
    "predator_prey_scarcity_penalty_multiplier",
    "food_cycle_amplitude",
)

_BASE_FIELDNAMES = [
    "timestamp_utc",
    "session_started_at_utc",
    "event_type",
    "event_note",
    "mode",
    "seed",
    "sim_ticks",
    "survival_ticks",
    "predator_low_ticks",
    "prey_low_ticks",
    "near_extinction_pressure",
    "collapse_cause",
    "collapse_predators",
    "collapse_prey",
    "rolling_average_at_collapse",
    "beat_average",
    "was_new_highest",
    "best_recent_survival_ticks",
    "highest_survival_ticks",
    "history_window_size",
    "run_history",
    "run_was_trial",
    "run_trial_dial",
    "run_trial_direction",
    "run_trial_delta",
    "run_trial_value",
    "run_trial_baseline_average",
    "trial_id",
    "run_evaluation_role",
    "verification_seed",
    "survival_deadband",
    "decision_basis",
    "keep_revert_outcome",
    "survival_median_candidate",
    "survival_median_baseline",
    "near_extinction_candidate",
    "near_extinction_baseline",
    "post_run_trial_decision",
    "next_trial_active",
    "next_trial_dial",
    "next_trial_direction",
    "next_trial_baseline_average",
    "non_improving_run_streak",
    "adjustment_step_multiplier",
    "adjustment_step_increase_percent",
    "predator_actual_speed",
    "prey_actual_speed",
    "recent_kills",
    "recent_cross_band_misses",
    "total_kills",
]
_FIELDNAMES = (
    _BASE_FIELDNAMES
    + [f"run_dial_{key}" for key in _DIAL_KEYS]
    + [f"current_dial_{key}" for key in _DIAL_KEYS]
    + [f"baseline_dial_{key}" for key in _DIAL_KEYS]
)


if TYPE_CHECKING:
    from .simulation import Simulation


class PredatorPreyCSVRunLogger:
    """Append predator-prey run telemetry to a single CSV file."""

    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path
        self.session_started_at_utc = self._timestamp()
        try:
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_header()
        except OSError as exc:
            logger.warning("Unable to initialize run log at %s: %s", self.csv_path, exc)

    def log_completed_run(self, simulation: "Simulation") -> None:
        self._append_row(self._build_completed_run_row(simulation))

    def log_trial_decision(self, simulation: "Simulation") -> None:
        self._append_row(self._build_trial_decision_row(simulation))

    def log_dial_reset(
        self,
        simulation: "Simulation",
        *,
        note: str = "manual_reset_to_baseline",
    ) -> None:
        self._append_row(self._build_reset_row(simulation, note=note))

    def _build_completed_run_row(self, simulation: "Simulation") -> dict[str, Any]:
        stats = simulation.get_predator_prey_stability_stats()
        runtime_state = simulation.export_predator_prey_runtime_state()
        adaptive = runtime_state.get("adaptive_tuning", {})
        run_dials = stats.get("collapse_dial_values", {}) or {}
        current_dials = adaptive.get("current_values", {}) or {}
        baseline_dials = adaptive.get("baseline_values", {}) or {}
        pred_actual_speed, prey_actual_speed = simulation.get_species_avg_actual_speeds()
        predation = simulation.get_recent_predation_stats()
        run_was_trial = stats.get("collapse_trial_role") in {"candidate", "baseline"}
        decision_completed = (
            run_was_trial
            and adaptive.get("last_decision") in {"kept", "reverted"}
        )
        row = self._base_row(
            event_type="run_complete",
            event_note="species_collapse",
            simulation=simulation,
            stats=stats,
        )
        row.update(
            {
                "run_was_trial": run_was_trial,
                "run_trial_dial": stats.get("collapse_trial_dial"),
                "run_trial_direction": stats.get("collapse_trial_direction"),
                "run_trial_delta": self._float_or_none(
                    stats.get("collapse_trial_delta")
                ),
                "run_trial_value": self._float_or_none(
                    stats.get("collapse_trial_value")
                ),
                "run_trial_baseline_average": (
                    self._float_or_none(stats.get("collapse_rolling_average"))
                    if run_was_trial
                    else None
                ),
                "trial_id": (
                    stats.get("collapse_trial_id")
                    if run_was_trial
                    else None
                ),
                "run_evaluation_role": (
                    stats.get("collapse_trial_role")
                    if run_was_trial
                    else None
                ),
                "verification_seed": (
                    stats.get("collapse_trial_seed")
                    if run_was_trial
                    else None
                ),
                "survival_deadband": self._float_or_none(
                    stats.get("survival_deadband")
                ),
                "decision_basis": (
                    stats.get("trial_last_decision_basis")
                    if decision_completed
                    else None
                ),
                "keep_revert_outcome": (
                    adaptive.get("last_decision")
                    if decision_completed
                    else None
                ),
                "survival_median_candidate": (
                    self._float_or_none(
                        stats.get("trial_last_survival_median_candidate")
                    )
                    if decision_completed
                    else None
                ),
                "survival_median_baseline": (
                    self._float_or_none(
                        stats.get("trial_last_survival_median_baseline")
                    )
                    if decision_completed
                    else None
                ),
                "near_extinction_candidate": (
                    self._float_or_none(
                        stats.get("trial_last_near_extinction_candidate")
                    )
                    if decision_completed
                    else None
                ),
                "near_extinction_baseline": (
                    self._float_or_none(
                        stats.get("trial_last_near_extinction_baseline")
                    )
                    if decision_completed
                    else None
                ),
                "post_run_trial_decision": adaptive.get("last_decision"),
                "next_trial_active": bool(stats.get("trial_active", False)),
                "next_trial_dial": stats.get("trial_dial"),
                "next_trial_direction": stats.get("trial_direction"),
                "next_trial_baseline_average": self._float_or_none(
                    stats.get("trial_baseline_average")
                ),
                "non_improving_run_streak": int(
                    stats.get("non_improving_run_streak", 0)
                ),
                "adjustment_step_multiplier": self._float_or_none(
                    stats.get("adjustment_step_multiplier")
                ),
                "adjustment_step_increase_percent": self._float_or_none(
                    stats.get("adjustment_step_increase_percent")
                ),
                "predator_actual_speed": pred_actual_speed,
                "prey_actual_speed": prey_actual_speed,
                "recent_kills": int(predation.get("recent_kills", 0)),
                "recent_cross_band_misses": int(
                    predation.get("recent_cross_band_misses", 0)
                ),
                "total_kills": int(predation.get("total_kills", 0)),
            }
        )
        self._add_dial_columns(
            row,
            run_dials=run_dials,
            current_dials=current_dials,
            baseline_dials=baseline_dials,
        )
        return row

    def _build_trial_decision_row(self, simulation: "Simulation") -> dict[str, Any]:
        stats = simulation.get_predator_prey_stability_stats()
        runtime_state = simulation.export_predator_prey_runtime_state()
        adaptive = runtime_state.get("adaptive_tuning", {})
        run_dials = stats.get("collapse_dial_values", {}) or {}
        current_dials = adaptive.get("current_values", {}) or {}
        baseline_dials = adaptive.get("baseline_values", {}) or {}
        row = self._base_row(
            event_type="trial_decision",
            event_note="adaptive_trial_complete",
            simulation=simulation,
            stats=stats,
        )
        row.update(
            {
                "run_was_trial": True,
                "run_trial_dial": stats.get("collapse_trial_dial"),
                "run_trial_direction": stats.get("collapse_trial_direction"),
                "run_trial_delta": self._float_or_none(
                    stats.get("collapse_trial_delta")
                ),
                "run_trial_value": self._float_or_none(
                    stats.get("collapse_trial_value")
                ),
                "run_trial_baseline_average": self._float_or_none(
                    stats.get("collapse_rolling_average")
                ),
                "trial_id": stats.get("trial_last_decision_trial_id"),
                "run_evaluation_role": stats.get("collapse_trial_role"),
                "verification_seed": stats.get("collapse_trial_seed"),
                "survival_deadband": self._float_or_none(
                    stats.get("survival_deadband")
                ),
                "decision_basis": stats.get("trial_last_decision_basis"),
                "keep_revert_outcome": adaptive.get("last_decision"),
                "survival_median_candidate": self._float_or_none(
                    stats.get("trial_last_survival_median_candidate")
                ),
                "survival_median_baseline": self._float_or_none(
                    stats.get("trial_last_survival_median_baseline")
                ),
                "near_extinction_candidate": self._float_or_none(
                    stats.get("trial_last_near_extinction_candidate")
                ),
                "near_extinction_baseline": self._float_or_none(
                    stats.get("trial_last_near_extinction_baseline")
                ),
                "post_run_trial_decision": adaptive.get("last_decision"),
                "next_trial_active": bool(stats.get("trial_active", False)),
                "next_trial_dial": stats.get("trial_dial"),
                "next_trial_direction": stats.get("trial_direction"),
                "next_trial_baseline_average": self._float_or_none(
                    stats.get("trial_baseline_average")
                ),
                "non_improving_run_streak": int(
                    stats.get("non_improving_run_streak", 0)
                ),
                "adjustment_step_multiplier": self._float_or_none(
                    stats.get("adjustment_step_multiplier")
                ),
                "adjustment_step_increase_percent": self._float_or_none(
                    stats.get("adjustment_step_increase_percent")
                ),
                "predator_actual_speed": None,
                "prey_actual_speed": None,
                "recent_kills": None,
                "recent_cross_band_misses": None,
                "total_kills": None,
            }
        )
        self._add_dial_columns(
            row,
            run_dials=run_dials,
            current_dials=current_dials,
            baseline_dials=baseline_dials,
        )
        return row

    def _build_reset_row(
        self,
        simulation: "Simulation",
        *,
        note: str,
    ) -> dict[str, Any]:
        stats = simulation.get_predator_prey_stability_stats()
        runtime_state = simulation.export_predator_prey_runtime_state()
        adaptive = runtime_state.get("adaptive_tuning", {})
        current_dials = adaptive.get("current_values", {}) or {}
        baseline_dials = adaptive.get("baseline_values", {}) or {}
        row = self._base_row(
            event_type="dial_reset",
            event_note=note,
            simulation=simulation,
            stats=stats,
        )
        row.update(
            {
                "run_was_trial": False,
                "run_trial_dial": None,
                "run_trial_direction": "",
                "run_trial_delta": None,
                "run_trial_value": None,
                "run_trial_baseline_average": None,
                "trial_id": None,
                "run_evaluation_role": None,
                "verification_seed": None,
                "survival_deadband": self._float_or_none(
                    stats.get("survival_deadband")
                ),
                "decision_basis": None,
                "keep_revert_outcome": None,
                "survival_median_candidate": None,
                "survival_median_baseline": None,
                "near_extinction_candidate": None,
                "near_extinction_baseline": None,
                "post_run_trial_decision": adaptive.get("last_decision"),
                "next_trial_active": bool(stats.get("trial_active", False)),
                "next_trial_dial": stats.get("trial_dial"),
                "next_trial_direction": stats.get("trial_direction"),
                "next_trial_baseline_average": self._float_or_none(
                    stats.get("trial_baseline_average")
                ),
                "non_improving_run_streak": int(
                    stats.get("non_improving_run_streak", 0)
                ),
                "adjustment_step_multiplier": self._float_or_none(
                    stats.get("adjustment_step_multiplier")
                ),
                "adjustment_step_increase_percent": self._float_or_none(
                    stats.get("adjustment_step_increase_percent")
                ),
                "predator_actual_speed": None,
                "prey_actual_speed": None,
                "recent_kills": None,
                "recent_cross_band_misses": None,
                "total_kills": None,
            }
        )
        self._add_dial_columns(
            row,
            run_dials={},
            current_dials=current_dials,
            baseline_dials=baseline_dials,
        )
        return row

    def _base_row(
        self,
        *,
        event_type: str,
        event_note: str,
        simulation: "Simulation",
        stats: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "timestamp_utc": self._timestamp(),
            "session_started_at_utc": self.session_started_at_utc,
            "event_type": event_type,
            "event_note": event_note,
            "mode": simulation.settings.sim_mode,
            "seed": stats.get("current_seed"),
            "sim_ticks": int(stats.get("sim_ticks", 0)),
            "survival_ticks": int(stats.get("survival_ticks", 0)),
            "predator_low_ticks": int(stats.get("predator_low_ticks", 0)),
            "prey_low_ticks": int(stats.get("prey_low_ticks", 0)),
            "near_extinction_pressure": int(
                stats.get("near_extinction_pressure", 0)
            ),
            "collapse_cause": stats.get("collapse_cause"),
            "collapse_predators": int(stats.get("collapse_predators", 0)),
            "collapse_prey": int(stats.get("collapse_prey", 0)),
            "rolling_average_at_collapse": self._float_or_none(
                stats.get("collapse_rolling_average")
            ),
            "beat_average": bool(stats.get("collapse_beat_average", False)),
            "was_new_highest": bool(stats.get("collapse_was_new_highest", False)),
            "best_recent_survival_ticks": int(
                stats.get("best_recent_survival_ticks", 0)
            ),
            "highest_survival_ticks": int(stats.get("highest_survival_ticks", 0)),
            "history_window_size": int(stats.get("history_window_size", 0)),
            "run_history": self._encode_run_history(simulation),
        }

    def _add_dial_columns(
        self,
        row: dict[str, Any],
        *,
        run_dials: dict[str, Any],
        current_dials: dict[str, Any],
        baseline_dials: dict[str, Any],
    ) -> None:
        for key in _DIAL_KEYS:
            row[f"run_dial_{key}"] = self._float_or_none(run_dials.get(key))
            row[f"current_dial_{key}"] = self._float_or_none(current_dials.get(key))
            row[f"baseline_dial_{key}"] = self._float_or_none(
                baseline_dials.get(key)
            )

    def _append_row(self, row: dict[str, Any]) -> None:
        try:
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_header()
            with self.csv_path.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=_FIELDNAMES)
                writer.writerow(row)
        except OSError as exc:
            logger.warning("Unable to append run log row to %s: %s", self.csv_path, exc)

    def _ensure_header(self) -> None:
        if self.csv_path.exists() and self.csv_path.stat().st_size > 0:
            return
        with self.csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=_FIELDNAMES)
            writer.writeheader()

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _encode_run_history(simulation: "Simulation") -> str:
        history = simulation.export_predator_prey_runtime_state().get("run_history", [])
        if not isinstance(history, list):
            return ""
        return "|".join(str(int(item)) for item in history)
