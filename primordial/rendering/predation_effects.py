from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import pygame

from .snapshot import LineSprite, RadialSprite


Color = tuple[int, int, int]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def _rgb01(color: Color, alpha: float) -> tuple[float, float, float, float]:
    return (
        _clamp(color[0] / 255.0, 0.0, 1.0),
        _clamp(color[1] / 255.0, 0.0, 1.0),
        _clamp(color[2] / 255.0, 0.0, 1.0),
        _clamp(alpha, 0.0, 1.0),
    )


def _mix_color(left: Color, right: Color, t: float) -> Color:
    t = _clamp(t, 0.0, 1.0)
    return tuple(int((a * (1.0 - t)) + (b * t)) for a, b in zip(left, right))


def _cyan_accent(color: Color) -> Color:
    return _mix_color(color, (120, 246, 255), 0.72)


@dataclass(slots=True)
class PredationStrikeEffect:
    created_at: float
    ax: float
    ay: float
    tx: float
    ty: float
    color: Color
    accent_color: Color
    duration: float

    def progress(self, now: float) -> float:
        if self.duration <= 0.0:
            return 1.0
        return _clamp((now - self.created_at) / self.duration, 0.0, 1.0)

    def expired(self, now: float) -> bool:
        return (now - self.created_at) >= self.duration


@dataclass(slots=True)
class PredationKillEffect:
    created_at: float
    x: float
    y: float
    predator_x: float
    predator_y: float
    predator_color: Color
    prey_color: Color
    duration: float
    predator_pulse_duration: float

    def progress(self, now: float) -> float:
        if self.duration <= 0.0:
            return 1.0
        return _clamp((now - self.created_at) / self.duration, 0.0, 1.0)

    def pulse_progress(self, now: float) -> float:
        if self.predator_pulse_duration <= 0.0:
            return 1.0
        return _clamp((now - self.created_at) / self.predator_pulse_duration, 0.0, 1.0)

    def expired(self, now: float) -> bool:
        return (now - self.created_at) >= self.duration


@dataclass(frozen=True, slots=True)
class PredationGpuSprites:
    strike_glow_lines: tuple[LineSprite, ...] = ()
    strike_core_lines: tuple[LineSprite, ...] = ()
    bloom_radials: tuple[RadialSprite, ...] = ()
    ripple_radials: tuple[RadialSprite, ...] = ()
    predator_pulse_radials: tuple[RadialSprite, ...] = ()


class PredationEffectManager:
    """Bounded, renderer-owned kill visibility effects for predator-prey mode."""

    _BLOOM_FRAME_COUNT = 24
    _RIPPLE_FRAME_COUNT = 20
    _PULSE_FRAME_COUNT = 16
    _BLOOM_CACHE: dict[int, list[tuple[pygame.Surface, int]]] = {}
    _RIPPLE_CACHE: dict[int, list[tuple[pygame.Surface, int]]] = {}
    _PULSE_CACHE: dict[int, list[tuple[pygame.Surface, int]]] = {}

    def __init__(
        self,
        *,
        enabled: bool = True,
        intensity: float = 1.0,
        max_active: int = 64,
    ) -> None:
        self.enabled = bool(enabled)
        self.intensity = self._sanitize_intensity(intensity)
        self.max_active = self._sanitize_max_active(max_active)
        self._strikes: list[PredationStrikeEffect] = []
        self._kills: list[PredationKillEffect] = []

    def configure(self, *, enabled: bool, intensity: float, max_active: int) -> None:
        enabled_flag = bool(enabled)
        self.intensity = self._sanitize_intensity(intensity)
        self.max_active = self._sanitize_max_active(max_active)
        if not enabled_flag:
            self.reset()
        self.enabled = enabled_flag
        if self.enabled:
            self._trim_to_capacity()

    def reset(self) -> None:
        self._strikes.clear()
        self._kills.clear()

    @property
    def active_count(self) -> int:
        return len(self._strikes) + len(self._kills)

    @property
    def strike_count(self) -> int:
        return len(self._strikes)

    @property
    def kill_count(self) -> int:
        return len(self._kills)

    def process_events(
        self,
        death_events: list[dict],
        active_attacks: list[tuple[float, float, float, float, str, float, float]],
        *,
        resolve_attack_color: Callable[[str, float, float], Color],
        resolve_death_color: Callable[[dict], Color],
        now: float,
    ) -> None:
        self._prune(now)
        if not self.enabled:
            return

        strike_duration = _clamp(0.38 + (self.intensity * 0.18), 0.35, 0.80)
        kill_duration = _clamp(0.58 + (self.intensity * 0.28), 0.50, 1.20)
        pulse_duration = _clamp(0.24 + (self.intensity * 0.12), 0.20, 0.55)

        for ax, ay, tx, ty, species, hue, saturation in active_attacks:
            if species != 'predator':
                continue
            color = resolve_attack_color(species, hue, saturation)
            self._strikes.append(
                PredationStrikeEffect(
                    created_at=now,
                    ax=float(ax),
                    ay=float(ay),
                    tx=float(tx),
                    ty=float(ty),
                    color=color,
                    accent_color=_cyan_accent(color),
                    duration=strike_duration,
                )
            )

        for event in death_events:
            if event.get('cause') != 'predation':
                continue
            predator_hue = float(event.get('predator_hue', getattr(event.get('genome'), 'hue', 0.0)))
            predator_saturation = float(event.get('predator_saturation', getattr(event.get('genome'), 'saturation', 0.0)))
            predator_species = str(event.get('predator_species', 'predator'))
            predator_color = resolve_attack_color(predator_species, predator_hue, predator_saturation)
            prey_color = resolve_death_color(event)
            self._kills.append(
                PredationKillEffect(
                    created_at=now,
                    x=float(event['x']),
                    y=float(event['y']),
                    predator_x=float(event.get('predator_x', event['x'])),
                    predator_y=float(event.get('predator_y', event['y'])),
                    predator_color=predator_color,
                    prey_color=prey_color,
                    duration=kill_duration,
                    predator_pulse_duration=pulse_duration,
                )
            )

        self._trim_to_capacity()

    def draw_pygame(self, overlay: pygame.Surface, now: float) -> None:
        self._prune(now)
        if not self.enabled or self.active_count <= 0:
            return

        bloom_frames = self._get_bloom_frames()
        ripple_frames = self._get_ripple_frames()
        pulse_frames = self._get_pulse_frames()

        for strike in self._strikes:
            progress = strike.progress(now)
            fade = 1.0 - progress
            beam = _ease_out_cubic(fade)
            glow_alpha = int(34 * self.intensity * beam)
            thread_alpha = int(96 * self.intensity * beam)
            core_alpha = int(185 * self.intensity * (0.35 + beam * 0.65))
            core_color = _mix_color(strike.color, (255, 248, 255), 0.38)
            pygame.draw.line(overlay, (*strike.color, glow_alpha), (int(strike.ax), int(strike.ay)), (int(strike.tx), int(strike.ty)), 4)
            pygame.draw.line(overlay, (*strike.accent_color, thread_alpha), (int(strike.ax), int(strike.ay)), (int(strike.tx), int(strike.ty)), 2)
            pygame.draw.line(overlay, (*core_color, core_alpha), (int(strike.ax), int(strike.ay)), (int(strike.tx), int(strike.ty)), 1)
            prey_glow_radius = max(3, int(4 + (beam * 4 * self.intensity)))
            predator_glow_radius = max(2, int(3 + (beam * 3 * self.intensity)))
            pygame.draw.circle(overlay, (*strike.accent_color, min(255, core_alpha)), (int(strike.tx), int(strike.ty)), prey_glow_radius)
            pygame.draw.circle(overlay, (*strike.color, min(255, thread_alpha)), (int(strike.ax), int(strike.ay)), predator_glow_radius)

        for kill in self._kills:
            progress = kill.progress(now)
            bloom_index = min(self._BLOOM_FRAME_COUNT - 1, int(progress * (self._BLOOM_FRAME_COUNT - 1)))
            ripple_index = min(self._RIPPLE_FRAME_COUNT - 1, int(progress * (self._RIPPLE_FRAME_COUNT - 1)))
            bloom_surface, bloom_offset = bloom_frames[bloom_index]
            ripple_surface, ripple_offset = ripple_frames[ripple_index]
            overlay.blit(bloom_surface, (int(kill.x) - bloom_offset, int(kill.y) - bloom_offset))
            overlay.blit(ripple_surface, (int(kill.x) - ripple_offset, int(kill.y) - ripple_offset))
            pulse_progress = kill.pulse_progress(now)
            if pulse_progress < 1.0:
                pulse_index = min(self._PULSE_FRAME_COUNT - 1, int(pulse_progress * (self._PULSE_FRAME_COUNT - 1)))
                pulse_surface, pulse_offset = pulse_frames[pulse_index]
                overlay.blit(pulse_surface, (int(kill.predator_x) - pulse_offset, int(kill.predator_y) - pulse_offset))

    def build_gpu_sprites(self, now: float) -> PredationGpuSprites:
        self._prune(now)
        if not self.enabled or self.active_count <= 0:
            return PredationGpuSprites()

        strike_glow_lines: list[LineSprite] = []
        strike_core_lines: list[LineSprite] = []
        bloom_radials: list[RadialSprite] = []
        ripple_radials: list[RadialSprite] = []
        predator_pulse_radials: list[RadialSprite] = []

        for strike in self._strikes:
            progress = strike.progress(now)
            fade = 1.0 - progress
            beam = _ease_out_cubic(fade)
            glow_alpha = 0.10 * self.intensity * beam
            core_alpha = 0.42 * self.intensity * (0.35 + beam * 0.65)
            strike_glow_lines.append(LineSprite(strike.ax, strike.ay, strike.tx, strike.ty, _rgb01(strike.color, glow_alpha)))
            strike_core_lines.append(LineSprite(strike.ax, strike.ay, strike.tx, strike.ty, _rgb01(_mix_color(strike.accent_color, (255, 248, 255), 0.35), core_alpha)))
            bloom_radials.append(
                RadialSprite(
                    strike.tx,
                    strike.ty,
                    6.0 + (beam * 5.0 * self.intensity),
                    6.0 + (beam * 5.0 * self.intensity),
                    _rgb01(strike.accent_color, 0.16 * self.intensity * beam),
                    0.22,
                    7.5,
                )
            )

        for kill in self._kills:
            progress = kill.progress(now)
            bloom_t = _ease_out_cubic(progress)
            bloom_radius = 9.0 + (28.0 * self.intensity * bloom_t)
            warm_core = _mix_color(kill.predator_color, (255, 244, 252), 0.56)
            cool_halo = _mix_color(kill.prey_color, (128, 244, 255), 0.70)
            fade = 1.0 - progress
            bloom_radials.append(RadialSprite(kill.x, kill.y, bloom_radius * 0.92, bloom_radius * 0.92, _rgb01(cool_halo, 0.15 * self.intensity * fade), 0.88, 1.45))
            bloom_radials.append(RadialSprite(kill.x, kill.y, max(4.0, bloom_radius * 0.36), max(4.0, bloom_radius * 0.36), _rgb01(warm_core, 0.42 * self.intensity * fade), 0.55, 0.45))
            ripple_radials.append(
                RadialSprite(
                    kill.x,
                    kill.y,
                    12.0 + (34.0 * self.intensity * progress),
                    12.0 + (34.0 * self.intensity * progress),
                    _rgb01(_mix_color(cool_halo, (255, 255, 255), 0.18), 0.18 * self.intensity * fade),
                    0.16,
                    8.5,
                )
            )
            pulse_progress = kill.pulse_progress(now)
            if pulse_progress < 1.0:
                pulse_fade = 1.0 - pulse_progress
                predator_pulse_radials.append(
                    RadialSprite(
                        kill.predator_x,
                        kill.predator_y,
                        8.0 + (16.0 * self.intensity * pulse_progress),
                        8.0 + (16.0 * self.intensity * pulse_progress),
                        _rgb01(_mix_color(kill.predator_color, (255, 232, 210), 0.28), 0.16 * self.intensity * pulse_fade),
                        0.18,
                        7.0,
                    )
                )

        return PredationGpuSprites(
            strike_glow_lines=tuple(strike_glow_lines),
            strike_core_lines=tuple(strike_core_lines),
            bloom_radials=tuple(bloom_radials),
            ripple_radials=tuple(ripple_radials),
            predator_pulse_radials=tuple(predator_pulse_radials),
        )

    @staticmethod
    def _sanitize_intensity(value: float) -> float:
        return _clamp(float(value), 0.1, 2.5)

    @staticmethod
    def _sanitize_max_active(value: int) -> int:
        return max(1, int(value))

    def _prune(self, now: float) -> None:
        self._strikes = [effect for effect in self._strikes if not effect.expired(now)]
        self._kills = [effect for effect in self._kills if not effect.expired(now)]

    def _trim_to_capacity(self) -> None:
        while self.active_count > self.max_active:
            oldest_strike = self._strikes[0].created_at if self._strikes else float('inf')
            oldest_kill = self._kills[0].created_at if self._kills else float('inf')
            if oldest_strike <= oldest_kill:
                if self._strikes:
                    self._strikes.pop(0)
                elif self._kills:
                    self._kills.pop(0)
            else:
                if self._kills:
                    self._kills.pop(0)
                elif self._strikes:
                    self._strikes.pop(0)

    def _cache_key(self) -> int:
        return int(round(self.intensity * 100.0))

    def _get_bloom_frames(self) -> list[tuple[pygame.Surface, int]]:
        key = self._cache_key()
        cached = self._BLOOM_CACHE.get(key)
        if cached is not None:
            return cached
        if len(self._BLOOM_CACHE) >= 16:
            self._BLOOM_CACHE.clear()
        scale = self.intensity
        frames: list[tuple[pygame.Surface, int]] = []
        for index in range(self._BLOOM_FRAME_COUNT):
            t = index / max(1, self._BLOOM_FRAME_COUNT - 1)
            spread = _ease_out_cubic(t)
            radius = int(12 + (26 * scale * spread))
            size = max(12, radius * 2 + 8)
            center = size // 2
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            halo_alpha = int(118 * scale * (1.0 - t) ** 1.15)
            core_alpha = int(224 * scale * (1.0 - t) ** 0.62)
            fragment_alpha = int(88 * scale * (1.0 - t) ** 1.35)
            pygame.draw.circle(surface, (104, 240, 255, halo_alpha), (center, center), radius)
            pygame.draw.circle(surface, (255, 156, 218, halo_alpha // 2), (center, center), max(4, int(radius * 0.72)))
            pygame.draw.circle(surface, (255, 248, 255, core_alpha), (center, center), max(3, int(radius * 0.26)))
            fragment_radius = max(2, int(radius * 0.12))
            fragment_distance = max(5, int(radius * 0.58))
            for angle in (0.65 + t, 2.65 + t * 0.7, 4.45 + t * 1.2):
                fx = center + int(math.cos(angle) * fragment_distance)
                fy = center + int(math.sin(angle) * fragment_distance)
                pygame.draw.circle(surface, (132, 248, 255, fragment_alpha), (fx, fy), fragment_radius)
            frames.append((surface, center))
        self._BLOOM_CACHE[key] = frames
        return frames

    def _get_ripple_frames(self) -> list[tuple[pygame.Surface, int]]:
        key = self._cache_key()
        cached = self._RIPPLE_CACHE.get(key)
        if cached is not None:
            return cached
        if len(self._RIPPLE_CACHE) >= 16:
            self._RIPPLE_CACHE.clear()
        scale = self.intensity
        frames: list[tuple[pygame.Surface, int]] = []
        for index in range(self._RIPPLE_FRAME_COUNT):
            t = index / max(1, self._RIPPLE_FRAME_COUNT - 1)
            radius = int(10 + (40 * scale * _ease_out_cubic(t)))
            size = max(12, radius * 2 + 10)
            center = size // 2
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            alpha = int(72 * scale * (1.0 - t) ** 1.45)
            width = max(1, int(2 + (1.0 - t) * 2))
            pygame.draw.circle(surface, (164, 234, 255, alpha), (center, center), radius, width)
            pygame.draw.circle(surface, (255, 255, 255, max(0, alpha // 2)), (center, center), max(1, radius - 1), 1)
            frames.append((surface, center))
        self._RIPPLE_CACHE[key] = frames
        return frames

    def _get_pulse_frames(self) -> list[tuple[pygame.Surface, int]]:
        key = self._cache_key()
        cached = self._PULSE_CACHE.get(key)
        if cached is not None:
            return cached
        if len(self._PULSE_CACHE) >= 16:
            self._PULSE_CACHE.clear()
        scale = self.intensity
        frames: list[tuple[pygame.Surface, int]] = []
        for index in range(self._PULSE_FRAME_COUNT):
            t = index / max(1, self._PULSE_FRAME_COUNT - 1)
            radius = int(8 + (18 * scale * t))
            size = max(12, radius * 2 + 8)
            center = size // 2
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            ring_alpha = int(86 * scale * (1.0 - t) ** 1.25)
            fill_alpha = int(36 * scale * (1.0 - t) ** 1.85)
            pygame.draw.circle(surface, (255, 182, 136, fill_alpha), (center, center), max(2, int(radius * 0.54)))
            pygame.draw.circle(surface, (255, 220, 196, ring_alpha), (center, center), radius, 2)
            frames.append((surface, center))
        self._PULSE_CACHE[key] = frames
        return frames
