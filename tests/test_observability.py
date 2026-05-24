from __future__ import annotations

import pytest
from types import SimpleNamespace

from primordial.simulation.observability import (
    average_age_ticks,
    average_traits,
    evolution_distance_mean_abs,
    lineage_summary_for_population,
    top_trait_directions,
    trait_deltas,
)
from primordial.settings import Settings
from primordial.simulation.simulation import Simulation


def _creature(age: int, lineage_id: int, species: str = "prey", **traits):
    defaults = dict(speed=0.5, size=0.5, sense_radius=0.5, aggression=0.5, efficiency=0.5, longevity=0.5, depth_preference=0.5, conformity=0.5, motion_style=0.5)
    defaults.update(traits)
    return SimpleNamespace(age=age, lineage_id=lineage_id, species=species, genome=SimpleNamespace(**defaults))


def test_average_age_ticks():
    creatures = [_creature(10, 1), _creature(20, 2), _creature(30, 2)]
    assert average_age_ticks(creatures) == 20.0


def test_trait_summary_and_evolution_delta():
    baseline = {"speed": 0.4, "size": 0.5}
    current = {"speed": 0.5, "size": 0.4}
    deltas = trait_deltas(current, baseline)
    assert deltas["speed"] == pytest.approx(0.1)
    assert deltas["size"] == pytest.approx(-0.1)
    assert evolution_distance_mean_abs(deltas) == pytest.approx(0.1)


def test_top_trait_direction_filter_sort():
    deltas = {"speed": 0.06, "sense_radius": 0.03, "aggression": -0.08, "size": 0.01}
    top = top_trait_directions(deltas, noise_threshold=0.015, limit=2)
    assert top == ("aggression -0.08", "speed +0.06")


def test_lineage_summary_active_counts_and_ages():
    creatures = [_creature(40, 10), _creature(20, 11), _creature(10, 11)]
    summary = lineage_summary_for_population(creatures, current_tick=100, lineage_first_seen_ticks={10: 20, 11: 80})
    assert summary.active_lineage_count == 2
    assert summary.oldest_lineage_age_ticks == 80
    assert summary.average_lineage_age_ticks == 50


def test_reset_recaptures_run_baseline_observability():
    settings = Settings()
    settings.sim_mode = "energy"
    sim = Simulation(240, 160, settings)
    assert sim._run_baseline_traits
    original = dict(sim._run_baseline_traits)
    sim._run_baseline_traits = {}
    sim.reset()
    assert sim._run_baseline_traits
    assert sim._run_baseline_traits != {}
    assert set(sim._run_baseline_traits) == set(original)


def test_creature_observability_uses_mode_tick_hz():
    settings = Settings()
    settings.sim_mode = "drift"
    settings.mode_params["drift"]["simulation_tick_hz"] = 60
    sim = Simulation(240, 160, settings)
    creature = sim.creatures[0]
    creature.age = 120
    sim._frame = 240
    sim._lineage_first_seen_tick[creature.lineage_id] = 60
    obs = sim.get_creature_observability(creature)
    assert obs["age_seconds"] == pytest.approx(2.0)
    assert obs["lineage_age_seconds"] == pytest.approx(3.0)
