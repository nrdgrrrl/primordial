from __future__ import annotations

import unittest

from tools import predator_contact_forensics as forensics


class PredatorContactForensicsTests(unittest.TestCase):
    def test_parse_args_parses_seed_list_and_paths(self) -> None:
        args = forensics.parse_args(
            [
                "--seeds",
                "1, 2,3",
                "--max-ticks",
                "123",
                "--output",
                "run_logs/out.md",
                "--json",
                "run_logs/out.json",
            ]
        )
        self.assertEqual(args.seeds, [1, 2, 3])
        self.assertEqual(args.max_ticks, 123)
        self.assertEqual(args.output, "run_logs/out.md")
        self.assertEqual(args.json, "run_logs/out.json")

    def test_follow_window_counts_once_per_event(self) -> None:
        aggregate = forensics.make_empty_aggregate()
        pending = [
            forensics.PendingNearContactEvent(frame=10),
            forensics.PendingNearContactEvent(frame=12),
        ]

        forensics._increment_follow_counts(
            aggregate,
            pending,
            current_frame=13,
            kill_delta=1,
        )
        self.assertEqual(aggregate["near_contact_followed_by_kill_1f"], 1)
        self.assertEqual(aggregate["near_contact_followed_by_kill_3f"], 2)
        self.assertEqual(aggregate["near_contact_followed_by_kill_5f"], 2)
        self.assertEqual(aggregate["near_contact_followed_by_kill_10f"], 2)

        forensics._increment_follow_counts(
            aggregate,
            pending,
            current_frame=14,
            kill_delta=1,
        )
        self.assertEqual(aggregate["near_contact_followed_by_kill_1f"], 1)
        self.assertEqual(aggregate["near_contact_followed_by_kill_3f"], 2)
        self.assertEqual(aggregate["near_contact_followed_by_kill_5f"], 2)
        self.assertEqual(aggregate["near_contact_followed_by_kill_10f"], 2)

    def test_aggregate_runs_sums_and_diagnoses_radius_timing(self) -> None:
        runs = [
            {
                "seed": 1,
                "final_sim_ticks": 100,
                "final_predator_count": 0,
                "final_prey_count": 10,
                "total_kills": 2,
                "predator_zero_ever": True,
                "prey_zero_ever": False,
                "aggregate": {
                    **forensics.make_empty_aggregate(),
                    "total_ticks": 100,
                    "total_kills": 2,
                    "near_contact_events": 20,
                    "same_depth_near_contact_events": 18,
                    "cross_depth_near_contact_events": 2,
                    "same_depth_contact_radius_events": 4,
                    "cross_depth_contact_radius_events": 0,
                    "near_contact_followed_by_kill_1f": 1,
                    "near_contact_followed_by_kill_3f": 2,
                    "near_contact_followed_by_kill_5f": 2,
                    "near_contact_followed_by_kill_10f": 3,
                    "same_depth_just_outside_contact_events": 14,
                },
            }
        ]
        aggregate = forensics.aggregate_runs(runs)
        self.assertEqual(aggregate["total_ticks"], 100)
        self.assertEqual(aggregate["predator_zero_runs"], 1)
        self.assertEqual(aggregate["prey_zero_runs"], 0)
        self.assertEqual(aggregate["final_predator_counts"], [0])
        self.assertEqual(aggregate["final_prey_counts"], [10])
        self.assertEqual(aggregate["primary_bottleneck"], "radius/timing gap")

    def test_markdown_report_includes_core_questions(self) -> None:
        aggregate = {
            **forensics.make_empty_aggregate(),
            **{
                "total_ticks": 10,
                "total_kills": 1,
                "near_contact_events": 4,
                "same_depth_near_contact_events": 3,
                "cross_depth_near_contact_events": 1,
                "same_depth_contact_radius_events": 1,
                "cross_depth_contact_radius_events": 0,
                "near_contact_followed_by_kill_1f": 1,
                "near_contact_followed_by_kill_3f": 2,
                "near_contact_followed_by_kill_5f": 2,
                "near_contact_followed_by_kill_10f": 2,
                "predator_zero_runs": 1,
                "prey_zero_runs": 0,
                "final_predator_counts": [0],
                "final_prey_counts": [5],
                "share_near_contact_followed_by_kill_1f": 0.25,
                "share_near_contact_followed_by_kill_3f": 0.5,
                "share_near_contact_followed_by_kill_5f": 0.5,
                "share_near_contact_followed_by_kill_10f": 0.5,
                "share_same_depth_near_contact": 0.75,
                "share_cross_depth_near_contact": 0.25,
                "share_same_depth_near_inside_contact_radius": 1 / 3,
                "share_cross_depth_near_inside_contact_radius": 0.0,
                "share_same_depth_just_outside_contact": 2 / 3,
                "share_near_contact_with_target_switch": 0.0,
                "share_near_contact_with_moving_away": 0.0,
                "mean_nearest_contact_ratio": 1.2,
                "primary_bottleneck": "radius/timing gap",
                "recommended_next_change": "Investigate a very small same-depth contact-conversion adjustment first.",
                "predator_zero_ever_runs": 1,
                "prey_zero_ever_runs": 0,
            },
        }
        report = forensics.build_markdown_report(
            seeds=[1],
            scenario_id="predator_prey_medium",
            max_ticks=10,
            runs=[
                {
                    "seed": 1,
                    "final_sim_ticks": 10,
                    "final_predator_count": 0,
                    "final_prey_count": 5,
                    "total_kills": 1,
                    "predator_zero_ever": True,
                    "aggregate": aggregate,
                }
            ],
            aggregate=aggregate,
        )
        self.assertIn("Are predators usually near prey but in the wrong depth?", report)
        self.assertIn("Are they same-depth near prey but just outside contact radius?", report)
        self.assertIn("Recommended Next Change", report)


if __name__ == "__main__":
    unittest.main()
