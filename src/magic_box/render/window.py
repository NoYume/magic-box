"""Game window: Layout C fight scene, other scenes, input pump (spec section 9).

Owner: Adetola + Nikhil
"""

import os
from collections.abc import Mapping

import pygame

from magic_box.core.contracts import Frame, GameView, PlayerState
from magic_box.render.camera_view import (
    CropSmoother,
    crop_rect_for_bbox,
    draw_opponent,
    draw_selfview,
    frame_to_surface,
)
from magic_box.render.debug_overlay import draw_debug_overlay
from magic_box.render.hud import draw_enemy_bar, draw_hud
from magic_box.render.layout import Rect, compute_layout
from magic_box.render.projectiles import draw_projectiles
from magic_box.render.scenes import draw_scene

ALL_KEY_CODES = tuple(
    getattr(pygame, name) for name in dir(pygame) if name.startswith("K_") and name != "K_"
)
TEXT_RGB = (240, 240, 240)
BANNER_SIZE = 96
HUD_FONT_SIZE = 32
HINT_FONT_SIZE = 56


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
        self.screen = pygame.display.set_mode((self.width, self.height), flags)
        pygame.display.set_caption("Magic Box")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, HUD_FONT_SIZE)
        self.hint_font = pygame.font.Font(None, HINT_FONT_SIZE)
        self.banner_font = pygame.font.Font(None, BANNER_SIZE)
        self.layout = compute_layout(self.width, self.height, self.render_cfg)
        self.opp_smoothers = (
            CropSmoother(self.render_cfg["crop_smoothing"]),
            CropSmoother(self.render_cfg["crop_smoothing"]),
        )
        self.self_smoothers = (
            CropSmoother(self.render_cfg["crop_smoothing"]),
            CropSmoother(self.render_cfg["crop_smoothing"]),
        )
        self.debug = False
        self._surf_cache: tuple[int, pygame.Surface] | None = None
        self._quit_key = pygame.key.key_code(cfg["keys"]["quit"])
        self._debug_key = pygame.key.key_code(cfg["keys"]["debug_overlay"])

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

    def _centered_text(self, text: str, font, rect: Rect) -> None:
        img = font.render(text, True, TEXT_RGB)
        self.screen.blit(img, img.get_rect(center=(rect.x + rect.w // 2, rect.y + rect.h // 2)))

    def draw(
        self,
        view: GameView,
        frame: Frame | None,
        states: Mapping[int, PlayerState],
        fps: float,
        dropped: int = 0,
    ) -> None:
        self.screen.fill(tuple(self.render_cfg["background_rgb"]))
        if view.scene == "fight":
            self._draw_fight(view, frame, states)
        else:
            draw_scene(self.screen, view)
        if view.banner:
            img = self.banner_font.render(view.banner, True, TEXT_RGB)
            self.screen.blit(img, img.get_rect(center=(self.width // 2, self.height // 2)))
        if self.debug:
            draw_debug_overlay(self.screen, states, fps, dropped)
        pygame.display.flip()

    def _draw_fight(
        self, view: GameView, frame: Frame | None, states: Mapping[int, PlayerState]
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
                self._centered_text("STEP INTO VIEW", self.hint_font, half.half)
            draw_enemy_bar(self.screen, half.enemy_bar, view.players[half.shows_slot], self.font)
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
            draw_hud(self.screen, half.hud, view.players[half.viewer_slot], self.font)
            if crop is None and surf is not None:
                crop = Rect(0, 0, surf.get_width(), surf.get_height())
            if crop is not None:
                draw_projectiles(self.screen, half.half, crop, view.projectiles, half.viewer_slot)
        div = rc["divider_px"]
        pygame.draw.rect(
            self.screen,
            tuple(rc["divider_rgb"]),
            (self.width // 2 - div // 2, 0, div, self.height),
        )
