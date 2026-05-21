from __future__ import annotations

import unittest
from unittest.mock import patch

from primordial.utils.cli import (
    format_runtime_help,
    parse_runtime_args,
    should_print_runtime_help,
)
from primordial.utils.screensaver import ScreensaverArgs, parse_screensaver_args


class RuntimeCliTests(unittest.TestCase):
    def test_help_flags_are_detected(self) -> None:
        self.assertTrue(should_print_runtime_help(["--help"]))
        self.assertTrue(should_print_runtime_help(["-h"]))
        self.assertFalse(should_print_runtime_help(["/s"]))
        self.assertFalse(should_print_runtime_help(["--mode", "energy"]))

    def test_help_text_lists_runtime_options_and_screensaver_args(self) -> None:
        help_text = format_runtime_help()
        normalized_help = " ".join(help_text.split())

        self.assertIn("usage: primordial", help_text)
        self.assertIn("Primordial evolutionary screensaver and simulation.", help_text)
        for token in (
            "-h, --help",
            "--debug",
            "--profile",
            "--mode MODE",
            "--theme THEME",
            "--load PATH",
            "--save PATH",
            "--log KIND",
            "--milestone-log PATH",
            "--tutorial",
            "--show-tutorial",
            "/s",
            "/p HWND",
            "/c",
            "energy, predator_prey, boids, drift",
            "ocean, petri, geometric, chaotic",
        ):
            self.assertIn(token, normalized_help)

    def test_runtime_parser_remains_tolerant_of_unknown_args(self) -> None:
        args = parse_runtime_args(["--debug", "/s", "--unknown", "--mode", "energy"])

        self.assertTrue(args.debug)
        self.assertEqual(args.mode, "energy")

    def test_runtime_parser_still_parses_supported_options(self) -> None:
        args = parse_runtime_args(
            [
                "--profile",
                "--mode",
                "predator_prey",
                "--theme",
                "ocean",
                "--load",
                "world.toml",
                "--save",
                "out.toml",
                "--log=csv",
                "--milestone-log",
                "milestones.yml",
                "--show-tutorial",
            ]
        )

        self.assertTrue(args.profile)
        self.assertEqual(args.mode, "predator_prey")
        self.assertEqual(args.theme, "ocean")
        self.assertEqual(args.load, "world.toml")
        self.assertEqual(args.save, "out.toml")
        self.assertEqual(args.log, "csv")
        self.assertEqual(args.milestone_log, "milestones.yml")
        self.assertTrue(args.tutorial)


class ScreensaverCliTests(unittest.TestCase):
    def test_screensaver_args_are_unchanged(self) -> None:
        with patch("sys.argv", ["primordial", "/s"]):
            self.assertEqual(parse_screensaver_args(), ScreensaverArgs(mode="screensaver"))
