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
_COSTS: dict[str, int] = {
    # Federation
    "barracks":      100,
    "rover_bay":     150,
    "spec_ops":      250,
    "refinery":      200,
    "heavy_factory": 300,
    "starport":      350,
    # Swarm
    "acid_pool":     100,
    "toxin_chamber": 140,
    "spine_ridge":   160,
    "mutation_pit":  250,
    "scourge_nest":  150,
    "hive_nest":     200,
    # Rogue AI
    "sensor_array":    120,
    "assembly_matrix": 150,
    "plasma_forge":    200,
    "data_node":       280,
    "quantum_core":    320,
    "oblivion_engine": 350,
}

# Phase / timing (all in seconds — decoupled from frame rate)
_EARLY_GAME_SECS   = 180.0       # 3 min early-game phase
_ACTION_COOLDOWN   = 2.0         # seconds between build decisions
_NUKE_THREAT_COUNT = 6           # min enemy units in own half to trigger nuke
_DEMOLISH_COOLDOWN = 12.0        # min seconds between AI self-demolitions
_NEAR_FULL_THRESH  = 30          # slots occupied before demolish logic activates

# ── Default build weights (Federation only — used by _building_usefulness) ────
# Weights are reset to _BASE_WEIGHTS at the start of each _analyze_threats call.
_BASE_WEIGHTS: dict[str, float] = {
    "barracks":      1.0,
    "refinery":      1.0,
    "rover_bay":     1.0,
    "spec_ops":      1.0,
    "heavy_factory": 1.0,
    "starport":      1.0,
}

# ── Per-building unit properties (mirror of sprite.py UNIT_STATS keys) ────────
# Used by _building_usefulness() to score owned buildings against current threats.
_BUILDING_UNIT: dict[str, dict] = {
    # Federation
    "barracks":      {"armor": "light",  "can_aa": True,  "is_flying": False},
    "rover_bay":     {"armor": "light",  "can_aa": False, "is_flying": False},
    "spec_ops":      {"armor": "light",  "can_aa": True,  "is_flying": False},
    "refinery":      {"armor": "heavy",  "can_aa": False, "is_flying": False},
    "heavy_factory": {"armor": "heavy",  "can_aa": False, "is_flying": False},
    "starport":      {"armor": "heavy",  "can_aa": True,  "is_flying": True},
    # Swarm
    "acid_pool":     {"armor": "structure", "can_aa": False, "is_flying": False},
    "toxin_chamber": {"armor": "structure", "can_aa": True,  "is_flying": False},
    "spine_ridge":   {"armor": "structure", "can_aa": False, "is_flying": False},
    "mutation_pit":  {"armor": "structure", "can_aa": False, "is_flying": False},
    "scourge_nest":  {"armor": "structure", "can_aa": True,  "is_flying": False},
    "hive_nest":     {"armor": "structure", "can_aa": True,  "is_flying": False},
    # Rogue AI
    "sensor_array":    {"armor": "structure", "can_aa": True,  "is_flying": False},
    "assembly_matrix": {"armor": "structure", "can_aa": False, "is_flying": False},
    "plasma_forge":    {"armor": "structure", "can_aa": True,  "is_flying": False},
    "data_node":       {"armor": "structure", "can_aa": True,  "is_flying": False},
    "quantum_core":    {"armor": "structure", "can_aa": False, "is_flying": False},
    "oblivion_engine": {"armor": "structure", "can_aa": False, "is_flying": False},
}


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
        faction:           str  = "federation",
    ) -> None:
        # Team identity
        self.team        = team
        self.enemy_team  = enemy_team
        self.is_left     = is_left
        # Faction tag — used for UI display and future faction-specific behaviour
        self.faction     = faction

        # Slot grid (defaults to right-side AI mirror grid)
        self.slots: list[tuple[int, int]] = (
            slots if slots is not None else AI_ALL_SLOTS
        )

        # Own economy — independent from player's ResourceManager
        from src.logic import ResourceManager as _RM
        self.res = _RM(starting=starting_minerals)

        # slot_idx → Building sprite  (dead buildings lazily removed)
        self._slot_map:      dict[int, "Building"] = {}
        self._last_act_time: float                 = -_ACTION_COOLDOWN   # allow instant first build
        # Set when emergency nuke fires; read by GameLoop for VFX
        self.last_nuke_target: tuple[float, float] | None = None

        # ── Threat-analysis state ─────────────────────────────────────────────
        # Live copy of weights — reset + re-multiplied each _analyze_threats call
        self._build_weights:       dict[str, float] = dict(_BASE_WEIGHTS)
        # Last demolish timestamp (prevents rapid chain-demolition)
        self._last_demolish_time:  float            = -_DEMOLISH_COOLDOWN
        # Cached threat counts from the most recent analysis (for logging/debug)
        self._threat_cache:        dict             = {"flying": 0, "heavy": 0, "light": 0}

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

    # ── Threat analysis ───────────────────────────────────────────────────────
    def _analyze_threats(self, enemy_stats: dict, my_hq=None) -> dict:
        flying = enemy_stats.get("flying", 0)
        heavy  = enemy_stats.get("heavy", 0)
        light  = enemy_stats.get("light", 0)

        self._threat_cache = {"flying": flying, "heavy": heavy, "light": light}
        w = dict(_BASE_WEIGHTS)

        if flying > 3:
            w["starport"] *= 4.0
            w["spec_ops"] *= 3.0
            w["barracks"] *= 0.5
            w["rover_bay"] *= 0.4
        if heavy > 5:
            w["refinery"] *= 4.0
            w["heavy_factory"] *= 4.0
            w["barracks"] *= 0.4
            w["rover_bay"] *= 0.3
        if light > 10:
            w["heavy_factory"] *= 3.5
            w["rover_bay"] *= 2.0

        if my_hq is not None and my_hq.max_hp > 0:
            hp_ratio = my_hq.hp / my_hq.max_hp
            if hp_ratio < 0.40:
                w["barracks"] *= 3.0
                w["spec_ops"] *= 2.0
            elif hp_ratio < 0.70:
                w["barracks"] *= 1.5

        self._build_weights = w
        return self._threat_cache

    def _weighted_build_kind(self) -> str:
        """Pick a building kind via weighted random using current _build_weights."""
        kinds   = list(self._build_weights.keys())
        weights = [self._build_weights[k] for k in kinds]
        return random.choices(kinds, weights=weights, k=1)[0]

    def _building_usefulness(self, kind: str) -> float:
        """
        Usefulness score for an owned building given current threat weights.

        We use the current build weight as a proxy: a building whose unit type
        is heavily counter-indicated will have a low weight → low usefulness →
        candidate for demolition.  Refinery gets a small floor bonus because
        economy is always valuable.
        """
        base = self._build_weights.get(kind, 1.0)
        # Income buildings are worth keeping unless we have many of them
        if kind == "refinery":
            base = max(base, 1.5)
        return base

    def _try_demolish_least_useful(self, play_time: float) -> bool:
        """
        When near grid capacity, find and demolish the least-useful building.

        Rules
        -----
        • Cooldown: at most one demolition every _DEMOLISH_COOLDOWN seconds.
        • Never demolish if fewer than 3 refineries exist and the target is a
          refinery (keeps a minimum economic base).
        • Picks the building with the lowest _building_usefulness() score,
          breaking ties by lowest HP (damaged buildings have less value).

        Returns True if a demolition was executed.
        """
        if play_time - self._last_demolish_time < _DEMOLISH_COOLDOWN:
            return False
        if not self._slot_map:
            return False

        # Count income buildings for the safety floor
        refinery_count = sum(
            1 for b in self._slot_map.values() if b.kind == "refinery"
        )

        # Sort candidates by usefulness ascending, then HP ascending as tiebreak
        candidates = sorted(
            self._slot_map.items(),
            key=lambda kv: (
                self._building_usefulness(kv[1].kind),
                kv[1].hp,
            ),
        )

        for slot_idx, building in candidates:
            if building.kind == "refinery" and refinery_count <= 2:
                continue   # protect minimum economy
            # Execute demolish: refunds 60 % cost to AI res, marks dead
            building.demolish(self.res)
            del self._slot_map[slot_idx]
            self._last_demolish_time = play_time
            print(
                f"[AI t{self.team}] 🔨 Demolished {building.kind} "
                f"slot={slot_idx}  "
                f"usefulness={self._building_usefulness(building.kind):.2f}  "
                f"threats={self._threat_cache}"
            )
            return True

        return False

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

    # ── Federation-faction build logic ────────────────────────────────────────
    def _fed_pick_building(self, enemy_stats: dict, my_hq=None) -> str:
        w = {"barracks": 0.25, "rover_bay": 0.20, "spec_ops": 0.15,
             "refinery": 0.20, "heavy_factory": 0.10, "starport": 0.10}
        if my_hq and my_hq.max_hp > 0 and (my_hq.hp / my_hq.max_hp) < 0.4:
            return "barracks"   # 緊急防禦：大量生出步兵扛線

        flying = enemy_stats.get("flying", 0)
        heavy  = enemy_stats.get("heavy",  0)
        light  = enemy_stats.get("light",  0)

        if flying > 3: w["spec_ops"] += 0.4; w["starport"] += 0.2
        if heavy > 5:  w["refinery"] += 0.4; w["heavy_factory"] += 0.3
        if light > 10: w["heavy_factory"] += 0.5; w["rover_bay"] += 0.2

        choices, weights = list(w.keys()), list(w.values())
        return random.choices(choices, weights=weights, k=1)[0]

    # ── Swarm-faction build logic ─────────────────────────────────────────────
    def _swarm_pick_building(self, enemy_stats: dict, my_hq=None) -> str:
        w = {"acid_pool": 0.30, "toxin_chamber": 0.15, "spine_ridge": 0.15,
             "mutation_pit": 0.15, "scourge_nest": 0.10, "hive_nest": 0.15}
        if my_hq and my_hq.max_hp > 0 and (my_hq.hp / my_hq.max_hp) < 0.4:
            return "acid_pool"   # 緊急防禦：雙胞胎肉盾海

        flying = enemy_stats.get("flying", 0)
        heavy  = enemy_stats.get("heavy",  0)
        light  = enemy_stats.get("light",  0)

        if flying > 3: w["toxin_chamber"] += 0.3; w["scourge_nest"] += 0.3; w["hive_nest"] += 0.1
        if heavy > 5:  w["spine_ridge"] += 0.4; w["mutation_pit"] += 0.3
        if light > 10: w["acid_pool"] += 0.4; w["mutation_pit"] += 0.2

        choices, weights = list(w.keys()), list(w.values())
        return random.choices(choices, weights=weights, k=1)[0]

    def _try_build_swarm(
        self,
        kind:       str,
        candidates: list[int],
        manager:    "AssetManager",
    ) -> "Building | None":
        """
        Place a Swarm production building (acid_pool or toxin_chamber) at a
        random candidate slot.  Each kind has a fixed unit_type baked into
        BUILDING_SPECS, so no post-construction patching is needed.
        """
        if not candidates:
            return None
        cost = _COSTS.get(kind, 99_999)
        if not self.res.spend(cost):
            return None

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
            f"[Swarm t{self.team}] Built {kind}→{b.unit_type}  "
            f"slot={slot_idx}  lane={lane}  minerals_left={self.res.minerals}"
        )
        return b

    # ── Rogue-AI-faction build logic ──────────────────────────────────────────
    def _rogue_pick_building(self, enemy_stats: dict, my_hq=None) -> str:
        w = {"sensor_array": 0.20, "assembly_matrix": 0.20, "plasma_forge": 0.15,
             "data_node": 0.15, "quantum_core": 0.15, "oblivion_engine": 0.15}
        if my_hq and my_hq.max_hp > 0 and (my_hq.hp / my_hq.max_hp) < 0.4:
            return "assembly_matrix"   # 緊急防禦：快速射擊機甲

        flying = enemy_stats.get("flying", 0)
        heavy  = enemy_stats.get("heavy",  0)
        light  = enemy_stats.get("light",  0)

        if flying > 3: w["sensor_array"] += 0.3; w["plasma_forge"] += 0.3
        if heavy > 5:  w["quantum_core"] += 0.5; w["oblivion_engine"] += 0.2
        if light > 10: w["assembly_matrix"] += 0.5; w["data_node"] += 0.2

        choices, weights = list(w.keys()), list(w.values())
        return random.choices(choices, weights=weights, k=1)[0]

    def _try_build_rogue(
        self,
        kind:       str,
        candidates: list[int],
        manager:    "AssetManager",
    ) -> "Building | None":
        """
        Place a Rogue AI building at a random candidate slot.
        Each kind has a fixed unit_type baked into BUILDING_SPECS (1-to-1).
        """
        if not candidates:
            return None
        cost = _COSTS.get(kind, 99_999)
        if not self.res.spend(cost):
            return None

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
            f"[Rogue t{self.team}] Built {kind}→{b.unit_type}  "
            f"slot={slot_idx}  lane={lane}  minerals_left={self.res.minerals}"
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
        play_time:    float,
        units:        list,
        manager:      "AssetManager",
        my_hq,
        spawn_vfx,
        team_stats:   dict | None = None,
    ) -> bool:
        dead = [k for k, b in self._slot_map.items() if b.is_dead]
        for k in dead:
            del self._slot_map[k]

        enemy_stats = team_stats.get(self.enemy_team, {"units": [], "flying": 0, "heavy": 0, "light": 0}) if team_stats else {"units": [], "flying": 0, "heavy": 0, "light": 0}

        self._analyze_threats(enemy_stats, my_hq=my_hq)

        if self.trigger_emergency_nuke(enemy_stats.get("units", []), my_hq, spawn_vfx):
            return True

        if play_time - self._last_act_time < _ACTION_COOLDOWN:
            return False
        self._last_act_time = play_time

        if len(self._slot_map) >= _NEAR_FULL_THRESH:
            self._try_demolish_least_useful(play_time)

        if len(self._slot_map) >= len(self.slots):
            return False

        if self.faction == "swarm":
            chosen_kind = self._swarm_pick_building(enemy_stats, my_hq=my_hq)
            target_lane = self._weakest_enemy_lane(units)
            _SWARM_REAR = {"toxin_chamber", "mutation_pit", "scourge_nest"}
            if chosen_kind in _SWARM_REAR:
                slots = (
                    self._free_slots(col_filter=_REAR_COLS, lane=target_lane)
                    or self._free_slots(col_filter=_REAR_COLS)
                    or self._free_slots()
                )
            else:
                slots = (
                    self._free_slots(col_filter=_FRONT_COLS, lane=target_lane)
                    or self._free_slots(col_filter=_FRONT_COLS)
                    or self._free_slots()
                )
            self._try_build_swarm(chosen_kind, slots, manager)
        elif self.faction == "rogue_ai":
            chosen_kind = self._rogue_pick_building(enemy_stats, my_hq=my_hq)
            target_lane = self._weakest_enemy_lane(units)
            _ROGUE_REAR = {"data_node", "oblivion_engine", "quantum_core"}
            if chosen_kind in _ROGUE_REAR:
                slots = (self._free_slots(col_filter=_REAR_COLS, lane=target_lane) or self._free_slots(col_filter=_REAR_COLS) or self._free_slots())
            else:
                slots = (self._free_slots(col_filter=_FRONT_COLS, lane=target_lane) or self._free_slots(col_filter=_FRONT_COLS) or self._free_slots())
            self._try_build_rogue(chosen_kind, slots, manager)
        else:
            chosen_kind = self._fed_pick_building(enemy_stats, my_hq=my_hq)
            target_lane = self._weakest_enemy_lane(units)
            _FED_REAR = {"spec_ops", "heavy_factory", "starport"}
            if chosen_kind in _FED_REAR:
                slots = (
                    self._free_slots(col_filter=_REAR_COLS, lane=target_lane)
                    or self._free_slots(col_filter=_REAR_COLS)
                    or self._free_slots()
                )
            else:
                slots = (
                    self._free_slots(col_filter=_FRONT_COLS, lane=target_lane)
                    or self._free_slots(col_filter=_FRONT_COLS)
                    or self._free_slots()
                )
            self._try_build(chosen_kind, slots, manager)

        return False
