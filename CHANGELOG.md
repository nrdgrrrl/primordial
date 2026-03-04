# Changelog

All notable changes to Primordial are documented in this file.

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
