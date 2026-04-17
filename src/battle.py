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
        """
        防止單位重疊。

        演算法（等價於 pygame.sprite.collide_circle）
        -----------------------------------------------
        對每對 (A, B) 不同陣營或同陣營的存活單位：
          dist = distance(A, B)
          min_dist = A.collision_radius + B.collision_radius
          if dist < min_dist and dist > 0:
              overlap  = min_dist - dist
              push_vec = normalize(B.pos - A.pos) * (overlap / 2)
              A.pos -= push_vec   (向後推)
              B.pos += push_vec   (向前推)

        複雜度 O(n²)，n 小（<100）時足夠。
        """
        living = [u for u in units if not u.is_dead]
        n = len(living)
        for i in range(n):
            for j in range(i + 1, n):
                a = living[i]
                b = living[j]
                # Same team, or both on the allied side (0+1) → pass through.
                # Allied blocking causes traffic jams in narrow lanes.
                if a.team == b.team:
                    continue
                if a.team in _ALLY_TEAMS and b.team in _ALLY_TEAMS:
                    continue
                # Flying units occupy a different Z-layer — no ground collision.
                if a.is_flying != b.is_flying:
                    continue
                dx = b.pos[0] - a.pos[0]
                dy = b.pos[1] - a.pos[1]
                dist = math.hypot(dx, dy)
                min_dist = a.collision_radius + b.collision_radius

                if dist < min_dist and dist > 1e-6:
                    overlap = min_dist - dist
                    nx = dx / dist
                    ny = dy / dist
                    push = overlap / 2.0
                    a.pos[0] -= nx * push
                    a.pos[1] -= ny * push
                    b.pos[0] += nx * push
                    b.pos[1] += ny * push

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
