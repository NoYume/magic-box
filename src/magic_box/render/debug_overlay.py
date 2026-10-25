"""Perception debug overlay: status panels, wrist_vz graph, top-down map (spec section 10).

Owner: Enoch
"""

import time
from collections import deque
from collections.abc import Mapping, Sequence

import pygame

from magic_box.core.contracts import PlayerState, Push
from magic_box.render.layout import Rect, compute_layout


class SlotHistory:
    """Recent wrist_vz samples and the last push for one slot."""

    def __init__(self, graph_s: float) -> None:
        self.graph_s = graph_s
        self.samples: deque[tuple[float, float, float]] = deque()  # (cam_t, vz_l, vz_r)
        self.frames: deque[tuple[int, float]] = deque()  # (frame_idx, cam_t)
        self.last_push: Push | None = None
        self.last_push_t = 0.0
        self._last_idx: int | None = None

    def add(self, state: PlayerState) -> bool:
        """Record a state. False when this frame_idx was already seen."""
        if state.frame_idx == self._last_idx:
            return False
        newest_t = self.samples[-1][0] if self.samples else None
        newest_idx = self.frames[-1][0] if self.frames else None
        if (newest_t is not None and state.cam_t < newest_t) or (
            newest_idx is not None and state.frame_idx < newest_idx
        ):
            self.samples.clear()  # SVO rewind or perception restart: the old loop is stale
            self.frames.clear()
        self._last_idx = state.frame_idx
        self.samples.append((state.cam_t, state.wrist_vz["L"], state.wrist_vz["R"]))
        self.frames.append((state.frame_idx, state.cam_t))
        if state.push is not None:
            self.last_push = state.push
            self.last_push_t = state.t
        cutoff = state.cam_t - self.graph_s
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()
        while self.frames and self.frames[0][1] < cutoff:
            self.frames.popleft()
        return True


def camera_fps(frames: Sequence[tuple[int, float]]) -> float:
    if len(frames) < 2:
        return 0.0
    dt = frames[-1][1] - frames[0][1]
    return (frames[-1][0] - frames[0][0]) / dt if dt > 0 else 0.0


def vz_to_y(vz: float, rect: Rect, vz_range: float) -> int:
    y = round(rect.y + rect.h / 2 + (vz / vz_range) * rect.h / 2)
    return max(rect.y, min(rect.y + rect.h, y))


def topdown_point(x: float, z: float, rect: Rect, x_m: float, z_m: float) -> tuple[int, int]:
    px = round(rect.x + rect.w / 2 - (x / x_m) * rect.w / 2)
    py = round(rect.y + rect.h - (z / z_m) * rect.h)
    return (max(rect.x, min(rect.x + rect.w, px)), max(rect.y, min(rect.y + rect.h, py)))


def overlay_rects(width: int, height: int, cfg, line_h: int) -> tuple[Rect, dict[int, Rect], Rect]:
    """Header, per-shown-slot player panels and the top-down map, in screen pixels."""
    render_cfg = cfg["render"]
    oc = render_cfg["debug_overlay"]
    margin = render_cfg["margin_px"]
    pad = oc["pad_px"]
    header = Rect(0, 0, oc["panel_w_px"], line_h + 2 * pad)
    top = header.h + margin
    panel_h = 2 * line_h + oc["graph_h_px"] + line_h + 4 * pad
    panels = {
        half.shows_slot: Rect(half.half.x + margin, top, oc["panel_w_px"], panel_h)
        for half in compute_layout(width, height, render_cfg)
    }
    side = oc["map_px"]
    map_top = top + panel_h + margin
    return header, panels, Rect((width - side) // 2, map_top, side, side)


class DebugOverlay:
    """Draws the F1 overlay. Build after pygame.init()."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.render_cfg = cfg["render"]
        self.oc = self.render_cfg["debug_overlay"]
        self.margin = self.render_cfg["margin_px"]
        self.pad = self.oc["pad_px"]
        self.dot_radius = self.oc["dot_radius_px"]
        self.push_speed = cfg["perception"]["push_speed_mps"]
        self.zones = cfg["perception"]["zones"]
        self.font = pygame.font.Font(None, self.oc["font_px"])
        self.line_h = self.font.get_linesize()
        self.histories = {0: SlotHistory(self.oc["graph_s"]), 1: SlotHistory(self.oc["graph_s"])}

    def draw(
        self,
        surface: pygame.Surface,
        states: Mapping[int, PlayerState],
        fps: float,
        dropped: int,
        now: float | None = None,
    ) -> None:
        now = time.monotonic() if now is None else now
        for slot, state in states.items():
            self.histories[slot].add(state)
        cam_fps = max(camera_fps(h.frames) for h in self.histories.values())
        header = f"render {fps:.0f} fps | camera {cam_fps:.1f} fps | dropped {dropped}"
        self._text_panel(surface, header, (0, 0))
        _, panels, map_rect = overlay_rects(
            surface.get_width(), surface.get_height(), self.cfg, self.line_h
        )
        for slot, rect in panels.items():
            self._draw_player_panel(surface, rect, slot, states.get(slot), now)
        self._draw_map(surface, map_rect, states)

    def _text_panel(self, surface, text: str, pos: tuple[int, int]) -> pygame.Rect:
        img = self.font.render(text, True, self.oc["text_rgb"])
        rect = pygame.Rect(pos, (img.get_width() + 2 * self.pad, img.get_height() + 2 * self.pad))
        self._fill_translucent(surface, rect)
        surface.blit(img, (rect.x + self.pad, rect.y + self.pad))
        return rect

    def _fill_translucent(self, surface, rect: pygame.Rect) -> None:
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill(self.oc["panel_rgba"])
        surface.blit(panel, rect.topleft)

    def _draw_player_panel(
        self, surface, at: Rect, slot: int, state: PlayerState | None, now: float
    ) -> None:
        oc = self.oc
        graph_h = oc["graph_h_px"]
        panel = pygame.Rect(at.as_tuple())
        self._fill_translucent(surface, panel)
        text_rgb = oc["text_rgb"]
        x, y = panel.x + self.pad, panel.y + self.pad
        if state is None:
            line1, line2 = f"P{slot + 1}  not seen", ""
        else:
            status = "TRACKED" if state.tracking_ok else "LOST"
            line1 = f"P{slot + 1}  id {state.player_id}  {status}"
            line2 = f"{state.root[2]:.2f} m  {state.zone}  {' '.join(sorted(state.pose_flags))}"
        surface.blit(self.font.render(line1, True, oc["slot_rgb"][slot]), (x, y))
        surface.blit(self.font.render(line2, True, text_rgb), (x, y + self.line_h))
        graph = Rect(x, y + 2 * self.line_h + self.pad, at.w - 2 * self.pad, graph_h)
        pygame.draw.rect(surface, text_rgb, graph.as_tuple(), 1)
        self._draw_graph(surface, graph, self.histories[slot], slot)
        hist = self.histories[slot]
        if hist.last_push is not None and now - hist.last_push_t < oc["push_flash_s"]:
            flash = f"PUSH {hist.last_push.hand} {hist.last_push.speed:.1f} m/s"
            surface.blit(
                self.font.render(flash, True, oc["threshold_rgb"]),
                (x, graph.y + graph.h + self.pad),
            )

    def _draw_graph(self, surface, graph: Rect, hist: SlotHistory, slot: int) -> None:
        oc = self.oc
        rng = oc["vz_range_mps"]
        ty = vz_to_y(-self.push_speed, graph, rng)
        pygame.draw.line(surface, oc["threshold_rgb"], (graph.x, ty), (graph.x + graph.w, ty))
        if len(hist.samples) < 2:
            return
        newest = hist.samples[-1][0]
        for idx, rgb in ((2, oc["slot_rgb"][slot]), (1, oc["text_rgb"])):
            pts = [
                (
                    round(graph.x + graph.w - (newest - s[0]) / oc["graph_s"] * graph.w),
                    vz_to_y(s[idx], graph, rng),
                )
                for s in hist.samples
            ]
            surface.set_clip(graph.as_tuple())
            pygame.draw.lines(surface, rgb, False, pts, 2)
            surface.set_clip(None)

    def _draw_map(self, surface, rect: Rect, states: Mapping[int, PlayerState]) -> None:
        oc = self.oc
        z_m, x_m = oc["topdown_z_m"], oc["topdown_x_m"]
        edges = (0.0, self.zones["danger_max_m"], self.zones["far_min_m"], z_m)
        for name, lo, hi in zip(("danger", "neutral", "far"), edges, edges[1:], strict=False):
            y_lo = topdown_point(0.0, lo, rect, x_m, z_m)[1]
            y_hi = topdown_point(0.0, hi, rect, x_m, z_m)[1]
            pygame.draw.rect(surface, oc["zone_rgb"][name], (rect.x, y_hi, rect.w, y_lo - y_hi))
        pygame.draw.rect(surface, oc["text_rgb"], rect.as_tuple(), 1)
        for slot, state in states.items():
            if not state.tracking_ok:
                continue
            pos = topdown_point(state.root[0], state.root[2], rect, x_m, z_m)
            pygame.draw.circle(surface, oc["slot_rgb"][slot], pos, self.dot_radius)
            label = self.font.render(f"P{slot + 1}", True, oc["text_rgb"])
            surface.blit(label, (pos[0] + self.dot_radius + 2, pos[1] - label.get_height() // 2))
