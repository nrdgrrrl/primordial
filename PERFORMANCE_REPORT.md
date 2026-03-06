# Performance Improvement Report (No Code Changes)

## Scope and framing

This report is based on a code review of the simulation/render pipeline, with an emphasis on frame-time stability for long-running fullscreen sessions. The current architecture is strong (simulation/render separation, spatial bucketing, cProfile path already present), so most upside now is in **render-cost control**, **high-population pairwise operations**, and **data-oriented hot-loop execution**.

---

## High-impact opportunities (prioritized)

### 1) Add an adaptive quality governor (frame-budget aware)

**Why this is likely #1:** The renderer performs many optional effects every frame (ambient, zone atmospherics, territory shimmer, kin/flock links, trails, particles, HUD/overlay), and boids/line effects can spike cost nonlinearly at population peaks.

**Observed in code:**
- Renderer tracks detailed per-stage timing (`events_ms`, `ambient_ms`, `links_ms`, `trails_ms`, `creatures_ms`, etc.), so the telemetry needed for adaptation already exists.
- Target FPS is fixed via `clock.tick(target_fps)`.

**Proposal:** Define quality tiers (Ultra/High/Medium/Low) and auto-step down/up based on rolling draw+sim budget (e.g., 60 FPS target → 16.67 ms budget).

**Tier knobs to scale dynamically:**
- Kin/flock line density (limit max pairs per lineage/flock).
- Trail resolution (skip every Nth historical point or reduce alpha passes).
- Territory shimmer layers/radii.
- Ambient particle count.
- Attack-line and death-particle counts.
- HUD update frequency (e.g., every 2–4 frames).

**Expected impact:** Smoother frame pacing with minimal perceived quality loss during stress.

---

### 2) Reduce pairwise O(n²) rendering work with neighbor culling structures

**Why:** Pair loops in line rendering are still pairwise within groups. At high lineage concentration or large flocks, this can become a major spike source.

**Observed in code:**
- Kin lines: all-pairs within each lineage bucket with distance check.
- Flock lines: all-pairs within each flock bucket with distance check.

**Proposal options:**
1. Spatial hash per lineage/flock (same pattern as food manager) to only compare local cells.
2. k-nearest cap per creature (draw only nearest 3–5 links).
3. Stochastic subsampling (stable seeded sample by lineage/flock id per frame window).
4. Hard line budget per frame (e.g., max 2k lines) with fair rotation across groups.

**Expected impact:** Major reduction of worst-case spikes in dense scenes.

---

### 3) Cache and incrementally update lineage statistics for territory shimmer

**Why:** Territory shimmer repeatedly computes centroid/spread from full member lists each frame; this is expensive and scales with population.

**Observed in code:**
- Each frame builds `lineage_creatures` buckets.
- Then computes `xs`, `ys`, sums, and std-dev-like calculations for top lineages.

**Proposal:** Maintain rolling lineage accumulators in simulation state:
- count, sum_x, sum_y, sum_x2, sum_y2 (and optionally wrapped-space handling).
- update on births/deaths/moves or at lower frequency (e.g., every 6 frames).

**Expected impact:** Lower constant factors on every frame; better scalability.

---

### 4) Decouple simulation tick and render tick (fixed-step sim, variable render)

**Why:** Right now one simulation step is coupled to each rendered frame. When rendering is overloaded, sim cadence also slows, distorting ecosystem dynamics.

**Proposal:**
- Fixed simulation timestep (e.g., 30 or 60 Hz) with accumulator.
- Render at display rate, interpolating visuals where useful.
- Under stress: drop render quality first, avoid changing sim correctness.

**Expected impact:** Better deterministic behavior and more graceful degradation.

---

### 5) Move selected hot loops to native speed paths (Cython/Numba/Rust extension)

**Why:** Python per-object loops dominate in boids forces and pair checks.

**Best candidates:**
- boid neighbor-force accumulation,
- creature update loop math,
- pairwise link candidate generation.

**Proposal:** Keep architecture, but compile narrow kernels. Start with one kernel and benchmark before/after.

**Expected impact:** Potentially very large CPU reduction without redesigning the app.

---

## Medium-impact improvements

### 6) Data-oriented representation for simulation state

Transition from object-heavy `Creature` iteration to SoA-like arrays for hot fields (`x,y,vx,vy,energy,age,...`) while retaining dataclass facade where needed. This improves cache behavior and unlocks vectorization paths.

### 7) Multi-process split: simulation worker + render process

Python GIL limits threaded CPU parallelism. A process split with shared memory/ring buffer snapshots can isolate simulation from render stalls and improve responsiveness.

### 8) Event-driven redraw shortcuts for static layers

Zone backgrounds are already cached (good). Extend this philosophy:
- update HUD text surfaces only when values change,
- recalc expensive overlays at reduced cadence (e.g., every 2–3 frames) and reuse between frames.

### 9) Overdraw/alpha optimization

The pipeline uses multiple full-screen alpha surfaces (`_line_surf`, `_attack_surf`, `_shimmer_surf`, theme trail surface). Consolidating passes or region-constrained draws can reduce fill-rate pressure, especially on integrated GPUs.

### 10) Memory churn minimization

Several frame paths allocate transient lists/dicts (`defaultdict(list)`, per-frame bucket maps, temporary coordinate lists). Reusing pools and preallocated buffers can shave GC overhead and improve frame consistency.

---

## “Out of the box” ideas

### A) Two-mode runtime: **Eco mode** vs **Showcase mode**

- **Eco mode:** lower visual complexity, stable thermals/power for 24/7 screensaver use.
- **Showcase mode:** all effects for demos.

Auto-select by battery state, thermal headroom, or time-of-day.

### B) Perceptual foveation (center-priority quality)

If user attention is likely centered (or if preview pane is tiny), render full detail in center and reduced effects near edges. For fullscreen art this can be nearly invisible but saves cost.

### C) Temporal interleaving of expensive effects

Split heavy effects across alternating frames:
- frame N: kin/flock lines,
- frame N+1: territory shimmer refresh,
- frame N+2: higher-cost ambient updates.

Perceived continuity remains high while average frame time drops.

### D) Dynamic population budgeting by frame health

Instead of static `max_population`, expose a soft auto-budget that nudges reproduction threshold/food spawn to keep frame time in target band.

---

## Should you abandon pygame?

Short answer: **not immediately**. You likely have substantial headroom left without a renderer rewrite.

### What pygame currently gives you
- Fast iteration and portability.
- Adequate 2D primitives for this project.
- Existing architecture already tuned around it.

### Where pygame hurts
- CPU-bound draw loops and alpha compositing in Python-heavy paths.
- Limited GPU pipeline leverage compared with modern GL/Vulkan-first frameworks.

### Better alternatives (if you do decide to migrate)

1. **Moderngl / pyglet / vispy (GPU-first 2D/instanced rendering)**
   - Best when you want to keep Python but offload draw/transform work to GPU.
   - Biggest upside for trails, particles, links, glyph instances.

2. **Godot (GDExtension/Python bridge optional)**
   - Strong rendering pipeline, tooling, and batching.
   - Heavier migration and ecosystem shift.

3. **Rust/C++ simulation core + Python or engine front-end**
   - Maximum long-term performance and determinism.
   - Highest complexity cost.

4. **“Nothing” (headless simulation + occasional frame emit)**
   - If this were analytics-first, headless makes sense.
   - For a visual screensaver product, removing realtime rendering undermines core value.

### Recommended migration strategy

- **Phase 1 (stay on pygame):** implement adaptive quality + pairwise culling + cadence decoupling.
- **Phase 2:** prototype one GPU-backed renderer path for just links/trails.
- **Phase 3:** decide based on measured gains whether full migration is justified.

This de-risks effort and avoids “rewrite first, benchmark later.”

---

## Suggested benchmark plan (before touching architecture)

1. Define scenarios:
   - energy mode @ pop 150/220,
   - boids mode @ pop 150/300,
   - worst-case lineage concentration.
2. Capture:
   - p50/p95 frame time,
   - sim_ms vs draw_ms split,
   - max spike, dropped-frame count.
3. A/B each optimization independently.
4. Keep a “visual acceptability” checklist (art quality regressions are easy to miss in numeric-only tuning).

---

## 30-day execution roadmap

### Week 1
- Add frame-budget governor design doc + runtime telemetry dashboards.
- Implement manual quality tiers first (no auto switching yet).

### Week 2
- Implement kin/flock line budgets and culling.
- Add reduced-cadence shimmer/HUD updates.

### Week 3
- Add auto quality scaling and hysteresis.
- Add fixed-step simulation loop option and compare behavior.

### Week 4
- Prototype one native/GPU acceleration path on a single hotspot.
- Decide go/no-go for broader renderer migration.

---

## Final recommendation

The highest ROI path is to **optimize within current pygame architecture first**, because your bottlenecks appear to be specific hot loops and effect density rather than an immediate hard limit of pygame itself. A full migration should be treated as a **measured second step** after adaptive quality and pairwise-culling wins are captured.
