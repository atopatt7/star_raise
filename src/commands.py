"""
commands.py — Star Raise Command System
Command 模式: 將建造 / 拆除 / 核彈動作封裝為獨立物件，統一由 GameScene.execute_command() 執行。

使用方式
--------
from src.commands import BuildCommand, DemolishCommand, NukeCommand

game.execute_command(BuildCommand(team=0, slot=3, kind="barracks"))
game.execute_command(NukeCommand(team=1, x=4500.0, y=354.0))

AI 指令請帶 ctrl=self：2V2 有兩個 team=2 的 AI，只靠 team 會找錯控制器。
"""

from __future__ import annotations
from typing import Any


class Command:
    """Base command — subclasses override execute()."""

    def execute(self, game: Any) -> None:  # noqa: D102
        pass


def _resolve_ctrl(game: Any, team: int, ctrl: Any = None) -> Any:
    """Return the issuing AIController (explicit ctrl wins over team lookup)."""
    if ctrl is not None:
        return ctrl
    return next((c for c in game.ai_controllers if c.team == team), None)


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
    ctrl : AIController | None   issuing controller (AI only)
    """

    def __init__(self, team: int, slot: int, kind: str, ctrl: Any = None) -> None:
        self.team = team
        self.slot = slot
        self.kind = kind
        self.ctrl = ctrl

    def execute(self, game: Any) -> None:
        from src.logic import BUILDING_SPECS
        spec = BUILDING_SPECS.get(self.kind)
        if spec is None:
            return
        cost: int = spec["cost"]

        if self.team == 0:
            # ── Player build — delegate entirely to GameScene._place_building ──
            if self.slot in game._occupied_slots:
                return
            if game.res.spend(cost):
                game._place_building(self.slot, self.kind, team=0)

        else:
            # ── AI build ──
            ctrl = _resolve_ctrl(game, self.team, self.ctrl)
            if ctrl is None or self.slot in ctrl._slot_map:
                return
            # Left-side AI (2V2 ally) shares the player's slot grid
            if ctrl.is_left and self.slot in game._occupied_slots:
                return
            if not ctrl.res.spend(cost):
                return

            from src.sprite import Building
            from src.logic import SLOT_SIZE

            # AI controllers store their own slot grid in ctrl.slots
            sx, sy = ctrl.slots[self.slot]
            cx, cy = sx + SLOT_SIZE // 2, sy + SLOT_SIZE // 2
            lane   = ctrl._lane_of(self.slot)

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
            if ctrl.is_left:
                game._occupied_slots.add(self.slot)


# ─────────────────────────────────────────────────────────────────────────────
# Demolish
# ─────────────────────────────────────────────────────────────────────────────

class DemolishCommand(Command):
    """Demolish the building occupying *slot* for *team*.

    Parameters
    ----------
    team : int   0 = player, ≥1 = AI team id
    slot : int   index into ALL_SLOTS (player) or ctrl.slots (AI)
    ctrl : AIController | None   issuing controller (AI only)
    """

    def __init__(self, team: int, slot: int, ctrl: Any = None) -> None:
        self.team = team
        self.slot = slot
        self.ctrl = ctrl

    def execute(self, game: Any) -> None:
        if self.team == 0:
            b = game._player_slot_map.get(self.slot)
            target_res = game.res
        else:
            ctrl = _resolve_ctrl(game, self.team, self.ctrl)
            if ctrl is None:
                return
            b = ctrl._slot_map.get(self.slot)
            target_res = ctrl.res

        if b is None or b.is_dead or b.is_hq:
            return
        b.demolish(target_res, game.spawn_vfx)

        if self.team == 0:
            game._player_slot_map.pop(self.slot, None)
            game._occupied_slots.discard(self.slot)
        else:
            ctrl._slot_map.pop(self.slot, None)
            if ctrl.is_left:
                game._occupied_slots.discard(self.slot)


# ─────────────────────────────────────────────────────────────────────────────
# Nuke
# ─────────────────────────────────────────────────────────────────────────────

class NukeCommand(Command):
    """Fire a nuke for *team* at world position (*x*, *y*).

    Parameters
    ----------
    team : int     0 = player, ≥1 = AI team id
    x, y : float  world-space target coordinates
    ctrl : AIController | None   issuing controller (AI only)
    """

    def __init__(self, team: int, x: float, y: float, ctrl: Any = None) -> None:
        self.team = team
        self.x    = x
        self.y    = y
        self.ctrl = ctrl

    def execute(self, game: Any) -> None:
        if self.team == 0:
            target_res = game.res
        else:
            ctrl = _resolve_ctrl(game, self.team, self.ctrl)
            target_res = ctrl.res if ctrl else None

        if target_res is None:
            return

        fired = target_res.launch_nuke(
            (self.x, self.y), game.units, game.spawn_vfx, team=self.team
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
    team       : int   0 = player, >=1 = AI team id
    slot       : int   index into ALL_SLOTS (player) or ctrl.slots (AI)
    branch_idx : int   which branch to take when the next level is a choice
    ctrl       : AIController | None   issuing controller (AI only)
    """

    def __init__(self, team: int, slot: int, branch_idx: int = 0, ctrl: Any = None) -> None:
        self.team       = team
        self.slot       = slot
        self.branch_idx = branch_idx
        self.ctrl       = ctrl

    def execute(self, game: Any) -> None:
        from src.logic import BUILDING_SPECS

        if self.team == 0:
            target_building = game._player_slot_map.get(self.slot)
            target_res      = game.res
        else:
            ctrl = _resolve_ctrl(game, self.team, self.ctrl)
            if ctrl is None:
                return
            target_building = ctrl._slot_map.get(self.slot)
            target_res      = ctrl.res

        if target_building is None or target_building.is_dead or target_building.is_hq:
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
