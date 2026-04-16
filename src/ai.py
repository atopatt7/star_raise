"""
ai.py — Star Raise  Phase 5+: Multi-Team Grid-Based Strategic AI

AIController is now fully parameterised so it can drive any team on either
side of the map — enabling 1V1, 2V2, and future n-team modes.

Constructor parameters
----------------------
team              : int   — which team this controller builds for (default 1)
enemy_team        : int   — which team's units are considered threats (default 0)
slots             : list  — 32 (x,y) world positions for this controller's grid;
                            defaults to AI_ALL_SLOTS (right-side mirror grid)
is_left           : bool  — True  → base is on the LEFT  (units march right)
                            False → base is on the RIGHT (units march left)
starting_minerals : int   — starting mineral balance for this controller's economy

Built-in ResourceManager
------------------------
Each controller owns self.res — a ResourceManager that tracks its own minerals
and building income independently of the player's or other AIs' economies.
main.py no longer needs to create a separate ai_res per controller.

Three-phase strategy (unchanged)
---------------------------------
Early game  (frame < 10,800 ≈ 3 min @ 60 fps)
    70 % → Refinery in REAR slots  (closest to own HQ — income first)
    30 % → Barracks anywhere free

Mid game    (frame ≥ 10,800)
    80 % → Barracks in FRONT slots of the lane where the enemy is weakest
    20 % → Refinery anywhere free

Emergency   (every frame, one-shot)
    Condition : self.res.nuke_available is True
                AND own HQ hp < 50 % max_hp
                AND ≥ 6 enemy units have crossed into own half of the map
    Action    : launch_nuke() targeting the centroid of those threatening units

AI grid layout — right-side (is_left=False, default)
------------------------------------------------------
    col 0 (REAR)   x ≈ 10886  ←  closest to AI HQ at x≈11170
    col 1          x ≈ 10794
    col 2          x ≈ 10702
    col 3 (FRONT)  x ≈ 10610  ←  closest to battlefield / player

Left-side grid (is_left=True) uses the same positions as the player base
(ALL_SLOTS from main.py), passed in via the `slots` parameter.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.sprite        import Building
    from src.asset_manager import AssetManager

# ── Layout constants (mirror of main.py; local copy avoids circular import) ───
# Figma v2 spec: 2556×1179, HUD=140, DECK=180, SAFE=132, HQ_W=400
# SLOT=84, GAP=8, GRID_ORIGIN_X=532 (SAFE+HQ_W)
# WORLD_VIEWPORT_H=859, LANE_H=429, gPadY=34
_WORLD_W            = 11502              # 2556 * 9 // 2  (neutral zone halved)
_SLOT_SIZE          = 84
_SLOT_GAP           = 8
_SLOT_STEP          = _SLOT_SIZE + _SLOT_GAP    # 92
_GRID_COLS          = 4
_GRID_ROWS          = 4
_GRID_ORIGIN_X      = 532               # SAFE(132) + HQ_W(400)
_GRID_ORIGIN_Y_TOP  = 174              # HUD_H(140) + gPadY(34)
_GRID_ORIGIN_Y_BOT  = 603              # HUD_H(140) + LANE_H(429) + gPadY(34)
_TOP_LANE_Y         = 354              # HUD_H(140) + LANE_H//2(214)
_BOT_LANE_Y         = 783              # HUD_H(140) + LANE_H(429) + LANE_H//2(214)

# ── AI slot grid (mirrored — col 0 = rear / right, col 3 = front / left) ─────
def _make_ai_slots(origin_y: int) -> list[tuple[int, int]]:
    """
    32 slot top-left corners for the AI's 4×4 grid.

    Mirror formula:
        x = WORLD_W − GRID_ORIGIN_X − SLOT_SIZE − col × SLOT_STEP
        y = origin_y + row × SLOT_STEP
    """
    return [
        (
            _WORLD_W - _GRID_ORIGIN_X - _SLOT_SIZE - col * _SLOT_STEP,
            origin_y + row * _SLOT_STEP,
        )
        for row in range(_GRID_ROWS)
        for col in range(_GRID_COLS)
    ]


AI_TOP_SLOTS: list[tuple[int, int]] = _make_ai_slots(_GRID_ORIGIN_Y_TOP)
AI_BOT_SLOTS: list[tuple[int, int]] = _make_ai_slots(_GRID_ORIGIN_Y_BOT)
AI_ALL_SLOTS: list[tuple[int, int]] = AI_TOP_SLOTS + AI_BOT_SLOTS   # 32 total

# Column role flags  (slot_idx % _GRID_COLS gives the column)
_REAR_COLS  = frozenset({0, 1})   # close to own HQ  — income buildings preferred
_FRONT_COLS = frozenset({2, 3})   # close to battle  — barracks preferred

# Building costs (must match BUILDING_SPECS in logic.py)
_COSTS: dict[str, int] = {"barracks": 100, "refinery": 200}

# Phase / timing
_EARLY_GAME_FRAMES = 10_800      # 3 min × 60 fps
_ACTION_COOLDOWN   = 120         # frames between build decisions (2 s @ 60 fps)
_NUKE_THREAT_COUNT = 6           # min enemy units in own half to trigger nuke


# ── AIController ──────────────────────────────────────────────────────────────
class AIController:
    """
    Manages one AI team's building grid, economy, unit spawning, and nuke.

    Each controller is self-contained: it owns its ResourceManager (self.res)
    and can be placed on either side of the map via `is_left` / `slots`.

    Public interface
    ----------------
    ctrl.team                  — int: team number for spawned buildings/units
    ctrl.is_left               — bool: True = left-side base, units march right
    ctrl.res                   — ResourceManager: this AI's mineral economy
    ctrl.slot_buildings        — list[Building]: live buildings owned by this AI
    ctrl.occupied_slots        — set[int]: slot indices with live buildings
    ctrl.last_nuke_target      — world-pos of last nuke (or None)
    ctrl.update(...)           — call every game frame; returns True if nuke fired
    """

    def __init__(
        self,
        team:              int  = 1,
        enemy_team:        int  = 0,
        slots:             list | None = None,
        is_left:           bool = False,
        starting_minerals: int  = 150,
    ) -> None:
        # Team identity
        self.team        = team
        self.enemy_team  = enemy_team
        self.is_left     = is_left

        # Slot grid (defaults to right-side AI mirror grid)
        self.slots: list[tuple[int, int]] = (
            slots if slots is not None else AI_ALL_SLOTS
        )

        # Own economy — independent from player's ResourceManager
        from src.logic import ResourceManager as _RM
        self.res = _RM(starting=starting_minerals)

        # slot_idx → Building sprite  (dead buildings lazily removed)
        self._slot_map:       dict[int, "Building"] = {}
        self._last_act_frame: int                   = -_ACTION_COOLDOWN
        # Set when emergency nuke fires; read by GameLoop for VFX
        self.last_nuke_target: tuple[float, float] | None = None

    # ── Public accessors ──────────────────────────────────────────────────────
    @property
    def slot_buildings(self) -> list["Building"]:
        """Live list of all buildings owned by this controller."""
        return list(self._slot_map.values())

    @property
    def occupied_slots(self) -> set[int]:
        return set(self._slot_map.keys())

    # ── Private helpers ───────────────────────────────────────────────────────
    def _col_of(self, slot_idx: int) -> int:
        """Column within the 4×4 grid (0 = rear, 3 = front)."""
        return slot_idx % _GRID_COLS

    def _lane_of(self, slot_idx: int) -> str:
        """
        Determine lane by actual world Y-coordinate of the slot, not by index.

        Using index < 16 breaks when self.slots is a slice of AI_ALL_SLOTS
        (e.g. 2V2 half-grid where each controller only has 16 slots starting
        at index 0, all of which could be in the bottom lane).
        """
        _, sy = self.slots[slot_idx]
        return "bottom" if sy > 400 else "top"

    def _free_slots(
        self,
        col_filter: frozenset[int] | None = None,
        lane:       str             | None = None,
    ) -> list[int]:
        """
        Return unoccupied slot indices, optionally restricted to a column set
        and/or a lane.  Uses len(self.slots) so controllers with fewer than 32
        slots (e.g. half-grid for 2V2 lane specialisation) work correctly.
        Lane filtering uses _lane_of() (Y-coord based) not raw index comparison.
        """
        result = []
        for idx in range(len(self.slots)):
            if idx in self._slot_map:
                continue
            if col_filter is not None and self._col_of(idx) not in col_filter:
                continue
            if lane is not None and self._lane_of(idx) != lane:
                continue
            result.append(idx)
        return result

    def _enemy_units_in_my_half(self, units: list) -> list:
        """
        Return enemy (self.enemy_team) units that have entered this AI's half.

        is_left=True  → own half is world x < WORLD_W / 2 (left side)
        is_left=False → own half is world x > WORLD_W / 2 (right side)
        """
        half = _WORLD_W // 2
        if self.is_left:
            return [
                u for u in units
                if not u.is_dead and u.team == self.enemy_team
                and u.pos[0] < half
            ]
        else:
            return [
                u for u in units
                if not u.is_dead and u.team == self.enemy_team
                and u.pos[0] > half
            ]

    def _weakest_enemy_lane(self, units: list) -> str:
        """
        Lane where self.enemy_team has fewer alive units.
        AI focuses Barracks there to press the thinner line.
        """
        top = sum(
            1 for u in units
            if not u.is_dead and u.team == self.enemy_team
            and abs(u.pos[1] - _TOP_LANE_Y) < abs(u.pos[1] - _BOT_LANE_Y)
        )
        bot = sum(
            1 for u in units
            if not u.is_dead and u.team == self.enemy_team
            and abs(u.pos[1] - _BOT_LANE_Y) <= abs(u.pos[1] - _TOP_LANE_Y)
        )
        return "top" if top <= bot else "bottom"

    # ── Construction ──────────────────────────────────────────────────────────
    def _try_build(
        self,
        kind:       str,
        candidates: list[int],
        manager:    "AssetManager",
    ) -> "Building | None":
        """
        Place *kind* building at a random slot chosen from *candidates*.

        Uses self.res for spending and self.team for the building's team.
        Returns the new Building sprite, or None if placement failed.
        """
        if not candidates:
            return None
        cost = _COSTS.get(kind, 99_999)
        if not self.res.spend(cost):
            return None   # insufficient minerals — nothing deducted

        from src.sprite import Building as _Bld

        slot_idx = random.choice(candidates)
        sx, sy   = self.slots[slot_idx]
        cx       = sx + _SLOT_SIZE // 2
        cy       = sy + _SLOT_SIZE // 2
        lane     = self._lane_of(slot_idx)
        b        = _Bld(kind, manager, pos=(cx, cy), team=self.team, lane=lane)

        self._slot_map[slot_idx] = b
        self.res.register_building(b)
        print(
            f"[AI t{self.team}] Built {kind}  slot={slot_idx}  lane={lane}  "
            f"col={self._col_of(slot_idx)}  minerals_left={self.res.minerals}"
        )
        return b

    # ── Emergency nuke ────────────────────────────────────────────────────────
    def trigger_emergency_nuke(
        self,
        units:    list,
        my_hq,              # this controller's own HQ building
        spawn_vfx,
    ) -> bool:
        """
        Defensive one-shot nuke.

        Fires when:
          1. self.res.nuke_available is True
          2. own HQ hp < 50 % of max_hp
          3. ≥ _NUKE_THREAT_COUNT enemy units are inside own half of the map

        Target: centroid of the threatening units.
        """
        if not self.res.nuke_available:
            return False
        if my_hq.hp >= int(my_hq.max_hp * 0.5):
            return False

        threats = self._enemy_units_in_my_half(units)
        if len(threats) < _NUKE_THREAT_COUNT:
            return False

        tx = sum(u.pos[0] for u in threats) / len(threats)
        ty = sum(u.pos[1] for u in threats) / len(threats)
        self.last_nuke_target = (tx, ty)

        print(
            f"[AI t{self.team}] ☢ EMERGENCY NUKE  "
            f"hq_hp={my_hq.hp}/{my_hq.max_hp}  "
            f"threats={len(threats)}  target=({tx:.0f}, {ty:.0f})"
        )
        return self.res.launch_nuke((tx, ty), units, spawn_vfx)

    # ── Main tick ─────────────────────────────────────────────────────────────
    def update(
        self,
        frame:     int,
        units:     list,
        manager:   "AssetManager",
        my_hq,              # this controller's own HQ (for nuke condition)
        spawn_vfx,
    ) -> bool:
        """
        Called every game frame by GameLoop.

        Returns True on the frame an emergency nuke fires.

        Build decisions are throttled to once per _ACTION_COOLDOWN frames.
        The emergency nuke check runs every frame (unthrottled).
        """
        # ── 1) Lazily remove dead buildings (frees slots for rebuilding) ──────
        dead = [k for k, b in self._slot_map.items() if b.is_dead]
        for k in dead:
            del self._slot_map[k]
            print(f"[AI t{self.team}] slot {k} freed (building destroyed)")

        # ── 2) Emergency nuke (unthrottled) ───────────────────────────────────
        if self.trigger_emergency_nuke(units, my_hq, spawn_vfx):
            return True

        # ── 3) Build decision (throttled to 1 per _ACTION_COOLDOWN frames) ────
        if frame - self._last_act_frame < _ACTION_COOLDOWN:
            return False
        self._last_act_frame = frame

        if len(self._slot_map) >= len(self.slots):
            return False   # grid is full

        if frame < _EARLY_GAME_FRAMES:
            # ── Early game: 80% Barracks / 20% Refinery ──────────────────────
            # Refinery chance reduced to 0.20 to prevent an unstoppable Tank
            # army while the AI is still trying to boost its economy.
            if random.random() < 0.20:
                self._try_build(
                    "refinery",
                    self._free_slots(col_filter=_REAR_COLS),
                    manager,
                )
            else:
                self._try_build("barracks", self._free_slots(), manager)
        else:
            # ── Mid game: pressure the weakest enemy lane ─────────────────────
            if random.random() < 0.80:
                target_lane = self._weakest_enemy_lane(units)
                front       = self._free_slots(col_filter=_FRONT_COLS, lane=target_lane)
                if not front:
                    front = self._free_slots(col_filter=_FRONT_COLS)
                self._try_build("barracks", front, manager)
            else:
                self._try_build("refinery", self._free_slots(), manager)

        return False
