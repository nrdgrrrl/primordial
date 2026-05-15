#!/usr/bin/env python3
"""Compare predator/prey ecology outcomes under pygame vs gpu backends.

This is a fixed-seed, fixed-tick parity check. It does not compare wall-clock
timing. The purpose is to verify that choosing the render backend does not
change the simulation outcome or contaminate the simulation RNG sequence.

Requires a live display and a working OpenGL path for the GPU variant.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

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
)
from primordial.scenarios import build_settings_for_scenario, list_scenarios
from primordial.settings import Settings
from primordial.simulation import Simulation


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        default="predator_prey_medium",
        choices=list_scenarios(),
        help="Predator/prey scenario to run.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override scenario seed.",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=1200,
        help="Simulation ticks to execute per backend.",
    )
    parser.add_argument(
        "--render-every",
        type=int,
        default=3,
        help="Render cadence in simulation ticks.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )
    return parser.parse_args()


def _genome_tuple(genome: Any) -> tuple[float, ...]:
    return (
        round(float(genome.speed), 6),
        round(float(genome.size), 6),
        round(float(genome.sense_radius), 6),
        round(float(genome.aggression), 6),
        round(float(genome.hue), 6),
        round(float(genome.saturation), 6),
        round(float(genome.efficiency), 6),
        round(float(genome.complexity), 6),
        round(float(genome.symmetry), 6),
        round(float(genome.stroke_scale), 6),
        round(float(genome.appendages), 6),
        round(float(genome.rotation_speed), 6),
        round(float(genome.motion_style), 6),
        round(float(genome.longevity), 6),
        round(float(genome.conformity), 6),
        round(float(genome.depth_preference), 6),
    )


def _digest_items(items: list[tuple[Any, ...]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(items):
        digest.update(json.dumps(item, separators=(",", ":"), default=str).encode("utf-8"))
    return digest.hexdigest()


def _rng_digest() -> str:
    return hashlib.sha256(repr(random.getstate()).encode("utf-8")).hexdigest()


def _creature_digest(simulation: Simulation) -> str:
    items = [
        (
            creature.lineage_id,
            creature.species,
            round(float(creature.x), 6),
            round(float(creature.y), 6),
            round(float(creature.vx), 6),
            round(float(creature.vy), 6),
            round(float(creature.energy), 6),
            int(creature.age),
            int(creature.depth_band),
            int(creature.flock_id),
            round(float(creature.rotation_angle), 6),
            round(float(creature.recent_animal_energy), 6),
            int(creature.satiety_ticks_remaining),
            tuple((round(float(x), 6), round(float(y), 6)) for x, y in creature.trail),
            _genome_tuple(creature.genome),
        )
        for creature in simulation.creatures
    ]
    return _digest_items(items)


def _food_digest(simulation: Simulation) -> str:
    items = [
        (
            round(float(food.x), 6),
            round(float(food.y), 6),
            int(food.depth_band),
            round(float(food.energy), 6),
            round(float(food.twinkle_phase), 6),
        )
        for food in simulation.food_manager.particles
    ]
    return _digest_items(items)


def _sanitize_observability(snapshot: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(snapshot, sort_keys=True, default=str))


def _sanitize_stability(snapshot: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = (
        "sim_ticks",
        "survival_ticks",
        "rolling_average_survival_ticks",
        "highest_survival_ticks",
        "current_seed",
        "game_over_active",
        "collapse_predators",
        "collapse_prey",
        "collapse_cause",
    )
    return {
        key: json.loads(json.dumps(snapshot.get(key), sort_keys=True, default=str))
        for key in allowed_keys
    }


def _capture_result(
    backend: str,
    simulation: Simulation,
    *,
    ticks: int,
) -> dict[str, Any]:
    predator_count, prey_count = simulation.get_species_counts()
    return {
        "backend": backend,
        "ticks_requested": ticks,
        "sim_frame": int(simulation._frame),  # noqa: SLF001
        "population": int(simulation.population),
        "predator_count": int(predator_count),
        "prey_count": int(prey_count),
        "food_count": int(simulation.food_count),
        "generation": int(simulation.generation),
        "total_births": int(simulation.total_births),
        "total_deaths": int(simulation.total_deaths),
        "predation_kill_count": int(simulation.predation_kill_count),
        "observability": _sanitize_observability(simulation.build_observability_snapshot()),
        "stability": _sanitize_stability(simulation.get_predator_prey_stability_stats()),
        "creature_digest": _creature_digest(simulation),
        "food_digest": _food_digest(simulation),
        "rng_digest": _rng_digest(),
    }


def _build_backend_settings(scenario_id: str, backend: str) -> tuple[Any, Settings]:
    scenario, settings = build_settings_for_scenario(scenario_id)
    settings = copy.deepcopy(settings)
    settings.fullscreen = False
    settings.show_hud = False
    settings.render_backend = backend
    return scenario, settings


def _run_backend(
    scenario_id: str,
    backend: str,
    *,
    seed: int,
    ticks: int,
    render_every: int,
) -> dict[str, Any]:
    scenario, settings = _build_backend_settings(scenario_id, backend)
    random.seed(seed)

    pygame.init()
    try:
        screen = pygame.display.set_mode(
            (scenario.width, scenario.height),
            display_flags_for_settings(settings),
        )
        simulation = Simulation(
            scenario.width,
            scenario.height,
            settings,
            seed=seed,
        )
        renderer = create_renderer(screen, settings, debug=False)
        renderer.resize(simulation.width, simulation.height, screen=screen)
        actual_backend = renderer_backend_name(renderer)
        if actual_backend != backend:
            raise RuntimeError(
                f"Expected backend '{backend}' but got '{actual_backend}'. "
                f"gpu_info={renderer_gpu_info(renderer)}"
            )

        for tick_index in range(ticks):
            simulation.step()
            if (tick_index + 1) % render_every == 0:
                renderer.draw(simulation)
                pygame.display.flip()
                pygame.event.pump()

        if ticks % render_every:
            renderer.draw(simulation)
            pygame.display.flip()
            pygame.event.pump()

        result = _capture_result(actual_backend, simulation, ticks=ticks)
        result["gpu_info"] = renderer_gpu_info(renderer)
        return result
    finally:
        pygame.quit()


def _compare(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "sim_frame",
        "population",
        "predator_count",
        "prey_count",
        "food_count",
        "generation",
        "total_births",
        "total_deaths",
        "predation_kill_count",
        "observability",
        "stability",
        "creature_digest",
        "food_digest",
        "rng_digest",
    )
    deltas = {
        key: {
            "match": left[key] == right[key],
            "pygame": left[key],
            "gpu": right[key],
        }
        for key in keys
    }
    return {
        "parity_holds": all(item["match"] for item in deltas.values()),
        "deltas": deltas,
    }


def main() -> int:
    args = _parse_args()
    scenario, _settings = build_settings_for_scenario(args.scenario)
    seed = args.seed if args.seed is not None else scenario.seed
    render_every = max(1, int(args.render_every))
    ticks = max(1, int(args.ticks))

    pygame_result = _run_backend(
        args.scenario,
        "pygame",
        seed=seed,
        ticks=ticks,
        render_every=render_every,
    )
    gpu_result = _run_backend(
        args.scenario,
        "gpu",
        seed=seed,
        ticks=ticks,
        render_every=render_every,
    )
    comparison = _compare(pygame_result, gpu_result)

    report = {
        "audit": "predator_prey_backend_parity",
        "scenario": args.scenario,
        "seed": seed,
        "ticks": ticks,
        "render_every": render_every,
        "pygame": pygame_result,
        "gpu": gpu_result,
        "comparison": comparison,
        "limitations": [
            "Requires a live display and working OpenGL path.",
            "Compares ecology outcomes by fixed simulation ticks, not wall-clock time.",
            "This is a backend-behavior smoke/parity check, not a visual pixel-comparison test.",
        ],
    }

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")

    print(payload)

    if not comparison["parity_holds"]:
        mismatches = [
            key for key, value in comparison["deltas"].items() if not value["match"]
        ]
        print(
            f"Backend parity failed for: {', '.join(mismatches)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
