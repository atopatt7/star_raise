"""
ui_manager.py — Star Raise (v5+: UI Manager)

Centralises ALL HUD / overlay rendering that was previously scattered
across a dozen top-level functions in main.py.

Usage (in GameLoop.__init__)
-----------------------------
    from src.ui_manager import UIManager
    self.ui = UIManager(SCREEN_W, SCREEN_H)

Usage (in GameLoop.run — draw phase)
--------------------------------------
    snap = self.ui.make_snapshot(self)          # build a read-only snapshot
    self.ui.draw_all(self.screen, snap)         # render every HUD layer

Design goals
-------------
1. Zero game-logic — UIManager only READS game state via UISnapshot.
2. Asset-free placeholder art — colour blocks + emoji-rendered text until
   real PNG assets arrive; swap in by overriding _draw_card_art().
3. Single draw_all() entry point keeps main.py's render section to ~5 lines.
4. Each sub-draw method is public so individual panels can be called
   selectively (useful for debugging or future split-screen).

Layer order (back → front)
---------------------------
    draw_background()       world grid + lane guides    (scrolling layer)
    draw_building_slots()   empty slot placeholders     (scrolling layer)
    draw_top_hud()          resource bar + timer        (fixed HUD)
    draw_minimap()          7:1 tactical minimap        (fixed HUD)
    draw_ghost()            build placement ghost       (fixed HUD, conditional)
    draw_nuke_ghost()       nuke targeting cursor       (fixed HUD, conditional)
    draw_bottom_controls()  card row + demolish + nuke  (fixed HUD)
    draw_floating_notifs()  "礦石不足" fly-up text      (fixed HUD)
    draw_result_overlay()   victory / defeat banner     (overlay, conditional)
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    # Avoid circular import; only used for type hints
    from src.logic import ResourceManager, BuildState, GameState
    from src.sprite import Building, Unit

# ── Colour palette (single source of truth) ───────────────────────────────────
C = {
    "bg":           (18,  22,  36),
    "grid":         (28,  34,  50),
    "lane_div":     (40,  60, 100),
    "zone_div":     (80,  50, 140),
    "top_lane":     (80, 160, 255),
    "bot_lane":    (255, 160,  60),
    "text":        (200, 220, 255),
    "gold":        (255, 200,  30),
    "warn":        (255,  80,  80),
    "ok":          ( 80, 220, 120),
    "victory":     ( 60, 220, 100),
    "defeat":      (220,  60,  60),
    "hud_bg":       (20,  28,  50),
    "hud_border":   (50,  70, 110),
    "slot_fill":    (40,  80, 140,  60),   # SRCALPHA
    "slot_edge":   (100, 160, 220),
    "card_bg":      (25,  40,  60),
    "card_active":  (40,  70,  50),
    "card_border": (100, 160, 220),
    "card_active_border": (80, 220, 120),
    "demolish_bg":  (60,  20,  20),
    "demolish_on": (160,  30,  30),
    "demolish_border": (120, 60, 60),
    "demolish_border_on": (255, 80, 80),
    "nuke_bg":      (50,  12,  12),
    "nuke_active": (120,  20,  20),
}

# Card tier colours (T1 / T2 / T3)
TIER_COLORS = {
    1: (138, 138, 138),
    2: ( 74, 158, 255),
    3: (180,  90, 255),
}

# ── Floating notification ─────────────────────────────────────────────────────

@dataclass
class FloatingNotif:
    """A single fly-up warning text (e.g. 礦石不足)."""
    text: str
    x: float
    y: float
    life: int = 90          # frames remaining
    total: int = 90
    color: tuple = (255, 80, 80)

    def update(self) -> bool:
        """Advance one frame. Returns False when expired."""
        self.y -= 0.5
        self.life -= 1
        return self.life > 0

    @property
    def alpha(self) -> int:
        return int(255 * self.life / self.total)


# ── Read-only game state snapshot ─────────────────────────────────────────────

@dataclass
class UISnapshot:
    """
    Immutable view of all game state needed by UIManager.
    Created each frame via UIManager.make_snapshot(game_loop).
    UIManager never writes back to game state.
    """
    # Economy
    minerals: int = 0
    income_per_cycle: int = 0
    income_bonus: int = 0
    cycle_progress: float = 0.0
    frames_to_next_cycle: int = 300
    income_flash: bool = False
    nuke_available: bool = True

    # Timer
    frame: int = 0
    game_timer_seconds: int = 0   # elapsed seconds

    # Build state
    build_state_name: str = "NONE"   # BuildState.name
    ghost_kind: Optional[str] = None
    ghost_pos: tuple = (0, 0)
    ghost_slot: Optional[int] = None
    ghost_valid: bool = False

    # Game result
    game_state_name: str = "PLAYING"  # GameState.name

    # Camera
    cam_x: float = 0.0
    fps: float = 60.0

    # Misc
    debug_mode: bool = False

    # Collections (shallow refs — UIManager reads only)
    slot_buildings: list = field(default_factory=list)
    units: list = field(default_factory=list)
    all_buildings: list = field(default_factory=list)
    occupied_slots: set = field(default_factory=set)


# ── UIManager ─────────────────────────────────────────────────────────────────

class UIManager:
    """
    Owns all HUD rendering.  Game logic lives exclusively in GameLoop.

    Parameters
    ----------
    screen_w, screen_h : int
        Logical screen dimensions (1280 × 590 by default).
    slot_size : int
        Pixel size of one building slot square (64 px default).
    card_w, card_h : int
        Pixel dimensions of bottom build cards.

    Public entry points
    -------------------
    make_snapshot(game_loop)  → UISnapshot
    draw_all(screen, snap)    → None
    push_notif(text, x, y)    → None    (call from game logic on events)
    update()                  → None    (advance notif timers; call every frame)
    """

    # ── Card layout constants ──────────────────────────────────────────────
    CARD_W  = 90
    CARD_H  = 58
    CARD_MARGIN = 8

    # Card kinds: first two are buildings, then nuke, then demolish
    CARD_KINDS: list[Optional[str]] = ["barracks", "refinery", "nuke", None]

    def __init__(
        self,
        screen_w: int = 1280,
        screen_h: int = 590,
        slot_size: int = 64,
        world_w: int = 8960,
    ) -> None:
        self.sw = screen_w
        self.sh = screen_h
        self.slot_size = slot_size
        self.world_w = world_w

        # Font cache — created lazily so __init__ doesn't require pygame.init()
        self._fonts: dict[int, pygame.font.Font] = {}

        # Floating notifications queue
        self._notifs: list[FloatingNotif] = []

        # Pre-built reusable surfaces
        self._slot_surf: Optional[pygame.Surface] = None
        self._card_rects: Optional[list[pygame.Rect]] = None

        # Ghost placeholder surfaces keyed by kind
        self._ghost_surfs: dict[str, pygame.Surface] = {}

    # ── Font helpers ──────────────────────────────────────────────────────────

    def _font(self, size: int) -> pygame.font.Font:
        if size not in self._fonts:
            self._fonts[size] = pygame.font.Font(None, size)
        return self._fonts[size]

    def _txt(
        self,
        screen: pygame.Surface,
        text: str,
        pos: tuple[int, int],
        size: int = 18,
        color: tuple = (200, 220, 255),
        bold: bool = False,
    ) -> None:
        f = self._font(size)
        surf = f.render(text, True, color)
        screen.blit(surf, pos)

    # ── Lazy surfaces ─────────────────────────────────────────────────────────

    def _get_slot_surf(self) -> pygame.Surface:
        if self._slot_surf is None:
            s = pygame.Surface((self.slot_size, self.slot_size), pygame.SRCALPHA)
            s.fill(C["slot_fill"])
            self._slot_surf = s
        return self._slot_surf

    def _get_ghost_surf(self, kind: str) -> pygame.Surface:
        if kind not in self._ghost_surfs:
            s = pygame.Surface((self.slot_size, self.slot_size), pygame.SRCALPHA)
            color = (
                (100, 180, 255, 120) if kind == "barracks"
                else (255, 160,  60, 120)
            )
            s.fill(color)
            self._ghost_surfs[kind] = s
        return self._ghost_surfs[kind]

    def _get_card_rects(self) -> list[pygame.Rect]:
        if self._card_rects is None:
            cw, ch, m = self.CARD_W, self.CARD_H, self.CARD_MARGIN
            cy = self.sh - ch - 8
            rects = [
                pygame.Rect(10 + i * (cw + m), cy, cw, ch)
                for i in range(2)            # [0] barracks  [1] refinery
            ]
            rects.append(pygame.Rect(        # [2] nuke — second from right
                self.sw - (cw + m) * 2 - 10, cy, cw, ch
            ))
            rects.append(pygame.Rect(        # [3] demolish — far right
                self.sw - cw - 10, cy, cw, ch
            ))
            self._card_rects = rects
        return self._card_rects

    # ── Snapshot factory ──────────────────────────────────────────────────────

    @staticmethod
    def make_snapshot(gl) -> UISnapshot:
        """
        Read game state from a GameLoop instance and return a UISnapshot.
        'gl' is typed as Any to avoid importing GameLoop (circular dep).
        """
        elapsed = gl.frame // 60
        return UISnapshot(
            minerals          = gl.res.minerals,
            income_per_cycle  = gl.res.income_per_cycle,
            income_bonus      = gl.res.income_bonus,
            cycle_progress    = gl.res.cycle_progress,
            frames_to_next_cycle = gl.res.frames_to_next_cycle,
            income_flash      = bool(gl.income_flash),
            nuke_available    = gl.res.nuke_available,
            frame             = gl.frame,
            game_timer_seconds= elapsed,
            build_state_name  = gl.build_state.name,
            ghost_kind        = gl.ghost_kind,
            ghost_pos         = gl.ghost_pos,
            ghost_slot        = gl.ghost_slot,
            ghost_valid       = gl.ghost_valid,
            game_state_name   = gl.game_state.name,
            cam_x             = gl.camera.cam_x,
            fps               = gl.fps_clk.get_fps(),
            debug_mode        = gl.debug_mode,
            slot_buildings    = gl.slot_buildings,
            units             = gl.units,
            all_buildings     = gl.all_buildings,
            occupied_slots    = gl._UIManager__occupied_slots
                                if hasattr(gl, '_UIManager__occupied_slots')
                                else gl._occupied_slots,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self) -> None:
        """Advance animation timers. Call once per frame before draw_all()."""
        self._notifs = [n for n in self._notifs if n.update()]

    def push_notif(
        self,
        text: str,
        x: Optional[float] = None,
        y: Optional[float] = None,
        color: tuple = (255, 80, 80),
    ) -> None:
        """
        Spawn a floating fly-up notification.
        Defaults to screen centre if x/y not given.
        """
        nx = x if x is not None else self.sw // 2
        ny = y if y is not None else self.sh // 2
        self._notifs.append(FloatingNotif(text, nx, ny, color=color))

    def draw_all(self, screen: pygame.Surface, snap: UISnapshot) -> None:
        """
        Master render call.  Draws every HUD layer in correct order.
        Call once per frame after the game world (sprites, VFX) is drawn.
        """
        # ── Scrolling world layer ────────────────────────────────────────
        self.draw_background(screen, snap.cam_x)

        # ── Fixed HUD layers ─────────────────────────────────────────────
        self.draw_top_hud(screen, snap)
        self.draw_minimap(screen, snap)

        # Ghost (only when placing / nuking)
        if snap.build_state_name == "CONSTRUCTING":
            self.draw_ghost(screen, snap)
        elif snap.build_state_name == "NUKING":
            self.draw_nuke_ghost(screen, snap.ghost_pos)

        self.draw_bottom_controls(screen, snap)
        self.draw_floating_notifs(screen)

        if snap.debug_mode:
            self.draw_debug_strip(screen, snap)

        # ── End-game overlay (on top of everything) ───────────────────────
        if snap.game_state_name != "PLAYING":
            self.draw_result_overlay(screen, snap.game_state_name)

    # ──────────────────────────────────────────────────────────────────────────
    # BACKGROUND  (world / scrolling layer)
    # ──────────────────────────────────────────────────────────────────────────

    def draw_background(self, screen: pygame.Surface, cam_x: float) -> None:
        """Scrolling world grid, zone boundaries, lane guides."""
        screen.fill(C["bg"])

        # Vertical grid lines
        first_wx = (int(cam_x) // 64) * 64
        for wx in range(first_wx, int(cam_x) + self.sw + 64, 64):
            sx = wx - int(cam_x)
            pygame.draw.line(screen, C["grid"], (sx, 0), (sx, self.sh))

        # Horizontal grid lines
        for y in range(0, self.sh, 64):
            pygame.draw.line(screen, C["grid"], (0, y), (self.sw, y))

        # Zone boundary lines (player | neutral | enemy)
        for bwx in (self.sw, self.world_w - self.sw):
            bsx = bwx - int(cam_x)
            if -2 <= bsx <= self.sw + 2:
                pygame.draw.line(screen, C["zone_div"], (bsx, 0), (bsx, self.sh), 2)

        # Horizontal lane divider
        pygame.draw.line(
            screen, C["lane_div"],
            (0, self.sh // 2), (self.sw, self.sh // 2), 1
        )

        # Lane Y guides (dashed horizontal lines)
        top_y = self.sh // 4
        bot_y = 3 * self.sh // 4
        for lane_y, col in ((top_y, C["top_lane"]), (bot_y, C["bot_lane"])):
            self._dashed_hline(screen, col, 0, self.sw, lane_y)

    def draw_building_slots(
        self,
        screen: pygame.Surface,
        cam_x: float,
        all_slots: list[tuple[int, int]],
        occupied: set[int],
    ) -> None:
        """
        Draw empty slot placeholders (occupied slots skip — building sprite
        handles its own rendering).

        Call this BEFORE drawing sprite groups so buildings render on top.
        """
        slot_surf = self._get_slot_surf()
        ss = self.slot_size
        for idx, (wx, wy) in enumerate(all_slots):
            if idx in occupied:
                continue
            sx = wx - int(cam_x)
            if sx + ss < 0 or sx > self.sw:
                continue
            screen.blit(slot_surf, (sx, wy))
            lane_color = C["top_lane"] if idx < 16 else C["bot_lane"]
            self._dashed_rect(screen, lane_color, sx, wy, ss, ss)

    # ──────────────────────────────────────────────────────────────────────────
    # TOP HUD  (resource bar)
    # ──────────────────────────────────────────────────────────────────────────

    def draw_top_hud(self, screen: pygame.Surface, snap: UISnapshot) -> None:
        """
        Fixed top bar: [timer] [ore] [income breakdown] [cycle bar] [pause]
        Height: 28 px (info strip) + 10 px (hint) = 38 px total.
        """
        # Background strip
        pygame.draw.rect(screen, C["hud_bg"], (0, 0, self.sw, 28))
        pygame.draw.rect(screen, C["hud_border"], (0, 0, self.sw, 28), 1)

        # Timer (left)
        m = snap.game_timer_seconds // 60
        s = snap.game_timer_seconds % 60
        timer_str = f"{m:02d}:{s:02d}"
        self._txt(screen, timer_str, (8, 7), size=20,
                  color=(80, 220, 255) if snap.game_timer_seconds % 2 == 0 else (60, 180, 220))

        # Minerals (centre-left)
        ore_col = C["gold"] if snap.income_flash else (200, 180, 80)
        self._txt(screen, f"⛏ {snap.minerals}", (90, 7), size=18, color=ore_col)

        # Income breakdown
        alive = [b for b in snap.slot_buildings if not b.is_dead]
        bar_n  = sum(1 for b in alive if b.kind == "barracks")
        ref_n  = sum(1 for b in alive if b.kind == "refinery")
        parts  = [f"Base 10"]
        if bar_n: parts.append(f"{bar_n}×Bar(+{bar_n*5})")
        if ref_n: parts.append(f"{ref_n}×Ref(+{ref_n*10})")
        parts.append(f"= {snap.income_per_cycle}/5s")
        income_str = "  ".join(parts)
        self._txt(screen, income_str, (230, 7), size=16, color=(160, 200, 255))

        # Income cycle progress bar (right side)
        bar_x, bar_y, bar_w, bar_h = self.sw - 180, 8, 170, 10
        pygame.draw.rect(screen, (40, 40, 70), (bar_x, bar_y, bar_w, bar_h))
        fill_w = int(bar_w * snap.cycle_progress)
        # Flash gold when cycle fires
        bar_col = (255, 220, 50) if snap.income_flash else C["gold"]
        if fill_w > 0:
            pygame.draw.rect(screen, bar_col, (bar_x, bar_y, fill_w, bar_h))
        pygame.draw.rect(screen, (120, 100, 40), (bar_x, bar_y, bar_w, bar_h), 1)
        self._txt(screen, f"{snap.frames_to_next_cycle}f",
                  (bar_x - 36, bar_y - 1), size=14, color=(180, 160, 80))

        # Hint strip (row 2)
        hint = (
            f"FPS:{snap.fps:.0f}  CAM:{snap.cam_x:.0f}/{self.world_w - self.sw}  "
            "Drag=scroll  D=demolish  RMB/ESC=cancel  F1=debug  R=reset  ESC=quit"
        )
        self._txt(screen, hint, (8, 32), size=16, color=(255, 200, 60))

    # ──────────────────────────────────────────────────────────────────────────
    # MINIMAP
    # ──────────────────────────────────────────────────────────────────────────

    def draw_minimap(self, screen: pygame.Surface, snap: UISnapshot) -> None:
        """
        7:1 tactical minimap — top-right corner.
        Blue = player units/buildings, red = enemy.
        Viewport box shows current camera window.
        """
        MAP_W, MAP_H = 200, 30
        MAP_X = self.sw - MAP_W - 8
        MAP_Y = 42

        # Background
        pygame.draw.rect(screen, (10, 18, 40), (MAP_X, MAP_Y, MAP_W, MAP_H))
        pygame.draw.rect(screen, (50, 80, 140), (MAP_X, MAP_Y, MAP_W, MAP_H), 1)

        # Label
        self._txt(screen, "MINIMAP", (MAP_X, MAP_Y - 13), size=14, color=(80, 120, 180))

        # Scale factor: world_w → MAP_W
        sx_scale = MAP_W / self.world_w
        sy_scale = MAP_H / self.sh

        # Draw building dots
        for b in snap.all_buildings:
            if b.is_dead:
                continue
            dx = MAP_X + int(b.pos[0] * sx_scale)
            dy = MAP_Y + int(b.pos[1] * sy_scale)
            col = (80, 160, 255) if b.team == 0 else (255, 80, 80)
            radius = 3 if b.is_hq else 2
            pygame.draw.circle(screen, col, (dx, dy), radius)

        # Draw unit dots
        for u in snap.units:
            if u.is_dead:
                continue
            dx = MAP_X + int(u.pos[0] * sx_scale)
            dy = MAP_Y + int(u.pos[1] * sy_scale)
            col = (100, 220, 255) if u.team == 0 else (255, 140, 80)
            pygame.draw.circle(screen, col, (dx, dy), 1)

        # Viewport box
        vp_x = MAP_X + int(snap.cam_x * sx_scale)
        vp_w = int(self.sw * sx_scale)
        pygame.draw.rect(screen, (0, 220, 200), (vp_x, MAP_Y, vp_w, MAP_H), 1)

    # ──────────────────────────────────────────────────────────────────────────
    # GHOST  (build placement preview)
    # ──────────────────────────────────────────────────────────────────────────

    def draw_ghost(
        self,
        screen: pygame.Surface,
        snap: UISnapshot,
        all_slots: Optional[list[tuple[int, int]]] = None,
    ) -> None:
        """
        Ghost building sprite following cursor + slot highlight.
        all_slots must be passed if snap.ghost_slot index is to be shown.
        """
        if snap.ghost_kind is None:
            return

        gx, gy = snap.ghost_pos
        ss = self.slot_size

        # Slot highlight at snap position
        if snap.ghost_slot is not None and all_slots is not None:
            wx, wy = all_slots[snap.ghost_slot]
            sx = wx - int(snap.cam_x)
            col = (0, 220, 80, 90) if snap.ghost_valid else (220, 50, 50, 90)
            hi = pygame.Surface((ss, ss), pygame.SRCALPHA)
            hi.fill(col)
            screen.blit(hi, (sx, wy))
            border_col = (0, 255, 100) if snap.ghost_valid else (255, 60, 60)
            pygame.draw.rect(screen, border_col, (sx, wy, ss, ss), 2)
            label = "Place" if snap.ghost_valid else "Occupied"
            self._txt(screen, label, (sx + 2, wy - 14), size=16, color=border_col)

        # Ghost sprite (50 % alpha placeholder)
        ghost_surf = self._get_ghost_surf(snap.ghost_kind)
        alpha_surf = ghost_surf.copy()
        alpha_surf.set_alpha(160)
        rect = alpha_surf.get_rect(center=(gx, gy))
        screen.blit(alpha_surf, rect)

    def draw_nuke_ghost(
        self,
        screen: pygame.Surface,
        ghost_pos: tuple[int, int],
    ) -> None:
        """Nuke targeting crosshair + AoE circle."""
        gx, gy = ghost_pos
        aoe = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        pygame.draw.circle(aoe, (220, 30, 30,  45), (gx, gy), 450)
        pygame.draw.circle(aoe, (255, 80, 60, 180), (gx, gy), 450, 2)
        screen.blit(aoe, (0, 0))

        for dx, dy in ((-24, 0), (24, 0), (0, -24), (0, 24)):
            pygame.draw.line(screen, (255, 60, 60), (gx, gy), (gx+dx, gy+dy), 2)
        pygame.draw.circle(screen, (255, 100, 80), (gx, gy), 9, 2)

        self._txt(screen, "☢ NUKE — click to detonate",
                  (gx + 14, gy - 18), size=16, color=(255, 80, 80))

    # ──────────────────────────────────────────────────────────────────────────
    # BOTTOM CONTROLS  (card row + demolish + nuke)
    # ──────────────────────────────────────────────────────────────────────────

    def draw_bottom_controls(self, screen: pygame.Surface, snap: UISnapshot) -> None:
        """
        Fixed bottom bar containing:
        [Barracks] [Refinery]  …  [Nuke] [Demolish]
        """
        # Semi-transparent backing strip
        bar_h = self.CARD_H + 16
        bar_surf = pygame.Surface((self.sw, bar_h), pygame.SRCALPHA)
        bar_surf.fill((10, 16, 30, 200))
        screen.blit(bar_surf, (0, self.sh - bar_h))
        pygame.draw.line(screen, C["hud_border"],
                         (0, self.sh - bar_h), (self.sw, self.sh - bar_h), 1)

        from src.logic import BuildState  # local import avoids circular dep
        card_rects = self._get_card_rects()

        for i, rect in enumerate(card_rects):
            kind = self.CARD_KINDS[i]
            is_demolish = (kind is None)
            is_nuke     = (kind == "nuke")

            if is_demolish:
                self._draw_demolish_card(screen, rect, snap)
            elif is_nuke:
                self._draw_nuke_card(screen, rect, snap)
            else:
                self._draw_build_card(screen, rect, kind, snap)

    def _draw_demolish_card(
        self, screen: pygame.Surface, rect: pygame.Rect, snap: UISnapshot
    ) -> None:
        active = (snap.build_state_name == "DEMOLISHING")
        bg     = C["demolish_on"] if active else C["demolish_bg"]
        border = C["demolish_border_on"] if active else C["demolish_border"]
        pygame.draw.rect(screen, bg, rect)
        pygame.draw.rect(screen, border, rect, 2)
        label_col = (255, 100, 100) if active else (200, 120, 120)
        self._txt(screen, "DEMOLISH", (rect.x + 6, rect.y + 8),  size=16, color=label_col)
        self._txt(screen, "[D key]",  (rect.x + 6, rect.y + 26), size=14, color=(160, 80, 80))
        self._txt(screen, "60% refund",(rect.x + 6, rect.y + 42),size=13, color=(120, 60, 60))

    def _draw_nuke_card(
        self, screen: pygame.Surface, rect: pygame.Rect, snap: UISnapshot
    ) -> None:
        active = (snap.build_state_name == "NUKING")
        avail  = snap.nuke_available
        bg     = C["nuke_active"] if active else C["nuke_bg"]
        border = (255, 60, 60) if active else ((200, 80, 80) if avail else (50, 40, 40))
        pygame.draw.rect(screen, bg, rect)
        pygame.draw.rect(screen, border, rect, 2)
        label_col = (255, 100, 80)  if avail else (80,  60, 60)
        hint_col  = (255,  60, 60)  if avail else (80,  70, 70)
        note_col  = (160, 100, 100) if avail else (60,  50, 50)
        self._txt(screen, "☢ NUKE",         (rect.x + 6, rect.y + 8),  size=16, color=label_col)
        self._txt(screen, "ARMED" if avail else "EXPENDED",
                                              (rect.x + 6, rect.y + 26), size=14, color=hint_col)
        self._txt(screen, "450px AoE",       (rect.x + 6, rect.y + 42), size=13, color=note_col)

    def _draw_build_card(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        kind: str,
        snap: UISnapshot,
    ) -> None:
        from src.logic import BUILDING_SPECS
        spec       = BUILDING_SPECS.get(kind, {})
        cost       = spec.get("cost", 0)
        unit_type  = spec.get("unit_type", "?")
        spawn_rate = spec.get("spawn_rate_frames", 480) // 60
        income_b   = spec.get("income_bonus", 0)

        active     = (snap.ghost_kind == kind and snap.build_state_name == "CONSTRUCTING")
        affordable = (snap.minerals >= cost)

        bg     = C["card_active"] if (active and affordable) else C["card_bg"]
        border = C["card_active_border"] if active else (
            C["card_border"] if affordable else (80, 60, 60)
        )
        pygame.draw.rect(screen, bg, rect)
        pygame.draw.rect(screen, border, rect, 2)

        label_col = (200, 230, 200) if affordable else (120, 100, 100)
        cost_col  = C["gold"]       if affordable else (200, 120,  60)
        self._txt(screen, kind.upper(),          (rect.x + 6, rect.y + 8),  size=16, color=label_col)
        self._txt(screen, f"{cost} min",         (rect.x + 6, rect.y + 26), size=14, color=cost_col)
        self._txt(screen, f"→{unit_type} {spawn_rate}s  +{income_b}/c",
                                                 (rect.x + 6, rect.y + 42), size=12, color=(120, 160, 200))

        # Colour block art (placeholder — replace with sprite blit later)
        art_col = (80, 140, 220) if kind == "barracks" else (220, 130, 60)
        art_rect = pygame.Rect(rect.right - 28, rect.y + 6, 22, 22)
        pygame.draw.rect(screen, art_col, art_rect, border_radius=4)
        icon = "⚔" if kind == "barracks" else "⛽"
        self._txt(screen, icon, (art_rect.x + 3, art_rect.y + 3), size=14,
                  color=(220, 240, 255))

    # ──────────────────────────────────────────────────────────────────────────
    # FLOATING NOTIFICATIONS
    # ──────────────────────────────────────────────────────────────────────────

    def draw_floating_notifs(self, screen: pygame.Surface) -> None:
        for n in self._notifs:
            surf = self._font(20).render(n.text, True, n.color)
            surf.set_alpha(n.alpha)
            screen.blit(surf, (int(n.x) - surf.get_width() // 2, int(n.y)))

    # ──────────────────────────────────────────────────────────────────────────
    # RESULT OVERLAY
    # ──────────────────────────────────────────────────────────────────────────

    def draw_result_overlay(
        self, screen: pygame.Surface, game_state_name: str
    ) -> None:
        """Victory / Defeat full-screen overlay."""
        is_win = (game_state_name == "VICTORY")

        # Dim + tint
        overlay = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        overlay.fill((10, 60, 10, 210) if is_win else (60, 10, 10, 210))
        screen.blit(overlay, (0, 0))

        # Banner strip
        bh = 110
        banner = pygame.Surface((self.sw, bh), pygame.SRCALPHA)
        banner.fill((30, 160, 30, 230) if is_win else (160, 30, 30, 230))
        screen.blit(banner, (0, self.sh // 2 - bh // 2 - 10))

        # Headline
        color    = C["victory"] if is_win else C["defeat"]
        headline = "★  VICTORY  ★" if is_win else "✖  DEFEAT  ✖"
        font_xl  = self._font(110)
        s_head   = font_xl.render(headline, True, color)
        screen.blit(s_head, s_head.get_rect(center=(self.sw // 2, self.sh // 2 + 2)))

        sub     = "Enemy HQ destroyed!" if is_win else "Your HQ has fallen!"
        sub_col = (230, 255, 230)       if is_win else (255, 230, 230)
        s_sub   = self._font(36).render(sub, True, sub_col)
        screen.blit(s_sub, s_sub.get_rect(center=(self.sw // 2, self.sh // 2 + 62)))

        hint    = "[ R to Restart ]  [ ESC to Quit ]"
        hint_col= (180, 220, 180) if is_win else (220, 180, 180)
        s_hint  = self._font(24).render(hint, True, hint_col)
        screen.blit(s_hint, s_hint.get_rect(center=(self.sw // 2, self.sh // 2 + 100)))

    # ──────────────────────────────────────────────────────────────────────────
    # DEBUG STRIP
    # ──────────────────────────────────────────────────────────────────────────

    def draw_debug_strip(self, screen: pygame.Surface, snap: UISnapshot) -> None:
        """Extra debug info row below the hint strip (F1 toggle)."""
        alive_units = [u for u in snap.units if not u.is_dead]
        p_units = sum(1 for u in alive_units if u.team == 0)
        e_units = sum(1 for u in alive_units if u.team == 1)
        msg = (
            f"[DEBUG]  units P:{p_units} E:{e_units}  "
            f"buildings:{len(snap.slot_buildings)}  "
            f"build_state:{snap.build_state_name}  "
            f"ghost_slot:{snap.ghost_slot}  "
            f"nuke:{snap.nuke_available}"
        )
        self._txt(screen, msg, (8, 50), size=14, color=(200, 255, 200))

    # ──────────────────────────────────────────────────────────────────────────
    # CARD HIT-TEST  (used by GameLoop for mouse events)
    # ──────────────────────────────────────────────────────────────────────────

    def card_at(self, mx: int, my: int) -> Optional[tuple[int, Optional[str]]]:
        """
        Returns (card_index, kind) if (mx, my) falls inside a card rect.
        kind is None for the demolish button.
        Returns None if no card was hit.
        """
        for i, rect in enumerate(self._get_card_rects()):
            if rect.collidepoint(mx, my):
                return (i, self.CARD_KINDS[i])
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # DASHED LINE HELPERS  (private)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _dashed_hline(
        surf: pygame.Surface,
        color: tuple,
        x1: int, x2: int, y: int,
        dash: int = 8, gap: int = 4,
    ) -> None:
        pos = x1
        while pos < x2:
            end = min(pos + dash, x2)
            pygame.draw.line(surf, color, (pos, y), (end, y))
            pos += dash + gap

    @staticmethod
    def _dashed_vline(
        surf: pygame.Surface,
        color: tuple,
        x: int, y1: int, y2: int,
        dash: int = 8, gap: int = 4,
    ) -> None:
        pos = y1
        while pos < y2:
            end = min(pos + dash, y2)
            pygame.draw.line(surf, color, (x, pos), (x, end))
            pos += dash + gap

    @classmethod
    def _dashed_rect(
        cls,
        surf: pygame.Surface,
        color: tuple,
        x: int, y: int, w: int, h: int,
    ) -> None:
        cls._dashed_hline(surf, color, x, x + w, y)
        cls._dashed_hline(surf, color, x, x + w, y + h)
        cls._dashed_vline(surf, color, x, y, y + h)
        cls._dashed_vline(surf, color, x + w, y, y + h)
