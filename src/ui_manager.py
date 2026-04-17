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
import os
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
    "gold":        (255, 180,  50),   # amber/gold — warmer than old (255,200,30)
    "warn":        (255,  80,  80),
    "ok":          ( 80, 220, 120),
    "victory":     ( 60, 220, 100),
    "defeat":      (220,  60,  60),
    "hud_bg":       (20,  28,  50),
    "hud_border":   (50,  65,  85),   # muted steel
    "deck_bg":      (15,  20,  28),   # deep space dark blue
    "border_active":(  0, 210, 255),  # neon cyber-cyan
    "slot_fill":    (40,  80, 140,  60),   # SRCALPHA
    "slot_edge":   (100, 160, 220),
    "card_bg":      (28,  35,  48),   # slate blue
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

    # End-game stats (populated from GameLoop counters)
    player_kills:         int = 0
    buildings_placed:     int = 0
    total_income_earned:  int = 0

    # HQ health (for HUD bars)
    player_hq_hp:     int = 2500
    player_hq_max:    int = 2500
    enemy_hq_hp:      int = 2500
    enemy_hq_max:     int = 2500

    # Camera
    cam_x: float = 0.0
    fps: float = 60.0

    # Faction
    player_faction: str = "federation"

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

    # ── Figma v2 Palette (0-255 from JS 0-1 floats × 255) ────────────────────
    # Source: P dict in star_raise_figma_v2.js
    _FG = {
        "bg":      (  2,   4,   7),   # near-black world   panelA≈dark
        "panelA":  (  4,   9,  18),   # frosted HUD panel
        "panelB":  (  2,   5,  10),   # command deck panel
        "green":   (  0, 255, 136),   # neon green accent
        "greenD":  (  0, 107,  56),   # dim green
        "greenG":  (  0, 153,  79),   # mid green
        "cyan":    (  0, 212, 255),   # cyan accent
        "orange":  (255, 107,  43),   # enemy orange
        "red":     (255,  34,  68),   # danger red
        "gold":    (255, 204,  68),   # mineral gold
        "gray":    ( 71,  79,  97),   # neutral gray
        "midGy":   (115, 120, 130),   # mid gray
    }

    # ── Figma v2 command-deck card layout (6 build + demolish + turret + nuke) ─
    # Deck: y=999, h=180.  Build cards: 190×150, centred vertically → card_y=1014.
    # Slots [0-5] build buildings; [6] demolish toggle; [7] turret; [8] nuke.
    # Spacing: 190w + 14gap = 204 per card; first card at x=152 (SAFE+20)

    # ── Federation card layout ────────────────────────────────────────────────
    CARD_KINDS: list[Optional[str]] = [
        "barracks", "refinery", "rover_bay", "spec_ops",
        "heavy_factory", "starport", None, "turret", "nuke",
    ]
    CARD_W = 190   # standard card width (px)
    CARD_H = 172   # max card height — nuke card (px)

    _FIGMA_CARD_RECTS = [
        (152,  1014, 190, 150),   # [0] 步兵營   barracks
        (356,  1014, 190, 150),   # [1] 裝甲廠   refinery
        (560,  1014, 190, 150),   # [2] 突擊車廠  rover_bay
        (764,  1014, 190, 150),   # [3] 特戰中心  spec_ops
        (968,  1014, 190, 150),   # [4] 重型兵工廠 heavy_factory
        (1172, 1014, 190, 150),   # [5] 航空機場  starport
        (1400, 1014, 116, 150),   # [6] 安全開關  demolish toggle
        (1544, 1014, 190, 150),   # [7] 防禦砲塔  turret
        (2218, 1003, 194, 172),   # [8] 核彈     nuke (taller: h=172)
    ]

    # ── Swarm card layout (acid_pool + demolish + nuke only) ─────────────────
    SWARM_CARD_KINDS: list[Optional[str]] = [
        "acid_pool", None, "nuke",
    ]
    _SWARM_CARD_RECTS = [
        (152,  1014, 190, 150),   # [0] 酸液繁殖池  acid_pool
        (1400, 1014, 116, 150),   # [1] 安全開關   demolish toggle
        (2218, 1003, 194, 172),   # [2] 核彈      nuke
    ]

    # ── Frame 1 — 首頁 (Main Menu) button rects  [Figma v3 landscape ergonomics] ─
    # Layout: iPhone 15 Pro Max Landscape 2796×1290  (Python runs at 2556×1179).
    # Thumb-zone stack: right-aligned, right boundary = W-SAFE = 2556-132 = 2424
    # pvpX  = 2424-600 = 1824;   stackY starts at 300 → vertically centred
    # secX  = 2424-500 = 1924
    # setX  = 2424-116 = 2308;   setY = 20  (top-right corner, inside safe zone)
    #
    # Figma v3 JSON spec (2796×1290 master; scale ×0.914 for Python 2556×1179):
    # {
    #   "frame":      {"w":2796,"h":1290,"bg":"#02040B"},
    #   "pvp":        {"x":2064,"y":275,"w":600,"h":160,"fill":"#00FF88"},
    #   "one_v_one":  {"x":2164,"y":455,"w":500,"h":120,"fill":"#00D4FF"},
    #   "two_v_two":  {"x":2164,"y":595,"w":500,"h":120,"fill":"#00D4FF"},
    #   "ai_battle":  {"x":2164,"y":735,"w":500,"h":120,"fill":"#1A6BFF"},
    #   "settings":   {"x":2548,"y":20, "w":100,"h":100,"fill":"#00D4FF"},
    #   "title_cn":   {"x":192, "y":340,"text":"星核戰線","size":96},
    #   "title_en":   {"x":192, "y":460,"text":"Star Raise","size":148},
    #   "info":       {"x":152, "y":1200,"text":"Winstar  v1.0  ·  D E V","size":26}
    # }
    _BTN_PVP        = (1824, 300, 600, 160)   # primary: P V P 多人對戰
    _BTN_1V1        = (1924, 480, 500, 120)   # secondary (locked visual)
    _BTN_2V2        = (1924, 620, 500, 120)   # secondary (locked visual)
    _BTN_AI_BATTLE  = (1924, 760, 500, 120)   # AI 對戰 — interactive (blue)
    _BTN_SETTINGS   = (2308,  20, 100, 100)   # 系統設定 corner btn

    # ── Frame 3 — 結算畫面 (Result) action button rects  [Figma v2] ─────────
    # aY   = vitY(120) + 375(stats_panel_h+spacing) + 326 = 821
    # aW=420, aH=112, aGap=36, W/2=1278
    # 再戰一局 : W/2 - aW - aGap/2 = 1278 - 420 - 18 = 840
    # 返回首頁 : W/2 + aGap/2       = 1278 + 18        = 1296
    _BTN_REMATCH  = ( 840, 821, 420, 112)   # 再戰一局 Play Again
    _BTN_HOME     = (1296, 821, 420, 112)   # 返回首頁 Main Menu

    def __init__(
        self,
        screen_w: int = 2556,
        screen_h: int = 1179,
        slot_size: int = 84,
        world_w: int = 17892,
        asset_manager=None,
    ) -> None:
        self.sw = screen_w
        self.sh = screen_h
        self.slot_size = slot_size
        self.world_w = world_w
        self._assets = asset_manager   # Optional AssetManager for encyclopedia icons

        # Font cache — created lazily so __init__ doesn't require pygame.init()
        self._fonts: dict[int, pygame.font.Font] = {}

        # Floating notifications queue
        self._notifs: list[FloatingNotif] = []

        # Encyclopedia state
        self.encyclopedia_tab: str = "federation"

        # Pre-built reusable surfaces
        self._slot_surf: Optional[pygame.Surface] = None
        self._card_rects: Optional[list[pygame.Rect]] = None

        # Ghost placeholder surfaces keyed by kind
        self._ghost_surfs: dict[str, pygame.Surface] = {}

        # General-purpose cached SRCALPHA surfaces (key → Surface)
        self._cached_surfs: dict[str, pygame.Surface] = {}

        # Minimap rect — lazily initialised (see `minimap_rect` property)
        self._minimap_rect: Optional[pygame.Rect] = None

        # Hit-test rects for menu / result buttons (updated each draw call)
        self._pvp_rect:        pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._1v1_rect:        pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._2v2_rect:        pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._unit_info_rect:  pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._restart_rect:    pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._home_rect:       pygame.Rect = pygame.Rect(0, 0, 0, 0)
        # Faction select screen rects
        self._fac_fed_rect:    Optional[pygame.Rect] = None
        self._fac_start_rect:  Optional[pygame.Rect] = None
        self._fac_back_rect:   Optional[pygame.Rect] = None

        # ── Sci-fi palette shortcuts (mirrors C dict; available as self.C_* in methods) ──
        self.C_DECK_BG = C["deck_bg"]        # (15,  20,  28) deep space dark blue
        self.C_CARD_BG = C["card_bg"]        # (28,  35,  48) slate blue
        self.C_BORDER  = C["hud_border"]     # (50,  65,  85) muted steel
        self.C_ACTIVE  = C["border_active"]  # ( 0, 210, 255) neon cyber-cyan
        self.C_GOLD    = C["gold"]           # (255, 180,  50) amber/gold

    # ── Font helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _is_valid_ttf(path: str) -> bool:
        """Return True only if the file starts with a known TrueType/OpenType magic."""
        try:
            with open(path, "rb") as f:
                magic = f.read(4)
            # TrueType: 00 01 00 00 or 'true'; OpenType CFF: 'OTTO'
            return magic in (b"\x00\x01\x00\x00", b"true", b"OTTO")
        except Exception:
            return False

    def _font(self, size: int) -> pygame.font.Font:
        if size not in self._fonts:
            font_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "assets", "fonts", "NotoSansTC.ttf"
            )
            try:
                self._fonts[size] = pygame.font.Font(font_path, size)
            except Exception:
                self._fonts[size] = pygame.font.Font(None, size)
        return self._fonts[size]

    def _safe_render(
        self,
        font: pygame.font.Font,
        text: str,
        antialias: bool,
        color: tuple,
        background=None,
    ) -> pygame.Surface:
        """Render text safely — never raises even on zero-width or missing glyphs."""
        if text is None or text == "":
            text = " "
        try:
            if background:
                surf = font.render(str(text), antialias, color, background)
            else:
                surf = font.render(str(text), antialias, color)
            if surf.get_width() == 0:
                return font.render("?", antialias, color)
            return surf
        except Exception:
            try:
                return font.render("?", antialias, color)
            except Exception:
                return pygame.Surface((8, 8), pygame.SRCALPHA)

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
        surf = self._safe_render(f, text, True, color)
        screen.blit(surf, pos)

    def _txt_shd(
        self,
        screen: pygame.Surface,
        text: str,
        pos: tuple[int, int],
        size: int,
        color: tuple,
    ) -> None:
        """Render text with a 2-px dark shadow for depth (WASM-safe: 2 renders, no extra Surfaces)."""
        f = self._font(size)
        shd = self._safe_render(f, text, True, (0, 0, 0))
        screen.blit(shd, (pos[0] + 2, pos[1] + 2))
        surf = self._safe_render(f, text, True, color)
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

    def _get_surf(self, key: str, size: tuple[int, int]) -> pygame.Surface:
        """Return a cached SRCALPHA Surface of the given size.
        Always call fill() on the returned surface before drawing to clear
        content from previous frames."""
        if key not in self._cached_surfs:
            self._cached_surfs[key] = pygame.Surface(size, pygame.SRCALPHA)
        return self._cached_surfs[key]

    def _get_card_rects(self) -> list[pygame.Rect]:
        """Return hardcoded Figma v2 card rects — one per CARD_KINDS entry."""
        if self._card_rects is None:
            self._card_rects = [
                pygame.Rect(x, y, w, h)
                for x, y, w, h in self._FIGMA_CARD_RECTS
            ]
        return self._card_rects

    def get_card_layout(
        self, faction: str = "federation"
    ) -> tuple[list, list[pygame.Rect]]:
        """
        Return (kinds, rects) for the given player faction.

        Federation → 9-card layout (barracks…nuke)
        Swarm      → 3-card layout (acid_pool, demolish, nuke)

        Rects are cached per faction to avoid per-frame allocation.
        """
        if faction == "swarm":
            if not hasattr(self, "_swarm_card_rects"):
                self._swarm_card_rects = [
                    pygame.Rect(x, y, w, h) for x, y, w, h in self._SWARM_CARD_RECTS
                ]
            return self.SWARM_CARD_KINDS, self._swarm_card_rects
        else:
            return self.CARD_KINDS, self._get_card_rects()

    # ── Snapshot factory ──────────────────────────────────────────────────────

    @staticmethod
    def make_snapshot(gl) -> UISnapshot:
        """
        Read game state from a GameLoop instance and return a UISnapshot.
        'gl' is typed as Any to avoid importing GameLoop (circular dep).
        """
        elapsed = int(getattr(gl, "play_time", gl.frame / 60))
        return UISnapshot(
            minerals          = gl.res.minerals,
            income_per_cycle  = gl.res.income_per_cycle,
            income_bonus      = gl.res.income_bonus,
            cycle_progress    = gl.res.cycle_progress,
            frames_to_next_cycle = gl.res.frames_to_next_cycle,
            income_flash      = (gl.income_flash > 0),
            nuke_available    = gl.res.nuke_available,
            frame             = gl.frame,
            game_timer_seconds= elapsed,
            build_state_name  = gl.build_state.name,
            ghost_kind        = gl.ghost_kind,
            ghost_pos         = gl.ghost_pos,
            ghost_slot        = gl.ghost_slot,
            ghost_valid       = gl.ghost_valid,
            game_state_name   = gl.game_state.name,
            player_kills         = getattr(gl, "player_kills",         0),
            buildings_placed     = getattr(gl, "buildings_placed",     0),
            total_income_earned  = getattr(gl, "total_income_earned",  0),
            player_hq_hp  = getattr(gl.player_hq, "hp",     2500),
            player_hq_max = getattr(gl.player_hq, "max_hp", 2500),
            enemy_hq_hp   = getattr(gl.enemy_hq,  "hp",     2500),
            enemy_hq_max  = getattr(gl.enemy_hq,  "max_hp", 2500),
            cam_x             = gl.camera.cam_x,
            fps               = gl.fps_clk.get_fps(),
            player_faction    = getattr(gl, "player_faction", "federation"),
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

        For MAIN_MENU: draws the title screen and returns early.
        For PLAYING / VICTORY / DEFEAT: draws HUD layers on top of the
        world that main.py already rendered (background + sprites).
        NOTE: draw_background() is intentionally NOT called here — main.py
        calls it before sprite drawing to avoid overdrawing sprites.
        """
        # ── Title screen (early return) ───────────────────────────────────
        if snap.game_state_name == "MAIN_MENU":
            self.draw_main_menu(screen)
            return

        # ── Fixed HUD layers (drawn on top of world sprites) ─────────────
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
        if snap.game_state_name in ("VICTORY", "DEFEAT"):
            self.draw_result_overlay(screen, snap.game_state_name, snap=snap)

    # ──────────────────────────────────────────────────────────────────────────
    # BACKGROUND  (world / scrolling layer)
    # ──────────────────────────────────────────────────────────────────────────

    def draw_background(self, screen: pygame.Surface, cam_x: float) -> None:
        """Scrolling world grid, zone tints, HQ anchors, lane guides."""
        # ── Tiled deep-space background ───────────────────────────────────────
        # Uses the asset manager injected at construction time (self._assets).
        # Falls back to a solid colour fill if no asset manager is available.
        _bg_drawn = False
        if self._assets is not None:
            try:
                _bg = self._assets.get("background")
                _tw, _th = _bg.get_size()
                # Scroll the tile with the camera (modulo tile width) so
                # the background feels attached to the world.
                _ox = -(int(cam_x) % _tw)
                _oy = 0
                _tx = _ox
                while _tx < self.sw:
                    _ty = _oy
                    while _ty < self.sh:
                        screen.blit(_bg, (_tx, _ty))
                        _ty += _th
                    _tx += _tw
                _bg_drawn = True
            except Exception:
                pass
        if not _bg_drawn:
            screen.fill(C["bg"])

        # ── Grid lines (darker — less intrusive than debug era) ───────────
        _GRID = (18, 22, 34)
        first_wx = (int(cam_x) // 64) * 64
        for wx in range(first_wx, int(cam_x) + self.sw + 64, 64):
            sx = wx - int(cam_x)
            pygame.draw.line(screen, _GRID, (sx, 0), (sx, self.sh))
        for y in range(0, self.sh, 64):
            pygame.draw.line(screen, _GRID, (0, y), (self.sw, y))

        # ── Base zone tint — player (left, blue) & enemy (right, red) ────
        # Layout constants matching Figma v2: HUD_H=140, DECK_H=180
        _HUD_Y  = 140
        _ZONE_H = self.sh - 180 - _HUD_Y   # playable band height

        # Player zone: world x 0 → sw
        p_right_sx = self.sw - int(cam_x)
        if p_right_sx > 0:
            w = min(p_right_sx, self.sw)
            pz = self._get_surf("pzone_bg", (self.sw, self.sh))
            pz.fill((0, 0, 0, 0))
            pygame.draw.rect(pz, (20, 60, 140, 18), (0, _HUD_Y, w, _ZONE_H))
            screen.blit(pz, (0, 0))

        # Enemy zone: world x (world_w - sw) → world_w
        e_left_sx = (self.world_w - self.sw) - int(cam_x)
        if e_left_sx < self.sw:
            x_start = max(0, e_left_sx)
            w = self.sw - x_start
            ez = self._get_surf("ezone_bg", (self.sw, self.sh))
            ez.fill((0, 0, 0, 0))
            pygame.draw.rect(ez, (140, 40, 20, 18), (x_start, _HUD_Y, w, _ZONE_H))
            screen.blit(ez, (0, 0))

        # ── Zone boundary lines ────────────────────────────────────────────
        for bwx in (self.sw, self.world_w - self.sw):
            bsx = bwx - int(cam_x)
            if -2 <= bsx <= self.sw + 2:
                pygame.draw.line(screen, C["zone_div"], (bsx, 0), (bsx, self.sh), 2)

        # ── HQ anchor outlines (no SRCALPHA — solid border rect) ──────────
        # Player HQ world-x = SAFE(132) + HQ_W//2(200) = 332
        # Enemy  HQ world-x = world_w − 332
        _HQ_HALF = 200
        for hq_wx, col in ((332, (50, 130, 220)), (self.world_w - 332, (220, 80, 40))):
            hq_sx = hq_wx - int(cam_x)
            if -_HQ_HALF - 4 <= hq_sx <= self.sw + _HQ_HALF + 4:
                pygame.draw.rect(screen, col,
                                 (hq_sx - _HQ_HALF, _HUD_Y,
                                  _HQ_HALF * 2, _ZONE_H), 1)

        # ── Horizontal lane divider ────────────────────────────────────────
        pygame.draw.line(
            screen, C["lane_div"],
            (0, self.sh // 2), (self.sw, self.sh // 2), 1
        )

        # ── Lane Y guides (dimmer than before) ────────────────────────────
        top_y = 354
        bot_y = 783
        for lane_y, col in ((top_y, (40, 80, 140)), (bot_y, (140, 80, 30))):
            self._dashed_hline(screen, col, 0, self.sw, lane_y)

    def draw_building_slots(
        self,
        screen: pygame.Surface,
        cam_x: float,
        all_slots: list[tuple[int, int]],
        occupied: set[int],
        build_state_name: str = "NONE",
    ) -> None:
        """
        Draw empty slot placeholders with 3 visual states:
          NONE         — low contrast (idle, barely visible)
          CONSTRUCTING — medium contrast (build mode)
          DEMOLISHING  — dim red tint (demolish mode)
        Occupied slots are skipped; the building sprite renders itself.
        """
        ss = self.slot_size

        # Choose fill & border by build state
        if build_state_name == "CONSTRUCTING":
            surf_key, fill_col = "slot_build", (50, 100, 180, 38)
            b_top, b_bot = (60, 110, 190), (170, 100, 40)
        elif build_state_name == "DEMOLISHING":
            surf_key, fill_col = "slot_demo", (140, 40, 40, 28)
            b_top = b_bot = (110, 50, 50)
        else:
            surf_key, fill_col = "slot_idle", (28, 55, 100, 14)
            b_top, b_bot = (28, 48, 82), (82, 52, 22)

        # Allocate once; reuse every frame (WASM-safe)
        if surf_key not in self._cached_surfs:
            s = pygame.Surface((ss, ss), pygame.SRCALPHA)
            s.fill(fill_col)
            self._cached_surfs[surf_key] = s
        slot_surf = self._cached_surfs[surf_key]

        for idx, (wx, wy) in enumerate(all_slots):
            if idx in occupied:
                continue
            sx = wx - int(cam_x)
            if sx + ss < 0 or sx > self.sw:
                continue
            screen.blit(slot_surf, (sx, wy))
            self._dashed_rect(screen, b_top if idx < 16 else b_bot, sx, wy, ss, ss)

    # ──────────────────────────────────────────────────────────────────────────
    # TOP HUD  (resource bar)
    # ──────────────────────────────────────────────────────────────────────────

    def draw_top_hud(self, screen: pygame.Surface, snap: UISnapshot) -> None:
        """
        Fixed top bar: [timer] [ore] [income] [cycle bar]
        Debug mode adds: full income breakdown + FPS/CAM hint strip (row 2).
        """
        # Background strip
        pygame.draw.rect(screen, C["hud_bg"], (0, 0, self.sw, 28))
        pygame.draw.rect(screen, C["hud_border"], (0, 0, self.sw, 28), 1)

        # Timer (left)
        m = snap.game_timer_seconds // 60
        s = snap.game_timer_seconds % 60
        self._txt(screen, f"{m:02d}:{s:02d}", (8, 5), size=22,
                  color=(80, 220, 255) if snap.game_timer_seconds % 2 == 0 else (60, 180, 220))

        # Minerals
        ore_col = C["gold"] if snap.income_flash else (200, 180, 80)
        self._txt(screen, f"⛏ {snap.minerals}", (120, 5), size=22, color=ore_col)

        # Income: simple in normal mode; full breakdown in debug mode
        if snap.debug_mode:
            alive = [b for b in snap.slot_buildings if not b.is_dead]
            bar_n = sum(1 for b in alive if b.kind == "barracks")
            ref_n = sum(1 for b in alive if b.kind == "refinery")
            parts = ["Base 10"]
            if bar_n: parts.append(f"{bar_n}×Bar(+{bar_n*5})")
            if ref_n: parts.append(f"{ref_n}×Ref(+{ref_n*10})")
            parts.append(f"= {snap.income_per_cycle}/5s")
            self._txt(screen, "  ".join(parts), (300, 8), size=15, color=(140, 180, 240))
        else:
            self._txt(screen, f"+{snap.income_per_cycle}/5s",
                      (300, 5), size=20, color=(100, 160, 240))

        # Income cycle progress bar (right side)
        bar_x, bar_y, bar_w, bar_h = self.sw - 180, 9, 170, 9
        pygame.draw.rect(screen, (40, 40, 70), (bar_x, bar_y, bar_w, bar_h))
        fill_w = int(bar_w * snap.cycle_progress)
        bar_col = (255, 220, 50) if snap.income_flash else C["gold"]
        if fill_w > 0:
            pygame.draw.rect(screen, bar_col, (bar_x, bar_y, fill_w, bar_h))
        pygame.draw.rect(screen, (120, 100, 40), (bar_x, bar_y, bar_w, bar_h), 1)

        # ── HQ HP bars (centred in top bar) ──────────────────────────────────
        # Player HQ: left side  |  Enemy HQ: right side (mirrored)
        hq_bar_w, hq_bar_h = 140, 9
        hq_bar_y = 9

        # Player HQ bar (blue)
        p_ratio   = max(0.0, snap.player_hq_hp / max(1, snap.player_hq_max))
        p_bar_x   = self.sw // 2 - hq_bar_w - 8
        p_fill_w  = int(hq_bar_w * p_ratio)
        p_col     = (0, 200, 80) if p_ratio > 0.5 else (220, 180, 0) if p_ratio > 0.25 else (220, 50, 50)
        pygame.draw.rect(screen, (20, 30, 60),   (p_bar_x, hq_bar_y, hq_bar_w, hq_bar_h))
        if p_fill_w > 0:
            pygame.draw.rect(screen, p_col,      (p_bar_x, hq_bar_y, p_fill_w, hq_bar_h))
        pygame.draw.rect(screen, (60, 120, 200), (p_bar_x, hq_bar_y, hq_bar_w, hq_bar_h), 1)
        self._txt(screen, f"HQ {snap.player_hq_hp}",
                  (p_bar_x, hq_bar_y + hq_bar_h + 1), size=12, color=(100, 160, 255))

        # Enemy HQ bar (red, fills right-to-left)
        e_ratio   = max(0.0, snap.enemy_hq_hp / max(1, snap.enemy_hq_max))
        e_bar_x   = self.sw // 2 + 8
        e_fill_w  = int(hq_bar_w * e_ratio)
        e_col     = (220, 50, 50) if e_ratio > 0.25 else (255, 140, 0)
        pygame.draw.rect(screen, (60, 20, 20),   (e_bar_x, hq_bar_y, hq_bar_w, hq_bar_h))
        if e_fill_w > 0:
            # Enemy bar fills from the right edge so depletion is visually obvious
            pygame.draw.rect(screen, e_col,
                             (e_bar_x + hq_bar_w - e_fill_w, hq_bar_y,
                              e_fill_w, hq_bar_h))
        pygame.draw.rect(screen, (180, 60, 60),  (e_bar_x, hq_bar_y, hq_bar_w, hq_bar_h), 1)
        e_hp_lbl = f"{snap.enemy_hq_hp} HQ"
        e_surf   = self._safe_render(self._font(12), e_hp_lbl, True, (255, 100, 100))
        screen.blit(e_surf, (e_bar_x + hq_bar_w - e_surf.get_width(),
                             hq_bar_y + hq_bar_h + 1))

        # ── VS label between the two bars ────────────────────────────────────
        vs_surf = self._safe_render(self._font(14), "VS", True, (120, 120, 140))
        screen.blit(vs_surf, (self.sw // 2 - vs_surf.get_width() // 2, 5))

        # Debug hint strip (row 2) — only when debug_mode is on
        if snap.debug_mode:
            hint = (
                f"FPS:{snap.fps:.0f}  CAM:{snap.cam_x:.0f}/{self.world_w - self.sw}  "
                "D=demolish  RMB/ESC=cancel  F1=off  R=reset"
            )
            self._txt(screen, hint, (8, 32), size=14, color=(180, 140, 40))

    # ──────────────────────────────────────────────────────────────────────────
    # MINIMAP
    # ──────────────────────────────────────────────────────────────────────────

    # Minimap dimensions (200×150 tactical minimap per spec).
    MINIMAP_W = 200
    MINIMAP_H = 150

    @property
    def minimap_rect(self) -> pygame.Rect:
        """
        Lazily-constructed minimap hit-rect, cached on the instance.

        Positioned in the top-right corner of the screen with a small margin
        so it doesn't clash with the existing top HUD (resource bar + HP bars)
        or the bottom card deck.
        """
        if self._minimap_rect is None:
            map_x = self.sw - self.MINIMAP_W - 16
            map_y = 48   # below the 28-px top HUD with a little gap
            self._minimap_rect = pygame.Rect(
                map_x, map_y, self.MINIMAP_W, self.MINIMAP_H
            )
        return self._minimap_rect

    def draw_minimap(
        self,
        screen: pygame.Surface,
        snap: Optional[UISnapshot] = None,
        world_width:  Optional[int]   = None,
        world_height: Optional[int]   = None,
        camera_x:     Optional[float] = None,
        camera_y:     Optional[float] = None,
        units:        Optional[list]  = None,
        buildings:    Optional[list]  = None,
    ) -> None:
        """
        Tactical minimap — 200×150 rectangle in the top-right corner.

        Draws a semi-transparent dark background, then one small coloured
        square per Building (HQs are slightly larger), one smaller dot per
        Unit, and finally a hollow rectangle showing where the current
        camera viewport sits within the world.

        Colour code
        -----------
            team 0  (player) →  blue / cyan
            team 1  (ally)   →  cyan / green
            team 2  (enemy)  →  red  / purple

        Parameter resolution
        --------------------
        When called with an explicit `snap` (the existing call-site in
        `draw_all`) the world / camera / unit / building refs are pulled
        off the snapshot.  Any caller may override individual refs via
        the keyword arguments — which also matches the task-brief
        `draw_minimap(screen, world_width, world_height, camera_x,
        camera_y, units, buildings)` signature.
        """
        # ── Resolve inputs (keyword overrides snapshot values) ───────────
        ww = world_width  if world_width  is not None else self.world_w
        wh = world_height if world_height is not None else self.sh
        cx = camera_x     if camera_x     is not None else (snap.cam_x if snap else 0.0)
        cy = camera_y     if camera_y     is not None else 0.0
        blds = (buildings if buildings is not None
                else (snap.all_buildings if snap else []))
        uns  = (units if units is not None
                else (snap.units if snap else []))

        rect = self.minimap_rect

        # ── Semi-transparent dark background ─────────────────────────────
        bg = self._get_surf("minimap_bg", (rect.width, rect.height))
        bg.fill((6, 10, 20, 200))
        screen.blit(bg, (rect.x, rect.y))
        pygame.draw.rect(screen, (60, 90, 140), rect, 1)

        # Label above the minimap rect
        self._txt(screen, "MINIMAP", (rect.x, rect.y - 15),
                  size=14, color=(100, 150, 200))

        # ── Scale factors: world → minimap ───────────────────────────────
        scale_x = rect.width  / max(1, ww)
        scale_y = rect.height / max(1, wh)

        # ── Buildings (squares; HQs are larger) ──────────────────────────
        for b in blds:
            if getattr(b, "is_dead", False):
                continue
            team = getattr(b, "team", 0)
            if team == 0:
                col = ( 80, 160, 255)   # Player: blue
            elif team == 1:
                col = ( 80, 240, 180)   # Ally: cyan
            else:
                col = (235,  80, 120)   # Enemy / Swarm: red-purple

            size = 6 if getattr(b, "is_hq", False) else 4
            half = size // 2
            bx = rect.x + int(b.pos[0] * scale_x) - half
            by = rect.y + int(b.pos[1] * scale_y) - half
            # Clamp so the square is always fully inside the minimap
            bx = max(rect.x, min(rect.right  - size, bx))
            by = max(rect.y, min(rect.bottom - size, by))
            pygame.draw.rect(screen, col, (bx, by, size, size))

        # ── Units (2×2 dots) ─────────────────────────────────────────────
        for u in uns:
            if getattr(u, "is_dead", False):
                continue
            team = getattr(u, "team", 0)
            if team == 0:
                col = (120, 200, 255)   # Player: light blue
            elif team == 1:
                col = (120, 240, 200)   # Ally: cyan
            else:
                col = (220, 120, 200)   # Enemy / Swarm: purple-red

            ux = rect.x + int(u.pos[0] * scale_x)
            uy = rect.y + int(u.pos[1] * scale_y)
            ux = max(rect.x, min(rect.right  - 2, ux))
            uy = max(rect.y, min(rect.bottom - 2, uy))
            pygame.draw.rect(screen, col, (ux, uy, 2, 2))

        # ── Camera viewport (hollow rect, width=1) ───────────────────────
        vp_w = max(2, int(self.sw * scale_x))
        vp_h = max(2, int(self.sh * scale_y))
        vp_x = rect.x + int(cx * scale_x)
        vp_y = rect.y + int(cy * scale_y)
        # Keep the viewport rect inside the minimap bounds
        vp_x = max(rect.x, min(rect.right  - vp_w, vp_x))
        vp_y = max(rect.y, min(rect.bottom - vp_h, vp_y))
        pygame.draw.rect(screen, (255, 255, 255),
                         (vp_x, vp_y, vp_w, vp_h), 1)

    # ── Minimap click-to-pan ──────────────────────────────────────────────────

    def handle_minimap_click(
        self, mx: int, my: int
    ) -> Optional[tuple[float, float]]:
        """
        If (mx, my) falls inside the minimap rect, return the desired
        (target_cam_x, target_cam_y) in world coordinates — unclamped,
        so the caller is responsible for clamping to its own world bounds.

        Returns None if the click is outside the minimap (caller should
        keep handling the event normally).

        The target is computed so that the clicked spot on the minimap
        becomes the centre of the screen:

            pct_x = (mx - rect.x) / rect.width
            target_cam_x = pct_x * world_width - screen_width / 2
        """
        rect = self.minimap_rect
        if not rect.collidepoint(mx, my):
            return None
        pct_x = (mx - rect.x) / rect.width
        pct_y = (my - rect.y) / rect.height
        target_cam_x = pct_x * self.world_w - (self.sw / 2)
        target_cam_y = pct_y * self.sh      - (self.sh / 2)
        return target_cam_x, target_cam_y

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
            hi = self._get_surf("ghost_hi", (ss, ss))
            hi.fill(col)
            screen.blit(hi, (sx, wy))
            border_col = (0, 255, 100) if snap.ghost_valid else (255, 60, 60)
            pygame.draw.rect(screen, border_col, (sx, wy, ss, ss), 2)
            label = "Place" if snap.ghost_valid else "Occupied"
            self._txt(screen, label, (sx + 2, wy - 14), size=16, color=border_col)

        # Ghost sprite — blit cached surface directly (alpha=120 baked in)
        ghost_surf = self._get_ghost_surf(snap.ghost_kind)
        rect = ghost_surf.get_rect(center=(gx, gy))
        screen.blit(ghost_surf, rect)

    def draw_nuke_ghost(
        self,
        screen: pygame.Surface,
        ghost_pos: tuple[int, int],
    ) -> None:
        """Nuke targeting crosshair + AoE circle."""
        gx, gy = ghost_pos
        aoe = self._get_surf("nuke_aoe", (self.sw, self.sh))
        aoe.fill((0, 0, 0, 0))   # clear previous frame
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
        # Deck backing strip — deep space bg + neon-cyan separator line
        bar_h = self.CARD_H + 16
        bar_surf = self._get_surf("bottom_bar", (self.sw, bar_h))
        bar_surf.fill((*C["deck_bg"], 240))
        screen.blit(bar_surf, (0, self.sh - bar_h))
        pygame.draw.line(screen, C["border_active"],
                         (0, self.sh - bar_h), (self.sw, self.sh - bar_h), 2)

        from src.logic import BuildState  # local import avoids circular dep
        active_kinds, card_rects = self.get_card_layout(snap.player_faction)

        for i, rect in enumerate(card_rects):
            kind = active_kinds[i]
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
        if active:
            bg, bdr, bdr_w = (85, 18, 18), (220, 55, 55), 2
            accent, label_col, hint_col = (255, 70, 70), (255, 120, 110), (180, 75, 75)
        else:
            bg, bdr, bdr_w = (20, 13, 13), (55, 32, 32), 1
            accent, label_col, hint_col = (75, 30, 30), (130, 75, 75), (85, 52, 52)

        bdr = C["border_active"] if active else bdr   # neon cyan when active
        pygame.draw.rect(screen, bg,  rect, border_radius=8)
        pygame.draw.rect(screen, bdr, rect, bdr_w, border_radius=8)
        pygame.draw.rect(screen, accent,
                         (rect.x + 1, rect.y + 4, 4, rect.h - 8), border_radius=2)

        self._txt_shd(screen, "DEMOLISH",  (rect.x + 12, rect.y + 10), 20, label_col)
        self._txt(screen, "[D key]",    (rect.x + 12, rect.y + 42), size=15, color=hint_col)
        self._txt(screen, "60% refund", (rect.x + 12, rect.y + 64), size=13, color=hint_col)

    def _draw_nuke_card(
        self, screen: pygame.Surface, rect: pygame.Rect, snap: UISnapshot
    ) -> None:
        active = (snap.build_state_name == "NUKING")
        avail  = snap.nuke_available

        if active:
            bg, bdr, bdr_w = (125, 14, 14), (255, 35, 35), 2
        elif avail:
            bg, bdr, bdr_w = (48, 11, 11), (180, 55, 55), 2
        else:
            bg, bdr, bdr_w = (15, 9, 9), (42, 32, 32), 1

        bdr = C["border_active"] if active else bdr   # neon cyan when firing
        pygame.draw.rect(screen, bg,  rect, border_radius=8)
        pygame.draw.rect(screen, bdr, rect, bdr_w, border_radius=8)

        accent = (210, 45, 45) if avail else (55, 35, 35)
        pygame.draw.rect(screen, accent,
                         (rect.x + 1, rect.y + 4, 4, rect.h - 8), border_radius=2)

        label_col  = (255, 100, 80) if avail else (65, 52, 50)
        status_col = (255, 55, 55) if active else ((195, 75, 75) if avail else (58, 48, 48))
        note_col   = (130, 72, 72) if avail else (50, 44, 44)

        self._txt_shd(screen, "☢ NUKE",
                      (rect.x + 12, rect.y + 10), 20, label_col)
        self._txt_shd(screen, "⚡ ARMED" if avail else "✕ EXPENDED",
                      (rect.x + 12, rect.y + 42), 16, status_col)
        self._txt(screen, "450px AoE",
                  (rect.x + 12, rect.y + 68), size=13, color=note_col)

    # Per-building accent colour and icon table
    _CARD_THEME: dict[str, tuple] = {
        #         accent RGB         icon
        "barracks":      ((70,  130, 220), "⚔"),
        "refinery":      ((220, 120,  40), "⛽"),
        "rover_bay":     ((200, 160,  30), "▶"),
        "spec_ops":      ((80,   60, 175), "◈"),
        "heavy_factory": ((180,  60,  30), "◉"),
        "starport":      ((50,  160, 200), "✦"),
        "turret":        ((60,  100, 160), "🔫"),   # static defence
    }

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
        # Prefer Traditional Chinese name from spec; fallback to kind in caps
        display_name = spec.get("name", kind.upper())

        active     = (snap.ghost_kind == kind and snap.build_state_name == "CONSTRUCTING")
        affordable = (snap.minerals >= cost)

        # Background
        if active and affordable:
            bg = (22, 45, 32)
        elif not affordable:
            bg = (16, 20, 30)
        else:
            bg = C["card_bg"]
        pygame.draw.rect(screen, bg, rect, border_radius=8)

        # Border — neon cyan when active, muted steel otherwise
        if active:
            bdr_col = C["border_active"] if affordable else (180, 60, 60)
            pygame.draw.rect(screen, bdr_col, rect, 2, border_radius=8)
        elif affordable:
            pygame.draw.rect(screen, C["hud_border"], rect, 1, border_radius=8)
        else:
            pygame.draw.rect(screen, (38, 34, 48), rect, 1, border_radius=8)

        # Left accent bar (4 px) — per-building colour
        theme = self._CARD_THEME.get(kind, ((120, 120, 120), "?"))
        _a, icon = theme
        accent = tuple(max(0, c - 80) for c in _a) if not affordable else _a
        pygame.draw.rect(screen, accent,
                         (rect.x + 1, rect.y + 4, 4, rect.h - 8), border_radius=2)

        # Name — Traditional Chinese, shadow + main text
        name_col = (230, 245, 230) if affordable else (90, 82, 95)
        self._txt_shd(screen, display_name, (rect.x + 12, rect.y + 10), 20, name_col)

        # Cost — shadow + amber gold
        cost_col = C["gold"] if affordable else (110, 90, 50)
        self._txt_shd(screen, f"⛏ {cost}", (rect.x + 12, rect.y + 42), 19, cost_col)

        # Stats (small — no shadow needed at this size)
        stats_col = (70, 105, 155) if affordable else (52, 52, 68)
        if kind == "turret":
            atk_dmg    = spec.get("atk_dmg", 0)
            scan_range = spec.get("scan_range", 0)
            stat_line  = f"ATK {atk_dmg}  RNG {scan_range}px  +{income_b}/c"
        elif unit_type:
            stat_line = f"→{unit_type} {spawn_rate}s  +{income_b}/c"
        else:
            stat_line = f"+{income_b}/c"
        self._txt(screen, stat_line,
                  (rect.x + 12, rect.y + 70), size=13, color=stats_col)

        # Top-right icon block — per-building colour
        art_col = tuple(max(0, c - 80) for c in _a) if not affordable else _a
        art_rect = pygame.Rect(rect.right - 34, rect.y + 8, 26, 26)
        pygame.draw.rect(screen, art_col, art_rect, border_radius=4)
        self._txt(screen, icon, (art_rect.x + 5, art_rect.y + 4), size=14,
                  color=(220, 240, 255))

    # ──────────────────────────────────────────────────────────────────────────
    # FLOATING NOTIFICATIONS
    # ──────────────────────────────────────────────────────────────────────────

    def draw_floating_notifs(self, screen: pygame.Surface) -> None:
        for n in self._notifs:
            surf = self._safe_render(self._font(20), n.text, True, n.color)
            surf.set_alpha(n.alpha)
            screen.blit(surf, (int(n.x) - surf.get_width() // 2, int(n.y)))

    # ──────────────────────────────────────────────────────────────────────────
    # RESULT OVERLAY
    # ──────────────────────────────────────────────────────────────────────────

    def draw_result_overlay(
        self,
        screen:          pygame.Surface,
        game_state_name: str,
        snap:            "UISnapshot | None" = None,
    ) -> None:
        """
        Victory / Defeat full-screen overlay matching Figma v2 Frame 3 — 結算畫面.

        Pixel-exact button rects (from Figma):
          再戰一局  x=840,  y=821, 420×112  →  result_hit_test returns "restart"
          返回首頁  x=1296, y=821, 420×112  →  result_hit_test returns "home"
        """
        FG   = self._FG
        is_win = (game_state_name == "VICTORY")
        cx = self.sw // 2
        SAFE = 132

        accent = FG["green"] if is_win else FG["red"]

        # ── Full-screen dark overlay (Figma: dark,0.72) ───────────────────
        overlay = self._get_surf("result_overlay", (self.sw, self.sh))
        overlay.fill((0, 0, 0, 184))
        screen.blit(overlay, (0, 0))

        # BG glow behind hero text (Figma: W/2-600,H/2-440, 1200×880, green .035)
        glow_key = f"result_glow_{'w' if is_win else 'l'}"
        glow = self._get_surf(glow_key, (1200, 880))
        glow.fill((0, 0, 0, 0))
        pygame.draw.rect(glow, (*accent, 9), (0, 0, 1200, 880), border_radius=70)
        screen.blit(glow, (cx - 600, self.sh // 2 - 440))

        # Safe zone dim
        s = self._get_surf("result_safe", (SAFE, self.sh))
        s.fill((0, 0, 0, 72))
        screen.blit(s, (0, 0))
        screen.blit(s, (self.sw - SAFE, 0))

        # ── Hero text — 勝利 / 敗北  (Figma vitY=120) ─────────────────────
        vitY = 120
        # Halo rect behind hero text
        halo_key = f"result_halo_{'w' if is_win else 'l'}"
        halo = self._get_surf(halo_key, (1040, 340))
        halo.fill((0, 0, 0, 0))
        pygame.draw.rect(halo, (*accent, 9), (0, 0, 1040, 340), border_radius=32)
        screen.blit(halo, (cx - 520, vitY - 40))

        if is_win:
            hero     = self._safe_render(self._font(240), "勝  利", True, FG["green"])
            sub_en   = self._safe_render(self._font(52), "V I C T O R Y", True, FG["green"])
        else:
            hero     = self._safe_render(self._font(240), "敗  北", True, FG["red"])
            sub_en   = self._safe_render(self._font(52), "D E F E A T", True,   FG["red"])

        screen.blit(hero,   hero.get_rect(centerx=cx, top=vitY))
        screen.blit(sub_en, sub_en.get_rect(centerx=cx, top=vitY + 256))
        pygame.draw.rect(screen, (*accent, 115),
                         (cx - 260, vitY + 328, 520, 3))

        # ── Stats panel  (Figma: spX=878,spY=495, 800×290, panelA) ────────
        spW, spH, spX, spY = 800, 290, cx - 400, vitY + 375
        sp_surf = self._get_surf("result_stats", (spW, spH))
        sp_surf.fill((*FG["panelA"], 230))
        pygame.draw.rect(sp_surf, (*FG["cyan"], 51),
                         (0, 0, spW, spH), 1, border_radius=20)
        screen.blit(sp_surf, (spX, spY))

        if snap is not None:
            t   = snap.game_timer_seconds
            rows = [
                ("存活時間", f"{t // 60:02d}:{t % 60:02d}"),
                ("擊殺數",   str(snap.player_kills)),
                ("建築建造", str(snap.buildings_placed)),
                ("礦石收入", str(snap.total_income_earned)),
            ]
        else:
            rows = [
                ("存活時間", "--:--"),
                ("擊殺數",   "?"),
                ("建築建造", "?"),
                ("礦石收入", "?"),
            ]
        for i, (label, val) in enumerate(rows):
            ry = spY + 24 + i * 58
            self._txt(screen, label, (spX + 32, ry), size=24, color=FG["midGy"])
            v_surf = self._safe_render(self._font(30), val, True, (255, 255, 255))
            screen.blit(v_surf, (spX + spW - 38 - v_surf.get_width(), ry))
            if i < len(rows) - 1:
                pygame.draw.rect(screen, (255, 255, 255, 15),
                                 (spX + 24, ry + 50, spW - 48, 1))

        # ── Action buttons (Figma pixel-exact) ────────────────────────────
        # 再戰一局: x=840, y=821, 420×112
        rx, ry, rw, rh = self._BTN_REMATCH
        self._restart_rect = pygame.Rect(rx, ry, rw, rh)

        # 返回首頁: x=1296, y=821, 420×112
        hx, hy, hw, hh = self._BTN_HOME
        self._home_rect = pygame.Rect(hx, hy, hw, hh)

        # Draw 再戰一局 — neon green fill + bracket corners
        pygame.draw.rect(screen, (0, 22, 10), self._restart_rect, border_radius=18)
        pygame.draw.rect(screen, FG["green"], self._restart_rect, 2, border_radius=18)
        r_lbl = self._safe_render(self._font(48), "再戰一局", True, FG["green"])
        screen.blit(r_lbl, r_lbl.get_rect(center=self._restart_rect.center))

        # Draw 返回首頁 — cyan fill + bracket corners
        pygame.draw.rect(screen, (5, 11, 28), self._home_rect, border_radius=18)
        pygame.draw.rect(screen, FG["cyan"], self._home_rect, 2, border_radius=18)
        h_lbl = self._safe_render(self._font(48), "返回首頁", True, FG["cyan"])
        screen.blit(h_lbl, h_lbl.get_rect(center=self._home_rect.center))

    # ──────────────────────────────────────────────────────────────────────────
    # MAIN MENU  (title screen)
    # ──────────────────────────────────────────────────────────────────────────

    def draw_main_menu(self, screen: pygame.Surface) -> None:
        """
        Title screen — Figma v3 ergonomic landscape layout.

        Thumb-zone button stack (right side, pixel-exact):
          PVP        600×160  at (1824, 300)  → "pvp"      neon green
          1V1        500×120  at (1924, 480)  → locked     frosted cyan
          2V2        500×120  at (1924, 620)  → locked     frosted cyan
          AI Battle  500×120  at (1924, 760)  → "ai_battle" blue
          Settings   100×100  at (2308,  20)  → "settings"  corner

        Left zone: Chinese + English title, bottom-left game info.
        """
        FG   = self._FG
        sw, sh = self.sw, self.sh
        SAFE = 132

        # ── Background (near-black + atmospheric glows) ───────────────────
        screen.fill(FG["bg"])

        if not hasattr(self, "_mm_glows"):
            self._mm_glows = pygame.Surface((sw, sh), pygame.SRCALPHA)
            pygame.draw.ellipse(self._mm_glows, (0, 12, 60, 28),
                                (-80, sh - 560, 760, 720))
            pygame.draw.ellipse(self._mm_glows, (0, 30, 80, 18),
                                (sw - 600, -140, 700, 560))
            pygame.draw.ellipse(self._mm_glows, (0, 100, 40, 10),
                                (sw - 800, 200, 860, 700))
        screen.blit(self._mm_glows, (0, 0))

        # Subtle hex-grid lines
        for i in range(1, 9):
            x = int(sw / 8 * i)
            pygame.draw.line(screen, (20, 30, 60), (x, 0), (x, sh))
        for i in range(1, 5):
            y = int(sh / 4 * i)
            pygame.draw.line(screen, (20, 30, 60), (0, y), (sw, y))

        # Safe zone edges (Dynamic Island shadow)
        if not hasattr(self, "_mm_safe"):
            self._mm_safe = pygame.Surface((SAFE, sh), pygame.SRCALPHA)
            self._mm_safe.fill((0, 0, 0, 80))
        screen.blit(self._mm_safe, (0, 0))
        screen.blit(self._mm_safe, (sw - SAFE, 0))

        # ── Left zone — title art ─────────────────────────────────────────
        title_x = SAFE + 60

        # Dim art-placeholder rectangle
        if not hasattr(self, "_mm_art_surf"):
            self._mm_art_surf = pygame.Surface((1560, sh - 100), pygame.SRCALPHA)
            self._mm_art_surf.fill((255, 255, 255, 5))
        screen.blit(self._mm_art_surf, (SAFE, 50))

        # Chinese title — 星核戰線
        cn_shadow = self._safe_render(self._font(96), "星核戰線", True, FG["panelA"])
        screen.blit(cn_shadow, (title_x + 3, 313))
        cn_main   = self._safe_render(self._font(96), "星核戰線", True, FG["cyan"])
        screen.blit(cn_main, (title_x, 310))

        # English title — Star Raise
        en_shadow = self._safe_render(self._font(148), "Star Raise", True, FG["panelA"])
        screen.blit(en_shadow, (title_x + 4, 424))
        en_main   = self._safe_render(self._font(148), "Star Raise", True, FG["gold"])
        screen.blit(en_main, (title_x, 420))

        # Subtitle tagline
        tag = self._safe_render(self._font(32), "Real-Time Strategy", True, FG["cyan"])
        screen.blit(tag, (title_x + 4, 580))

        # ── Bottom-left game info (inside safe zone) ──────────────────────
        info_lbl = self._safe_render(self._font(24), 
            "Winstar  v1.0  ·  D E V", True, FG["gray"])
        screen.blit(info_lbl, (SAFE + 20, sh - 60))

        # ── Right button stack ────────────────────────────────────────────

        # PVP — 1824,300  600×160  neon-green, interactive
        px, py, pw, ph = self._BTN_PVP
        self._pvp_rect = pygame.Rect(px, py, pw, ph)

        if not hasattr(self, "_mm_pvp_bloom"):
            self._mm_pvp_bloom = pygame.Surface((pw + 60, ph + 60), pygame.SRCALPHA)
            pygame.draw.rect(self._mm_pvp_bloom, (*FG["green"], 14),
                             (0, 0, pw + 60, ph + 60), border_radius=26)
        screen.blit(self._mm_pvp_bloom, (px - 30, py - 30))

        pygame.draw.rect(screen, (0, 19, 9), self._pvp_rect, border_radius=18)
        pygame.draw.rect(screen, FG["green"], self._pvp_rect, 3, border_radius=18)

        pvp_lbl = self._safe_render(self._font(100), "P  V  P", True, FG["green"])
        screen.blit(pvp_lbl,
                    pvp_lbl.get_rect(left=px + 22, centery=py + ph // 2 - 14))
        sub_pvp = self._safe_render(self._font(22), "多人對戰", True, FG["greenG"])
        screen.blit(sub_pvp, (px + 22, py + ph - 34))
        pygame.draw.rect(screen, (*FG["green"], 90),
                         (px + 22, py + ph - 38, pw - 44, 2))

        # 1V1 — 1924,480  500×120  cyan, interactive
        bx, by, bw, bh = self._BTN_1V1
        self._1v1_rect = pygame.Rect(bx, by, bw, bh)
        pygame.draw.rect(screen, (5, 13, 32), (bx, by, bw, bh), border_radius=16)
        pygame.draw.rect(screen, FG["cyan"], (bx, by, bw, bh), 2, border_radius=16)
        lbl1 = self._safe_render(self._font(78), "1  V  1", True, (166, 219, 249))
        screen.blit(lbl1, lbl1.get_rect(left=bx + 22, centery=by + bh // 2 - 12))
        sub1 = self._safe_render(self._font(22), "單挑對決", True, FG["gray"])
        screen.blit(sub1, (bx + 22, by + bh - 28))

        # 2V2 — 1924,620  500×120  cyan, interactive
        bx, by, bw, bh = self._BTN_2V2
        self._2v2_rect = pygame.Rect(bx, by, bw, bh)
        pygame.draw.rect(screen, (5, 13, 32), (bx, by, bw, bh), border_radius=16)
        pygame.draw.rect(screen, FG["cyan"], (bx, by, bw, bh), 2, border_radius=16)
        lbl2 = self._safe_render(self._font(78), "2  V  2", True, (166, 219, 249))
        screen.blit(lbl2, lbl2.get_rect(left=bx + 22, centery=by + bh // 2 - 12))
        sub2 = self._safe_render(self._font(22), "組隊對戰", True, FG["gray"])
        screen.blit(sub2, (bx + 22, by + bh - 28))

        # 單位說明 — 1924,760  500×120  blue, interactive (was AI Battle)
        ax, ay, aw, ah = self._BTN_AI_BATTLE
        self._unit_info_rect = pygame.Rect(ax, ay, aw, ah)

        if not hasattr(self, "_mm_ai_bloom"):
            self._mm_ai_bloom = pygame.Surface((aw + 40, ah + 40), pygame.SRCALPHA)
            pygame.draw.rect(self._mm_ai_bloom, (26, 107, 255, 18),
                             (0, 0, aw + 40, ah + 40), border_radius=20)
        screen.blit(self._mm_ai_bloom, (ax - 20, ay - 20))

        pygame.draw.rect(screen, (4, 14, 40), self._unit_info_rect, border_radius=16)
        pygame.draw.rect(screen, (26, 107, 255), self._unit_info_rect,
                         2, border_radius=16)
        ui_lbl = self._safe_render(self._font(78), "單位說明", True, (100, 170, 255))
        screen.blit(ui_lbl,
                    ui_lbl.get_rect(left=ax + 22, centery=ay + ah // 2 - 12))
        sub_ui = self._safe_render(self._font(22), "查看各單位數值", True, FG["gray"])
        screen.blit(sub_ui, (ax + 22, ay + ah - 28))

        # Settings — 2308,20  100×100  corner button
        sx, sy, sw2, sh2 = self._BTN_SETTINGS
        pygame.draw.rect(screen, (6, 15, 37), (sx, sy, sw2, sh2), border_radius=14)
        pygame.draw.rect(screen, FG["cyan"], (sx, sy, sw2, sh2), 1, border_radius=14)
        gear = self._safe_render(self._font(54), "⚙", True, FG["cyan"])
        screen.blit(gear, (sx + 22, sy + 8))
        slbl = self._safe_render(self._font(14), "系統設定", True, FG["gray"])
        screen.blit(slbl, (sx + 2, sy + sw2 - 20))

        # ── Bottom hint ───────────────────────────────────────────────────
        hint_lbl = self._safe_render(self._font(26),
            "選擇  1 V 1  或  2 V 2  開始遊戲  ·  ESC 退出",
            True, FG["midGy"])
        screen.blit(hint_lbl,
                    hint_lbl.get_rect(center=(sw // 2, sh - 36)))

        # ── Floating notifications (e.g. AI Battle toast) ─────────────────
        self.draw_floating_notifs(screen)

    # ──────────────────────────────────────────────────────────────────────────
    # HIT-TEST HELPERS  (for GameLoop mouse event routing)
    # ──────────────────────────────────────────────────────────────────────────

    def main_menu_hit_test(self, mx: int, my: int) -> Optional[str]:
        """
        Hit-test for Frame 1 — 首頁 buttons.

        Returns
        -------
        "pvp"        — PVP large button  (WIP — does nothing in main.py)
        "1v1"        — 1V1 button        (starts 1V1 game)
        "2v2"        — 2V2 button        (starts 2V2 game)
        "unit_info"  — 單位說明 button   (WIP — does nothing in main.py)
        "settings"   — ⚙ corner button   (WIP)
        None         — miss

        Rects are populated by draw_main_menu() on the first draw call.
        """
        if self._pvp_rect.collidepoint(mx, my):
            return "pvp"
        if self._1v1_rect.collidepoint(mx, my):
            return "1v1"
        if self._2v2_rect.collidepoint(mx, my):
            return "2v2"
        if self._unit_info_rect.collidepoint(mx, my):
            return "unit_info"
        sx, sy, sw2, sh2 = self._BTN_SETTINGS
        if pygame.Rect(sx, sy, sw2, sh2).collidepoint(mx, my):
            return "settings"
        return None

    def result_hit_test(self, mx: int, my: int) -> Optional[str]:
        """
        Returns "restart" (再戰一局) or "home" (返回首頁) based on which
        result-screen button was clicked.  Returns None for misses.
        The rects are populated by draw_result_overlay() on the first draw.
        """
        if self._restart_rect.collidepoint(mx, my):
            return "restart"
        if self._home_rect.collidepoint(mx, my):
            return "home"
        return None

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
        screen: pygame.Surface,
        color: tuple,
        x0: int,
        x1: int,
        y: int,
        dash: int = 12,
        gap: int = 8,
        width: int = 1,
    ) -> None:
        """Draw a horizontal dashed line from x0 to x1 at height y."""
        x = x0
        while x < x1:
            end = min(x + dash, x1)
            pygame.draw.line(screen, color, (x, y), (end, y), width)
            x += dash + gap

    @staticmethod
    def _dashed_rect(
        screen: pygame.Surface,
        color: tuple,
        x: int,
        y: int,
        w: int,
        h: int,
        dash: int = 8,
        gap: int = 6,
        width: int = 1,
    ) -> None:
        """Draw a dashed rectangle outline."""
        # Top edge
        cx = x
        while cx < x + w:
            end = min(cx + dash, x + w)
            pygame.draw.line(screen, color, (cx, y), (end, y), width)
            cx += dash + gap
        # Bottom edge
        cx = x
        while cx < x + w:
            end = min(cx + dash, x + w)
            pygame.draw.line(screen, color, (cx, y + h), (end, y + h), width)
            cx += dash + gap
        # Left edge
        cy = y
        while cy < y + h:
            end = min(cy + dash, y + h)
            pygame.draw.line(screen, color, (x, cy), (x, end), width)
            cy += dash + gap
        # Right edge
        cy = y
        while cy < y + h:
            end = min(cy + dash, y + h)
            pygame.draw.line(screen, color, (x + w, cy), (x + w, end), width)
            cy += dash + gap

    # ──────────────────────────────────────────────────────────────────────────
    # UNIT INFO SCREEN
    # ──────────────────────────────────────────────────────────────────────────

    def draw_unit_info(self, screen: pygame.Surface) -> None:
        """
        Full-screen unit encyclopedia with faction tabs.

        Layout
        ------
        • Dark starfield background
        • Header (title + subtitle)
        • Faction tab bar  [★ 星際聯邦]  [? 未知陣營]
        • 3 × 2 card grid — 6 Star Federation units
        • Back button at the bottom
        """
        W, H = screen.get_width(), screen.get_height()
        screen.fill((10, 14, 26))

        # ── Subtle star-field bg ──────────────────────────────────────────────
        rng = __import__("random").Random(42)
        for _ in range(120):
            sx = rng.randint(0, W)
            sy = rng.randint(0, H)
            pygame.draw.circle(screen, (rng.randint(60, 160),) * 3, (sx, sy), 1)

        # ── Header ────────────────────────────────────────────────────────────
        self._txt_shd(screen, "單位百科", (W // 2 - 110, 20), 54, (140, 210, 255))
        self._txt(screen, "Unit Encyclopedia", (W // 2 - 160, 80),
                  size=30, color=(55, 95, 160))

        # ── Faction tab bar ───────────────────────────────────────────────────
        TAB_Y    = 120
        TAB_H    = 52
        TAB_GAP  = 12
        tabs = [
            ("federation", "★ 星際聯邦  Star Federation"),
            ("unknown",    "?  未知陣營  Unknown Faction"),
        ]
        tab_rects: dict[str, pygame.Rect] = {}
        tab_x = W // 2 - 480
        for key, label in tabs:
            is_active = (self.encyclopedia_tab == key)
            tw        = 440
            tbg   = (25, 50, 110) if is_active else (14, 18, 32)
            tbdr  = (80, 160, 255) if is_active else (35, 40, 60)
            ttxt  = (200, 230, 255) if is_active else (55, 65, 90)
            r = pygame.Rect(tab_x, TAB_Y, tw, TAB_H)
            tab_rects[key] = r
            pygame.draw.rect(screen, tbg,  r, border_radius=8)
            pygame.draw.rect(screen, tbdr, r, 2, border_radius=8)
            self._txt(screen, label, (tab_x + 18, TAB_Y + 12), size=24, color=ttxt)
            tab_x += tw + TAB_GAP
        # Store for hit-test
        self._fed_tab_rect     = tab_rects["federation"]
        self._unknown_tab_rect = tab_rects["unknown"]

        # Divider line below tabs
        pygame.draw.line(screen, (35, 55, 110),
                         (W // 2 - 500, TAB_Y + TAB_H + 6),
                         (W // 2 + 500, TAB_Y + TAB_H + 6), 1)

        # ── Card layout — 3 × 2 grid ──────────────────────────────────────────
        COLS      = 3
        ROWS      = 2
        MARGIN_X  = 70
        MARGIN_TOP= TAB_Y + TAB_H + 20
        MARGIN_BOT= 110      # space for back button
        GAP_X     = 36
        GAP_Y     = 28
        CARD_W    = (W - 2 * MARGIN_X - (COLS - 1) * GAP_X) // COLS   # ≈ 772
        CARD_H    = (H - MARGIN_TOP - MARGIN_BOT - (ROWS - 1) * GAP_Y) // ROWS  # ≈ 414

        # ── Federation unit data ──────────────────────────────────────────────
        _FED_UNITS = [
            {
                "kind": "marine", "label": "Marine", "zh": "步兵",
                "accent": (50, 150, 255), "icon": "▲",
                "stats": [
                    ("生命值 HP",      "100"),
                    ("移速 Speed",     "1.8 px/f"),
                    ("傷害 ATK",       "15  ×1.5 vs Light"),
                    ("攻速 CD",        "1.0 s"),
                    ("偵測 Scan",      "150 px"),
                    ("飛行 Flying",    "否 No"),
                ],
                "atk":   "穿甲 Piercing",
                "armor": "輕甲 Light",
                "desc":  "快速步兵，穿甲彈有效克制輕甲。\nFast rifle infantry, shreds light armor.",
                "built": "步兵營 Barracks",
            },
            {
                "kind": "jackal", "label": "Jackal", "zh": "突擊車",
                "accent": (200, 160, 30), "icon": "▶",
                "stats": [
                    ("生命值 HP",      "80"),
                    ("移速 Speed",     "2.8 px/f  最快"),
                    ("傷害 ATK",       "20  均等傷害"),
                    ("攻速 CD",        "0.83 s"),
                    ("偵測 Scan",      "160 px"),
                    ("飛行 Flying",    "否 No"),
                ],
                "atk":   "普通 Normal",
                "armor": "輕甲 Light",
                "desc":  "最快地面單位，均等傷害無克制。\nFastest ground unit, neutral damage.",
                "built": "突擊車廠 Rover Bay",
            },
            {
                "kind": "ghost", "label": "Ghost", "zh": "幽靈",
                "accent": (80, 60, 200), "icon": "◈",
                "stats": [
                    ("生命值 HP",      "40  低"),
                    ("移速 Speed",     "1.6 px/f"),
                    ("傷害 ATK",       "35  ×1.5 vs Light"),
                    ("攻速 CD",        "1.33 s"),
                    ("偵測 Scan",      "250 px  遠"),
                    ("飛行 Flying",    "否 / 可擊空"),
                ],
                "atk":   "穿甲 Piercing",
                "armor": "輕甲 Light",
                "desc":  "超遠程狙擊手，可攻擊飛行目標。\nLong-range sniper, can hit aircraft.",
                "built": "特戰中心 Spec Ops",
            },
            {
                "kind": "tank", "label": "Tank", "zh": "坦克",
                "accent": (255, 140, 30), "icon": "■",
                "stats": [
                    ("生命值 HP",      "250  高"),
                    ("移速 Speed",     "1.1 px/f  慢"),
                    ("傷害 ATK",       "40  ×1.5 vs Heavy"),
                    ("攻速 CD",        "1.5 s"),
                    ("偵測 Scan",      "180 px"),
                    ("飛行 Flying",    "否 No"),
                ],
                "atk":   "重砲 Siege",
                "armor": "重甲 Heavy",
                "desc":  "耐久重型單位，重砲克制建築與重甲。\nDurable heavy; siege rounds smash structures.",
                "built": "裝甲廠 Refinery",
            },
            {
                "kind": "hellfire", "label": "Hellfire", "zh": "地獄火",
                "accent": (200, 55, 30), "icon": "◉",
                "stats": [
                    ("生命值 HP",      "120"),
                    ("移速 Speed",     "0.9 px/f  最慢"),
                    ("傷害 ATK",       "40  ×2.0 vs Structure"),
                    ("攻速 CD",        "1.67 s"),
                    ("偵測 Scan",      "300 px  最遠"),
                    ("濺射 Splash",    "60 px AoE"),
                ],
                "atk":   "重砲 Siege",
                "armor": "重甲 Heavy",
                "desc":  "重型AoE砲兵，摧毀建築效率最高。\nHeavy AoE artillery, annihilates structures.",
                "built": "重型兵工廠 Heavy Factory",
            },
            {
                "kind": "valkyrie", "label": "Valkyrie", "zh": "女武神",
                "accent": (50, 180, 210), "icon": "✦",
                "stats": [
                    ("生命值 HP",      "150"),
                    ("移速 Speed",     "2.2 px/f"),
                    ("傷害 ATK",       "25  ×0.5 vs Heavy"),
                    ("攻速 CD",        "1.17 s"),
                    ("偵測 Scan",      "150 px"),
                    ("飛行 Flying",    "★ 是 Yes / 可擊空"),
                ],
                "atk":   "穿甲 Piercing",
                "armor": "重甲 Heavy",
                "desc":  "飛行砲艦，可空對空作戰。\nGunship, air-to-air capable.",
                "built": "航空機場 Starport",
            },
        ]

        for idx, card in enumerate(_FED_UNITS):
            col = idx % COLS
            row = idx // COLS
            cx  = MARGIN_X + col * (CARD_W + GAP_X)
            cy  = MARGIN_TOP + row * (CARD_H + GAP_Y)
            accent = card["accent"]

            # Card background
            bg_surf = self._get_surf(f"enc_card_{idx}", (CARD_W, CARD_H))
            bg_surf.fill((16, 22, 44, 230))
            screen.blit(bg_surf, (cx, cy))

            # Top accent bar
            pygame.draw.rect(screen, accent, (cx, cy, CARD_W, 6))
            # Border
            border_col = (accent[0]//4, accent[1]//4, accent[2]//4)
            pygame.draw.rect(screen, border_col, (cx, cy, CARD_W, CARD_H), 2)

            # ── Left unit sprite (or fallback icon circle) ────────────────────
            IC_X, IC_Y, IC_R = cx + 48, cy + 56, 34
            _sprite_drawn = False
            if self._assets is not None:
                try:
                    _unit_surf = self._assets.get(card["kind"], scale=(72, 72))
                    _sr = _unit_surf.get_rect(center=(IC_X, IC_Y))
                    screen.blit(_unit_surf, _sr)
                    _sprite_drawn = True
                except Exception:
                    pass
            if not _sprite_drawn:
                pygame.draw.circle(screen, accent, (IC_X, IC_Y), IC_R)
                pygame.draw.circle(screen, (10, 14, 26), (IC_X, IC_Y), IC_R - 4)
                self._txt(screen, card["icon"], (IC_X - 12, IC_Y - 14), size=24, color=accent)

            # ── Unit name ─────────────────────────────────────────────────────
            self._txt_shd(screen, card["label"], (cx + 94, cy + 22), 34, accent)
            self._txt(screen, card["zh"],         (cx + 94, cy + 62), size=22,
                      color=(160, 185, 220))

            # ── Type badges ───────────────────────────────────────────────────
            badge_y = cy + 96
            for bi, (btxt, bcol) in enumerate([
                (f"攻 {card['atk']}",   (accent[0]//2+60, accent[1]//2+60, accent[2]//2+60)),
                (f"甲 {card['armor']}", (60, 80, 110)),
            ]):
                bx = cx + 94 + bi * 230
                pygame.draw.rect(screen, (20, 28, 55), (bx, badge_y, 210, 28), border_radius=4)
                self._txt(screen, btxt, (bx + 6, badge_y + 4), size=17, color=bcol)

            # Divider
            div_y = cy + 132
            pygame.draw.line(screen, (*accent, 80),
                             (cx + 12, div_y), (cx + CARD_W - 12, div_y), 1)

            # ── Stats rows ────────────────────────────────────────────────────
            row_h = (CARD_H - 148 - 52) // 6   # distribute remaining height over 6 rows
            for ri, (sname, sval) in enumerate(card["stats"]):
                ry  = div_y + 8 + ri * row_h
                rbg = (22, 30, 56) if ri % 2 == 0 else (16, 22, 44)
                pygame.draw.rect(screen, rbg, (cx + 8, ry, CARD_W - 16, row_h - 2))
                self._txt(screen, sname, (cx + 14, ry + 4), size=18,
                          color=(110, 140, 185))
                self._txt(screen, sval,  (cx + CARD_W // 2, ry + 4), size=18,
                          color=(210, 225, 255))

            # ── Description ───────────────────────────────────────────────────
            desc_y = cy + CARD_H - 52
            pygame.draw.line(screen, (30, 42, 80),
                             (cx + 12, desc_y - 4), (cx + CARD_W - 12, desc_y - 4), 1)
            for li, dline in enumerate(card["desc"].split("\n")):
                self._txt(screen, dline,
                          (cx + 12, desc_y + li * 24), size=17,
                          color=(90, 115, 160))

        # ── Back button ───────────────────────────────────────────────────────
        btn_w, btn_h = 300, 68
        btn_x = (W - btn_w) // 2
        btn_y = H - 88
        pygame.draw.rect(screen, (22, 36, 80),  (btn_x, btn_y, btn_w, btn_h), border_radius=12)
        pygame.draw.rect(screen, (60, 110, 200), (btn_x, btn_y, btn_w, btn_h), 2, border_radius=12)
        self._txt_shd(screen, "← 返回  Back", (btn_x + 42, btn_y + 16), 28, (140, 200, 255))
        self._unit_info_back_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

    def unit_info_hit_test(self, mx: int, my: int) -> bool:
        """
        Returns True if the Back button was clicked (caller navigates away).
        Also handles tab switching internally (returns False so screen stays).
        """
        # Tab: federation (already active, but still accept click)
        if getattr(self, "_fed_tab_rect", None) and \
                self._fed_tab_rect.collidepoint(mx, my):
            self.encyclopedia_tab = "federation"
            return False
        # Tab: unknown — grayed out / no-op for now
        if getattr(self, "_unknown_tab_rect", None) and \
                self._unknown_tab_rect.collidepoint(mx, my):
            # No-op: unknown faction not yet implemented
            return False
        # Back button
        r = getattr(self, "_unit_info_back_rect", None)
        return bool(r and r.collidepoint(mx, my))

    # ──────────────────────────────────────────────────────────────────────────
    # FACTION SELECT SCREEN
    # ──────────────────────────────────────────────────────────────────────────

    def draw_faction_select(
        self,
        screen: pygame.Surface,
        selected_faction: str,
        pending_mode: str = "1v1",
    ) -> None:
        """
        Full-screen faction selection — two side-by-side faction cards.

        Layout
        ------
        • Dark starfield background
        • Title + mode badge at top
        • LEFT  card: Star Federation (blue/silver)
        • RIGHT card: The Swarm      (purple/green)
        • Selected card has neon accent border + checkmark badge
        • 返回 BACK (bottom-left)  |  確認出擊 LAUNCH (bottom-right, always lit)
        """
        W, H = screen.get_width(), screen.get_height()
        screen.fill((8, 12, 24))

        # Subtle deterministic star field
        for i in range(100):
            sx = (i * 137 + 42) % W
            sy = (i * 97  + 11) % (H - 200)
            br = 60 + (i * 31) % 100
            pygame.draw.circle(screen, (br,) * 3, (sx, sy), 1)

        # ── Title ─────────────────────────────────────────────────────────────
        self._txt_shd(screen, "選擇陣營", (W // 2 - 160, 28), 56, (0, 220, 255))
        self._txt(screen, "SELECT YOUR FACTION",
                  (W // 2 - 200, 96), size=30, color=(40, 140, 180))

        # Mode badge
        badge_surf = self._safe_render(self._font(26),
                                       f"MODE:  {pending_mode.upper()}", True, (0, 220, 255))
        bw = badge_surf.get_width() + 32
        bx, by = W // 2 - bw // 2, 140
        pygame.draw.rect(screen, (0, 40, 60),   (bx, by, bw, 44), border_radius=8)
        pygame.draw.rect(screen, (0, 140, 180), (bx, by, bw, 44), 2, border_radius=8)
        screen.blit(badge_surf, (bx + 16, by + 9))

        # ── Card geometry — two cards, 50 px gap ──────────────────────────────
        CARD_W, CARD_H = 580, 460
        GAP   = 50
        TOTAL = CARD_W * 2 + GAP
        LEFT_X  = (W - TOTAL) // 2
        RIGHT_X = LEFT_X + CARD_W + GAP
        CARD_Y  = 208

        def _draw_faction_card(
            cx: int, cy: int, cw: int, ch: int,
            is_sel: bool,
            emblem_glyph: str,
            emblem_bg: tuple,
            accent:    tuple,
            dim:       tuple,
            title_cn:  str,
            title_en:  str,
            tag:       str,
            desc_lines: list[tuple[str, tuple]],
        ) -> None:
            border_col = accent if is_sel else dim
            glow_col   = emblem_bg

            # Glow aura
            if is_sel:
                for mg in (14, 9, 4):
                    av = 20 * (4 - mg // 4)
                    gs = self._get_surf(f"fac_glow_{tag}_{mg}",
                                        (cw + mg*2, ch + mg*2))
                    gs.fill((*accent[:3], av))
                    screen.blit(gs, (cx - mg, cy - mg))

            # Card bg
            cb = self._get_surf(f"fac_card_{tag}", (cw, ch))
            cb.fill((14, 20, 38, 240))
            screen.blit(cb, (cx, cy))

            # Accent top bar + border
            pygame.draw.rect(screen, border_col, (cx, cy, cw, 6))
            pygame.draw.rect(screen, border_col, (cx, cy, cw, ch), 2, border_radius=4)

            # Emblem
            emb_cx, emb_cy = cx + 110, cy + ch // 2 - 20
            pygame.draw.circle(screen, glow_col, (emb_cx, emb_cy), 80)
            pygame.draw.circle(screen, border_col, (emb_cx, emb_cy), 80, 3)
            self._txt_shd(screen, emblem_glyph,
                          (emb_cx - 38, emb_cy - 50), 72, border_col)

            # Faction name
            tc = accent if is_sel else (120, 140, 160)
            self._txt_shd(screen, title_cn, (cx + 220, cy + 50), 46, tc)
            self._txt(screen, title_en,
                      (cx + 220, cy + 108), size=26, color=(60, 160, 200) if is_sel else (50, 70, 90))

            # Divider
            pygame.draw.line(screen, (*border_col[:3], 80),
                             (cx + 216, cy + 152), (cx + cw - 28, cy + 152), 1)

            # Desc lines
            for li, (line, col) in enumerate(desc_lines):
                self._txt(screen, line, (cx + 220, cy + 166 + li * 40),
                          size=22, color=col)

            # Checkmark / selection badge
            if is_sel:
                ck_x, ck_y = cx + cw - 86, cy + 18
                pygame.draw.rect(screen, (0, 160, 70),
                                 (ck_x, ck_y, 72, 32), border_radius=6)
                self._txt(screen, "✓ 已選", (ck_x + 6, ck_y + 6),
                          size=18, color=(210, 255, 210))

        # ── Federation card (LEFT) ────────────────────────────────────────────
        _draw_faction_card(
            cx=LEFT_X, cy=CARD_Y, cw=CARD_W, ch=CARD_H,
            is_sel=(selected_faction == "federation"),
            emblem_glyph="★",
            emblem_bg=(0, 50, 100),
            accent=(0, 210, 255),
            dim=(45, 60, 80),
            title_cn="星際聯邦",
            title_en="Star Federation",
            tag="fed",
            desc_lines=[
                ("均衡重火力  正面推進擅長", (160, 190, 220)),
                ("Balanced heavy-assault faction.", (90, 120, 150)),
                ("", (0,0,0)),
                ("Marine  ·  HP100  ATK15  速度快", (90, 150, 190)),
                ("Tank    ·  HP250  ATK40  重裝甲", (90, 150, 190)),
                ("Turret  ·  防禦砲塔 ATK25 RNG300", (70, 130, 170)),
            ],
        )
        self._fac_fed_rect = pygame.Rect(LEFT_X, CARD_Y, CARD_W, CARD_H)

        # ── Swarm card (RIGHT) ────────────────────────────────────────────────
        _draw_faction_card(
            cx=RIGHT_X, cy=CARD_Y, cw=CARD_W, ch=CARD_H,
            is_sel=(selected_faction == "swarm"),
            emblem_glyph="⬡",
            emblem_bg=(40, 8, 60),
            accent=(140, 50, 220),
            dim=(55, 30, 75),
            title_cn="蟲群意志",
            title_en="The Swarm",
            tag="swarm",
            desc_lines=[
                ("酸液速攻  以量取勝策略", (180, 130, 220)),
                ("Acid-spitter swarm tactics.", (110, 70, 160)),
                ("", (0,0,0)),
                ("Crawler ·  HP40  ATK15  近戰快攻", (120, 80, 180)),
                ("Spitter ·  HP60  ATK20  酸液彈射", (120, 80, 180)),
                ("Acid Pool · 60%爬蟲/40%吐液", (100, 60, 150)),
            ],
        )
        self._fac_swarm_rect = pygame.Rect(RIGHT_X, CARD_Y, CARD_W, CARD_H)

        # ── Bottom buttons ────────────────────────────────────────────────────
        BTN_Y   = CARD_Y + CARD_H + 44
        BTN_H   = 80
        BACK_W  = 280
        START_W = 400

        # 返回 BACK
        back_x = LEFT_X
        pygame.draw.rect(screen, (22, 30, 50),
                         (back_x, BTN_Y, BACK_W, BTN_H), border_radius=14)
        pygame.draw.rect(screen, (60, 80, 120),
                         (back_x, BTN_Y, BACK_W, BTN_H), 2, border_radius=14)
        self._txt_shd(screen, "← 返回  BACK",
                      (back_x + 40, BTN_Y + 22), 28, (120, 150, 200))
        self._fac_back_rect = pygame.Rect(back_x, BTN_Y, BACK_W, BTN_H)

        # 確認出擊 LAUNCH — always lit (federation is default selection)
        start_x = RIGHT_X + CARD_W - START_W
        pygame.draw.rect(screen, (0, 50, 80),
                         (start_x, BTN_Y, START_W, BTN_H), border_radius=14)
        pygame.draw.rect(screen, (0, 200, 255),
                         (start_x, BTN_Y, START_W, BTN_H), 2, border_radius=14)
        self._txt_shd(screen, "確認出擊  LAUNCH  →",
                      (start_x + 36, BTN_Y + 22), 28, (0, 230, 255))
        self._fac_start_rect = pygame.Rect(start_x, BTN_Y, START_W, BTN_H)

    def faction_select_hit_test(
        self, mx: int, my: int
    ) -> Optional[str]:
        """
        Returns:
          "federation"  — Federation faction card clicked
          "swarm"       — Swarm faction card clicked
          "start"       — LAUNCH button clicked
          "back"        — BACK button clicked
          None          — no interactive element hit
        """
        if getattr(self, "_fac_fed_rect",   None) and self._fac_fed_rect.collidepoint(mx, my):
            return "federation"
        if getattr(self, "_fac_swarm_rect", None) and self._fac_swarm_rect.collidepoint(mx, my):
            return "swarm"
        if getattr(self, "_fac_start_rect", None) and self._fac_start_rect.collidepoint(mx, my):
            return "start"
        if getattr(self, "_fac_back_rect",  None) and self._fac_back_rect.collidepoint(mx, my):
            return "back"
        return None
