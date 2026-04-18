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
    "barracks":      100,
    "refinery":      200,
    "rover_bay":     150,
    "spec_ops":      250,
    "heavy_factory": 300,
    "starport":      350,
    "turret":        150,
    # Swarm faction
    "acid_pool":     80,
    "toxin_chamber": 120,
    # Rogue AI faction
    "logic_core":      140,
    "data_node":        90,
    "quantum_array":   240,
    "assembly_matrix": 180,
    "plasma_tower":    150,
}

# Phase / timing (all in seconds — decoupled from frame rate)
_EARLY_GAME_SECS   = 180.0       # 3 min early-game phase
_ACTION_COOLDOWN   = 2.0         # seconds between build decisions
_NUKE_THREAT_COUNT = 6           # min enemy units in own half to trigger nuke
_DEMOLISH_COOLDOWN = 12.0        # min seconds between AI self-demolitions
_NEAR_FULL_THRESH  = 30          # slots occupied before demolish logic activates

# ── Default build weights ─────────────────────────────────────────────────────
# One entry per buildable kind.  Threat analysis multiplies these.
# Weights are reset to _BASE_WEIGHTS at the start of each _analyze_threats call.
_BASE_WEIGHTS: dict[str, float] = {
    "barracks":      1.0,
    "refinery":      1.0,
    "rover_bay":     1.0,
    "spec_ops":      1.0,
    "heavy_factory": 1.0,
    "starport":      1.0,
    "turret":        0.4,   # built occasionally; boosted heavily when HQ is under pressure
}

# ── Per-building unit properties (mirror of sprite.py UNIT_STATS keys) ────────
# Used by _building_usefulness() to score owned buildings against current threats.
_BUILDING_UNIT: dict[str, dict] = {
    "barracks":      {"armor": "light",  "can_aa": True,  "is_flying": False},
    "rover_bay":     {"armor": "light",  "can_aa": False, "is_flying": False},
    "spec_ops":      {"armor": "light",  "can_aa": True,  "is_flying": False},
    "refinery":      {"armor": "heavy",  "can_aa": False, "is_flying": False},
    "heavy_factory": {"armor": "heavy",  "can_aa": False, "is_flying": False},
    "starport":      {"armor": "heavy",  "can_aa": True,  "is_flying": True},
    "turret":        {"armor": "structure", "can_aa": True,  "is_flying": False},
    # Swarm faction
    "acid_pool":     {"armor": "structure", "can_aa": False, "is_flying": False},
    "toxin_chamber": {"armor": "structure", "can_aa": False, "is_flying": False},
    # Rogue AI faction
    "logic_core":      {"armor": "structure", "can_aa": True,  "is_flying": False},
    "data_node":       {"armor": "structure", "can_aa": True,  "is_flying": False},
    "quantum_array":   {"armor": "structure", "can_aa": False, "is_flying": False},
    "assembly_matrix": {"armor": "structure", "can_aa": False, "is_flying": False},
    "plasma_tower":    {"armor": "structure", "can_aa": True,  "is_flying": False},
}


# ── Swarm faction constants ───────────────────────────────────────────────────
# The Swarm AI chooses between two dedicated production buildings:
#   • acid_pool     — cheap (80), spawns crawlers (fast melee swarmers)
#   • toxin_chamber — costlier (120), spawns spitters (ranged acid, anti-armour/air)
# Threat analysis biases the choice: flying / heavy threats → toxin_chamber,
# light / early-game → acid_pool.
_SWARM_ACID_BASE_WEIGHT:  float = 0.65
_SWARM_TOXIN_BASE_WEIGHT: float = 0.35


# ── Rogue AI faction constants ────────────────────────────────────────────────
# Strict 1-to-1 production buildings:
#   • logic_core      — cost 140, spawns observer (hover laser scout, AA capable)
#   • data_node       — cost 90,  spawns coder    (glass-cannon extreme-range sniper)
#   • quantum_array   — cost 240, spawns ravager  (tanky AoE bruiser)
#   • assembly_matrix — cost 180, spawns splitter (slow siege hammer)
#   • plasma_tower    — cost 150, pure defensive turret (no unit spawn)
# Threat analysis biases choice:
#   logic_core + data_node favoured vs air / light,
#   quantum_array + assembly_matrix favoured vs heavy armour / structures.
_ROGUE_LOGIC_BASE_WEIGHT:    float = 0.30
_ROGUE_DATA_BASE_WEIGHT:     float = 0.20
_ROGUE_QUANTUM_BASE_WEIGHT:  float = 0.25
_ROGUE_MATRIX_BASE_WEIGHT:   float = 0.20
_ROGUE_PLASMA_BASE_WEIGHT:   float = 0.05


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
    def _analyze_threats(self, player_units: list, my_hq=None) -> dict:
        """
        Count enemy unit types and update self._build_weights accordingly.

        Called every frame so the weights stay current even between build ticks.

        Threat → weight adjustments
        ----------------------------
        flying  > 3   : × 4 starport  (Valkyrie: air-to-air)
                        × 3 spec_ops  (Ghost: long-range AA)
                        × 0.5 barracks, × 0.4 rover_bay (ground AA only)
        heavy   > 5   : × 4 refinery  (Tank: siege vs heavy)
                        × 4 heavy_factory (Hellfire: siege AoE)
                        × 0.4 barracks, × 0.3 rover_bay (piercing/normal weak vs heavy)
        light   > 10  : × 3.5 heavy_factory (Hellfire: AoE shreds light masses)
                        × 2   rover_bay     (Jackal: fast, bonus vs light)
        hq_hp  < 40 % : × 5 turret   (emergency static defence ring around HQ)
                        × 2 spec_ops  (long-range interdiction)
        hq_hp  < 70 % : × 2 turret   (preventive defensive reinforcement)
        """
        living = [u for u in player_units if not u.is_dead]

        flying = sum(1 for u in living if getattr(u, "is_flying",   False))
        heavy  = sum(1 for u in living if getattr(u, "armor_type",  "") == "heavy")
        light  = sum(1 for u in living if getattr(u, "armor_type",  "") == "light")

        self._threat_cache = {"flying": flying, "heavy": heavy, "light": light}

        # Start from base weights each analysis
        w = dict(_BASE_WEIGHTS)

        if flying > 3:
            w["starport"]      *= 4.0
            w["spec_ops"]      *= 3.0
            w["barracks"]      *= 0.5
            w["rover_bay"]     *= 0.4
            print(
                f"[AI t{self.team}] ✈ Flying threat={flying}  "
                f"→ boosting starport×4 spec_ops×3"
            )

        if heavy > 5:
            w["refinery"]      *= 4.0
            w["heavy_factory"] *= 4.0
            w["barracks"]      *= 0.4
            w["rover_bay"]     *= 0.3
            print(
                f"[AI t{self.team}] 🛡 Heavy threat={heavy}  "
                f"→ boosting refinery×4 heavy_factory×4"
            )

        if light > 10:
            w["heavy_factory"] *= 3.5
            w["rover_bay"]     *= 2.0
            print(
                f"[AI t{self.team}] 🏃 Light-mass threat={light}  "
                f"→ boosting heavy_factory×3.5 rover_bay×2"
            )

        # HQ health-based turret escalation
        if my_hq is not None and my_hq.max_hp > 0:
            hp_ratio = my_hq.hp / my_hq.max_hp
            if hp_ratio < 0.40:
                w["turret"]    *= 5.0
                w["spec_ops"]  *= 2.0
                print(
                    f"[AI t{self.team}] 🏰 HQ critical ({my_hq.hp}/{my_hq.max_hp})  "
                    f"→ turret×5 spec_ops×2"
                )
            elif hp_ratio < 0.70:
                w["turret"]    *= 2.0

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
        # Defensive turrets are always somewhat useful — don't demolish them easily
        if kind == "turret":
            base = max(base, 0.6)
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

    # ── Swarm-faction build logic ─────────────────────────────────────────────
    def _swarm_pick_building(self, player_units: list | None) -> str:
        """
        Choose which Swarm production building to queue up this cycle.

        Each Swarm building now has a FIXED unit type:
          • acid_pool     → crawler  (cheap swarm melee)
          • toxin_chamber → spitter  (ranged acid; counters armour / air)

        Base odds: 65 % acid_pool, 35 % toxin_chamber.
        Threat override (applied in priority order):
          - Player has ≥ 4 flying units → toxin_chamber 75 %   (acid vs gunships)
          - Player has ≥ 6 heavy units  → toxin_chamber 65 %   (range beats armour)
          - Player has ≥ 12 light units → acid_pool      80 %  (overwhelm with numbers)
        """
        aw, tw = _SWARM_ACID_BASE_WEIGHT, _SWARM_TOXIN_BASE_WEIGHT
        if player_units:
            living = [u for u in player_units if not u.is_dead]
            flying = sum(1 for u in living if getattr(u, "is_flying",  False))
            heavy  = sum(1 for u in living if getattr(u, "armor_type", "") == "heavy")
            light  = sum(1 for u in living if getattr(u, "armor_type", "") == "light")
            if flying >= 4:
                aw, tw = 0.25, 0.75
                print(
                    f"[Swarm t{self.team}] ✈ Flying threat={flying} "
                    f"→ heavy toxin_chamber bias"
                )
            elif heavy >= 6:
                aw, tw = 0.35, 0.65
                print(
                    f"[Swarm t{self.team}] 🛡 Heavy threat={heavy} "
                    f"→ toxin_chamber bias"
                )
            elif light >= 12:
                aw, tw = 0.80, 0.20
                print(
                    f"[Swarm t{self.team}] 🏃 Light-mass threat={light} "
                    f"→ acid_pool bias"
                )
        return random.choices(["acid_pool", "toxin_chamber"], weights=[aw, tw], k=1)[0]

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
    def _rogue_pick_building(self, player_units: list | None, my_hq=None) -> str:
        """
        Choose which Rogue AI building to queue up this cycle.

        Roster (strict 1-to-1):
          • logic_core      → observer (hover laser scout, AA capable)
          • data_node       → coder    (extreme-range glass-cannon sniper)
          • quantum_array   → ravager  (tanky AoE bruiser)
          • assembly_matrix → splitter (slow siege hammer)
          • plasma_tower    → pure defence (no unit spawn, high DPS turret)

        Base odds: 30 % logic_core, 20 % data_node, 25 % quantum_array,
                   20 % assembly_matrix, 5 % plasma_tower.
        Threat override (priority order):
          - HQ hp < 40 % → plasma_tower 50 % (emergency static defence)
          - HQ hp < 70 % → plasma_tower 25 % (preventive defence ring)
          - Player has ≥ 4 flying units → logic_core 40 % + data_node 35 % (AA + sniper)
          - Player has ≥ 6 heavy  units → quantum_array 45 % + assembly_matrix 40 % (siege)
          - Player has ≥ 12 light units → quantum_array 50 % + assembly_matrix 35 % (AoE cleave)
        """
        lw = _ROGUE_LOGIC_BASE_WEIGHT
        dw = _ROGUE_DATA_BASE_WEIGHT
        qw = _ROGUE_QUANTUM_BASE_WEIGHT
        mw = _ROGUE_MATRIX_BASE_WEIGHT
        pw = _ROGUE_PLASMA_BASE_WEIGHT

        # HQ health escalates plasma_tower priority (mirrors Federation turret logic)
        if my_hq is not None and my_hq.max_hp > 0:
            hp_ratio = my_hq.hp / my_hq.max_hp
            if hp_ratio < 0.40:
                lw, dw, qw, mw, pw = 0.15, 0.10, 0.15, 0.10, 0.50
                print(
                    f"[Rogue t{self.team}] 🏰 HQ critical ({my_hq.hp}/{my_hq.max_hp}) "
                    f"→ plasma_tower 50 % (emergency defence)"
                )
            elif hp_ratio < 0.70:
                lw, dw, qw, mw, pw = 0.20, 0.15, 0.20, 0.20, 0.25
                print(
                    f"[Rogue t{self.team}] 🏰 HQ low ({my_hq.hp}/{my_hq.max_hp}) "
                    f"→ plasma_tower 25 % (preventive defence)"
                )

        if player_units:
            living = [u for u in player_units if not u.is_dead]
            flying = sum(1 for u in living if getattr(u, "is_flying",  False))
            heavy  = sum(1 for u in living if getattr(u, "armor_type", "") == "heavy")
            light  = sum(1 for u in living if getattr(u, "armor_type", "") == "light")
            # Only override unit-composition weights when HQ is not already in crisis
            if (my_hq is None or my_hq.hp / max(my_hq.max_hp, 1) >= 0.70):
                if flying >= 4:
                    lw, dw, qw, mw, pw = 0.40, 0.35, 0.10, 0.10, 0.05
                    print(
                        f"[Rogue t{self.team}] ✈ Flying threat={flying} "
                        f"→ logic_core+data_node bias (AA observer + coder snipers)"
                    )
                elif heavy >= 6:
                    lw, dw, qw, mw, pw = 0.10, 0.05, 0.45, 0.35, 0.05
                    print(
                        f"[Rogue t{self.team}] 🛡 Heavy threat={heavy} "
                        f"→ quantum_array+assembly_matrix bias (siege)"
                    )
                elif light >= 12:
                    lw, dw, qw, mw, pw = 0.05, 0.05, 0.50, 0.35, 0.05
                    print(
                        f"[Rogue t{self.team}] 🏃 Light-mass threat={light} "
                        f"→ quantum_array+assembly_matrix bias (AoE cleave)"
                    )
        return random.choices(
            ["logic_core", "data_node", "quantum_array", "assembly_matrix", "plasma_tower"],
            weights=[lw, dw, qw, mw, pw], k=1,
        )[0]

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
        my_hq,                          # this controller's own HQ (for nuke condition)
        spawn_vfx,
        player_units: list | None = None,   # living player units for threat analysis
    ) -> bool:
        """
        Called every game frame by GameLoop.

        Returns True on the frame an emergency nuke fires.

        Build decisions are throttled to once per _ACTION_COOLDOWN seconds.
        The emergency nuke check and threat analysis run every frame (unthrottled).

        Threat-reactive build pipeline (new)
        -------------------------------------
        Each frame:
          1. Lazily free slots of destroyed buildings.
          2. Recompute threat weights from player_units (if provided).
          3. Check emergency nuke.
          4. On build tick:
             a. If near grid capacity (≥ _NEAR_FULL_THRESH slots filled), attempt
                to demolish the least-useful building (self-financed; 60 % refund).
             b. Choose a building kind via _weighted_build_kind() which reflects
                the current threat weights.
             c. Place it in the best available slot.
        """
        # ── 1) Lazily remove dead buildings (frees slots for rebuilding) ──────
        dead = [k for k, b in self._slot_map.items() if b.is_dead]
        for k in dead:
            del self._slot_map[k]
            print(f"[AI t{self.team}] slot {k} freed (building destroyed)")

        # ── 2) Threat analysis — runs every frame so weights are always fresh ──
        if player_units is not None:
            self._analyze_threats(player_units, my_hq=my_hq)

        # ── 3) Emergency nuke (unthrottled) ───────────────────────────────────
        if self.trigger_emergency_nuke(units, my_hq, spawn_vfx):
            return True

        # ── 4) Build decision (throttled to 1 per _ACTION_COOLDOWN seconds) ───
        if play_time - self._last_act_time < _ACTION_COOLDOWN:
            return False
        self._last_act_time = play_time

        # ── 4a) Near-capacity: try to demolish a low-value building ───────────
        if len(self._slot_map) >= _NEAR_FULL_THRESH:
            self._try_demolish_least_useful(play_time)
            # Slot may now be free; fall through to build phase below.

        if len(self._slot_map) >= len(self.slots):
            return False   # grid still full even after demolish attempt

        # ── 4b) Choose building kind via threat-reactive weights ──────────────
        if self.faction == "swarm":
            # ── SWARM: threat-weighted choice between acid_pool & toxin_chamber ──
            chosen_kind = self._swarm_pick_building(player_units)
            target_lane = self._weakest_enemy_lane(units)
            # Spread across all slots; prefer front cols to push aggressively
            slots = (
                self._free_slots(col_filter=_FRONT_COLS, lane=target_lane)
                or self._free_slots(col_filter=_FRONT_COLS)
                or self._free_slots()
            )
            self._try_build_swarm(chosen_kind, slots, manager)

        elif self.faction == "rogue_ai":
            # ── ROGUE AI: threat-weighted choice across 5 building types ──────────
            # Placement strategy:
            #   REAR cols : logic_core, data_node (ranged/sniper), plasma_tower (defence)
            #   FRONT cols: quantum_array, assembly_matrix (siege/pressure)
            chosen_kind = self._rogue_pick_building(player_units, my_hq=my_hq)
            target_lane = self._weakest_enemy_lane(units)
            _ROGUE_REAR  = {"logic_core", "data_node", "plasma_tower"}
            if chosen_kind in _ROGUE_REAR:
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
            self._try_build_rogue(chosen_kind, slots, manager)

        elif play_time < _EARLY_GAME_SECS:
            # Early game: secure economy first (20 % refinery), then
            # let threat weights guide the rest of the builds.
            if random.random() < 0.20:
                self._try_build(
                    "refinery",
                    self._free_slots(col_filter=_REAR_COLS),
                    manager,
                )
            else:
                kind = self._weighted_build_kind()
                slots = (
                    self._free_slots(col_filter=_REAR_COLS) or self._free_slots()
                ) if kind == "turret" else self._free_slots()
                self._try_build(kind, slots, manager)
        else:
            # Mid / late game: fully threat-reactive.
            # Turrets always go in rear (defensive) cols; other buildings prefer
            # the front of the weakest enemy lane.
            kind = self._weighted_build_kind()
            if kind == "turret":
                slots = self._free_slots(col_filter=_REAR_COLS) or self._free_slots()
            else:
                target_lane = self._weakest_enemy_lane(units)
                slots = (
                    self._free_slots(col_filter=_FRONT_COLS, lane=target_lane)
                    or self._free_slots(col_filter=_FRONT_COLS)
                    or self._free_slots()
                )
            self._try_build(kind, slots, manager)

        return False
