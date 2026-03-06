"""Simulation module - creature logic, genome, food, world."""

from .genome import Genome
from .creature import Creature
from .food import Food, FoodManager
from .persistence import (
    SAVE_FORMAT_VERSION,
    SnapshotError,
    build_snapshot,
    inspect_snapshot_dimensions,
    load_snapshot,
    load_snapshot_payload,
    save_snapshot,
)
from .simulation import Simulation

__all__ = [
    "Genome",
    "Creature",
    "Food",
    "FoodManager",
    "SAVE_FORMAT_VERSION",
    "Simulation",
    "SnapshotError",
    "build_snapshot",
    "inspect_snapshot_dimensions",
    "load_snapshot",
    "load_snapshot_payload",
    "save_snapshot",
]
