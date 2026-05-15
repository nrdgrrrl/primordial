#!/usr/bin/env python3
"""A/B benchmark comparing kin-line rendering cost in predator_prey GPU mode.

Runs 2-3 scenarios (kin_off, kin_on, optionally kin_on_synthetic) with the same
seed(s) and duration, then prints a short summary table.  Uses in-memory settings
overrides only — never touches the user config.

Requires a real display (X11/Wayland) for GPU renderer.  The SDL_VIDEODRIVER
dummy backend disables GPU rendering, so this script does NOT set it.

Output:
  benchmark_outputs/kin_lines_ab_<timestamp>/summary.json
  benchmark_outputs/kin_lines_ab_<timestamp>/summary.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from primordial.rendering import create_renderer, display_flags_for_settings, renderer_backend_name
from primordial.runtime import (
    LoopFrameMetrics,
    LoopTimingCollector,
    advance_fixed_step_frame,
    create_fixed_step_loop_state,
    get_effective_target_fps,
    simulation_timing_is_suppressed,
)
from primordial.scenarios import apply_scenario_settings, get_scenario
from primordial.settings import Settings
from primordial.simulation import Simulation


@dataclass
class ScenarioConfig:
    id: str
    label: str
    kin_line_max_distance: float
    kin_line_min_group: int
    kin_line_debug_boost: bool = False
    lineage_cluster_size: int = 0
    extra_overrides: dict[str, Any] = field(default_factory=dict)


KIN_OFF = ScenarioConfig(
    id="kin_off",
    label="kin_off",
    kin_line_max_distance=0.001,
    kin_line_min_group=3,
)

KIN_ON_PLAIN = ScenarioConfig(
    id="kin_on_plain",
    label="kin_on_plain",
    kin_line_max_distance=180.0,
    kin_line_min_group=3,
)

KIN_ON_SYNTHETIC = ScenarioConfig(
    id="kin_on_synthetic",
    label="kin_on_synthetic",
    kin_line_max_distance=220.0,
    kin_line_min_group=2,
    lineage_cluster_size=6,
)

KIN_DEBUG_BOOST = ScenarioConfig(
    id="kin_debug_boost",
    label="kin_debug_boost (diagnostic)",
    kin_line_max_distance=180.0,
    kin_line_min_group=3,
    kin_line_debug_boost=True,
)

DEFAULT_SCENARIOS = [KIN_OFF, KIN_ON_PLAIN, KIN_ON_SYNTHETIC]

DEFAULT_SEEDS = [161803]
DEFAULT_SECONDS = 60.0
SCENARIO_ID = "predator_prey_medium"


def _assign_lineage_clusters(simulation: Simulation, cluster_size: int) -> None:
    """Benchmark-only: reassign lineage_id so nearby creatures share an id.

    Sorts creatures by spatial grid cell then assigns sequential groups the
    same lineage_id.  Uses ids starting at 1000 to avoid collisions with
    simulation-assigned ids.  Does not change any simulation behaviour beyond
    the lineage label.
    """
    creatures = simulation.creatures
    if not creatures or cluster_size < 2:
        return

    cell = 120.0
    sorted_creatures = sorted(
        creatures,
        key=lambda c: (int(c.x // cell), int(c.y // cell), c.x, c.y),
    )

    for i, creature in enumerate(sorted_creatures):
        creature.lineage_id = 1000 + (i // cluster_size)


def _apply_overrides(settings: Settings, cfg: ScenarioConfig) -> None:
    settings.kin_line_max_distance = cfg.kin_line_max_distance
    settings.kin_line_min_group = cfg.kin_line_min_group
    settings.kin_line_debug_boost = cfg.kin_line_debug_boost
    for key, value in cfg.extra_overrides.items():
        setattr(settings, key, value)


def _run_scenario(
    cfg: ScenarioConfig,
    seed: int,
    seconds: float,
    scenario_id: str,
) -> dict[str, Any]:
    scenario = get_scenario(scenario_id)
    pygame.init()
    try:
        settings = Settings()
        apply_scenario_settings(settings, scenario)
        _apply_overrides(settings, cfg)
        settings.fullscreen = False

        screen = pygame.display.set_mode(
            (scenario.width, scenario.height),
            display_flags_for_settings(settings),
        )
        pygame.display.set_caption(f"Kin-line A/B: {cfg.id} seed={seed}")

        renderer = create_renderer(screen, settings, debug=False)
        backend = renderer_backend_name(renderer)
        if backend != "gpu":
            print(
                f"  WARNING: renderer backend is '{backend}', not 'gpu'. "
                f"Kin-line metrics will not be available.",
                file=sys.stderr,
            )

        random.seed(seed)

        if scenario.mode == "predator_prey":
            simulation = Simulation(scenario.width, scenario.height, settings, seed=seed)
            simulation.reset_predator_prey_adaptive_tuning()
            simulation.set_predator_prey_adaptive_tuning_enabled(False)
        else:
            simulation = Simulation(scenario.width, scenario.height, settings)

        if cfg.lineage_cluster_size >= 2:
            _assign_lineage_clusters(simulation, cfg.lineage_cluster_size)

        renderer.resize(simulation.width, simulation.height, screen=screen)
        clock = pygame.time.Clock()
        runtime_loop = create_fixed_step_loop_state(settings)
        timing_collector = LoopTimingCollector(retain_samples=True)

        render_breakdown_sums: dict[str, float] = {}
        render_breakdown_counts: dict[str, int] = {}
        kin_line_count_samples: list[int] = []
        kin_qualifying_lineages_samples: list[int] = []
        kin_largest_lineage_samples: list[int] = []

        start_time = time.perf_counter()
        end_time = start_time + seconds

        while time.perf_counter() < end_time:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    break

            sim_suppressed = simulation_timing_is_suppressed(simulation)
            sim_ms, sim_steps, clamp_frames, dropped_seconds = advance_fixed_step_frame(
                simulation,
                runtime_loop,
                allow_simulation=not sim_suppressed,
            )
            runtime_loop.restore_buffered_attacks(simulation)

            if cfg.lineage_cluster_size >= 2:
                _assign_lineage_clusters(simulation, cfg.lineage_cluster_size)

            render_metrics = renderer.draw(simulation)
            render_ms = render_metrics.get("draw_total_ms", 0.0)
            present_start = time.perf_counter()
            pygame.display.flip()
            present_ms = (time.perf_counter() - present_start) * 1000.0
            pacing_start = time.perf_counter()
            clock.tick(max(1, get_effective_target_fps(settings)))
            pacing_ms = (time.perf_counter() - pacing_start) * 1000.0

            frame_ms = render_ms + sim_ms + present_ms + pacing_ms
            effective_fps = 1000.0 / frame_ms if frame_ms > 0.0 else 0.0
            timing_collector.record_frame(LoopFrameMetrics(
                event_ms=0.0,
                sim_ms=sim_ms,
                render_ms=render_ms,
                present_ms=present_ms,
                pacing_ms=pacing_ms,
                frame_ms=frame_ms,
                effective_fps=effective_fps,
                sim_steps=sim_steps,
                clamp_frames=clamp_frames,
                dropped_seconds=dropped_seconds,
                accumulator_seconds=runtime_loop.accumulator_seconds,
            ))

            for key, value in render_metrics.items():
                if not key.endswith("_ms"):
                    continue
                render_breakdown_sums[key] = render_breakdown_sums.get(key, 0.0) + float(value)
                render_breakdown_counts[key] = render_breakdown_counts.get(key, 0) + 1

            if "kin_line_count" in render_metrics:
                kin_line_count_samples.append(int(render_metrics["kin_line_count"]))
            if "kin_line_qualifying_lineages" in render_metrics:
                kin_qualifying_lineages_samples.append(int(render_metrics["kin_line_qualifying_lineages"]))
            if "kin_line_largest_lineage" in render_metrics:
                kin_largest_lineage_samples.append(int(render_metrics["kin_line_largest_lineage"]))

            if simulation.update_predator_prey_runtime(now_seconds=time.monotonic()):
                renderer.reset_runtime_state()
                runtime_loop.reset_timing_debt()

        elapsed = max(0.0, time.perf_counter() - start_time)
        timing_summary = timing_collector.build_summary(
            elapsed_wall_seconds=elapsed,
            runtime_loop=runtime_loop,
        )

        render_breakdown_mean_ms = {
            key: (render_breakdown_sums[key] / render_breakdown_counts[key])
            for key in sorted(render_breakdown_sums)
            if render_breakdown_counts.get(key)
        }

        fps_samples = timing_collector.get_samples("effective_fps")

        result: dict[str, Any] = {
            "scenario": cfg.id,
            "label": cfg.label,
            "seed": seed,
            "duration_seconds": elapsed,
            "frames_rendered": timing_collector.frame_count,
            "fps_mean": statistics.mean(fps_samples) if fps_samples else 0.0,
            "fps_min": min(fps_samples) if fps_samples else 0.0,
            "render_ms_mean": timing_summary["timing_ms"]["render"]["mean"],
            "sim_ms_mean": timing_summary["timing_ms"]["sim"]["mean"],
            "snapshot_ms_mean": render_breakdown_mean_ms.get("snapshot_ms", 0.0),
            "kin_lines_build_ms_mean": render_breakdown_mean_ms.get("kin_lines_build_ms", 0.0),
            "kin_lines_ms_mean": render_breakdown_mean_ms.get("kin_lines_ms", 0.0),
            "kin_line_count_mean": (
                statistics.mean(kin_line_count_samples) if kin_line_count_samples else 0.0
            ),
            "kin_line_count_max": max(kin_line_count_samples) if kin_line_count_samples else 0,
            "kin_qualifying_lineages_mean": (
                statistics.mean(kin_qualifying_lineages_samples) if kin_qualifying_lineages_samples else 0.0
            ),
            "kin_qualifying_lineages_max": max(kin_qualifying_lineages_samples) if kin_qualifying_lineages_samples else 0,
            "kin_largest_lineage_mean": (
                statistics.mean(kin_largest_lineage_samples) if kin_largest_lineage_samples else 0.0
            ),
            "kin_largest_lineage_max": max(kin_largest_lineage_samples) if kin_largest_lineage_samples else 0,
            "render_breakdown_mean_ms": render_breakdown_mean_ms,
            "active_work_mean": (
                timing_summary["timing_ms"]["render"]["mean"]
                + timing_summary["timing_ms"]["sim"]["mean"]
            ),
            "headroom_30hz": max(
                0.0,
                33.33 - (timing_summary["timing_ms"]["render"]["mean"] + timing_summary["timing_ms"]["sim"]["mean"]),
            ),
            "settings_overrides": {
                "kin_line_max_distance": cfg.kin_line_max_distance,
                "kin_line_min_group": cfg.kin_line_min_group,
                "kin_line_debug_boost": cfg.kin_line_debug_boost,
                "lineage_cluster_size": cfg.lineage_cluster_size,
            },
        }
        return result
    finally:
        pygame.quit()


def _run_all_scenarios(
    scenarios: list[ScenarioConfig],
    seeds: list[int],
    seconds: float,
    scenario_id: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for cfg in scenarios:
        for seed in seeds:
            print(f"  Running {cfg.label} seed={seed} duration={seconds}s ...", flush=True)
            result = _run_scenario(cfg, seed, seconds, scenario_id)
            results.append(result)
            print(
                f"    fps_mean={result['fps_mean']:.1f}  "
                f"render_ms={result['render_ms_mean']:.2f}  "
                f"sim_ms={result['sim_ms_mean']:.2f}  "
                f"kin_lines_ms={result['kin_lines_ms_mean']:.3f}  "
                f"kin_lines_build_ms={result['kin_lines_build_ms_mean']:.3f}  "
                f"kin_line_count_mean={result['kin_line_count_mean']:.1f}  "
                f"qual_lineages={result['kin_qualifying_lineages_mean']:.1f}  "
                f"largest_lineage={result['kin_largest_lineage_mean']:.1f}",
                flush=True,
            )
    return results


def _average_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {}
    if len(results) == 1:
        return dict(results[0])

    numeric_keys = [
        "fps_mean", "fps_min", "render_ms_mean", "sim_ms_mean",
        "snapshot_ms_mean", "kin_lines_build_ms_mean", "kin_lines_ms_mean",
        "kin_line_count_mean", "kin_line_count_max",
        "kin_qualifying_lineages_mean", "kin_qualifying_lineages_max",
        "kin_largest_lineage_mean", "kin_largest_lineage_max",
        "active_work_mean", "headroom_30hz",
    ]
    avg: dict[str, Any] = {
        "scenario": results[0]["scenario"],
        "label": results[0]["label"],
        "seeds": [r["seed"] for r in results],
        "seed_count": len(results),
        "duration_seconds": max(r["duration_seconds"] for r in results),
        "frames_rendered": sum(r["frames_rendered"] for r in results),
    }
    for key in numeric_keys:
        values = [r[key] for r in results if key in r]
        avg[key] = statistics.mean(values) if values else 0.0
    avg["settings_overrides"] = results[0]["settings_overrides"]
    return avg


def _build_summary_table(rows: list[dict[str, Any]], baseline_row: dict[str, Any]) -> str:
    headers = [
        "scenario", "seeds", "FPS mean/min", "render_ms", "sim_ms",
        "snapshot_ms", "kin_build_ms", "kin_draw_ms", "lines",
        "qual_lin", "largest", "active_work", "headroom@30Hz",
    ]
    lines = []
    col_widths = [len(h) for h in headers]

    table_rows: list[list[str]] = []
    for row in rows:
        cells = [
            row["label"],
            str(row.get("seed_count", 1)),
            f"{row['fps_mean']:.1f}/{row['fps_min']:.1f}",
            f"{row['render_ms_mean']:.2f}",
            f"{row['sim_ms_mean']:.2f}",
            f"{row['snapshot_ms_mean']:.2f}",
            f"{row['kin_lines_build_ms_mean']:.3f}",
            f"{row['kin_lines_ms_mean']:.3f}",
            f"{row['kin_line_count_mean']:.1f}/{row['kin_line_count_max']}",
            f"{row['kin_qualifying_lineages_mean']:.1f}/{row['kin_qualifying_lineages_max']}",
            f"{row['kin_largest_lineage_mean']:.1f}/{row['kin_largest_lineage_max']}",
            f"{row['active_work_mean']:.2f}",
            f"{row['headroom_30hz']:.2f}",
        ]
        table_rows.append(cells)
        for i, cell in enumerate(cells):
            col_widths[i] = max(col_widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        parts = []
        for i, cell in enumerate(cells):
            if i == 0:
                parts.append(cell.ljust(col_widths[i]))
            else:
                parts.append(cell.rjust(col_widths[i]))
        return "  ".join(parts)

    sep = "  ".join("-" * w for w in col_widths)
    lines.append(fmt_row(headers))
    lines.append(sep)
    for row_cells in table_rows:
        lines.append(fmt_row(row_cells))

    if baseline_row:
        lines.append("")
        lines.append("Delta vs kin_off:")
        for row in rows:
            if row["scenario"] == "kin_off":
                continue
            d_render = row["render_ms_mean"] - baseline_row["render_ms_mean"]
            d_active = row["active_work_mean"] - baseline_row["active_work_mean"]
            lines.append(
                f"  {row['label']:30s}  "
                f"Δrender_ms={d_render:+.3f}  "
                f"Δactive_work={d_active:+.3f}"
            )

    return "\n".join(lines)


def _build_conclusion(rows: list[dict[str, Any]], baseline: dict[str, Any]) -> str:
    if not baseline:
        return "No baseline (kin_off) result available."
    lines: list[str] = []
    kin_on_rows = [r for r in rows if r["scenario"] != "kin_off"]
    if not kin_on_rows:
        return "Only kin_off scenario was run."

    for row in kin_on_rows:
        d_render = row["render_ms_mean"] - baseline["render_ms_mean"]
        d_active = row["active_work_mean"] - baseline["active_work_mean"]
        pct_render = (
            (d_render / baseline["render_ms_mean"] * 100.0) if baseline["render_ms_mean"] > 0 else 0.0
        )
        lines.append(
            f"{row['label']}: Δrender_ms={d_render:+.3f} ({pct_render:+.1f}%), "
            f"Δactive_work={d_active:+.3f} ms"
        )

    affordable = all(r["headroom_30hz"] > 0 for r in kin_on_rows)
    if affordable:
        lines.append(
            "Kin lines appear affordable at 30 Hz — all scenarios retain positive headroom."
        )
    else:
        worst = min(r["headroom_30hz"] for r in kin_on_rows)
        lines.append(
            f"Kin lines may be costly at 30 Hz — worst headroom is {worst:.2f} ms."
        )

    return "\n".join(lines)


def _build_markdown(
    rows: list[dict[str, Any]],
    baseline: dict[str, Any],
    command: str,
    output_dir: str,
) -> str:
    lines: list[str] = []
    lines.append("# Kin-Line A/B Benchmark")
    lines.append("")
    lines.append(f"- Command: `{command}`")
    lines.append(f"- Output: `{output_dir}`")
    lines.append(f"- Scenarios: {', '.join(r['label'] for r in rows)}")
    lines.append(f"- Seeds per scenario: {rows[0].get('seed_count', 1)}")
    lines.append(f"- Duration per run: {rows[0].get('duration_seconds', 0):.0f}s")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("```")
    lines.append(_build_summary_table(rows, baseline))
    lines.append("```")
    lines.append("")
    lines.append("## Conclusion")
    lines.append("")
    lines.append(_build_conclusion(rows, baseline))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seconds",
        type=float,
        default=DEFAULT_SECONDS,
        help=f"Duration per run in seconds (default: {DEFAULT_SECONDS}).",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default=None,
        help="Comma-separated seed list (default: 161803).",
    )
    parser.add_argument(
        "--scenarios",
        type=str,
        default=None,
        help="Comma-separated scenario ids: kin_off,kin_on_plain,kin_on_synthetic,kin_debug_boost (default: kin_off,kin_on_plain,kin_on_synthetic).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("benchmark_outputs"),
        help="Root directory for benchmark outputs.",
    )
    args = parser.parse_args()

    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else list(DEFAULT_SEEDS)

    scenario_map = {
        "kin_off": KIN_OFF,
        "kin_on_plain": KIN_ON_PLAIN,
        "kin_on_synthetic": KIN_ON_SYNTHETIC,
        "kin_debug_boost": KIN_DEBUG_BOOST,
    }
    if args.scenarios:
        scenario_ids = [s.strip() for s in args.scenarios.split(",")]
        scenarios = []
        for sid in scenario_ids:
            if sid not in scenario_map:
                print(f"Unknown scenario: {sid}. Valid: {', '.join(scenario_map)}", file=sys.stderr)
                return 1
            scenarios.append(scenario_map[sid])
    else:
        scenarios = list(DEFAULT_SCENARIOS)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_root / f"kin_lines_ab_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    command = " ".join(sys.argv)
    print(f"Kin-line A/B benchmark")
    print(f"  Scenarios: {[s.label for s in scenarios]}")
    print(f"  Seeds: {seeds}")
    print(f"  Duration: {args.seconds}s per run")
    print(f"  Output: {output_dir}")
    print()

    raw_results = _run_all_scenarios(scenarios, seeds, args.seconds, SCENARIO_ID)

    averaged: list[dict[str, Any]] = []
    for cfg in scenarios:
        matching = [r for r in raw_results if r["scenario"] == cfg.id]
        averaged.append(_average_results(matching))

    baseline = next((r for r in averaged if r["scenario"] == "kin_off"), None)

    for r in averaged:
        if baseline and r["scenario"] != "kin_off":
            r["delta_render_ms_vs_off"] = r["render_ms_mean"] - baseline["render_ms_mean"]
            r["delta_active_work_vs_off"] = r["active_work_mean"] - baseline["active_work_mean"]
        else:
            r["delta_render_ms_vs_off"] = 0.0
            r["delta_active_work_vs_off"] = 0.0

    summary_json = {
        "command": command,
        "timestamp": timestamp,
        "scenarios": [s.id for s in scenarios],
        "seeds": seeds,
        "seconds_per_run": args.seconds,
        "scenario_id": SCENARIO_ID,
        "raw_results": raw_results,
        "averaged_results": averaged,
    }

    json_path = output_dir / "summary.json"
    json_path.write_text(json.dumps(summary_json, indent=2, sort_keys=True), encoding="utf-8")

    md = _build_markdown(averaged, baseline, command, str(output_dir))
    md_path = output_dir / "summary.md"
    md_path.write_text(md, encoding="utf-8")

    print()
    print(md)
    print()
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
