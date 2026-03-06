#!/usr/bin/env python3
"""Exercise M3.5 save/load/resume flow and emit a machine-readable summary."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import random
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primordial.settings import Settings
from primordial.simulation import (
    SAVE_FORMAT_VERSION,
    Simulation,
    build_snapshot,
    load_snapshot,
    save_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Path to the summary JSON file.")
    parser.add_argument("--save-path", required=True, help="Path to the snapshot JSON file.")
    args = parser.parse_args()

    output_path = Path(args.output)
    save_path = Path(args.save_path)

    settings = _build_settings()
    random.seed(20260306)
    simulation = Simulation(640, 360, settings)
    for _ in range(150):
        simulation.step()

    snapshot_path = save_snapshot(simulation, save_path)
    loaded = load_snapshot(snapshot_path, settings=_build_settings())

    saved_payload = build_snapshot(simulation)
    loaded_payload = build_snapshot(loaded)

    reference_rng_state = random.getstate()
    random.setstate(reference_rng_state)
    for _ in range(45):
        simulation.step()
    advanced_original = build_snapshot(simulation)

    random.setstate(reference_rng_state)
    for _ in range(45):
        loaded.step()
    advanced_loaded = build_snapshot(loaded)

    summary = {
        "snapshot_path": str(snapshot_path),
        "save_format_version": SAVE_FORMAT_VERSION,
        "roundtrip": {
            "version_matches": saved_payload["version"] == SAVE_FORMAT_VERSION,
            "payload_matches_after_load": saved_payload == loaded_payload,
            "resume_matches_after_steps": advanced_original == advanced_loaded,
        },
        "continuity": {
            "population": simulation.population,
            "generation": simulation.generation,
            "food_count": simulation.food_count,
            "lineages": simulation.get_lineage_count(),
        },
        "save_boundary": {
            "world_has_authoritative_sections": _sections_present(saved_payload),
            "omits_renderer_transients": _omits_transients(saved_payload),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return 0


def _build_settings() -> Settings:
    settings = Settings()
    settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
    settings.sim_mode = "energy"
    settings.visual_theme = "ocean"
    settings.show_hud = False
    settings.fullscreen = False
    settings.initial_population = 28
    settings.max_population = 56
    settings.food_spawn_rate = 0.75
    settings.food_max_particles = 140
    settings.food_cycle_enabled = True
    settings.food_cycle_period = 900
    settings.mutation_rate = 0.06
    settings.cosmic_ray_rate = 0.0003
    settings.energy_to_reproduce = 0.8
    settings.zone_count = 5
    settings.zone_strength = 0.8
    return settings


def _sections_present(payload: dict[str, Any]) -> bool:
    world = payload["world"]
    expected = {"width", "height", "settings", "counters", "creatures", "food", "zones", "rng_state"}
    return expected.issubset(world)


def _omits_transients(payload: dict[str, Any]) -> bool:
    world = payload["world"]
    if any(key in world for key in ("death_events", "birth_events", "cosmic_ray_events", "active_attacks")):
        return False
    if not world["creatures"]:
        return True
    creature = world["creatures"][0]
    return all(
        key not in creature
        for key in ("trail", "rotation_angle", "glyph_surface", "flock_id")
    )


if __name__ == "__main__":
    raise SystemExit(main())
