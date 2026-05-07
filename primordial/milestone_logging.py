"""Milestone log writer for predator-prey narrative generation.

Produces a YAML file of semantic events (population explosions/crashes,
species role flips, lineage evolution, adaptive tuning changes, etc.)
designed to be fed to an LLM for narrative storytelling.

Usage:
    python -m primordial --mode=predator_prey --milestone-log=milestone.yml
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_POPULATION_EXPLOSION_FACTOR = 2.0
_POPULATION_CRASH_FACTOR = 0.5
_SPECIES_FLIP_WINDOW_TICKS = 300
_DOMINANCE_SHIFT_RATIO = 0.3
_LINEAGE_EMERGENCE_MIN_POP = 5


@dataclass
class _PopulationSnapshot:
    pred_count: int = 0
    prey_count: int = 0
    total: int = 0
    tick: int = 0


@dataclass
class _SpeciesFlipTracker:
    pred_to_prey: int = 0
    prey_to_pred: int = 0
    last_reset_tick: int = 0


@dataclass
class _DialSnapshot:
    values: dict[str, float] = field(default_factory=dict)
    tick: int = 0


class PredatorPreyMilestoneLogger:
    """Attaches to a Simulation and records narrative-significant events to YAML."""

    def __init__(self, yaml_path: str | Path) -> None:
        self._yaml_path = Path(yaml_path)
        self._yaml_path.parent.mkdir(parents=True, exist_ok=True)
        self._events: list[dict[str, Any]] = []
        self._session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._session_started = datetime.now(timezone.utc).isoformat()
        self._prev_snap = _PopulationSnapshot()
        self._flip_tracker = _SpeciesFlipTracker()
        self._prev_dial_snap = _DialSnapshot()
        self._seen_lineages: set[int] = set()
        self._last_event_tick: int = 0
        self._min_event_gap = 10
        self._population_history: list[_PopulationSnapshot] = []
        self._run_number: int = 0
        logger.info("Milestone log enabled: %s", self._yaml_path)

    def log_session_start(self, sim: Any) -> None:
        self._append_event("session_start", sim, {
            "seed": self._safe_attr(sim, "current_seed"),
            "population": self._safe_attr(sim, "population"),
        })

    def log_run_start(self, sim: Any) -> None:
        self._run_number += 1
        pred, prey = self._safe_call(sim, "get_species_counts", (0, 0))
        snap = _PopulationSnapshot(pred_count=pred, prey_count=prey, total=pred + prey, tick=self._tick(sim))
        self._prev_snap = snap
        self._population_history = [snap]
        self._flip_tracker = _SpeciesFlipTracker()
        self._append_event("run_start", sim, {
            "run_number": self._run_number,
            "seed": self._safe_attr(sim, "current_seed"),
            "predator_count": pred,
            "prey_count": prey,
        })

    def log_population_change(self, sim: Any) -> None:
        tick = self._tick(sim)
        if tick - self._last_event_tick < self._min_event_gap:
            return
        pred, prey = self._safe_call(sim, "get_species_counts", (0, 0))
        total = pred + prey
        if total == 0:
            return
        snap = _PopulationSnapshot(pred_count=pred, prey_count=prey, total=total, tick=tick)
        self._population_history.append(snap)
        if len(self._population_history) > 60:
            self._population_history = self._population_history[-60:]
        prev = self._prev_snap
        if prev.total > 0:
            ratio = total / prev.total
            if ratio >= _POPULATION_EXPLOSION_FACTOR:
                self._append_event("population_explosion", sim, {
                    "species": self._dominant_species(pred, prey),
                    "from_total": prev.total,
                    "to_total": total,
                    "predator_count": pred,
                    "prey_count": prey,
                    "ratio": round(ratio, 2),
                })
            elif ratio <= _POPULATION_CRASH_FACTOR and prev.total >= 5:
                self._append_event("population_crash", sim, {
                    "species": self._crashed_species(prev, snap),
                    "from_total": prev.total,
                    "to_total": total,
                    "predator_count": pred,
                    "prey_count": prey,
                    "ratio": round(ratio, 2),
                })
            if prev.total > 0:
                prev_pred_frac = prev.pred_count / prev.total
                curr_pred_frac = pred / total if total > 0 else 0
                if abs(curr_pred_frac - prev_pred_frac) >= _DOMINANCE_SHIFT_RATIO:
                    if prev_pred_frac > 0.6 and curr_pred_frac < 0.4:
                        self._append_event("dominance_shift", sim, {
                            "from": "predator_dominated",
                            "to": "prey_dominated",
                            "predator_fraction_before": round(prev_pred_frac, 2),
                            "predator_fraction_after": round(curr_pred_frac, 2),
                        })
                    elif prev_pred_frac < 0.4 and curr_pred_frac > 0.6:
                        self._append_event("dominance_shift", sim, {
                            "from": "prey_dominated",
                            "to": "predator_dominated",
                            "predator_fraction_before": round(prev_pred_frac, 2),
                            "predator_fraction_after": round(curr_pred_frac, 2),
                        })
        self._prev_snap = snap

    def log_species_flip(self, sim: Any, creature: Any, from_species: str, to_species: str) -> None:
        tick = self._tick(sim)
        if to_species == "predator":
            self._flip_tracker.prey_to_pred += 1
        else:
            self._flip_tracker.pred_to_prey += 1
        if tick - self._flip_tracker.last_reset_tick >= _SPECIES_FLIP_WINDOW_TICKS:
            total_flips = self._flip_tracker.pred_to_prey + self._flip_tracker.prey_to_pred
            if total_flips >= 3:
                self._append_event("species_role_flux", sim, {
                    "predator_to_prey": self._flip_tracker.pred_to_prey,
                    "prey_to_predator": self._flip_tracker.prey_to_pred,
                    "window_ticks": _SPECIES_FLIP_WINDOW_TICKS,
                    "creature_lineage": self._safe_attr(creature, "lineage_id"),
                    "creature_aggression": round(self._safe_genome_attr(creature, "aggression"), 3),
                })
            self._flip_tracker = _SpeciesFlipTracker(last_reset_tick=tick)
        genome_summary = self._genome_summary(creature)
        self._append_event("species_flip", sim, {
            "from_species": from_species,
            "to_species": to_species,
            "trigger": "cosmic_ray",
            "lineage_id": self._safe_attr(creature, "lineage_id"),
            "genome": genome_summary,
        })

    def log_lineage_evolution(self, sim: Any) -> None:
        lineage_counts = self._safe_call(sim, "get_lineage_counts", {})
        tick = self._tick(sim)
        for lid, count in lineage_counts.items():
            if lid not in self._seen_lineages and count >= _LINEAGE_EMERGENCE_MIN_POP:
                self._seen_lineages.add(lid)
                self._append_event("lineage_emergence", sim, {
                    "lineage_id": lid,
                    "population": count,
                })
        extinct = self._seen_lineages - set(lineage_counts.keys())
        for lid in extinct:
            self._seen_lineages.discard(lid)
            self._append_event("lineage_extinction", sim, {
                "lineage_id": lid,
            })

    def log_adaptive_tuning_change(self, sim: Any, dial_name: str, old_value: float, new_value: float) -> None:
        delta = new_value - old_value
        if abs(delta) < 0.001:
            return
        self._append_event("adaptive_tuning_change", sim, {
            "dial": dial_name,
            "old_value": round(old_value, 4),
            "new_value": round(new_value, 4),
            "delta": round(delta, 4),
        })

    def log_dial_reset(self, sim: Any) -> None:
        state = self._safe_attr(sim, "_predator_prey_state")
        if state is None:
            return
        tuning = self._safe_attr(state, "adaptive_tuning")
        if tuning is None:
            return
        current = self._safe_attr(tuning, "current_values", {})
        baseline = self._safe_attr(tuning, "baseline_values", {})
        self._append_event("adaptive_tuning_reset", sim, {
            "reset_values": dict(current),
            "baseline_values": dict(baseline),
        })

    def log_collapse(self, sim: Any, cause: str) -> None:
        pred, prey = self._safe_call(sim, "get_species_counts", (0, 0))
        self._append_event("ecosystem_collapse", sim, {
            "cause": cause,
            "predator_count": pred,
            "prey_count": prey,
            "survival_ticks": self._safe_attr(sim, "predator_prey_survival_ticks", 0),
        })

    def log_run_end(self, sim: Any, survival_ticks: int) -> None:
        pred, prey = self._safe_call(sim, "get_species_counts", (0, 0))
        pred_speed, prey_speed = self._safe_call(sim, "get_species_avg_speeds", (0.0, 0.0))
        state = self._safe_attr(sim, "_predator_prey_state")
        highest = self._safe_attr(state, "highest_survival_ticks", 0) if state else 0
        self._append_event("run_end", sim, {
            "run_number": self._run_number,
            "survival_ticks": survival_ticks,
            "highest_survival_ticks": highest,
            "new_record": survival_ticks >= highest and highest > 0,
            "predator_count": pred,
            "prey_count": prey,
            "avg_predator_speed": round(pred_speed, 3),
            "avg_prey_speed": round(prey_speed, 3),
            "total_kills": self._safe_attr(sim, "predation_kill_count", 0),
        })

    def log_completed_run(self, sim: Any) -> None:
        state = self._safe_attr(sim, "_predator_prey_state")
        ticks = self._safe_attr(state, "survival_ticks", 0) if state else 0
        self.log_run_end(sim, ticks)
        self._flush()

    def log_trial_decision(self, sim: Any) -> None:
        state = self._safe_attr(sim, "_predator_prey_state")
        if state is None:
            return
        tuning = self._safe_attr(state, "adaptive_tuning")
        if tuning is None:
            return
        decision = self._safe_attr(tuning, "last_decision", "unknown")
        dial = self._safe_attr(tuning, "trial_dial", "unknown")
        direction = self._safe_attr(tuning, "trial_direction", 0)
        self._append_event("trial_decision", sim, {
            "decision": decision,
            "dial": dial,
            "direction": "+" if direction > 0 else ("-" if direction < 0 else "0"),
        })
        self._flush()

    def close(self) -> None:
        self._flush()

    def _flush(self) -> None:
        payload = {
            "session_id": self._session_id,
            "session_started_at_utc": self._session_started,
            "total_events": len(self._events),
            "events": self._events,
        }
        try:
            self._yaml_path.write_text(
                yaml.dump(payload, default_flow_style=False, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to write milestone log to %s: %s", self._yaml_path, exc)

    def _append_event(self, event_type: str, sim: Any, details: dict[str, Any]) -> None:
        tick = self._tick(sim)
        self._last_event_tick = tick
        event: dict[str, Any] = {
            "tick": tick,
            "sim_ticks": tick,
            "event_type": event_type,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        event.update(details)
        self._events.append(event)

    @staticmethod
    def _tick(sim: Any) -> int:
        state = getattr(sim, "_predator_prey_state", None)
        if state is not None:
            return getattr(state, "sim_ticks", 0)
        return 0

    @staticmethod
    def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
        return getattr(obj, name, default)

    @staticmethod
    def _safe_call(obj: Any, method: str, default: Any) -> Any:
        fn = getattr(obj, method, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                return default
        return default

    @staticmethod
    def _safe_genome_attr(creature: Any, trait: str) -> float:
        genome = getattr(creature, "genome", None)
        if genome is not None:
            return getattr(genome, trait, 0.0)
        return 0.0

    @staticmethod
    def _genome_summary(creature: Any) -> dict[str, float]:
        genome = getattr(creature, "genome", None)
        if genome is None:
            return {}
        return {
            "speed": round(genome.speed, 3),
            "size": round(genome.size, 3),
            "sense_radius": round(genome.sense_radius, 3),
            "aggression": round(genome.aggression, 3),
            "efficiency": round(genome.efficiency, 3),
            "longevity": round(genome.longevity, 3),
        }

    @staticmethod
    def _dominant_species(pred: int, prey: int) -> str:
        if pred > prey:
            return "predator"
        elif prey > pred:
            return "prey"
        return "balanced"

    @staticmethod
    def _crashed_species(prev: _PopulationSnapshot, curr: _PopulationSnapshot) -> str:
        pred_drop = prev.pred_count - curr.pred_count
        prey_drop = prev.prey_count - curr.prey_count
        if pred_drop > prey_drop:
            return "predator"
        elif prey_drop > pred_drop:
            return "prey"
        return "both"