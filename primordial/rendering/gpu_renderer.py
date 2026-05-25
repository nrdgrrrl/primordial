"""OpenGL predator/prey renderer."""

from __future__ import annotations

import json
import logging
import math
import time
from collections import deque
from dataclasses import dataclass
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
    glGetUniformLocation,
    glUniform1f,
    glUniform1i,
    glUniform2f,
    glUniform4f,
    glUseProgram,
    glVertexAttribDivisor,
    glViewport,
)
from OpenGL.raw.GL.VERSION.GL_2_0 import (
    glVertexAttribPointer as raw_glVertexAttribPointer,
)

from .presentation_layout import PresentationLayout, compute_layout
from .action_bar import ActionBar
from .glyphs import build_glyph_surface
from .help_overlay import HelpOverlay
from .hud import HUD
from .hud_focus import HUDFocus
from .inspect_mode import (
    InspectMode,
    build_inspect_overlay_surfaces,
    inspect_attention_refresh_interval_ticks,
)
from .predation_effects import PredationEffectManager
from .renderer import _ZONE_BG_COLORS, _blit_zone_labels
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
uniform float u_play_scale;
uniform float u_play_offset_x;
uniform float u_play_offset_y;

out vec2 v_local;
out vec4 v_color;
out vec2 v_shape;

void main() {
    vec2 pixel = (i_center + (in_pos * i_radius)) * u_play_scale + vec2(u_play_offset_x, u_play_offset_y);
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
uniform float u_play_scale;
uniform float u_play_offset_x;
uniform float u_play_offset_y;

out vec2 v_uv;
out vec4 v_color;

void main() {
    float c = cos(i_angle);
    float s = sin(i_angle);
    mat2 rot = mat2(c, -s, s, c);
    vec2 pixel = (i_center + rot * (in_pos * i_size)) * u_play_scale + vec2(u_play_offset_x, u_play_offset_y);
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
uniform float u_play_scale;
uniform float u_play_offset_x;
uniform float u_play_offset_y;
out vec4 v_color;

void main() {
    vec2 pixel = in_pos * u_play_scale + vec2(u_play_offset_x, u_play_offset_y);
    vec2 ndc = vec2((pixel.x / u_viewport.x) * 2.0 - 1.0,
                    1.0 - (pixel.y / u_viewport.y) * 2.0);
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


_OVERLAY_TEXTURE_VERTEX_SHADER = """
#version 330 core
layout (location = 0) in vec2 in_pos;
uniform vec2 u_viewport;
uniform vec4 u_rect;
out vec2 v_uv;

void main() {
    vec2 local_uv = in_pos * 0.5 + 0.5;
    vec2 pixel = vec2(
        u_rect.x + (local_uv.x * u_rect.z),
        u_rect.y + (local_uv.y * u_rect.w)
    );
    vec2 ndc = vec2((pixel.x / u_viewport.x) * 2.0 - 1.0,
                    1.0 - (pixel.y / u_viewport.y) * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
    v_uv = vec2(local_uv.x, 1.0 - local_uv.y);
}
"""


_OVERLAY_TEXTURE_FRAGMENT_SHADER = """
#version 330 core
uniform sampler2D u_texture;
uniform float u_alpha;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    vec4 sample_color = texture(u_texture, v_uv);
    float alpha = sample_color.a * u_alpha;
    if (alpha < 0.001) {
        discard;
    }
    frag_color = vec4(sample_color.rgb * alpha, alpha);
}
"""


@dataclass
class _OverlayTextureSlot:
    texture: int | None = None
    size: tuple[int, int] = (0, 0)
    content_key: tuple[object, ...] | None = None


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
        location = glGetUniformLocation(self.program, "u_viewport")
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
        self.hud_focus = HUDFocus()
        self.action_bar = ActionBar()
        self.hud = HUD(font_size=16)
        self.hud.visible = settings.show_hud
        self.settings_overlay = SettingsOverlay(settings)
        self.help_overlay = HelpOverlay()
        self.tutorial_overlay = TutorialOverlay()
        self._ui_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._ui_texture: int | None = None
        self._overlay_textures_supported = True
        self._overlay_textures: dict[str, _OverlayTextureSlot] = {
            "hud": _OverlayTextureSlot(),
            "zone_labels": _OverlayTextureSlot(),
            "inspect_panel": _OverlayTextureSlot(),
            "inspect_graph": _OverlayTextureSlot(),
            "action_bar": _OverlayTextureSlot(),
            "fallback_ui": _OverlayTextureSlot(),
            "gutter_right": _OverlayTextureSlot(),
            "gutter_bottom": _OverlayTextureSlot(),
        }
        self._overlay_font = pygame.font.Font(None, 72)
        self._overlay_small_font = pygame.font.Font(None, 24)
        self._debug_font = pygame.font.Font(None, 18)
        self._debug_timing: dict[str, float] = {}
        self._snapshot_debug_metrics: dict[str, float] = {}
        self._external_debug_metrics: dict[str, float] = {}
        self._debug_inspect_click_marker: tuple[float, float, float] | None = None
        self._inspect_highlight_cache_key: tuple[object, ...] | None = None
        self._inspect_highlight_cache_lines: tuple[LineSprite, ...] = ()
        self.predation_effect_manager = PredationEffectManager(
            enabled=bool(getattr(settings, "predation_kill_effects_enabled", True)),
            intensity=float(getattr(settings, "predation_kill_effect_intensity", 1.0)),
            max_active=int(getattr(settings, "predation_kill_effect_max_active", 64)),
        )
        self.ambient_particles = self.theme.create_ambient_particles(self.width, self.height, 30)
        self._zone_cache_key: tuple[object, ...] | None = None
        self._zone_cache: tuple[RadialSprite, ...] = ()
        self._zone_label_cache_key: tuple[object, ...] | None = None
        self._zone_label_surface: pygame.Surface | None = None
        self._layout_cache_key: tuple | None = None
        self._layout: PresentationLayout | None = None
        self._play_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
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
        self._overlay_texture_program = _ShaderProgram(
            _OVERLAY_TEXTURE_VERTEX_SHADER,
            _OVERLAY_TEXTURE_FRAGMENT_SHADER,
        )
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
        self._reset_overlay_texture_state()

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

    @property
    def layout(self) -> PresentationLayout:
        dw = getattr(self, "display_width", self.width)
        dh = getattr(self, "display_height", self.height)
        w = self.width
        h = self.height
        inspect = self.inspect_mode.enabled
        cache_key = (dw, dh, w, h, inspect)
        if cache_key != getattr(self, "_layout_cache_key", None) or self._layout is None:
            self._layout = compute_layout(
                dw,
                dh,
                w,
                h,
                inspect_active=inspect,
            )
            self._layout_cache_key = cache_key
        return self._layout

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

    def _reset_overlay_texture_state(self) -> None:
        for slot in self._overlay_textures.values():
            slot.size = (0, 0)
            slot.content_key = None

    def _mark_overlay_dirty(self, *names: str) -> None:
        for name in names:
            slot = self._overlay_textures.get(name)
            if slot is None:
                continue
            slot.content_key = None

    def set_theme(self, theme_name: str) -> None:
        self.theme = OceanTheme()
        self.ambient_particles = self.theme.create_ambient_particles(self.width, self.height, 30)
        self.inspect_mode.invalidate_render_caches()
        self.hud.invalidate_cache()
        self._reset_overlay_texture_state()

    def set_mode(self, mode_name: str) -> None:
        _ = mode_name
        self.inspect_mode.invalidate_render_caches()
        self.hud.invalidate_cache()
        self._reset_overlay_texture_state()

    def set_external_debug_metrics(self, metrics: dict[str, float]) -> None:
        self._external_debug_metrics = metrics

    def set_runtime_mode(self, mode: str) -> None:
        self.action_bar.set_runtime_mode(mode)

    def notify_mouse_motion(self, rel: tuple[int, int]) -> None:
        self.action_bar.notify_mouse_motion(rel)

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
        self._play_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._layout_cache_key = None
        self.ambient_particles = self.theme.create_ambient_particles(self.width, self.height, 30)
        self._zone_cache_key = None
        self._zone_cache = ()
        self._zone_label_cache_key = None
        self._zone_label_surface = None
        self._inspect_highlight_cache_key = None
        self._inspect_highlight_cache_lines = ()
        self.inspect_mode.invalidate_render_caches()
        self.hud.invalidate_cache()
        self._reset_overlay_texture_state()
        self._initialize_gl()
        self._log_gpu_coordinate_diagnostics("resize")

    def reset_runtime_state(self) -> None:
        self.frame_times.clear()
        self.fps = 0.0
        self._glyph_atlas = _GlyphAtlas()
        self._zone_cache_key = None
        self._zone_cache = ()
        self._zone_label_cache_key = None
        self._zone_label_surface = None
        self._debug_inspect_click_marker = None
        self._inspect_highlight_cache_key = None
        self._inspect_highlight_cache_lines = ()
        self.inspect_mode.invalidate_render_caches()
        self.hud.invalidate_cache()
        self.hud_focus.clear_selection()
        self._reset_overlay_texture_state()
        self.predation_effect_manager = PredationEffectManager(
            enabled=bool(getattr(self.settings, "predation_kill_effects_enabled", True)),
            intensity=float(getattr(self.settings, "predation_kill_effect_intensity", 1.0)),
            max_active=int(getattr(self.settings, "predation_kill_effect_max_active", 64)),
        )

    def toggle_hud(self) -> None:
        self.hud.toggle()
        self.settings.show_hud = self.hud.visible
        if not self.hud.visible:
            self.hud_focus.clear_selection()
        self.hud.invalidate_cache()
        self._mark_overlay_dirty("hud")
        self._mark_overlay_dirty("zone_labels")

    def _hud_refresh_interval_ticks(self, simulation) -> int:
        if self.debug_enabled:
            return 1
        quality = str(getattr(self.settings, "inspect_visual_quality", "balanced"))
        if self.inspect_mode.enabled and quality == "performance":
            return 8
        if self.inspect_mode.enabled and quality == "balanced":
            return 5
        if self.inspect_mode.enabled and quality == "high":
            return 3
        return 4

    def _inspect_budget_profile(self) -> str:
        return str(getattr(self.settings, "inspect_visual_quality", "balanced"))

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
        observe_inspect = getattr(self.inspect_mode, "observe_simulation", None)
        if callable(observe_inspect):
            timings.update(observe_inspect(simulation) or {})
        resolve_death_color = lambda event: self.theme.resolve_color_for_species(
            str(event.get("species", "none")),
            float(event["genome"].hue),
            float(event["genome"].saturation),
        )
        resolve_attack_color = lambda species, hue, saturation: self.theme.resolve_color_for_species(
            str(species),
            float(hue),
            float(saturation),
        )
        self.predation_effect_manager.configure(
            enabled=(
                simulation.settings.sim_mode == "predator_prey"
                and bool(getattr(self.settings, "predation_kill_effects_enabled", True))
            ),
            intensity=float(getattr(self.settings, "predation_kill_effect_intensity", 1.0)),
            max_active=int(getattr(self.settings, "predation_kill_effect_max_active", 64)),
        )
        self.predation_effect_manager.process_events(
            simulation.death_events,
            simulation.active_attacks,
            resolve_attack_color=resolve_attack_color,
            resolve_death_color=resolve_death_color,
            now=current_time,
        )
        t0 = time.perf_counter()
        snapshot = self._build_snapshot(simulation, anim_time)
        predation_sprites = self.predation_effect_manager.build_gpu_sprites(current_time)
        timings["snapshot_ms"] = (time.perf_counter() - t0) * 1000.0
        timings.update(self._snapshot_debug_metrics)
        bg = snapshot.background_color
        t0 = time.perf_counter()
        layout = self.layout
        gutter_mode = layout.is_gutter_layout
        if gutter_mode:
            glClearColor(0.024, 0.039, 0.071, 1.0)
        else:
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
        if predation_sprites.strike_glow_lines:
            self._draw_lines(predation_sprites.strike_glow_lines, width=3.0)
        if predation_sprites.strike_core_lines:
            self._draw_lines(predation_sprites.strike_core_lines, width=1.5)
        if predation_sprites.bloom_radials:
            self._draw_radials(predation_sprites.bloom_radials, blend="additive")
        if predation_sprites.ripple_radials:
            self._draw_radials(predation_sprites.ripple_radials, blend="normal")
        if predation_sprites.predator_pulse_radials:
            self._draw_radials(predation_sprites.predator_pulse_radials, blend="additive")
        self._draw_lines(snapshot.attack_lines, width=1.0)
        timings["attacks_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        self._draw_lines(snapshot.predator_highlights, width=2.0)
        timings["predator_highlights_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        inspect_lines, inspect_highlight_metrics = self._build_inspect_highlight(simulation, anim_time)
        timings.update(inspect_highlight_metrics)
        draw_lines_t0 = time.perf_counter()
        if inspect_lines:
            self._draw_lines(inspect_lines, width=2.0)
        debug_click_lines = self._build_debug_inspect_click_marker(current_time)
        if debug_click_lines:
            self._draw_lines(debug_click_lines, width=2.0)
        timings["inspect_highlight_draw_ms"] = (time.perf_counter() - draw_lines_t0) * 1000.0
        timings["inspect_highlight_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        hud_focus_creature = None
        if not self.inspect_mode.enabled and self.hud.visible and self.hud_focus.has_selection:
            self.hud_focus.observe_simulation(simulation)
            hud_focus_creature = self.hud_focus.get_selected_creature(simulation)
            if hud_focus_creature is None:
                self.hud_focus.clear_selection()
        hud_focus_lines = self._build_hud_focus_highlight(simulation, anim_time, hud_focus_creature)
        if hud_focus_lines:
            self._draw_lines(hud_focus_lines, width=1.0)
        timings["hud_focus_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        timings.update(self._draw_ui(simulation))
        timings["ui_ms"] = (time.perf_counter() - t0) * 1000.0

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
        budget_profile = self._inspect_budget_profile()
        budget_active = self.inspect_mode.enabled and budget_profile == "performance"
        ambient_step = 2 if budget_active else 1
        trail_step = 2 if budget_active else 1
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
            for particle in self.ambient_particles[::ambient_step]
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
                sampled_trail = trail[::trail_step]
                sampled_len = max(1, len(sampled_trail))
                for index, (tx, ty) in enumerate(sampled_trail):
                    t = (index + 1) / sampled_len
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
        kin_glow_lines = () if budget_active else kin_render.glow_lines
        kin_shimmer_sprites = () if budget_active else kin_render.shimmer_sprites
        kin_ms = (time.perf_counter() - kin_t0) * 1000.0

        attack_lines = []
        if not self.predation_effect_manager.enabled:
            attack_lines = [
                LineSprite(
                    ax,
                    ay,
                    tx,
                    ty,
                    (*_rgb01(self.theme.resolve_color_for_species(species, hue, saturation), 0.28),),
                )
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
            "inspect_quality_budget_active": 1.0 if budget_active else 0.0,
            "ambient_sprite_count": float(len(ambient)),
            "trail_sprite_count": float(len(trails)),
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

    def _play_transform(self) -> tuple[float, float, float, int, int]:
        layout = self.layout
        if layout.is_gutter_layout:
            vx, vy, vw, vh = layout.play_viewport_rect
            scale = layout.scale
            offset_x = float(vx) + layout.offset_x
            offset_y = float(vy) + layout.offset_y
            dw = getattr(self, "display_width", self.width)
            dh = getattr(self, "display_height", self.height)
            viewport_w = dw
            viewport_h = dh
        else:
            scale = 1.0
            offset_x = 0.0
            offset_y = 0.0
            viewport_w = self.width
            viewport_h = self.height
        return scale, offset_x, offset_y, viewport_w, viewport_h

    def _set_play_uniforms(self, program: _ShaderProgram, viewport_w: int, viewport_h: int, scale: float, offset_x: float, offset_y: float) -> None:
        program.use(viewport_w, viewport_h)
        glUniform1f(glGetUniformLocation(program.program, "u_play_scale"), scale)
        glUniform1f(glGetUniformLocation(program.program, "u_play_offset_x"), offset_x)
        glUniform1f(glGetUniformLocation(program.program, "u_play_offset_y"), offset_y)

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
        scale, offset_x, offset_y, viewport_w, viewport_h = self._play_transform()
        self._set_play_uniforms(self._radial_program, viewport_w, viewport_h, scale, offset_x, offset_y)
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
        scale, offset_x, offset_y, viewport_w, viewport_h = self._play_transform()
        self._set_play_uniforms(self._glyph_program, viewport_w, viewport_h, scale, offset_x, offset_y)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._glyph_atlas.texture)
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
        scale, offset_x, offset_y, viewport_w, viewport_h = self._play_transform()
        self._set_play_uniforms(self._line_program, viewport_w, viewport_h, scale, offset_x, offset_y)
        glBindVertexArray(self._line_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self._line_vbo)
        glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, GL_DYNAMIC_DRAW)
        glLineWidth(width)
        glDrawArrays(GL_LINES, 0, len(lines) * 2)

    def _draw_ui(self, simulation) -> dict[str, float]:
        timings = {
            "hud_ms": 0.0,
            "overlay_ms": 0.0,
            "inspect_ms": 0.0,
            "inspect_panel_ms": 0.0,
            "inspect_panel_layout_ms": 0.0,
            "inspect_graph_ms": 0.0,
            "inspect_graph_static_ms": 0.0,
            "inspect_graph_dynamic_ms": 0.0,
            "settings_ms": 0.0,
            "help_ms": 0.0,
            "tutorial_ms": 0.0,
            "action_bar_ms": 0.0,
            "ui_upload_ms": 0.0,
            "ui_overlay_count": 0.0,
        }
        action_bar_context = self.action_bar.build_context(
            simulation,
            inspect_enabled=self.inspect_mode.enabled,
            settings_visible=self.settings_overlay.visible,
            help_visible=self.help_overlay.visible,
            tutorial_visible=self.tutorial_overlay.visible,
            hud_visible=self.hud.visible,
            hud_focus_active=self.hud_focus.has_selection,
        )
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
            or self.action_bar.opacity(action_bar_context) > 0.0
        )
        if not should_draw:
            return timings
        use_overlay_textures = bool(getattr(self, "_overlay_textures_supported", False)) and not (
            self.settings_overlay.visible
            or self.settings_overlay.fade > 0
            or self.help_overlay.visible
            or self.help_overlay.fade > 0
            or self.tutorial_overlay.visible
            or self.tutorial_overlay.fade > 0
            or simulation.predator_prey_game_over_active
        )
        layout = self.layout
        gutter_mode = layout.is_gutter_layout

        if gutter_mode and use_overlay_textures:
            return self._draw_ui_gutter_overlay(simulation, timings, action_bar_context)

        if gutter_mode:
            return self._draw_ui_gutter_fallback(simulation, timings, action_bar_context)

        if use_overlay_textures:
            return self._draw_ui_overlay_textures(simulation, timings, action_bar_context)

        return self._draw_ui_fallback(simulation, timings, action_bar_context)

    def _draw_gutter_rect(self, name: str, rect: tuple[int, int, int, int], color: tuple[int, int, int, int]) -> None:
        rx, ry, rw, rh = rect
        if rw <= 0 or rh <= 0:
            return
        surface = pygame.Surface((rw, rh), pygame.SRCALPHA)
        surface.fill(color)
        self._upload_overlay_surface(
            name,
            surface,
            content_key=(name, rw, rh),
        )
        self._draw_overlay_texture(name, pygame.Rect(rx, ry, rw, rh), viewport=(self.display_width, self.display_height))

    def _draw_ui_gutter_overlay(self, simulation, timings: dict[str, float], action_bar_context) -> dict[str, float]:
        layout = self.layout
        overlay_viewport = (self.display_width, self.display_height)

        right_gx, right_gy, right_gw, right_gh = layout.right_gutter_rect
        if right_gw > 0 and right_gh > 0:
            self._draw_gutter_rect("gutter_right", layout.right_gutter_rect, (10, 18, 28, 240))

        bot_gx, bot_gy, bot_gw, bot_gh = layout.bottom_gutter_rect
        if bot_gw > 0 and bot_gh > 0:
            self._draw_gutter_rect("gutter_bottom", layout.bottom_gutter_rect, (10, 18, 28, 240))

        current_tick = int(getattr(simulation, "_frame", 0))
        debug_lines = self._build_debug_lines(self._debug_timing) if self.debug_enabled else None
        hud_refresh_bucket = current_tick // max(1, self._hud_refresh_interval_ticks(simulation))

        hud_x, hud_y, hud_w, hud_h = layout.hud_rect
        if self.hud.visible and hud_w > 0 and hud_h > 0:
            t0 = time.perf_counter()
            hud_surface, _ = self.hud.build_panel_surface(
                (hud_w, hud_h),
                simulation,
                self.fps,
                debug_lines=debug_lines,
                refresh_token=("hud", hud_refresh_bucket, tuple(debug_lines or ())),
            )
            timings["hud_ms"] = (time.perf_counter() - t0) * 1000.0
            if hud_surface.get_width() > 1 and hud_surface.get_height() > 1:
                timings["ui_upload_ms"] += self._upload_overlay_surface(
                    "hud",
                    hud_surface,
                    content_key=("hud", id(hud_surface), hud_surface.get_size()),
                )
                self._draw_overlay_texture("hud", pygame.Rect(hud_x, hud_y, hud_surface.get_width(), hud_surface.get_height()), viewport=overlay_viewport)
                timings["ui_overlay_count"] += 1.0

        if self.inspect_mode.enabled:
            right_gx, right_gy, right_gw, right_gh = layout.right_gutter_rect
            if right_gw > 0 and right_gh > 0:
                t0 = time.perf_counter()
                inspect_overlay = build_inspect_overlay_surfaces(
                    target_width=right_gw,
                    target_height=right_gh,
                    inspect_mode=self.inspect_mode,
                    simulation=simulation,
                )
                timings["inspect_ms"] = (time.perf_counter() - t0) * 1000.0
                if inspect_overlay is not None:
                    timings.update(inspect_overlay["timings"])
                    panel_surface = inspect_overlay["panel_surface"]
                    panel_rect = inspect_overlay["panel_rect"]
                    graph_surface = inspect_overlay["graph_surface"]
                    graph_rect = inspect_overlay["graph_rect"]
                    if panel_surface is not None:
                        screen_panel_rect = pygame.Rect(
                            right_gx + panel_rect.x,
                            right_gy + panel_rect.y,
                            panel_rect.width,
                            panel_rect.height,
                        )
                        timings["ui_upload_ms"] += self._upload_overlay_surface(
                            "inspect_panel",
                            panel_surface,
                            content_key=("inspect_panel", id(panel_surface), panel_surface.get_size()),
                        )
                        self._draw_overlay_texture("inspect_panel", screen_panel_rect, viewport=overlay_viewport)
                        timings["ui_overlay_count"] += 1.0
                    if graph_surface is not None:
                        graph_x, graph_y, graph_w, graph_h = layout.graph_rect
                        if graph_w > 0 and graph_h > 0:
                            screen_graph_rect = pygame.Rect(graph_x, graph_y, graph_rect.width, graph_rect.height)
                            timings["ui_upload_ms"] += self._upload_overlay_surface(
                                "inspect_graph",
                                graph_surface,
                                content_key=("inspect_graph", id(graph_surface), graph_surface.get_size()),
                            )
                            self._draw_overlay_texture("inspect_graph", screen_graph_rect, viewport=overlay_viewport)
                            timings["ui_overlay_count"] += 1.0

        t0 = time.perf_counter()
        action_bar_surface, action_bar_rect, action_bar_alpha = self.action_bar.overlay_state(
            (self.display_width, self.display_height),
            action_bar_context,
        )
        timings["action_bar_ms"] = (time.perf_counter() - t0) * 1000.0
        if action_bar_surface is not None and action_bar_rect is not None and action_bar_alpha > 0.0:
            timings["ui_upload_ms"] += self._upload_overlay_surface(
                "action_bar",
                action_bar_surface,
                content_key=("action_bar", id(action_bar_surface), action_bar_surface.get_size()),
            )
            self._draw_overlay_texture("action_bar", action_bar_rect, alpha=action_bar_alpha, viewport=overlay_viewport)
            timings["ui_overlay_count"] += 1.0
        return timings

    def _draw_ui_gutter_fallback(self, simulation, timings: dict[str, float], action_bar_context) -> dict[str, float]:
        layout = self.layout

        right_gx, right_gy, right_gw, right_gh = layout.right_gutter_rect
        if right_gw > 0 and right_gh > 0:
            gutter_panel = pygame.Surface((right_gw, right_gh), pygame.SRCALPHA)
            gutter_panel.fill((10, 18, 28, 240))
            self._upload_overlay_surface("gutter_right", gutter_panel, content_key=("gutter_right", right_gw, right_gh))
            self._draw_overlay_texture("gutter_right", pygame.Rect(right_gx, right_gy, right_gw, right_gh), viewport=(self.display_width, self.display_height))

        bot_gx, bot_gy, bot_gw, bot_gh = layout.bottom_gutter_rect
        if bot_gw > 0 and bot_gh > 0:
            gutter_panel = pygame.Surface((bot_gw, bot_gh), pygame.SRCALPHA)
            gutter_panel.fill((10, 18, 28, 240))
            self._upload_overlay_surface("gutter_bottom", gutter_panel, content_key=("gutter_bottom", bot_gw, bot_gh))
            self._draw_overlay_texture("gutter_bottom", pygame.Rect(bot_gx, bot_gy, bot_gw, bot_gh), viewport=(self.display_width, self.display_height))

        if self.settings_overlay.visible or self.settings_overlay.fade > 0:
            t0 = time.perf_counter()
            self.settings_overlay.update()
            ui_surf = pygame.Surface((self.display_width, self.display_height), pygame.SRCALPHA)
            self.settings_overlay.draw(ui_surf)
            self._upload_overlay_surface("fallback_ui", ui_surf, content_key=("fallback_ui_settings", time.perf_counter_ns()))
            self._draw_overlay_texture("fallback_ui", pygame.Rect(0, 0, self.display_width, self.display_height), viewport=(self.display_width, self.display_height))
            timings["settings_ms"] = (time.perf_counter() - t0) * 1000.0
        if self.help_overlay.visible or self.help_overlay.fade > 0:
            t0 = time.perf_counter()
            self.help_overlay.update()
            ui_surf = pygame.Surface((self.display_width, self.display_height), pygame.SRCALPHA)
            self.help_overlay.draw(ui_surf)
            self._upload_overlay_surface("fallback_ui", ui_surf, content_key=("fallback_ui_help", time.perf_counter_ns()))
            self._draw_overlay_texture("fallback_ui", pygame.Rect(0, 0, self.display_width, self.display_height), viewport=(self.display_width, self.display_height))
            timings["help_ms"] = (time.perf_counter() - t0) * 1000.0
        if self.tutorial_overlay.visible or self.tutorial_overlay.fade > 0:
            t0 = time.perf_counter()
            self.tutorial_overlay.set_runtime_context(
                hud_visible=self.hud.visible,
                settings_visible=self.settings_overlay.visible,
                help_visible=self.help_overlay.visible,
                game_over_visible=simulation.predator_prey_game_over_active,
            )
            self.tutorial_overlay.update()
            ui_surf = pygame.Surface((self.display_width, self.display_height), pygame.SRCALPHA)
            self.tutorial_overlay.draw(ui_surf)
            self._upload_overlay_surface("fallback_ui", ui_surf, content_key=("fallback_ui_tutorial", time.perf_counter_ns()))
            self._draw_overlay_texture("fallback_ui", pygame.Rect(0, 0, self.display_width, self.display_height), viewport=(self.display_width, self.display_height))
            timings["tutorial_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        action_bar_surface, action_bar_rect, action_bar_alpha = self.action_bar.overlay_state(
            (self.display_width, self.display_height),
            action_bar_context,
        )
        timings["action_bar_ms"] = (time.perf_counter() - t0) * 1000.0
        if action_bar_surface is not None and action_bar_rect is not None and action_bar_alpha > 0.0:
            self._upload_overlay_surface(
                "action_bar",
                action_bar_surface,
                content_key=("action_bar", id(action_bar_surface), action_bar_surface.get_size()),
            )
            self._draw_overlay_texture("action_bar", action_bar_rect, alpha=action_bar_alpha, viewport=(self.display_width, self.display_height))
            timings["action_bar_count"] += 1.0
        return timings

    def _draw_ui_overlay_textures(self, simulation, timings: dict[str, float], action_bar_context) -> dict[str, float]:
        current_tick = int(getattr(simulation, "_frame", 0))
        debug_lines = self._build_debug_lines(self._debug_timing) if self.debug_enabled else None
        hud_refresh_bucket = current_tick // max(1, self._hud_refresh_interval_ticks(simulation))
        t0 = time.perf_counter()
        hud_surface, hud_pos = self.hud.build_panel_surface(
            (self.width, self.height),
            simulation,
            self.fps,
            debug_lines=debug_lines,
            refresh_token=("hud", hud_refresh_bucket, tuple(debug_lines or ())),
        )
        timings["hud_ms"] = (time.perf_counter() - t0) * 1000.0
        if self.hud.visible and hud_surface.get_width() > 1 and hud_surface.get_height() > 1:
            timings["ui_upload_ms"] += self._upload_overlay_surface(
                "hud",
                hud_surface,
                content_key=("hud", id(hud_surface), hud_surface.get_size()),
            )
            self._draw_overlay_texture(
                "hud",
                pygame.Rect(hud_pos[0], hud_pos[1], hud_surface.get_width(), hud_surface.get_height()),
            )
            timings["ui_overlay_count"] += 1.0
            zone_label_surface = self._draw_zone_labels(simulation, target=None)
            if zone_label_surface is not None:
                timings["ui_upload_ms"] += self._upload_overlay_surface(
                    "zone_labels",
                    zone_label_surface,
                    content_key=("zone_labels", id(zone_label_surface), zone_label_surface.get_size()),
                )
                self._draw_overlay_texture(
                    "zone_labels",
                    pygame.Rect(0, 0, zone_label_surface.get_width(), zone_label_surface.get_height()),
                )
                timings["ui_overlay_count"] += 1.0
        t0 = time.perf_counter()
        inspect_overlay = build_inspect_overlay_surfaces(
            target_width=self.width,
            target_height=self.height,
            inspect_mode=self.inspect_mode,
            simulation=simulation,
        ) if self.inspect_mode.enabled else None
        timings["inspect_ms"] = (time.perf_counter() - t0) * 1000.0
        if inspect_overlay is not None:
            timings.update(inspect_overlay["timings"])
            panel_surface = inspect_overlay["panel_surface"]
            panel_rect = inspect_overlay["panel_rect"]
            graph_surface = inspect_overlay["graph_surface"]
            graph_rect = inspect_overlay["graph_rect"]
            if panel_surface is not None:
                timings["ui_upload_ms"] += self._upload_overlay_surface(
                    "inspect_panel",
                    panel_surface,
                    content_key=("inspect_panel", id(panel_surface), panel_surface.get_size()),
                )
                self._draw_overlay_texture("inspect_panel", panel_rect)
                timings["ui_overlay_count"] += 1.0
            if graph_surface is not None:
                timings["ui_upload_ms"] += self._upload_overlay_surface(
                    "inspect_graph",
                    graph_surface,
                    content_key=("inspect_graph", id(graph_surface), graph_surface.get_size()),
                )
                self._draw_overlay_texture("inspect_graph", graph_rect)
                timings["ui_overlay_count"] += 1.0
        t0 = time.perf_counter()
        action_bar_surface, action_bar_rect, action_bar_alpha = self.action_bar.overlay_state(
            (self.width, self.height),
            action_bar_context,
        )
        timings["action_bar_ms"] = (time.perf_counter() - t0) * 1000.0
        if action_bar_surface is not None and action_bar_rect is not None and action_bar_alpha > 0.0:
            timings["ui_upload_ms"] += self._upload_overlay_surface(
                "action_bar",
                action_bar_surface,
                content_key=("action_bar", id(action_bar_surface), action_bar_surface.get_size()),
            )
            self._draw_overlay_texture("action_bar", action_bar_rect, alpha=action_bar_alpha)
            timings["ui_overlay_count"] += 1.0
        return timings

    def _draw_ui_fallback(self, simulation, timings: dict[str, float], action_bar_context) -> dict[str, float]:
        self._ui_surface.fill((0, 0, 0, 0))
        if self.hud.visible:
            self._draw_zone_labels(simulation, target=self._ui_surface)
        debug_lines = self._build_debug_lines(self._debug_timing) if self.debug_enabled else None
        t0 = time.perf_counter()
        self.hud.render(self._ui_surface, simulation, self.fps, debug_lines=debug_lines)
        timings["hud_ms"] = (time.perf_counter() - t0) * 1000.0
        if simulation.predator_prey_game_over_active:
            t0 = time.perf_counter()
            self._draw_game_over_overlay(simulation)
            timings["overlay_ms"] = (time.perf_counter() - t0) * 1000.0
        t0 = time.perf_counter()
        timings.update(self._draw_inspect_overlay(simulation) or {})
        timings["inspect_ms"] = (time.perf_counter() - t0) * 1000.0
        if self.settings_overlay.visible or self.settings_overlay.fade > 0:
            t0 = time.perf_counter()
            self.settings_overlay.update()
            self.settings_overlay.draw(self._ui_surface)
            timings["settings_ms"] = (time.perf_counter() - t0) * 1000.0
        if self.help_overlay.visible or self.help_overlay.fade > 0:
            t0 = time.perf_counter()
            self.help_overlay.update()
            self.help_overlay.draw(self._ui_surface)
            timings["help_ms"] = (time.perf_counter() - t0) * 1000.0
        if self.tutorial_overlay.visible or self.tutorial_overlay.fade > 0:
            t0 = time.perf_counter()
            self.tutorial_overlay.set_runtime_context(
                hud_visible=self.hud.visible,
                settings_visible=self.settings_overlay.visible,
                help_visible=self.help_overlay.visible,
                game_over_visible=simulation.predator_prey_game_over_active,
            )
            self.tutorial_overlay.update()
            self.tutorial_overlay.draw(self._ui_surface)
            timings["tutorial_ms"] = (time.perf_counter() - t0) * 1000.0
        t0 = time.perf_counter()
        self.action_bar.draw(self._ui_surface, action_bar_context)
        timings["action_bar_ms"] = (time.perf_counter() - t0) * 1000.0
        upload_t0 = time.perf_counter()
        self._draw_surface_texture(self._ui_surface)
        timings["ui_upload_ms"] += (time.perf_counter() - upload_t0) * 1000.0
        return timings

    def _draw_zone_labels(self, simulation, target: pygame.Surface | None = None) -> pygame.Surface | None:
        """Build or blit the recovered HUD-gated environmental zone labels."""
        zone_label_key = (
            self.width,
            self.height,
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
        if zone_label_key != self._zone_label_cache_key:
            self._zone_label_cache_key = zone_label_key
            self._zone_label_surface = pygame.Surface(
                (self.width, self.height), pygame.SRCALPHA
            )
            _blit_zone_labels(
                self._zone_label_surface,
                simulation.zone_manager.zones,
                self._debug_font,
            )
        actual_target = self._ui_surface if target is None else target
        if self._zone_label_surface is not None and actual_target is not None:
            actual_target.blit(self._zone_label_surface, (0, 0))
        return self._zone_label_surface

    def _draw_inspect_overlay(self, simulation) -> dict[str, float]:
        """Draw the creature card overlay on the UI surface."""
        from .inspect_mode import draw_inspect_overlay

        return draw_inspect_overlay(self._ui_surface, self.inspect_mode, simulation)

    def _build_inspect_highlight(
        self,
        simulation,
        anim_time: float,
    ) -> tuple[list[LineSprite], dict[str, float]]:
        """Build line sprites for the inspect selection ring and attention target."""
        timings = {
            "inspect_ring_build_ms": 0.0,
            "inspect_attention_infer_ms": 0.0,
        }
        if not self.inspect_mode.enabled:
            return [], timings
        get_focus_creature = getattr(self.inspect_mode, "get_focus_creature", None)
        if callable(get_focus_creature):
            creature = get_focus_creature(simulation)
        else:
            creature = self.inspect_mode.get_selected_creature(simulation)
        if creature is None:
            self._inspect_highlight_cache_key = None
            self._inspect_highlight_cache_lines = ()
            return [], timings
        current_tick = int(getattr(simulation, "_frame", 0))
        pulse = 0.5 + 0.5 * math.sin(anim_time * 4.0)
        radius = creature.get_radius() + 6.0 + 4.0 * pulse
        color = (1.0, 1.0, 1.0, 0.8)
        cx, cy = creature.x, creature.y
        cache_key = (
            id(creature),
            round(cx, 2),
            round(cy, 2),
            round(radius, 2),
            current_tick,
        )
        if self._inspect_highlight_cache_key == cache_key and self._inspect_highlight_cache_lines:
            return list(self._inspect_highlight_cache_lines), timings
        ring_t0 = time.perf_counter()
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
        timings["inspect_ring_build_ms"] = (time.perf_counter() - ring_t0) * 1000.0
        attention_t0 = time.perf_counter()
        attention = self.inspect_mode.get_attention_target(
            simulation,
            creature,
            refresh_interval_ticks=inspect_attention_refresh_interval_ticks(simulation),
        )
        timings["inspect_attention_infer_ms"] = (time.perf_counter() - attention_t0) * 1000.0
        if attention is not None:
            t_pulse = 0.4 + 0.4 * math.sin(anim_time * 3.0)
            kind_colors = {
                "prey": (1.0, 0.3, 0.3, t_pulse),
                "threat": (1.0, 0.8, 0.2, t_pulse),
                "food": (0.3, 1.0, 0.3, t_pulse),
            }
            att_color = kind_colors.get(attention.kind, (1.0, 1.0, 1.0, t_pulse))
            lines.append(LineSprite(cx, cy, attention.x, attention.y, att_color))
        self._inspect_highlight_cache_key = cache_key
        self._inspect_highlight_cache_lines = tuple(lines)
        return lines, timings

    def _build_hud_focus_highlight(
        self,
        simulation,
        anim_time: float,
        hud_focus_creature,
    ) -> list[LineSprite]:
        """Build line sprites for the HUD focus ring and attention target."""
        if hud_focus_creature is None:
            return []
        cx, cy = hud_focus_creature.x, hud_focus_creature.y
        pulse = 0.5 + 0.5 * math.sin(anim_time * 3.0)
        radius = hud_focus_creature.get_radius() + 6.0 + 2.5 * pulse
        color = (0.7, 0.86, 1.0, 0.55 + 0.15 * pulse)
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
        attention = self.hud_focus.get_attention_target(simulation, hud_focus_creature)
        if attention is not None:
            t_pulse = 0.27 + 0.2 * math.sin(anim_time * 2.5)
            kind_colors = {
                "prey": (0.78, 0.31, 0.31, t_pulse),
                "threat": (0.78, 0.67, 0.20, t_pulse),
                "food": (0.31, 0.78, 0.31, t_pulse),
            }
            att_color = kind_colors.get(attention.kind, (0.63, 0.63, 0.71, t_pulse))
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
            "Dbg ui: inspect {inspect:.2f}  panel {panel:.2f}  graph {graph:.2f}  "
            "sample {sample:.2f}  upload {upload:.2f}".format(
                inspect=timings.get("inspect_ms", 0.0),
                panel=timings.get("inspect_panel_ms", 0.0),
                graph=timings.get("inspect_graph_ms", 0.0),
                sample=timings.get("inspect_lineage_sample_ms", 0.0),
                upload=timings.get("ui_upload_ms", 0.0),
            ),
            "Dbg inspect: ring {ring:.2f}  attention {attn:.2f}  line {line:.2f}  "
            "overlays {count:.0f}  q={quality}".format(
                ring=timings.get("inspect_ring_build_ms", 0.0),
                attn=timings.get("inspect_attention_infer_ms", 0.0),
                line=timings.get("inspect_highlight_draw_ms", 0.0),
                count=timings.get("ui_overlay_count", 0.0),
                quality=self._inspect_budget_profile(),
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

    def _ensure_overlay_texture(self, name: str) -> int | None:
        slot = self._overlay_textures.get(name)
        if slot is None:
            return None
        if slot.texture is None:
            slot.texture = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, slot.texture)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        return slot.texture

    def _upload_overlay_surface(
        self,
        name: str,
        surface: pygame.Surface,
        *,
        content_key: tuple[object, ...],
    ) -> float:
        texture = self._ensure_overlay_texture(name)
        slot = self._overlay_textures[name]
        if texture is None or slot.content_key == content_key:
            return 0.0
        t0 = time.perf_counter()
        data = pygame.image.tostring(surface, "RGBA", True)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, texture)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        if slot.size != surface.get_size():
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
            slot.size = surface.get_size()
        else:
            glTexSubImage2D(
                GL_TEXTURE_2D,
                0,
                0,
                0,
                surface.get_width(),
                surface.get_height(),
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                data,
            )
        slot.content_key = content_key
        return (time.perf_counter() - t0) * 1000.0

    def _draw_overlay_texture(
        self,
        name: str,
        rect: pygame.Rect,
        *,
        alpha: float = 1.0,
        viewport: tuple[int, int] | None = None,
    ) -> None:
        slot = self._overlay_textures.get(name)
        if slot is None or slot.texture is None:
            return
        vp = viewport or (self.width, self.height)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, slot.texture)
        glUseProgram(self._overlay_texture_program.program)
        glUniform1i(glGetUniformLocation(self._overlay_texture_program.program, "u_texture"), 0)
        glUniform2f(
            glGetUniformLocation(self._overlay_texture_program.program, "u_viewport"),
            float(vp[0]),
            float(vp[1]),
        )
        glUniform4f(
            glGetUniformLocation(self._overlay_texture_program.program, "u_rect"),
            float(rect.x),
            float(rect.y),
            float(rect.width),
            float(rect.height),
        )
        glUniform1f(
            glGetUniformLocation(self._overlay_texture_program.program, "u_alpha"),
            float(alpha),
        )
        glBindVertexArray(self._texture_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

    def _draw_surface_texture(self, surface: pygame.Surface) -> None:
        upload_ms = self._upload_overlay_surface(
            "fallback_ui",
            surface,
            content_key=("fallback_ui", time.perf_counter_ns()),
        )
        _ = upload_ms
        self._draw_overlay_texture(
            "fallback_ui",
            pygame.Rect(0, 0, surface.get_width(), surface.get_height()),
        )

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
