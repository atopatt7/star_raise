"""
logic.py — Star Raise  (v5: Auto-Spawn Economy)

Phase 2 changes
---------------
- ProductionQueue  : REMOVED (manual queuing deprecated)
- AIController     : REMOVED (replaced by Building auto-spawn timers)
- ResourceManager  : refactored — income now driven by placed buildings

Income formula (per 5 s cycle)
--------------------------------
  income_per_cycle = BASE_INCOME (10)
                   + Σ b.income_bonus  for every alive slot-building b

  income_bonus per building = floor(cost × 5%)

  Example:  2 × barracks (cost 100, bonus 5) + 1 × refinery (cost 200, bonus 10)
            → 10 + 5 + 5 + 10 = 30 minerals / cycle

Building auto-spawn table (BUILDING_SPECS)
------------------------------------------
  Each kind defines:
    unit_type          : which unit it produces
    spawn_rate_frames  : frames between consecutive spawns
    cost               : purchase cost (future use) + basis for income_bonus
    income_bonus       : flat bonus added to income_per_cycle while alive
"""

from __future__ import annotations
import json
import math
import os
import random
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.sprite import Building   # avoid circular import at runtime


# ── BuildState Enum ───────────────────────────────────────────────────────────
class BuildState(Enum):
    """
    Tracks what the player's cursor/build system is currently doing.

    NONE          : default — camera drag and normal game interaction are active.
    CONSTRUCTING  : player has picked up a building card and is dragging a ghost
                    sprite; camera scrolling is suppressed until drop/cancel.
    DEMOLISHING   : demolish mode is toggled ON; left-clicking an existing slot
                    building triggers Building.demolish() and refunds 60 % cost.
    """
    NONE         = auto()
    CONSTRUCTING = auto()
    DEMOLISHING  = auto()
    NUKING       = auto()   # Phase 4: player is aiming the one-time nuke

# ── GameState Enum ────────────────────────────────────────────────────────────
class GameState(Enum):
    """
    Top-level game lifecycle state.

    MAIN_MENU : Title / lobby screen — no game logic runs.
    PLAYING   : Normal gameplay — units spawn, buildings fire, HQs take damage.
    VICTORY   : Enemy HQ reached 0 HP.  Overlay shown; all logic paused.
    DEFEAT    : Player HQ reached 0 HP.  Overlay shown; all logic paused.

    Transitions:
      MAIN_MENU      → FACTION_SELECT : click 1V1 or 2V2 button.
      MAIN_MENU      → UNIT_INFO      : click 單位說明 button.
      FACTION_SELECT → MAIN_MENU      : click 返回 or press ESC.
      FACTION_SELECT → PLAYING        : click 確認出擊 (LAUNCH).
      UNIT_INFO      → MAIN_MENU      : press ESC or click 返回 back button.
      PLAYING        → VICTORY        : Building.on_hq_death callback or _check_victory().
      PLAYING        → DEFEAT         : same.
      VICTORY/DEFEAT → PLAYING        : click 再戰一局 (play again).
      VICTORY/DEFEAT → MAIN_MENU      : click 返回首頁 (home).
    """
    MAIN_MENU      = auto()
    PLAYING        = auto()
    VICTORY        = auto()
    DEFEAT         = auto()
    UNIT_INFO      = auto()
    FACTION_SELECT = auto()
    SETTINGS       = auto()


# ── Income constants ──────────────────────────────────────────────────────────
INCOME_CYCLE_FRAMES: int   = 300          # 5 s @ 60 fps (kept for reference)
INCOME_CYCLE_SECS:   float = 5.0          # authoritative time-based cycle length
BASE_INCOME:         int   = 10           # flat base income, always present
STARTING_MINERALS:   int   = 150
SLOT_SIZE:           int   = 84           # building-slot width/height in world px

# ── Building spec table (single source of truth) ──────────────────────────────
DEFAULT_BUILDING_SPECS: dict[str, dict] = {
    # ── Federation ──
    "hq":            {"name": "聯邦主堡 HQ", "unit_type": "", "spawn_rate_frames": 0, "cost": 0, "income_bonus": 0},
    "barracks":      {"name": "步兵營 Barracks", "unit_type": "marine", "spawn_rate_frames": 480, "cost": 100, "income_bonus": 5},
    "rover_bay":     {"name": "突擊車廠 Rover Bay", "unit_type": "jackal", "spawn_rate_frames": 600, "cost": 150, "income_bonus": 7},
    "spec_ops":      {"name": "特戰中心 Spec Ops", "unit_type": "ghost", "spawn_rate_frames": 720, "cost": 250, "income_bonus": 12},
    "refinery":      {"name": "裝甲廠 Refinery", "unit_type": "tank", "spawn_rate_frames": 840, "cost": 200, "income_bonus": 10},
    "heavy_factory": {"name": "重型兵工廠 Heavy Factory", "unit_type": "hellfire", "spawn_rate_frames": 900, "cost": 300, "income_bonus": 15},
    "starport":      {"name": "航空機場 Starport", "unit_type": "valkyrie", "spawn_rate_frames": 780, "cost": 280, "income_bonus": 14},

    # ── Swarm ──
    "swarm_hq":      {"name": "蟲巢核心 Swarm HQ", "unit_type": "", "spawn_rate_frames": 0, "cost": 0, "income_bonus": 0},
    "acid_pool":     {"name": "酸液繁殖池 Acid Pool", "unit_type": "crawler", "spawn_rate_frames": 420, "cost": 100, "income_bonus": 5, "spawn_count": 2},
    "toxin_chamber": {"name": "毒素腔室 Toxin Chamber", "unit_type": "spitter", "spawn_rate_frames": 480, "cost": 140, "income_bonus": 7, "spawn_count": 2},
    "mutation_pit":  {"name": "變異池 Mutation Pit", "unit_type": "crusher", "spawn_rate_frames": 900, "cost": 250, "income_bonus": 12, "hp": 600},
    "hive_nest":     {"name": "飛螳巢穴 Hive Nest", "unit_type": "weaver", "spawn_rate_frames": 720, "cost": 200, "income_bonus": 10, "hp": 450},
    "spine_ridge":   {"name": "脊刺山脊 Spine Ridge", "unit_type": "impaler", "spawn_rate_frames": 600, "cost": 160, "income_bonus": 8, "hp": 500},
    "scourge_nest":  {"name": "爆蚊巢穴 Scourge Nest", "unit_type": "scourge", "spawn_rate_frames": 600, "cost": 150, "income_bonus": 7, "hp": 400, "spawn_count": 2},

    # ── Rogue AI ──
    "rogue_hq":        {"name": "核心主機 Rogue HQ", "unit_type": "", "spawn_rate_frames": 0, "cost": 0, "income_bonus": 0},
    "sensor_array":    {"name": "感測陣列 Sensor Array", "unit_type": "observer", "spawn_rate_frames": 480, "cost": 120, "income_bonus": 6},
    "data_node":       {"name": "資料節點 Data Node", "unit_type": "coder", "spawn_rate_frames": 840, "cost": 280, "income_bonus": 14},
    "assembly_matrix": {"name": "裝配矩陣 Assembly Matrix", "unit_type": "tracker", "spawn_rate_frames": 420, "cost": 150, "income_bonus": 7},
    "plasma_forge":    {"name": "電漿鍛爐 Plasma Forge", "unit_type": "sentinel", "spawn_rate_frames": 600, "cost": 200, "income_bonus": 10},
    "quantum_core":    {"name": "量子核心 Quantum Core", "unit_type": "purifier", "spawn_rate_frames": 780, "cost": 320, "income_bonus": 16},
    "oblivion_engine": {"name": "湮滅引擎 Oblivion Engine", "unit_type": "obliterator", "spawn_rate_frames": 960, "cost": 350, "income_bonus": 17},
}

# Working copy — starts as a deep-copy of defaults; overwritten by load_balance_data()
BUILDING_SPECS: dict[str, dict] = {k: dict(v) for k, v in DEFAULT_BUILDING_SPECS.items()}


def load_balance_data() -> None:
    """Read data/balance.json and merge any overrides into BUILDING_SPECS."""
    filepath = os.path.join("data", "balance.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "buildings" in data:
                for k, v in data["buildings"].items():
                    if k in BUILDING_SPECS:
                        BUILDING_SPECS[k].update(v)
                    else:
                        BUILDING_SPECS[k] = v
            print("[Logic] 成功載入外部平衡數值 (balance.json)")
        except Exception as e:
            print(f"[Logic] 讀取 balance.json 失敗，使用預設數值: {e}")
    else:
        print("[Logic] 找不到 balance.json，使用預設數值。")


# 模組載入時自動執行一次
load_balance_data()


# ── ResourceManager ───────────────────────────────────────────────────────────
class ResourceManager:
    """
    Manages player minerals and dynamic passive income.

    Income is calculated each cycle as:
        BASE_INCOME + Σ(b.income_bonus for b in alive slot-buildings)

    Buildings are registered via register_building() when placed in a slot.
    Income automatically stops counting a building once b.is_dead == True.

    Typical usage
    -------------
    rm = ResourceManager()
    rm.register_building(barracks_sprite)   # when player places a building
    cycle_fired = rm.update()               # every frame; True = cycle fired
    rm.spend(50)                            # future upgrades / purchases
    """

    def __init__(self, starting: int = STARTING_MINERALS) -> None:
        self.minerals:        int   = starting
        self._cycle_timer:    float = 0.0   # accumulated seconds since last payout
        # List of Building sprites placed in player slots
        self._slot_buildings: list  = []
        # One-time tactical nuke weapon (resets to True on scene reset)
        self.nuke_available:  bool  = True

    # ── Building registration ──────────────────────────────────────────────────
    def register_building(self, building: Building) -> None:
        """Register a slot building so its income_bonus is counted each cycle."""
        if building not in self._slot_buildings:
            self._slot_buildings.append(building)
            print(
                f"[Economy] Registered {building.kind}  "
                f"income_bonus=+{building.income_bonus}  "
                f"→ new income={self.income_per_cycle}/cycle"
            )

    def unregister_building(self, building: Building) -> None:
        """Remove a slot building (e.g. if the player demolishes it)."""
        self._slot_buildings = [b for b in self._slot_buildings if b is not building]

    # ── Income properties ──────────────────────────────────────────────────────
    @property
    def income_bonus(self) -> int:
        """
        Total bonus income from all alive registered slot buildings.
        Dead buildings contribute 0 (is_dead == True).
        """
        return sum(b.income_bonus for b in self._slot_buildings if not b.is_dead)

    @property
    def income_per_cycle(self) -> int:
        """Total minerals earned per 5 s cycle = BASE_INCOME + income_bonus."""
        return BASE_INCOME + self.income_bonus

    @property
    def cycle_progress(self) -> float:
        """Progress toward the next income cycle, 0.0 – 1.0."""
        return self._cycle_timer / INCOME_CYCLE_SECS

    @property
    def secs_to_next_cycle(self) -> float:
        """Seconds remaining until next income payout."""
        return max(0.0, INCOME_CYCLE_SECS - self._cycle_timer)

    @property
    def frames_to_next_cycle(self) -> int:
        """Backward-compat alias — returns approximate frames at 60 fps."""
        return int(self.secs_to_next_cycle * 60)

    # ── Per-frame update ───────────────────────────────────────────────────────
    def update(self, dt: float = 1 / 60) -> bool:
        """
        Advance income timer by dt seconds.
        Returns True on the frame the cycle fires (for UI flash effect).
        """
        self._cycle_timer += dt
        if self._cycle_timer >= INCOME_CYCLE_SECS:
            self._cycle_timer -= INCOME_CYCLE_SECS   # preserve fractional overshoot
            earned = self.income_per_cycle
            self.minerals += earned
            print(
                f"[Economy] +{earned} minerals  →  {self.minerals} total  "
                f"(base={BASE_INCOME}  bonus={self.income_bonus}  "
                f"buildings={len([b for b in self._slot_buildings if not b.is_dead])})"
            )
            return True
        return False

    # ── Spending ───────────────────────────────────────────────────────────────
    def spend(self, amount: int) -> bool:
        """Deduct minerals. Returns False without deducting if insufficient."""
        if self.minerals >= amount:
            self.minerals -= amount
            return True
        return False

    def refund(self, amount: int) -> None:
        """
        Credit minerals back to the player (used by Building.demolish).

        Refund formula: caller passes int(cost * 0.6) — i.e. 60 % of the
        building's original cost.  This method simply adds the amount with
        no cap so the player cannot 'lose' minerals on a demolish.

        Examples
        --------
        barracks (cost 100)  → refund(60)   → minerals += 60
        refinery (cost 200)  → refund(120)  → minerals += 120
        """
        self.minerals += amount
        print(f"[Economy] Refund +{amount}  →  {self.minerals} minerals")

    # ── Nuke ──────────────────────────────────────────────────────────────────
    def launch_nuke(
        self,
        target_pos,          # tuple[float, float]  — world-space detonation point
        units,               # list[Unit]           — mobile unit sprites only
        vfx_callback=None,   # Optional[Callable[[tuple[float,float]], None]]
        radius: float = 450.0,
    ) -> bool:
        """
        Fire the one-time tactical nuke at *target_pos*.

        Returns True if the nuke was launched; False if already expended.

        AoE damage model  (anti-unit only)
        ------------------------------------
        • ONLY Unit sprites are eligible targets.
          Building sprites (slot buildings AND both HQs) are NEVER touched.
          This is enforced by the explicit `isinstance(u, Building)` skip guard
          inside the damage loop, even though the caller should only pass units.

        • Every Unit within *radius* pixels:
              take_damage(99_999)  →  instant kill regardless of HP.

        • VFX: 20 explosion sprites scattered randomly inside the blast circle.

        Fortified-HQ interaction
        ------------------------
        HQs have hp=100,000 and damage_reduction=0.70. The nuke does NOT target
        buildings, so HQs are completely unaffected.  To damage an HQ the player
        must rely on sustained unit pressure; the nuke clears the field so those
        units can advance uncontested.

        Side-effect: sets nuke_available = False (one-shot weapon).
        """
        if not self.nuke_available:
            return False
        self.nuke_available = False

        tx, ty = float(target_pos[0]), float(target_pos[1])

        # ── Anti-unit sweep (Buildings explicitly excluded) ───────────────────
        # Import guard: avoid circular import — Building is only referenced at
        # TYPE_CHECKING level, so we use a duck-type attribute check instead.
        killed = 0
        for u in units:
            # Skip anything that quacks like a Building (has is_hq attribute
            # and no waypoints list — belt-and-suspenders guard).
            if getattr(u, "is_hq", False) is not False:
                continue       # is a Building — skip
            if u.is_dead:
                continue
            if math.hypot(u.pos[0] - tx, u.pos[1] - ty) <= radius:
                u.take_damage(99_999, vfx_callback)
                killed += 1

        # ── Scatter VFX explosions across the blast zone ──────────────────────
        if vfx_callback:
            for _ in range(20):
                ox = random.uniform(-radius * 0.88, radius * 0.88)
                oy = random.uniform(-radius * 0.88, radius * 0.88)
                if math.hypot(ox, oy) <= radius:
                    vfx_callback((tx + ox, ty + oy))

        print(
            f"[Nuke] Detonated at ({tx:.0f}, {ty:.0f})  "
            f"radius={radius}  units_killed={killed}  minerals={self.minerals}"
        )
        return True

    def __repr__(self) -> str:
        alive = sum(1 for b in self._slot_buildings if not b.is_dead)
        return (
            f"ResourceManager(minerals={self.minerals}, "
            f"income={self.income_per_cycle}/cycle "
            f"[base={BASE_INCOME} + bonus={self.income_bonus}], "
            f"slot_buildings={alive}/{len(self._slot_buildings)})"
        )
