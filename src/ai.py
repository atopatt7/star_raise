"""
ai.py — Star Raise  Phase 5: Grid-Based Strategic AI

Three-phase strategy
--------------------
Early game  (frame < 10,800 ≈ 3 min at 60 fps)
    70 % → Refinery in REAR slots  (cols 0–1, close to AI HQ — income first)
    30 % → Barracks anywhere free

Mid game    (frame ≥ 10,800)
    80 % → Barracks in FRONT slots (cols 2–3) of the "weakest" player lane
            (the lane where the PLAYER has fewer alive units — push the
            advantage where the enemy is thinner)
    20 % → Refinery anywhere free

Emergency   (every frame, one-shot)
    Condition : AI HQ hp < 50 % max_hp
                AND ≥ 6 player (team-0) units in the AI's half of the world
    Action    : launch_nuke() targeting the centroid of those threatening units
    Goal      : repel a massed assault that has already broken through to the
                AI's base — the nuke clears the field so the AI can recover

AI grid layout
--------------
The player's 32 slots occupy world x ≈ 148–428 (cols 0–3, left to right).
The AI's 32 slots are the mirror image on the far right:

    col 0 (REAR)   x ≈ 8748  ←  closest to AI HQ at x=8880
    col 1          x ≈ 8676
    col 2          x ≈ 8604
    col 3 (FRONT)  x ≈ 8532  ←  closest to battlefield / player

Top-lane rows share GRID_ORIGIN_Y_TOP (y=7), bottom-lane GRID_ORIGIN_Y_BOT (y=302).
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.sprite        import Building
    from src.logic         import ResourceManager
    from src.asset_manager import AssetManager

# ── Layout constants (mirror of main.py; local copy avoids circular import) ───
# Figma v2 spec: 2556×1179, HUD=140, DECK=180, SAFE=132, HQ_W=400
# SLOT=84, GAP=8, GRID_ORIGIN_X=532 (SAFE+HQ_W)
# WORLD_VIEWPORT_H=859, LANE_H=429, gPadY=34
_WORLD_W            = 17892              # 2556 * 7
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

    So col 0 is the rightmost (rear, 148 px from the right edge of the world,
    mirroring the player's col 0 being 148 px from the left edge).
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
_REAR_COLS  = frozenset({0, 1})   # close to AI HQ  — income buildings preferred
_FRONT_COLS = frozenset({2, 3})   # close to battle — barracks preferred

# Building costs (must match BUILDING_SPECS in logic.py)
_COSTS: dict[str, int] = {"barracks": 100, "refinery": 200}

# Phase / timing
_EARLY_GAME_FRAMES = 10_800      # 3 min × 60 fps
_ACTION_COOLDOWN   = 120         # frames between build decisions (2 s @ 60 fps)
_NUKE_THREAT_COUNT = 6           # min player units in AI half to trigger nuke


# ── AIController ──────────────────────────────────────────────────────────────
class AIController:
    """
    Manages the enemy (team 1) building grid, income, unit spawning,
    and the one-shot emergency tactical nuke.

    Owned by GameLoop; the instance is replaced on each scene reset (R key).

    Public interface
    ----------------
    ai.slot_buildings          — list of live Building sprites (AI team 1)
    ai.occupied_slots          — set of occupied slot indices (0–31)
    ai.last_nuke_target        — world-pos of last nuke detonation (or None)
    ai.update(...)             — call every game frame; returns True if nuke fired
    """

    def __init__(self) -> None:
        # slot_idx → Building sprite  (dead buildings are lazily removed)
        self._slot_map:       dict[int, "Building"]       = {}
        self._last_act_frame: int                         = -_ACTION_COOLDOWN
        # Set when trigger_emergency_nuke fires; read by GameLoop for VFX
        self.last_nuke_target: tuple[float, float] | None = None

    # ── Public accessors ──────────────────────────────────────────────────────
    @property
    def slot_buildings(self) -> list["Building"]:
        """Live list of all AI slot buildings."""
        return list(self._slot_map.values())

    @property
    def occupied_slots(self) -> set[int]:
        return set(self._slot_map.keys())

    # ── Private helpers ───────────────────────────────────────────────────────
    def _col_of(self, slot_idx: int) -> int:
        """Column within the 4×4 grid (0 = rear, 3 = front)."""
        return slot_idx % _GRID_COLS

    def _lane_of(self, slot_idx: int) -> str:
        return "top" if slot_idx < 16 else "bottom"

    def _free_slots(
        self,
        col_filter: frozenset[int] | None = None,
        lane:       str             | None = None,
    ) -> list[int]:
        """
        Return unoccupied slot indices, optionally restricted to a column set
        and/or a lane.  O(32) — fast enough to call every decision tick.
        """
        result = []
        for idx in range(32):
            if idx in self._slot_map:
                continue
            if col_filter is not None and self._col_of(idx) not in col_filter:
                continue
            if lane == "top"    and idx >= 16:
                continue
            if lane == "bottom" and idx <  16:
                continue
            result.append(idx)
        return result

    def _player_units_in_ai_half(self, units: list) -> list:
        """Team-0 units whose world-x > WORLD_W / 2 (inside the AI's half)."""
        half = _WORLD_W // 2
        return [
            u for u in units
            if not u.is_dead and u.team == 0 and u.pos[0] > half
        ]

    def _weakest_player_lane(self, units: list) -> str:
        """
        Lane where the PLAYER (team 0) has fewer alive units.

        The AI focuses Barracks into the front slots of that lane to overwhelm
        the thinner defence — 'press where they're weakest'.
        """
        top = sum(
            1 for u in units
            if not u.is_dead and u.team == 0
            and abs(u.pos[1] - _TOP_LANE_Y) < abs(u.pos[1] - _BOT_LANE_Y)
        )
        bot = sum(
            1 for u in units
            if not u.is_dead and u.team == 0
            and abs(u.pos[1] - _BOT_LANE_Y) <= abs(u.pos[1] - _TOP_LANE_Y)
        )
        return "top" if top <= bot else "bottom"

    # ── Construction ──────────────────────────────────────────────────────────
    def _try_build(
        self,
        kind:       str,
        candidates: list[int],
        ai_res:     "ResourceManager",
        manager:    "AssetManager",
    ) -> "Building | None":
        """
        Place *kind* building at a random slot chosen from *candidates*.

        Follows Phase 3 rules:
          • No slot overlap — candidates are already filtered to free slots.
          • Uses ai_res.spend(cost) which returns False (no deduction) if
            the AI can't afford it.
          • Registers the building with ai_res for passive income.

        Returns the new Building sprite, or None if placement failed.
        """
        if not candidates:
            return None
        cost = _COSTS.get(kind, 99_999)
        if not ai_res.spend(cost):
            return None   # insufficient minerals — nothing deducted

        # Local import prevents circular dependency at module level
        from src.sprite import Building as _Bld

        slot_idx = random.choice(candidates)
        sx, sy   = AI_ALL_SLOTS[slot_idx]
        cx       = sx + _SLOT_SIZE // 2
        cy       = sy + _SLOT_SIZE // 2
        lane     = self._lane_of(slot_idx)
        b        = _Bld(kind, manager, pos=(cx, cy), team=1, lane=lane)

        self._slot_map[slot_idx] = b
        ai_res.register_building(b)
        print(
            f"[AI] Built {kind}  slot={slot_idx}  lane={lane}  "
            f"col={self._col_of(slot_idx)}  minerals_left={ai_res.minerals}"
        )
        return b

    # ── Emergency nuke ────────────────────────────────────────────────────────
    def trigger_emergency_nuke(
        self,
        ai_res:    "ResourceManager",
        units:     list,
        ai_hq,                          # enemy_hq in GameLoop
        spawn_vfx,
    ) -> bool:
        """
        Defensive one-shot nuke.

        Condition
        ---------
        1. ai_res.nuke_available is True
        2. AI HQ hp  <  50 % of ai_hq.max_hp  (base is in danger)
        3. ≥ _NUKE_THREAT_COUNT (6) player units in the AI's half of the map

        Target: centroid of those threatening player units.
        Since the nuke is anti-unit only (Phase 4b), neither HQ is affected.

        Stores target pos in self.last_nuke_target so GameLoop can trigger
        the red-alert flash and screen shake.
        """
        if not ai_res.nuke_available:
            return False
        if ai_hq.hp >= int(ai_hq.max_hp * 0.5):
            return False    # HQ still healthy, no panic

        threats = self._player_units_in_ai_half(units)
        if len(threats) < _NUKE_THREAT_COUNT:
            return False

        tx = sum(u.pos[0] for u in threats) / len(threats)
        ty = sum(u.pos[1] for u in threats) / len(threats)
        self.last_nuke_target = (tx, ty)

        print(
            f"[AI] ☢ EMERGENCY NUKE  "
            f"hq_hp={ai_hq.hp}/{ai_hq.max_hp}  "
            f"threats={len(threats)}  target=({tx:.0f}, {ty:.0f})"
        )
        return ai_res.launch_nuke((tx, ty), units, spawn_vfx)

    # ── Main tick ─────────────────────────────────────────────────────────────
    def update(
        self,
        frame:     int,
        units:     list,
        ai_res:    "ResourceManager",
        manager:   "AssetManager",
        ai_hq,
        spawn_vfx,
    ) -> bool:
        """
        Called every game frame by GameLoop.

        Returns True on the frame an emergency nuke fires (so GameLoop can
        trigger screen shake / red-alert flash at the correct world position).

        Build decisions are throttled to once per _ACTION_COOLDOWN frames
        (120 frames = 2 s @ 60 fps) to prevent CPU / resource spam.
        The emergency nuke check is NOT throttled — it reacts immediately.
        """
        # ── 1) Lazily remove dead buildings (frees slots for rebuilding) ──────
        dead = [k for k, b in self._slot_map.items() if b.is_dead]
        for k in dead:
            del self._slot_map[k]
            print(f"[AI] slot {k} freed (building destroyed)")

        # ── 2) Emergency nuke (runs every frame, unthrottled) ─────────────────
        nuke_fired = self.trigger_emergency_nuke(ai_res, units, ai_hq, spawn_vfx)
        if nuke_fired:
            return True

        # ── 3) Build decision (throttled) ─────────────────────────────────────
        if frame - self._last_act_frame < _ACTION_COOLDOWN:
            return False
        self._last_act_frame = frame

        if len(self._slot_map) >= 32:
            return False   # grid is full

        if frame < _EARLY_GAME_FRAMES:
            # ── Early game: income first (70 % Refinery in rear) ─────────────
            if random.random() < 0.70:
                self._try_build(
                    "refinery",
                    self._free_slots(col_filter=_REAR_COLS),
                    ai_res, manager,
                )
            else:
                self._try_build(
                    "barracks",
                    self._free_slots(),
                    ai_res, manager,
                )
        else:
            # ── Mid game: unit pressure in weakest player lane ────────────────
            if random.random() < 0.80:
                target_lane = self._weakest_player_lane(units)
                front       = self._free_slots(col_filter=_FRONT_COLS, lane=target_lane)
                if not front:
                    # Preferred lane full — fall back to any front slot
                    front = self._free_slots(col_filter=_FRONT_COLS)
                self._try_build("barracks", front, ai_res, manager)
            else:
                self._try_build(
                    "refinery",
                    self._free_slots(),
                    ai_res, manager,
                )

        return False
