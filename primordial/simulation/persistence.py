"""Versioned save/load helpers for simulation world snapshots."""

from __future__ import annotations

import json
from pathlib import Path
import random
from typing import Any

from ..settings import Settings
from .creature import Creature
from .depth import DEPTH_MID, clamp_depth_band, depth_band_from_preference
from .food import Food, FoodManager
from .genome import Genome
from .simulation import Simulation
from .zones import Zone, ZoneManager


SAVE_FORMAT_VERSION = 2
_SUPPORTED_SAVE_FORMAT_VERSIONS = {1, SAVE_FORMAT_VERSION}
SAVE_KIND = "primordial.world_snapshot"

_SIMULATION_SETTING_FIELDS = (
    "sim_mode",
    "initial_population",
    "max_population",
    "food_spawn_rate",
    "food_max_particles",
    "food_cycle_enabled",
    "food_cycle_period",
    "energy_to_reproduce",
    "creature_speed_base",
    "mutation_rate",
    "cosmic_ray_rate",
    "zone_count",
    "zone_strength",
)


class SnapshotError(ValueError):
    """Raised when a snapshot cannot be loaded safely."""


def save_snapshot(simulation: Simulation, path: str | Path) -> Path:
    """Serialize the authoritative simulation state to JSON on disk."""
    snapshot_path = Path(path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_snapshot(simulation)
    snapshot_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return snapshot_path


def load_snapshot(path: str | Path, settings: Settings | None = None) -> Simulation:
    """Load a simulation snapshot from disk and rebuild transient state."""
    payload = _read_snapshot_payload(path)
    return load_snapshot_payload(payload, settings=settings)


def load_snapshot_payload(
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> Simulation:
    """Load a simulation snapshot from an in-memory payload."""
    _validate_snapshot_payload(payload)

    world = payload["world"]
    resolved_settings = settings if settings is not None else Settings()
    _apply_simulation_settings(resolved_settings, world["settings"])

    simulation = Simulation(
        int(world["width"]),
        int(world["height"]),
        resolved_settings,
        bootstrap_world=False,
    )
    simulation.creatures = [_deserialize_creature(item) for item in world["creatures"]]
    simulation.food_manager = _deserialize_food_manager(
        world["food"],
        simulation.width,
        simulation.height,
    )
    simulation.zone_manager = _deserialize_zone_manager(
        world["zones"],
        simulation.width,
        simulation.height,
    )
    counters = world["counters"]
    simulation.generation = int(counters["generation"])
    simulation.total_births = int(counters["total_births"])
    simulation.total_deaths = int(counters["total_deaths"])
    simulation._frame = int(counters["frame"])
    simulation._next_lineage_id = int(counters["next_lineage_id"])
    simulation.paused = False
    simulation._old_age_lifespans.clear()
    if resolved_settings.sim_mode == "predator_prey":
        simulation.restore_predator_prey_runtime_state(world.get("predator_prey", {}))
    simulation.rebuild_derived_state()

    random.setstate(_deserialize_random_state(world["rng_state"]))
    return simulation


def build_snapshot(simulation: Simulation) -> dict[str, Any]:
    """Build a deterministic, machine-readable snapshot payload."""
    return {
        "version": SAVE_FORMAT_VERSION,
        "metadata": {
            "kind": SAVE_KIND,
        },
        "world": {
            "width": simulation.width,
            "height": simulation.height,
            "settings": _serialize_simulation_settings(simulation.settings),
            "counters": {
                "generation": simulation.generation,
                "total_births": simulation.total_births,
                "total_deaths": simulation.total_deaths,
                "frame": simulation._frame,
                "next_lineage_id": simulation._next_lineage_id,
            },
            "creatures": [_serialize_creature(creature) for creature in simulation.creatures],
            "food": _serialize_food_manager(simulation.food_manager),
            "zones": _serialize_zone_manager(simulation.zone_manager),
            "rng_state": _serialize_random_state(random.getstate()),
            "predator_prey": (
                simulation.export_predator_prey_runtime_state()
                if simulation.settings.sim_mode == "predator_prey"
                else {}
            ),
        },
    }


def inspect_snapshot_dimensions(path: str | Path) -> tuple[int, int]:
    """Read the saved world dimensions without constructing a Simulation."""
    snapshot = _read_snapshot_payload(path)
    _validate_snapshot_payload(snapshot)
    world = snapshot["world"]
    return int(world["width"]), int(world["height"])


def _read_snapshot_payload(path: str | Path) -> dict[str, Any]:
    snapshot_path = Path(path)
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SnapshotError(f"Snapshot file not found: {snapshot_path}") from exc
    except json.JSONDecodeError as exc:
        raise SnapshotError(
            f"Snapshot is not valid JSON: {snapshot_path} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc
    if not isinstance(payload, dict):
        raise SnapshotError("Snapshot root must be an object.")
    return payload


def _validate_snapshot_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SnapshotError("Snapshot root must be an object.")
    version = payload.get("version")
    if version not in _SUPPORTED_SAVE_FORMAT_VERSIONS:
        raise SnapshotError(
            f"Unsupported snapshot version: {version!r}. "
            f"Expected one of {sorted(_SUPPORTED_SAVE_FORMAT_VERSIONS)}."
        )
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise SnapshotError("Snapshot metadata must be an object.")
    if metadata.get("kind") != SAVE_KIND:
        raise SnapshotError(
            f"Unsupported snapshot kind: {metadata.get('kind')!r}. "
            f"Expected {SAVE_KIND!r}."
        )
    world = payload.get("world")
    if not isinstance(world, dict):
        raise SnapshotError("Snapshot world must be an object.")
    for key in ("width", "height", "settings", "counters", "creatures", "food", "zones", "rng_state"):
        if key not in world:
            raise SnapshotError(f"Snapshot world is missing '{key}'.")


def _serialize_simulation_settings(settings: Settings) -> dict[str, Any]:
    return {
        "fields": {name: getattr(settings, name) for name in _SIMULATION_SETTING_FIELDS},
        "mode_params": settings.mode_params,
    }


def _apply_simulation_settings(settings: Settings, payload: dict[str, Any]) -> None:
    fields = payload.get("fields", {})
    for name in _SIMULATION_SETTING_FIELDS:
        if name in fields:
            setattr(settings, name, fields[name])
    mode_params = payload.get("mode_params")
    if isinstance(mode_params, dict):
        settings.mode_params = mode_params


def _serialize_creature(creature: Creature) -> dict[str, Any]:
    return {
        "x": creature.x,
        "y": creature.y,
        "vx": creature.vx,
        "vy": creature.vy,
        "energy": creature.energy,
        "age": creature.age,
        "lineage_id": creature.lineage_id,
        "species": creature.species,
        "recent_animal_energy": creature.recent_animal_energy,
        "satiety_ticks_remaining": creature.satiety_ticks_remaining,
        "depth_band": creature.depth_band,
        "genome": _serialize_genome(creature.genome),
        "motion_state": {
            "swim_phase": creature._swim_phase,
            "dart_burst_remaining": creature._dart_burst_remaining,
            "dart_cooldown": creature._dart_cooldown,
        },
    }


def _deserialize_creature(payload: dict[str, Any]) -> Creature:
    motion_state = payload["motion_state"]
    genome = _deserialize_genome(payload["genome"])
    creature = Creature(
        x=float(payload["x"]),
        y=float(payload["y"]),
        genome=genome,
        vx=float(payload["vx"]),
        vy=float(payload["vy"]),
        energy=float(payload["energy"]),
        age=int(payload["age"]),
        lineage_id=int(payload["lineage_id"]),
        species=str(payload.get("species", "none")),
        recent_animal_energy=float(payload.get("recent_animal_energy", 0.0)),
        satiety_ticks_remaining=int(payload.get("satiety_ticks_remaining", 0)),
        depth_band=clamp_depth_band(
            int(payload.get("depth_band", depth_band_from_preference(genome.depth_preference)))
        ),
        _glyph_phase=genome.hue * 6.28,
        _swim_phase=float(motion_state["swim_phase"]),
        _dart_burst_remaining=int(motion_state["dart_burst_remaining"]),
        _dart_cooldown=int(motion_state["dart_cooldown"]),
    )
    creature.trail = []
    creature.rotation_angle = 0.0
    creature.glyph_surface = None
    return creature


def _serialize_genome(genome: Genome) -> dict[str, float]:
    return {
        "speed": genome.speed,
        "size": genome.size,
        "sense_radius": genome.sense_radius,
        "aggression": genome.aggression,
        "hue": genome.hue,
        "saturation": genome.saturation,
        "efficiency": genome.efficiency,
        "complexity": genome.complexity,
        "symmetry": genome.symmetry,
        "stroke_scale": genome.stroke_scale,
        "appendages": genome.appendages,
        "rotation_speed": genome.rotation_speed,
        "motion_style": genome.motion_style,
        "longevity": genome.longevity,
        "conformity": genome.conformity,
        "depth_preference": genome.depth_preference,
    }


def _deserialize_genome(payload: dict[str, Any]) -> Genome:
    return Genome(
        speed=float(payload["speed"]),
        size=float(payload["size"]),
        sense_radius=float(payload["sense_radius"]),
        aggression=float(payload["aggression"]),
        hue=float(payload["hue"]),
        saturation=float(payload["saturation"]),
        efficiency=float(payload["efficiency"]),
        complexity=float(payload["complexity"]),
        symmetry=float(payload["symmetry"]),
        stroke_scale=float(payload["stroke_scale"]),
        appendages=float(payload["appendages"]),
        rotation_speed=float(payload["rotation_speed"]),
        motion_style=float(payload["motion_style"]),
        longevity=float(payload["longevity"]),
        conformity=float(payload["conformity"]),
        depth_preference=float(payload.get("depth_preference", 0.5)),
    )


def _serialize_food_manager(food_manager: FoodManager) -> dict[str, Any]:
    return {
        "bucket_size": food_manager.bucket_size,
        "max_particles": food_manager.max_particles,
        "particles": [
            {
                "x": food.x,
                "y": food.y,
                "energy": food.energy,
                "depth_band": food.depth_band,
            }
            for food in food_manager.particles
        ],
    }


def _deserialize_food_manager(
    payload: dict[str, Any],
    width: int,
    height: int,
) -> FoodManager:
    food_manager = FoodManager(
        width,
        height,
        bucket_size=int(payload["bucket_size"]),
        max_particles=int(payload["max_particles"]),
    )
    food_manager.particles = [
        Food(
            x=float(food["x"]),
            y=float(food["y"]),
            energy=float(food["energy"]),
            depth_band=clamp_depth_band(int(food.get("depth_band", DEPTH_MID))),
            twinkle_phase=0.0,
        )
        for food in payload["particles"]
    ]
    food_manager.rebuild_buckets()
    return food_manager


def _serialize_zone_manager(zone_manager: ZoneManager) -> dict[str, Any]:
    return {
        "global_strength": zone_manager.global_strength,
        "zones": [
            {
                "x": zone.x,
                "y": zone.y,
                "radius": zone.radius,
                "zone_type": zone.zone_type,
                "local_strength": zone.local_strength,
            }
            for zone in zone_manager.zones
        ],
    }


def _deserialize_zone_manager(
    payload: dict[str, Any],
    width: int,
    height: int,
) -> ZoneManager:
    zone_manager = ZoneManager(
        width,
        height,
        0,
        float(payload["global_strength"]),
    )
    zone_manager.zones = [
        Zone(
            x=float(zone["x"]),
            y=float(zone["y"]),
            radius=float(zone["radius"]),
            zone_type=str(zone["zone_type"]),
            local_strength=float(zone["local_strength"]),
        )
        for zone in payload["zones"]
    ]
    return zone_manager


def _serialize_random_state(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_serialize_random_state(item) for item in value]
    if isinstance(value, list):
        return [_serialize_random_state(item) for item in value]
    return value


def _deserialize_random_state(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_deserialize_random_state(item) for item in value)
    return value
