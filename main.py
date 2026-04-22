# ume_block = 0
"""
main.py — Star Raise  (v5: Phase 1 + Phase 2)

Phase 1 features (camera & world)
----------------------------------
  - 19.5:9 landscape screen  1280 × 590
  - 7× wide battlefield      8960 × 590
  - Camera: left-mouse drag scrolls horizontally; clamped to world bounds
  - Player 1× base (x 0–1280) contains two 4×4 building grids (Top / Bot lane)
  - Player HQ at world (80, 295)  |  Enemy HQ at world (8880, 295)
  - All world objects use camera_offset; HUD is always screen-fixed

Phase 2 features (auto-spawn & economy)
-----------------------------------------
  - Manual B/T queuing REMOVED; no ProductionQueue; no AIController
  - Slot buildings auto-spawn their unit_type when spawn_timer fires
  - Top-grid buildings  → units march along TOP_LANE_Y  (y ≈ 147)
  - Bottom-grid buildings → units march along BOT_LANE_Y (y ≈ 442)
  - Enemy HQ auto-spawns on both lanes at a fixed cadence
  - ResourceManager income = BASE (10) + Σ building.income_bonus per 5 s cycle
  - HUD shows income breakdown: base + bonus per building type

Lane paths (straight horizontal, two Y-coordinates)
------------------------------------------------------
  TOP_LANE_Y = SCREEN_H // 4   ≈ 147
  BOT_LANE_Y = 3*SCREEN_H // 4 ≈ 442

  Player units:  spawn_pos  →  (SCREEN_W+50, lane_y)  →  (WORLD_W-200, lane_y)
  Enemy  units:  spawn_pos  →  (WORLD_W-SCREEN_W-50, lane_y)  →  (200, lane_y)
"""

from __future__ import annotations

import asyncio
import math
import os
import random
import sys
import threading

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Web / desktop detection ───────────────────────────────────────────────────
_WEB: bool = sys.platform == "emscripten"

from src.asset_manager import AssetManager
from src.sprite        import Building, Unit, VFXSprite, Projectile
from src.battle        import BattleManager
from src.logic         import ResourceManager, BUILDING_SPECS, BASE_INCOME, BuildState, GameState
from src.ai            import AIController, AI_ALL_SLOTS
from src.ui_manager    import UIManager
from src.shared        import pop_actions
import src.shared as shared

# ── Screen / world constants ──────────────────────────────────────────────────
SCREEN_W = 2556
SCREEN_H = 1179
WORLD_W  = SCREEN_W * 9 // 2          # 11502
WORLD_H  = SCREEN_H                   # 1179
FPS      = 60
TITLE    = "Star Raise — v5 (Phase 2: Auto-Spawn)"

# ── Sandwich layout ──────────────────────────────────────────
HUD_H               = 140
DECK_H              = 180
WORLD_VIEWPORT_H    = SCREEN_H - HUD_H - DECK_H
SAFE_ZONE           = 132
HQ_W                = 400

# ── Building-slot layout ───────────────────────────────
SLOT_SIZE  = 84
SLOT_GAP   = 8
SLOT_STEP  = SLOT_SIZE + SLOT_GAP
GRID_COLS  = 4
GRID_ROWS  = 4
GRID_H     = GRID_ROWS * SLOT_SIZE + (GRID_ROWS - 1) * SLOT_GAP

GRID_ORIGIN_X    = SAFE_ZONE + HQ_W

_LANE_H          = WORLD_VIEWPORT_H // 2
_gPadY           = (_LANE_H - GRID_H) // 2
GRID_ORIGIN_Y_TOP = HUD_H + _gPadY
GRID_ORIGIN_Y_BOT = HUD_H + _LANE_H + _gPadY

# ── Lane Y-coordinates ───────────────────────────────
TOP_LANE_Y: int = HUD_H + _LANE_H // 2
BOT_LANE_Y: int = HUD_H + _LANE_H + _LANE_H // 2

def _make_slot_positions(origin_y: int) -> list[tuple[int, int]]:
    return [
        (GRID_ORIGIN_X + col * SLOT_STEP,
         origin_y       + row * SLOT_STEP)
        for row in range(GRID_ROWS)
        for col in range(GRID_COLS)
    ]

TOP_LANE_SLOTS: list[tuple[int, int]] = _make_slot_positions(GRID_ORIGIN_Y_TOP)
BOT_LANE_SLOTS: list[tuple[int, int]] = _make_slot_positions(GRID_ORIGIN_Y_BOT)
ALL_SLOTS:      list[tuple[int, int]] = TOP_LANE_SLOTS + BOT_LANE_SLOTS

# ── Font loader ───────────────────────────────────────────────────────────────
def _load_font(size: int) -> pygame.font.Font:
    for loader in (
        lambda: pygame.font.Font("assets/fonts/NotoSansTC.ttf", size),
        lambda: pygame.font.SysFont("Arial", max(size, 8)),
        lambda: pygame.font.Font(None, max(size, 8)),
    ):
        try:
            f = loader()
            if f is not None:
                return f
        except Exception:
            continue
    return pygame.font.Font(None, 12)

def _safe_render_text(
    font,
    text: str,
    antialias: bool,
    color: tuple,
    background=None,
) -> "pygame.Surface":
    try:
        surf = (font.render(text, antialias, color, background)
                if background else font.render(text, antialias, color))
        return surf
    except Exception as e:
        print(f"Font render failed: {e}")
        return pygame.Surface((1, 1), pygame.SRCALPHA)

# ── API ───────────────────────────────────────────────────────────────────────
API_PORT = int(os.environ.get("PORT", 8000))

# ── Colours ───────────────────────────────────────────────────────────────────
COLOR_BG        = (18,  22,  36)
COLOR_GRID      = (28,  34,  50)
COLOR_TEXT      = (200, 220, 255)
COLOR_GOLD      = (255, 200,  30)
COLOR_WARN      = (255,  80,  80)
COLOR_OK        = ( 80, 220, 120)
COLOR_LANE_DIV  = ( 40,  60, 100)
COLOR_ZONE_DIV  = ( 80,  50, 140)
COLOR_SLOT_FILL = ( 40,  80, 140,  60)
COLOR_SLOT_EDGE = (100, 160, 220)
COLOR_VICTORY   = ( 60, 220, 100)
COLOR_DEFEAT    = (220,  60,  60)
COLOR_TOP_LANE  = ( 80, 160, 255)
COLOR_BOT_LANE  = (255, 160,  60)

# ── Command-Deck card layout ─────────────────────────
DECK_Y  = SCREEN_H - DECK_H
CARD_W  = 190
CARD_H  = 150
_CARD_Y_IN_DECK = (DECK_H - CARD_H) // 2
CARD_Y  = DECK_Y + _CARD_Y_IN_DECK

CARD_KINDS = [
    "barracks", "refinery", "rover_bay", "spec_ops",
    "heavy_factory", "starport", None, "turret", "nuke",
]

_CARD_X0    = SAFE_ZONE + 20
_CARD_STEP  = CARD_W + 14
_DEMO_X     = _CARD_X0 + 6 * _CARD_STEP + 18
_TURRET_X   = 1544
_NUKE_W     = 194
_NUKE_H     = CARD_H + 22
_NUKE_X     = SCREEN_W - SAFE_ZONE - 206
_NUKE_Y     = DECK_Y + (DECK_H - _NUKE_H) // 2

CARD_RECTS: list[pygame.Rect] = [
    pygame.Rect(_CARD_X0 + 0 * _CARD_STEP, CARD_Y,  CARD_W, CARD_H),
    pygame.Rect(_CARD_X0 + 1 * _CARD_STEP, CARD_Y,  CARD_W, CARD_H),
    pygame.Rect(_CARD_X0 + 2 * _CARD_STEP, CARD_Y,  CARD_W, CARD_H),
    pygame.Rect(_CARD_X0 + 3 * _CARD_STEP, CARD_Y,  CARD_W, CARD_H),
    pygame.Rect(_CARD_X0 + 4 * _CARD_STEP, CARD_Y,  CARD_W, CARD_H),
    pygame.Rect(_CARD_X0 + 5 * _CARD_STEP, CARD_Y,  CARD_W, CARD_H),
    pygame.Rect(_DEMO_X,                   CARD_Y,  116,    CARD_H),
    pygame.Rect(_TURRET_X,                 CARD_Y,  CARD_W, CARD_H),
    pygame.Rect(_NUKE_X,                   _NUKE_Y, _NUKE_W,_NUKE_H),
]

CARD_COSTS = {k: BUILDING_SPECS[k]["cost"] for k in BUILDING_SPECS}
SNAP_RADIUS = SLOT_STEP * 1.2

# ── Touch / mouse event helpers ───────────────────────────────────────────────
_gameloop_ref = None

def _get_gameloop():
    return _gameloop_ref

def _evt_pos(event) -> tuple[int, int]:
    # 手機版觸控 (FINGER)：永遠乘上最原始的邏輯解析度 (SCREEN_W / SCREEN_H)
    if event.type in (pygame.FINGERDOWN, pygame.FINGERUP, pygame.FINGERMOTION):
        return int(event.x * SCREEN_W), int(event.y * SCREEN_H)
    
    # 電腦版滑鼠 (MOUSE)：如果視窗有縮小，就把座標放大回原始比例
    mx, my = event.pos
    _gl = _get_gameloop()
    if _gl is not None and getattr(_gl, "_scale", 1.0) < 1.0:
        s = _gl._scale
        return int(mx / s), int(my / s)
    return event.pos

def _start_api() -> None:
    try:
        import uvicorn
        uvicorn.run("server:app", host="0.0.0.0", port=API_PORT,
                    log_level="warning", access_log=False)
    except Exception as e:
        print(f"[API] server failed to start: {e}")

def launch_api_thread() -> None:
    if _WEB:
        print("[API] Skipped — running in browser (WebAssembly)")
        return
    t = threading.Thread(target=_start_api, daemon=True, name="api-server")
    t.start()
    print(f"[API] FastAPI at http://localhost:{API_PORT}")

# ── Camera ────────────────────────────────────────────────────────────────────
class Camera:
    DRAG_THRESHOLD = 4

    def __init__(self) -> None:
        self.cam_x: float = 0.0
        self._drag_active:   bool  = False
        self._drag_start_mx: int   = 0
        self._drag_start_cx: float = 0.0

    def on_mouse_down(self, mx: int) -> None:
        self._drag_active   = True
        self._drag_start_mx = mx
        self._drag_start_cx = self.cam_x

    def on_mouse_move(self, mx: int) -> None:
        if not self._drag_active:
            return
        self.cam_x = self._drag_start_cx - (mx - self._drag_start_mx)
        self._clamp()

    def on_mouse_up(self) -> None:
        self._drag_active = False

    def was_dragged(self, mx: int) -> bool:
        return abs(mx - self._drag_start_mx) > self.DRAG_THRESHOLD

    def _clamp(self) -> None:
        self.cam_x = max(0.0, min(self.cam_x, float(WORLD_W - SCREEN_W)))

    @property
    def offset(self) -> tuple[int, int]:
        return (int(self.cam_x), 0)

    def screen_to_world(self, sx: int, sy: int) -> tuple[float, float]:
        return (sx + self.cam_x, float(sy))

# ── Unit factory ──────────────────────────────────────────────────────────────
def make_unit_for_lane(
    unit_type:   str,
    spawn_pos:   tuple[float, float],
    lane:        str,
    team:        int,
    manager:     AssetManager,
    march_right: bool | None = None,
    is_player:   bool        = False,
) -> Unit:
    if march_right is None:
        march_right = (team != 2)

    lane_y = TOP_LANE_Y if lane == "top" else BOT_LANE_Y
    unit   = Unit(unit_type, manager, pos=spawn_pos, team=team, is_player=is_player)

    if march_right:
        unit.set_waypoints([
            (SCREEN_W + 50,  lane_y),
            (WORLD_W - 200,  lane_y),
        ])
    else:
        unit.set_waypoints([
            (WORLD_W - SCREEN_W - 50, lane_y),
            (200,                     lane_y),
        ])
    return unit

# ── Draw helpers ──────────────────────────────────────────────────────────────
def draw_background(screen: pygame.Surface, cam_x: float) -> None:
    screen.fill(COLOR_BG)
    first_wx = (int(cam_x) // 64) * 64
    for wx in range(first_wx, int(cam_x) + SCREEN_W + 64, 64):
        sx = wx - int(cam_x)
        pygame.draw.line(screen, COLOR_GRID, (sx, 0), (sx, SCREEN_H))
    for y in range(0, SCREEN_H, 64):
        pygame.draw.line(screen, COLOR_GRID, (0, y), (SCREEN_W, y))
    for bwx in (SCREEN_W, WORLD_W - SCREEN_W):
        bsx = bwx - int(cam_x)
        if -2 <= bsx <= SCREEN_W + 2:
            pygame.draw.line(screen, COLOR_ZONE_DIV, (bsx, 0), (bsx, SCREEN_H), 2)
    pygame.draw.line(screen, COLOR_LANE_DIV, (0, SCREEN_H // 2), (SCREEN_W, SCREEN_H // 2), 1)
    for lane_y, col in ((TOP_LANE_Y, COLOR_TOP_LANE), (BOT_LANE_Y, COLOR_BOT_LANE)):
        pos = 0
        while pos < SCREEN_W:
            pygame.draw.line(screen, col, (pos, lane_y), (min(pos + 20, SCREEN_W), lane_y))
            pos += 30

def _dashed_hline(surf, color, x1, x2, y, dash=8, gap=4):
    pos = x1
    while pos < x2:
        end = min(pos + dash, x2)
        pygame.draw.line(surf, color, (pos, y), (end, y))
        pos += dash + gap

def _dashed_vline(surf, color, x, y1, y2, dash=8, gap=4):
    pos = y1
    while pos < y2:
        end = min(pos + dash, y2)
        pygame.draw.line(surf, color, (x, pos), (x, end))
        pos += dash + gap

def _dashed_rect(surf, color, x, y, w, h):
    _dashed_hline(surf, color, x, x + w, y)
    _dashed_hline(surf, color, x, x + w, y + h)
    _dashed_vline(surf, color, x, y, y + h)
    _dashed_vline(surf, color, x + w, y, y + h)

def draw_building_slots(
    screen:     pygame.Surface,
    cam_x:      float,
    slots:      list[tuple[int, int]],
    occupied:   set[int],
    slot_surf:  pygame.Surface,
) -> None:
    for idx, (wx, wy) in enumerate(slots):
        if idx in occupied:
            continue
        sx = wx - int(cam_x)
        if sx + SLOT_SIZE < 0 or sx > SCREEN_W:
            continue
        screen.blit(slot_surf, (sx, wy))
        lane_color = COLOR_TOP_LANE if idx < 16 else COLOR_BOT_LANE
        _dashed_rect(screen, lane_color, sx, wy, SLOT_SIZE, SLOT_SIZE)

# ── HUD ───────────────────────────────────────────────────────────────────────
def draw_hud(
    screen:          pygame.Surface,
    font:            pygame.font.Font,
    fps:             float,
    res:             ResourceManager,
    cam_x:           float,
    income_flash:    bool,
    slot_buildings:  list[Building],
) -> None:
    pygame.draw.rect(screen, (20, 28, 50), (0, 0, SCREEN_W, 28))
    pygame.draw.rect(screen, (50, 70, 110), (0, 0, SCREEN_W, 28), 1)

    mineral_col = COLOR_GOLD if income_flash else (200, 180, 80)
    alive = [b for b in slot_buildings if not b.is_dead]
    barracks_n = sum(1 for b in alive if b.kind == "barracks")
    refinery_n = sum(1 for b in alive if b.kind == "refinery")

    income_breakdown = f"Base {BASE_INCOME}"
    if barracks_n:
        income_breakdown += f" + {barracks_n}×Bar({barracks_n * BUILDING_SPECS['barracks']['income_bonus']})"
    if refinery_n:
        income_breakdown += f" + {refinery_n}×Ref({refinery_n * BUILDING_SPECS['refinery']['income_bonus']})"
    income_breakdown += f" = {res.income_per_cycle}/5s"

    minerals_txt = f"Minerals: {res.minerals}"
    screen.blit(_safe_render_text(font, minerals_txt,     True, mineral_col),      (8, 7))
    screen.blit(_safe_render_text(font, income_breakdown, True, (160, 200, 255)),  (200, 7))

    bar_x, bar_y, bar_w, bar_h = SCREEN_W - 180, 8, 170, 10
    pygame.draw.rect(screen, (40, 40, 70),  (bar_x, bar_y, bar_w, bar_h))
    pygame.draw.rect(screen, COLOR_GOLD,    (bar_x, bar_y, int(bar_w * res.cycle_progress), bar_h))
    pygame.draw.rect(screen, (120, 100, 40),(bar_x, bar_y, bar_w, bar_h), 1)
    screen.blit(_safe_render_text(font, f"{res.frames_to_next_cycle}f", True, (180, 160, 80)),
                (bar_x - 36, bar_y - 1))

    hint_col = (255, 200, 60)
    screen.blit(
        _safe_render_text(font, 
            f"FPS: {fps:.0f}   CAM: {cam_x:.0f} / {WORLD_W - SCREEN_W}   "
            f"Drag to scroll  |  1-6 build  |  D demolish  |  N nuke  |  RMB/ESC cancel  |  F1 debug  |  R reset",
            True, hint_col,
        ),
        (8, 32),
    )

def draw_build_cards(
    screen:         pygame.Surface,
    font:           pygame.font.Font,
    minerals:       int,
    build_state:    BuildState,
    ghost_kind:     str | None,
    nuke_available: bool = True,
) -> None:
    for i, rect in enumerate(CARD_RECTS):
        kind = CARD_KINDS[i]
        is_demolish = (kind is None)
        is_nuke     = (kind == "nuke")

        if is_demolish:
            active = (build_state == BuildState.DEMOLISHING)
            bg     = (160, 30, 30) if active else (60, 20, 20)
            border = (255, 80, 80) if active else (120, 60, 60)
            pygame.draw.rect(screen, bg,     rect)
            pygame.draw.rect(screen, border, rect, 2)
            label     = "DEMOLISH"
            label_col = (255, 100, 100) if active else (200, 120, 120)
            hint      = "[D key]"
            hint_col  = (160, 80, 80)
            screen.blit(_safe_render_text(font, label, True, label_col), (rect.x + 6, rect.y + 8))
            screen.blit(_safe_render_text(font, hint,  True, hint_col),  (rect.x + 6, rect.y + 26))

        elif is_nuke:
            active = (ghost_kind == "nuke" and build_state == BuildState.NUKING)
            bg     = (120, 20, 20) if active else (50, 12, 12)
            border = (255, 60, 60) if active else (
                (200, 80, 80) if nuke_available else (50, 40, 40)
            )
            pygame.draw.rect(screen, bg,     rect)
            pygame.draw.rect(screen, border, rect, 2)
            label     = "☢ NUKE"
            label_col = (255, 100, 80) if nuke_available else (80, 60, 60)
            hint      = "ARMED" if nuke_available else "EXPENDED"
            hint_col  = (255, 60, 60) if nuke_available else (80, 70, 70)
            note      = "300px AoE"
            note_col  = (160, 100, 100) if nuke_available else (60, 50, 50)
            screen.blit(_safe_render_text(font, label, True, label_col), (rect.x + 6, rect.y + 8))
            screen.blit(_safe_render_text(font, hint,  True, hint_col),  (rect.x + 6, rect.y + 26))
            screen.blit(_safe_render_text(font, note,  True, note_col),  (rect.x + 6, rect.y + 42))

        else:
            active     = (ghost_kind == kind and build_state == BuildState.CONSTRUCTING)
            cost       = CARD_COSTS[kind]
            affordable = (minerals >= cost)
            bg         = (40, 70, 50) if (active and affordable) else (25, 40, 60)
            border     = (80, 220, 120) if active else (
                (100, 160, 220) if affordable else (80, 60, 60)
            )
            pygame.draw.rect(screen, bg,     rect)
            pygame.draw.rect(screen, border, rect, 2)
            label     = kind.upper()
            label_col = (200, 230, 200) if affordable else (120, 100, 100)
            hint      = f"{cost} min"
            hint_col  = COLOR_GOLD if affordable else (200, 120, 60)
            unit      = BUILDING_SPECS[kind]["unit_type"]
            rate      = BUILDING_SPECS[kind]["spawn_rate_frames"] // 60
            if kind == "turret":
                spec3 = BUILDING_SPECS["turret"]
                stat_line = f"ATK {spec3['atk_dmg']}  RNG {spec3['scan_range']}px"
            elif unit:
                stat_line = f"→{unit} {rate}s"
            else:
                stat_line = ""
            screen.blit(_safe_render_text(font, label,     True, label_col),      (rect.x + 6, rect.y + 8))
            screen.blit(_safe_render_text(font, hint,      True, hint_col),       (rect.x + 6, rect.y + 26))
            if stat_line:
                screen.blit(_safe_render_text(font, stat_line, True, (120, 160, 200)), (rect.x + 6, rect.y + 42))

def draw_ghost(
    screen:       pygame.Surface,
    font:         pygame.font.Font,
    ghost_surf:   pygame.Surface | None,
    ghost_screen: tuple[int, int],
    snap_slot:    int | None,
    snap_valid:   bool,
    cam_x:        float,
) -> None:
    gx, gy = ghost_screen
    if snap_slot is not None:
        wx, wy = ALL_SLOTS[snap_slot]
        sx = wx - int(cam_x)
        col = (0, 220, 80, 90) if snap_valid else (220, 50, 50, 90)
        hi = pygame.Surface((SLOT_SIZE, SLOT_SIZE), pygame.SRCALPHA)
        hi.fill(col)
        screen.blit(hi, (sx, wy))
        border_col = (0, 255, 100) if snap_valid else (255, 60, 60)
        pygame.draw.rect(screen, border_col, (sx, wy, SLOT_SIZE, SLOT_SIZE), 2)
        label = "Place" if snap_valid else "Occupied"
        screen.blit(_safe_render_text(font, label, True, border_col), (sx + 2, wy - 14))

    if ghost_surf is not None:
        alpha_surf = ghost_surf.copy()
        alpha_surf.set_alpha(160)
        rect = alpha_surf.get_rect(center=(gx, gy))
        screen.blit(alpha_surf, rect)

def draw_nuke_ghost(
    screen:       pygame.Surface,
    font:         pygame.font.Font,
    ghost_screen: tuple[int, int],
) -> None:
    gx, gy = ghost_screen
    aoe = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    pygame.draw.circle(aoe, (220, 30, 30, 45), (gx, gy), 450)
    pygame.draw.circle(aoe, (255, 80, 60, 180), (gx, gy), 450, 2)
    screen.blit(aoe, (0, 0))

    for dx, dy in ((-24, 0), (24, 0), (0, -24), (0, 24)):
        pygame.draw.line(screen, (255, 60, 60), (gx, gy), (gx + dx, gy + dy), 2)
    pygame.draw.circle(screen, (255, 100, 80), (gx, gy), 9, 2)

    screen.blit(
        _safe_render_text(font, "☢ NUKE  (release to detonate)", True, (255, 80, 80)),
        (gx + 14, gy - 18),
    )

def draw_result_overlay(screen: pygame.Surface, result: GameState) -> None:
    is_win = (result == GameState.VICTORY)
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((10, 60, 10, 210) if is_win else (60, 10, 10, 210))
    screen.blit(overlay, (0, 0))

    banner_h = 110
    banner   = pygame.Surface((SCREEN_W, banner_h), pygame.SRCALPHA)
    banner.fill((30, 160, 30, 230) if is_win else (160, 30, 30, 230))
    screen.blit(banner, (0, SCREEN_H // 2 - banner_h // 2 - 10))

    color    = COLOR_VICTORY if is_win else COLOR_DEFEAT
    headline = "★  VICTORY  ★" if is_win else "✖  DEFEAT  ✖"
    font_xl  = _load_font(110)
    font_md  = _load_font(36)
    font_sm  = _load_font(24)

    s_head = _safe_render_text(font_xl, headline, True, color)
    screen.blit(s_head, s_head.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 2)))

    sub = "Enemy HQ destroyed!" if is_win else "Your HQ has fallen!"
    s_sub = _safe_render_text(font_md, sub, True, (230, 255, 230) if is_win else (255, 230, 230))
    screen.blit(s_sub, s_sub.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 62)))

    hint = "[ Press  R  or  F5  to Restart ]         [ ESC  to Quit ]"
    s_hint = _safe_render_text(font_sm, hint, True, (180, 220, 180) if is_win else (220, 180, 180))
    screen.blit(s_hint, s_hint.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 100)))

def draw_unit_cards(
    screen: pygame.Surface,
    font:   pygame.font.Font,
    units:  list[Unit],
) -> None:
    for group, x_base in [
        ([u for u in units if u.team == 0][:3], 8),
        ([u for u in units if u.team == 1][:3], SCREEN_W - 218),
    ]:
        for i, u in enumerate(group):
            y0   = 52 + i * 50
            card = pygame.Surface((210, 44), pygame.SRCALPHA)
            card.fill((0, 0, 0, 120))
            screen.blit(card, (x_base, y0))

            label = "[Player]" if u.team == 0 else "[Enemy]"
            col   = COLOR_OK if u.team == 0 else COLOR_WARN
            sym   = {"march": ">>", "combat": "x", "assault": "HQ", "dead": "--"}.get(u.state, "?")
            screen.blit(
                _safe_render_text(font, f"{label} {u.kind.upper()} [{sym}]", True, col),
                (x_base + 4, y0 + 4),
            )
            bar_w = 198
            ratio = max(0.0, u.hp / u.max_hp)
            bar_c = (0, 200, 80) if ratio > 0.5 else (220, 180, 0) if ratio > 0.25 else (220, 50, 50)
            pygame.draw.rect(screen, (80,  0, 0), (x_base + 4, y0 + 24, bar_w, 8))
            pygame.draw.rect(screen, bar_c,       (x_base + 4, y0 + 24, int(bar_w * ratio), 8))
            screen.blit(
                _safe_render_text(font, f"HP {u.hp}/{u.max_hp}", True, (180, 180, 220)),
                (x_base + 4, y0 + 33),
            )

# ── GameLoop ──────────────────────────────────────────────────────────────────
class GameLoop:
    def __init__(self) -> None:
        pygame.display.init()
        pygame.font.init()
        print("[boot] display ready")
        
        global _gameloop_ref
        _gameloop_ref = self
        
        # ── 針對網頁與電腦版進行不同的視窗設定 ──
        if _WEB:
            # 網頁版 (Pygbag)：給予最高原生解析度，讓瀏覽器負責完美縮放
            self._scale  = 1.0
            self._win_w  = SCREEN_W
            self._win_h  = SCREEN_H
            self._window = pygame.display.set_mode((SCREEN_W, SCREEN_H))
            self.screen  = self._window  # 直接畫在最高畫質的畫布上
        else:
            # 電腦版：如果螢幕太小，手動縮小視窗以免超出邊界
            _info        = pygame.display.Info()
            _max_w       = max(320, _info.current_w  - 60)
            _max_h       = max(240, _info.current_h  - 80)
            _scale       = min(_max_w / SCREEN_W, _max_h / SCREEN_H, 1.0)
            self._win_w  = max(1, int(SCREEN_W * _scale))
            self._win_h  = max(1, int(SCREEN_H * _scale))
            self._scale  = _scale
            self._window = pygame.display.set_mode((self._win_w, self._win_h))
            self.screen  = pygame.Surface((SCREEN_W, SCREEN_H))
            
        pygame.display.set_caption(TITLE)
        
        self.font      = _load_font(18)
        self.fps_clk   = pygame.time.Clock()
        self.frame     = 0
        self.play_time = 0.0
        self.camera    = Camera()

        self._slot_surf = pygame.Surface((SLOT_SIZE, SLOT_SIZE), pygame.SRCALPHA)
        self._slot_surf.fill(COLOR_SLOT_FILL)

        from src.ui_manager import UIManager
        self._UIManager = UIManager
        self.manager = AssetManager()

        launch_api_thread()

        self.game_mode:          str = "1v1"
        self.pending_game_mode:  str = "1v1"
        self.selected_faction:   str = "federation"
        self.ai_faction:         str = "federation"
        self.sfx_on:             bool      = True

    def _init_scene(self) -> None:
        self.vfx_list:    list[VFXSprite]   = []
        self.projectiles: list[Projectile]  = []
        self.units:       list[Unit]        = []
        self.frame                      = 0
        self.play_time                  = 0.0
        self.game_state:  GameState     = GameState.PLAYING
        self.debug_mode:  bool          = False

        self.player_kills:        int = 0
        self.buildings_placed:    int = 0
        self.total_income_earned: int = 0
        self.income_flash:float         = 0.0
        self.nuke_flash:        float                     = 0.0
        self.nuke_circle:       tuple[float,float] | None = None
        self.nuke_circle_timer: float                     = 0.0
        self.shake_timer:       float                     = 0.0
        self.shake_amp:         int                       = 0

        self.build_state: BuildState     = BuildState.NONE
        self.ghost_kind:  str | None     = None
        self.ghost_slot:  int | None     = None
        self.ghost_valid: bool           = False
        self.ghost_pos:   tuple[int,int] = (0, 0)
        self._ghost_surfs: dict[str, pygame.Surface] = {}
        for _kind in BUILDING_SPECS:
            _gs = pygame.Surface((SLOT_SIZE, SLOT_SIZE), pygame.SRCALPHA)
            _gs.fill(
                (100, 180, 255, 120) if _kind == "barracks" else (255, 160, 60, 120)
            )
            self._ghost_surfs[_kind] = _gs

        def spawn_vfx(pos: tuple[float, float]) -> None:
            self.vfx_list.append(VFXSprite(pos))
        self.spawn_vfx = spawn_vfx

        def spawn_projectile(
            from_pos: tuple[float, float],
            to_pos:   tuple[float, float],
            atk_type: str,
        ) -> None:
            self.projectiles.append(
                Projectile(from_pos, to_pos, atk_type)
            )
        self.spawn_projectile = spawn_projectile

        self.player_faction: str = self.selected_faction

        _HQ_KIND_BY_FACTION = {
            "swarm":    "swarm_hq",
            "rogue_ai": "rogue_hq",
        }
        _player_hq_kind = _HQ_KIND_BY_FACTION.get(self.player_faction, "hq")
        self.player_hq = Building(
            _player_hq_kind, self.manager,
            pos=(SAFE_ZONE + HQ_W // 2, HUD_H + WORLD_VIEWPORT_H // 2),
            hp=2500, team=0,
            lane="none", is_hq=True, is_player=True,
        )

        _enemy_hq_kind = _HQ_KIND_BY_FACTION.get(self.ai_faction, "hq")
        self.enemy_hq = Building(
            _enemy_hq_kind, self.manager,
            pos=(WORLD_W - SAFE_ZONE - HQ_W // 2,
                 HUD_H + WORLD_VIEWPORT_H // 2),
            hp=2500, team=2,
            lane="none", is_hq=True,
        )

        self.player_hq.on_hq_death = lambda _t: setattr(
            self, "game_state", GameState.DEFEAT
        )
        self.enemy_hq.on_hq_death  = lambda _t: setattr(
            self, "game_state", GameState.VICTORY
        )

        self.slot_buildings: list[Building] = []
        self._occupied_slots: set[int]      = set()
        self.res = ResourceManager(starting=150)
        self.ai_controllers: list[AIController] = []

        def _make_enemy_ctrl(slots, faction: str) -> AIController:
            return AIController(
                team=2, enemy_team=0,
                slots=slots, is_left=False,
                faction=faction,
            )

        if self.game_mode == "1v1":
            ctrl = _make_enemy_ctrl(AI_ALL_SLOTS, self.ai_faction)
            self.ai_controllers.append(ctrl)
        elif self.game_mode == "2v2":
            allied = AIController(
                team=1, enemy_team=2,
                slots=list(ALL_SLOTS), is_left=True,
                faction="federation",
            )
            self.ai_controllers.append(allied)
            enemy1 = _make_enemy_ctrl(AI_ALL_SLOTS[:16],
                                      random.choice(["federation", "swarm", "rogue_ai"]))
            enemy2 = _make_enemy_ctrl(AI_ALL_SLOTS[16:],
                                      random.choice(["federation", "swarm", "rogue_ai"]))
            self.ai_controllers.append(enemy1)
            self.ai_controllers.append(enemy2)

        print(f"[Scene] Reset.  Slot buildings: {len(self.slot_buildings)}  "
              f"Income: {self.res.income_per_cycle}/cycle")

    def _do_tap_begin(self, mx: int, my: int) -> None:
        self._tap_was_minimap = False

        if self.game_state == GameState.MAIN_MENU:
            hit = self.ui.main_menu_hit_test(mx, my)
            if hit == "1v1":
                self.pending_game_mode = "1v1"
                self.game_state = GameState.FACTION_SELECT
            elif hit == "2v2":
                self.pending_game_mode = "2v2"
                self.game_state = GameState.FACTION_SELECT
            elif hit == "pvp":
                self.ui.push_notif(
                    "P V P  多人對戰  敬請期待", mx, my, color=(0, 220, 180)
                )
            elif hit == "unit_info":
                self.game_state = GameState.UNIT_INFO
            elif hit == "settings":
                self.game_state = GameState.SETTINGS

        elif self.game_state == GameState.SETTINGS:
            hit = self.ui.settings_hit_test(mx, my)
            if hit == "sfx":
                self.sfx_on = not self.sfx_on
                self.ui.push_notif(
                    f"音效  {'ON ✓' if self.sfx_on else 'OFF'}", mx, my,
                    color=(0, 220, 120) if self.sfx_on else (180, 100, 100),
                )
            elif hit == "close":
                self.game_state = GameState.MAIN_MENU

        elif self.game_state == GameState.FACTION_SELECT:
            action = self.ui.faction_select_hit_test(mx, my)
            if action == "back":
                self.game_state = GameState.MAIN_MENU
            elif action in ("federation", "swarm", "rogue_ai"):
                self.selected_faction = action
            elif action == "start":
                self.ai_faction  = random.choice(["federation", "swarm", "rogue_ai"])
                self.game_mode   = self.pending_game_mode
                self._init_scene()

        elif self.game_state == GameState.UNIT_INFO:
            if self.ui.unit_info_hit_test(mx, my):
                self.game_state = GameState.MAIN_MENU

        elif self.game_state in (GameState.VICTORY, GameState.DEFEAT):
            hit = self.ui.result_hit_test(mx, my)
            if hit == "restart":
                self._init_scene()
            elif hit == "home":
                self.game_state = GameState.MAIN_MENU

        elif self.game_state == GameState.PLAYING:
            _mm_target = self.ui.handle_minimap_click(mx, my)
            if _mm_target is not None:
                target_cam_x, _target_cam_y = _mm_target
                self.camera.cam_x = max(
                    0.0, min(target_cam_x, float(WORLD_W - SCREEN_W))
                )
                self.camera.on_mouse_up()
                self._tap_was_minimap = True
                return

            _active_kinds, _active_rects = self.ui.get_card_layout(
                getattr(self, "player_faction", "federation")
            )
            for i, rect in enumerate(_active_rects):
                if rect.collidepoint(mx, my):
                    kind = _active_kinds[i]
                    if kind is None:
                        if self.build_state == BuildState.DEMOLISHING:
                            self.build_state = BuildState.NONE
                        else:
                            self.build_state = BuildState.DEMOLISHING
                            self.ghost_kind  = None
                    elif kind == "nuke":
                        if self.res.nuke_available:
                            self.build_state      = BuildState.NUKING
                            self.ghost_kind       = "nuke"
                            self.ghost_pos        = (mx, my)
                            self.ghost_slot       = None
                            self.ghost_valid      = True
                            self._nuke_just_armed = True
                    else:
                        cost = CARD_COSTS[kind]
                        if self.res.minerals >= cost:
                            self.build_state = BuildState.CONSTRUCTING
                            self.ghost_kind  = kind
                            self.ghost_pos   = (mx, my)
                            self.ghost_slot  = None
                            self.ghost_valid = False
                    break

    def _place_building(self, slot_idx: int, kind: str, team: int) -> Building:
        sx, sy = ALL_SLOTS[slot_idx]
        cx     = sx + SLOT_SIZE // 2
        cy     = sy + SLOT_SIZE // 2
        lane   = "top" if slot_idx < 16 else "bottom"
        b      = Building(kind, self.manager, pos=(cx, cy), team=team, lane=lane,
                          is_player=(team == 0))
        self.slot_buildings.append(b)
        self._occupied_slots.add(slot_idx)
        self.res.register_building(b)
        if team == 0:
            self.buildings_placed += 1
        return b

    @property
    def all_buildings(self) -> list[Building]:
        ai_blds: list[Building] = []
        for ctrl in self.ai_controllers:
            ai_blds.extend(ctrl.slot_buildings)
        return [self.player_hq, self.enemy_hq] + self.slot_buildings + ai_blds

    def _check_victory(self) -> None:
        if self.game_state != GameState.PLAYING:
            return
        if self.enemy_hq.is_dead:
            self.game_state = GameState.VICTORY
            shared.write({"game_result": "VICTORY"})
            print("[Game] VICTORY")
        elif self.player_hq.is_dead:
            self.game_state = GameState.DEFEAT
            shared.write({"game_result": "DEFEAT"})
            print("[Game] DEFEAT")

    def _push_state(self) -> None:
        shared.write({
            "frame":        self.frame,
            "game_result":  self.game_state.name,
            "minerals":     self.res.minerals,
            "income_base":  BASE_INCOME,
            "income_bonus": self.res.income_bonus,
            "income_rate":  self.res.income_per_cycle,
            "unit_count": sum(1 for u in self.units if not u.is_dead),
            "units": [
                {
                    "kind":   u.kind,
                    "team":   u.team,
                    "hp":     u.hp,
                    "max_hp": u.max_hp,
                    "state":  u.state,
                    "pos":    [round(u.pos[0], 1), round(u.pos[1], 1)],
                }
                for u in self.units if not u.is_dead
            ],
            "buildings": [
                {
                    "kind":         b.kind,
                    "team":         b.team,
                    "hp":           b.hp,
                    "max_hp":       b.max_hp,
                    "is_dead":      b.is_dead,
                    "is_hq":        b.is_hq,
                    "lane":         b.lane,
                    "income_bonus": b.income_bonus,
                    "spawn_progress": round(b.spawn_progress, 3),
                }
                for b in self.all_buildings
            ],
            "slot_buildings": len(self.slot_buildings),
        })

    def _find_nearest_slot(
        self, wx: float, wy: float
    ) -> tuple[int | None, bool]:
        best_idx  = None
        best_dist = float("inf")
        for idx, (sx, sy) in enumerate(ALL_SLOTS):
            cx = sx + SLOT_SIZE // 2
            cy = sy + SLOT_SIZE // 2
            d  = math.hypot(wx - cx, wy - cy)
            if d < best_dist:
                best_dist = d
                best_idx  = idx
        if best_dist > SNAP_RADIUS or best_idx is None:
            return None, False
        return best_idx, (best_idx not in self._occupied_slots)

    async def run(self) -> None:
        try:
            await self._run_inner()
        except Exception as _fatal_exc:
            import traceback as _tb
            _err = _tb.format_exc()
            print(f"FATAL: {_fatal_exc}\n{_err}")
            try:
                _fs = pygame.font.SysFont(None, 22)
                self.screen.fill((140, 0, 0))
                _y = 10
                for _line in _err.split("\n"):
                    _s = _fs.render(_line[:120], True, (255, 255, 255))
                    self.screen.blit(_s, (10, _y))
                    _y += 26
                    if _y > self.screen.get_height() - 30:
                        break
                pygame.display.flip()
            except Exception:
                pass
            while True:
                await asyncio.sleep(0.1)

    async def _run_inner(self) -> None:
        if sys.platform == "emscripten":
            import platform
            if not hasattr(platform, "_overlay_cleared"):
                platform._overlay_cleared = True
                platform.window.eval('''(function() {
                    var loader = document.getElementById('status');
                    var spinner = document.getElementById('spinner');
                    if(loader) loader.style.display = 'none';
                    if(spinner) spinner.style.display = 'none';
                    document.body.style.backgroundColor = 'black';
                })();''')

        self.screen.fill((0, 0, 0))
        pygame.display.flip()
        await asyncio.sleep(0)

        print("[boot] loading assets...")
        await self.manager.preload_all_async()
        print("[boot] assets ready")

        print("[boot] init scene...")
        self._init_scene()
        self.game_state = GameState.MAIN_MENU
        self.ui = self._UIManager(SCREEN_W, SCREEN_H, SLOT_SIZE, WORLD_W,
                                  asset_manager=self.manager)
        print("[boot] ui ready — entering loop")

        lmb_down     = False
        lmb_down_pos = (0, 0)
        running      = True
        _touch_down_ui_handled: bool = False

        while running:
            raw_ms = self.fps_clk.tick(FPS)
            dt     = min(raw_ms / 1000.0, 0.1)
            self.frame += 1
            fps = self.fps_clk.get_fps()

            for act in pop_actions():
                atype = act.get("type")
                if atype == "build":
                    slot = act.get("slot")
                    kind = act.get("kind")
                    if (slot is not None and kind in BUILDING_SPECS
                            and slot not in self._occupied_slots
                            and self.game_state.name == "PLAYING"):
                        cost = BUILDING_SPECS[kind]["cost"]
                        if self.res.spend(cost):
                            self._place_building(slot, kind, team=0)
                elif atype == "demolish":
                    slot = act.get("slot")
                    if slot is not None and slot in self._occupied_slots:
                        sx, sy = ALL_SLOTS[slot]
                        cx = sx + SLOT_SIZE // 2
                        cy = sy + SLOT_SIZE // 2
                        for b in self.slot_buildings:
                            if (not b.is_dead and not b.is_hq
                                    and abs(b.pos[0] - cx) < SLOT_SIZE // 2 + 4
                                    and abs(b.pos[1] - cy) < SLOT_SIZE // 2 + 4):
                                b.demolish(self.res, self.spawn_vfx)
                                self._occupied_slots.discard(slot)
                                break
                elif atype == "nuke":
                    if self.game_state.name == "PLAYING":
                        self.res.launch_nuke(
                            (act.get("x", 0), act.get("y", 0)),
                            self.units,
                            self.spawn_vfx,
                        )

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.game_state in (GameState.UNIT_INFO,
                                               GameState.FACTION_SELECT,
                                               GameState.SETTINGS):
                            self.game_state = GameState.MAIN_MENU
                        elif self.build_state != BuildState.NONE:
                            self.build_state = BuildState.NONE
                            self.ghost_kind  = None
                            self.ghost_slot  = None
                        else:
                            running = False
                    elif event.key in (pygame.K_r, pygame.K_F5):
                        self._init_scene()
                    elif event.key == pygame.K_d:
                        if self.build_state == BuildState.DEMOLISHING:
                            self.build_state = BuildState.NONE
                        else:
                            self.build_state = BuildState.DEMOLISHING
                            self.ghost_kind  = None
                    elif event.key == pygame.K_F1:
                        self.debug_mode = not self.debug_mode
                    elif (event.key == pygame.K_n
                            and self.game_state == GameState.PLAYING
                            and self.res.nuke_available):
                        self.build_state      = BuildState.NUKING
                        self.ghost_kind       = "nuke"
                        self.ghost_pos        = (SCREEN_W // 2, SCREEN_H // 2)
                        self.ghost_slot       = None
                        self.ghost_valid      = True
                        self._nuke_just_armed = True
                    elif self.game_state == GameState.PLAYING:
                        _num_key_map = {
                            pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2,
                            pygame.K_4: 3, pygame.K_5: 4, pygame.K_6: 5,
                        }
                        _card_idx = _num_key_map.get(event.key)
                        if _card_idx is not None:
                            _kinds, _ = self.ui.get_card_layout(
                                getattr(self, "player_faction", "federation")
                            )
                            if _card_idx < len(_kinds):
                                _kind = _kinds[_card_idx]
                                if _kind is not None and _kind != "nuke":
                                    _cost = CARD_COSTS.get(_kind, 0)
                                    if self.res.minerals >= _cost:
                                        self.build_state = BuildState.CONSTRUCTING
                                        self.ghost_kind  = _kind
                                        self.ghost_pos   = (SCREEN_W // 2, SCREEN_H // 2)
                                        self.ghost_slot  = None
                                        self.ghost_valid = False

                elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                    mx, my = _evt_pos(event)
                    btn    = 1 if event.type == pygame.FINGERDOWN else event.button
                    if btn == 1:
                        lmb_down     = True
                        lmb_down_pos = (mx, my)

                        _state_before = self.build_state
                        self._do_tap_begin(mx, my)

                        if event.type == pygame.FINGERDOWN:
                            _touch_down_ui_handled = True

                        if (self.build_state == BuildState.NONE
                                and _state_before == BuildState.NONE
                                and self.game_state == GameState.PLAYING
                                and not getattr(self, "_tap_was_minimap", False)):
                            self.camera.on_mouse_down(mx)

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    if self.build_state != BuildState.NONE:
                        self.build_state = BuildState.NONE
                        self.ghost_kind  = None
                        self.ghost_slot  = None
                    else:
                        wx, wy = self.camera.screen_to_world(mx, my)
                        if self.units:
                            u = self.units[0]
                            u.waypoints.clear()
                            u.move_to((wx, wy))

                elif event.type in (pygame.MOUSEMOTION, pygame.FINGERMOTION):
                    mx, my = _evt_pos(event)
                    if self.game_state == GameState.MAIN_MENU:
                        pass
                    elif self.build_state == BuildState.CONSTRUCTING:
                        self.ghost_pos = (mx, my)
                        wx, wy = self.camera.screen_to_world(mx, my)
                        self.ghost_slot, self.ghost_valid = self._find_nearest_slot(wx, wy)
                    elif self.build_state == BuildState.NUKING:
                        self.ghost_pos = (mx, my)
                    elif self.build_state == BuildState.DEMOLISHING:
                        wx, wy = self.camera.screen_to_world(mx, my)
                        snap_idx, _ = self._find_nearest_slot(wx, wy)
                        self.ghost_slot = snap_idx
                        self.ghost_pos  = (mx, my)
                    elif self.build_state == BuildState.NONE and lmb_down:
                        self.camera.on_mouse_move(mx)

                elif event.type in (pygame.MOUSEBUTTONUP, pygame.FINGERUP):
                    mx, my = _evt_pos(event)
                    btn    = 1 if event.type == pygame.FINGERUP else event.button
                    if btn == 1:
                        if getattr(self, "_tap_was_minimap", False):
                            self._tap_was_minimap = False
                            lmb_down               = False
                            _touch_down_ui_handled = False
                            continue

                        if event.type == pygame.FINGERUP and not _touch_down_ui_handled:
                            _build_before_fallback = self.build_state
                            self._do_tap_begin(mx, my)

                            if self.build_state in (BuildState.CONSTRUCTING,
                                                    BuildState.NUKING):
                                lmb_down               = False
                                _touch_down_ui_handled = False
                                continue

                        _touch_down_ui_handled = False

                        if self.game_state == GameState.MAIN_MENU:
                            lmb_down = False

                        elif self.build_state == BuildState.CONSTRUCTING:
                            if self.ghost_slot is None:
                                wx_up, wy_up = self.camera.screen_to_world(mx, my)
                                snap_idx, snap_ok = self._find_nearest_slot(wx_up, wy_up)
                                if snap_idx is not None:
                                    self.ghost_slot  = snap_idx
                                    self.ghost_valid = snap_ok

                            if self.ghost_slot is not None and self.ghost_valid:
                                cost = CARD_COSTS[self.ghost_kind]
                                if self.res.spend(cost):
                                    self._place_building(
                                        self.ghost_slot, self.ghost_kind, team=0
                                    )
                                    print(
                                        f"[Build] placed {self.ghost_kind} "
                                        f"at slot {self.ghost_slot}  "
                                        f"minerals={self.res.minerals}"
                                    )
                            self.build_state = BuildState.NONE
                            self.ghost_kind  = None
                            self.ghost_slot  = None

                        elif self.build_state == BuildState.NUKING:
                            if getattr(self, "_nuke_just_armed", False):
                                self._nuke_just_armed = False
                                lmb_down = False
                                continue
                            wx, wy = self.camera.screen_to_world(mx, my)
                            fired = self.res.launch_nuke(
                                (wx, wy),
                                self.units,
                                self.spawn_vfx,
                            )
                            if fired:
                                self.nuke_flash        = 1.5
                                self.shake_timer       = 0.5
                                self.shake_amp         = 10
                                self.nuke_circle       = (wx, wy)
                                self.nuke_circle_timer = 3.0
                            self.build_state = BuildState.NONE
                            self.ghost_kind  = None
                            self.ghost_slot  = None

                        elif self.build_state == BuildState.DEMOLISHING:
                            wx, wy = self.camera.screen_to_world(mx, my)
                            slot_idx, _ = self._find_nearest_slot(wx, wy)
                            if slot_idx is not None and slot_idx in self._occupied_slots:
                                sx, sy = ALL_SLOTS[slot_idx]
                                cx = sx + SLOT_SIZE // 2
                                cy = sy + SLOT_SIZE // 2
                                for b in self.slot_buildings:
                                    if (
                                        not b.is_dead
                                        and not b.is_hq
                                        and abs(b.pos[0] - cx) < SLOT_SIZE // 2 + 4
                                        and abs(b.pos[1] - cy) < SLOT_SIZE // 2 + 4
                                    ):
                                        b.demolish(self.res, self.spawn_vfx)
                                        self._occupied_slots.discard(slot_idx)
                                        print(
                                            f"[Demolish] slot {slot_idx}  "
                                            f"minerals={self.res.minerals}"
                                        )
                                        break
                        else:
                            self.camera.on_mouse_up()

                        lmb_down = False

            if self.game_state == GameState.PLAYING:
                self.play_time += dt

                if self.res.update(dt):
                    self.total_income_earned += self.res.income_per_cycle
                    self.income_flash = 0.5
                if self.income_flash > 0:
                    self.income_flash -= dt

                for b in self.slot_buildings:
                    result = b.update(
                        dt,
                        units=self.units,
                        projectile_callback=self.spawn_projectile,
                        vfx_callback=self.spawn_vfx,
                    )
                    if result:
                        unit_type, spawn_pos, lane = result
                        u = make_unit_for_lane(
                            unit_type, spawn_pos, lane, team=0,
                            manager=self.manager, is_player=True,
                        )
                        self.units.append(u)

                for _ctrl in self.ai_controllers:
                    _ctrl.res.update(dt)
                    for _ab in _ctrl.slot_buildings:
                        _ar = _ab.update(
                            dt,
                            units=self.units,
                            projectile_callback=self.spawn_projectile,
                            vfx_callback=self.spawn_vfx,
                        )
                        if _ar:
                            _au_type, _asp, _al = _ar
                            _au = make_unit_for_lane(
                                _au_type, _asp, _al,
                                team=_ctrl.team,
                                march_right=_ctrl.is_left,
                                manager=self.manager,
                            )
                            self.units.append(_au)

                    _my_hq  = self.player_hq if _ctrl.is_left else self.enemy_hq
                    _player_units = [
                        u for u in self.units if not u.is_dead and u.team == 0
                    ]
                    _nuke   = _ctrl.update(
                        play_time    = self.play_time,
                        units        = self.units,
                        manager      = self.manager,
                        my_hq        = _my_hq,
                        spawn_vfx    = self.spawn_vfx,
                        player_units = _player_units,
                    )
                    if _nuke and _ctrl.last_nuke_target:
                        self.nuke_flash        = 1.5
                        self.shake_timer       = 0.5
                        self.shake_amp         = 10
                        self.nuke_circle       = _ctrl.last_nuke_target
                        self.nuke_circle_timer = 3.0
                        print(f"[AI t{_ctrl.team}] Nuke VFX triggered")

                self.player_kills += sum(
                    1 for u in self.units if u.is_dead and u.team == 2
                )
                BattleManager.process_combat(
                    self.units,
                    self.spawn_vfx,
                    buildings=self.all_buildings,
                    dt=dt,
                    projectile_callback=self.spawn_projectile,
                )
                BattleManager.resolve_collisions(self.units)
                self.units = BattleManager.cleanup_dead(self.units)

                for _p in self.projectiles:
                    _p.update(dt)
                self.projectiles = [_p for _p in self.projectiles if not _p.is_done]

                self.vfx_list = BattleManager.update_vfx(self.vfx_list, dt=dt)
                self._check_victory()

            self._push_state()

            cam_x      = self.camera.cam_x
            cam_offset = self.camera.offset

            if self.shake_timer > 0:
                t          = min(1.0, self.shake_timer / 0.5)
                amp        = int(self.shake_amp * t)
                shake_dx   = int(amp * math.sin(self.frame * 1.7))
                shake_dy   = int(amp * math.cos(self.frame * 2.3))
                cam_offset = (cam_offset[0] + shake_dx, cam_offset[1] + shake_dy)
                self.shake_timer -= dt

            self.ui.update()
            snap = UIManager.make_snapshot(self)

            if self.game_state == GameState.MAIN_MENU:
                self.screen.fill((18, 22, 36))
                self.ui.draw_all(self.screen, snap)

            elif self.game_state == GameState.FACTION_SELECT:
                self.ui.draw_faction_select(
                    self.screen,
                    self.selected_faction,
                    self.pending_game_mode,
                )

            elif self.game_state == GameState.UNIT_INFO:
                self.ui.draw_unit_info(self.screen)

            elif self.game_state == GameState.SETTINGS:
                self.screen.fill((18, 22, 36))
                self.ui.draw_main_menu(self.screen)
                self.ui.draw_settings_overlay(self.screen, sfx_on=self.sfx_on)

            else:
                self.ui.draw_background(self.screen, snap.cam_x)
                self.ui.draw_building_slots(
                    self.screen, snap.cam_x, ALL_SLOTS, self._occupied_slots,
                    snap.build_state_name
                )

                _render_list = []
                _render_list.append(self.player_hq)
                _render_list.append(self.enemy_hq)
                _render_list.extend(self.slot_buildings)
                for _ctrl in self.ai_controllers:
                    _render_list.extend(_ctrl.slot_buildings)
                _render_list.extend(self.units)

                def _sort_key(obj):
                    try:
                        return obj.pos[1] + (obj.surface.get_height() * 0.5 if obj.surface else 0)
                    except Exception:
                        return obj.pos[1]
                _render_list.sort(key=_sort_key)

                for _obj in _render_list:
                    _obj.draw(self.screen, cam_offset)

                if self.debug_mode:
                    for u in self.units:
                        u.draw_debug(self.screen, cam_offset)

                for _proj in self.projectiles:
                    _proj.draw(self.screen, cam_offset)

                for vfx in self.vfx_list:
                    vfx.draw(self.screen, cam_offset)

                if self.nuke_flash > 0:
                    alpha = int(min(1.0, self.nuke_flash / 1.5) * 190)
                    flash_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                    flash_surf.fill((220, 20, 20, alpha))
                    self.screen.blit(flash_surf, (0, 0))
                    self.nuke_flash -= dt

                if self.nuke_circle is not None and self.nuke_circle_timer > 0:
                    wx_n, wy_n = self.nuke_circle
                    sx_n = int(wx_n) - int(cam_x)
                    sy_n = int(wy_n)
                    t    = min(1.0, self.nuke_circle_timer / 3.0)
                    radius = int(120 + (1.0 - t) * 280)
                    alpha  = int(t * 180)
                    _circ  = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
                    pygame.draw.circle(_circ, (255, 120, 20, alpha),
                                       (radius, radius), radius, 6)
                    self.screen.blit(_circ, (sx_n - radius, sy_n - radius))
                    self.nuke_circle_timer -= dt

                if self.build_state == BuildState.DEMOLISHING:
                    _demo_slot = getattr(self, "ghost_slot", None)
                    if _demo_slot is not None and _demo_slot in self._occupied_slots:
                        _demo_bld = next(
                            (b for b in self.slot_buildings
                             if not b.is_dead and
                             abs(b.pos[0] - (ALL_SLOTS[_demo_slot][0] + SLOT_SIZE // 2)) < 5),
                            None,
                        )
                        _wx_d, _wy_d = ALL_SLOTS[_demo_slot]
                        _sx_d = _wx_d - int(cam_x)
                        _demo_surf = pygame.Surface((SLOT_SIZE, SLOT_SIZE), pygame.SRCALPHA)
                        _demo_surf.fill((220, 40, 40, 110))
                        pygame.draw.rect(_demo_surf, (255, 60, 60), (0, 0, SLOT_SIZE, SLOT_SIZE), 3)
                        self.screen.blit(_demo_surf, (_sx_d, _wy_d))
                        if _demo_bld is not None:
                            _refund = int(BUILDING_SPECS[_demo_bld.kind]["cost"] * 0.6)
                            _label  = self.font.render(f"+{_refund}", True, (255, 220, 80))
                            self.screen.blit(
                                _label,
                                (_sx_d + SLOT_SIZE // 2 - _label.get_width() // 2,
                                 _wy_d + SLOT_SIZE // 2 - _label.get_height() // 2),
                            )
                self.ui.draw_all(self.screen, snap)

            # ── Scale logical canvas → real window, then flip ─────────────────
            if not _WEB:
                if self._scale < 1.0:
                    scaled = pygame.transform.scale(self.screen, (self._win_w, self._win_h))
                    self._window.blit(scaled, (0, 0))
                else:
                    self._window.blit(self.screen, (0, 0))
                    
            pygame.display.flip()
            await asyncio.sleep(0)

# ── Entry point ───────────────────────────────────────────────────────────────
asyncio.run(GameLoop().run())