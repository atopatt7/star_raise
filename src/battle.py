import math
from typing import Optional, Callable
from src.sprite import Unit, Building, VFXSprite, Projectile, _ALLY_TEAMS
from src.asset_manager import AssetManager

VFXCallback = Callable[[tuple[float, float]], None]


class SpatialGrid:
    def __init__(self, cell_size=100):
        self.cell_size = cell_size
        self.grid = {}

    def build(self, units: list[Unit]):
        # GC opt: reuse existing lists instead of clearing the whole dict
        for cell_list in self.grid.values():
            cell_list.clear()

        for u in units:
            if u.is_dead: continue
            cell = (int(u.pos[0] // self.cell_size), int(u.pos[1] // self.cell_size))
            if cell not in self.grid:
                self.grid[cell] = []
            self.grid[cell].append(u)

    def get_in_radius(self, pos: tuple[float, float], radius: float) -> list[Unit]:
        min_cx = int((pos[0] - radius) // self.cell_size)
        max_cx = int((pos[0] + radius) // self.cell_size)
        min_cy = int((pos[1] - radius) // self.cell_size)
        max_cy = int((pos[1] + radius) // self.cell_size)
        res = []
        for x in range(min_cx, max_cx + 1):
            for y in range(min_cy, max_cy + 1):
                if (x, y) in self.grid and self.grid[(x, y)]:
                    res.extend(self.grid[(x, y)])
        return res


class BattleManager:
    # GC opt: class-level set reused every frame instead of allocating a new one
    _checked_pairs: set = set()

    @staticmethod
    def process_combat(
        spatial_grid: SpatialGrid,
        units: list[Unit],
        vfx_callback: Optional[VFXCallback] = None,
        buildings: Optional[list[Building]] = None,
        dt: float = 1 / 60,
        projectile_callback: Optional[Callable] = None,
    ) -> None:
        living = [u for u in units if not u.is_dead]
        for unit in living:
            unit.update(
                spatial_grid=spatial_grid,
                vfx_callback=vfx_callback,
                enemy_buildings=buildings,
                dt=dt,
                projectile_callback=projectile_callback,
            )

    @staticmethod
    def resolve_collisions(spatial_grid: SpatialGrid) -> None:
        # Reuse class-level set; never allocate a new one per frame
        BattleManager._checked_pairs.clear()

        for (cx, cy), cell_units in spatial_grid.grid.items():
            if not cell_units: continue

            neighbors = [
                (cx, cy), (cx+1, cy), (cx-1, cy),
                (cx, cy+1), (cx, cy-1), (cx+1, cy+1),
                (cx-1, cy-1), (cx+1, cy-1), (cx-1, cy+1)
            ]

            for u in cell_units:
                uid = id(u)
                for nx, ny in neighbors:
                    if (nx, ny) in spatial_grid.grid:
                        for other in spatial_grid.grid[(nx, ny)]:
                            if u is other: continue

                            oid = id(other)
                            # GC opt: sorted tuple instead of frozenset (much cheaper)
                            pair_id = (uid, oid) if uid < oid else (oid, uid)

                            if pair_id in BattleManager._checked_pairs: continue
                            BattleManager._checked_pairs.add(pair_id)

                            if u.team == other.team: continue
                            if u.team in _ALLY_TEAMS and other.team in _ALLY_TEAMS: continue
                            if u.is_flying != other.is_flying: continue

                            dx, dy = other.pos[0] - u.pos[0], other.pos[1] - u.pos[1]
                            dist = math.hypot(dx, dy)
                            min_dist = u.collision_radius + other.collision_radius

                            if dist < min_dist and dist > 1e-6:
                                overlap = min_dist - dist
                                nx_dir, ny_dir = dx / dist, dy / dist
                                push = overlap / 2.0
                                u.pos[0] -= nx_dir * push
                                u.pos[1] -= ny_dir * push
                                other.pos[0] += nx_dir * push
                                other.pos[1] += ny_dir * push

    @staticmethod
    def cleanup_dead(units: list[Unit]) -> list[Unit]:
        # Fast path: skip allocation if nothing is dead
        if not any(u.is_dead for u in units):
            return units

        survivors = [u for u in units if not u.is_dead]
        removed   = len(units) - len(survivors)
        if removed:
            print(f"[BattleManager] cleared {removed} dead units")
        return survivors
