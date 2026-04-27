"""
commands.py — Star Raise Command System
Command 模式: 將建造 / 拆除 / 核彈動作封裝為獨立物件，統一由 GameScene.execute_command() 執行。

使用方式
--------
from src.commands import BuildCommand, DemolishCommand, NukeCommand

game.execute_command(BuildCommand(team=0, slot=3, kind="barracks"))
game.execute_command(NukeCommand(team=1, x=4500.0, y=354.0))
"""

from __future__ import annotations
from typing import Any


class Command:
    """Base command — subclasses override execute()."""

    def execute(self, game: Any) -> None:  # noqa: D102
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────────────────────────────────────

class BuildCommand(Command):
    """Place a building at *slot* for *team*.

    Parameters
    ----------
    team : int   0 = player, ≥1 = AI team id
    slot : int   index into ALL_SLOTS (player) or ctrl.slots (AI)
    kind : str   building type key, e.g. "barracks"
    """

    def __init__(self, team: int, slot: int, kind: str) -> None:
        self.team = team
        self.slot = slot
        self.kind = kind

    def execute(self, game: Any) -> None:
        from src.logic import BUILDING_SPECS
        spec = BUILDING_SPECS.get(self.kind)
        if spec is None:
            return
        cost: int = spec["cost"]

        if self.team == 0:
            # ── Player build — delegate entirely to GameScene._place_building ──
            if game.res.spend(cost):
                game._place_building(self.slot, self.kind, team=0)

        else:
            # ── AI build ──
            ctrl = next(
                (c for c in game.ai_controllers if c.team == self.team), None
            )
            if ctrl is None or not ctrl.res.spend(cost):
                return

            from src.sprite import Building
            from src.logic import SLOT_SIZE

            # AI controllers store their own slot grid in ctrl.slots
            sx, sy = ctrl.slots[self.slot]
            cx, cy = sx + SLOT_SIZE // 2, sy + SLOT_SIZE // 2
            lane   = "top" if self.slot < len(ctrl.slots) // 2 else "bottom"

            b = Building(
                self.kind,
                game.manager,
                pos=(cx, cy),
                team=self.team,
                lane=lane,
                is_player=False,
            )
            ctrl._slot_map[self.slot] = b
            ctrl.res.register_building(b)
            # NOTE: Do NOT touch game._occupied_slots here — that set tracks
            # only the *player's* slots.  The AI tracks its own occupancy via
            # ctrl._slot_map, so adding self.slot here would incorrectly block
            # the player from building on those same-numbered player slots.


# ─────────────────────────────────────────────────────────────────────────────
# Demolish
# ─────────────────────────────────────────────────────────────────────────────

class DemolishCommand(Command):
    """Demolish the building occupying *slot* for *team*.

    Parameters
    ----------
    team : int   0 = player, ≥1 = AI team id
    slot : int   index into ALL_SLOTS (player) or ctrl.slots (AI)
    """

    def __init__(self, team: int, slot: int, branch_idx: int = 0) -> None:
        self.team = team
        self.slot = slot
        self.branch_idx = branch_idx

    def execute(self, game: Any) -> None:
        from src.logic import SLOT_SIZE

        if self.team == 0:
            # ── Player demolish — resolve coords from game-level ALL_SLOTS ──
            import sys
            _main = sys.modules.get("__main__") or sys.modules.get("main")
            ALL_SLOTS = _main.ALL_SLOTS  # type: ignore[union-attr]

            sx, sy = ALL_SLOTS[self.slot]
            cx, cy = sx + SLOT_SIZE // 2, sy + SLOT_SIZE // 2
            target_blds = game.slot_buildings
            target_res  = game.res

        else:
            # ── AI demolish — resolve coords from ctrl.slots ──
            ctrl = next(
                (c for c in game.ai_controllers if c.team == self.team), None
            )
            if ctrl is None:
                return
            sx, sy = ctrl.slots[self.slot]
            cx, cy = sx + SLOT_SIZE // 2, sy + SLOT_SIZE // 2
            target_blds = ctrl.slot_buildings
            target_res  = ctrl.res

        half = SLOT_SIZE // 2 + 4
        for b in target_blds:
            if (
                not b.is_dead
                and not b.is_hq
                and abs(b.pos[0] - cx) < half
                and abs(b.pos[1] - cy) < half
            ):
                b.demolish(target_res, game.spawn_vfx)
                game._occupied_slots.discard(self.slot)
                break


# ─────────────────────────────────────────────────────────────────────────────
# Nuke
# ─────────────────────────────────────────────────────────────────────────────

class NukeCommand(Command):
    """Fire a nuke for *team* at world position (*x*, *y*).

    Parameters
    ----------
    team : int     0 = player, ≥1 = AI team id
    x, y : float  world-space target coordinates
    """

    def __init__(self, team: int, x: float, y: float) -> None:
        self.team = team
        self.x    = x
        self.y    = y

    def execute(self, game: Any) -> None:
        if self.team == 0:
            target_res = game.res
        else:
            ctrl = next(
                (c for c in game.ai_controllers if c.team == self.team), None
            )
            target_res = ctrl.res if ctrl else None

        if target_res is None:
            return

        fired = target_res.launch_nuke(
            (self.x, self.y), game.units, game.spawn_vfx
        )
        if fired:
            game.nuke_flash        = 1.5
            game.shake_timer       = 0.5
            game.shake_amp         = 10
            game.nuke_circle       = (self.x, self.y)
            game.nuke_circle_timer = 3.0


# ─────────────────────────────────────────────────────────────────────────────
# Upgrade
# ─────────────────────────────────────────────────────────────────────────────

class UpgradeCommand(Command):
    """Upgrade the building occupying *slot* to its next level.

    Parameters
    ----------
    team : int   0 = player, >=1 = AI team id
    slot : int   index into ALL_SLOTS (player) or ctrl.slots (AI)
    """

    def __init__(self, team: int, slot: int) -> None:
        self.team = team
        self.slot = slot

    def execute(self, game: Any) -> None:
        from src.logic import BUILDING_SPECS, SLOT_SIZE
        import sys
        _main = sys.modules.get("__main__") or sys.modules.get("main")
        ALL_SLOTS = _main.ALL_SLOTS  # type: ignore[union-attr]

        if self.team == 0:
            target_blds = game.slot_buildings
            target_res  = game.res
            sx, sy = ALL_SLOTS[self.slot]
        else:
            ctrl = next(
                (c for c in game.ai_controllers if c.team == self.team), None
            )
            if ctrl is None:
                return
            target_blds = ctrl.slot_buildings
            target_res  = ctrl.res
            sx, sy = ctrl.slots[self.slot]

        cx, cy = sx + SLOT_SIZE // 2, sy + SLOT_SIZE // 2
        half   = SLOT_SIZE // 2 + 4

        target_building = None
        for b in target_blds:
            if (not b.is_dead and not b.is_hq
                    and abs(b.pos[0] - cx) < half
                    and abs(b.pos[1] - cy) < half):
                target_building = b
                break

        if target_building is None:
            return

        specs    = BUILDING_SPECS.get(target_building.kind, {})
        levels   = specs.get("levels", [])
        next_idx = target_building.level   # level starts at 1 -> next index in array

        if next_idx < len(levels):
            next_level_data = levels[next_idx]
            # Handle branching upgrade (List)
            if isinstance(next_level_data, list):
                if self.branch_idx < len(next_level_data):
                    next_level_data = next_level_data[self.branch_idx]
                else:
                    return  # invalid branch index
            cost = next_level_data.get("cost", 0)
            if target_res.spend(cost):
                target_building.apply_upgrade(next_level_data)
