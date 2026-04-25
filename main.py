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
import functools
import sys
import threading

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Web / desktop detection ───────────────────────────────────────────────────
# pygbag sets sys.platform = "emscripten" when running in the browser.
# Use this flag to skip features that are unavailable in WebAssembly
# (background threads, FastAPI server, sys.exit, etc.).
_WEB: bool = sys.platform == "emscripten"

from src.asset_manager import AssetManager
from src.sprite        import Building, Unit, VFXSprite, Projectile
from src.battle        import BattleManager, SpatialGrid
from src.logic         import ResourceManager, BUILDING_SPECS, BASE_INCOME, BuildState, GameState
from src.ai            import AIController, AI_ALL_SLOTS
from src.ui_manager import UIManager
from src.shared import pop_actions
from src.commands import BuildCommand, DemolishCommand, NukeCommand, UpgradeCommand
from src.input_handler import InputHandler
from src.entity_manager import EntityManager

import src.shared as shared

# ── Screen / world constants ──────────────────────────────────────────────────
# Figma v2: iPhone 15 Pro Landscape — 2556 × 1179
SCREEN_W = 2556
SCREEN_H = 1179
WORLD_W  = SCREEN_W * 9 // 2          # 11502 — neutral zone halved (was 7×=17892)
WORLD_H  = SCREEN_H                   # 1179 (no vertical scroll)
FPS      = 60
TITLE    = "Star Raise — v5 (Phase 2: Auto-Spawn)"

# ── Sandwich layout (Figma v2 spec) ──────────────────────────────────────────
HUD_H               = 140             # top HUD strip
DECK_H              = 180             # bottom command deck
WORLD_VIEWPORT_H    = SCREEN_H - HUD_H - DECK_H   # 859 — playable world band
SAFE_ZONE           = 132             # L + R dead zone (Dynamic Island)
HQ_W                = 400             # fortified HQ block width

# ── Building-slot layout (player 1× base zone) ───────────────────────────────
# Slot: 84 × 84 px, gap 8 px, 4 × 4 grid  → GRID = 360 px wide
SLOT_SIZE  = 84
SLOT_GAP   = 8
SLOT_STEP  = SLOT_SIZE + SLOT_GAP     # 92
GRID_COLS  = 4
GRID_ROWS  = 4
GRID_H     = GRID_ROWS * SLOT_SIZE + (GRID_ROWS - 1) * SLOT_GAP  # 360

GRID_ORIGIN_X    = SAFE_ZONE + HQ_W   # 532  (right edge of HQ block)

_LANE_H          = WORLD_VIEWPORT_H // 2              # 429
_gPadY           = (_LANE_H - GRID_H) // 2            #  34 — vertical centering pad
GRID_ORIGIN_Y_TOP = HUD_H + _gPadY                    # 174
GRID_ORIGIN_Y_BOT = HUD_H + _LANE_H + _gPadY          # 603

# ── Lane Y-coordinates (horizontal march paths) ───────────────────────────────
TOP_LANE_Y: int = HUD_H + _LANE_H // 2                # 354
BOT_LANE_Y: int = HUD_H + _LANE_H + _LANE_H // 2     # 783


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

# ── Font loader ───────────────────────────────────────────────────────────────
def _load_font(size: int) -> pygame.font.Font:
    """Load NotoSansTC.ttf; tries three loaders — NEVER returns None."""
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
    # Should never reach here, but prevents implicit None
    return pygame.font.Font(None, 12)


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

# ── Command-Deck card layout (Figma v2 coordinates) ─────────────────────────
# Deck sits at y = SCREEN_H − DECK_H = 999, height = 180.
# Cards (CW=190, CH=150) are centred vertically in the deck.
DECK_Y  = SCREEN_H - DECK_H                           # 999
CARD_W  = 190
CARD_H  = 150
_CARD_Y_IN_DECK = (DECK_H - CARD_H) // 2             # 15
CARD_Y  = DECK_Y + _CARD_Y_IN_DECK                   # 1014

# Build cards [0-5] → buildings; [6] demolish toggle; [7] turret; [8] nuke
CARD_KINDS = [                       # None = demolish toggle
    "barracks", "refinery", "rover_bay", "spec_ops",
    "heavy_factory", "starport", None, "turret", "nuke",
]

# x[i] = 152 + i*204  for build cards 0-5 (CW=190, gap=14)
_CARD_X0    = SAFE_ZONE + 20                           # 152
_CARD_STEP  = CARD_W + 14                              # 204
_DEMO_X     = _CARD_X0 + 6 * _CARD_STEP + 18          # 152 + 1224 + 18 = 1394 → 1400
_TURRET_X   = 1544                                     # after demolish card
_NUKE_W     = 194
_NUKE_H     = CARD_H + 22                              # 172
_NUKE_X     = SCREEN_W - SAFE_ZONE - 206               # 2218
_NUKE_Y     = DECK_Y + (DECK_H - _NUKE_H) // 2        # 1003

CARD_RECTS: list[pygame.Rect] = [
    pygame.Rect(_CARD_X0 + 0 * _CARD_STEP, CARD_Y,  CARD_W, CARD_H),  # [0] 步兵營
    pygame.Rect(_CARD_X0 + 1 * _CARD_STEP, CARD_Y,  CARD_W, CARD_H),  # [1] 裝甲廠
    pygame.Rect(_CARD_X0 + 2 * _CARD_STEP, CARD_Y,  CARD_W, CARD_H),  # [2] 突擊車廠
    pygame.Rect(_CARD_X0 + 3 * _CARD_STEP, CARD_Y,  CARD_W, CARD_H),  # [3] 特戰中心
    pygame.Rect(_CARD_X0 + 4 * _CARD_STEP, CARD_Y,  CARD_W, CARD_H),  # [4] 重型兵工廠
    pygame.Rect(_CARD_X0 + 5 * _CARD_STEP, CARD_Y,  CARD_W, CARD_H),  # [5] 航空機場
    pygame.Rect(_DEMO_X,                    CARD_Y,  116,    CARD_H),  # [6] demolish
    pygame.Rect(_TURRET_X,                  CARD_Y,  CARD_W, CARD_H),  # [7] 防禦砲塔
    pygame.Rect(_NUKE_X,                    _NUKE_Y, _NUKE_W,_NUKE_H), # [8] nuke
]

CARD_COSTS = {k: BUILDING_SPECS[k]["cost"] for k in BUILDING_SPECS}

# Snap radius: ghost snaps to a slot when cursor world-centre is within this px
SNAP_RADIUS = SLOT_STEP * 1.2   # ≈ 110 px


# ── FastAPI background thread ─────────────────────────────────────────────────

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
    unit_type:   str,
    spawn_pos:   tuple[float, float],
    lane:        str,
    team:        int,
    manager:     AssetManager,
    march_right: bool | None = None,
    is_player:   bool        = False,
) -> Unit:
    """
    Create a Unit and assign lane-appropriate waypoints.

    Lane path layout (straight horizontal lines)
    ---------------------------------------------
    lane_y = TOP_LANE_Y or BOT_LANE_Y

    march_right=True  (left-side base → march toward right/enemy HQ):
      spawn_pos  →  (SCREEN_W+50, lane_y)  →  (WORLD_W-200, lane_y)

    march_right=False (right-side base → march toward left/player HQ):
      spawn_pos  →  (WORLD_W-SCREEN_W-50, lane_y)  →  (200, lane_y)

    If march_right is not supplied, it is inferred from team:
      team 0 → march right  (player units go right by default)
      any other → march left
    """
    if march_right is None:
        # Teams 0 (player) and 1 (allied AI) both start on the left → march right.
        # Team 2 (enemy) starts on the right → march left.
        march_right = (team != 2)

    lane_y = TOP_LANE_Y if lane == "top" else BOT_LANE_Y
    unit   = Unit(unit_type, manager, pos=spawn_pos, team=team, is_player=is_player)

    if march_right:
        unit.set_waypoints([
            (SCREEN_W + 50,  lane_y),   # exit left zone aligned with lane
            (WORLD_W - 200,  lane_y),   # near right / enemy HQ
        ])
    else:
        unit.set_waypoints([
            (WORLD_W - SCREEN_W - 50, lane_y),   # exit right zone
            (200,                     lane_y),   # near left / player HQ
        ])
    return unit


# ── GameLoop ──────────────────────────────────────────────────────────────────
class GameLoop:

    def __init__(self) -> None:
        pygame.display.init()   # no pygame.init() — avoids mixer/audio entirely
        pygame.font.init()
        print("[boot] display ready")
        # Web (pygbag/emscripten): skip scaling entirely — set_mode must own the surface
        if _WEB:
            self._win_w  = SCREEN_W
            self._win_h  = SCREEN_H
            self._scale  = 1.0
            self.screen  = pygame.display.set_mode((SCREEN_W, SCREEN_H))
            self._window = self.screen
        else:
            # Desktop: auto-fit window to monitor, render to logical canvas then blit
            _info        = pygame.display.Info()
            _max_w       = max(320, _info.current_w  - 60)
            _max_h       = max(240, _info.current_h  - 80)
            _scale       = min(_max_w / SCREEN_W, _max_h / SCREEN_H, 1.0)
            self._win_w  = max(1, int(SCREEN_W * _scale))
            self._win_h  = max(1, int(SCREEN_H * _scale))
            self._scale  = _scale
            self._window = pygame.display.set_mode((self._win_w, self._win_h))
            self.screen  = pygame.Surface((SCREEN_W, SCREEN_H))   # logical canvas
        pygame.display.set_caption(TITLE)
        self.font      = _load_font(18)
        self.fps_clk   = pygame.time.Clock()
        self.frame     = 0
        self.play_time = 0.0   # accumulated game time in seconds (only advances while PLAYING)
        self.camera    = Camera()

        # Pre-create reusable slot placeholder surface
        self._slot_surf = pygame.Surface((SLOT_SIZE, SLOT_SIZE), pygame.SRCALPHA)
        self._slot_surf.fill(COLOR_SLOT_FILL)

        # Assets manager (no preload here — done async in run())
        from src.ui_manager import UIManager
        self._UIManager = UIManager          # store class ref for use in run()
        self.manager = AssetManager()

        # API
        launch_api_thread()

        # Game mode — set before _init_scene() so it can read it
        # "1v1": player vs 1 enemy AI  |  "2v2": player+allied AI vs 2 enemy AIs
        self.game_mode:          str = "1v1"
        # Faction select state
        self.pending_game_mode:  str = "1v1"    # staged by main-menu, confirmed at launch
        self.selected_faction:   str = "federation"
        # Set by faction-select LAUNCH click (randomized independently of player)
        self.ai_faction:         str = "federation"

        # ── Settings state (persists across scene resets) ─────────────────────
        self.sfx_on:     bool      = True

        # ── Input controller ──────────────────────────────────────────────────
        self.input_handler = InputHandler()

        # ── Entity manager & shared spatial grid ──────────────────────────────
        self.entities      = EntityManager()
        self.spatial_grid  = None

    # ── Scene init (also used for R-reset) ───────────────────────────────────
    def _init_scene(self) -> None:
        # 實作物件池：預先分配記憶體，後續重複使用
        if not hasattr(self, "vfx_pool"):
            self.vfx_pool = [VFXSprite((-1000, -1000)) for _ in range(300)]
        for v in self.vfx_pool: v.is_done = True

        if not hasattr(self, "proj_pool"):
            self.proj_pool = [Projectile((-1000, -1000), (-1000, -1000), "piercing") for _ in range(500)]
        for p in self.proj_pool: p.is_done = True

        self.entities.clear_all()   # reset all entity lists for the new scene
        self.frame                      = 0
        self.play_time                  = 0.0   # reset elapsed game time on new scene
        self.game_state:  GameState     = GameState.PLAYING
        self.debug_mode:  bool          = False

        # ── Per-session stats (shown in result overlay) ────────────────────────
        self.player_kills:        int = 0   # enemy team-2 units destroyed
        self.buildings_placed:    int = 0   # slot buildings placed by the player
        self.total_income_earned: int = 0   # cumulative minerals from income cycles
        self.income_flash:float         = 0.0   # seconds remaining for HUD flash
        # Nuke red-alert flash (counts down 1.5 s → 0 after detonation)
        self.nuke_flash:        float                     = 0.0
        # Nuke blast circle (world pos + fade timer in seconds)
        self.nuke_circle:       tuple[float,float] | None = None
        self.nuke_circle_timer: float                     = 0.0
        # Screen shake — 0.5 s after nuke detonation
        self.shake_timer:       float                     = 0.0
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
            for v in self.vfx_pool:
                if v.is_done:
                    v.reset(pos)
                    self.entities.spawn_vfx(v)
                    return
        self.spawn_vfx = spawn_vfx

        def spawn_projectile(
            from_pos: tuple[float, float],
            to_pos:   tuple[float, float],
            atk_type: str,
        ) -> None:
            for p in self.proj_pool:
                if p.is_done:
                    p.reset(from_pos, to_pos, atk_type)
                    self.entities.spawn_projectile(p)
                    return
        self.spawn_projectile = spawn_projectile

        # ── Player faction — locked in at faction-select LAUNCH ───────────────
        self.player_faction: str = self.selected_faction

        # ── Player HQ — art depends on player faction ─────────────────────────
        # Positioned at centre of the HQ slot block:
        #   x = SAFE_ZONE + HQ_W // 2 = 132 + 200 = 332
        #   y = HUD_H + WORLD_VIEWPORT_H // 2 = 140 + 429 = 569
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

        # ── Enemy HQ — art depends on ai_faction (set at LAUNCH) ─────────────
        _enemy_hq_kind = _HQ_KIND_BY_FACTION.get(self.ai_faction, "hq")
        self.enemy_hq = Building(
            _enemy_hq_kind, self.manager,
            pos=(WORLD_W - SAFE_ZONE - HQ_W // 2,
                 HUD_H + WORLD_VIEWPORT_H // 2),
            hp=2500, team=2,
            lane="none", is_hq=True,
        )

        # Phase 4: HQ death callbacks — transition game_state immediately
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

        # ── AI controllers (one per AI team) ─────────────────────────────────
        # Each AIController owns its ResourceManager (ctrl.res).
        # self.ai_faction was set at faction-select LAUNCH; defaults "federation".
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
        elif self.game_mode == "pvp":
            # 建立承載遠端玩家資源與建築的控制器，並標記為人類 (停用 AI 決策)
            ctrl = _make_enemy_ctrl(AI_ALL_SLOTS, self.ai_faction)
            ctrl.is_human = True
            self.ai_controllers.append(ctrl)
        elif self.game_mode == "2v2":
            # Allied AI: always federation (plays alongside human)
            allied = AIController(
                team=1, enemy_team=2,
                slots=list(ALL_SLOTS), is_left=True,
                faction="federation",
            )
            self.ai_controllers.append(allied)
            # Two enemy AIs each get independently randomized factions
            enemy1 = _make_enemy_ctrl(AI_ALL_SLOTS[:16],
                                      random.choice(["federation", "swarm", "rogue_ai"]))
            enemy2 = _make_enemy_ctrl(AI_ALL_SLOTS[16:],
                                      random.choice(["federation", "swarm", "rogue_ai"]))
            self.ai_controllers.append(enemy1)
            self.ai_controllers.append(enemy2)

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
        b      = Building(kind, self.manager, pos=(cx, cy), team=team, lane=lane,
                          is_player=(team == 0))
        self.slot_buildings.append(b)
        self._occupied_slots.add(slot_idx)
        self.res.register_building(b)
        if team == 0:
            self.buildings_placed += 1
        return b

    # ── Properties ────────────────────────────────────────────────────────────
    @property
    def all_buildings(self) -> list[Building]:
        """All buildings: HQs + player slot buildings + all AI slot buildings."""
        ai_blds: list[Building] = []
        for ctrl in self.ai_controllers:
            ai_blds.extend(ctrl.slot_buildings)
        return [self.player_hq, self.enemy_hq] + self.slot_buildings + ai_blds

    # Backward-compat aliases so commands.py / input_handler.py / ai.py
    # can continue to read and write game.units / game.projectiles / game.vfx_list.
    @property
    def units(self):             return self.entities.units
    @units.setter
    def units(self, val):        self.entities.units = val

    @property
    def projectiles(self):       return self.entities.projectiles

    @property
    def vfx_list(self):          return self.entities.vfx_list

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
        # ── Force-dismiss the pygbag HTML loading overlay ─────────────────────
        self.screen.fill((0, 0, 0))
        pygame.display.flip()
        await asyncio.sleep(0)

        # ── Async asset loading (yields to browser; prevents WASM freeze) ──────
        print("[boot] loading assets...")
        await self.manager.preload_all_async()
        print("[boot] assets ready")

        # ── Scene + UI (after assets so sprites get real surfaces) ────────────
        print("[boot] init scene...")
        self._init_scene()
        self.game_state = GameState.MAIN_MENU
        self.ui = self._UIManager(SCREEN_W, SCREEN_H, SLOT_SIZE, WORLD_W,
                                  asset_manager=self.manager)
        print("[boot] ui ready — entering loop")

        running    = True
        team_stats = {}

        while running:
            raw_ms = self.fps_clk.tick(FPS)
            dt     = min(raw_ms / 1000.0, 0.1)   # seconds; capped at 100 ms to prevent jumps
            self.frame += 1
            fps = self.fps_clk.get_fps()

            # ── Process API actions ───────────────────────────────────────────
            for act in pop_actions():
                atype = act.get("type")
                pid = act.get("player_id", 0)

                # 判定是本機玩家 (0) 還是遠端對手 (1)
                is_p1 = (pid == 0)
                # 取得負責 Team 2 (右側敵方) 的控制器
                p2_ctrl = next((c for c in self.ai_controllers if c.team == 2), None)

                if atype == "build":
                    slot = act.get("slot")
                    kind = act.get("kind")
                    if (slot is not None and kind in BUILDING_SPECS
                            and slot not in self._occupied_slots
                            and self.game_state.name == "PLAYING"):
                        BuildCommand(pid, slot, kind).execute(self)
                elif atype == "demolish":
                    slot = act.get("slot")
                    if slot is not None and slot in self._occupied_slots:
                        DemolishCommand(pid, slot).execute(self)
                elif atype == "nuke":
                    if self.game_state.name == "PLAYING":
                        nx, ny = act.get("x", 0), act.get("y", 0)
                        NukeCommand(pid, nx, ny).execute(self)
            # ── Events ────────────────────────────────────────────────────────
            if not self.input_handler.process_events(self):
                running = False

            # ── Game logic ────────────────────────────────────────────────────
            if self.game_state == GameState.PLAYING:
                self.play_time += dt   # advance real-time game clock

                # 1) Player income cycle
                if self.res.update(dt):
                    self.total_income_earned += self.res.income_per_cycle
                    self.income_flash = 0.5   # 0.5 s HUD flash
                if self.income_flash > 0:
                    self.income_flash -= dt

                # 2) Slot buildings auto-spawn + turret fire (player-placed)
                for b in self.slot_buildings:
                    result = b.update(
                        dt,
                        spatial_grid=self.spatial_grid,
                        projectile_callback=self.spawn_projectile,
                        vfx_callback=self.spawn_vfx,
                    )
                    if result:
                        unit_type, spawn_pos, lane = result
                        count = BUILDING_SPECS.get(b.kind, {}).get("spawn_count", 1)
                        for i in range(count):
                            offset_y = (i * 20 - 10) if count > 1 else 0
                            actual_pos = (spawn_pos[0], spawn_pos[1] + offset_y)
                            u = make_unit_for_lane(
                                unit_type, actual_pos, lane, team=0,
                                manager=self.manager, is_player=True,
                            )
                            self.units.append(u)

                # 3) All AI controllers — economy + auto-spawn + strategy
                # (HQ-level cheat-spawns removed: AIController slot buildings
                #  are the only enemy spawn source, keeping unit counts fair)
                for _ctrl in self.ai_controllers:
                    # a) Economy tick (each controller has its own ResourceManager)
                    _ctrl.res.update(dt)

                    # b) Slot buildings auto-spawn + turret fire (AI)
                    for _ab in _ctrl.slot_buildings:
                        _ar = _ab.update(
                            dt,
                            spatial_grid=self.spatial_grid,
                            projectile_callback=self.spawn_projectile,
                            vfx_callback=self.spawn_vfx,
                        )
                        if _ar:
                            _au_type, _asp, _al = _ar
                            _count = BUILDING_SPECS.get(_ab.kind, {}).get("spawn_count", 1)
                            for _i in range(_count):
                                _offset_y = (_i * 20 - 10) if _count > 1 else 0
                                _actual_pos = (_asp[0], _asp[1] + _offset_y)
                                _au = make_unit_for_lane(
                                    _au_type, _actual_pos, _al,
                                    team=_ctrl.team,
                                    march_right=_ctrl.is_left,
                                    manager=self.manager,
                                )
                                self.units.append(_au)

                    # c) Strategic decisions (throttled to _ACTION_COOLDOWN s internally)
                    # 如果該控制器是人類玩家 (PVP的遠端對手)，則跳過 AI 決策邏輯
                    if not getattr(_ctrl, "is_human", False):
                        _my_hq  = self.player_hq if _ctrl.is_left else self.enemy_hq
                        commands = _ctrl.update(
                            play_time    = self.play_time,
                            units        = self.units,
                            manager      = self.manager,
                            my_hq        = _my_hq,
                            spawn_vfx    = self.spawn_vfx,
                            team_stats   = team_stats,
                        )
                        for cmd in commands:
                            cmd.execute(self)

                # ── 1. Combat & Physics ───────────────────────────────────────────
                # 建立本幀共用的 SpatialGrid 與隊伍統計
                self.spatial_grid = SpatialGrid(cell_size=100)
                self.spatial_grid.build(self.units)

                team_stats = {}
                for u in self.units:
                    if u.is_dead: continue
                    if u.team not in team_stats:
                        team_stats[u.team] = {"units": [], "flying": 0, "heavy": 0, "light": 0}
                    ts = team_stats[u.team]
                    ts["units"].append(u)
                    if getattr(u, "is_flying", False): ts["flying"] += 1
                    if getattr(u, "armor_type", "") == "heavy": ts["heavy"] += 1
                    if getattr(u, "armor_type", "") == "light": ts["light"] += 1

                # Count enemy units that died this frame (before cleanup removes them)
                self.player_kills += sum(
                    1 for u in self.units if u.is_dead and u.team == 2
                )

                # Delegate combat, projectile/VFX updates, and cleanup to EntityManager
                all_buildings = self.slot_buildings.copy()
                for ctrl in self.ai_controllers:
                    all_buildings.extend(ctrl.slot_buildings)
                self.entities.update(self.spatial_grid, dt, self.all_buildings)

                # 6) Victory check
                self._check_victory()

            # 7) API snapshot (always)
            self._push_state()

            # ── Render ────────────────────────────────────────────────────────
            cam_x      = self.camera.cam_x
            cam_offset = self.camera.offset

            # Screen shake: sinusoidal offset decaying over 0.5 s
            if self.shake_timer > 0:
                t          = min(1.0, self.shake_timer / 0.5)   # 1.0 → 0.0
                amp        = int(self.shake_amp * t)
                shake_dx   = int(amp * math.sin(self.frame * 1.7))
                shake_dy   = int(amp * math.cos(self.frame * 2.3))
                cam_offset = (cam_offset[0] + shake_dx, cam_offset[1] + shake_dy)
                self.shake_timer -= dt

            # ── UI update & snapshot ──────────────────────────────────────
            self.ui.update()
            snap = UIManager.make_snapshot(self)

            # ── Render: branch on game state ──────────────────────────────
            if self.game_state == GameState.MAIN_MENU:
                # Title screen — UIManager owns the full draw
                self.screen.fill((18, 22, 36))
                self.ui.draw_all(self.screen, snap)

            elif self.game_state == GameState.FACTION_SELECT:
                # Faction selection — shown between main menu and game start
                self.ui.draw_faction_select(
                    self.screen,
                    self.selected_faction,
                    self.pending_game_mode,
                )

            elif self.game_state == GameState.UNIT_INFO:
                # Unit & building reference card screen
                self.ui.draw_unit_info(self.screen)

            else:
                # ── Gameplay: world + sprites + HUD ───────────────────────
                self.ui.draw_background(self.screen, snap.cam_x)
                self.ui.draw_building_slots(
                    self.screen, snap.cam_x, ALL_SLOTS, self._occupied_slots,
                    snap.build_state_name
                )

                # ── Y-sorted render pass (2.5D depth) ─────────────────────
                # Collect every sprite that occupies world-space.
                # Sort by the sprite's bottom-Y in world coordinates so that
                # entities lower on screen (closer to camera in 60° 2.5D)
                # are painted on top of those higher up.
                _render_list = []
                _render_list.append(self.player_hq)
                _render_list.append(self.enemy_hq)
                _render_list.extend(self.slot_buildings)
                for _ctrl in self.ai_controllers:
                    _render_list.extend(_ctrl.slot_buildings)
                _render_list.extend(self.units)

                # Key: world-Y of sprite's bottom edge
                # (pos[1] is the centre; adding half the surface height
                #  gives the bottom pixel in world space)
                def _sort_key(obj):
                    try:
                        return obj.pos[1] + (obj.surface.get_height() * 0.5 if obj.surface else 0)
                    except Exception:
                        return obj.pos[1]
                _render_list.sort(key=_sort_key)

                for _obj in _render_list:
                    _obj.draw(self.screen, cam_offset)

                # Debug overlays drawn on top of sorted sprites (units only)
                if self.debug_mode:
                    for u in self.units:
                        u.draw_debug(self.screen, cam_offset)

                # Projectiles drawn above units, below VFX impact rings
                for _proj in self.projectiles:
                    if not _proj.is_done:
                        _proj.draw(self.screen, cam_offset)

                # VFX always on top of world sprites
                for vfx in self.vfx_list:
                    if not vfx.is_done:
                        vfx.draw(self.screen, cam_offset)

                # ── Phase 4: nuke VFX overlays ────────────────────────────
                # Red-alert flash (fades 90→0 frames after detonation)
                if self.nuke_flash > 0:
                    alpha = int(min(1.0, self.nuke_flash / 1.5) * 190)
                    flash_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                    flash_surf.fill((220, 20, 20, alpha))
                    self.screen.blit(flash_surf, (0, 0))
                    self.nuke_flash -= dt

                # Blast circle (fades over 3 s, drawn in world-to-screen space)
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

                # ── HUD on top of gameplay world ───────────────────────────
                # Demolish refund preview overlay
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

            # ── Settings overlay ──────────────────────────────────────────
            if self.game_state == GameState.SETTINGS:
                self.screen.fill((18, 22, 36))
                self.ui.draw_main_menu(self.screen)
                self.ui.draw_settings_overlay(self.screen, sfx_on=self.sfx_on)

            # ── Scale logical canvas → real window, then flip ─────────────────
            # Web: self.screen IS the display surface — just flip directly.
            # Desktop: blit logical canvas (scaled if needed) onto real window.
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