# Changelog

All notable changes to Primordial are documented in this file.

## [2026-05-22] — fix: restore HUD-gated environmental zone labels

Restored the original environmental zone labels so `Warm Vent`, `Open Water`,
`Kelp Forest`, `Hunting Ground`, and `Deep Trench` appear again when the HUD
is visible.

What changed:
- Reused the original `b65edf2` zone-label styling and placement code instead
  of inventing a new label system.
- Restored the missing label layer on the GPU predator/prey renderer, which
  had preserved zone backgrounds but omitted the HUD-gated zone names.
- Kept the existing pygame renderer behavior intact while sharing the recovered
  label blit logic between both renderers.

Tests:
- Added GPU renderer regression coverage for HUD-visible and HUD-hidden zone
  label drawing behavior.

## [2026-05-22] — feat: add eco-morphological epistasis

Added the first real phenotype layer to Primordial so existing genome traits
now interact to produce effective ecological modifiers without mutating the raw
genome.

What changed:
- Added `primordial/simulation/phenotype.py` with deterministic effective
  modifiers for speed, movement cost, metabolic cost, sensing, food
  efficiency, reproduction burden, predation contact, flee agility, and depth
  behavior.
- Wired phenotype translation into energy, predator-prey, boids, and drift
  movement/sensing/reproduction seams while preserving near-legacy behavior
  when epistasis is disabled.
- Added `simulation.epistasis_enabled` and `simulation.epistasis_strength`
  config controls, settings-overlay metadata, and snapshot persistence.
- Added HUD, observability snapshot, and predator-prey CSV summaries for
  emerging body-plan strategies and average phenotype modifiers.
- Updated help/docs to describe simple epistasis honestly and removed the old
  claim that Primordial could not model it.

Tests:
- Added focused phenotype unit tests plus enabled/disabled headless smoke
  coverage across modes.
- Extended persistence, benchmark observability, run logging, and settings
  serialization coverage for the new phenotype/config paths.

## [2026-05-22] — fix: remove visual theme from settings UI

Removed the `Visual Theme` row from the settings UI so the in-app settings
overlay and launcher config screen now only expose backend, fullscreen, target
FPS, and HUD controls in the Display area.

Docs and tests:
- Updated the settings help text and guide docs to match the slimmer Display
  category.
- Added a regression assertion that `build_settings_fields()` no longer
  includes `visual_theme`.

## [2026-05-22] — fix: repair help browser scrolling

Fixed the in-app Help browser so sidebar and content scrolling now behave
as a real scrollable view instead of snapping back during draw.

Root cause:
- The sidebar was still being auto-scrolled toward the selected section from
  inside `_draw_sidebar()`, so wheel scrolling and drag scrolling would move
  briefly and then get pulled back on the next frame.
- The scrollbar track and thumb were not represented as distinct hit regions,
  so clicks could not reliably distinguish dragging the thumb from clicking
  the track.

Behavior now:
- Mouse wheel over the left sidebar scrolls the sidebar tree only.
- Mouse wheel over the right content pane scrolls the article body only.
- Sidebar and content scrollbar thumbs are separately hittable and draggable.
- Track clicks page-scroll instead of starting a drag.
- Scroll offsets are clamped after wheel, drag, collapse/expand, and search
  changes.
- Keyboard selection still auto-scrolls the sidebar into view, but only when
  selection changes.

Tests:
- Added coverage for sidebar wheel persistence, content wheel isolation,
  sidebar/content thumb dragging, and scroll clamping after collapse/search.
- Full `tests/` suite passes: 408 tests.

## [2026-05-21] — fix: replace help tabs with expandable sidebar

Replaced the horizontal document tab strip in the Help browser with a
vertical expandable/collapsible sidebar tree, added visible scrollbars
for sidebar and content pane, and improved text wrapping throughout.

Sidebar tree:
- Each registered help document is a top-level group in the left sidebar.
- Clicking a group heading expands/collapses its child sections.
- The active group and active section are visually highlighted.
- Left key collapses an expanded group; Right key expands a collapsed group.
- Enter/Space toggles groups or selects sections.
- Default: first document (Start) expanded, all others collapsed.
- Selecting a section in a collapsed group auto-expands that group.

Scrollbars:
- Visible scrollbar in sidebar and content pane where content overflows.
- Scrollbar thumb size reflects visible/total row ratio.
- Scrollbar thumb is draggable with mouse.
- Mouse wheel scrolls sidebar when cursor is over sidebar, content otherwise.

Text wrapping:
- Sidebar group and section labels wrap to available width (up to 3 lines).
- Content pane paragraphs wrap to available width with hanging bullet indent.
- Footer hint wraps to multiple lines.
- Header title and subtitle no longer cut off.

Layout:
- Removed doc_tabs_rect and nav_rect from HelpOverlayLayout.
- Added sidebar_rect, sidebar_scrollbar_rect, content_scrollbar_rect.
- Sidebar width set to 34% of available width (moderate increase).
- Gave vertical space formerly used by doc tab row back to sidebar/content.
- HelpOverlay constructor no longer takes document/doc_id arguments.
- Navigation loads all documents eagerly and tracks state internally.

Search:
- Search filters the sidebar tree to matching groups/sections.
- Matching groups auto-expand while search is active.
- Clearing search restores the user's pre-search expanded/collapsed state.

Shortcuts preserved:
- H opens Help, U toggles HUD (unchanged).
- Settings overlay Help action shortcut remains H.
- No ? or F1 Help shortcuts reintroduced.
- Bottom action bar shows H Help and U HUD (unchanged).

Code:
- Rewrote `primordial/rendering/help_navigation.py` with HelpNavItem model
  and expandable tree state tracking (selected_doc_id, selected_section_index,
  expanded_groups, sidebar_scroll, focused_sidebar_index, search state).
- Rewrote `primordial/rendering/help_overlay.py` to draw sidebar tree
  with group/section rows, visible scrollbars, and improved text wrapping.
- Rewrote `primordial/rendering/help_layout.py` with sidebar/content
  scrollbar rects, removed doc_tabs/nav_rect fields.
- Updated `primordial/rendering/help_mouse.py` with scrollbar hit region
  flags and doc_id field.
- Removed doc_tab hit regions, _draw_doc_tabs, _cycle_document.
- Navigation now uses `sidebar_items` built from HelpNavItem tree instead
  of flat `visible_section_indices`.

Tests:
- 53 tests covering sidebar tree model, group expand/collapse, section
  selection, search behavior, scrollbar hit regions, text wrapping, and
  layout invariants.
- No doc_tab hit region tests (tabs removed).
- All 403 project tests pass.

## [2026-05-21] — fix: organize in-app help and normalize help shortcuts

Changed Help from a buried Settings sub-action to a top-level runtime
feature, reorganized the help content from one giant 48-section document
into five curated tabbed documents, fixed nav scrolling, and corrected
all shortcut mappings.

Shortcuts:

- `H` opens Help from the main simulation (was `?`/`F1`).
- `U` toggles the HUD (was `H`).
- `?` and `F1` no longer open Help.
- Settings overlay Help action shows keyboard shortcut `H` (was `?`).

Help content:

- Split `docs/primordial_guide.md` (48 flat sections) into five focused
  in-app help documents with short tab labels:
  - "Start" (`help_quick_start.md`): what Primordial is, screen elements,
    basic controls, HUD reading.
  - "Organisms" (`help_organisms.md`): what organisms are, genome traits,
    reproduction, mutation, lineages, evolution, model limits.
  - "Reading" (`help_reading_creatures.md`): visual morphology, what you
    can/cannot infer, limits of visual inference, watching evolution.
  - "Predator-Prey" (`help_predator_prey.md`): predator/prey behavior,
    depth bands, scarcity, food cycles, game over, adaptive tuning.
  - "Controls" (`help_controls_settings.md`): runtime controls, settings
    guide, tutorial, save/load, other modes, glossary.
- `HELP_DOCUMENTS` registry now has five entries (was one).
- `DEFAULT_HELP_DOC_ID` changed from `primordial_guide` to `quick_start`.
- Tab key cycles help documents (was toggling search focus in single-doc
  mode).
- Help browser doc tab strip visible again (was hidden for single doc).

Nav scrolling fix:

- Mouse wheel over the left nav panel no longer snaps the scroll position
  back to the selected item on every draw. `ensure_selected_nav_visible`
  now skips when the scroll was set by a wheel event, and only fires after
  keyboard selection, click selection, or search changes.
- Nav wheel scroll amount increased from 1 to 3 rows per notch.

Code:

- Renamed `bundled_primordial_guide_path()` to `bundled_help_doc_path()`.
- Updated `_predator_prey_help_path()` to resolve `help_quick_start.md`.
- Action bar normal shortcuts: `H Help`, `U HUD` (was `H HUD`, `? Help`).
- Action bar game-over shortcuts: `U HUD` (was `H HUD`).
- Settings overlay Help action: shortcut `H` (was `?`).
- Keyboard handler: `pygame.K_h` opens Help, `pygame.K_u` toggles HUD,
  removed `pygame.K_QUESTION`/`pygame.K_F1` Help handling.

Docs:

- Updated `docs/primordial_guide.md`, `docs/predator_prey_system_guide.md`,
  `README.md`, and `AGENTS.md` — all `H` references now point to Help, all
  HUD references now point to `U`, no `?` or `F1` Help shortcuts remain
  in user-facing text.
- Original deep reference docs (`organism_biology.md`,
  `predator_prey_system_guide.md`, `primordial_guide.md`) kept in repo
  and PyInstaller bundle.

Build:

- Added five `docs/help_*.md` files to `build.py` and `primordial.spec`.
- Added `docs/organism_biology.md` to `build.py` and `primordial.spec`.

Tests:

- Updated `test_help_browser.py`: registry checks for all five docs, tab
  cycling test for multi-doc case, nav scroll test proving wheel scroll
  is not undone by draw.
- Updated `test_action_bar.py`: normal shortcuts show `H Help` and `U HUD`.
- Updated `test_fixed_step_loop.py`: help path resolves
  `help_quick_start.md`.

## [2026-05-21] — docs/help: unify organism biology into single help guide

The organism biology content was previously in a separate help document
tab that required tab-switching to discover. Now the in-app help browser
shows a single unified Primordial Guide with all sections visible in one
navigation pane: what organisms are, genome traits, reproduction,
selection, predator-prey biology, visual morphology, how to watch
evolution, controls, settings, and glossary.

Changed:

- Created `docs/primordial_guide.md`: unified guide combining the
  predator-prey system guide and organism biology into one document with
  logically ordered sections. No content was removed or summarized.
- Changed `HELP_DOCUMENTS` registry from two entries (predator_prey_guide,
  organism_biology) to one entry (primordial_guide).
- Changed `DEFAULT_HELP_DOC_ID` from `predator_prey_guide` to
  `primordial_guide`.
- Removed doc tab strip from help browser UI (no longer needed with a
  single document).
- Tab key now toggles search focus instead of cycling documents.
- Updated footer hint to reflect single-document navigation.
- Renamed `bundled_predator_prey_guide_path()` to
  `bundled_primordial_guide_path()`.
- Updated `_predator_prey_help_path()` in persistence/runtime_state.py
  to resolve `primordial_guide.md`.
- Added `docs/primordial_guide.md` to PyInstaller bundle (build.py
  and primordial.spec).
- Updated tests: registry checks for primordial_guide, organism-biology
  and predator-prey section presence tests, tab-focus test replaces
  tab-cycling tests.

Kept:

- `docs/organism_biology.md` and `docs/predator_prey_system_guide.md`
  remain in the repo as source docs and are still bundled in the
  PyInstaller build.

## [2026-05-21] — keyboard: add ? and F1 shortcuts to open help browser directly

The organism biology and predator-prey guides were previously only
reachable by opening Settings (S) then finding the Help action in the
Actions category. Now pressing ? or F1 opens the help browser directly
from the running simulation.

Changed:

- Added `?` (pygame.K_QUESTION) and `F1` keyboard shortcuts to
  `primordial/input/keyboard.py` that open the in-app help browser
  directly from normal simulation playback.
- Added `?` Help hint to the bottom action bar shortcut strip.
- Updated the Settings overlay Help action key label from `H` to `?`
  to match the direct shortcut (H already toggles the HUD).

## [2026-05-21] — docs/help: expose organism biology in app help browser

Wired the organism biology documentation into the in-app help browser so
users can discover and read it directly from the app, not just as a markdown
file in the repo.

Changed:

- Extended the in-app help browser to support multiple documents with a tab
  strip for document switching (click or Tab/Shift+Tab to cycle).
- Added a `HelpDocEntry` / `HELP_DOCUMENTS` registry in
  `primordial/help/document_model.py` that lists available help documents
  with titles, descriptions, and relative paths.
- Added `load_help_document_by_id()` to load registered documents by ID.
- Added `organism_biology` as a registered help document alongside the
  existing `predator_prey_guide`.
- Help overlay header now shows the active document title instead of the
  generic "PRIMORDIAL GUIDE".
- Cross-references added between the predator-prey guide and organism biology
  doc (the predator-prey guide now ends with a section pointing to the
  Organism Biology tab; organism biology doc references the Predator-Prey
  Guide tab).
- Renamed the settings overlay "Predator-Prey Guide" action to "Help" with an
  updated description mentioning both guides.
- Added `docs/organism_biology.md` to the PyInstaller bundle (build.py and
  primordial.spec).
- Added 10 new tests: 7 for the document registry and 3 for document
  switching in the help overlay.

## [2026-05-21] — docs: explain organism biology and visual evolution

Added comprehensive documentation explaining what organisms are biologically,
how their genomes determine both behavior and appearance, how to read creature
morphology visually, how predator/prey ecology works, and how to watch
evolution happen over different timescales.

Changed:

- Added `docs/organism_biology.md`: a deep user-facing document covering
  organism biology, genome trait groups, reproduction and mutation mechanics,
  selection pressure systems, lineage meaning, predator/prey ecology in
  detail, the meaning of every visual feature, invisible mechanics, limits
  of visual inference, and a practical guide to watching evolution.
- Updated `README.md` with concise "What You Are Watching", "Biology of the
  Organisms", "Reading the Creatures", and "Predator-Prey Biology" sections
  that link to the deeper doc. Also fixed the trait count reference (15→16
  in the Evolution list) and added the organism biology doc to the design
  documentation references.
- Updated `AGENTS.md` with the organism biology doc reference, the design
  philosophy point that glyph morphology is the organism's phenotype, the
  correct genome trait count in the architecture map (13→16), and the new
  "glyph morphology is semantically meaningful" rule in the Do Not Break
  list.

## [2026-05-21] — tune: make boids flocking loose and lifelike

This pass focused on boids behavior and motion quality after the recent
performance work made the live `30 Hz` path readable.

Changed:

- Reworked boids local force composition in
  `primordial/simulation/simulation.py`:
  - stronger near-contact separation with a steeper close-range falloff
  - density-aware alignment and cohesion so compact neighborhoods stop
    collapsing inward and moving like rigid pucks
  - smooth per-creature low-frequency wander variation so schools bend, shear,
    split, and recombine more naturally
- Tightened boids flock-link assignment so sparse bridge chains no longer merge
  visibly separate groups into one giant flock for HUD/flock-line grouping.
- Adjusted boids initial spawn ranges to preserve heritable variation while
  reducing blob-prone sensing defaults.
- Reworked boids energy/reproduction around moderate local formation quality:
  reward readable spacing and alignment, penalize crowding more clearly, and
  add an explicit overpopulation tax near carrying capacity.
- Added boids behavior diagnostics to the simulation observability path and
  added targeted tests for the new metrics.
- Captured new seeded before/after boids behavior artifacts, screenshots, and a
  report under `docs/behavior/boids_motion_2026-05-21.md`.

Behavior results from seeded runs (`seed = 130363`):

- Default boids, `90s`
  - nearest-neighbor mean: `18.92 -> 29.79`
  - largest-flock share mean: `0.697 -> 0.199`
  - overcrowded share mean: `0.985 -> 0.273`
  - dense-cluster share mean: `0.790 -> 0.029`
  - end-state flock bands changed from `2 medium` groups to a mix of `small`,
    `medium`, `large`, and `huge` schools
- Stress boids, `60s`, `initial_population = 220`, `max_population = 320`
  - nearest-neighbor mean: `18.48 -> 30.13`
  - largest-flock share mean: `0.758 -> 0.240`
  - overcrowded share mean: `0.992 -> 0.261`
  - dense-cluster share mean: `0.971 -> 0.045`
  - end-state flock bands changed from `2 large + 1 huge` to a mixed spread of
    `small`, `medium`, and `large` schools

Live graphical results:

- `boids` default live run, `90s`, seed `130363`
  - FPS mean `29.84`
  - population mean / max `236.12 / 276`
  - final flock mix: `12` flocks, largest `72`, loners `10`
- `boids` stress live run, `60s`, seed `130363`
  - FPS mean `29.07`
  - population mean / max `275.07 / 320`
  - final flock mix: `17` flocks, largest `36`, loners `10`
- `predator_prey` default regression run, `90s`, seed `104729`
  - FPS mean `30.04`
  - sim/render mean `7.80 / 7.56 ms`

Artifacts:

- `docs/behavior/boids_motion_2026-05-21.md`
- `docs/behavior/boids_motion_2026-05-21/before/`
- `docs/behavior/boids_motion_2026-05-21/after/`
- `docs/behavior/boids_motion_2026-05-21/regression_predator_prey/`

## [2026-05-21] — perf: smooth boids graphical mode without predator_prey regression

Measured the real graphical path on a live `1920x1080` display before changing
code. The important pre-change diagnosis was:

- boids startup was mainly `simulation-bound`, not flock-line-bound;
- `_build_boid_neighbor_cache()` and `_update_flock_assignments()` dominated the
  live boids profile;
- the fixed-step loop amplified the problem by forcing 4 to 5 boids sim steps
  into single rendered frames during startup;
- boids render cost was secondary and came mostly from trails and creature
  drawing on the pygame path;
- predator_prey was already stable on its protected GPU-backed `30 Hz` path and
  was treated as regression-sensitive.

Changed:

- Replaced the old boids directed-neighbor pass plus separate flock BFS with a
  single spatial-bucket pair pass in `primordial/simulation/simulation.py`.
- Set boids mode defaults to `target_fps = 30` and `simulation_tick_hz = 30`
  in `primordial/config/defaults.toml`, matching the intended smooth visual
  cadence instead of chasing a `60 Hz` path that produced ugly startup stalls.
- Reused per-frame creature render state across boids trail/body passes and
  expanded OceanTheme glow/age-overlay cache capacity to reduce repeated pygame
  work without removing trails, glyphs, glow, flock lines, or phase-sync.
- Updated boids benchmark scenario defaults and added/updated tests covering the
  boids fixed-step override, benchmark expectations, and renderer cache helper.

Real graphical benchmark results:

- `boids` default fullscreen live run, seed `130363`, `90s`
  - before: FPS mean `58.22`, startup `17.28`, steady `59.52`, 1% low `8.50`
  - after: FPS mean `30.19`, startup `30.04`, steady `30.21`, 1% low `24.19`
  - frame pacing changed from a misleading high-average / terrible-tail `60 FPS`
    chase into a stable, correctly capped `30 FPS` presentation path
- `boids` stress fullscreen live run, seed `130363`, `60s`,
  `initial_population=220`, `max_population=320`
  - before: FPS mean `52.17`, startup `9.69`, steady `53.99`, 1% low `6.05`
  - after: FPS mean `29.70`, startup `29.65`, steady `29.71`, 1% low `19.22`
- `predator_prey` default fullscreen live regression run, seed `104729`, `90s`
  - before: FPS mean `30.34`, sim/render mean `6.82 / 8.23 ms`
  - after: FPS mean `30.33`, sim/render mean `6.88 / 8.43 ms`
- `predator_prey` debug+HUD fullscreen live regression run, seed `104729`, `60s`
  - before: FPS mean `30.26`, sim/render mean `6.66 / 11.29 ms`
  - after: FPS mean `30.22`, sim/render mean `6.50 / 11.29 ms`

GPU offload was considered and not implemented for boids in this pass. The
measured root cause was boids simulation neighbor/connectivity work plus
fixed-step catch-up amplification, not a flock-line or generic GPU-sized draw
problem. Extending the predator_prey GPU renderer to boids would have been a
larger rewrite than warranted for the measured issue.

Artifacts:

- `docs/performance/boids_graphical_perf_2026-05-21.md`
- `docs/performance/boids_graphical_perf_2026-05-21.json`
- `docs/performance/prechange_graphical_2026-05-21/`
- `docs/performance/postchange_graphical_2026-05-21/`

Remaining risk:

- the boids stress case is now close to the target and no longer collapses at
  startup, but the next measured optimization target would still be the pygame
  boids trail/body render path if visual density rises further.

## [2026-05-21] — feat: add command-line help output

Added a standard `-h` / `--help` path that prints conventional CLI help for
runtime flags and the Windows screensaver argument forms, then exits before
pygame initialization or config/runtime startup. The tolerant
`parse_runtime_args()` path still uses `parse_known_args()` so `/s`, `/p`,
`/c`, and unknown launcher arguments do not become fatal during normal startup.

## [2026-05-21] — feat: add mouse-activated action bar

Added a renderer-owned bottom action bar that appears when the mouse moves
during normal simulation playback, stays fully visible for 5 seconds, then
fades out over 10 seconds. The bar uses centralized shortcut metadata in
`primordial/rendering/action_bar.py`, filters commands by normal/inspect/game-over
context, stays hidden during settings/help/tutorial overlays and non-normal
runtime modes, and draws in both pygame and GPU renderer paths without showing
the OS cursor.

## [2026-05-21] — fix: polish tutorial highlights and pause restore

Removed confusing tutorial highlight boxes for conceptual steps like Welcome,
Settings, Help Browser, Depth, and Game Over. Tutorial highlights now appear
only for visible, stable targets such as the HUD or broad world-reading areas,
with softer labeled treatment instead of empty panel-like boxes. Tutorial exit
now resumes normal simulation playback on finish, skip, or close instead of
leaving the run paused.

## [2026-05-21] — feat: add in-game tutorial onboarding

Added a renderer-owned in-game tutorial overlay with declarative steps,
mouse/keyboard Next/Back/Skip/Finish controls, concept highlights, first-launch
user-state persistence, and a `--tutorial` / `--show-tutorial` CLI override.
Tutorial state/content, layout, mouse hit regions, and rendering live in focused
modules separate from settings and help. The settings Actions category can also
start the tutorial, and the main loop now routes tutorial events before help,
settings, and normal simulation controls while preserving cursor behavior.

## [2026-05-21] — feat: add in-app documentation browser

Added a renderer-owned in-app help browser opened from the settings Guide action.
The browser loads `docs/predator_prey_system_guide.md` through a new help
document model, parses Markdown headings into navigable sections, supports
search, scrolling, mouse clicks, keyboard navigation, and draws in the existing
ocean/bioluminescent modal style. Help layout/navigation/mouse/rendering now
live in focused modules separate from the settings overlay, and docs/README
planning notes now describe the in-app help workflow.

## [2026-05-21] — docs: refresh roadmap and implementation plan

Updated `docs/implementation_program.md` and `docs/roadmap.md` from the
current codebase and recent documentation/settings work. The planning docs now
mark completed early milestones, preserve remaining ecology/observability goals,
and make the next near-term priorities explicit: an in-app documentation/help
browser followed by a first-launch tutorial/onboarding flow. Added architecture
guardrails so future help/tutorial work does not collapse into the settings
overlay or hardcode documentation in renderer code.

## [2026-05-21] — docs: refresh architecture and predator-prey guide

Rewrote `docs/architecture_reference.md` around the current module layout,
settings overlay refactor, cursor helpers, runtime action routing, config
authority, persistence, and predator-prey state. Reworked
`docs/predator_prey_system_guide.md` as a current-state user guide, correcting
stale predator-prey defaults and behavior notes, clarifying that adaptive tuning
is implemented but disabled by default, and documenting current controls,
settings, HUD, game-over, snapshot, and guide-launch behavior. Also corrected
matching README/AGENTS references for genome trait count, predator-prey defaults,
adaptive tuning default state, and game-over hold time.

## [2026-05-21] — polish: settings overlay long-label layout

Adjusted the redesigned settings overlay layout so long category names and
setting labels wrap cleanly instead of clipping or colliding with value
controls. Overlay panel sizing now uses measured category/item text through
`primordial/rendering/settings_layout.py`, preserving the current readable font
sizes while keeping mouse hit regions aligned with the drawn controls.

## [2026-05-21] — input: clickable settings overlay

Added mouse support to the redesigned settings overlay: category sidebar items,
setting rows, value steppers, action rows, and footer buttons are now clickable,
with hover feedback and wheel scrolling. Normal simulation playback now keeps
the OS cursor hidden in both fullscreen and windowed mode, shows it while the
settings overlay or Inspect Mode is interactive, and restores it on clean
shutdown through `primordial/display/cursor.py`.

## [2026-05-21] — redesign: categorized settings overlay

Reworked the in-app settings overlay from a single cramped list into a
categorized modal with sidebar navigation, stronger contrast, selected-setting
details, compact reset badges, unapplied-change status, fixed footer controls,
and action descriptions. Settings labels/descriptions/ranges now live in
`primordial/rendering/settings_metadata.py`, category state lives in
`primordial/rendering/settings_navigation.py`, and runtime apply/discard/reset
behavior remains delegated to `primordial/runtime/settings_actions.py`.

## [2026-05-15] — fix: settings overlay runtime action handling

Extracted settings-overlay action handling from `primordial/main.py` into
`primordial/runtime/settings_actions.py`. The reset-defaults action now applies
runtime display/backend/theme/mode/timing updates instead of only mutating saved
settings, and snapshot loads from the overlay reattach the existing predator-prey
run and milestone loggers. Removed stale unused imports found during the code
health audit.

## [2026-05-15] — refactor: peel display and runtime-state helpers out of main

Moved display mode switching, coordinate diagnostics, keyboard handling, and
runtime sidecar persistence helpers out of `primordial/main.py` into focused
modules under `primordial/display/`, `primordial/input/`, and
`primordial/persistence/`. Updated probes, graphical benchmarking, and tests to
import those helpers from their new homes without changing simulation,
rendering, timing, benchmark, or UI behavior.

## [2026-05-15] — cleanup: expose runtime helper API names

Renamed shared fixed-step and frame-metrics runtime helpers to package-internal
public names, re-exported the intended runtime API from `primordial.runtime`,
and updated app code, benchmarks, probes, tools, and tests to use the cleaner
imports. Removed stale parity-audit imports left behind by the runtime split.

## [2026-05-15] — refactor: split runtime loop out of main module

Moved fixed-step loop state, frame timing collection, bounded runtime sessions,
and profile-session output into `primordial/runtime/`. `primordial/main.py` now
keeps high-level application orchestration while benchmarks, probes, parity
audit tooling, and tests import runtime internals from their focused modules.

## [2026-05-15] — refactor: split AGENTS.md into focused files

Moved design/system reference content out of AGENTS.md into
`docs/architecture_reference.md` and build/integration content into
`docs/build_and_integration.md`. AGENTS.md now contains only agent-relevant
instructions, contracts, and conventions. Also renamed AGENT.md to AGENTS.md
so opencode picks it up correctly.

## [2026-05-15] — fix: kin_line_count always reported as 0 in GPU renderer metrics

`gpu_renderer.py` read `kin_line_count`, `kin_line_segment_count`, and
`kin_line_shimmer_count` from the `kin_line_diagnostics` dict passed into
`build_kin_line_render_data`, but those metrics are written to a separate
`render_diag` dict inside that function (returned as `kin_render.diagnostics`).
The `kin_line_diagnostics` dict only receives `qualifying_lineages` and
`largest_lineage_size` from `build_gpu_kin_line_sprites`. Changed all three
reads to use `kin_render.diagnostics` instead.

Also updated `tools/benchmark_kin_lines_ab.py` to:
- Add `kin_on_synthetic` scenario that assigns spatially-clustered lineage IDs
  for benchmarking render cost with nonzero kin-line load.
- Capture `qualifying_lineages` and `largest_lineage_size` metrics.
- Re-apply lineage cluster assignment each frame so new creatures inherit
  cluster IDs.

## [2026-05-15] — render: filament-style kin lines with glow, wave, and shimmer

**What changed** (`primordial/rendering/snapshot.py`,
`primordial/rendering/gpu_renderer.py`, `primordial/config/config.py`,
`primordial/config/defaults.toml`, `config.toml`,
`tests/test_gpu_kin_lines.py`, `CHANGELOG.md`):

- Kin lines now support a **filament** style that replaces plain straight debug
  lines with soft, organic-looking connective threads between related organisms.
- `KinLineStyle` dataclass controls wave amplitude, segment count, wave speed,
  glow layer, and shimmer particles — all configurable via `[rendering]` config.
- Wave segments break each logical kin line into 6 (configurable) short line
  segments offset perpendicular to the line using a deterministic sine wave
  animated by `anim_time`. Phase is derived from endpoint coordinates, not RNG.
- Amplitude fades down for very short lines (< 50px) so tiny connections don't
  over-wave.
- Glow pass draws the same wave segments at wider width and reduced alpha
  (`glow_width_scale=2.5`, `glow_alpha_scale=0.35`) beneath the core line,
  creating a soft bloom effect.
- Shimmer places 1 tiny radial glow per line that moves deterministically along
  the curve, giving a living filament shimmer without glitter.
- Debug boost still works: it boosts alpha values while preserving wave/glow/shimmer.
- New config keys: `kin_line_style`, `kin_line_width`, `kin_line_wave_amplitude`,
  `kin_line_wave_segments`, `kin_line_wave_speed`, `kin_line_glow`,
  `kin_line_shimmer`, `kin_line_shimmer_strength`.
- Plain mode (`kin_line_style = "plain"`) is available and returns simple straight
  lines for debugging or minimal rendering.
- `PredatorPreyRenderSnapshot` now includes `kin_glow_lines` and
  `kin_shimmer_sprites` fields alongside `kin_lines`.
- GPU renderer draws glow lines first (wider), then core lines, then shimmer
  sprites with additive blending.
- Diagnostics now include `kin_line_segment_count` and `kin_line_shimmer_count`
  in the debug HUD.
- 17 new pure tests covering wave determinism, zero amplitude, segment count,
  shimmer positions, glow on/off, style builder, max caps, plain mode,
  debug boost non-interference, and config default/override.
- Visual hierarchy preserved: kin lines remain softer than attack lines and
  inspect highlights.
- No simulation, lineage, reproduction, or ecology behavior was changed.

**Suggested normal config:**

```toml
[rendering]
kin_line_max_distance = 140.0
kin_line_min_group = 3
kin_line_width = 1.5
kin_line_debug_boost = false
kin_line_style = "filament"
kin_line_wave_amplitude = 2.5
kin_line_wave_segments = 6
kin_line_wave_speed = 1.0
kin_line_glow = true
kin_line_shimmer = true
kin_line_shimmer_strength = 0.35
```

**Suggested visible test config:**

```toml
[rendering]
kin_line_max_distance = 220.0
kin_line_min_group = 2
kin_line_width = 3.0
kin_line_debug_boost = true
kin_line_style = "filament"
kin_line_wave_amplitude = 5.0
kin_line_wave_segments = 6
kin_line_wave_speed = 1.0
kin_line_glow = true
kin_line_shimmer = true
kin_line_shimmer_strength = 0.35
```

## [2026-05-15] — render: restore gpu kin lines

**What changed** (`primordial/rendering/snapshot.py`,
`primordial/rendering/gpu_renderer.py`, `primordial/config/config.py`,
`tools/smoke_gpu_predator_prey.py`, `README.md`,
`docs/predator_prey_system_guide.md`, `tests/test_gpu_kin_lines.py`,
`tests/test_config_authority.py`):

- Restored faint lineage connection lines in the GPU predator/prey renderer
  with a pure snapshot-side builder that groups by `lineage_id`, uses local
  spatial buckets, respects `kin_line_min_group`, fades alpha by distance,
  and avoids naive whole-population `O(n^2)` scans.
- Split GPU kin lines from attack lines so kin threads now draw beneath
  creatures while attack lines remain brighter and above-creature.
- Added conservative density caps for dense lineages and skipped screen-spanning
  wraparound segments to keep the effect readable instead of turning into a
  full-screen spiderweb.
- Kept the global committed render default at `kin_line_max_distance = 0.0`,
  but the GPU predator/prey renderer now uses a modest internal fallback when
  that key was not explicitly set by the user. Explicitly setting
  `kin_line_max_distance = 0.0` still disables kin lines.
- Added snapshot timing/telemetry for GPU kin-line build and draw cost plus a
  pure test suite covering disabled mode, minimum group size, same-lineage
  generation, different-lineage exclusion, density caps, determinism, and
  config-explicit disable handling.

## [2026-05-15] — inspect: polish creature card layout

**What changed** (`primordial/rendering/inspect_mode.py`,
`primordial/rendering/renderer.py`, `primordial/rendering/gpu_renderer.py`,
`primordial/main.py`, `README.md`, `docs/predator_prey_system_guide.md`,
`tests/test_inspect_mode.py`, `tests/test_predator_prey_stability.py`):

- Moved the Inspect Mode card to the top-right in both pygame and GPU render
  paths with a stable `24px` screen margin and shared positioning logic.
- Replaced the debug-style card rendering with a calmer microscope-style panel:
  darker translucent background, restrained luminous border, better padding,
  clearer typography hierarchy, and subtle divider lines.
- Added a presentation layer on top of the existing read-only creature
  observation builder so the card now leads with title, narrative summary,
  state, behavior, and temperament before lower-priority details.
- Added friendlier labels for rendered fields, compacted the default layout,
  and gracefully pruned lower-priority rows when the card would exceed the
  available screen height.
- Added an optional Inspect Mode detail toggle on `D`: compact mode keeps the
  story/state view prominent, while detail mode adds raw genome values,
  position, exact age, and predator-only satiety / recent prey energy.
- Updated controls/docs and added regression tests for narrative summary,
  label mapping, top-right placement, height clamping, and the `D` key toggle.

## [2026-05-15] — fix: inspect click selection compares Linux coordinate spaces

**What changed** (`primordial/main.py`, `tests/test_fixed_step_loop.py`):

- Fixed windowed Inspect Mode selection on Linux OpenGL setups where SDL mouse
  events, the OpenGL drawable, and the apparent window size can disagree after
  a fullscreen/windowed transition.
- Inspect click selection now evaluates raw display, window-to-display scaled,
  and mixed-axis coordinate candidates, then chooses the candidate with the
  best normalized pick score.
- Added debug-only JSON diagnostics for Inspect Mode mouse clicks, including
  raw event coordinates, `pygame.mouse.get_pos()`, display/window/screen/world
  sizes, renderer backend and flags, mapped world coordinates, and selected
  creature render deltas.
- Added regression tests for display/window size reporting, coordinate mapping,
  and normalized candidate selection.

## [2026-05-14] — feat: Inspect Mode (read-only creature observability)

**What changed** (`rendering/inspect_mode.py`, `rendering/renderer.py`,
`rendering/gpu_renderer.py`, `rendering/__init__.py`, `primordial/main.py`,
`tests/test_inspect_mode.py`):

- Added an optional **Inspect Mode** for read-only creature observability,
  toggled with **I**. While active the simulation is paused (default) or in
  slow-motion at 2 Hz (press **M** to switch). Clicking a creature selects it
  and displays a detail card (species, lineage, age, energy, depth, genome
  traits, position, velocity, behavior guess; predators also show recent animal
  energy and satiety).
- The mode is purely observational: it never mutates simulation state, consumes
  RNG, or alters ecology dials. Exiting restores the prior paused/running state.
- Both the pygame and OpenGL renderers draw a selection highlight ring around
  the selected creature and a right-side info card overlay.
- Slow-mode ticks use an accumulator pattern independent of target FPS, so
  determinism is preserved at full speed and behaviour is identical when
  observed at 2 Hz.
- Selection uses `id(creature)` so it naturally resets on world reset.
- Added 42 unit tests covering toggle, selection, slow-mode accumulator,
  creature card building, behavior guessing, and coordinate conversion.

## [2026-03-13] — feat: predator_prey stability scoring, extinction game-over, and adaptive tuning

**What changed** (`simulation/simulation.py`, `rendering/hud.py`,
`rendering/renderer.py`, `simulation/persistence.py`, `primordial/main.py`,
`config/defaults.toml`, `config/config.py`):

- Predator-prey now scores runs by **stability**: the key metric is how many
  `sim_ticks` elapse before predators or prey collapse to zero.
- Fixed the predator-dominance rule to the stabilizing behavior:
  when predators exceed 60% of population, predator reproduction becomes harder
  by increasing their reproduction threshold by 20%.
- Removed automatic extinction rescue from normal predator-prey play.
  Species collapse now freezes the simulation, tints the screen red, shows a
  `GAME OVER` overlay with cause/seed/counts/survival ticks, highest survival
  record, rolling average comparison, and current run dial values, holds for
  10 seconds, then restarts with a new seed.
- Pressing `Space` during predator-prey `GAME OVER` now skips the hold and
  immediately starts the next seeded run.
- Replaced predator-prey HUD generation display with `sim_ticks`, seed,
  current `survival_ticks`, rolling average survival over the configured
  history window, best recent survival from that same window, and current
  adaptive trial status.
- Added a bounded adaptive dial controller for a small set of ecological
  constants (`predator_contact_kill_distance_scale`,
  `predator_kill_energy_gain_cap`, `predator_hunt_sense_multiplier`,
  `prey_flee_sense_multiplier`,
  `predator_prey_scarcity_penalty_multiplier`, `food_cycle_amplitude`).
  Below-average collapses start a one-dial trial run; the threshold is the
  rolling average, not the median or all-time best. The next run either keeps
  or reverts the change based on whether it meets or beats that pre-trial
  rolling average. Long non-improving streaks can scale the dial step size up
  via user config.
- Predator-prey snapshots now persist adaptive tuning state, current seed,
  `sim_ticks`, `survival_ticks`, rolling history, and trial metadata.
- The adaptive predator-prey tuning state is also written on app exit and
  restored on next launch without requiring a world snapshot.
- Added a settings-overlay action to reset predator-prey adaptive dials to
  baseline values, clear the max survival tick record, and restart the mode
  from a clean run.
- Clarified the `GAME OVER` overlay semantics in docs: dial highlight means
  "this run tested that dial", not "that trial succeeded".
- Added optional `--log=csv` predator-prey run logging. When enabled, the app
  creates `run_logs/predator_prey_runs.csv`, appends one row per completed run
  with seed/ticks/collapse/trial/dial telemetry, and writes a `dial_reset`
  marker row when predator-prey adaptive dials are manually reset.

**Why:** predator-prey previously optimized for endless continuity via species
rescue, which made extinction invisible and contradicted the intended
stabilizing predator-dominance rule. The mode now exposes stability directly,
keeps run-to-run tuning bounded and explicit, and remains replayable via saved
state.

---

## [2026-03-05] — Comprehensive Audit + Optimization Pass

### Summary

This pass focused on correctness hardening, measured performance work, and
developer tooling. The app now handles malformed config data safely, avoids
several silent state-consistency failures, and exposes first-class debug/profile
CLI workflows.

---

## [2026-03-05] — fix: config validation hardening, safe coercion, and mode override safety

**What changed** (`primordial/config/config.py`, `simulation/simulation.py`):

- Reworked config merge path to be type-safe:
  - invalid types now warn and keep defaults instead of raising exceptions
  - unknown keys are explicitly warned and ignored
  - malformed section types are ignored safely
- Added validation and persistence for previously-missed fields:
  - `food_max_particles`
  - rendering config values (`glyph_size_base`, kin/shimmer/animation tuning)
- Fixed mode override coercion bug (`bool("false") -> True`) by removing runtime
  `type(fallback)` casting and validating mode overrides once at config load.
- `to_toml()` now serializes effective mode override values from `mode_params`
  instead of hardcoded static mode blocks.

**Why:** malformed or hand-edited `config.toml` values could previously crash
startup or silently coerce to incorrect values.

---

## [2026-03-05] — fix: state consistency in predation, resize/fullscreen, and boids connectivity

**What changed** (`simulation/simulation.py`, `simulation/food.py`,
`rendering/renderer.py`, `primordial/main.py`):

- Predation energy transfer is now bounded by prey energy:
  - prevents multiple attackers farming energy from already-dead targets in the
    same frame.
- Predator-prey species normalization:
  - creatures with invalid species tags are reclassified deterministically from aggression.
- Added `Simulation.resize()` + `FoodManager.resize_world()`:
  - resizes now rebuild food grid buckets safely and wrap entities into new bounds.
- Added `Renderer.resize()`:
  - recreates size-dependent surfaces, clears shimmer state, invalidates zone cache,
    and refreshes ambient particles.
- Boids flock connectivity now uses undirected adjacency semantics (if either
  boid senses the other, they connect), eliminating order-dependent flock splits.
- `_nearby_creatures()` now deduplicates wrapped cell keys only when needed to
  avoid duplicate neighbor scans at large radii.

**Why:** these paths previously allowed subtle state drift and stale geometry
after resolution changes.

---

## [2026-03-05] — perf: profile-driven simulation hot path refactor

**Baseline harness** (headless dummy SDL, 1920×1080):

- Energy mode step time:
  - pop 50: **1.284ms**
  - pop 150: **4.082ms**
  - pop 250: **7.684ms**
- Full frame (step+render) at pop 150: **25.445ms**
- Boids mode step time:
  - pop 80: **17.135ms**
  - pop 150: **16.829ms**
  - pop 250: **16.638ms**

**What changed** (`simulation/simulation.py`):

- Replaced repeated boids neighbor scanning with a shared per-frame neighbor cache.
- Split boids flow into:
  - `_build_boid_neighbor_cache()`
  - `_compute_boid_forces(...neighbors...)`
  - `_update_flock_assignments(...neighbor_cache...)`
- Reduced expensive distance math:
  - added toroidal squared-distance helpers
  - replaced many sqrt-based comparisons with squared thresholds
  - reused wrapped delta vectors where possible.
- Fixed toroidal cohesion behavior by averaging neighbor offset vectors rather
  than naive absolute coordinates.

**Measured result (same harness):**

- Energy mode step time:
  - pop 50: **0.803ms** (from 1.284ms, **1.60× faster**)
  - pop 150: **2.005ms** (from 4.082ms, **2.04× faster**)
  - pop 250: **3.310ms** (from 7.684ms, **2.32× faster**)
- Full frame at pop 150: **13.425ms** (from 25.445ms, **1.89× faster**)
- Boids step time:
  - pop 80: **12.535ms** (from 17.135ms, **1.37× faster**)
  - pop 150: **11.887ms** (from 16.829ms, **1.42× faster**)
  - pop 250: **12.803ms** (from 16.638ms, **1.30× faster**)

---

## [2026-03-05] — feat: runtime developer tooling (`--debug`, `--profile`, `--mode`, `--theme`)

**What changed** (`main.py`, `primordial/main.py`, `primordial/utils/cli.py`,
`rendering/renderer.py`, `rendering/hud.py`, `Makefile`):

- Added CLI runtime flags:
  - `--debug` enables debug HUD timing lines + FPS/population graph overlay
  - `--profile` runs for 60 seconds, writes `.pstats` + text report, exits
  - `--mode <name>` sets sim mode at launch without editing config
  - `--theme <name>` sets visual theme at launch without editing config
- Added tolerant runtime parser (`parse_runtime_args`) that coexists with `/s`,
  `/p`, `/c` screensaver args.
- Added per-frame debug timing pipeline:
  - external metrics from main loop (`event_ms`, `sim_ms`)
  - renderer sub-system timing breakdown shown in HUD in debug mode
  - FPS and population history mini-graphs (debug overlay)
- Hardened output paths for restricted environments:
  - log file creation falls back to working directory if config path is not writable
  - profile report writes (`.pstats` + `.txt`) fall back similarly instead of crashing
- Added `Makefile` tasks:
  - `make run`, `make debug`, `make profile`, `make build`, `make clean`

**Why:** this makes iterative tuning and future audit/profile work repeatable.

---

## [2026-03-05] — perf: reduced per-frame rendering allocations

**What changed** (`rendering/themes.py`, `rendering/animations.py`,
`rendering/settings_overlay.py`):

- Added age-overlay surface cache in `OceanTheme` (radius+alpha key) to avoid
  allocating a new greyscale wash surface per old creature per frame.
- Added frame caches for `CosmicRayAnimation` and color/frame caches for
  `ParentPulse` to eliminate per-frame temporary surface creation.
- Cached settings overlay shade surface and reuse per resolution.

**Why:** removes allocation churn and reduces GC pressure in long runs.

---

## [2026-03-05] — validation: memory + build checks

**What changed / verified:**

- 10-minute-equivalent headless run (36,000 frames) remained memory-stable:
  - RSS **44.76 MB → 45.27 MB** (`+0.51 MB`).
- PyInstaller pipeline verified after changes:
  - `python build.py` succeeded on Linux.
  - `dist/primordial` produced (33.1 MB).

---

## [2026-03-05] — All Four Simulation Modes Implemented

### Summary

This pass fully implements the three previously-stubbed simulation modes:
`predator_prey`, `boids`, and `drift`. The "coming soon" overlay has been
removed for all four modes. Each mode is genuinely distinct in its energy
model, selection pressure, visual feel, and HUD stats.

---

## [2026-03-05] — feat: drift mode — meditative evolution through pure random drift

**What changed** (`simulation/simulation.py`, `rendering/*`):

- Passive energy regen (+0.002/frame); no food; no movement cost; die only of old age
- All creatures use glide motion regardless of `motion_style` genome trait
- Very slow, smoothly curving paths via `_drift_wander()` with per-creature
  rotation direction stored in repurposed `_swim_phase` field
- Soft boundary repulsion keeps creatures away from screen edges
- Cosmic ray rate doubled (0.0006/frame default) — drift is mutation-driven
- `_drift_update_position()`: skips swim oscillation, halves glyph rotation
  speed, doubles trail length for long gossamer trails
- Zone effects applied as a very gentle energy nudge (no kill)
- HUD: population, generation, distinct lineage count, most-variable trait
- Mode defaults: pop=60, max_pop=200, mutation_rate=0.04, energy_to_reproduce=0.95

---

## [2026-03-05] — feat: boids mode — flocking simulation with evolved flock behaviour

**What changed** (`simulation/simulation.py`, `rendering/renderer.py`):

- No food; energy from being in a well-formed flock (3–12 neighbours optimal)
- Three genome-controlled boid rules:
  - Separation: avoid crowding (strength = `aggression`)
  - Alignment: match flock heading (strength = `conformity`)
  - Cohesion: steer toward flock centroid (strength = `efficiency`)
- Energy model: optimal band regenerates at rate ∝ alignment quality;
  isolation (<3 neighbours) and crowding (>12) both drain energy
- Flock detection: BFS connected-components via spatial bucket pre-computation;
  O(n × avg_neighborhood) per frame; singletons get `flock_id = -1`
- Glyph pulse phase-sync: each frame, `_glyph_phase` lerps toward flock
  circular average → synchronized bioluminescent pulse within each flock
- Flock lines: faint lines drawn between same-flock creatures (replaces kin
  lines in boids mode); loners show no connections
- HUD: flock count, avg/largest flock size, avg conformity trait, loner count
- Mode defaults: pop=150, max_pop=300, mutation_rate=0.07, energy_to_reproduce=0.72

---

## [2026-03-05] — feat: predator_prey mode — Lotka-Volterra ecosystem

**What changed** (`simulation/simulation.py`):

- Init: 30% predators (warm hues 0.48–0.88, aggression 0.62–0.95),
  70% prey (cool hues 0.05–0.45, aggression 0.0–0.38)
- Predators: hunt nearest prey within `sense_radius*2`; kill on contact
  (energy gain = `prey.size * 3 * 0.1`); pay 1.4× movement cost;
  wander when no prey found; ignore food
- Prey: flee nearest predator within `sense_radius*1.2`; seek food when safe
- Ecosystem balance:
  - >60% predators: increase predator reproduction threshold by 20%
  - <15% prey: predators pay 2× energy cost (prey scarcity)
  - Predators extinct: convert 3 highest-aggression prey → prevents sim death
  - Prey extinct: convert 10 lowest-aggression predators → prevents sim death
- Cosmic ray species flip: aggression crossing 0.5 triggers species conversion
  + new lineage_id (visible speciation event)
- HUD: predator/prey counts, avg speed per species, food cycle bar
- Mode defaults: pop=120, predator_fraction=0.30, food_spawn_rate=0.5,
  mutation_rate=0.08, energy_to_reproduce=0.70

---

## [2026-03-05] — feat: conformity genome trait + species/flock_id/glyph_phase fields

**What changed** (`simulation/genome.py`, `simulation/creature.py`):

- `Genome`: 15th trait `conformity` (0.0–1.0) controls boids alignment
  strength; inert in other modes (drifts randomly via normal mutation)
- `Genome`: updated `random()`, `mutate()`, `copy()`, `mutate_one()`
- `Creature`: `species: str` field ("none"|"prey"|"predator")
- `Creature`: `flock_id: int` field (-1=loner, >=0=flock component id)
- `Creature`: `_glyph_phase: float` — initialised to `genome.hue * 6.28`
  at spawn; updated on mutations and births to track hue; in boids mode
  slowly phase-locks toward flock average for synchronized pulse effect
- `OceanTheme`: pulse animation now uses `creature._glyph_phase` instead
  of `genome.hue * 6.28` (behavior identical in non-boids modes)
- `Creature.spawn()`: added `species` parameter

---

## [2026-03-05] — feat: mode-specific HUD, renderer flock lines, config mode_params, transition fade

**What changed** (`rendering/hud.py`, `rendering/renderer.py`, `config/config.py`, `main.py`):

- HUD: mode-aware rendering — each mode shows relevant stats only:
  - energy: H/G/O counts, food cycle bar, zone, avg lifespan (unchanged)
  - predator_prey: predator/prey counts, avg speed per species, food cycle bar
  - boids: flock count, avg/largest flock, avg conformity, loner count
  - drift: population, generation, lineage count, most-variable trait
- Renderer: removed "coming soon" stub overlay for all four modes
- Renderer: `_draw_flock_lines()` — faint lines between same-flock creatures
  in boids mode; drawn instead of kin lines
- Renderer: `set_mode()` updates stub detection and invalidates zone cache
- Config: `mode_params` dict loaded from `[modes.*]` TOML sections;
  default `[modes.predator_prey/boids/drift]` sections written to config.toml
- Main loop: 2-second fade-to-black transition when mode changes in settings
  overlay; simulation resets at peak opacity and fades back in

---

## [2026-03-05] — audit + config persistence + in-app settings overlay

### Audit pass
- Fixed correctness edge cases in `Simulation`: guarded `max_population` and `food_cycle_period` divisors to prevent divide-by-zero, and hard-clamped food-cycle spawn rate to never go negative.
- Hardened preview argument parsing: `/p` with non-positive HWND now falls back to normal mode to avoid unstable preview embedding.
- Confirmed existing behavior: death events are enqueued for every removal path and consumed by renderer each frame; reproduction returns exactly one offspring per successful parent check; lineage IDs are monotonic via `_alloc_lineage_id`.
- Deferred larger algorithmic refactors (e.g., shimmer centroid O(n) stats) because current code already uses spatial bucketing in hot simulation paths and holds 60fps target on typical loads.

### Persistent config (TOML)
- Replaced dataclass-backed settings with `Config` class in `primordial/config/config.py`.
- Added platform-aware config path resolution and automatic directory creation.
- Added first-run default `config.toml` creation, corruption backup (`config.toml.bak`), typed attribute merge/validation, and save/reset APIs.
- Kept `primordial/settings.py` as compatibility alias (`Settings = Config`) to minimize call-site churn.

### In-app settings screen
- Added renderer-owned `SettingsOverlay` panel (`S` key in normal mode): keyboard-driven navigation and edit controls, 20-frame fade in/out, semi-transparent pause overlay, apply/discard/reset behavior.
- Settings apply on Enter and are auto-saved to user config; close via S/Escape discards unapplied edits.
- Settings marked as requiring reset are annotated in UI; explicit simulation reset remains user-driven.

### Documentation
- Added `AUDIT.md` with file-by-file findings and status markers (FIXED/DEFERRED/WONTFIX).
- Updated README and AGENT docs to describe Config/TOML architecture, platform config paths, and settings overlay workflow.

---

## [2026-03-04] — Evolution Selection Pressure Pass

### Summary

This pass adds four interacting selection systems so that evolution is visible
and meaningful over hundreds of generations.  All systems create genuine
tradeoffs; the visual tone stays calm and meditative throughout.

---

## [2026-03-04] — docs: AGENT.md and README updated for selection-pressure pass

**What changed:**  Added zone architecture, aggression behaviour tiers,
aging/longevity, and Selection Pressure section to AGENT.md.  Added
"Watching Evolution" and "Tuning" sections to README.md.

---

## [2026-03-04] — feat: tuning — selection pressure balance, spatial bucket

**What changed:**

*`settings.py`:*
- `food_spawn_rate` 0.4 → 0.6 (base rate; cycle makes it 0–1.2/frame)
- `food_max_particles` 500 → 300 (lower cap means famine buffer empties faster)
- `food_cycle_period` 1800 (30s per cycle)
- `max_population` 300 → 220 (crowding penalty starts at 110 creatures)
- `energy_to_reproduce` 0.75 → 0.80 (requires sustained feeding, not just lucky burst)
- `mutation_rate` 0.05 → 0.06 (faster trait drift — visible change by gen 300)

*`simulation/simulation.py`:*
- Aggression drain tuned to `aggression * 0.0012/frame` — hunters pay a real cost
  but can offset it with successful attacks
- Attack drain tuned to `aggression * 0.008 * size_ratio/frame` — frequency-
  dependent: profitable in dense prey environment, marginal in sparse
- Grazer efficiency bonus raised to 20% (from spec's 15%) to ensure coexistence
- Prey size cap: hunters only attack creatures ≤ 1.3× own radius

*Creature spatial bucket:*  `_build_creature_bucket()` / `_nearby_creatures()`
builds a 150px grid hash each frame and limits hunting queries to local cells.
Reduces hunt step from O(n²) to O(n × local_density).
Result: 476 fps sim-only at pop=100 on 1920×1080 (well above 60fps target).

*Initial state:*  Creatures start with `energy=0.7`; 200 food particles
pre-seeded so the population doesn't starve before the cycle's first feast.

**Tuning rationale:**

The core balance challenge: with predation providing a second energy source,
hunters can survive famine by eating prey (which are also stressed by famine).
This dampens the boom/bust oscillation and allows hunters to gradually dominate.
The chosen parameters create frequency-dependent selection: hunting is
marginally profitable at high population density (feast) and marginally
unprofitable when prey is scarce (famine).  In practice, observed dynamics
are run-dependent: some seeds reach hunter/grazer coexistence around H:G 4:1;
others evolve toward hunter dominance.  Grazers are continuously re-introduced
by cosmic ray mutations (0.0003 rate × 100 creatures ≈ 1 mutation every 33
frames) so complete extinction requires sustained predation pressure over many
generations.

Expected observable dynamics at 1920×1080:
- Population: 36–230 range, oscillating with food cycle
- Hunters dominate after ~generation 100 in most runs
- Average aggression rises to 0.6–0.8 by generation 500
- Average efficiency rises in parallel (both traits co-selected)
- Rare grazers persist as a minority throughout

**Why these specific values:**
- food_spawn_rate=0.6 × 2 = 1.2 at feast; feeds 200 creatures comfortably
- food_max_particles=300: at 100 creatures, 300 food = 3 per creature; at
  famine they draw down the buffer in ~200 frames — a visible scarcity
- energy_to_reproduce=0.80: creatures need to eat ~4 food particles after
  splitting; achievable in feast but not guaranteed in famine
- Spatial bucket at 150px cells keeps hunting O(n × local) not O(n²)

---

## [2026-03-04] — feat: HUD updates — H/G/O counts, food bar, zone, avg lifespan

**What changed** (`rendering/hud.py`):

- **Oldest**: now shown as `N% lifespan` instead of raw frames — more meaningful
  since max lifespan varies by `longevity` genome trait
- **H:N G:N O:N**: live count of hunters (aggression > 0.6), grazers (< 0.4),
  and opportunists; updates every frame
- **Avg lifespan**: rolling average of last 20 natural (old-age) deaths in
  seconds; `—` until first natural death occurs
- **Zone**: dominant zone label (zone type containing the most creatures at
  this instant; `—` if no creatures are inside any zone)
- **Food cycle bar**: 80px horizontal bar with "Famine" ← → "Feast" labels;
  colour gradient red→green tracks `food_cycle_phase`; updated every frame

---

## [2026-03-04] — feat: rendering — cosmic ray rings, zone backgrounds, attack lines, aging grey

**What changed:**

*`rendering/animations.py`:*
- `CosmicRayAnimation`: 20-frame expanding white ring, max alpha 50, radius
  6→30px.  Added `add_cosmic_ray()` to `AnimationManager`.

*`rendering/renderer.py`:*
- `_draw_zone_backgrounds()`: soft atmospheric radial gradients drawn
  beneath territory shimmer; per-zone color at alpha 0–20; zones are static.
- `_draw_attack_lines()`: 1px lines from attacker to target, hue color
  alpha 40.  Consumes `simulation.active_attacks` each frame.
- Cosmic ray events consumed from `simulation.cosmic_ray_events` → animations.

*`rendering/themes.py`:*
- Age desaturation: after blitting glyph, overlay a grey circle (alpha up to
  160) on creatures past 70% max lifespan.  Applied at blit time — glyph cache
  NOT invalidated.  Subtle until ~85%, obvious at 100%.

---

## [2026-03-04] — feat: environmental zone system

**What changed** (`simulation/zones.py` new):

Five zone types: `warm_vent`, `open_water`, `kelp_forest`, `hunting_ground`,
`deep_trench`.  At startup, `ZoneManager` places `zone_count` (default 5)
circles randomly across the world, each 18–30% of the shorter screen
dimension in radius.

Each zone type favours 2 traits and penalises 1 trait via energy cost
multipliers (up to ±20% per zone, capped [0.75, 1.25] aggregate).
`get_energy_modifier(creature)` is O(zone_count) per creature per frame.
`get_dominant_zone(creatures)` for HUD: returns the zone label most creatures
currently overlap.

Zone rendering: `renderer._draw_zone_backgrounds()` draws each zone as
concentric circles with alpha 0–20, giving subtle screen regions.

---

## [2026-03-04] — feat: food cycle, aggression/hunting, cosmic rays, aging deaths

**What changed** (`simulation/simulation.py` rewritten):

*Food cycle:*  `_get_food_rate()` = `food_spawn_rate × (0.5 + 0.5×sin(2π×t/period))`.
`food_cycle_phase` property exposed for HUD bar.  Pre-seeded with 200 particles.

*Aggression tiers:*
- Hunters (> 0.6): seek nearest creature within `sense×1.5`, steer toward it,
  attack at `radius×4` range.  Fallback food-seek uses 0.85× sense radius.
- Grazers (< 0.4): pure food-seeking with 20% efficiency bonus at eat time.
- Opportunists (0.4–0.6): eat food + opportunistic attack vs tiny nearby prey.
Hunters pay `aggression×0.0012/frame`; must hunt to compensate.

*Cosmic rays:*  Per-frame per-creature chance → `mutate_one(std=0.15)`.
Hue shift > 0.2 → new `lineage_id`.  Position emitted to `cosmic_ray_events`.

*Aging deaths:*  Creatures dying at `age >= max_lifespan` → cause="age"; ages
tracked in rolling deque for `avg_old_age_lifespan_seconds` property.

*New event queues:*  `cosmic_ray_events`, `active_attacks` (rebuilt per frame).
New queries: `get_hunter_grazer_counts()`, `get_dominant_traits()` now includes
`longevity`.

---

## [2026-03-04] — feat: settings tuning, longevity genome trait, creature aging system

**What changed:**

*`settings.py`:*  Added `food_cycle_period` (1800), `food_cycle_enabled`,
`cosmic_ray_rate` (0.0003), `zone_count` (5), `zone_strength` (0.8),
`food_max_particles` (300).

*`genome.py`:*  Added `longevity` trait (0=short-lived, 1=long-lived);
updated `random()`, `mutate()`, `copy()`.  Added `mutate_one()` for cosmic-ray
single-trait mutation (picks one trait, Gaussian std=0.15).

*`creature.py`:*  Added `get_max_lifespan()` (3000–10000 frames based on
longevity), `get_age_fraction()`, `get_age_speed_mult()` (declines to 0.5×
after 70% lifespan), `get_effective_sense_radius()` (declines to 0.6× after
85% lifespan).  `update_position()` applies age speed mult before moving.
`Creature.spawn()` now accepts optional `energy` parameter.

---

## [2026-03-04] - Windows Screensaver Pass

### Summary

This pass converts Primordial into a proper Windows `.scr` screensaver file while
keeping it launchable as a normal app on both Linux and Windows.

---

## [2026-03-04] - docs: README, AGENT.md, CHANGELOG updated for screensaver pass

**What changed:**

- README.md: added "Screensaver Installation (Windows)" section documenting Method 1
  (right-click Install) and Method 2 (manual copy to System32), uninstall steps, and
  updated Distribution section to mention `dist/primordial.scr` alongside `.exe`
- AGENT.md: updated architecture map to include `utils/screensaver.py`; added
  "Screensaver Argument Parsing" section documenting the four modes, the SDL_WINDOWID
  trick and why ordering matters, screensaver input-quit behaviour and grace period,
  and the dual `.exe`/`.scr` build output

**Why:** Future agents need to understand the screensaver argument contract, the SDL
preview embedding mechanism, and the build output to safely extend or modify this pass.

---

## [2026-03-04] - feat: Windows .scr screensaver — arg parsing, modes, config dialog, build output

**What changed:**

*`primordial/utils/screensaver.py` (new):*
- `ScreensaverArgs` dataclass with `mode: str` and optional `preview_hwnd: int`
- `parse_screensaver_args()` — maps `/s`, `/p HWND`, `/c`, and no-args to the four modes

*`main.py` (root):*
- Parse screensaver args at the very top before importing `primordial.main`
- Set `os.environ["SDL_WINDOWID"]` for preview mode before the import so it lands
  before `pygame.init()` is called inside the package

*`primordial/main.py`:*
- `main()` now accepts optional `scr_args: ScreensaverArgs` parameter (defaults to normal)
- `screensaver` mode: fullscreen SCALED, hidden cursor, quit on KEYDOWN /
  MOUSEBUTTONDOWN / MOUSEMOTION > 4px, 2-second startup grace period
- `preview` mode: 152×112 window (SDL renders into HWND via SDL_WINDOWID), half tick
  rate to save CPU, no input handling beyond QUIT
- `config` mode: standalone 400×300 pygame dialog with app title, current settings
  (sim_mode, visual_theme, population, FPS), path to settings.py, OK button —
  no simulation started
- `normal` mode: existing behaviour fully preserved

*`build.py`:*
- After PyInstaller on Windows, copy `dist/primordial.exe` → `dist/primordial.scr`
- Attach `--version-file=version.txt` on Windows when the file exists

**Why:** Windows identifies screensaver binaries solely by the `.scr` extension and
passes `/s`, `/p`, `/c` arguments to control the execution mode. The SDL_WINDOWID
env var is the standard mechanism for embedding a pygame/SDL window into an existing
HWND for the screensaver preview pane. The grace period prevents false-quit from
cursor settling jitter that some systems emit at screensaver activation.

---

## [2026-03-04] - Windows Compatibility and PyInstaller Packaging

### Summary

This pass makes Primordial fully runnable on Windows and produces a self-contained
standalone `primordial.exe` via PyInstaller. All existing Linux functionality is preserved.

---

## [2026-03-04] - docs: README, AGENT.md updated for Windows/packaging pass

**What changed:** Added "Distribution" section to README.md documenting how to build the
executable, expected size, deployment, reproducible builds, and per-platform test status.
Updated AGENT.md architecture map to include new files (`utils/paths.py`, `main.py`, `build.py`,
`primordial.spec`) and added two new sections: "Asset Path Resolution" (explaining `get_base_path()`
and PyInstaller frozen environment detection) and "Build Process" (entry points, build steps,
spec file, and how to add new assets).

**Why:** Future agents and contributors need to understand when and why to use `get_base_path()`,
how the dual entry-point structure works, and how to reproduce or extend the build.

---

## [2026-03-04] - feat: PyInstaller packaging — build.py, main.py entry point, primordial.spec

**What changed:**

- Added top-level `main.py` as the PyInstaller entry point; it delegates to `primordial.main.main()`
  and also works for direct `python main.py` execution (the package uses relative imports so it
  could not be the direct build target itself)
- Added `build.py`: cross-platform build script that cleans previous artifacts, invokes
  `PyInstaller.__main__.run()` programmatically with `--onefile --noconsole --clean`, automatically
  includes `primordial/assets/` via `--add-data` when the directory exists, and applies
  `--icon=assets/icon.ico` on Windows when present
- Committed `primordial.spec` generated by the first successful build — allows reproducible
  rebuilds via `pyinstaller primordial.spec`
- Added `pyinstaller` to `requirements.txt` under a `# build` comment

**Platform testing:**
- ✅ Linux x86-64: `dist/primordial` built successfully, 31.9 MB
- ❌ Windows x86-64: untested (no Windows runner available; build is expected to work, producing `dist/primordial.exe`)

**Why:** The screensaver should run on Windows without requiring Python or pip. A single-file
executable is the most practical distribution format for a screensaver.

---

## [2026-03-04] - feat: Windows compatibility — DPI awareness, FULLSCREEN|SCALED, utils/paths.py

**What changed:**

*`primordial/main.py`:*
- Added `ctypes.windll.shcore.SetProcessDpiAwareness(2)` call before `pygame.init()` to fix
  blurry rendering on Windows high-DPI displays; wrapped in `try/except` so it silently no-ops
  on Linux/Mac and older Windows versions that lack `shcore`
- Changed fullscreen `set_mode` flags from `pygame.FULLSCREEN` to `pygame.FULLSCREEN | pygame.SCALED`
  in both the initial setup and `toggle_fullscreen()`; `SCALED` instructs pygame to handle DPI
  scaling internally, preventing the wrong-resolution issue on Windows

*`primordial/utils/paths.py` (new):*
- `get_base_path() -> Path` — returns `Path(sys._MEIPASS)` when running as a PyInstaller frozen
  bundle, or the project root (`Path(__file__).parent.parent.parent`) when running from source
- All future asset loading must use this helper (see AGENT.md)

*Audit findings (no changes required):*
- No `pygame.font.SysFont` calls — `pygame.font.Font(None, size)` already used throughout ✓
- No `os.system()` or shell calls ✓
- No string-based path construction (`os.path.join`, bare strings) for asset loading ✓
- `.gitignore` already excludes `.venv/` and `__pycache__/` ✓

**Why:** `pygame.SCALED` is the correct flag for Windows DPI-aware fullscreen. Without it, pygame
renders at the OS-upscaled resolution and appears blurry on 4K/HiDPI monitors. The DPI awareness
call prevents Windows from applying its own bitmap scaling before pygame sees the display size.

---

## [2026-03-04] - Enhancement Pass: Symbolic Glyphs and Behavioural Systems

### Summary

Five major systems added in this pass: procedurally generated symbolic glyph creatures, kin connection lines, territory shimmer for dominant lineages, death/birth animations, and three visible motion styles. The energy simulation and ocean theme are fully preserved.

---

## [2026-03-04] - Documentation: AGENT.md, README.md updated for enhancement pass

**What changed:** Updated AGENT.md with new class descriptions, trait list, event queue contract, performance notes for glyphs/kin lines/shimmer, and updated Do Not Break invariants. Updated README.md with full explanation of glyph traits, motion styles, new visual systems, settings, and extended project structure.

**Why:** Agents and users need accurate documentation to extend or understand the new systems. AGENT.md is the primary reference for future AI work on this codebase.

---

## [2026-03-04] - feat: Glyph rendering, kin lines, territory shimmer, and animations

**What changed:**

*Glyph system (`rendering/glyphs.py`):*
- Stroke vocabulary: arc, line, loop, fork, spiral, dot — six primitive drawing functions
- `build_glyph_surface(genome, color, base_size)` builds a fully deterministic glyph from genome hash seed
- Symmetry applied by rotating/mirroring the base stroke set (asymmetric / bilateral / 3-fold / 4-fold)
- Appendages: 0–4 evenly-spaced perimeter limb strokes from `genome.appendages`
- `get_glyph_surface(creature, color, size)` caches on `creature.glyph_surface`; rebuilt when `None`

*AnimationManager (`rendering/animations.py`):*
- `DeathAnimation`: 40-frame dissolution — frame-0 white flash, glyph fades to 0 alpha and shrinks to 0.3×, 4–6 scatter particles drift and fade over 20 frames
- `BirthScaleTracker`: 30-frame ease-out-cubic scale-up from 0.2× to 1.0×, tracked per `id(creature)`
- `ParentPulse`: 15-frame expanding ring on reproducing parent
- `AnimationManager.process_events()` ingests simulation death/birth event queues each frame
- `get_birth_scale(creature)` returns active scale override or None

*OceanTheme (`themes.py`):*
- `render_creature` now draws: trail → bloom glow halo → rotated glyph
- `scale` parameter added (default 1.0) for birth animation integration; backward-compatible

*Renderer (`rendering/renderer.py`):*
- Kin connection lines: creatures bucketed by lineage_id; lines drawn for groups of 3+ within 120px; alpha 15–30 inversely proportional to distance
- Territory shimmer: top-3 lineages get soft pulsing radial gradient ellipse; sine-wave alpha with per-lineage random period (4–6s); centroid lerps each frame; 2-second fade when lineage drops out of top 3
- AnimationManager integrated: processes events, tick_and_draw each frame; birth scale applied per-creature

**Why:** The glyph system makes creatures visually expressive and genetically legible — you can see family resemblance between kin. Kin lines and territory shimmer make population dynamics visible in the world without UI elements. Death/birth animations add biological weight to the simulation events that were previously invisible.

---

## [2026-03-04] - feat: Genome traits, lineage system, motion styles, and event queues

**What changed:**

*Genome (`simulation/genome.py`):*
- Added 6 new traits: `complexity`, `symmetry`, `stroke_scale`, `appendages`, `rotation_speed`, `motion_style`
- All follow the same 0–1 float range and mutation rules as existing traits
- `random()`, `mutate()`, `copy()` updated to include all 13 traits

*Creature (`simulation/creature.py`):*
- `lineage_id: int` — inherited lineage identifier for kin tracking
- `rotation_angle: float` — updated each frame; used by renderer to rotate glyph
- `glyph_surface: Any` — cache slot for renderer; `None` until first render
- Variable trail length: glide=14, swim=10, dart=5 positions (`get_trail_length()`)
- Swim oscillation: perpendicular sine component added to velocity in `update_position`
- Dart state machine: burst/cooldown timers; slow drift between bursts, fast snap toward food
- `steer_toward` enhanced: dart style uses 0.25 steer strength and 1.5× speed multiplier
- `wander` dispatches to `_wander_glide`, `_wander_swim`, `_wander_dart`

*Simulation (`simulation/simulation.py`):*
- `_next_lineage_id` counter; each initial creature gets its own lineage
- Speciation on reproduction: if offspring hue diverges > 0.15, it starts a new lineage
- `death_events: list[dict]` — populated on creature death; cleared by renderer
- `birth_events: list[Creature]` — populated on reproduction; cleared by renderer
- `get_lineage_counts() -> dict[int, int]` for renderer territory shimmer
- `get_dominant_traits()` updated to include all 13 traits

*Settings (`settings.py`):*
- New tuneable values: `glyph_size_base`, `kin_line_max_distance`, `kin_line_min_group`, `territory_top_n`, `territory_shimmer_lerp`, `territory_fade_seconds`, `death_animation_frames`, `birth_animation_frames`, `death_particle_count`

**Why:** The genome expansion provides the raw data for all new visual systems. Lineage tracking with speciation creates natural groupings that kin lines and territory shimmer can visualize. Event queues decouple animation triggering from simulation logic, preserving the sim/render boundary.

---

## [2026-03-04] - Initial Implementation

**What changed:** Created the complete Primordial screensaver application with energy mode simulation and ocean visual theme fully implemented. The project includes genome-based creatures with heritable traits, food particles with spatial bucketing for performance, smooth steering behavior, mutation/reproduction mechanics, and bioluminescent visual effects.

**Why:** This is the foundation of the project. The architecture was designed for extensibility — sim modes and visual themes are pluggable, simulation and rendering are decoupled, and all parameters are settings-driven. Energy mode and ocean theme serve as reference implementations for future modes/themes.

---

## [2026-03-04] - Project Scaffolding

**What changed:** Created project structure with virtual environment, installed pygame and numpy, initialized git repository, and set up .gitignore.

**Why:** Established clean project foundation with proper dependency isolation via venv, version control via git, and exclusion of generated files via .gitignore.

---

## [2026-03-04] - Settings System

**What changed:** Implemented Settings dataclass with validation for sim modes and visual themes, serialization methods, and all tuneable parameters.

**Why:** Central configuration ensures no hardcoded values and makes behavior easily adjustable. Validation catches invalid mode/theme names early.

---

## [2026-03-04] - Genome and Creature Systems

**What changed:** Implemented immutable Genome dataclass with random generation and mutation. Implemented Creature class with position, velocity, energy, steering behavior, and toroidal world handling.

**Why:** The genome system is the core of evolution — immutability ensures predictable mutation behavior. Smooth steering (vs. teleportation) makes movement visually pleasing. Toroidal topology removes edge effects.

---

## [2026-03-04] - Food System with Spatial Bucketing

**What changed:** Implemented Food particle and FoodManager with grid-based spatial hashing for efficient nearest-neighbor queries.

**Why:** With 300 creatures and 500 food particles, brute-force O(n²) lookup would kill framerate. Spatial bucketing brings this to O(1) average case per query, enabling smooth 60 FPS.

---

## [2026-03-04] - Energy Mode Simulation

**What changed:** Implemented the full energy mode simulation loop: food spawning, food-seeking with smooth steering, eating mechanics, energy-based reproduction with mutation, death from energy depletion, and overcrowding population control.

**Why:** Energy mode is the primary simulation. The loop order matters: spawn food → creatures act → reproduction → death cleanup. Overcrowding penalty creates natural population cycles.

---

## [2026-03-04] - Ocean Theme and Rendering

**What changed:** Implemented ocean theme with deep blue background, bioluminescent color palette, glowing blob creatures with trails, pulsing animation, twinkling food particles, and ambient depth particles.

**Why:** Visual appeal is critical for a screensaver. The glow effect uses concentric circles with decreasing alpha. Colors are mapped from genome hue to a cool-tones palette. Ambient particles add depth perception.

---

## [2026-03-04] - HUD System

**What changed:** Implemented toggleable HUD showing generation, population, oldest creature age, food count, current mode/theme, and FPS.

**Why:** HUD provides insight into simulation state without being intrusive. Semi-transparent panel with small font keeps it unobtrusive. Toggle (H key) lets users hide it for pure screensaver experience.

---

## [2026-03-04] - Main Loop and Controls

**What changed:** Implemented main entry point with pygame initialization, fullscreen/windowed support, game loop with FPS limiting, and keyboard controls (ESC/Q quit, H HUD, Space pause, F fullscreen, R reset, +/- food rate).

**Why:** Clean separation of concerns: main.py handles pygame setup and input, delegates simulation to Simulation class, delegates rendering to Renderer. Controls follow screensaver conventions.

---

## [2026-03-04] - Stub Modes and Documentation

**What changed:** Added stub themes that show "coming soon" overlay, created comprehensive README.md with installation/usage/extension guides, and AGENT.md with architectural documentation for future AI agents.

**Why:** Stubs make the settings system complete while clearly indicating unimplemented features. Documentation enables both human users and AI agents to understand and extend the codebase.
