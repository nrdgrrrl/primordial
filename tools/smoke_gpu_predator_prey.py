#!/usr/bin/env python3
"""Small live-display smoke for the predator/prey GPU backend."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from primordial.rendering import (
    create_renderer,
    display_flags_for_settings,
    renderer_backend_name,
    renderer_gpu_info,
    save_renderer_screenshot,
)
from primordial.settings import Settings
from primordial.simulation import Simulation


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=640, help="Window width.")
    parser.add_argument("--height", type=int, default=360, help="Window height.")
    parser.add_argument("--seed", type=int, default=12345, help="Simulation seed.")
    parser.add_argument("--ticks", type=int, default=10, help="Ticks to advance.")
    parser.add_argument(
        "--screenshot",
        type=Path,
        default=Path("build") / "gpu_predator_prey_smoke.png",
        help="Screenshot output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = Settings()
    settings.sim_mode = "predator_prey"
    settings.render_backend = "gpu"
    settings.fullscreen = False
    settings.show_hud = False

    pygame.init()
    try:
        screen = pygame.display.set_mode(
            (max(64, args.width), max(64, args.height)),
            display_flags_for_settings(settings),
        )
        simulation = Simulation(
            screen.get_width(),
            screen.get_height(),
            settings,
            seed=args.seed,
        )
        renderer = create_renderer(screen, settings, debug=False)
        renderer.resize(simulation.width, simulation.height, screen=screen)
        backend = renderer_backend_name(renderer)
        if backend != "gpu":
            raise RuntimeError(
                f"GPU smoke expected backend 'gpu' but got '{backend}'. "
                f"gpu_info={renderer_gpu_info(renderer)}"
            )

        metrics = {}
        for _ in range(max(1, args.ticks)):
            simulation.step()
            metrics = renderer.draw(simulation)
            pygame.display.flip()
            pygame.event.pump()

        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        save_renderer_screenshot(renderer, args.screenshot)
        screenshot_ok = args.screenshot.exists() and args.screenshot.stat().st_size > 0
        if not screenshot_ok:
            raise RuntimeError(f"Expected screenshot at {args.screenshot} was not created.")

        loaded = pygame.image.load(str(args.screenshot))
        required_metric_keys = (
            "snapshot_ms",
            "trails_ms",
            "creatures_ms",
            "draw_total_ms",
        )
        missing_metric_keys = [
            key for key in required_metric_keys if key not in metrics
        ]
        if missing_metric_keys:
            raise RuntimeError(
                "GPU smoke missing render timing keys: "
                + ", ".join(sorted(missing_metric_keys))
            )

        payload = {
            "backend": backend,
            "gpu_info": renderer_gpu_info(renderer),
            "screenshot": str(args.screenshot),
            "screenshot_size": [loaded.get_width(), loaded.get_height()],
            "ticks": max(1, args.ticks),
            "timing_ms": {
                "snapshot_ms": metrics["snapshot_ms"],
                "trails_ms": metrics["trails_ms"],
                "creatures_ms": metrics["creatures_ms"],
                "render_ms": metrics["draw_total_ms"],
            },
            "notes": [
                "This is a smoke guardrail, not a universal performance guarantee.",
                "It only proves that the GPU backend initialized, rendered, and produced output on this machine.",
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
