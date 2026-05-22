"""Tests for predator collapse diagnostics aggregation helpers."""
from __future__ import annotations

import unittest

# The diagnostics script lives in the tools/ directory, which is not a package.
# We add the repo root so the script can import, and then import specific helpers.
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import the tools directory for the script
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from predator_collapse_diagnostics import (
    _classify_death_context,
    _depth_band_name,
    _fmt,
    _pct,
    _pct_fmt,
    _safe_mean,
    _safe_median,
    build_report,
    render_markdown,
    _section_a_run_summary,
    _section_b_predator_life_summary,
    _section_c_death_context_breakdown,
    _section_d_origin_breakdown,
    _section_e_reproduction_bottleneck,
    _section_f_prey_access,
    _section_g_scarcity,
    _section_i_recommendations,
)


def _make_life(
    *,
    life_id=1,
    origin="initial",
    lineage_id=1,
    start_frame=0,
    end_frame=100,
    kills=0,
    deaths_produced=0,
    births_produced=0,
    highest_energy=0.5,
    frames_observed=100,
    frames_with_prey_sighted=30,
    prey_scarce_frames=60,
    cross_band_contact_misses=0,
    cross_band_misses_inside_refuge=0,
    cross_band_misses_outside_refuge=0,
    threshold_min=None,
    threshold_max=None,
    closest_peak_gap=None,
    closest_repro_check_gap=None,
    peak_reached_threshold=False,
    repro_check_reached_threshold=False,
    last_saw_prey_frame=None,
    last_kill_frame=None,
    death_cause="starvation",
    death_context="long_scarcity",
    end_reason="death",
    kill_pre_energies=None,
    kill_post_energies=None,
    age_at_death=None,
    predator_count_at_death=None,
    prey_count_at_death=None,
    depth_band_at_death=None,
    hunting_ground_frames=0,
    refuge_frames=0,
    refuge_bonus_factor_sum=0.0,
    kills_inside_refuge=0,
    kills_outside_refuge=0,
    died_inside_refuge=False,
    died_in_hunting_ground=False,
    death_zone_type=None,
    refuge_bonus_factor_at_death=0.0,
    local_predator_density_at_death=None,
    strategy_bucket_at_start="generalist",
    strategy_bucket_at_end=None,
    phenotype_modifiers_at_start=None,
    phenotype_modifiers_at_end=None,
    born_during_low_predator_rarity=False,
    start_energy=0.7,
    end_energy=0.0,
):
    """Create a synthetic predator life dict for testing."""
    return {
        "life_id": life_id,
        "origin": origin,
        "lineage_id": lineage_id,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "start_energy": start_energy,
        "end_energy": end_energy,
        "kills": kills,
        "kill_pre_energies": kill_pre_energies or [],
        "kill_post_energies": kill_post_energies or [],
        "highest_energy": highest_energy,
        "frames_observed": frames_observed,
        "frames_with_prey_sighted": frames_with_prey_sighted,
        "prey_scarce_frames": prey_scarce_frames,
        "cross_band_contact_misses": cross_band_contact_misses,
        "cross_band_misses_inside_refuge": cross_band_misses_inside_refuge,
        "cross_band_misses_outside_refuge": cross_band_misses_outside_refuge,
        "births_produced": births_produced,
        "threshold_min": threshold_min,
        "threshold_max": threshold_max,
        "closest_peak_gap": closest_peak_gap,
        "closest_repro_check_gap": closest_repro_check_gap,
        "peak_reached_threshold": peak_reached_threshold,
        "repro_check_reached_threshold": repro_check_reached_threshold,
        "last_saw_prey_frame": last_saw_prey_frame,
        "last_kill_frame": last_kill_frame,
        "death_cause": death_cause,
        "death_context": death_context,
        "end_reason": end_reason,
        "age_at_death": age_at_death,
        "predator_count_at_death": predator_count_at_death,
        "prey_count_at_death": prey_count_at_death,
        "depth_band_at_death": depth_band_at_death,
        "hunting_ground_frames": hunting_ground_frames,
        "refuge_frames": refuge_frames,
        "refuge_bonus_factor_sum": refuge_bonus_factor_sum,
        "kills_inside_refuge": kills_inside_refuge,
        "kills_outside_refuge": kills_outside_refuge,
        "died_inside_refuge": died_inside_refuge,
        "died_in_hunting_ground": died_in_hunting_ground,
        "death_zone_type": death_zone_type,
        "refuge_bonus_factor_at_death": refuge_bonus_factor_at_death,
        "local_predator_density_at_death": local_predator_density_at_death,
        "strategy_bucket_at_start": strategy_bucket_at_start,
        "strategy_bucket_at_end": strategy_bucket_at_end or strategy_bucket_at_start,
        "phenotype_modifiers_at_start": phenotype_modifiers_at_start or {
            "speed_mult": 1.0,
            "movement_cost_mult": 1.0,
            "metabolic_cost_mult": 1.0,
            "sense_radius_mult": 1.0,
            "food_efficiency_mult": 1.0,
            "reproduction_threshold_mult": 1.0,
            "predation_contact_mult": 1.0,
            "flee_agility_mult": 1.0,
        },
        "phenotype_modifiers_at_end": phenotype_modifiers_at_end or {
            "speed_mult": 1.0,
            "movement_cost_mult": 1.0,
            "metabolic_cost_mult": 1.0,
            "sense_radius_mult": 1.0,
            "food_efficiency_mult": 1.0,
            "reproduction_threshold_mult": 1.0,
            "predation_contact_mult": 1.0,
            "flee_agility_mult": 1.0,
        },
        "born_during_low_predator_rarity": born_during_low_predator_rarity,
    }


def _make_run(
    *,
    seed=12345,
    game_over=True,
    collapse_cause="Predators collapsed",
    final_sim_ticks=5000,
    final_survival_ticks=5000,
    final_predator_count=0,
    final_prey_count=60,
    tick_of_first_predator_zero=4000,
    predator_zero_ticks=1000,
    total_kills=25,
    completed_lives=None,
    active_lives=None,
):
    """Create a synthetic run result for testing."""
    completed_lives = completed_lives or []
    active_lives = active_lives or []
    return {
        "seed": seed,
        "scenario_id": "predator_prey_medium",
        "epistasis": "current",
        "max_ticks": 20000,
        "game_over": game_over,
        "collapse_cause": collapse_cause,
        "final_sim_ticks": final_sim_ticks,
        "final_survival_ticks": final_survival_ticks,
        "final_predator_count": final_predator_count,
        "final_prey_count": final_prey_count,
        "tick_of_first_predator_zero": tick_of_first_predator_zero,
        "predator_zero_ticks_at_end": predator_zero_ticks,
        "total_kills": total_kills,
        "species_counts": [{"step": 0, "predators": 15, "prey": 90}, {"step": final_sim_ticks, "predators": final_predator_count, "prey": final_prey_count}],
        "diagnostics": {
            "frame": final_sim_ticks,
            "base_threshold": 0.78,
            "predator_kill_energy_gain_cap": 0.30,
            "predator_hunt_sense_multiplier": 1.40,
            "predator_hunt_speed_multiplier": 0.70,
            "predator_contact_kill_distance_scale": 0.85,
            "completed_lives": completed_lives,
            "active_lives": active_lives,
            "events": {"births": [], "cosmic_flips_to_predator": [], "cosmic_flips_from_predator": []},
        },
        "stability": {},
        "epistasis_summary": {
            "enabled": True,
            "strength": 1.0,
            "top_strategy": "generalist",
            "top_strategy_share": 0.4,
            "strategy_counts": {},
            "average_modifiers": {},
        },
    }


class TestAggregationHelpers(unittest.TestCase):
    def test_safe_median_empty(self):
        self.assertIsNone(_safe_median([]))

    def test_safe_median_odd(self):
        self.assertEqual(_safe_median([1, 2, 3]), 2.0)

    def test_safe_median_even(self):
        self.assertEqual(_safe_median([1, 2, 3, 4]), 2.5)

    def test_safe_mean_empty(self):
        self.assertIsNone(_safe_mean([]))

    def test_safe_mean_values(self):
        self.assertAlmostEqual(_safe_mean([2.0, 4.0]), 3.0)

    def test_pct(self):
        self.assertAlmostEqual(_pct(3, 10), 30.0)
        self.assertAlmostEqual(_pct(0, 0), 0.0)

    def test_fmt_none(self):
        self.assertEqual(_fmt(None), "—")

    def test_fmt_float(self):
        self.assertEqual(_fmt(0.12345), "0.123")

    def test_fmt_int(self):
        self.assertEqual(_fmt(42), "42")

    def test_pct_fmt_none(self):
        self.assertEqual(_pct_fmt(None), "—")

    def test_classify_death_context_known(self):
        for ctx in ("old_age", "active_hunting", "after_failed_pursuit", "long_scarcity"):
            self.assertEqual(_classify_death_context(ctx), ctx)

    def test_classify_death_context_unknown(self):
        self.assertEqual(_classify_death_context("something_else"), "unknown")
        self.assertEqual(_classify_death_context(None), "unknown")

    def test_depth_band_name(self):
        self.assertEqual(_depth_band_name(0), "surface")
        self.assertEqual(_depth_band_name(1), "mid")
        self.assertEqual(_depth_band_name(2), "deep")
        self.assertEqual(_depth_band_name(None), "unknown")


class TestReportSections(unittest.TestCase):
    def test_section_a_run_summary(self):
        run = _make_run(seed=42, final_sim_ticks=5000, total_kills=30)
        rows = _section_a_run_summary([run])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["seed"], 42)
        self.assertEqual(rows[0]["total_kills"], 30)

    def test_section_b_predator_life_summary_empty(self):
        run = _make_run(completed_lives=[], active_lives=[])
        result = _section_b_predator_life_summary([run])
        self.assertEqual(result["predator_lives_started"], 0)

    def test_section_b_predator_life_summary_with_data(self):
        lives = [
            _make_life(life_id=1, kills=2, births_produced=1, highest_energy=0.9,
                        frames_observed=100, start_frame=0, end_frame=100,
                        peak_reached_threshold=True),
            _make_life(life_id=2, kills=0, births_produced=0, highest_energy=0.3,
                        frames_observed=80, start_frame=0, end_frame=80,
                        threshold_min=0.78, threshold_max=0.78,
                        closest_repro_check_gap=0.45, repro_check_reached_threshold=False),
        ]
        run = _make_run(completed_lives=lives)
        result = _section_b_predator_life_summary([run])
        self.assertEqual(result["predator_lives_started"], 2)
        self.assertEqual(result["completed_predator_lives"], 2)
        self.assertAlmostEqual(result["pct_with_zero_kills"], 50.0)

    def test_section_c_death_context_breakdown(self):
        lives = [
            _make_life(death_context="long_scarcity"),
            _make_life(death_context="long_scarcity"),
            _make_life(death_context="active_hunting"),
            _make_life(death_context="old_age"),
        ]
        run = _make_run(completed_lives=lives)
        result = _section_c_death_context_breakdown([run])
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["contexts"]["long_scarcity"], 2)
        self.assertEqual(result["contexts"]["active_hunting"], 1)
        self.assertEqual(result["contexts"]["old_age"], 1)

    def test_section_d_origin_breakdown(self):
        lives = [
            _make_life(origin="initial", kills=3, births_produced=1,
                       start_frame=0, end_frame=500),
            _make_life(origin="birth", kills=0, births_produced=0,
                       start_frame=100, end_frame=200),
            _make_life(origin="cosmic_flip", kills=1, births_produced=0,
                       start_frame=300, end_frame=600),
        ]
        run = _make_run(completed_lives=lives)
        result = _section_d_origin_breakdown([run])
        self.assertEqual(len(result), 3)
        initial_row = next(r for r in result if r["origin"] == "initial")
        self.assertEqual(initial_row["count"], 1)

    def test_section_e_reproduction_bottleneck(self):
        lives = [
            _make_life(kills=3, births_produced=1, peak_reached_threshold=True,
                        threshold_min=0.78, threshold_max=0.78,
                        closest_repro_check_gap=0.0),
            _make_life(kills=1, births_produced=0, peak_reached_threshold=True,
                        threshold_min=0.78, threshold_max=0.78,
                        closest_repro_check_gap=0.15, repro_check_reached_threshold=False),
        ]
        run = _make_run(completed_lives=lives)
        result = _section_e_reproduction_bottleneck([run])
        self.assertEqual(result["kills_but_no_births"], 1)  # second life
        self.assertEqual(result["threshold_reached_but_no_births"], 1)

    def test_section_f_prey_access(self):
        lives = [
            _make_life(frames_observed=200, frames_with_prey_sighted=50,
                        kills=3, cross_band_contact_misses=2,
                        refuge_frames=80, hunting_ground_frames=120,
                        kills_inside_refuge=2, kills_outside_refuge=1,
                        cross_band_misses_inside_refuge=1,
                        cross_band_misses_outside_refuge=1,
                        died_inside_refuge=True,
                        refuge_bonus_factor_at_death=0.55,
                        local_predator_density_at_death=2),
            _make_life(frames_observed=150, frames_with_prey_sighted=0,
                        kills=0, cross_band_contact_misses=0,
                        refuge_frames=0, hunting_ground_frames=20,
                        kills_inside_refuge=0, kills_outside_refuge=0,
                        cross_band_misses_inside_refuge=0,
                        cross_band_misses_outside_refuge=0,
                        died_inside_refuge=False,
                        refuge_bonus_factor_at_death=0.0,
                        local_predator_density_at_death=6),
        ]
        run = _make_run(completed_lives=lives)
        result = _section_f_prey_access([run])
        # median of [50/200=0.25, 0/150=0.0] = 0.125
        self.assertAlmostEqual(result["median_prey_sighting_share"], 0.125)
        self.assertEqual(result["kills_inside_refuge"], 2)
        self.assertEqual(result["cross_band_misses_inside_refuge"], 1)
        self.assertIn("mean_refuge_frames_per_life", result)

    def test_section_g_scarcity(self):
        lives = [
            _make_life(frames_observed=200, prey_scarce_frames=160,
                        death_context="long_scarcity"),
            _make_life(frames_observed=100, prey_scarce_frames=20,
                        death_context="active_hunting"),
        ]
        run = _make_run(completed_lives=lives)
        result = _section_g_scarcity([run])
        self.assertIsNotNone(result.get("median_prey_scarce_share"))

    def test_section_i_recommendations_long_scarcity(self):
        # More than 40% long_scarcity should trigger a recommendation
        section_c = {"contexts": {"long_scarcity": 8, "old_age": 2}, "total": 10}
        section_f = {"median_prey_sighting_share": 0.15, "cross_band_misses_per_kill": None}
        section_g = {"median_prey_scarce_share": 0.6}
        section_e = {"kills_but_no_births": 0, "threshold_reached_but_no_births": 0,
                     "total_predator_lives": 10}
        section_d = []
        recommendations = _section_i_recommendations(
            [_make_run()], section_c, section_f, section_g, section_e, section_d,
        )
        self.assertTrue(any("LONG SCARCITY" in r for r in recommendations))


class TestBuildAndRenderReport(unittest.TestCase):
    def test_build_report_and_render(self):
        lives = [
            _make_life(life_id=1, origin="initial", kills=2, births_produced=1,
                        start_frame=0, end_frame=500, highest_energy=0.85,
                        frames_observed=500, frames_with_prey_sighted=150,
                        prey_scarce_frames=300, cross_band_contact_misses=3,
                        threshold_min=0.78, threshold_max=0.78,
                        peak_reached_threshold=True, death_context="long_scarcity"),
            _make_life(life_id=2, origin="birth", kills=0, births_produced=0,
                        start_frame=200, end_frame=400, highest_energy=0.4,
                        frames_observed=200, frames_with_prey_sighted=10,
                        prey_scarce_frames=180, death_context="after_failed_pursuit"),
        ]
        run = _make_run(completed_lives=lives, total_kills=2)
        report = build_report([run])

        # Verify report structure
        self.assertIn("section_a_run_summary", report)
        self.assertIn("section_b_predator_life_summary", report)
        self.assertIn("section_c_death_context_breakdown", report)
        self.assertIn("section_d_origin_breakdown", report)
        self.assertIn("section_e_reproduction_bottleneck", report)
        self.assertIn("section_f_prey_access", report)
        self.assertIn("section_g_scarcity", report)
        self.assertIn("section_h_epistasis_body_plan", report)
        self.assertIn("section_i_recommendations", report)

        # Verify markdown renders
        md = render_markdown(report)
        self.assertIn("# Predator Collapse Diagnostics Report", md)
        self.assertIn("## A. Run Summary", md)
        self.assertIn("## I. Recommendations", md)
        self.assertIn("Kills inside refuge", md)


if __name__ == "__main__":
    unittest.main()
