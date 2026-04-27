from src.battle import BattleManager
from src.sprite import Projectile, VFXSprite

class EntityManager:
    def __init__(self):
        self.units = []
        self.projectiles = []
        self.vfx_list = []

    def spawn_unit(self, unit):
        self.units.append(unit)

    def spawn_projectile(self, proj):
        """接受一個已建立的 Projectile 物件並加入清單。"""
        self.projectiles.append(proj)

    def spawn_vfx(self, vfx):
        """接受一個已建立的 VFXSprite 物件並加入清單。"""
        self.vfx_list.append(vfx)

    # ── Fallback callbacks（當 main.py 未傳入正確版本時使用）────────────────
    def _proj_fallback(self, from_pos, to_pos, atk_type):
        """不使用 pool，直接建立 Projectile。"""
        proj = Projectile(from_pos, to_pos, atk_type)
        self.projectiles.append(proj)

    def _vfx_fallback(self, pos):
        """不使用 pool，直接建立 VFXSprite。"""
        vfx = VFXSprite(pos)
        self.vfx_list.append(vfx)

    def update(self, spatial_grid, dt, all_buildings,
               projectile_callback=None, vfx_callback=None):
        # 1. 更新簡單實體
        for p in self.projectiles:
            p.update(dt)
        for v in self.vfx_list:
            v.update(dt)

        # 2. 處理戰鬥與單位邏輯
        # projectile_callback(from_pos, to_pos, atk_type) — 由 main.py 傳入
        # vfx_callback(pos)                               — 由 main.py 傳入
        BattleManager.process_combat(
            spatial_grid=spatial_grid,
            units=self.units,
            vfx_callback=vfx_callback or self._vfx_fallback,
            buildings=all_buildings,
            dt=dt,
            projectile_callback=projectile_callback or self._proj_fallback,
        )

        # 3. 碰撞結算
        BattleManager.resolve_collisions(spatial_grid)

        # 4. 清理陣亡與過期實體
        self.units = BattleManager.cleanup_dead(self.units)
        self.projectiles = [p for p in self.projectiles if not p.is_done]
        self.vfx_list = [v for v in self.vfx_list if not v.is_done]

    def clear_all(self):
        self.units.clear()
        self.projectiles.clear()
        self.vfx_list.clear()
