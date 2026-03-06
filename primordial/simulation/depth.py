"""Shared bounded depth-band helpers for the simulation."""

from __future__ import annotations


DEPTH_SURFACE = 0
DEPTH_MID = 1
DEPTH_DEEP = 2
DEPTH_BANDS = (DEPTH_SURFACE, DEPTH_MID, DEPTH_DEEP)
DEPTH_BAND_NAMES = {
    DEPTH_SURFACE: "surface",
    DEPTH_MID: "mid",
    DEPTH_DEEP: "deep",
}


def clamp_depth_band(depth_band: int) -> int:
    """Clamp an arbitrary integer to the supported depth-band range."""
    return max(DEPTH_SURFACE, min(DEPTH_DEEP, int(depth_band)))


def depth_band_name(depth_band: int) -> str:
    """Return the stable name for a depth band."""
    return DEPTH_BAND_NAMES[clamp_depth_band(depth_band)]


def depth_band_from_preference(depth_preference: float) -> int:
    """Map a normalized preference scalar to one of the three bands."""
    if depth_preference < (1.0 / 3.0):
        return DEPTH_SURFACE
    if depth_preference < (2.0 / 3.0):
        return DEPTH_MID
    return DEPTH_DEEP


def depth_band_separation(left: int, right: int) -> int:
    """Return the absolute separation between two bounded bands."""
    return abs(clamp_depth_band(left) - clamp_depth_band(right))


def step_depth_band_toward(current: int, target: int) -> int:
    """Move one bounded step toward a target band."""
    current_band = clamp_depth_band(current)
    target_band = clamp_depth_band(target)
    if current_band == target_band:
        return current_band
    if current_band < target_band:
        return current_band + 1
    return current_band - 1
