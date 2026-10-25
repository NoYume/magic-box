"""Game window: Layout C fight scene, other scenes, input pump (spec section 9).

Owner: Adetola + Nikhil
"""

import os
import time
from collections.abc import Mapping

import pygame

from magic_box.core.contracts import Frame, GameView, PlayerState
from magic_box.render.audio import Audio
from magic_box.render.camera_view import (
    CropSmoother,
    crop_rect_for_bbox,
    draw_opponent,
    draw_selfview,
    frame_to_surface,
)
from magic_box.render.debug_overlay import DebugOverlay
from magic_box.render.fx import Fx
from magic_box.render.hud import Hud
from magic_box.render.layout import Rect, compute_layout
from magic_box.render.projectiles import draw_projectiles
from magic_box.render.projectiles import glow_tints as projectile_glow_tints
from magic_box.render.scenes import draw_scene, make_style
from magic_box.render.scenes.victory import glow_tints as victory_glow_tints
from magic_box.render.style import Theme, lerp_rgb, make_background, pulse

ALL_KEY_CODES = tuple(
    getattr(pygame, name) for name in dir(pygame) if name.startswith("K_") and name != "K_"
)
MAX_DT_S = 0.1
STEP_HINT = "STEP INTO VIEW"


class Window:
    def __init__(self, cfg, headless: bool = False) -> None:
        if headless:
            os.environ["SDL_VIDEODRIVER"] = "dummy"
        pygame.init()
        self.cfg = cfg
        self.render_cfg = cfg["render"]
        disp = cfg["display"]
        self.width, self.height, self.fps = disp["width"], disp["height"], disp["fps"]
        flags = pygame.FULLSCREEN if disp["fullscreen"] else 0
        if disp["vsync"]:
            flags |= pygame.SCALED  # pygame only honors vsync with SCALED or OPENGL
        self.screen = pygame.display.set_mode(
            (self.width, self.height), flags, vsync=1 if disp["vsync"] else 0
        )
        pygame.display.set_caption("Magic Box")
        self.clock = pygame.time.Clock()
        self.theme = Theme(self.render_cfg)
        self.hud = Hud(cfg, self.theme)
        self.scene_style = make_style(self.render_cfg["scenes"], self.theme, cfg)
        self.proj_font = pygame.font.Font(None, self.render_cfg["projectiles"]["font_px"])
        self.layout = compute_layout(self.width, self.height, self.render_cfg)
        self.background = make_background(self.width, self.height, self.theme)
        self.fx = Fx(cfg, self.theme, self.layout)
        self.theme.prewarm(
            projectile_glow_tints(self.theme, self.render_cfg["projectiles"])
            + self.fx.glow_tints()
            + victory_glow_tints(self.theme)
        )
        self.audio = Audio(cfg, enabled=not headless)
        self.opp_smoothers = (
            CropSmoother(self.render_cfg["crop_smoothing"]),
            CropSmoother(self.render_cfg["crop_smoothing"]),
        )
        self.self_smoothers = (
            CropSmoother(self.render_cfg["crop_smoothing"]),
            CropSmoother(self.render_cfg["crop_smoothing"]),
        )
        self.debug = False
        self._debug_overlay = DebugOverlay(cfg)
        self._surf_cache: tuple[int, pygame.Surface] | None = None
        self._quit_key = pygame.key.key_code(cfg["keys"]["quit"])
        self._debug_key = pygame.key.key_code(cfg["keys"]["debug_overlay"])
        self._last_draw_t: float | None = None
        self._banner_text: str | None = None
        self._banner_since = 0.0

    def pump(self) -> tuple[frozenset[str], bool]:
        quit_requested = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_requested = True
            elif event.type == pygame.KEYDOWN:
                if event.key == self._quit_key:
                    quit_requested = True
                elif event.key == self._debug_key:
                    self.debug = not self.debug
        pressed = pygame.key.get_pressed()
        held = frozenset(pygame.key.name(code) for code in ALL_KEY_CODES if pressed[code])
        return held, quit_requested

    def tick(self) -> float:
        return self.clock.tick(self.fps) / 1000

    def close(self) -> None:
        pygame.quit()

    def _frame_surface(self, frame: Frame) -> pygame.Surface:
        if self._surf_cache is None or self._surf_cache[0] != frame.frame_idx:
            self._surf_cache = (frame.frame_idx, frame_to_surface(frame))
        return self._surf_cache[1]

    def draw(
        self,
        view: GameView,
        frame: Frame | None,
        states: Mapping[int, PlayerState],
        fps: float,
        dropped: int = 0,
    ) -> None:
        self.render(view, frame, states, time.monotonic())
        if self.debug:
            self._debug_overlay.draw(self.screen, states, fps, dropped)
        pygame.display.flip()

    def render(
        self, view: GameView, frame: Frame | None, states: Mapping[int, PlayerState], now: float
    ) -> None:
        """Draw one frame into `self.screen` at time `now` (no flip; tests call this)."""
        dt = 0.0 if self._last_draw_t is None else min(MAX_DT_S, max(0.0, now - self._last_draw_t))
        self._last_draw_t = now
        self.hud.update(view, dt)
        self.fx.update(view, dt)
        self.audio.update(view)
        if view.scene == "fight":
            self.screen.fill(tuple(self.render_cfg["background_rgb"]))
            self._draw_fight(view, frame, states, now)
        else:
            self.screen.blit(self.background, (0, 0))
            draw_scene(self.screen, view, self.scene_style, now)
        self._draw_banner(view, now)
        if view.scene == "fight":
            self.fx.draw_overlay(self.screen)

    # -- banner -------------------------------------------------------------

    def _draw_banner(self, view: GameView, now: float) -> None:
        if view.banner != self._banner_text:
            self._banner_text, self._banner_since = view.banner, now
        if not view.banner or view.scene == "victory":
            return  # the victory scene draws the banner as its headline
        th = self.theme
        if view.scene != "fight":
            font = th.font("big")
            w = font.size(view.banner)[0]
            if w > self.width - 220:  # shrink to fit the ribbon
                font = th.font_px(max(20, int(font.get_height() * (self.width - 220) / w)))
            img = th.text(view.banner, font, th.c["gold"])
            band = th.panel(self.width - 160, img.get_height() + 30, th.c["panel"], 210)
            y = self.height - band.get_height() - 30
            self.screen.blit(band, (80, y))
            self.screen.blit(
                img, img.get_rect(center=(self.width // 2, y + band.get_height() // 2))
            )
            return
        pop = self.render_cfg["fx"]["banner_pop_s"]
        age = now - self._banner_since
        scale = 1.0 + 0.3 * max(0.0, 1.0 - age / pop) if pop > 0 else 1.0
        for half in self.layout:
            self._half_banner(view.banner, half.half, scale)

    def _half_banner(self, text: str, half: Rect, scale: float) -> None:
        th = self.theme
        max_w = half.w - 140
        banner_px = th.title_px["banner"]
        font = th.font_px(banner_px)
        w = font.size(text)[0]
        if w > max_w:
            font = th.font_px(max(24, int(banner_px * max_w / w)))
        img = th.text(text, font, th.c["text"])
        cx, cy = half.x + half.w // 2, int(half.h * 0.42)
        band = th.panel(half.w - 20, img.get_height() + 36, th.c["panel"], 170)
        self.screen.blit(band, band.get_rect(center=(cx, cy)))
        img = th.scaled(img, scale)
        self.screen.blit(img, img.get_rect(center=(cx, cy)))

    # -- fight --------------------------------------------------------------

    def _draw_fight(
        self, view: GameView, frame: Frame | None, states: Mapping[int, PlayerState], now: float
    ) -> None:
        rc = self.render_cfg
        surf = self._frame_surface(frame) if frame is not None else None
        for half in self.layout:
            opp = states.get(half.shows_slot)
            crop = None
            if surf is not None and opp is not None and opp.tracking_ok:
                crop = self.opp_smoothers[half.viewer_slot].update(
                    crop_rect_for_bbox(
                        opp.bbox_px,
                        rc["crop_aspect"],
                        rc["crop_padding"],
                        surf.get_width(),
                        surf.get_height(),
                    )
                )
                draw_opponent(self.screen, half.half, surf, crop)
            else:
                if not (view.banner or "").startswith(STEP_HINT):  # "STEP INTO VIEW · 12"
                    self._step_into_view(half.half, now)
            enemy = view.players[half.shows_slot]
            limit_x = half.selfview.x - 10
            self.hud.draw_enemy(self.screen, half.enemy_bar, enemy, limit_x, now)
            me = states.get(half.viewer_slot)
            if surf is not None and me is not None and me.tracking_ok:
                sv_crop = self.self_smoothers[half.viewer_slot].update(
                    crop_rect_for_bbox(
                        me.bbox_px,
                        (half.selfview.w, half.selfview.h),
                        rc["crop_padding"],
                        surf.get_width(),
                        surf.get_height(),
                    )
                )
                draw_selfview(self.screen, half.selfview, surf, sv_crop, me.keypoints_px)
            self.hud.draw_panel(self.screen, half.hud, view.players[half.viewer_slot], now)
            if crop is None and surf is not None:
                crop = Rect(0, 0, surf.get_width(), surf.get_height())
            if crop is not None:
                draw_projectiles(
                    self.screen,
                    half.half,
                    crop,
                    view.projectiles,
                    half.viewer_slot,
                    rc["projectiles"],
                    self.proj_font,
                    self.theme,
                    now,
                )
        self.fx.draw(self.screen)
        for half in self.layout:
            self._shake(half.half, self.fx.shake_offset(half.viewer_slot, now))
        div = rc["divider_px"]
        pygame.draw.rect(
            self.screen,
            tuple(rc["divider_rgb"]),
            (self.width // 2 - div // 2, 0, div, self.height),
        )
        self.hud.draw_timer(self.screen, self.width // 2, view.timer_s, now)

    def _shake(self, half: Rect, offset: tuple[int, int]) -> None:
        if offset == (0, 0):
            return
        rect = pygame.Rect(half.as_tuple())
        copy = self.screen.subsurface(rect).copy()
        self.screen.set_clip(rect)
        self.screen.fill(tuple(self.render_cfg["background_rgb"]), rect)
        self.screen.blit(copy, (rect.x + offset[0], rect.y + offset[1]))
        self.screen.set_clip(None)

    def _step_into_view(self, half: Rect, now: float) -> None:
        th = self.theme
        col = lerp_rgb(th.c["dim"], th.c["text"], pulse(now, 3.0))
        th.blit_text(
            self.screen,
            STEP_HINT,
            "huge",
            col,
            "center",
            (half.x + half.w // 2, half.h // 3),
        )
