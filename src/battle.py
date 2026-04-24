"""
battle.py — Star Raise Game  (v4: Base Assault)
BattleManager: 統一處理碰撞分離、戰鬥回合、死亡清理。

碰撞邏輯
--------
使用「圓形分離推力」演算法，等同於
  pygame.sprite.spritecollide(sprite, group, False, pygame.sprite.collide_circle)
但因本專案 GameSprite 不繼承 pygame.sprite.Sprite，
改為純數學實作：若兩單位圓心距 < 兩半徑之和，
沿圓心連線方向各自後退 overlap/2 的距離。
"""

import math
from typing import Optional, Callable, List

# 使用相對 import 確保模組內部一致
from src.sprite import Unit, Building, VFXSprite, Projectile, _ALLY_TEAMS
from src.asset_manager import AssetManager

VFXCallback = Callable[[tuple[float, float]], None]


class BattleManager:
    """
    遊戲戰鬥系統的單一責任類別，所有方法設計為靜態，
    由 GameLoop 每幀呼叫。

    典型呼叫順序（在 GameLoop.update 中）
    ----------------------------------------
    1. BattleManager.process_combat(all_units, vfx_cb)
    2. BattleManager.resolve_collisions(all_units)
    3. BattleManager.cleanup_dead(all_units)   → 回傳新 list
    """

    # ── 1. 戰鬥回合 ──────────────────────────────────────────────────────────
    @staticmethod
    def process_combat(
        units:               list[Unit],
        vfx_callback:        Optional[VFXCallback] = None,
        buildings:           Optional[list[Building]] = None,
        dt:                  float = 1 / 60,
        projectile_callback: Optional[Callable] = None,
    ) -> None:
        """
        對所有存活單位執行「掃描 → 攻擊 → 攻城」一輪。
        每個 Unit 呼叫 update(enemies, vfx_callback, enemy_buildings, dt, projectile_callback)：
        - scan_range 內有敵 Unit → combat（攻擊單位）
        - 行軍中     → march（沿 waypoints）
        - waypoints 耗盡 → assault（攻打最近敵方建築）
        """
        living = [u for u in units if not u.is_dead]
        for unit in living:
            unit.update(
                enemies=living,
                vfx_callback=vfx_callback,
                enemy_buildings=buildings,
                dt=dt,
                projectile_callback=projectile_callback,
            )

    # ── 2. 圓形碰撞分離 ───────────────────────────────────────────────────────
    @staticmethod
    def resolve_collisions(units: list[Unit]) -> None:
        living = [u for u in units if not u.is_dead]
        CELL_SIZE = 100
        grid = {}

        # 1. 將單位分配到網格中
        for u in living:
            cell = (int(u.pos[0] // CELL_SIZE), int(u.pos[1] // CELL_SIZE))
            if cell not in grid:
                grid[cell] = []
            grid[cell].append(u)
        checked_pairs = set()
        # 2. 僅與自身網格及相鄰的 8 個網格內的單位進行碰撞比對
        for (cx, cy), cell_units in grid.items():
            neighbors = [
                (cx, cy), (cx+1, cy), (cx-1, cy),
                (cx, cy+1), (cx, cy-1), (cx+1, cy+1),
                (cx-1, cy-1), (cx+1, cy-1), (cx-1, cy+1)
            ]
            for u in cell_units:
                for nx, ny in neighbors:
                    if (nx, ny) in grid:
                        for other in grid[(nx, ny)]:
                            if u is other:
                                continue

                            # 確保一對單位只檢查一次
                            pair_id = frozenset((id(u), id(other)))
                            if pair_id in checked_pairs:
                                continue
                            checked_pairs.add(pair_id)
                            # 保留原有的邏輯過濾條件
                            if u.team == other.team:
                                continue
                            if u.team in _ALLY_TEAMS and other.team in _ALLY_TEAMS:
                                continue
                            if u.is_flying != other.is_flying:
                                continue
                            dx = other.pos[0] - u.pos[0]
                            dy = other.pos[1] - u.pos[1]
                            dist = math.hypot(dx, dy)
                            min_dist = u.collision_radius + other.collision_radius
                            if dist < min_dist and dist > 1e-6:
                                overlap = min_dist - dist
                                nx_dir = dx / dist
                                ny_dir = dy / dist
                                push = overlap / 2.0
                                u.pos[0] -= nx_dir * push
                                u.pos[1] -= ny_dir * push
                                other.pos[0] += nx_dir * push
                                other.pos[1] += ny_dir * push

    # ── 3. 死亡清理 ───────────────────────────────────────────────────────────
    @staticmethod
    def cleanup_dead(units: list[Unit]) -> list[Unit]:
        """
        從列表移除 is_dead 的單位並回傳乾淨列表。
        死亡爆炸 VFX 已在 Unit.die() 中透過 vfx_callback 觸發，
        此處只做列表過濾。
        """
        survivors = [u for u in units if not u.is_dead]
        removed   = len(units) - len(survivors)
        if removed:
            print(f"[BattleManager] 🗑  清除 {removed} 個陣亡單位")
        return survivors

    # ── 4. VFX 更新（便利方法，可選擇放在 GameLoop 也行）─────────────────────
    @staticmethod
    def update_vfx(vfx_list: list[VFXSprite], dt: float = 1 / 60) -> list[VFXSprite]:
        """更新所有 VFX 並移除已播完的。"""
        for vfx in vfx_list:
            vfx.update(dt)
        return [v for v in vfx_list if not v.is_done]

    # ── 5. 偵錯資訊 ───────────────────────────────────────────────────────────
    @staticmethod
    def debug_report(units: list[Unit]) -> str:
        """產生每個單位狀態的單行摘要（供 HUD 顯示）。"""
        lines = []
        for u in units:
            state_sym = {"march": "🚶", "combat": "⚔️", "dead": "💀"}.get(u.state, "?")
            lines.append(
                f"{state_sym} {u.kind}[t{u.team}] "
                f"HP:{u.hp}/{u.max_hp} "
                f"CD:{u.atk_timer}/{u.atk_cd}"
            )
        return "  |  ".join(lines)
