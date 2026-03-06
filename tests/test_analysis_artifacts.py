from __future__ import annotations

import unittest

from primordial.analysis import (
    compare_history_artifacts,
    format_history_summary,
    generate_history_artifact,
)


class AnalysisArtifactTests(unittest.TestCase):
    def test_history_artifact_has_shared_core_across_representative_modes(self) -> None:
        expected_shared_keys = {
            "step",
            "generation",
            "population",
            "food_count",
            "lineages",
            "strategies",
            "zone_occupancy",
            "dominant_zone",
        }

        energy = generate_history_artifact(
            "energy_medium",
            steps=30,
            sample_every=10,
            seed=111,
        )
        predator_prey = generate_history_artifact(
            "predator_prey_medium",
            steps=30,
            sample_every=10,
            seed=222,
        )
        boids = generate_history_artifact(
            "boids_dense",
            steps=30,
            sample_every=10,
            seed=333,
        )

        self.assertEqual(energy["artifact"]["kind"], "primordial.history")
        self.assertEqual(set(energy["series"][0]), expected_shared_keys)
        self.assertIn("species", predator_prey["series"][0])
        self.assertNotIn("flocks", predator_prey["series"][0])
        self.assertIn("flocks", boids["series"][0])
        self.assertNotIn("species", boids["series"][0])
        self.assertEqual(energy["summary"]["sample_steps"], [0, 10, 20, 30])
        self.assertGreaterEqual(energy["summary"]["lineage_history"]["active_end"], 1)
        self.assertIn("open_water", energy["summary"]["zone_history"]["mean_counts"])

    def test_same_seed_history_is_exactly_repeatable(self) -> None:
        left = generate_history_artifact(
            "energy_medium",
            steps=45,
            sample_every=15,
            seed=424242,
        )
        right = generate_history_artifact(
            "energy_medium",
            steps=45,
            sample_every=15,
            seed=424242,
        )

        self.assertEqual(left, right)

    def test_same_seed_comparison_report_marks_exact_match_and_zero_deltas(self) -> None:
        left = generate_history_artifact(
            "energy_medium",
            steps=45,
            sample_every=15,
            seed=424242,
        )
        right = generate_history_artifact(
            "energy_medium",
            steps=45,
            sample_every=15,
            seed=424242,
        )

        report = compare_history_artifacts(left, right)

        self.assertEqual(report["report"]["kind"], "primordial.history_compare")
        self.assertTrue(report["comparable"]["scenario_id_match"])
        self.assertTrue(report["comparable"]["mode_match"])
        self.assertTrue(report["comparable"]["sample_steps_match"])
        self.assertTrue(report["determinism"]["same_seed"])
        self.assertTrue(report["determinism"]["exact_match"])
        self.assertEqual(report["delta"]["population_end"], 0)
        self.assertEqual(report["delta"]["lineages_active_end"], 0)
        self.assertEqual(report["delta"]["dominant_zone_switches"], 0)
        self.assertTrue(report["delta"]["dominant_zone_end_match"])

    def test_history_summary_formatter_emits_key_lines(self) -> None:
        history = generate_history_artifact(
            "predator_prey_medium",
            steps=30,
            sample_every=10,
            seed=5150,
        )

        text = format_history_summary(history)

        self.assertIn("Scenario: predator_prey_medium", text)
        self.assertIn("Dominant zone:", text)
        self.assertIn("Species end:", text)


if __name__ == "__main__":
    unittest.main()
