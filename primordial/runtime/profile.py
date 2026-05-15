"""Profile-session orchestration and output writing."""

from __future__ import annotations

import cProfile
import json
import logging
import pstats
from datetime import datetime
from pathlib import Path

import pygame

from primordial.rendering import Renderer
from primordial.settings import Settings
from primordial.simulation import Simulation

from .fixed_step import FixedStepLoopState, get_effective_target_fps
from .session import run_bounded_session
from .timing import LoopTimingCollector

logger = logging.getLogger(__name__)


def _run_profile_session(
    simulation: Simulation,
    renderer: Renderer,
    clock: pygame.time.Clock,
    settings: Settings,
    runtime_loop: FixedStepLoopState,
    timing_collector: LoopTimingCollector,
) -> str:
    """
    Run a 60-second profile session, dump .pstats and text report, then return base path.
    """
    out_dir = Path(settings.config_path).parent
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = f"profile-{stamp}"

    profiler = cProfile.Profile()
    logger.info("Running 60-second profile session...")
    profiler.enable()
    elapsed_wall_seconds = run_bounded_session(
        simulation,
        renderer,
        clock,
        runtime_loop,
        timing_collector,
        duration_seconds=60.0,
        target_fps=get_effective_target_fps(settings),
    )
    profiler.disable()

    for candidate_dir in (out_dir, Path.cwd()):
        try:
            candidate_dir.mkdir(parents=True, exist_ok=True)
            base = candidate_dir / base_name
            pstats_path = base.with_suffix(".pstats")
            text_path = base.with_suffix(".txt")
            timing_path = base.with_suffix(".timing.json")
            profiler.dump_stats(str(pstats_path))
            with text_path.open("w", encoding="utf-8") as fp:
                stats = pstats.Stats(profiler, stream=fp).sort_stats("cumulative")
                stats.print_stats(120)
            with timing_path.open("w", encoding="utf-8") as fp:
                json.dump(
                    timing_collector.build_summary(
                        elapsed_wall_seconds=elapsed_wall_seconds,
                        runtime_loop=runtime_loop,
                    ),
                    fp,
                    indent=2,
                    sort_keys=True,
                )
            if candidate_dir != out_dir:
                logger.warning("Profile output fallback path in use: %s", candidate_dir)
            return str(base)
        except OSError as exc:
            logger.warning("Profile write failed at %s: %s", candidate_dir, exc)

    raise RuntimeError("Unable to write profile output to any candidate directory.")
