# Primordial Implementation Program

This document turns the strategic roadmap into practical, bounded work for
future coding agents. It should stay tactical: what to do next, where the work
belongs, how to validate it, and what not to accidentally turn it into.

Current architecture reference: `docs/architecture_reference.md`.
Current human-facing guide: `docs/predator_prey_system_guide.md`.

## Current Project Status

Primordial is no longer at the beginning of the original milestone sequence.
Several earlier roadmap items are implemented:

- **Fixed-step runtime and instrumentation**: implemented in
  `primordial/runtime/`, integrated from `primordial/main.py`, with tests.
- **Performance/headroom work**: pygame and GPU renderer paths exist, kin-line
  and render-cache work has landed, and benchmark/probe tooling is present.
- **Lightweight observability**: HUDs, debug timing, CSV run logging,
  milestone logging, observability snapshots, and graphical probes exist.
- **Predator-prey ecology**: predator/prey roles, food cycles, zones,
  imperfect sensing, depth bands, collapse/game-over, and optional adaptive
  tuning machinery exist.
- **Persistence**: versioned world snapshots and predator-prey tuning sidecar
  persistence exist.
- **Settings UX**: the settings overlay is now categorized, readable,
  mouse-capable, cursor-aware, and split across metadata, layout, navigation,
  mouse, rendering, and runtime-action modules.
- **In-app help**: the Guide action now opens a renderer-owned help browser
  that loads `docs/predator_prey_system_guide.md`, parses Markdown headings
  into sections, supports search, mouse, keyboard, and scrolling, and keeps help
  state separate from settings.
- **In-game tutorial**: fresh normal-mode launches can open a guided onboarding
  overlay; `--tutorial` / `--show-tutorial` force replay; tutorial content,
  state, persistence, layout, mouse, and rendering are split into focused
  modules separate from settings and help.
- **Current-state documentation**: `docs/architecture_reference.md` and
  `docs/predator_prey_system_guide.md` were refreshed from code.

The next gap is not simulation capability. The next gap is user understanding:
the app has enough behavior that users need guided onboarding and richer
observability.

## Development Principles

Every milestone should preserve these rules:

- Protect simulation/rendering decoupling.
- Keep `primordial/main.py` as orchestration and event routing, not as the owner
  of overlay internals.
- Keep configuration defaults and validation in `primordial/config/`.
- Keep documentation content in docs or structured content files, not hardcoded
  into renderer logic.
- Keep parsing/loading models separate from rendering.
- Let settings UI, help UI, and tutorial UI share layout concepts without
  becoming one monolithic overlay file.
- Use pygame event screen coordinates for UI hit testing. Do not apply
  simulation/world transforms to overlay clicks.
- Keep cursor visibility intentional through `primordial/display/cursor.py`.
- Preserve keyboard support when adding mouse support.
- Add tests and smoke checks for UI/navigation work.

## Milestone Status Review

| Original Item | Decision | Current Notes |
| --- | --- | --- |
| M1 fixed-step simulation and instrumentation | Complete | Runtime helpers, fixed-step state, profile/session support, and tests exist. |
| M2 headroom and lightweight observability | Mostly complete | Renderer/backend work, probes, logs, and observability snapshots exist. Continue targeted performance work only when measurement justifies it. |
| M3 ecology deepening and imperfect sensing | Partially complete | Predator-prey includes imperfect sensing, zones, food cycles, role pressure, and tuning dials. Deeper strategy diversity remains valid but should wait behind help/tutorial. |
| M3.5 simulation persistence | Complete | Versioned world snapshots and predator-prey runtime/tuning state persistence exist. Future persistence work should be schema evolution, not first-version design. |
| M4 rich observability and analysis tooling | Partially complete | CSV logging, benchmark summaries, probes, inspect mode, and HUDs exist. Rich in-app evolution visualization remains future work. |
| M5 constrained depth-layer model | Complete as first ecological version | Predator-prey has surface/mid/deep bands, depth-aware sensing, food access, escape, and cross-band misses. Better visualization can be future observability work. |
| Settings overlay redesign | Complete | Recent refactor split metadata, navigation, layout, mouse hit regions, rendering, cursor behavior, and runtime actions. |
| Current-state docs refresh | Complete | Architecture and predator-prey guide now reflect current code. |
| M6 in-app documentation/help browser | Complete | Guide opens the in-app browser; parser/search/navigation/layout/mouse/rendering are split across focused modules. |
| M7 in-game tutorial/onboarding flow | Complete as first version | First-launch onboarding, CLI replay, settings Actions launch, broad highlights, pause restore, and tutorial sidecar persistence exist. |

## Immediate Next Milestones

Recommended order:

1. **M8: Richer Observability and Evolution Readability**
2. Expand help/tutorial content where new user-facing behavior needs it.
3. Then return to deeper ecology/strategy diversity where measurements justify it.

This order is intentional. The refreshed guide now powers in-app help. The
tutorial should use that knowledge and the help browser as support rather than
inventing a parallel explanation system.

## M6: In-App Documentation / Help Browser

Status: **Complete as first version.**

### Purpose

The old external-browser Guide workflow has been replaced as the primary path.
The app now has an in-app browser that reads the existing human-facing
documentation and makes it usable while the simulation is running.

### Scope

- Use `docs/predator_prey_system_guide.md` as the first content source.
- Parse Markdown headings and body text into a simple section model.
- Display sections in a modal overlay with:
  - left section navigation;
  - main reading area;
  - search;
  - scrolling;
  - mouse support;
  - keyboard support;
  - readable ocean/bioluminescent styling consistent with settings.
- Route the existing Guide/Documentation action to the in-app browser.
- Preserve a fallback or error status if the docs file is missing.
- Design the content model so other modes can eventually have help sections.

### Likely Files / Modules

- `primordial/help/document_model.py` for loading/parsing docs.
- Rendering modules under `primordial/rendering/`:
  - `help_overlay.py`
  - `help_layout.py`
  - `help_navigation.py`
  - `help_mouse.py`
- `primordial/runtime/settings_actions.py` for routing the Guide action.
- `primordial/main.py` only for high-level event routing if a new overlay state
  requires it.
- Tests under `tests/` for parser, search, navigation, and action routing.

### Architecture Notes

- Start simple: parse headings and content from Markdown. Do not build a full
  Markdown renderer unless a real need appears.
- Keep documentation text in docs files. Rendering code should receive parsed
  content, not contain a giant string copy of the guide.
- Reuse settings overlay layout ideas, but do not put help logic into
  `settings_overlay.py`.
- Help overlay hit testing should register rectangles from layout/draw logic,
  as the settings overlay does.
- Cursor visibility should follow interactive overlay rules.
- The Guide action uses the in-app browser as the primary path; any external
  browser helper should stay fallback-only.

### Validation

- Parser tests:
  - headings become sections;
  - empty/malformed sections are handled safely;
  - source file missing returns a clear error.
- Search tests:
  - title/body matches are found;
  - results navigate to the expected section;
  - search is case-insensitive.
- Overlay state tests:
  - section navigation bounds;
  - scrolling bounds;
  - keyboard and mouse actions preserve selected section;
  - Escape closes without applying settings changes.
- Runtime tests:
  - settings Guide action opens in-app help;
  - existing fullscreen/cursor behavior remains intentional.
- Smoke checks:
  - headless draw at common window sizes;
  - normal app startup;
  - settings overlay still opens and works.

### Non-Goals

- Do not create a new documentation authoring framework.
- Do not implement a full Markdown renderer.
- Do not add tutorial behavior.
- Do not remove the docs file from packaging.
- Do not collapse settings/help/tutorial UI into one generic mega-overlay.

### Risks

- Long documents can create wrapping and scrolling bugs.
- Search can become too broad or too slow if it tries to be a full text engine.
- Reusing settings code too directly could entangle unrelated UI state.
- Browser fallback behavior remains available as lower-level infrastructure, but
  the primary Guide action is now in-app.

## M7: In-Game Tutorial / Onboarding Flow

Status: **Complete as first version.**

### Purpose

Give new users a guided first-run path that explains how to use Primordial and
what they are seeing without requiring external reading first.

### Scope

- Run tutorial on first launch, using a stored user-state sidecar.
- Add a command-line option to force the tutorial for developers/testers.
- Make it launchable from settings/actions.
- Launch the simulation and control tutorial progression through overlay steps.
- Support Next / Back with mouse and keyboard.
- Pause or slow the simulation when a step needs a stable scene.
- Highlight important UI/world elements.
- Keep the first version linear and simple.

### Tutorial Content

App basics:

- what Primordial is;
- opening settings;
- opening help/documentation;
- pause/unpause;
- fullscreen/windowed behavior;
- HUD basics;
- reset behavior;
- mouse and keyboard basics.

Simulation basics:

- predators and prey;
- food particles;
- creature glyphs;
- trails and movement;
- hunting/fleeing;
- births and deaths;
- lineages and kin lines;
- zones;
- depth bands;
- food cycle/famine;
- game over/collapse;
- adaptive tuning at a simple high level;
- what evolution means in this simulation;
- what is currently hidden or subtle.

### Likely Files / Modules

- Tutorial data/model module:
  `primordial/tutorial/steps.py`.
- Tutorial runtime state/persistence modules:
  `primordial/tutorial/state.py` and `primordial/tutorial/persistence.py`.
- Rendering modules under `primordial/rendering/`:
  - `tutorial_overlay.py`
  - `tutorial_layout.py`
  - `tutorial_mouse.py`
- `primordial/utils/cli.py` for `--tutorial` / `--show-tutorial`.
- `tutorial_state.json` sidecar next to `config.toml`.
- `primordial/main.py` only for high-level routing and lifecycle hooks.

### Architecture Notes

- Use a declarative tutorial step structure:
  - `title`;
  - explanatory text;
  - target/highlight type;
  - optional UI/world anchor;
  - paused/slow/running state;
  - optional action required to continue.
- Tutorial state should be separate from simulation state where practical.
- The tutorial must not corrupt saved config, snapshots, or adaptive tuning
  history.
- First-launch completion state should be stored carefully in config or a small
  user-state sidecar.
- Highlight overlays should be clear and tasteful, not a pile of debug boxes.
- Cursor visibility should be shown while tutorial UI is interactive and hidden
  again afterward when appropriate.

### Validation

- Unit tests:
  - tutorial step schema;
  - next/back bounds;
  - first-launch flag behavior;
  - command-line force option parsing;
  - required-action step behavior if included.
- Overlay tests:
  - buttons and keyboard navigation;
  - hit rectangles align with drawn controls;
  - cursor visibility transitions.
- Runtime smoke:
  - first-launch path starts tutorial without changing user settings unexpectedly;
  - forced tutorial works;
  - closing/completing tutorial returns to normal simulation;
  - settings/help still work after tutorial closes.

### Non-Goals

- Do not build interactive missions or scoring in the first version.
- Do not require the user to perform complex actions to proceed.
- Do not teach every setting.
- Do not make tutorial text the only source of help; keep the guide as the
  deeper reference.

### Remaining Follow-Up

- Highlights are broad conceptual regions, not tracked moving world objects.
- The tutorial is linear and does not yet open linked help sections.
- Future content changes should remain declarative and tested.

### Risks

- First-launch state can annoy returning users if stored incorrectly.
- Pausing/controlling the sim from tutorial state can interfere with inspect,
  settings, or game-over state if not carefully routed.
- Highlighting world elements may require stable selectors for creatures, food,
  zones, or HUD regions.

## M8: Richer Observability and Evolution Readability

### Purpose

Make long-term adaptation easier to see after users can access help and basic
onboarding.

### Candidate Scope

- Trait trend summaries for speed, sense, efficiency, depth preference, and
  role-specific averages.
- Better death-cause visibility.
- Depth-band visualization improvements.
- More legible kill events.
- In-app views or exported reports that explain whether lineages are diverging.

### Notes

This should not be started as a vague "improve UX" pass. Each observability
feature should answer a concrete question a user currently cannot answer.

## M9: Deeper Ecology and Strategy Diversity

### Purpose

Continue the older roadmap goal of more durable branching, niches, and
strategy-level divergence.

### Candidate Scope

- Stronger tradeoffs.
- Sharper niches.
- More meaningful species/lineage concepts.
- Additional imperfect sensing variations only if they create measurable
  ecological tension.
- Environmental variation that does not overwhelm legibility.

### Notes

The project already has many dials. Future ecology should add new tensions, not
just more parameters.

## Standard Agent Workflow

For non-trivial work:

1. Read `docs/architecture_reference.md`, this implementation program, and the
   current roadmap.
2. Inspect code before assuming ownership boundaries.
3. Write a short implementation plan.
4. Keep edits scoped to the milestone.
5. Add or update tests with the implementation.
6. Run targeted tests, then the full suite when practical.
7. Run a headless smoke check for UI/runtime work.
8. Update `CHANGELOG.md`.
9. Make a meaningful git commit.

## Creating a Milestone Spec

Large milestones should still get a focused spec before implementation. Use
`docs/spec_M<N>.md` and `docs/acceptance_M<N>.yaml` when the work is broad
enough to need staged delivery. For smaller self-contained passes, this document
plus the user prompt may be enough.

Each spec should include:

- purpose;
- scope;
- likely files;
- architecture constraints;
- non-goals;
- risks;
- validation plan;
- human review gates where automation is insufficient.

## Final Guidance

The near-term program is not about adding more simulation machinery. It is about
making the existing world understandable from inside the app.

Build richer observability next. Then return to deeper ecology with
better user-facing context already in place.
