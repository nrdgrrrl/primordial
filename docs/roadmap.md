# Primordial Roadmap Rewrite

## Purpose

This document reframes the performance and architecture discussion around the actual long-term goal of the project.

The goal is not just to render more creatures or hit a better benchmark number. The goal is to build a mesmerizing living system that remains beautiful on screen while also becoming a genuinely richer evolutionary simulation over time. That means the project has to protect two things at once:

1. visual spectacle
2. simulation integrity and future evolvability

Performance work should be judged by how well it serves those goals.

---

## Core Position

The project should not pursue a major rewrite yet.

The current architecture is already stronger than a casual Python simulation project. It has meaningful separation between simulation and rendering, a disciplined event model, deterministic and heritable genome-driven agents, spatial bucketing, and evidence of substantial optimization gains already achieved.

The next stage should focus on solidifying simulation integrity first, buying headroom early, and then using that room to deepen the ecology. A constrained depth-layer system should be treated as the next major simulation expansion after that foundation is in place.

---

## What Matters Most

The project is trying to achieve two things that can easily conflict if approached carelessly:

- It should remain compelling as an ambient piece of eye candy.
- It should gradually become a system capable of more genuine emergent structure, including long-term divergence, niche formation, predator/prey strategy differences, and species-like branching.

That means not all simplifications are equal.

Visual compromises are often acceptable if they preserve the underlying world.
Simulation compromises are much more dangerous, because they can alter the actual evolutionary history of the ecosystem.

The key principle is:

**Protect simulation truth, spend rendering budget artistically.**

---

## Why Fixed-Step Simulation Comes First

One issue stands above all others: if rendering load can slow the simulation itself, then the ecosystem’s history changes under graphical stress.

That is not just a performance problem. It is a scientific and design problem.

If two lineages survive or fail because a visual effect caused the world to advance more slowly, then the system is no longer telling the truth about its own rules. For a project centered on emergence and long-run behavioral divergence, that is unacceptable.

So the first architectural priority should be:

- fixed-step simulation
- variable-rate rendering
- clear measurement of sim time versus render time

This protects the world from the screen.

It also creates a stable foundation for every later decision.

---

## Recommended Roadmap

### Phase 1: Protect Sim/Render Integrity

This phase should happen before deeper ecological work.

#### Goals
- Make simulation cadence independent from render load.
- Preserve deterministic or at least stable long-run system behavior under varying visual cost.
- Improve measurement so the real bottlenecks are visible.

#### Recommended work
- Convert to fixed-step simulation with variable-rate rendering.
- Instrument the main loop so simulation time, render time, and frame pacing are separately observable.
- Add hard caps to catastrophic visual paths such as pairwise line work and expensive overlays.
- Keep adaptive quality simple at first, just enough to prevent spikes from compromising the whole experience.

#### Why this phase is first
Without this, every later performance or ecology decision is built on unstable ground.

---

### Phase 2: Buy Headroom Early, Add Lightweight Observability

Once simulation truth is protected, the next priority should be buying compute headroom before deeper ecological complexity is added.

This phase should also introduce the first tier of ecological observability. The goal is not rich dashboards yet. The goal is to avoid tuning future ecology changes blind.

#### Why move this up?
Richer emergence will almost certainly require more computational budget. New ecological mechanisms, more decision logic, more state, and denser interaction patterns all consume CPU and memory. If headroom is not created early, future biology will be shaped by current bottlenecks instead of by the actual design goals.

#### Primary targets
1. **Rendering acceleration first**
   - Move the highest-value visual hotspots toward GPU-assisted rendering or a more efficient render path.
   - Best early candidates include kin/flock links, trails, particles, shimmer-like effects, and alpha-heavy layered passes.

2. **Targeted simulation acceleration second**
   - After measurement, move one or two simulation hotspots into a native or compiled path if needed.
   - Best candidates are likely boid force accumulation, neighbor math, and dense interaction kernels.

3. **Tier 1 observability**
   - Add lightweight, decision-oriented ecological telemetry before serious ecology expansion begins.
   - Focus on simple measurements that reveal whether changes are producing branching, coexistence, or collapse.

#### Tier 1 observability should include
- lineage divergence metrics
- phenotype cluster summaries
- basic strategy-ratio logging
- lightweight zone occupancy summaries
- simple run-to-run comparable CSV or JSON logs

#### Why this order?
The current project still appears to spend substantial cost on rendering richness. Solving that first may buy enough room that deeper ecology can be added without an immediate architectural upheaval. At the same time, lightweight ecology telemetry needs to be in place before tradeoff and niche changes start landing.

---

## On Running the Simulation on a Separate CPU Core

This idea is promising, but only in certain forms.

### What not to do first
A simple Python thread for simulation and another for rendering is unlikely to deliver the hoped-for gains if the simulation remains CPU-bound Python code. The GIL will limit the value of this approach.

### Better options
1. **Process-level separation**
   - One process handles simulation.
   - One process handles rendering.
   - This can isolate simulation cadence from render stalls and avoid some GIL issues.
   - But it only works well if state transfer is designed carefully.

2. **Native or compiled simulation kernels**
   - Move specific heavy kernels out of pure Python.
   - This can buy much of the practical benefit without the architectural cost of a full process split.

### Recommendation
Do not begin with threads.

If additional simulation headroom is needed after render-side improvement, first try targeted acceleration of hot kernels. Only consider a process-level split if measurement shows that simulation itself remains a hard blocker and the team is willing to design a compact state boundary between sim and render.

---

## Phase 3: Deepen the Ecology

Once the system is protected, there is more headroom, and lightweight observability is available, the next priority should be ecological depth.

The goal here is not simply to add more traits or more knobs. The goal is to make the world more capable of producing durable, branching, strategy-level differences.

That means focusing on evolvability rather than raw complexity.

### Important principle
Many simulations look evolutionary while actually producing only drift, oscillation, or parameter sorting. Genuine emergent structure needs selective pressures and tradeoffs that support different viable ways to live.

### What deeper ecology should emphasize

#### 1. Stronger tradeoffs
No one trait bundle should dominate everywhere.

Examples:
- speed should carry higher energetic cost
- long lifespan may require slower maturation or lower reproductive output
- stronger perception may require higher maintenance cost
- safer schooling behavior may reduce exploration or adaptability

The goal is to prevent one universal winner from flattening the ecosystem.

#### 2. Sharper niches
Zones and food cycles are a good start, but niches should become more behaviorally and ecologically meaningful.

The simulation should reward different strategies in different conditions, not just produce cosmetic regional variation.

#### 3. Temporal variation
If the world is too static, evolution often settles into repeating equilibria.

Dynamic environmental pressures such as moving resources, seasonal shifts, temporary danger zones, or fluctuating prey refuge patterns can keep the fitness landscape open and encourage branching.

#### 4. Better species logic
A future species concept should be based less on a visual or hue threshold and more on sustained functional divergence, lineage persistence, or ecological differentiation.

The point is not taxonomic realism for its own sake. The point is to make “new species” reflect something real in the world.

#### 5. Imperfect sensing
Perfect sensing flattens an important part of the ecological problem. If organisms can always act on clean local knowledge, one major source of strategy differentiation disappears.

Introducing imperfect sensing can create:
- ambush versus scouting tradeoffs
- false positives and wasted pursuit
- prey hiding value
- sensory specialization
- more meaningful environmental complexity

This should likely be introduced before the depth-layer system so its ecological effects can be understood on their own.

Possible directions include:
- distance-based uncertainty
- directional blind spots
- noisy target estimates
- delayed updates
- different acuity for food versus predators versus prey
- heritable sensing reliability, not just sensing radius

---

## Why More Traits Alone Is Not the Answer

A common trap in evolutionary simulations is adding many more parameters and calling that complexity.

That usually produces more tuning burden, not more emergence.

The better question is:

**What new forms of ecological tension would allow lineages to become different in kind, not just degree?**

The system should aim for:
- more expressive phenotype
- more ecological variety
- more stable coexistence of strategies
- more persistent lineage differentiation

Raw agent count is secondary to those goals.

---

## Phase 3.5: Simulation Persistence, Save and Resume

As the project becomes both more beautiful and more historically meaningful, persistence becomes more important.

If the world is supposed to accumulate real evolutionary history, it is worth considering whether it should resume rather than restart.

### Why this matters
- long-running ecosystems can preserve lineage history across sessions
- the project feels more like a living world and less like a transient effect
- deeper simulation becomes more meaningful when progress can continue

### Recommended scope for the first version
Focus on simulation persistence first, not full visual persistence.

That means:
- save enough simulation state to resume the world faithfully
- do not try to preserve transient renderer state at first
- rebuild caches and allow visual flourishes to restart naturally on load

### Likely contents of saved state
- all creature state and genomes
- lineage and ID allocator state
- food state
- world or zone state that materially affects future evolution
- cycle phases and environmental state
- RNG state if continuity quality matters
- save-format versioning from the start

### Why this should be its own milestone
Persistence has real architectural implications and should not be smuggled in as a side effect of ecology work. It deserves a clean scope and a versioned format.

---

## Phase 4: Richer Observability and Analysis Tooling

Observability is still important, but it should now be understood as a two-tier system.

Tier 1 exists earlier to support ecology tuning.
Tier 2 belongs here, once the ecosystem is mature enough to justify deeper interpretation and comparison tooling.

### Tier 2 observability should include
- replay tooling
- seeded comparison harnesses with report output
- visual dashboards
- long-run comparative ecology views
- richer zone occupancy and lineage history visualization

### What this phase should answer
- Are lineages actually diverging?
- Are niche-specialized forms persisting?
- Is the ecosystem collapsing into one dominant strategy?
- Are environmental pressures producing qualitatively different histories?

This phase should support both tuning and understanding.

---

## Phase 5: Next Major Simulation Expansion, Constrained Depth Layer

This should be the next major simulation enhancement after the first phases are reasonably in place.

Not full 3D.
Not 2.5D presentation work.
A constrained ecological depth layer.

### Why this is promising
The project’s current world is fundamentally 2D. That makes it legible and manageable, but it also limits the kinds of coexistence and predator/prey behavior that can evolve.

Adding a bounded depth dimension could create a powerful new axis for ecological differentiation without requiring a full volumetric simulation rewrite.

### What this would add
- resource layers at different depths
- predator/prey encounters filtered by depth overlap
- refuge behaviors based on depth preference
- migration between depth bands
- lineage specialization around surface, midwater, or deep behaviors
- a new axis for niche partitioning and strategy divergence

### Why this is so appealing
It adds more room for evolution to branch.

That matters more than adding graphical complexity.

A constrained depth layer could produce:
- more persistent coexistence
- stratified ecosystems
- ambush versus pursuit specializations
- foraging specializations
- more legible ecological difference between lineages

### Interaction with sensing
Once imperfect sensing exists, the depth layer can later modulate it further.

Examples:
- poorer cross-depth detection
- visibility differences by depth band
- lineage-specific depth acuity
- better sensing within a preferred band than across bands

This is another reason to add imperfect sensing first and then layer depth on top.

### Why not full 3D yet?
Full 3D would multiply simulation cost, rendering complexity, tuning difficulty, and visual legibility problems all at once.

The depth-layer approach is much more disciplined. It creates a third ecological axis without forcing the whole project into a true 3D engine before the foundations are ready.

### Suggested implementation shape
- add a bounded `depth` state or trait
- make food, hazards, or comfort ranges partially depth-dependent
- make detection and attack success depend on both planar distance and depth separation
- let some lineages evolve depth preferences or tolerances
- keep rendering straightforward and functional at first, enough to make depth readable without prioritizing spectacle work yet

This is not a graphics trick.
It is an ecological expansion.

That is why it belongs near the end of this roadmap as the next major simulation phase.

---

## Final Position

The project should not chase glamour in the wrong order.

The right sequence is:

1. protect simulation integrity
2. buy headroom early and add lightweight observability
3. deepen ecology, including imperfect sensing
4. add simulation persistence through save and resume
5. build richer observability and analysis tooling
6. introduce a constrained depth-layer system as the next major simulation expansion

This keeps the system honest, creates room for future growth, and points development toward the actual long-term goal: not just prettier motion, but a world capable of producing surprising evolutionary history.

The project becomes most interesting when the eye candy is the visible trace of something real.

That should remain the guiding principle for every next phase.

