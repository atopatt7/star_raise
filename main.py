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

import math
import os
import sys
import threading

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.asset_manager import AssetManager
from src.sprite        import Building, Unit, VFXSprite
from src.battle        import BattleManager
from src.logic         import ResourceManager, BUILDING_SPECS, BASE_INCOME, BuildState, GameState
from src.ai            import AIController, AI_ALL_SLOTS
from src.ui_manager import UIManager
from src.shared import pop_actions

import src.shared as shared

# ── Screen / world constants ──────────────────────────────────────────────────
SCREEN_W = 1280
SCREEN_H = int(SCREEN_W * 9 / 19.5)   # 590  (19.5:9 landscape)
WORLD_W  = SCREEN_W * 7               # 8960
WORLD_H  = SCREEN_H
FPS      = 60
TITLE    = "Star Raise — v5 (Phase 2: Auto-Spawn)"

# ── Lane Y-coordinates (horizontal march paths) ───────────────────────────────
# Top lane: upper quarter  /  Bot lane: lower quarter
TOP_LANE_Y: int = SCREEN_H // 4          # ≈ 147
BOT_LANE_Y: int = 3 * SCREEN_H // 4      # ≈ 442

# ── Building-slot layout (player 1× base zone) ───────────────────────────────
SLOT_SIZE  = 64
SLOT_GAP   = 8
SLOT_STEP  = SLOT_SIZE + SLOT_GAP   # 72
GRID_COLS  = 4
GRID_ROWS  = 4
GRID_H     = GRID_ROWS * SLOT_STEP - SLOT_GAP   # 280

GRID_ORIGIN_X    = 148               # clears Player HQ sprite (cx=80, w=96)
_LANE_H          = SCREEN_H // 2     # 295
_TOP_LANE_MID    = _LANE_H // 2      # 147  (= TOP_LANE_Y ✓)
_BOT_LANE_MID    = _LANE_H + _LANE_H // 2  # 442  (= BOT_LANE_Y ✓)
GRID_ORIGIN_Y_TOP = _TOP_LANE_MID - GRID_H // 2   #  7
GRID_ORIGIN_Y_BOT = _BOT_LANE_MID - GRID_H // 2   # 302


def _make_slot_positions(origin_y: int) -> list[tuple[int, int]]:
    """Return 16 world (x, y) top-left corners for a 4×4 grid."""
    return [
        (GRID_ORIGIN_X + col * SLOT_STEP,
         origin_y       + row * SLOT_STEP)
        for row in range(GRID_ROWS)
        for col in range(GRID_COLS)
    ]


TOP_LANE_SLOTS: list[tuple[int, int]] = _make_slot_positions(GRID_ORIGIN_Y_TOP)
BOT_LANE_SLOTS: list[tuple[int, int]] = _make_slot_positions(GRID_ORIGIN_Y_BOT)
ALL_SLOTS:      list[tuple[int, int]] = TOP_LANE_SLOTS + BOT_LANE_SLOTS   # 32

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

# ── Build-card layout (bottom HUD) ───────────────────────────────────────────
# Three screen-fixed rectangles at the bottom:
#   CARD_KINDS[0] → Barracks  (cost 100)
#   CARD_KINDS[1] → Refinery  (cost 200)
#   CARD_KINDS[2] → Demolish toggle button

CARD_W, CARD_H = 90, 58
CARD_Y         = SCREEN_H - CARD_H - 8
# Four build cards:  [0] Barracks  [1] Refinery  [2] Nuke  [3] Demolish
# Barracks + Refinery sit on the left; Nuke + Demolish sit on the right.
CARD_KINDS = ["barracks", "refinery", "nuke", None]   # None = demolish button

CARD_RECTS: list[pygame.Rect] = [
    pygame.Rect(10 + i * (CARD_W + 8), CARD_Y, CARD_W, CARD_H)
    for i in range(2)                      # [0] barracks   [1] refinery
]
CARD_RECTS.append(pygame.Rect(           # [2] nuke  — second card from right
    SCREEN_W - (CARD_W + 8) * 2 - 10, CARD_Y, CARD_W, CARD_H
))
CARD_RECTS.append(pygame.Rect(           # [3] demolish — far right
    SCREEN_W - CARD_W - 10, CARD_Y, CARD_W, CARD_H
))

CARD_COSTS = {
    "barracks": BUILDING_SPECS["barracks"]["cost"],   # 100
    "refinery": BUILDING_SPECS["refinery"]["cost"],   # 200
}

# Snap radius: ghost snaps to a slot when cursor world-centre is within this px
SNAP_RADIUS = SLOT_STEP * 1.2   # ≈ 86 px


# ── FastAPI background thread ─────────────────────────────────────────────────
def _start_api() -> None:
    try:
        import uvicorn
        uvicorn.run("server:app", host="0.0.0.0", port=API_PORT,
                    log_level="warning", access_log=False)
    except Exception as e:
        print(f"[API] server failed to start: {e}")


def launch_api_thread() -> None:
    t = threading.Thread(target=_start_api, daemon=True, name="api-server")
    t.start()
    print(f"[API] FastAPI at http://localhost:{API_PORT}")


# ── Camera ────────────────────────────────────────────────────────────────────
class Camera:
    """
    Horizontal-scroll camera over the 7× battlefield.

    cam_x = world-X of the viewport's left edge.
    offset = (cam_x, 0) → subtract from world pos before drawing.

    Scroll mechanic
    ---------------
    Left-mouse drag: cam_x moves opposite to mouse delta.
    Boundaries:  0  ≤  cam_x  ≤  WORLD_W − SCREEN_W  (= 7680)
    """

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
    unit_type:  str,
    spawn_pos:  tuple[float, float],
    lane:       str,
    team:       int,
    manager:    AssetManager,
) -> Unit:
    """
    Create a Unit and assign lane-appropriate waypoints.

    Lane path layout (straight horizontal lines)
    ---------------------------------------------
    lane_y = TOP_LANE_Y (147) or BOT_LANE_Y (442)

    Player (team 0):
      spawn_pos  →  align-point (SCREEN_W+50, lane_y)  →  (WORLD_W-200, lane_y)

    Enemy  (team 1):
      spawn_pos  →  align-point (WORLD_W-SCREEN_W-50, lane_y)  →  (200, lane_y)

    The intermediate "align-point" ensures the unit reaches its lane Y
    before marching horizontally, regardless of where the building sits
    within the player's 1× base zone.
    """
    lane_y  = TOP_LANE_Y if lane == "top" else BOT_LANE_Y
    unit    = Unit(unit_type, manager, pos=spawn_pos, team=team)

    if team == 0:
        unit.set_waypoints([
            (SCREEN_W + 50,  lane_y),   # exit player zone aligned with lane
            (WORLD_W - 200,  lane_y),   # near enemy HQ
        ])
    else:
        unit.set_waypoints([
            (WORLD_W - SCREEN_W - 50, lane_y),   # exit enemy zone
            (200,                     lane_y),   # near player HQ
        ])
    return unit


# ── Draw helpers ──────────────────────────────────────────────────────────────

def draw_background(screen: pygame.Surface, cam_x: float) -> None:
    """Scrolling world grid + zone boundaries + lane guides."""
    screen.fill(COLOR_BG)

    # Vertical grid lines (only those on-screen)
    first_wx = (int(cam_x) // 64) * 64
    for wx in range(first_wx, int(cam_x) + SCREEN_W + 64, 64):
        sx = wx - int(cam_x)
        pygame.draw.line(screen, COLOR_GRID, (sx, 0), (sx, SCREEN_H))

    # Horizontal grid lines
    for y in range(0, SCREEN_H, 64):
        pygame.draw.line(screen, COLOR_GRID, (0, y), (SCREEN_W, y))

    # Zone boundary lines (player | neutral | enemy)
    for bwx in (SCREEN_W, WORLD_W - SCREEN_W):
        bsx = bwx - int(cam_x)
        if -2 <= bsx <= SCREEN_W + 2:
            pygame.draw.line(screen, COLOR_ZONE_DIV, (bsx, 0), (bsx, SCREEN_H), 2)

    # Horizontal lane divider (screen midline)
    pygame.draw.line(screen, COLOR_LANE_DIV,
                     (0, SCREEN_H // 2), (SCREEN_W, SCREEN_H // 2), 1)

    # Lane Y guides (dashed horizontal lines showing march paths)
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
    occupied:   set[int],          # indices of occupied slots
    slot_surf:  pygame.Surface,
) -> None:
    """Draw empty slot placeholders (occupied slots show building sprite instead)."""
    for idx, (wx, wy) in enumerate(slots):
        if idx in occupied:
            continue                # building sprite drawn elsewhere
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
    """
    Fixed-to-screen HUD.  Two sections:

    Top bar (resource strip):
      Minerals  |  Income breakdown  |  Income cycle progress

    Info strip below:
      FPS  |  Camera position  |  hint line
    """
    # ── Top resource bar ──────────────────────────────────────────────────────
    pygame.draw.rect(screen, (20, 28, 50), (0, 0, SCREEN_W, 28))
    pygame.draw.rect(screen, (50, 70, 110), (0, 0, SCREEN_W, 28), 1)

    mineral_col = COLOR_GOLD if income_flash else (200, 180, 80)

    # Count alive buildings by type for income breakdown display
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
    screen.blit(font.render(minerals_txt,     True, mineral_col),      (8, 7))
    screen.blit(font.render(income_breakdown, True, (160, 200, 255)),  (200, 7))

    # Income cycle progress bar (right side of top bar)
    bar_x, bar_y, bar_w, bar_h = SCREEN_W - 180, 8, 170, 10
    pygame.draw.rect(screen, (40, 40, 70),  (bar_x, bar_y, bar_w, bar_h))
    pygame.draw.rect(screen, COLOR_GOLD,    (bar_x, bar_y, int(bar_w * res.cycle_progress), bar_h))
    pygame.draw.rect(screen, (120, 100, 40),(bar_x, bar_y, bar_w, bar_h), 1)
    screen.blit(font.render(f"{res.frames_to_next_cycle}f", True, (180, 160, 80)),
                (bar_x - 36, bar_y - 1))

    # ── Info / hint strip ────────────────────────────────────────────────────
    hint_col = (255, 200, 60)
    screen.blit(
        font.render(
            f"FPS: {fps:.0f}   CAM: {cam_x:.0f} / {WORLD_W - SCREEN_W}   "
            f"Drag to scroll  |  D demolish  |  RMB/ESC cancel  |  F1 debug  |  R reset  |  ESC quit",
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
    """
    Bottom HUD — four build cards:
      [Barracks 100]  [Refinery 200]        [NUKE]  [DEMOLISH]

    Visual states:
      - Active card (being dragged/selected):  bright border + lighter bg
      - Demolish / Nuke ON:                    coloured bg
      - Insufficient minerals / nuke expended: dimmed label
    """
    for i, rect in enumerate(CARD_RECTS):
        kind = CARD_KINDS[i]
        is_demolish = (kind is None)
        is_nuke     = (kind == "nuke")

        # ── Demolish card ──────────────────────────────────────────────────
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
            screen.blit(font.render(label, True, label_col), (rect.x + 6, rect.y + 8))
            screen.blit(font.render(hint,  True, hint_col),  (rect.x + 6, rect.y + 26))

        # ── Nuke card ──────────────────────────────────────────────────────
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
            screen.blit(font.render(label, True, label_col), (rect.x + 6, rect.y + 8))
            screen.blit(font.render(hint,  True, hint_col),  (rect.x + 6, rect.y + 26))
            screen.blit(font.render(note,  True, note_col),  (rect.x + 6, rect.y + 42))

        # ── Building card (barracks / refinery) ────────────────────────────
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
            screen.blit(font.render(label,              True, label_col),      (rect.x + 6, rect.y + 8))
            screen.blit(font.render(hint,               True, hint_col),       (rect.x + 6, rect.y + 26))
            screen.blit(font.render(f"→{unit} {rate}s", True, (120, 160, 200)),(rect.x + 6, rect.y + 42))


def draw_ghost(
    screen:       pygame.Surface,
    font:         pygame.font.Font,
    ghost_surf:   pygame.Surface | None,
    ghost_screen: tuple[int, int],
    snap_slot:    int | None,
    snap_valid:   bool,
    cam_x:        float,
) -> None:
    """
    Render the ghost building sprite following the cursor during CONSTRUCTING.

    - Ghost sprite: 50 % alpha at cursor position.
    - Slot overlay: green (valid) or red (occupied/invalid) transparent rect
      drawn at the snapped slot's world-to-screen position.
    """
    gx, gy = ghost_screen

    # Slot highlight
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
        screen.blit(font.render(label, True, border_col), (sx + 2, wy - 14))

    # Ghost sprite
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
    """
    Nuke-targeting cursor: crosshair + translucent 300 px AoE circle.
    Drawn during BuildState.NUKING so the player can see blast coverage.
    """
    gx, gy = ghost_screen

    # Semi-transparent AoE fill
    aoe = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    pygame.draw.circle(aoe, (220, 30, 30, 45), (gx, gy), 450)
    pygame.draw.circle(aoe, (255, 80, 60, 180), (gx, gy), 450, 2)
    screen.blit(aoe, (0, 0))

    # Crosshair lines
    for dx, dy in ((-24, 0), (24, 0), (0, -24), (0, 24)):
        pygame.draw.line(screen, (255, 60, 60),
                         (gx, gy), (gx + dx, gy + dy), 2)
    pygame.draw.circle(screen, (255, 100, 80), (gx, gy), 9, 2)

    # Label
    screen.blit(
        font.render("☢ NUKE  (release to detonate)", True, (255, 80, 80)),
        (gx + 14, gy - 18),
    )


def draw_result_overlay(screen: pygame.Surface, result: GameState) -> None:
    """
    High-contrast full-screen end-game overlay.
    Completely replaces HUD — minerals/cards are intentionally hidden.
    Player restarts by pressing R (handled in run() event loop).
    """
    is_win = (result == GameState.VICTORY)

    # ── Full-screen dim ───────────────────────────────────────────────────────
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((10, 60, 10, 210) if is_win else (60, 10, 10, 210))
    screen.blit(overlay, (0, 0))

    # ── Bright banner strip ───────────────────────────────────────────────────
    banner_h = 110
    banner   = pygame.Surface((SCREEN_W, banner_h), pygame.SRCALPHA)
    banner.fill((30, 160, 30, 230) if is_win else (160, 30, 30, 230))
    screen.blit(banner, (0, SCREEN_H // 2 - banner_h // 2 - 10))

    # ── Main text ─────────────────────────────────────────────────────────────
    color    = COLOR_VICTORY if is_win else COLOR_DEFEAT
    headline = "★  VICTORY  ★" if is_win else "✖  DEFEAT  ✖"
    font_xl  = pygame.font.Font(None, 110)
    font_md  = pygame.font.Font(None, 36)
    font_sm  = pygame.font.Font(None, 24)

    s_head = font_xl.render(headline, True, color)
    screen.blit(s_head, s_head.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 2)))

    sub = "Enemy HQ destroyed!" if is_win else "Your HQ has fallen!"
    s_sub = font_md.render(sub, True, (230, 255, 230) if is_win else (255, 230, 230))
    screen.blit(s_sub, s_sub.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 62)))

    # ── Restart hint ──────────────────────────────────────────────────────────
    hint = "[ Press  R  to Restart ]         [ ESC  to Quit ]"
    s_hint = font_sm.render(hint, True, (180, 220, 180) if is_win else (220, 180, 180))
    screen.blit(s_hint, s_hint.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 100)))


def draw_unit_cards(
    screen: pygame.Surface,
    font:   pygame.font.Font,
    units:  list[Unit],
) -> None:
    """Compact unit status cards pinned to left (player) and right (enemy) sides."""
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
                font.render(f"{label} {u.kind.upper()} [{sym}]", True, col),
                (x_base + 4, y0 + 4),
            )
            # HP bar
            bar_w = 198
            ratio = max(0.0, u.hp / u.max_hp)
            bar_c = (0, 200, 80) if ratio > 0.5 else (220, 180, 0) if ratio > 0.25 else (220, 50, 50)
            pygame.draw.rect(screen, (80,  0, 0), (x_base + 4, y0 + 24, bar_w, 8))
            pygame.draw.rect(screen, bar_c,       (x_base + 4, y0 + 24, int(bar_w * ratio), 8))
            screen.blit(
                font.render(f"HP {u.hp}/{u.max_hp}", True, (180, 180, 220)),
                (x_base + 4, y0 + 33),
            )


# ── GameLoop ──────────────────────────────────────────────────────────────────
class GameLoop:

    # Pre-defined slot placements for demo (index into ALL_SLOTS, lane, kind)
    # Slot 0–15 = Top Lane,  Slot 16–31 = Bottom Lane
    _DEMO_BUILDINGS: list[tuple[int, str]] = [
        # (slot_index, kind)
        (0,  "barracks"),   # top-lane, col 0 row 0
        (1,  "barracks"),   # top-lane, col 1 row 0
        (4,  "refinery"),   # top-lane, col 0 row 1
        (16, "barracks"),   # bot-lane, col 0 row 0
        (17, "barracks"),   # bot-lane, col 1 row 0
        (20, "refinery"),   # bot-lane, col 0 row 1
    ]

    def __init__(self) -> None:
        pygame.init()
        self.screen  = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption(TITLE)
        self.font    = pygame.font.Font(None, 18)
        self.fps_clk = pygame.time.Clock()
        self.frame   = 0
        self.camera  = Camera()

        # Pre-create reusable slot placeholder surface
        self._slot_surf = pygame.Surface((SLOT_SIZE, SLOT_SIZE), pygame.SRCALPHA)
        self._slot_surf.fill(COLOR_SLOT_FILL)

        # Assets
        from src.ui_manager import UIManager
        self.manager = AssetManager()
        print("\n[Star Raise] Loading assets...")
        self.manager.preload_all()
        print("[Star Raise] Assets ready.\n")

        # API
        launch_api_thread()

        # Scene
        self._init_scene()
        self.ui = UIManager(SCREEN_W, SCREEN_H, SLOT_SIZE, WORLD_W)

    # ── Scene init (also used for R-reset) ───────────────────────────────────
    def _init_scene(self) -> None:
        self.vfx_list:  list[VFXSprite] = []
        self.units:     list[Unit]      = []
        self.frame                      = 0
        self.game_state:  GameState     = GameState.PLAYING
        self.debug_mode:  bool          = False
        self.income_flash:int           = 0
        # Nuke red-alert flash (counts down 90 → 0 after detonation)
        self.nuke_flash:        int                       = 0
        # Nuke blast circle (world pos + fade timer)
        self.nuke_circle:       tuple[float,float] | None = None
        self.nuke_circle_timer: int                       = 0
        # Screen shake — 30 frames = 0.5 s after nuke detonation
        self.shake_timer:       int                       = 0
        self.shake_amp:         int                       = 0

        # ── Phase 3: Build / demolish state ───────────────────────────────────
        self.build_state: BuildState     = BuildState.NONE
        self.ghost_kind:  str | None     = None
        self.ghost_slot:  int | None     = None
        self.ghost_valid: bool           = False
        self.ghost_pos:   tuple[int,int] = (0, 0)
        # Pre-render ghost surfaces (SLOT_SIZE × SLOT_SIZE coloured placeholder)
        self._ghost_surfs: dict[str, pygame.Surface] = {}
        for _kind in BUILDING_SPECS:
            _gs = pygame.Surface((SLOT_SIZE, SLOT_SIZE), pygame.SRCALPHA)
            _gs.fill(
                (100, 180, 255, 120) if _kind == "barracks" else (255, 160, 60, 120)
            )
            self._ghost_surfs[_kind] = _gs

        def spawn_vfx(pos: tuple[float, float]) -> None:
            self.vfx_list.append(
                VFXSprite("explosion_sheet", self.manager, pos, frame_delay=3)
            )
        self.spawn_vfx = spawn_vfx

        # ── Player HQ  (is_hq=True, victory condition) ────────────────────────
        # HP = 100,000  │  Armour DR = 70 %  (set by Building.__init__)
        self.player_hq = Building(
            "barracks", self.manager,
            pos=(80, WORLD_H // 2),
            hp=100_000, team=0,
            lane="none", is_hq=True,
        )

        # ── Enemy HQ  (is_hq=True) ─────────────────────────────────────────────
        self.enemy_hq = Building(
            "refinery", self.manager,
            pos=(WORLD_W - 80, WORLD_H // 2),
            hp=100_000, team=1,
            lane="none", is_hq=True,
        )

        # Phase 4: HQ death callbacks — transition game_state immediately
        # when a unit's attack_building() kills an HQ, without waiting for
        # the next _check_victory() frame poll.
        self.player_hq.on_hq_death = lambda _t: setattr(
            self, "game_state", GameState.DEFEAT
        )
        self.enemy_hq.on_hq_death  = lambda _t: setattr(
            self, "game_state", GameState.VICTORY
        )

        # ── Slot buildings (auto-spawn, income) ───────────────────────────────
        self.slot_buildings: list[Building] = []
        self._occupied_slots: set[int]      = set()

        # Economy — income driven by slot buildings
        self.res = ResourceManager(starting=150)

        # Place demo buildings from _DEMO_BUILDINGS table
        for slot_idx, kind in self._DEMO_BUILDINGS:
            self._place_building(slot_idx, kind, team=0)

        # ── Enemy auto-spawn state ─────────────────────────────────────────────
        # Enemy HQ spawns one unit per lane independently
        self._enemy_top_timer: int = 240   # stagger: top fires at t=240 first
        self._enemy_bot_timer: int = 0     # bot fires at t=480 first
        self._enemy_spawn_rate: int = 480  # 8 s @ 60 fps per lane

        # ── AI grid controller + economy (Phase 5) ────────────────────────────
        # AIController manages the enemy's 32 mirrored building slots.
        # self.ai_res is a SEPARATE ResourceManager — the AI earns its own
        # minerals independently of the player's self.res.
        self.ai_controller: AIController  = AIController()
        self.ai_res:        ResourceManager = ResourceManager(starting=150)

        print(f"[Scene] Reset.  Slot buildings: {len(self.slot_buildings)}  "
              f"Income: {self.res.income_per_cycle}/cycle")

    def _place_building(self, slot_idx: int, kind: str, team: int) -> Building:
        """
        Instantiate a building at the given ALL_SLOTS index and register it.
        Building centre = slot top-left + (SLOT_SIZE/2, SLOT_SIZE/2).
        """
        sx, sy = ALL_SLOTS[slot_idx]
        cx     = sx + SLOT_SIZE // 2
        cy     = sy + SLOT_SIZE // 2
        lane   = "top" if slot_idx < 16 else "bottom"
        b      = Building(kind, self.manager, pos=(cx, cy), team=team, lane=lane)
        self.slot_buildings.append(b)
        self._occupied_slots.add(slot_idx)
        self.res.register_building(b)
        return b

    # ── Properties ────────────────────────────────────────────────────────────
    @property
    def all_buildings(self) -> list[Building]:
        """All buildings: HQs + slot buildings (for BattleManager)."""
        return [self.player_hq, self.enemy_hq] + self.slot_buildings

    # ── Victory check ─────────────────────────────────────────────────────────
    def _check_victory(self) -> None:
        """
        Belt-and-suspenders poll each frame.
        The primary trigger is Building.on_hq_death callback (fires instantly
        inside Building.die()), so this only fires when the callback wasn't set
        (e.g. after a scene reset edge case) or as a safety net.
        """
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

    # ── Shared-state snapshot ─────────────────────────────────────────────────
    def _push_state(self) -> None:
        shared.write({
            "frame":        self.frame,
            "game_result":  self.game_state.name,

            # Economy
            "minerals":     self.res.minerals,
            "income_base":  BASE_INCOME,
            "income_bonus": self.res.income_bonus,
            "income_rate":  self.res.income_per_cycle,

            # Units
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

            # Buildings
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

            # Slot info
            "slot_buildings": len(self.slot_buildings),
        })

    # ── Slot finder ───────────────────────────────────────────────────────────
    def _find_nearest_slot(
        self, wx: float, wy: float
    ) -> tuple[int | None, bool]:
        """
        Return (slot_idx, is_valid) for the ALL_SLOTS entry nearest to
        world-pos (wx, wy) within SNAP_RADIUS.  is_valid=True means empty.
        Returns (None, False) if no slot is close enough.
        """
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

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self) -> None:
        lmb_down     = False
        lmb_down_pos = (0, 0)
        running      = True

        while running:
            self.fps_clk.tick(FPS)
            self.frame += 1
            fps = self.fps_clk.get_fps()

            # ── Process API actions ───────────────────────────────────────────

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
            # ── Events ────────────────────────────────────────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        # ESC cancels build/demolish mode first; second press quits
                        if self.build_state != BuildState.NONE:
                            self.build_state = BuildState.NONE
                            self.ghost_kind  = None
                            self.ghost_slot  = None
                        else:
                            running = False
                    elif event.key == pygame.K_r:
                        self._init_scene()
                    elif event.key == pygame.K_d:
                        # D key → toggle DEMOLISHING mode
                        if self.build_state == BuildState.DEMOLISHING:
                            self.build_state = BuildState.NONE
                        else:
                            self.build_state = BuildState.DEMOLISHING
                            self.ghost_kind  = None
                    elif event.key == pygame.K_F1:
                        self.debug_mode = not self.debug_mode

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if event.button == 1:
                        lmb_down     = True
                        lmb_down_pos = (mx, my)

                        # ── Card click detection ──────────────────────────────
                        card_clicked = False
                        for i, rect in enumerate(CARD_RECTS):
                            if rect.collidepoint(mx, my):
                                card_clicked = True
                                kind = CARD_KINDS[i]
                                if kind is None:
                                    # Demolish toggle button
                                    if self.build_state == BuildState.DEMOLISHING:
                                        self.build_state = BuildState.NONE
                                    else:
                                        self.build_state = BuildState.DEMOLISHING
                                        self.ghost_kind  = None
                                elif kind == "nuke":
                                    # Nuke card — enter NUKING if still available
                                    if self.res.nuke_available:
                                        self.build_state = BuildState.NUKING
                                        self.ghost_kind  = "nuke"
                                        self.ghost_pos   = (mx, my)
                                        self.ghost_slot  = None
                                        self.ghost_valid = True
                                else:
                                    # Building card — enter CONSTRUCTING if affordable
                                    cost = CARD_COSTS[kind]
                                    if self.res.minerals >= cost:
                                        self.build_state = BuildState.CONSTRUCTING
                                        self.ghost_kind  = kind
                                        self.ghost_pos   = (mx, my)
                                        self.ghost_slot  = None
                                        self.ghost_valid = False
                                break

                        if not card_clicked:
                            if self.build_state == BuildState.NONE:
                                # Normal camera drag start
                                self.camera.on_mouse_down(mx)

                    elif event.button == 3:
                        # RMB: cancel build/demolish; or move debug unit
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

                elif event.type == pygame.MOUSEMOTION:
                    mx, my = event.pos
                    if self.build_state == BuildState.CONSTRUCTING:
                        # Update ghost position and snap to nearest slot
                        self.ghost_pos = (mx, my)
                        wx, wy = self.camera.screen_to_world(mx, my)
                        self.ghost_slot, self.ghost_valid = self._find_nearest_slot(wx, wy)
                    elif self.build_state == BuildState.NUKING:
                        # Free-aim cursor — no slot snapping needed
                        self.ghost_pos = (mx, my)
                    elif self.build_state == BuildState.NONE and lmb_down:
                        self.camera.on_mouse_move(mx)

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        mx, my = event.pos

                        if self.build_state == BuildState.CONSTRUCTING:
                            # Place building if snapping to a valid empty slot
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
                            # Always exit constructing mode on mouse-up
                            self.build_state = BuildState.NONE
                            self.ghost_kind  = None
                            self.ghost_slot  = None

                        elif self.build_state == BuildState.NUKING:
                            # Detonate nuke at world cursor position
                            wx, wy = self.camera.screen_to_world(mx, my)
                            # Buildings list is intentionally NOT passed —
                            # this nuke is anti-unit only (see launch_nuke docstring)
                            fired = self.res.launch_nuke(
                                (wx, wy),
                                self.units,
                                self.spawn_vfx,
                            )
                            if fired:
                                # Red-alert flash (90 frames = 1.5 s)
                                self.nuke_flash        = 90
                                # Screen shake (30 frames = 0.5 s, ±10 px)
                                self.shake_timer       = 30
                                self.shake_amp         = 10
                                # Persistent blast circle (180 frames = 3 s)
                                self.nuke_circle       = (wx, wy)
                                self.nuke_circle_timer = 180
                            self.build_state = BuildState.NONE
                            self.ghost_kind  = None
                            self.ghost_slot  = None

                        elif self.build_state == BuildState.DEMOLISHING:
                            # Find slot building under cursor and demolish it
                            wx, wy = self.camera.screen_to_world(mx, my)
                            slot_idx, _ = self._find_nearest_slot(wx, wy)
                            if slot_idx is not None and slot_idx in self._occupied_slots:
                                # Find the Building sprite at that slot
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
                            # Stay in DEMOLISHING so player can keep clicking

                        else:
                            # Normal mode: click without drag spawns VFX
                            if not self.camera.was_dragged(mx):
                                wx, wy = self.camera.screen_to_world(mx, my)
                                self.spawn_vfx((wx, wy))
                            self.camera.on_mouse_up()

                        lmb_down = False

            # ── Game logic ────────────────────────────────────────────────────
            if self.game_state == GameState.PLAYING:

                # 1) Player income cycle
                if self.res.update():
                    self.income_flash = 30
                if self.income_flash > 0:
                    self.income_flash -= 1

                # 2) Slot buildings auto-spawn
                for b in self.slot_buildings:
                    result = b.update()
                    if result:
                        unit_type, spawn_pos, lane = result
                        u = make_unit_for_lane(
                            unit_type, spawn_pos, lane, team=0, manager=self.manager
                        )
                        self.units.append(u)

                # 3) Enemy HQ auto-spawn (both lanes, staggered)
                self._enemy_top_timer += 1
                self._enemy_bot_timer += 1

                if self._enemy_top_timer >= self._enemy_spawn_rate:
                    self._enemy_top_timer = 0
                    u = make_unit_for_lane(
                        "marine",
                        (WORLD_W - 200, float(TOP_LANE_Y)),
                        "top", team=1, manager=self.manager,
                    )
                    self.units.append(u)
                    print("[Enemy] spawned marine → top lane")

                if self._enemy_bot_timer >= self._enemy_spawn_rate:
                    self._enemy_bot_timer = 0
                    u = make_unit_for_lane(
                        "marine",
                        (WORLD_W - 200, float(BOT_LANE_Y)),
                        "bottom", team=1, manager=self.manager,
                    )
                    self.units.append(u)
                    print("[Enemy] spawned marine → bottom lane")

                # 4a) AI economy cycle (independent from player's self.res)
                self.ai_res.update()

                # 4b) AI slot buildings auto-spawn (team 1 units)
                for _ab in self.ai_controller.slot_buildings:
                    _ar = _ab.update()
                    if _ar:
                        _au_type, _asp, _al = _ar
                        _au = make_unit_for_lane(
                            _au_type, _asp, _al, team=1, manager=self.manager
                        )
                        self.units.append(_au)

                # 4c) AI strategic decisions (throttled internally to 1 per 2 s)
                #     Returns True if the AI fired its emergency nuke this frame.
                _ai_nuke = self.ai_controller.update(
                    frame     = self.frame,
                    units     = self.units,
                    ai_res    = self.ai_res,
                    manager   = self.manager,
                    ai_hq     = self.enemy_hq,
                    spawn_vfx = self.spawn_vfx,
                )
                if _ai_nuke and self.ai_controller.last_nuke_target:
                    # Trigger the same VFX the player gets when using the nuke
                    self.nuke_flash        = 90
                    self.shake_timer       = 30
                    self.shake_amp         = 10
                    self.nuke_circle       = self.ai_controller.last_nuke_target
                    self.nuke_circle_timer = 180
                    print("[AI] Nuke VFX triggered on main.py side")

                # 5) Combat + collision + cleanup
                BattleManager.process_combat(
                    self.units,
                    self.spawn_vfx,
                    buildings=self.all_buildings,
                )
                BattleManager.resolve_collisions(self.units)
                self.units = BattleManager.cleanup_dead(self.units)

                # 5) VFX
                self.vfx_list = BattleManager.update_vfx(self.vfx_list)

                # 6) Victory check
                self._check_victory()

            # 7) API snapshot (always)
            self._push_state()

            # ── Render ────────────────────────────────────────────────────────
            cam_x      = self.camera.cam_x
            cam_offset = self.camera.offset

            # Screen shake: sinusoidal offset decaying over shake_timer frames
            if self.shake_timer > 0:
                t          = self.shake_timer / 30        # 1.0 → 0.0
                amp        = int(self.shake_amp * t)
                shake_dx   = int(amp * math.sin(self.frame * 1.7))
                shake_dy   = int(amp * math.cos(self.frame * 2.3))
                cam_offset = (cam_offset[0] + shake_dx, cam_offset[1] + shake_dy)
                self.shake_timer -= 1

            # ── UI update & background ────────────────────────────────────
            self.ui.update()
            snap = UIManager.make_snapshot(self)
            self.ui.draw_background(self.screen, snap.cam_x)
            self.ui.draw_building_slots(
                self.screen, snap.cam_x, ALL_SLOTS, self._occupied_slots
            )

            self.player_hq.draw(self.screen, cam_offset)
            self.enemy_hq.draw(self.screen, cam_offset)

            for b in self.slot_buildings:
                b.draw(self.screen, cam_offset)

            # AI slot buildings (team 1, mirrored grid on far-right side)
            for b in self.ai_controller.slot_buildings:
                b.draw(self.screen, cam_offset)

            for u in self.units:
                u.draw(self.screen, cam_offset)
                if self.debug_mode:
                    u.draw_debug(self.screen, cam_offset)

            for vfx in self.vfx_list:
                vfx.draw(self.screen, cam_offset)

            # ── UI HUD & Cards ────────────────────────────────────────────
            self.ui.draw_all(self.screen, snap)

            # ── Phase 4: nuke VFX overlays ────────────────────────────────────
            # Red-alert flash (fades 90→0 frames after detonation)
            if self.nuke_flash > 0:
                alpha = int((self.nuke_flash / 90) * 190)
                flash_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                flash_surf.fill((220, 20, 20, alpha))
                self.screen.blit(flash_surf, (0, 0))
                self.nuke_flash -= 1

            # Blast circle (fades 180→0 frames, drawn in world-to-screen space)
            if self.nuke_circle is not None and self.nuke_circle_timer > 0:
                wx_n, wy_n = self.nuke_circle
                sx_n = int(wx_n) - int(cam_x)
                sy_n = int(wy_n)
                t    = self.nuke_circle_timer / 180
                a    = int(t * 200)
                ring = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                pygame.draw.circle(ring, (255, 100, 30, a),       (sx_n, sy_n), 450, 3)
                pygame.draw.circle(ring, (255, 200, 60, a // 4),  (sx_n, sy_n), 450)
                self.screen.blit(ring, (0, 0))
                self.nuke_circle_timer -= 1
                if self.nuke_circle_timer <= 0:
                    self.nuke_circle = None


            pygame.display.flip()

        pygame.quit()
        sys.exit()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    GameLoop().run()
