# Primordial — Build and Integration Reference

Practical details for building, packaging, and integrating the Primordial screensaver. This file covers topics that are primarily relevant to developers setting up builds or dealing with platform packaging — not things an AI agent editing code needs in its instructions file.

---

## Asset Path Resolution

All asset loading **must** use `get_base_path()` from `primordial/utils/paths.py`:

```python
from primordial.utils.paths import get_base_path

icon_path = get_base_path() / "assets" / "icon.ico"
font_path  = get_base_path() / "primordial" / "assets" / "font.ttf"
```

### Why this matters

When PyInstaller freezes the app with `--onefile`, all files are extracted at
runtime to a temporary directory and `sys._MEIPASS` is set to that directory.
Paths relative to `__file__` or the working directory won't resolve correctly
inside the bundle.

`get_base_path()` abstracts this:

| Environment | Returns |
|-------------|---------|
| Dev (source) | Project root (`Path(__file__).parent.parent.parent`) |
| PyInstaller frozen | `Path(sys._MEIPASS)` |

**Never** use bare `open("assets/foo.png")` or `Path(__file__).parent / "x"` for
files that must ship in the binary — use `get_base_path()` instead.

## Screensaver Argument Parsing

`primordial/utils/screensaver.py` provides `parse_screensaver_args() -> ScreensaverArgs`.

Windows passes arguments to `.scr` files when it invokes them:

| Windows argument | Parsed mode | Behaviour |
|-----------------|-------------|-----------|
| *(none)* | `normal` | Dev / direct launch — full controls, existing behaviour |
| `/s` or `-s` | `screensaver` | Fullscreen, hidden cursor, quit on any user input |
| `/p HWND` or `-p HWND` | `preview` | Render into existing window handle (screensaver Settings preview pane) |
| `/c` or `/c:HWND` | `config` | Show the config/about dialog |

### Preview mode and SDL_WINDOWID

When Windows invokes the `.scr` with `/p HWND`, it expects the screensaver to
render its output into an existing child window identified by the integer HWND.
SDL2 (and therefore pygame) honours the `SDL_WINDOWID` environment variable:
if set before `pygame.init()`, SDL renders into that window instead of creating
a new one.

**Critical ordering:**
1. Root `main.py` calls `parse_screensaver_args()` before importing `primordial.main`
2. If mode is `preview`, it sets `os.environ["SDL_WINDOWID"]` immediately
3. Only then does it `from primordial.main import main` — which triggers the
   module-level `import pygame`
4. `pygame.init()` called inside `main()` therefore sees the env var

Never move the SDL_WINDOWID assignment after the `from primordial.main import main`
line, or preview rendering will silently create a new window instead.

### Screensaver input handling (mode == "screensaver")

The screensaver must exit immediately on real user activity:

- `KEYDOWN` → quit
- `MOUSEBUTTONDOWN` → quit
- `MOUSEMOTION` with `abs(dx) > 4 or abs(dy) > 4` → quit (small threshold
  absorbs jitter; avoids false-quit on initial cursor settling)

A **2-second grace period** (`grace_until = time.time() + 2.0`) suppresses all
input events at startup — some systems emit a spurious mouse-move event when
the screensaver is first activated.

### Dual build output

`build.py` produces both files on Windows after a successful PyInstaller build:

```
dist/primordial.exe   ← for direct double-click launch
dist/primordial.scr   ← identical copy; right-click → Install for screensaver
```

Both files are the same binary; `.scr` is just the extension Windows recognises
as a screensaver. No `--add-data` or other flags differ between the two.

## Runtime CLI Flags

`primordial/utils/cli.py` provides `RuntimeArgs` via `parse_runtime_args()`.

Supported flags:

- `--debug`
  - Enables console logging (file logging is always on)
  - Enables debug HUD timing lines
  - Enables FPS + population history graph overlay
- `--profile`
  - Runs the app for 60 seconds
  - Dumps cProfile binary + text report to the config directory
  - Exits automatically
- `--mode <energy|predator_prey|boids|drift>`
  - Non-persistent mode override for this launch only
- `--theme <ocean|petri|geometric|chaotic>`
  - Non-persistent theme override for this launch only

The parser is tolerant (`parse_known_args`) so Windows screensaver args (`/s`, `/p`, `/c`) continue to work.

## Build Process

### Entry points

- `main.py` (project root) — top-level entry point; delegates to `primordial.main.main(scr_args, runtime_args)`.
  Used by PyInstaller and can also be run directly with `python main.py`.
- `primordial/main.py` — real implementation; uses relative imports, so it cannot be
  the direct PyInstaller target.

### Building the executable

```bash
python build.py          # cleans dist/, runs PyInstaller, prints result path
pyinstaller primordial.spec  # reproducible rebuild using committed .spec file
```

`build.py` does the following:
1. Deletes `build/` and `dist/` to ensure a clean state
2. Invokes `PyInstaller.__main__.run()` programmatically with `--onefile --noconsole`
3. Attaches `--add-data=primordial/assets:primordial/assets` when that directory exists
4. Attaches `--icon=assets/icon.ico` on Windows when the file exists

### .spec file

`primordial.spec` is committed and should be updated whenever build arguments change
(new `--add-data` entries, new hidden imports, etc.). The spec is regenerated
automatically on each `python build.py` run.

### Adding new assets

1. Place the file under `primordial/assets/` (create the directory if needed)
2. Load it via `get_base_path() / "primordial" / "assets" / "filename"`
3. Add `--add-data=primordial/assets{os.pathsep}primordial/assets` to `build.py` args
   (already present if the directory exists)

## Logging

`primordial/main.py` configures stdlib logging on startup:

- Log file: `primordial.log` in the same platform config directory as `config.toml`
- If that path is not writable, output falls back to the current working directory
- `--debug` adds a stdout handler at `DEBUG` level
- Non-debug runs log at `INFO` to file only