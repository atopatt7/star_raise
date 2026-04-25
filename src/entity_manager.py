from src.battle import BattleManager

class EntityManager:
    def __init__(self):
        self.units = []
        self.projectiles = []
        self.vfx_list = []

    def spawn_unit(self, unit):
        self.units.append(unit)

    def spawn_projectile(self, proj):
        self.projectiles.append(proj)

    def spawn_vfx(self, vfx):
        self.vfx_list.append(vfx)

    def update(self, spatial_grid, dt, all_buildings):
        # 1. 更新簡單實體
        for p in self.projectiles:
            p.update(dt)
        for v in self.vfx_list:
            v.update(dt)

        # 2. 處理戰鬥與單位邏輯
        BattleManager.process_combat(
            spatial_grid=spatial_grid,
            units=self.units,
            vfx_callback=self.spawn_vfx,
            buildings=all_buildings,
            dt=dt,
            projectile_callback=self.spawn_projectile
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
