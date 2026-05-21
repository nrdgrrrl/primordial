from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from primordial.runtime import create_fixed_step_loop_state
from primordial.runtime.settings_actions import (
    SettingsActionContext,
    handle_settings_overlay_event,
)


class FakeScreen:
    def __init__(self, flags: int = 0) -> None:
        self._flags = flags

    def get_flags(self) -> int:
        return self._flags


class FakeSettingsOverlay:
    def __init__(self, action: str | None) -> None:
        self.action = action
        self.fade_dir = -1
        self.pending: dict[str, object] = {}
        self.sync_calls = 0
        self.snapshot_paths: list[str] = []
        self.statuses: list[tuple[str, bool]] = []

    def handle_event(self, event: object) -> str | None:
        return self.action

    def sync_from_settings(self) -> None:
        self.sync_calls += 1

    def set_snapshot_path(self, path: str) -> None:
        self.snapshot_paths.append(path)

    def set_snapshot_status(self, message: str, *, is_error: bool = False) -> None:
        self.statuses.append((message, is_error))

    def close(self) -> None:
        self.fade_dir = -1


class FakeRenderer:
    def __init__(
        self,
        action: str | None,
        *,
        flags: int = 0,
        backend_name: str = "pygame",
    ) -> None:
        self.settings_overlay = FakeSettingsOverlay(action)
        self.screen = FakeScreen(flags)
        self.backend_name = backend_name
        self.width = 1280
        self.height = 720
        self.theme_changes: list[str] = []
        self.mode_changes: list[str] = []
        self.reset_runtime_state = mock.Mock()
        self.resize = mock.Mock()
        self.help_overlay = SimpleNamespace(status_message="")
        self.tutorial_overlay = SimpleNamespace(
            wants_simulation_paused=mock.Mock(return_value=True),
        )
        self.open_help_overlay = mock.Mock()
        self.open_tutorial_overlay = mock.Mock()

    def set_theme(self, theme: str) -> None:
        self.theme_changes.append(theme)

    def set_mode(self, mode: str) -> None:
        self.mode_changes.append(mode)


class FakeSimulation:
    def __init__(self) -> None:
        self.paused = True
        self.width = 1280
        self.height = 720
        self.run_logger = None
        self.milestone_logger = None
        self.reset_predator_prey_adaptive_tuning = mock.Mock()
        self.restart_predator_prey_run = mock.Mock()

    def set_predator_prey_run_logger(self, run_logger: object) -> None:
        self.run_logger = run_logger

    def set_predator_prey_milestone_logger(self, milestone_logger: object) -> None:
        self.milestone_logger = milestone_logger


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "sim_mode": "energy",
        "visual_theme": "ocean",
        "fullscreen": False,
        "render_backend": "pygame",
        "target_fps": 60,
        "mode_params": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _context(
    *,
    action: str | None,
    settings: SimpleNamespace | None = None,
    simulation: FakeSimulation | None = None,
    renderer: FakeRenderer | None = None,
    runtime_loop=None,
    active_snapshot_path: Path | None = None,
    previous_mode: str = "energy",
    csv_run_logger: object | None = None,
    milestone_logger: object | None = None,
) -> SettingsActionContext:
    settings = settings or _settings()
    simulation = simulation or FakeSimulation()
    renderer = renderer or FakeRenderer(action)
    runtime_loop = runtime_loop or create_fixed_step_loop_state(settings)
    active_snapshot_path = active_snapshot_path or Path("world_snapshot.json")
    return SettingsActionContext(
        settings=settings,
        simulation=simulation,
        renderer=renderer,
        runtime_loop=runtime_loop,
        active_snapshot_path=active_snapshot_path,
        previous_mode=previous_mode,
        debug=False,
        csv_run_logger=csv_run_logger,
        milestone_logger=milestone_logger,
    )


class SettingsActionTests(unittest.TestCase):
    def test_reset_action_rebuilds_runtime_config_and_updates_renderer(self) -> None:
        settings = _settings(
            visual_theme="petri",
            mode_params={"energy": {"simulation_tick_hz": 30}},
        )
        simulation = FakeSimulation()
        runtime_loop = create_fixed_step_loop_state(_settings())
        runtime_loop.accumulator_seconds = 5.0
        renderer = FakeRenderer("reset")
        context = _context(
            action="reset",
            settings=settings,
            simulation=simulation,
            renderer=renderer,
            runtime_loop=runtime_loop,
            previous_mode="energy",
        )

        result = handle_settings_overlay_event(object(), context)

        self.assertFalse(result.begin_mode_transition)
        self.assertIs(result.simulation, simulation)
        self.assertIs(result.renderer, renderer)
        self.assertFalse(simulation.paused)
        self.assertAlmostEqual(runtime_loop.config.fixed_timestep_seconds, 1.0 / 30.0)
        self.assertEqual(runtime_loop.accumulator_seconds, 0.0)
        self.assertEqual(renderer.theme_changes, ["petri"])
        self.assertEqual(renderer.mode_changes, ["energy"])
        self.assertEqual(renderer.settings_overlay.sync_calls, 1)
        self.assertEqual(
            renderer.settings_overlay.statuses[-1],
            ("Reset settings to defaults.", False),
        )

    def test_reset_action_invokes_display_change_path_when_fullscreen_changes(self) -> None:
        settings = _settings(fullscreen=True)
        renderer = FakeRenderer("reset", flags=0)
        context = _context(action="reset", settings=settings, renderer=renderer)

        with mock.patch(
            "primordial.runtime.settings_actions._apply_display_mode",
        ) as apply_display_mode:
            result = handle_settings_overlay_event(object(), context)

        self.assertFalse(result.begin_mode_transition)
        apply_display_mode.assert_called_once_with(
            settings,
            context.simulation,
            renderer,
        )

    def test_reset_action_invokes_backend_recreation_when_backend_changes(self) -> None:
        settings = _settings(
            sim_mode="predator_prey",
            render_backend="gpu",
            visual_theme="chaotic",
        )
        old_renderer = FakeRenderer("reset", backend_name="pygame")
        new_renderer = FakeRenderer(None, backend_name="gpu")
        context = _context(
            action="reset",
            settings=settings,
            renderer=old_renderer,
            previous_mode="predator_prey",
        )

        with mock.patch(
            "primordial.runtime.settings_actions._desired_renderer_backend_name",
            return_value="gpu",
        ), mock.patch(
            "primordial.runtime.settings_actions._recreate_renderer_for_backend",
            return_value=new_renderer,
        ) as recreate_renderer:
            result = handle_settings_overlay_event(object(), context)

        self.assertIs(result.renderer, new_renderer)
        recreate_renderer.assert_called_once_with(
            settings,
            context.simulation,
            debug=False,
            snapshot_path=context.active_snapshot_path,
        )
        self.assertEqual(new_renderer.theme_changes, ["chaotic"])
        self.assertEqual(new_renderer.mode_changes, ["predator_prey"])
        self.assertEqual(new_renderer.settings_overlay.sync_calls, 1)

    def test_reset_action_requests_mode_transition_when_mode_changed(self) -> None:
        settings = _settings(sim_mode="energy")
        simulation = FakeSimulation()
        context = _context(
            action="reset",
            settings=settings,
            simulation=simulation,
            previous_mode="predator_prey",
        )

        result = handle_settings_overlay_event(object(), context)

        self.assertTrue(result.begin_mode_transition)
        self.assertEqual(result.previous_mode, "energy")
        self.assertTrue(simulation.paused)

    def test_load_snapshot_reattaches_existing_loggers(self) -> None:
        csv_run_logger = object()
        milestone_logger = object()
        loaded_simulation = FakeSimulation()
        renderer = FakeRenderer("load_snapshot")
        runtime_loop = create_fixed_step_loop_state(_settings())
        runtime_loop.accumulator_seconds = 3.0

        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "world_snapshot.json"
            snapshot_path.write_text("{}", encoding="utf-8")
            context = _context(
                action="load_snapshot",
                renderer=renderer,
                runtime_loop=runtime_loop,
                active_snapshot_path=snapshot_path,
                csv_run_logger=csv_run_logger,
                milestone_logger=milestone_logger,
            )

            with mock.patch(
                "primordial.runtime.settings_actions.load_snapshot",
                return_value=loaded_simulation,
            ) as load_snapshot, mock.patch(
                "primordial.runtime.settings_actions._swap_loaded_simulation",
                return_value=loaded_simulation,
            ):
                result = handle_settings_overlay_event(object(), context)

        load_snapshot.assert_called_once_with(
            snapshot_path,
            settings=context.settings,
        )
        self.assertIs(result.simulation, loaded_simulation)
        self.assertIs(loaded_simulation.run_logger, csv_run_logger)
        self.assertIs(loaded_simulation.milestone_logger, milestone_logger)
        self.assertTrue(loaded_simulation.paused)
        self.assertEqual(runtime_loop.accumulator_seconds, 0.0)
        self.assertEqual(renderer.settings_overlay.sync_calls, 1)
        self.assertEqual(
            renderer.settings_overlay.statuses[-1],
            ("Loaded snapshot from world_snapshot.json", False),
        )

    def test_save_snapshot_updates_active_path_and_overlay_status(self) -> None:
        renderer = FakeRenderer("save_snapshot")
        context = _context(action="save_snapshot", renderer=renderer)
        saved_path = Path("saved_snapshot.json")

        with mock.patch(
            "primordial.runtime.settings_actions.save_snapshot",
            return_value=saved_path,
        ) as save_snapshot:
            result = handle_settings_overlay_event(object(), context)

        save_snapshot.assert_called_once_with(
            context.simulation,
            context.active_snapshot_path,
        )
        self.assertEqual(result.active_snapshot_path, saved_path)
        self.assertEqual(renderer.settings_overlay.snapshot_paths, [str(saved_path)])
        self.assertEqual(
            renderer.settings_overlay.statuses[-1],
            ("Saved snapshot to saved_snapshot.json", False),
        )

    def test_help_action_opens_in_app_help_overlay(self) -> None:
        settings = _settings(fullscreen=False)
        renderer = FakeRenderer("help")
        runtime_loop = create_fixed_step_loop_state(settings)
        runtime_loop.accumulator_seconds = 2.0
        context = _context(
            action="help",
            settings=settings,
            renderer=renderer,
            runtime_loop=runtime_loop,
        )

        result = handle_settings_overlay_event(object(), context)

        self.assertIs(result.renderer, renderer)
        renderer.open_help_overlay.assert_called_once_with()
        self.assertEqual(runtime_loop.accumulator_seconds, 0.0)
        self.assertEqual(
            renderer.settings_overlay.statuses[-1],
            ("Opened in-app predator-prey guide.", False),
        )

    def test_tutorial_action_opens_tutorial_and_pauses_simulation(self) -> None:
        settings = _settings(fullscreen=False)
        simulation = FakeSimulation()
        simulation.paused = False
        renderer = FakeRenderer("tutorial")
        runtime_loop = create_fixed_step_loop_state(settings)
        runtime_loop.accumulator_seconds = 2.0
        context = _context(
            action="tutorial",
            settings=settings,
            simulation=simulation,
            renderer=renderer,
            runtime_loop=runtime_loop,
        )

        result = handle_settings_overlay_event(object(), context)

        self.assertIs(result.renderer, renderer)
        renderer.open_tutorial_overlay.assert_called_once_with(
            forced=True,
            previous_paused=False,
        )
        self.assertTrue(simulation.paused)
        self.assertEqual(runtime_loop.accumulator_seconds, 0.0)

    def test_reset_predator_prey_dials_preserves_existing_branch_behavior(self) -> None:
        settings = _settings(sim_mode="predator_prey")
        simulation = FakeSimulation()
        renderer = FakeRenderer("reset_predator_prey_dials")
        runtime_loop = create_fixed_step_loop_state(settings)
        runtime_loop.accumulator_seconds = 4.0
        context = _context(
            action="reset_predator_prey_dials",
            settings=settings,
            simulation=simulation,
            renderer=renderer,
            runtime_loop=runtime_loop,
        )

        with mock.patch(
            "primordial.runtime.settings_actions._save_predator_prey_tuning_state",
        ) as save_tuning_state:
            result = handle_settings_overlay_event(object(), context)

        self.assertIs(result.simulation, simulation)
        simulation.reset_predator_prey_adaptive_tuning.assert_called_once_with()
        simulation.restart_predator_prey_run.assert_called_once_with()
        renderer.reset_runtime_state.assert_called_once_with()
        save_tuning_state.assert_called_once_with(settings, simulation)
        self.assertEqual(runtime_loop.accumulator_seconds, 0.0)
        self.assertEqual(
            renderer.settings_overlay.statuses[-1],
            ("Reset predator-prey dials to baseline and cleared max ticks.", False),
        )


if __name__ == "__main__":
    unittest.main()
