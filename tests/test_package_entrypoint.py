from __future__ import annotations

import os
import runpy
import sys
import types
import unittest
from unittest.mock import patch

from primordial.utils.cli import RuntimeArgs
from primordial.utils.screensaver import ScreensaverArgs


class PackageEntrypointTests(unittest.TestCase):
    def test_module_entrypoint_invokes_main_with_parsed_args(self) -> None:
        calls: list[tuple[ScreensaverArgs, RuntimeArgs]] = []
        fake_main_module = types.ModuleType("primordial.main")
        fake_main_module.main = lambda scr_args, runtime_args: calls.append(  # type: ignore[attr-defined]
            (scr_args, runtime_args)
        )
        scr_args = ScreensaverArgs(mode="normal")
        runtime_args = RuntimeArgs(mode="predator_prey", milestone_log="milestone.yml")

        with (
            patch("primordial.utils.screensaver.parse_screensaver_args", return_value=scr_args),
            patch("primordial.utils.cli.parse_runtime_args", return_value=runtime_args),
            patch.dict(sys.modules, {"primordial.main": fake_main_module}, clear=False),
            patch.dict(os.environ, {}, clear=True),
        ):
            runpy.run_module("primordial", run_name="__main__", alter_sys=True)

        self.assertEqual(calls, [(scr_args, runtime_args)])
        self.assertNotIn("SDL_WINDOWID", os.environ)

    def test_module_entrypoint_sets_preview_window_id_before_launch(self) -> None:
        calls: list[tuple[ScreensaverArgs, RuntimeArgs]] = []
        fake_main_module = types.ModuleType("primordial.main")
        fake_main_module.main = lambda scr_args, runtime_args: calls.append(  # type: ignore[attr-defined]
            (scr_args, runtime_args)
        )
        scr_args = ScreensaverArgs(mode="preview", preview_hwnd=123)
        runtime_args = RuntimeArgs()

        with (
            patch("primordial.utils.screensaver.parse_screensaver_args", return_value=scr_args),
            patch("primordial.utils.cli.parse_runtime_args", return_value=runtime_args),
            patch.dict(sys.modules, {"primordial.main": fake_main_module}, clear=False),
            patch.dict(os.environ, {}, clear=True),
        ):
            runpy.run_module("primordial", run_name="__main__", alter_sys=True)
            self.assertEqual(os.environ.get("SDL_WINDOWID"), "123")

        self.assertEqual(calls, [(scr_args, runtime_args)])
