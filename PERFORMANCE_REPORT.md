# Performance Improvement Report (No Code Changes)

## Scope and framing

This report reviews the current simulation/render pipeline with a focus on frame-time stability for long-running fullscreen sessions. The architecture is already good (simulation/render separation, spatial bucketing, built-in profiling mode), so the biggest upside now is in **render-cost governance**, **pairwise workload capping**, **hot-loop acceleration**, and a **phased path to GPU/alternative-language execution where it makes sense**.

---

## Executive summary

- **Do not rewrite immediately.** There is still large ROI available inside the current architecture.
- **Top 3 near-term wins:** adaptive quality governor, pairwise line-budget/culling, and decoupled sim/render cadence.
- **GPU is absolutely possible** and likely valuable for links/trails/particles first.
- **Alternative language reimplementation is viable**, but should be scoped to hotspots first (simulation kernels or renderer path), not a big-bang rewrite.

---

## High-impact opportunities (prioritized)

### 1) Add an adaptive quality governor (frame-budget aware)

**Why this is likely #1:** renderer work is composited from many optional effects each frame, and dense boids/line scenes can spike nonlinearly.

**Observed in codebase behavior:**
- Stage-level timing is already tracked.
- Target FPS is enforced, but quality does not currently adapt to budget misses.

**Proposal:** Define quality tiers (Ultra/High/Medium/Low) and auto-adjust using rolling frame-time and hysteresis.

**Tier knobs:**
- Max kin/flock links per frame.
- Trail sampling rate.
- Shimmer layers/radii.
- Ambient particle count.
- Animation particle counts.
- HUD refresh cadence.

**Expected impact:** smoother frame pacing under stress with minimal visual degradation.

---

### 2) Cap O(n²) pairwise line work with neighborhood culling + budgets

**Why:** kin/flock links are pairwise within groups and can dominate worst-case frames.

**Proposal options (can combine):**
1. Spatial hash per lineage/flock.
2. k-nearest links per creature.
3. Deterministic stochastic sampling per group.
4. Global line budget per frame with round-robin fairness.

**Expected impact:** large p95/p99 frame-time improvements in dense clusters.

---

### 3) Incremental lineage statistics for territory shimmer

**Why:** rebuilding lineage buckets + full spread math every frame scales poorly with population.

**Proposal:** maintain rolling lineage accumulators (`count/sum/sum_sq`) and refresh full recompute at reduced cadence.

**Expected impact:** reduced per-frame CPU overhead and steadier frame-time.

---

### 4) Decouple simulation tick from render tick

**Why:** render overload currently slows simulation cadence too, affecting ecosystem behavior.

**Proposal:** fixed-step simulation (30/60 Hz) + variable-rate rendering with interpolation where needed.

**Expected impact:** deterministic sim behavior and graceful visual degradation.

---

### 5) Accelerate hot kernels with native execution paths

**Why:** Python object-loop overhead is high in boids/neighbor math.

**Best first kernels:**
- boid force accumulation,
- motion update math,
- link candidate generation.

**Paths:** Cython / Numba / Rust extension.

**Expected impact:** significant CPU reduction without total rewrite.

---

## Medium-impact improvements

### 6) Data-oriented simulation storage

Migrate hot fields to SoA buffers while preserving current API shape where practical.

### 7) Process-level split (simulation worker + renderer)

Avoid GIL contention and isolate simulation cadence from render stalls.

### 8) Recompute expensive overlays at lower cadence

Cache/reuse outputs for effects that are perceptually tolerant to 15–30 Hz updates.

### 9) Reduce alpha overdraw pressure

Consolidate full-screen alpha passes and optionally constrain effects to dirty/active regions.

### 10) Reduce allocation churn

Reuse per-frame containers/buffers to minimize GC-related jitter.

---

## Out-of-the-box ideas

### A) Eco vs Showcase runtime modes

Automatically pick quality profile based on thermals/battery/time-of-day.

### B) Temporal interleaving of expensive effects

Alternate heavy effects across frames to flatten frame-time spikes.

### C) Adaptive population budget tied to frame health

Use frame budget feedback to gently tune food/reproduction pressure.

### D) Center-weighted quality (perceptual foveation)

Keep peak quality near visual focus and degrade at periphery.

---

## Should you abandon pygame?

Short answer: **not yet**.

### Why keep it for now
- Existing codebase maturity and portability.
- Fast iteration.
- Enough headroom remains from algorithmic + quality-governor optimizations.

### Where pygame is limiting
- Python-heavy draw loops.
- CPU-side alpha compositing overhead.
- Limited modern GPU pipeline ergonomics compared to GL/Vulkan-first stacks.

### Practical decision rule

Move off pygame only if, **after tier/culling/kernel optimizations**, you still miss your p95 frame budget on target hardware.

---

## Re-implementing in other languages: best candidates

You asked for concrete language alternatives. Below is a pragmatic shortlist.

### 1) **Rust** (best all-around long-term candidate)

**Why it fits:**
- High performance + memory safety.
- Excellent for deterministic simulation core.
- Strong ecosystem for desktop + GPU (`wgpu`).

**How to apply incrementally:**
- Start with Rust simulation core as a Python extension (PyO3/maturin) while keeping existing renderer.
- Or build a Rust+wgpu standalone renderer once simulation parity is proven.

**Pros:** max performance potential, robust architecture.
**Cons:** higher engineering complexity, steeper team learning curve.

**Best for:** long-lived project with emphasis on correctness and sustained performance.

---

### 2) **C++** (highest raw performance, highest operational complexity)

**Why it fits:**
- Mature high-performance path for both simulation and rendering.
- Easy access to SDL2/OpenGL/Vulkan ecosystems.

**Pros:** top-end performance and ecosystem breadth.
**Cons:** memory-safety risks, build/tooling complexity, slower iteration.

**Best for:** teams already strong in C++ who need absolute control/perf.

---

### 3) **Go** (good concurrency, weaker fit for graphics-heavy workloads)

**Why it may fit partially:**
- Good for orchestrating simulation/services.
- Simpler concurrency model.

**Limitations for this project:**
- Less natural for advanced realtime rendering compared to Rust/C++.

**Best for:** backend/control-plane style components, not primary renderer choice.

---

### 4) **Zig** (interesting systems option, smaller ecosystem)

**Why consider:**
- Performance and explicit control.
- Cleaner low-level ergonomics than C in many cases.

**Risk:** ecosystem/tooling maturity for this exact desktop + GPU stack is smaller.

**Best for:** experimental systems-focused teams.

---

### 5) **C# with Unity/Godot C#** (engine-first option)

**Why it fits:**
- Very strong rendering/tooling pipeline out of the box.
- Faster delivery for visually rich effects if engine constraints are acceptable.

**Trade-off:** less control over low-level determinism and runtime footprint.

**Best for:** rapid visual feature development with moderate performance needs.

---

## Language recommendation ranking for this project

1. **Rust (recommended)**: best balance of performance, safety, GPU path viability.
2. **C++**: strong but heavier engineering burden.
3. **C# engine path**: fastest visual tooling, less low-level control.
4. **Go/Zig**: niche fits; not first choice for this exact workload.

---

## GPU feasibility: yes, and likely high ROI

GPU use is not only possible; this workload is a good candidate for **partial GPU offload**.

### Best GPU-first targets

1. **Links (kin/flock):** large number of simple line primitives.
2. **Trails:** additive/alpha blended geometry over time.
3. **Particles/ambient/shimmer:** classic GPU-friendly instanced draws.
4. **Glyph transforms:** rotation/pulse handled in shaders.

### Simulation on GPU?

Possible, but higher complexity:
- Compute-shader boids can be very fast.
- Harder to maintain/debug and integrate with current Python architecture.

**Recommendation:** do rendering GPU first, simulation GPU later only if needed.

### Technology options

- **Python + moderngl/pyglet/vispy:** lowest migration friction for GPU rendering.
- **Rust + wgpu:** strongest long-term architecture and portability.
- **Engine route (Godot/Unity):** high productivity, less bespoke control.

### Minimal-risk GPU adoption sequence

1. Keep simulation as-is.
2. Replace only links/trails rendering with GPU path.
3. Benchmark p95 frame-time delta.
4. Expand GPU scope to particles/glyph passes if ROI holds.

---

## Migration strategies (from least to most disruptive)

### Strategy A: Stay Python, add GPU renderer path (recommended first)

- Keep current sim logic.
- Offload visual hotspots to GPU.
- Lowest risk and fastest measurable wins.

### Strategy B: Hybrid Python + Rust kernels

- Move boids/neighbor kernels to Rust extension.
- Preserve current architecture and UX.

### Strategy C: Full Rust rewrite (sim + render)

- Maximum long-term performance and control.
- Highest rewrite risk and delivery time.

### Strategy D: Engine migration (Godot/Unity)

- Strong toolchain and visual pipeline.
- Requires re-architecture and acceptance of engine constraints.

---

## Suggested benchmark plan

1. Scenarios:
   - energy mode @ population 150 and 220,
   - boids mode @ 150 and 300,
   - intentionally dense lineage/flock clusters.
2. Metrics:
   - p50/p95/p99 frame-time,
   - sim vs draw split,
   - spike frequency and duration,
   - power draw/thermals for long runs.
3. A/B method:
   - one change at a time,
   - 3-run median,
   - fixed seed where possible.
4. Acceptance:
   - maintain visual quality thresholds,
   - no simulation behavior regressions.

---

## 30-day execution roadmap

### Week 1
- Add quality-tier controls + instrumentation dashboard.
- Define benchmark harness and target envelopes.

### Week 2
- Implement link culling/budgeting and reduced-cadence expensive overlays.
- Capture p95/p99 impact.

### Week 3
- Prototype GPU links/trails pass (Python GPU stack).
- Evaluate perf gains and visual parity.

### Week 4
- Prototype Rust kernel for one simulation hotspot.
- Decide next quarter path: stay hybrid vs wider migration.

---

## Final recommendation

1. **Immediate:** optimize current architecture (quality governor + pairwise budgets + fixed-step sim).
2. **Near-term:** add targeted GPU rendering for links/trails/particles.
3. **Strategic:** if still constrained, move hot simulation kernels to **Rust**; reserve full rewrite for when measured evidence justifies it.

This approach gives fast wins now, preserves optionality, and avoids risky rewrites before the bottlenecks are quantified.
