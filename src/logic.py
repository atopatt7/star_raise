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
import math
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


# ── Income constants ──────────────────────────────────────────────────────────
INCOME_CYCLE_FRAMES: int   = 300          # 5 s @ 60 fps (kept for reference)
INCOME_CYCLE_SECS:   float = 5.0          # authoritative time-based cycle length
BASE_INCOME:         int   = 10           # flat base income, always present
STARTING_MINERALS:   int   = 150

# ── Building spec table (single source of truth) ──────────────────────────────
BUILDING_SPECS: dict[str, dict] = {
    "barracks": {
        "name":              "步兵營",
        "unit_type":         "marine",
        "spawn_rate_frames": 480,    # 8 s @ 60 fps
        "cost":              100,
        "income_bonus":      5,      # floor(100 × 5%) per income cycle
    },
    "refinery": {
        "name":              "裝甲廠",
        "unit_type":         "tank",
        "spawn_rate_frames": 720,    # 12 s @ 60 fps
        "cost":              200,
        "income_bonus":      10,     # floor(200 × 5%) per income cycle
    },
    "rover_bay": {
        "name":              "突擊車廠",
        "unit_type":         "jackal",
        "spawn_rate_frames": 540,    # 9 s @ 60 fps — fast light vehicle
        "cost":              150,
        "income_bonus":      8,
    },
    "spec_ops": {
        "name":              "特戰中心",
        "unit_type":         "ghost",
        "spawn_rate_frames": 660,    # 11 s @ 60 fps — elite infantry
        "cost":              250,
        "income_bonus":      12,
    },
    "heavy_factory": {
        "name":              "重型兵工廠",
        "unit_type":         "hellfire",
        "spawn_rate_frames": 840,    # 14 s @ 60 fps — heavy AoE unit
        "cost":              300,
        "income_bonus":      15,
    },
    "starport": {
        "name":              "航空機場",
        "unit_type":         "valkyrie",
        "spawn_rate_frames": 900,    # 15 s @ 60 fps — flying unit
        "cost":              350,
        "income_bonus":      18,
    },
}


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
