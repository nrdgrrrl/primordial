"""OpenGL predator/prey renderer."""

from __future__ import annotations

import json
import logging
import math
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
import pygame
from OpenGL.GL import (
    GL_ARRAY_BUFFER,
    GL_BLEND,
    GL_CLAMP_TO_EDGE,
    GL_COLOR_BUFFER_BIT,
    GL_COMPILE_STATUS,
    GL_DYNAMIC_DRAW,
    GL_FALSE,
    GL_FLOAT,
    GL_FRAGMENT_SHADER,
    GL_INFO_LOG_LENGTH,
    GL_LINEAR,
    GL_LINES,
    GL_LINK_STATUS,
    GL_NEAREST,
    GL_ONE,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_RGBA,
    GL_SRC_ALPHA,
    GL_STATIC_DRAW,
    GL_TEXTURE_2D,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T,
    GL_TRIANGLE_STRIP,
    GL_UNSIGNED_BYTE,
    GL_VIEWPORT,
    GL_VERTEX_SHADER,
    glActiveTexture,
    glAttachShader,
    glBindBuffer,
    glBindTexture,
    glBindVertexArray,
    glBlendFunc,
    glBufferData,
    glClear,
    glClearColor,
    glCompileShader,
    glCreateProgram,
    glCreateShader,
    glDeleteShader,
    glDrawArrays,
    glDrawArraysInstanced,
    glEnable,
    glEnableVertexAttribArray,
    glGenBuffers,
    glGenTextures,
    glGenVertexArrays,
    glGetProgramInfoLog,
    glGetProgramiv,
    glGetShaderInfoLog,
    glGetShaderiv,
    glGetIntegerv,
    glGetString,
    glLineWidth,
    glLinkProgram,
    glPixelStorei,
    glReadPixels,
    glShaderSource,
    glTexImage2D,
    glTexParameteri,
    glTexSubImage2D,
    glUniform1i,
    glUniform2f,
    glUseProgram,
    glVertexAttribDivisor,
    glViewport,
)
from OpenGL.raw.GL.VERSION.GL_2_0 import (
    glVertexAttribPointer as raw_glVertexAttribPointer,
)

from .glyphs import build_glyph_surface
from .help_overlay import HelpOverlay
from .hud import HUD
from .inspect_mode import InspectMode
from .renderer import _ZONE_BG_COLORS
from .settings_overlay import SettingsOverlay
from .tutorial_overlay import TutorialOverlay
from .snapshot import (
    GlyphSprite,
    KinLineStyle,
    KinLineRenderData,
    LineSprite,
    PredatorPreyRenderSnapshot,
    RadialSprite,
    build_gpu_kin_line_diagnostics,
    build_gpu_kin_line_sprites,
    build_kin_line_render_data,
    kin_line_style_from_settings,
    resolve_gpu_predator_prey_kin_line_distance,
    _GPU_PREDATOR_PREY_KIN_LINE_ALPHA_NEAR,
    _GPU_PREDATOR_PREY_KIN_LINE_ALPHA_FAR,
    _GPU_PREDATOR_PREY_KIN_LINE_WIDTH,
    _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_NEAR,
    _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_FAR,
    _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_WIDTH,
    KIN_LINE_STYLE_FILAMENT,
    KIN_LINE_STYLE_PLAIN,
)
from .themes import OceanTheme

GL_TEXTURE0 = 0x84C0
GL_UNPACK_ALIGNMENT = 0x0CF5
logger = logging.getLogger(__name__)


_QUAD_VERTICES = np.array(
    [
        -1.0,
        -1.0,
        1.0,
        -1.0,
        -1.0,
        1.0,
        1.0,
        1.0,
    ],
    dtype=np.float32,
)


_RADIAL_VERTEX_SHADER = """
#version 330 core
layout (location = 0) in vec2 in_pos;
layout (location = 1) in vec2 i_center;
layout (location = 2) in vec2 i_radius;
layout (location = 3) in vec4 i_color;
layout (location = 4) in vec2 i_shape;

uniform vec2 u_viewport;

out vec2 v_local;
out vec4 v_color;
out vec2 v_shape;

void main() {
    vec2 pixel = i_center + (in_pos * i_radius);
    vec2 ndc = vec2((pixel.x / u_viewport.x) * 2.0 - 1.0,
                    1.0 - (pixel.y / u_viewport.y) * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
    v_local = in_pos;
    v_color = i_color;
    v_shape = i_shape;
}
"""


_RADIAL_FRAGMENT_SHADER = """
#version 330 core
in vec2 v_local;
in vec4 v_color;
in vec2 v_shape;
out vec4 frag_color;

void main() {
    float d = length(v_local);
    if (d > 1.0) {
        discard;
    }
    float softness = clamp(v_shape.x, 0.001, 0.95);
    float power = max(0.05, v_shape.y);
    float edge = 1.0 - smoothstep(1.0 - softness, 1.0, d);
    float core = pow(max(0.0, 1.0 - d), power);
    float alpha = v_color.a * max(edge * 0.35, core);
    frag_color = vec4(v_color.rgb * alpha, alpha);
}
"""


_GLYPH_VERTEX_SHADER = """
#version 330 core
layout (location = 0) in vec2 in_pos;
layout (location = 1) in vec2 i_center;
layout (location = 2) in vec2 i_size;
layout (location = 3) in vec4 i_color;
layout (location = 4) in vec4 i_uv;
layout (location = 5) in float i_angle;

uniform vec2 u_viewport;

out vec2 v_uv;
out vec4 v_color;

void main() {
    float c = cos(i_angle);
    float s = sin(i_angle);
    mat2 rot = mat2(c, -s, s, c);
    vec2 pixel = i_center + rot * (in_pos * i_size);
    vec2 ndc = vec2((pixel.x / u_viewport.x) * 2.0 - 1.0,
                    1.0 - (pixel.y / u_viewport.y) * 2.0);
    vec2 local_uv = in_pos * 0.5 + 0.5;
    v_uv = mix(i_uv.xy, i_uv.zw, local_uv);
    v_color = i_color;
    gl_Position = vec4(ndc, 0.0, 1.0);
}
"""


_GLYPH_FRAGMENT_SHADER = """
#version 330 core
uniform sampler2D u_texture;
in vec2 v_uv;
in vec4 v_color;
out vec4 frag_color;

void main() {
    vec4 sample_color = texture(u_texture, v_uv);
    float alpha = sample_color.a * v_color.a;
    if (alpha < 0.01) {
        discard;
    }
    frag_color = vec4(v_color.rgb * alpha, alpha);
}
"""


_LINE_VERTEX_SHADER = """
#version 330 core
layout (location = 0) in vec2 in_pos;
layout (location = 1) in vec4 in_color;
uniform vec2 u_viewport;
out vec4 v_color;

void main() {
    vec2 ndc = vec2((in_pos.x / u_viewport.x) * 2.0 - 1.0,
                    1.0 - (in_pos.y / u_viewport.y) * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
    v_color = in_color;
}
"""


_LINE_FRAGMENT_SHADER = """
#version 330 core
in vec4 v_color;
out vec4 frag_color;

void main() {
    frag_color = vec4(v_color.rgb * v_color.a, v_color.a);
}
"""


_TEXTURE_VERTEX_SHADER = """
#version 330 core
layout (location = 0) in vec2 in_pos;
out vec2 v_uv;

void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""


_TEXTURE_FRAGMENT_SHADER = """
#version 330 core
uniform sampler2D u_texture;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    vec4 sample_color = texture(u_texture, v_uv);
    frag_color = vec4(sample_color.rgb * sample_color.a, sample_color.a);
}
"""


class _ShaderProgram:
    def __init__(self, vertex_source: str, fragment_source: str) -> None:
        self.program = glCreateProgram()
        vertex = self._compile(GL_VERTEX_SHADER, vertex_source)
        fragment = self._compile(GL_FRAGMENT_SHADER, fragment_source)
        glAttachShader(self.program, vertex)
        glAttachShader(self.program, fragment)
        glLinkProgram(self.program)
        if not glGetProgramiv(self.program, GL_LINK_STATUS):
            log = glGetProgramInfoLog(self.program).decode("utf-8", "replace")
            raise RuntimeError(f"OpenGL program link failed: {log}")
        glDeleteShader(vertex)
        glDeleteShader(fragment)

    @staticmethod
    def _compile(shader_type: int, source: str) -> int:
        shader = glCreateShader(shader_type)
        glShaderSource(shader, source)
        glCompileShader(shader)
        if not glGetShaderiv(shader, GL_COMPILE_STATUS):
            length = glGetShaderiv(shader, GL_INFO_LOG_LENGTH)
            log = glGetShaderInfoLog(shader, length).decode("utf-8", "replace")
            raise RuntimeError(f"OpenGL shader compile failed: {log}")
        return shader

    def use(self, width: int, height: int) -> None:
        glUseProgram(self.program)
        location = 0
        try:
            from OpenGL.GL import glGetUniformLocation

            location = glGetUniformLocation(self.program, "u_viewport")
        except Exception:
            location = -1
        if location >= 0:
            glUniform2f(location, float(width), float(height))


class _GlyphAtlas:
    def __init__(self, *, cell_size: int = 64, cells_per_row: int = 32) -> None:
        self.cell_size = cell_size
        self.cells_per_row = cells_per_row
        self.texture_size = cell_size * cells_per_row
        self.texture = glGenTextures(1)
        self._slots: dict[tuple[float, ...], tuple[float, float, float, float]] = {}
        self._next_slot = 0
        glBindTexture(GL_TEXTURE_2D, self.texture)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_RGBA,
            self.texture_size,
            self.texture_size,
            0,
            GL_RGBA,
            GL_UNSIGNED_BYTE,
            None,
        )

    def uv_for(self, glyph: GlyphSprite) -> tuple[float, float, float, float]:
        cached = self._slots.get(glyph.genome_key)
        if cached is not None:
            return cached
        if self._next_slot >= self.cells_per_row * self.cells_per_row:
            self._slots.clear()
            self._next_slot = 0

        slot = self._next_slot
        self._next_slot += 1
        col = slot % self.cells_per_row
        row = slot // self.cells_per_row
        x = col * self.cell_size
        y = row * self.cell_size
        surface = build_glyph_surface(glyph.genome, (255, 255, 255), self.cell_size)
        data = pygame.image.tostring(surface, "RGBA", True)
        glBindTexture(GL_TEXTURE_2D, self.texture)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        glTexSubImage2D(
            GL_TEXTURE_2D,
            0,
            x,
            y,
            self.cell_size,
            self.cell_size,
            GL_RGBA,
            GL_UNSIGNED_BYTE,
            data,
        )
        pad = 0.5 / self.texture_size
        uv = (
            (x / self.texture_size) + pad,
            (y / self.texture_size) + pad,
            ((x + self.cell_size) / self.texture_size) - pad,
            ((y + self.cell_size) / self.texture_size) - pad,
        )
        self._slots[glyph.genome_key] = uv
        return uv


class PredatorPreyGpuRenderer:
    """Lean OpenGL renderer for predator/prey mode."""

    backend_name = "gpu"

    def __init__(self, screen: pygame.Surface, settings, debug: bool = False) -> None:
        self.screen = screen
        self.settings = settings
        self.debug_enabled = debug
        self._refresh_presentation_sizes()
        self.width = self.window_width
        self.height = self.window_height
        self.theme = OceanTheme()
        self.start_time = time.time()
        self.frame_times: deque[float] = deque(maxlen=60)
        self.fps = 0.0
        self.show_predator_highlight = False
        self.show_cursor = False
        self.inspect_mode = InspectMode()
        self.hud = HUD(font_size=16)
        self.hud.visible = settings.show_hud
        self.settings_overlay = SettingsOverlay(settings)
        self.help_overlay = HelpOverlay()
        self.tutorial_overlay = TutorialOverlay()
        self._ui_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._ui_texture: int | None = None
        self._overlay_font = pygame.font.Font(None, 72)
        self._overlay_small_font = pygame.font.Font(None, 24)
        self._debug_timing: dict[str, float] = {}
        self._snapshot_debug_metrics: dict[str, float] = {}
        self._external_debug_metrics: dict[str, float] = {}
        self._debug_inspect_click_marker: tuple[float, float, float] | None = None
        self.ambient_particles = self.theme.create_ambient_particles(self.width, self.height, 30)
        self._zone_cache_key: tuple[object, ...] | None = None
        self._zone_cache: tuple[RadialSprite, ...] = ()
        self._initialize_gl()
        self._log_gpu_coordinate_diagnostics("startup")

    def _is_fullscreen(self) -> bool:
        return bool(self.screen.get_flags() & pygame.FULLSCREEN)

    def _active_gl_viewport_size(self) -> tuple[int, int]:
        if self._is_fullscreen():
            return self.drawable_width, self.drawable_height
        return self.window_width, self.window_height

    def _active_gl_viewport_policy(self) -> str:
        return "drawable_fullscreen" if self._is_fullscreen() else "logical_window"

    def _initialize_gl(self) -> None:
        viewport_w, viewport_h = self._active_gl_viewport_size()
        glViewport(0, 0, viewport_w, viewport_h)
        glEnable(GL_BLEND)
        glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
        self.gpu_info = {
            "vendor": _decode_gl_string(glGetString(0x1F00)),
            "renderer": _decode_gl_string(glGetString(0x1F01)),
            "version": _decode_gl_string(glGetString(0x1F02)),
            "glsl_version": _decode_gl_string(glGetString(0x8B8C)),
        }
        self._radial_program = _ShaderProgram(_RADIAL_VERTEX_SHADER, _RADIAL_FRAGMENT_SHADER)
        self._glyph_program = _ShaderProgram(_GLYPH_VERTEX_SHADER, _GLYPH_FRAGMENT_SHADER)
        self._line_program = _ShaderProgram(_LINE_VERTEX_SHADER, _LINE_FRAGMENT_SHADER)
        self._texture_program = _ShaderProgram(_TEXTURE_VERTEX_SHADER, _TEXTURE_FRAGMENT_SHADER)
        self._quad_vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self._quad_vbo)
        glBufferData(GL_ARRAY_BUFFER, _QUAD_VERTICES.nbytes, _QUAD_VERTICES, GL_STATIC_DRAW)
        self._radial_instance_vbo = glGenBuffers(1)
        self._glyph_instance_vbo = glGenBuffers(1)
        self._radial_vao = self._create_instanced_vao(
            stride=10,
            instance_vbo=self._radial_instance_vbo,
            extra_layout=(),
        )
        self._glyph_vao = self._create_instanced_vao(
            stride=13,
            instance_vbo=self._glyph_instance_vbo,
            extra_layout=((4, 4), (5, 1)),
        )
        self._line_vao = glGenVertexArrays(1)
        self._line_vbo = glGenBuffers(1)
        glBindVertexArray(self._line_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self._line_vbo)
        glEnableVertexAttribArray(0)
        raw_glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 6 * 4, ctypes_offset(0))
        glEnableVertexAttribArray(1)
        raw_glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 6 * 4, ctypes_offset(2 * 4))
        self._texture_vao = glGenVertexArrays(1)
        glBindVertexArray(self._texture_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self._quad_vbo)
        glEnableVertexAttribArray(0)
        raw_glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 2 * 4, ctypes_offset(0))
        self._glyph_atlas = _GlyphAtlas()
        self._ui_texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self._ui_texture)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

    def _refresh_presentation_sizes(self) -> None:
        """Refresh SDL logical-window and OpenGL drawable sizes."""
        window_size = (0, 0)
        get_window_size = getattr(pygame.display, "get_window_size", None)
        if callable(get_window_size):
            try:
                window_size = get_window_size()
            except pygame.error:
                window_size = (0, 0)
        drawable_size = self.screen.get_size()
        self.window_width = max(1, int(window_size[0] or drawable_size[0]))
        self.window_height = max(1, int(window_size[1] or drawable_size[1]))
        self.drawable_width = max(1, int(drawable_size[0]))
        self.drawable_height = max(1, int(drawable_size[1]))
        # Existing metrics/debug consumers use display_* for the GL drawable size.
        self.display_width = self.drawable_width
        self.display_height = self.drawable_height

    def _current_gl_viewport(self) -> list[int] | None:
        try:
            return [int(value) for value in glGetIntegerv(GL_VIEWPORT)]
        except Exception:
            return None

    def _log_gpu_coordinate_diagnostics(self, phase: str) -> None:
        active_viewport_w, active_viewport_h = self._active_gl_viewport_size()
        logger.debug(
            "GPU_COORDINATE_DIAGNOSTIC %s",
            json.dumps(
                {
                    "phase": phase,
                    "window_size": [self.window_width, self.window_height],
                    "screen_size": list(self.screen.get_size()),
                    "renderer_size": [self.width, self.height],
                    "renderer_display_size": [self.display_width, self.display_height],
                    "drawable_size": [self.drawable_width, self.drawable_height],
                    "active_gl_viewport_policy": self._active_gl_viewport_policy(),
                    "active_gl_viewport_size": [active_viewport_w, active_viewport_h],
                    "simulation_size": [self.width, self.height],
                    "gl_viewport": self._current_gl_viewport(),
                },
                sort_keys=True,
            ),
        )

    def _create_instanced_vao(
        self,
        *,
        stride: int,
        instance_vbo: int,
        extra_layout: tuple[tuple[int, int], ...],
    ) -> int:
        vao = glGenVertexArrays(1)
        glBindVertexArray(vao)
        glBindBuffer(GL_ARRAY_BUFFER, self._quad_vbo)
        glEnableVertexAttribArray(0)
        raw_glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 2 * 4, ctypes_offset(0))
        glBindBuffer(GL_ARRAY_BUFFER, instance_vbo)
        offset = 0
        for index, count in ((1, 2), (2, 2), (3, 4), *extra_layout):
            glEnableVertexAttribArray(index)
            raw_glVertexAttribPointer(index, count, GL_FLOAT, GL_FALSE, stride * 4, ctypes_offset(offset * 4))
            glVertexAttribDivisor(index, 1)
            offset += count
        if not extra_layout:
            glEnableVertexAttribArray(4)
            raw_glVertexAttribPointer(4, 2, GL_FLOAT, GL_FALSE, stride * 4, ctypes_offset(offset * 4))
            glVertexAttribDivisor(4, 1)
        return vao

    def set_theme(self, theme_name: str) -> None:
        self.theme = OceanTheme()
        self.ambient_particles = self.theme.create_ambient_particles(self.width, self.height, 30)

    def set_mode(self, mode_name: str) -> None:
        _ = mode_name

    def set_external_debug_metrics(self, metrics: dict[str, float]) -> None:
        self._external_debug_metrics = metrics

    def mark_debug_inspect_click(self, world_x: float, world_y: float) -> None:
        """Show the mapped inspect-click world position briefly in GPU debug mode."""
        if not self.debug_enabled:
            return
        self._debug_inspect_click_marker = (float(world_x), float(world_y), time.time() + 2.0)

    def resize(self, width: int, height: int, screen: pygame.Surface | None = None) -> None:
        self.width = width
        self.height = height
        if screen is not None:
            self.screen = screen
        self._refresh_presentation_sizes()
        self._ui_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.ambient_particles = self.theme.create_ambient_particles(self.width, self.height, 30)
        self._zone_cache_key = None
        self._zone_cache = ()
        self._initialize_gl()
        self._log_gpu_coordinate_diagnostics("resize")

    def reset_runtime_state(self) -> None:
        self.frame_times.clear()
        self.fps = 0.0
        self._glyph_atlas = _GlyphAtlas()
        self._zone_cache_key = None
        self._zone_cache = ()
        self._debug_inspect_click_marker = None

    def toggle_hud(self) -> None:
        self.hud.toggle()
        self.settings.show_hud = self.hud.visible

    def toggle_settings_overlay(self) -> None:
        if self.settings_overlay.visible:
            self.settings_overlay.close()
        else:
            self.settings_overlay.open()

    def open_help_overlay(self) -> None:
        self.help_overlay.open()

    def close_help_overlay(self) -> None:
        self.help_overlay.close()

    def open_tutorial_overlay(
        self,
        *,
        forced: bool = False,
        previous_paused: bool | None = None,
    ) -> None:
        self.tutorial_overlay.open(
            forced=forced,
            previous_paused=previous_paused,
        )

    def close_tutorial_overlay(self) -> str:
        return self.tutorial_overlay.close()

    def set_predator_highlight(self, active: bool) -> None:
        self.show_predator_highlight = active

    def blit_presentation_overlay(self, overlay: pygame.Surface) -> None:
        self._draw_surface_texture(overlay)

    def draw(self, simulation) -> dict[str, float]:
        frame_t0 = time.perf_counter()
        timings: dict[str, float] = {}
        current_time = time.time()
        anim_time = current_time - self.start_time
        self._update_fps(current_time)
        t0 = time.perf_counter()
        snapshot = self._build_snapshot(simulation, anim_time)
        timings["snapshot_ms"] = (time.perf_counter() - t0) * 1000.0
        timings.update(self._snapshot_debug_metrics)
        bg = snapshot.background_color
        t0 = time.perf_counter()
        glClearColor(bg[0], bg[1], bg[2], bg[3])
        glClear(GL_COLOR_BUFFER_BIT)
        timings["clear_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        self._draw_radials(snapshot.zones, blend="normal")
        timings["zones_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        self._draw_radials(snapshot.ambient, blend="normal")
        timings["ambient_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        self._draw_radials(snapshot.food, blend="additive")
        timings["food_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        self._draw_radials(snapshot.trails, blend="additive")
        timings["trails_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        kin_width = (
            _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_WIDTH
            if bool(getattr(self.settings, "kin_line_debug_boost", False))
            else _GPU_PREDATOR_PREY_KIN_LINE_WIDTH
        )
        kin_style = kin_line_style_from_settings(self.settings)
        if kin_style.style == KIN_LINE_STYLE_FILAMENT and snapshot.kin_glow_lines:
            glow_width = kin_width * kin_style.glow_width_scale
            self._draw_lines(snapshot.kin_glow_lines, width=glow_width)
        self._draw_lines(snapshot.kin_lines, width=kin_width)
        if snapshot.kin_shimmer_sprites:
            self._draw_radials(snapshot.kin_shimmer_sprites, blend="additive")
        timings["kin_lines_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        self._draw_radials(snapshot.glows, blend="additive")
        self._draw_radials(snapshot.bodies, blend="normal")
        self._draw_glyphs(snapshot.glyphs)
        timings["creatures_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        self._draw_lines(snapshot.attack_lines, width=1.0)
        timings["attacks_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        self._draw_lines(snapshot.predator_highlights, width=2.0)
        timings["predator_highlights_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        inspect_lines = self._build_inspect_highlight(simulation, anim_time)
        if inspect_lines:
            self._draw_lines(inspect_lines, width=2.0)
        debug_click_lines = self._build_debug_inspect_click_marker(current_time)
        if debug_click_lines:
            self._draw_lines(debug_click_lines, width=2.0)
        timings["inspect_highlight_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        self._draw_ui(simulation)
        timings["hud_ms"] = (time.perf_counter() - t0) * 1000.0

        self._drain_visual_events(simulation)
        timings.setdefault("events_ms", 0.0)
        timings.setdefault("territory_ms", 0.0)
        timings.setdefault("links_ms", timings.get("kin_lines_ms", 0.0))
        timings.setdefault("anim_ms", 0.0)
        timings.setdefault("stub_ms", 0.0)
        timings.setdefault("overlay_ms", 0.0)
        timings.setdefault("settings_ms", 0.0)
        timings.setdefault("presentation_copy_ms", 0.0)
        timings["render_core_ms"] = (time.perf_counter() - frame_t0) * 1000.0
        timings["draw_total_ms"] = timings["render_core_ms"]
        self._debug_timing = timings
        return timings

    def _build_snapshot(self, simulation, anim_time: float) -> PredatorPreyRenderSnapshot:
        zone_key = (
            self.width,
            self.height,
            float(self.settings.zone_background_intensity),
            tuple(
                (
                    zone.zone_type,
                    round(float(zone.x), 2),
                    round(float(zone.y), 2),
                    round(float(zone.radius), 2),
                )
                for zone in simulation.zone_manager.zones
            ),
        )
        if zone_key != self._zone_cache_key:
            intensity = max(0.0, float(self.settings.zone_background_intensity))
            self._zone_cache_key = zone_key
            self._zone_cache = tuple(
                RadialSprite(
                    zone.x,
                    zone.y,
                    zone.radius,
                    zone.radius,
                    _rgb01(
                        _ZONE_BG_COLORS.get(zone.zone_type, (60, 60, 60)),
                        alpha=min(0.22, 0.12 * intensity),
                    ),
                    0.95,
                    1.25,
                )
                for zone in simulation.zone_manager.zones
            )
        zones = self._zone_cache

        ambient = [
            RadialSprite(
                particle.x + math.sin(anim_time * particle.speed + particle.phase) * 20.0,
                particle.y + math.cos(anim_time * particle.speed * 0.7 + particle.phase) * 15.0,
                particle.radius,
                particle.radius,
                (0.07, 0.16, 0.34, particle.alpha / 255.0),
                0.95,
                1.5,
            )
            for particle in self.ambient_particles
        ]

        food: list[RadialSprite] = []
        for item in simulation.food_manager:
            depth = getattr(item, "depth_band", 1)
            bright = 1.15 if depth == 0 else 0.78 if depth == 2 else 1.0
            food.append(
                RadialSprite(
                    item.x,
                    item.y,
                    7.0,
                    7.0,
                    (0.72 * bright, 1.0 * bright, 1.0 * bright, 0.32),
                    0.82,
                    1.8,
                )
            )

        trails: list[RadialSprite] = []
        glows: list[RadialSprite] = []
        bodies: list[RadialSprite] = []
        glyphs: list[GlyphSprite] = []
        for creature in simulation.creatures:
            color = self.theme.resolve_color_for_creature(creature)
            depth_scale, depth_brightness, depth_alpha, trail_scale = _depth_style(creature.depth_band)
            color = tuple(min(255, int(channel * depth_brightness)) for channel in color)
            color = _apply_depth_tint(color, creature.depth_band)
            base_radius = creature.get_radius()
            pulse = 1.0 + 0.08 * math.sin(anim_time * 2.6 + creature._glyph_phase)
            radius = max(4.0, base_radius * pulse * depth_scale)
            rgb = _rgb01(color, depth_alpha)
            trail = creature.trail
            if trail:
                trail_len = max(1, len(trail))
                for index, (tx, ty) in enumerate(trail):
                    t = (index + 1) / trail_len
                    trails.append(
                        RadialSprite(
                            tx,
                            ty,
                            max(1.5, radius * 0.45 * t * trail_scale),
                            max(1.5, radius * 0.45 * t * trail_scale),
                            (rgb[0], rgb[1], rgb[2], 0.035 * t * depth_alpha),
                            0.92,
                            1.9,
                        )
                    )
            glows.append(
                RadialSprite(
                    creature.x,
                    creature.y,
                    radius * (2.9 if creature.depth_band == 0 else 2.2 if creature.depth_band == 2 else 2.55),
                    radius * (2.9 if creature.depth_band == 0 else 2.2 if creature.depth_band == 2 else 2.55),
                    (rgb[0], rgb[1], rgb[2], 0.22 * depth_alpha),
                    0.95,
                    1.65,
                )
            )
            bodies.append(
                RadialSprite(
                    creature.x,
                    creature.y,
                    radius,
                    radius,
                    (rgb[0], rgb[1], rgb[2], 0.55 * depth_alpha),
                    0.55,
                    0.45,
                )
            )
            age_frac = creature.get_age_fraction()
            alpha = max(0.35, 0.92 - max(0.0, age_frac - 0.72) * 1.35)
            glyphs.append(
                GlyphSprite(
                    creature.x,
                    creature.y,
                    max(20.0, base_radius * 2.45 * depth_scale),
                    (rgb[0], rgb[1], rgb[2], alpha * depth_alpha),
                    creature.rotation_angle,
                    _genome_key(creature.genome),
                    creature.genome,
                )
            )

        kin_t0 = time.perf_counter()
        kin_distance = resolve_gpu_predator_prey_kin_line_distance(self.settings)
        kin_min_group = max(2, int(self.settings.kin_line_min_group))
        kin_debug_boost = bool(getattr(self.settings, "kin_line_debug_boost", False))
        kin_alpha_near = (
            _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_NEAR
            if kin_debug_boost
            else _GPU_PREDATOR_PREY_KIN_LINE_ALPHA_NEAR
        )
        kin_alpha_far = (
            _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_FAR
            if kin_debug_boost
            else _GPU_PREDATOR_PREY_KIN_LINE_ALPHA_FAR
        )
        kin_style = kin_line_style_from_settings(self.settings)
        kin_line_diagnostics: dict[str, int | float] = {}
        kin_render = build_kin_line_render_data(
            simulation.creatures,
            world_width=self.width,
            world_height=self.height,
            max_distance=kin_distance,
            min_group=kin_min_group,
            color_for_member=lambda creature: _rgb3(
                self.theme.resolve_color_for_creature(creature)
            ),
            anim_time=anim_time,
            style=kin_style,
            alpha_near=kin_alpha_near,
            alpha_far=kin_alpha_far,
            diagnostics=kin_line_diagnostics,
        )
        kin_lines = kin_render.core_lines
        kin_glow_lines = kin_render.glow_lines
        kin_shimmer_sprites = kin_render.shimmer_sprites
        kin_ms = (time.perf_counter() - kin_t0) * 1000.0

        attack_lines = [
            LineSprite(ax, ay, tx, ty, (*_rgb01(self.theme.resolve_color_for_species(species, hue, saturation), 0.28),))
            for ax, ay, tx, ty, species, hue, saturation in simulation.active_attacks
        ]
        self._snapshot_debug_metrics = {
            "kin_lines_build_ms": kin_ms,
            "kin_line_count": float(kin_render.diagnostics.get("kin_line_count", 0)),
            "kin_line_segment_count": float(kin_render.diagnostics.get("kin_line_segment_count", 0)),
            "kin_line_shimmer_count": float(kin_render.diagnostics.get("kin_line_shimmer_count", 0)),
            "kin_line_max_distance": kin_distance,
            "kin_line_min_group": float(kin_min_group),
            "kin_line_qualifying_lineages": float(kin_line_diagnostics.get("qualifying_lineages", 0)),
            "kin_line_largest_lineage": float(kin_line_diagnostics.get("largest_lineage_size", 0)),
            "kin_line_debug_boost": 1.0 if kin_debug_boost else 0.0,
        }
        highlights = self._build_predator_highlights(simulation, anim_time)
        return PredatorPreyRenderSnapshot(
            background_color=(0.008, 0.031, 0.094, 1.0),
            zones=tuple(zones),
            ambient=tuple(ambient),
            food=tuple(food),
            trails=tuple(trails),
            kin_lines=tuple(kin_lines),
            kin_glow_lines=tuple(kin_glow_lines),
            kin_shimmer_sprites=tuple(kin_shimmer_sprites),
            glows=tuple(glows),
            bodies=tuple(bodies),
            glyphs=tuple(glyphs),
            attack_lines=tuple(attack_lines),
            predator_highlights=tuple(highlights),
        )

    def _build_predator_highlights(self, simulation, anim_time: float) -> list[LineSprite]:
        if not self.show_predator_highlight:
            return []
        result: list[LineSprite] = []
        for creature in simulation.creatures:
            if creature.species != "predator":
                continue
            color = _rgb01(self.theme.resolve_color_for_creature(creature), 0.72)
            pulse = 0.5 + 0.5 * math.sin(anim_time * 5.7 + creature._glyph_phase)
            radius = creature.get_radius() * self.settings.predator_highlight_radius_scale + 6.0 * pulse
            tick = max(8.0, radius * 0.55)
            cx, cy = creature.x, creature.y
            result.extend(
                [
                    LineSprite(cx, cy - radius, cx, cy - radius - tick, color),
                    LineSprite(cx + radius, cy, cx + radius + tick, cy, color),
                    LineSprite(cx, cy + radius, cx, cy + radius + tick, color),
                    LineSprite(cx - radius, cy, cx - radius - tick, cy, color),
                ]
            )
        return result

    def _draw_radials(self, sprites: tuple[RadialSprite, ...], *, blend: str) -> None:
        if not sprites:
            return
        glBlendFunc(GL_ONE, GL_ONE if blend == "additive" else GL_ONE_MINUS_SRC_ALPHA)
        data = np.array(
            [
                value
                for sprite in sprites
                for value in (
                    sprite.x,
                    sprite.y,
                    sprite.radius_x,
                    sprite.radius_y,
                    *sprite.color,
                    sprite.softness,
                    sprite.power,
                )
            ],
            dtype=np.float32,
        )
        self._radial_program.use(self.width, self.height)
        glBindVertexArray(self._radial_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self._radial_instance_vbo)
        glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, GL_DYNAMIC_DRAW)
        glDrawArraysInstanced(GL_TRIANGLE_STRIP, 0, 4, len(sprites))
        glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)

    def _draw_glyphs(self, glyphs: tuple[GlyphSprite, ...]) -> None:
        if not glyphs:
            return
        rows: list[float] = []
        for glyph in glyphs:
            uv = self._glyph_atlas.uv_for(glyph)
            rows.extend(
                [
                    glyph.x,
                    glyph.y,
                    glyph.size,
                    glyph.size,
                    *glyph.color,
                    *uv,
                    math.radians(glyph.angle_degrees),
                ]
            )
        data = np.array(rows, dtype=np.float32)
        self._glyph_program.use(self.width, self.height)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._glyph_atlas.texture)
        from OpenGL.GL import glGetUniformLocation

        glUniform1i(glGetUniformLocation(self._glyph_program.program, "u_texture"), 0)
        glBindVertexArray(self._glyph_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self._glyph_instance_vbo)
        glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, GL_DYNAMIC_DRAW)
        glDrawArraysInstanced(GL_TRIANGLE_STRIP, 0, 4, len(glyphs))

    def _draw_lines(self, lines: tuple[LineSprite, ...] | list[LineSprite], *, width: float) -> None:
        if not lines:
            return
        data = np.array(
            [
                value
                for line in lines
                for value in (
                    line.ax,
                    line.ay,
                    *line.color,
                    line.bx,
                    line.by,
                    *line.color,
                )
            ],
            dtype=np.float32,
        )
        self._line_program.use(self.width, self.height)
        glBindVertexArray(self._line_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self._line_vbo)
        glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, GL_DYNAMIC_DRAW)
        glLineWidth(width)
        glDrawArrays(GL_LINES, 0, len(lines) * 2)

    def _draw_ui(self, simulation) -> None:
        should_draw = (
            self.hud.visible
            or self.settings_overlay.visible
            or self.settings_overlay.fade > 0
            or self.help_overlay.visible
            or self.help_overlay.fade > 0
            or self.tutorial_overlay.visible
            or self.tutorial_overlay.fade > 0
            or simulation.predator_prey_game_over_active
            or self.inspect_mode.enabled
        )
        if not should_draw:
            return
        self._ui_surface.fill((0, 0, 0, 0))
        debug_lines = self._build_debug_lines(self._debug_timing) if self.debug_enabled else None
        self.hud.render(self._ui_surface, simulation, self.fps, debug_lines=debug_lines)
        if simulation.predator_prey_game_over_active:
            self._draw_game_over_overlay(simulation)
        self._draw_inspect_overlay(simulation)
        if self.settings_overlay.visible or self.settings_overlay.fade > 0:
            self.settings_overlay.update()
            self.settings_overlay.draw(self._ui_surface)
        if self.help_overlay.visible or self.help_overlay.fade > 0:
            self.help_overlay.update()
            self.help_overlay.draw(self._ui_surface)
        if self.tutorial_overlay.visible or self.tutorial_overlay.fade > 0:
            self.tutorial_overlay.set_runtime_context(
                hud_visible=self.hud.visible,
                settings_visible=self.settings_overlay.visible,
                help_visible=self.help_overlay.visible,
                game_over_visible=simulation.predator_prey_game_over_active,
            )
            self.tutorial_overlay.update()
            self.tutorial_overlay.draw(self._ui_surface)
        self._draw_surface_texture(self._ui_surface)

    def _draw_inspect_overlay(self, simulation) -> None:
        """Draw the creature card overlay on the UI surface."""
        from .inspect_mode import draw_inspect_overlay

        draw_inspect_overlay(self._ui_surface, self.inspect_mode, simulation)

    def _build_inspect_highlight(self, simulation, anim_time: float) -> list[LineSprite]:
        """Build line sprites for the inspect selection ring and attention target."""
        if not self.inspect_mode.enabled:
            return []
        creature = self.inspect_mode.get_selected_creature(simulation)
        if creature is None:
            return []
        pulse = 0.5 + 0.5 * math.sin(anim_time * 4.0)
        radius = creature.get_radius() + 6.0 + 4.0 * pulse
        color = (1.0, 1.0, 1.0, 0.8)
        cx, cy = creature.x, creature.y
        n = 24
        points = []
        for i in range(n):
            angle = 2.0 * math.pi * i / n
            px = cx + radius * math.cos(angle)
            py = cy + radius * math.sin(angle)
            points.append((px, py))
        lines = []
        for i in range(n):
            j = (i + 1) % n
            lines.append(LineSprite(points[i][0], points[i][1], points[j][0], points[j][1], color))

        from .creature_observation import infer_attention_target
        try:
            attention = infer_attention_target(creature, simulation)
        except Exception:
            attention = None
        if attention is not None:
            t_pulse = 0.4 + 0.4 * math.sin(anim_time * 3.0)
            kind_colors = {
                "prey": (1.0, 0.3, 0.3, t_pulse),
                "threat": (1.0, 0.8, 0.2, t_pulse),
                "food": (0.3, 1.0, 0.3, t_pulse),
            }
            att_color = kind_colors.get(attention.kind, (1.0, 1.0, 1.0, t_pulse))
            lines.append(LineSprite(cx, cy, attention.x, attention.y, att_color))

        return lines

    def _build_debug_inspect_click_marker(self, current_time: float) -> list[LineSprite]:
        """Build a short-lived debug marker at the inspect click's mapped world point."""
        marker = self._debug_inspect_click_marker
        if marker is None:
            return []
        x, y, expires_at = marker
        if current_time >= expires_at:
            self._debug_inspect_click_marker = None
            return []

        remaining = max(0.0, min(1.0, (expires_at - current_time) / 2.0))
        color = (1.0, 0.92, 0.22, 0.88 * remaining)
        radius = 14.0
        tick = 24.0
        segments = 24
        lines = [
            LineSprite(x - tick, y, x + tick, y, color),
            LineSprite(x, y - tick, x, y + tick, color),
        ]
        for index in range(segments):
            a0 = (math.tau * index) / segments
            a1 = (math.tau * (index + 1)) / segments
            lines.append(
                LineSprite(
                    x + math.cos(a0) * radius,
                    y + math.sin(a0) * radius,
                    x + math.cos(a1) * radius,
                    y + math.sin(a1) * radius,
                    color,
                )
            )
        return lines

    def _build_debug_lines(self, timings: dict[str, float]) -> list[str]:
        """Build compact debug timing lines for the HUD (GPU renderer)."""
        ext = self._external_debug_metrics
        event_ms = ext.get("event_ms", 0.0)
        sim_ms = ext.get("sim_ms", 0.0)
        draw_ms = timings.get("draw_total_ms", self._debug_timing.get("draw_total_ms", 0.0))
        present_ms = ext.get("present_ms", 0.0)
        pacing_ms = ext.get("pacing_ms", 0.0)
        frame_ms = ext.get("frame_ms", 0.0)
        eff_fps = ext.get("effective_fps", 0.0)
        sim_steps = int(ext.get("sim_steps", 0.0))
        clamp_frames = int(ext.get("clamp_frames", 0.0))
        dropped_ms = ext.get("dropped_ms", 0.0)
        result = [
            "Dbg frame: evt {evt:.2f}ms  sim {sim:.2f}ms  draw {draw:.2f}ms  "
            "flip {flip:.2f}ms".format(
                evt=event_ms,
                sim=sim_ms,
                draw=draw_ms,
                flip=present_ms,
            ),
            "Dbg loop: frame {frame:.2f}ms  pace {pace:.2f}ms  fps {fps:.1f}  "
            "steps {steps}  drops {drops}".format(
                frame=frame_ms,
                pace=pacing_ms,
                fps=eff_fps,
                steps=sim_steps,
                drops=clamp_frames,
            ),
            f"Dbg debt: dropped {dropped_ms:.2f}ms",
            "Dbg render: snap {snap:.2f}  clear {clear:.2f}  zones {zones:.2f}  "
            "amb {amb:.2f}  food {food:.2f}".format(
                snap=timings.get("snapshot_ms", 0.0),
                clear=timings.get("clear_ms", 0.0),
                zones=timings.get("zones_ms", 0.0),
                amb=timings.get("ambient_ms", 0.0),
                food=timings.get("food_ms", 0.0),
            ),
            "Dbg render: trails {trails:.2f}  creatures {creatures:.2f}  "
            "attacks {attacks:.2f}  hud {hud:.2f}".format(
                trails=timings.get("trails_ms", 0.0),
                creatures=timings.get("creatures_ms", 0.0),
                attacks=timings.get("attacks_ms", 0.0),
                hud=timings.get("hud_ms", 0.0),
            ),
        ]
        kin_count = int(timings.get("kin_line_count", 0.0))
        kin_segs = int(timings.get("kin_line_segment_count", 0.0))
        kin_shimmers = int(timings.get("kin_line_shimmer_count", 0.0))
        kin_dist = timings.get("kin_line_max_distance", 0.0)
        kin_min_grp = int(timings.get("kin_line_min_group", 0.0))
        kin_qual = int(timings.get("kin_line_qualifying_lineages", 0.0))
        kin_largest = int(timings.get("kin_line_largest_lineage", 0.0))
        kin_build_ms = timings.get("kin_lines_build_ms", 0.0)
        kin_boost = bool(timings.get("kin_line_debug_boost", 0.0))
        boost_tag = " [BOOST]" if kin_boost else ""
        result.append(
            f"Dbg kin: {kin_count} lines  {kin_segs} segs  "
            f"{kin_shimmers} shimmer  dist={kin_dist:.0f}  "
            f"min_grp={kin_min_grp}  qual={kin_qual}  "
            f"largest={kin_largest}  {kin_build_ms:.2f}ms{boost_tag}"
        )
        return result

    def _draw_game_over_overlay(self, simulation) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((160, 12, 18, 120))
        stats = simulation.get_predator_prey_stability_stats()
        title = self._overlay_font.render("GAME OVER", True, (255, 236, 236))
        overlay.blit(title, ((self.width - title.get_width()) // 2, max(40, self.height // 5)))
        lines = [
            f"Cause: {stats['collapse_cause'] or 'Unknown'}",
            f"Predators: {stats['collapse_predators']}   Prey: {stats['collapse_prey']}",
            f"Survival ticks: {stats['survival_ticks']}",
            f"Restart in: {math.ceil(float(stats['restart_countdown_seconds']))}s   Space: skip",
        ]
        y = max(40, self.height // 5) + title.get_height() + 24
        for line in lines:
            text = self._overlay_small_font.render(line, True, (255, 228, 228))
            overlay.blit(text, ((self.width - text.get_width()) // 2, y))
            y += text.get_height() + 10
        self._ui_surface.blit(overlay, (0, 0))

    def _draw_surface_texture(self, surface: pygame.Surface) -> None:
        if self._ui_texture is None:
            return
        data = pygame.image.tostring(surface, "RGBA", True)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._ui_texture)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_RGBA,
            surface.get_width(),
            surface.get_height(),
            0,
            GL_RGBA,
            GL_UNSIGNED_BYTE,
            data,
        )
        from OpenGL.GL import glGetUniformLocation

        glUseProgram(self._texture_program.program)
        glUniform1i(glGetUniformLocation(self._texture_program.program, "u_texture"), 0)
        glBindVertexArray(self._texture_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

    def _drain_visual_events(self, simulation) -> None:
        simulation.death_events.clear()
        simulation.birth_events.clear()
        simulation.cosmic_ray_events.clear()

    def _update_fps(self, current_time: float) -> None:
        self.frame_times.append(current_time)
        if len(self.frame_times) >= 2:
            elapsed = self.frame_times[-1] - self.frame_times[0]
            if elapsed > 0:
                self.fps = (len(self.frame_times) - 1) / elapsed

    def save_screenshot(self, path: str | Path) -> None:
        data = glReadPixels(0, 0, self.display_width, self.display_height, GL_RGBA, GL_UNSIGNED_BYTE)
        surface = pygame.image.fromstring(data, (self.display_width, self.display_height), "RGBA", True)
        pygame.image.save(surface, path)


def _decode_gl_string(raw: bytes | None) -> str:
    if raw is None:
        return "unknown"
    return raw.decode("utf-8", "replace")


def _rgb01(color: tuple[int, int, int], alpha: float) -> tuple[float, float, float, float]:
    return (
        max(0.0, min(1.0, color[0] / 255.0)),
        max(0.0, min(1.0, color[1] / 255.0)),
        max(0.0, min(1.0, color[2] / 255.0)),
        max(0.0, min(1.0, alpha)),
    )


def _rgb3(color: tuple[int, int, int]) -> tuple[float, float, float]:
    return (
        max(0.0, min(1.0, color[0] / 255.0)),
        max(0.0, min(1.0, color[1] / 255.0)),
        max(0.0, min(1.0, color[2] / 255.0)),
    )


def _depth_style(depth_band: int) -> tuple[float, float, float, float]:
    if depth_band <= 0:
        return 1.12, 1.18, 1.0, 1.25
    if depth_band >= 2:
        return 0.88, 0.72, 0.72, 0.78
    return 1.0, 1.0, 0.9, 1.0


def _apply_depth_tint(
    color: tuple[int, int, int],
    depth_band: int,
) -> tuple[int, int, int]:
    if depth_band <= 0:
        return (
            min(255, int(color[0] * 1.05 + 8)),
            min(255, int(color[1] * 1.04 + 10)),
            min(255, int(color[2] * 1.06 + 18)),
        )
    if depth_band >= 2:
        return (
            max(0, int(color[0] * 0.72)),
            max(0, int(color[1] * 0.82)),
            min(255, int(color[2] * 1.08 + 8)),
        )
    return color


def _genome_key(genome: Any) -> tuple[float, ...]:
    return (
        round(float(genome.complexity), 3),
        round(float(genome.symmetry), 3),
        round(float(genome.stroke_scale), 3),
        round(float(genome.appendages), 3),
        round(float(genome.rotation_speed), 3),
        round(float(genome.hue), 3),
        round(float(genome.saturation), 3),
        round(float(genome.speed), 3),
        round(float(genome.size), 3),
    )


def ctypes_offset(offset: int):
    import ctypes

    return ctypes.c_void_p(offset)
