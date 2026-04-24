"""
sprite.py — Star Raise  (v5: Auto-Spawn Economy)

Phase 2 changes
---------------
Building
  - queue / ProductionQueue  : REMOVED
  - gives_income             : REMOVED
  - produce()                : REMOVED
  + lane        : "top" | "bottom" | "none"  (slot lane; "none" = HQ)
  + is_hq       : True for Player/Enemy HQ (victory-condition targets)
  + spawn_timer : counts up toward spawn_rate_frames
  + unit_type   : from BUILDING_SPECS (what this building auto-spawns)
  + income_bonus: flat per-cycle mineral bonus (= floor(cost × 5%))
  + update()    : ticks timer; returns (unit_type, spawn_pos, lane) or None
  + _draw_spawn_bar() : progress bar toward next spawn

Unit / GameSprite / VFXSprite — unchanged from v4
"""

from __future__ import annotations

import math
import random
import pygame
from typing import Optional, Callable, TYPE_CHECKING

from src.asset_manager import AssetManager
from src.logic        import BUILDING_SPECS, ResourceManager
from src.shared       import DAMAGE_MATRIX

VFXCallback = Callable[[tuple[float, float]], None]


# ── Unit stat table ───────────────────────────────────────────────────────────
UNIT_STATS: dict[str, dict] = {
    "marine": {
        "scale":          (48, 64),   # 60° perspective sprite (48×64 source)
        "hp":             100,
        "speed":          1.8,
        "atk_dmg":        15,
        "atk_cd":         60,
        "scan_range":     150,
        "col_radius":     18,
        # Combat flags
        "is_flying":      False,   # ground unit
        "can_attack_air": True,    # marines can shoot air targets
        "splash_radius":  0,       # single-target
        # Damage matrix types
        "atk_type":       "piercing",
        "armor_type":     "light",
    },
    "tank": {
        "scale":          (56, 72),   # 60° perspective sprite (56×72 source)
        "hp":             250,
        "speed":          1.1,
        "atk_dmg":        40,
        "atk_cd":         90,
        "scan_range":     180,
        "col_radius":     26,
        # Combat flags
        "is_flying":      False,   # ground unit
        "can_attack_air": False,   # tank shells can't target aircraft
        "splash_radius":  0,
        # Damage matrix types
        "atk_type":       "siege",
        "armor_type":     "heavy",
    },
    "jackal": {
        "scale":          (52, 60),   # fast light vehicle
        "hp":             80,
        "speed":          2.8,        # fastest ground unit
        "atk_dmg":        20,
        "atk_cd":         50,
        "scan_range":     160,
        "col_radius":     22,
        # Combat flags
        "is_flying":      False,
        "can_attack_air": False,
        "splash_radius":  0,
        # Damage matrix types
        "atk_type":       "normal",
        "armor_type":     "light",
    },
    "ghost": {
        "scale":          (44, 60),   # elite sniper infantry
        "hp":             40,
        "speed":          1.6,
        "atk_dmg":        35,
        "atk_cd":         80,
        "scan_range":     250,        # long range
        "col_radius":     16,
        # Combat flags
        "is_flying":      False,
        "can_attack_air": True,       # ghost can shoot aircraft
        "splash_radius":  0,
        # Damage matrix types
        "atk_type":       "piercing",
        "armor_type":     "light",
    },
    "hellfire": {
        "scale":          (60, 76),   # heavy AoE artillery
        "hp":             120,
        "speed":          0.9,        # slow heavy unit
        "atk_dmg":        40,
        "atk_cd":         100,
        "scan_range":     300,        # long-range bombardment
        "col_radius":     28,
        # Combat flags
        "is_flying":      False,
        "can_attack_air": False,
        "splash_radius":  60,         # AoE blast radius
        # Damage matrix types
        "atk_type":       "siege",
        "armor_type":     "heavy",
    },
    "valkyrie": {
        "scale":          (64, 56),   # gunship — wider than tall
        "hp":             150,
        "speed":          2.2,
        "atk_dmg":        25,
        "atk_cd":         70,
        "scan_range":     150,
        "col_radius":     28,
        # Combat flags
        "is_flying":      True,       # flying unit — bypasses ground collision
        "can_attack_air": True,       # air-to-air capable
        "splash_radius":  0,
        # Damage matrix types
        "atk_type":       "piercing",
        "armor_type":     "heavy",
    },
    # ── Swarm faction units ──────────────────────────────────────────────────
    "crawler": {
        "scale":          (32, 32),   # tiny fast bug
        "hp":             40,
        "speed":          2.6,        # fast melee rusher
        "atk_dmg":        15,
        "atk_cd":         40,         # quick melee strikes
        "scan_range":     40,         # very short melee range
        "col_radius":     12,
        "is_flying":      False,
        "can_attack_air": False,
        "splash_radius":  0,
        "atk_type":       "normal",
        "armor_type":     "light",
    },
    "spitter": {
        "scale":          (32, 32),   # bulbous acid shooter
        "hp":             60,
        "speed":          1.4,        # slow — stays back and spits
        "atk_dmg":        20,
        "atk_cd":         72,         # 1.2 s between acid shots
        "scan_range":     200,        # medium-long range
        "col_radius":     14,
        "is_flying":      False,
        "can_attack_air": False,
        "splash_radius":  0,
        "atk_type":       "acid",     # unique neon-green projectile visual
        "armor_type":     "light",
    },
    # ── Rogue AI faction units ───────────────────────────────────────────────
    "observer": {
        "scale":          (44, 44),   # hovering optical drone
        "hp":             35,
        "speed":          3.2,        # fastest flying scout
        "atk_dmg":        8,
        "atk_cd":         30,         # 0.5 s — rapid pulse laser
        "scan_range":     180,
        "col_radius":     16,
        "is_flying":      True,       # hovering drone
        "can_attack_air": True,
        "splash_radius":  0,
        "atk_type":       "laser",    # red beam projectile
        "armor_type":     "light",
        "render_offset_y": 20,        # hovers above ground
    },
    "ravager": {
        "scale":          (64, 72),   # bulky alloy bruiser
        "hp":             450,
        "speed":          1.2,
        "atk_dmg":        20,
        "atk_cd":         90,         # 1.5 s between AoE slams
        "scan_range":     40,         # melee reach
        "col_radius":     28,
        "is_flying":      False,
        "can_attack_air": False,
        "splash_radius":  50,         # AoE cleave on each hit
        "atk_type":       "normal",
        "armor_type":     "heavy",
    },
    "coder": {
        "scale":          (40, 48),   # spindly airborne hacker
        "hp":             15,
        "speed":          1.8,
        "atk_dmg":        8,
        "atk_cd":         120,        # 2.0 s — slow heavy shot
        "scan_range":     750,        # extreme range glass-cannon
        "col_radius":     14,
        "is_flying":      True,
        "can_attack_air": True,
        "splash_radius":  0,
        "atk_type":       "piercing", # concentrated exploit burst
        "armor_type":     "light",
        "render_offset_y": 20,        # hovers above ground
    },
    "splitter": {
        "scale":          (60, 68),   # heavy melee siege unit
        "hp":             300,
        "speed":          0.8,
        "atk_dmg":        60,
        "atk_cd":         120,        # 2.0 s heavy siege swing
        "scan_range":     50,         # melee reach
        "col_radius":     26,
        "is_flying":      False,
        "can_attack_air": False,
        "splash_radius":  30,         # short cleave when it strikes
        "atk_type":       "siege",    # bonus vs structure / heavy
        "armor_type":     "heavy",
    },
}

# Lane indicator colours (used in draw)
_LANE_COLORS = {
    "top":    (80,  160, 255),
    "bottom": (255, 160,  60),
    "none":   (160, 160, 160),
}

# Alliance constant — teams 0 (player) and 1 (allied AI) never attack each other.
# Enemy team is always 2.
_ALLY_TEAMS: frozenset[int] = frozenset({0, 1})


# ── Base Sprite ───────────────────────────────────────────────────────────────
class GameSprite:
    """
    Base class for all game objects.

    pos              : world-space centre [x, y]
    angle            : facing angle in degrees (0 = right, CCW positive)
    surface          : current pygame.Surface (post-rotation)
    collision_radius : circular collision radius (overridden by subclasses)
    """

    collision_radius: int = 16

    def __init__(
        self,
        asset_key: str,
        manager: AssetManager,
        pos: tuple[float, float] = (0.0, 0.0),
        scale: Optional[tuple[int, int]] = None,
    ) -> None:
        self.asset_key     = asset_key
        self.manager       = manager
        self.pos           = list(pos)
        self.angle         = 0.0
        self._base_surface = manager.get(asset_key, scale=scale)
        self.surface       = self._base_surface

    # ── Rotation ──────────────────────────────────────────────────────────────
    def rotate_to(self, target: tuple[float, float]) -> None:
        dx = target[0] - self.pos[0]
        dy = target[1] - self.pos[1]
        self.angle = math.degrees(math.atan2(-dy, dx))
        self._apply_rotation()

    def rotate_by(self, delta_deg: float) -> None:
        self.angle = (self.angle + delta_deg) % 360
        self._apply_rotation()

    def _apply_rotation(self) -> None:
        self.surface = pygame.transform.rotate(self._base_surface, self.angle)

    # ── Rendering ─────────────────────────────────────────────────────────────
    def draw(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        rect = self.surface.get_rect(
            center=(
                int(self.pos[0]) - camera_offset[0],
                int(self.pos[1]) - camera_offset[1],
            )
        )
        screen.blit(self.surface, rect)

    def draw_debug(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        cx = int(self.pos[0]) - camera_offset[0]
        cy = int(self.pos[1]) - camera_offset[1]
        pygame.draw.circle(screen, (0, 255, 0), (cx, cy), self.collision_radius, 1)
        pygame.draw.circle(screen, (255, 0, 0), (cx, cy), 3)

    @property
    def rect(self) -> pygame.Rect:
        return self.surface.get_rect(center=(int(self.pos[0]), int(self.pos[1])))

    def dist_to(self, other: "GameSprite") -> float:
        return math.hypot(
            self.pos[0] - other.pos[0],
            self.pos[1] - other.pos[1],
        )


# ── Building ──────────────────────────────────────────────────────────────────
class Building(GameSprite):
    """
    Static building. Two subtypes:

    HQ building  (is_hq=True, lane="none")
        - Victory-condition target; never auto-spawns.
        - Placed at world edges by GameLoop.

    Slot building (is_hq=False, lane="top"|"bottom")
        - Placed inside the player's 4×4 grid slots.
        - Auto-spawns its unit_type when spawn_timer reaches spawn_rate_frames.
        - Contributes income_bonus minerals to each income cycle while alive.

    Parameters
    ----------
    kind  : "barracks" | "refinery"
    pos   : world-space centre
    hp    : starting hit-points
    team  : 0 = player, 1 = enemy
    lane  : "top" | "bottom" | "none"
    is_hq : True → HQ building (no auto-spawn, no income bonus)
    """

    collision_radius = 48

    # Spawn-point offset for HQ buildings (unit appears beside HQ)
    _HQ_SPAWN_OFFSET = 100

    def __init__(
        self,
        kind:      str,
        manager:   AssetManager,
        pos:       tuple[float, float],
        hp:        int  = 500,
        team:      int  = 0,
        lane:      str  = "none",
        is_hq:     bool = False,
        is_player: bool = False,
    ) -> None:
        super().__init__(kind, manager, pos, scale=(96, 96))
        self.kind      = kind
        # Allow BUILDING_SPECS to override the default hp (e.g. toxin_chamber=400).
        # The explicit `hp=` keyword still wins if the caller passes a non-default.
        _spec_hp       = BUILDING_SPECS.get(kind, {}).get("hp")
        if hp == 500 and _spec_hp is not None:
            hp = int(_spec_hp)
        self.hp        = hp
        self.max_hp    = hp
        self.team      = team
        self.is_dead   = False
        self.is_hq     = is_hq
        self.lane      = lane      # "top" | "bottom" | "none"
        self.is_player = is_player # True = human-placed (BLUE bar)
        self.armor_type = "structure"  # all buildings use structure armour type

        # ── Auto-spawn state (slot buildings only) ────────────────────────────
        spec = BUILDING_SPECS.get(kind, {})
        self.unit_type:         str   = spec.get("unit_type", "marine")
        # Optional multi-unit roster (Rogue AI buildings set this). When it
        # holds > 1 entry, Building.update() picks a random unit per spawn.
        _types = spec.get("unit_types")
        self.unit_types: list[str] = (
            list(_types) if _types else [self.unit_type]
        )
        self.spawn_rate_frames: int   = spec.get("spawn_rate_frames", 480)
        self._spawn_rate_secs:  float = self.spawn_rate_frames / 60.0
        self._cost:             int   = spec.get("cost", 0)
        self._income_bonus:     int   = spec.get("income_bonus", 0)
        self.spawn_timer:       float = 0.0   # accumulated seconds since last spawn

        # ── Turret combat state (turret kind only) ────────────────────────────
        self._is_turret:            bool  = (kind == "turret")
        self._turret_atk_dmg:       int   = spec.get("atk_dmg", 0)
        self._turret_atk_cd:        float = float(spec.get("atk_cd", 0.0))  # seconds
        self._turret_scan_range:    float = float(spec.get("scan_range", 0))
        self._fire_timer:           float = 0.0   # accumulated seconds toward next shot

        # Phase 4b: Armour plate — HQs absorb 70 % of all incoming damage.
        # Applied inside take_damage() BEFORE subtracting HP, so the effective
        # damage is:  effective = int(raw_amount × (1 − damage_reduction))
        # Slot buildings have DR = 0.0 (no reduction).
        self.damage_reduction: float = 0.70 if is_hq else 0.0

        # Phase 4: optional callback fired immediately when this HQ is destroyed.
        # Signature: on_hq_death(team: int) -> None
        # Set by GameLoop._init_scene so main.py can react without polling.
        # Non-HQ buildings leave this as None.
        self.on_hq_death = None

    # ── Properties ────────────────────────────────────────────────────────────
    @property
    def income_bonus(self) -> int:
        """
        Flat minerals added to income_per_cycle while this building is alive.
        0 for HQ buildings.
        """
        return 0 if self.is_hq else self._income_bonus

    @property
    def spawn_progress(self) -> float:
        """0.0 – 1.0 progress toward next unit spawn."""
        if self._spawn_rate_secs == 0:
            return 0.0
        return self.spawn_timer / self._spawn_rate_secs

    @property
    def spawn_point(self) -> tuple[float, float]:
        """
        World position where a newly spawned unit should appear.
        HQ: beside the building (team-direction offset).
        Slot: exactly at building centre (main.py routes via lane waypoints).
        """
        if self.is_hq:
            ox = self._HQ_SPAWN_OFFSET if self.team == 0 else -self._HQ_SPAWN_OFFSET
            return (self.pos[0] + ox, self.pos[1])
        return (float(self.pos[0]), float(self.pos[1]))

    # ── Per-frame update ──────────────────────────────────────────────────────
    def update(
        self,
        dt: float = 1 / 60,
        spatial_grid = None,
        projectile_callback: Optional[Callable] = None,
        vfx_callback: Optional[VFXCallback] = None,
    ) -> Optional[tuple[str, tuple[float, float], str]]:
        if self.is_dead:
            return None

        if self._is_turret and spatial_grid is not None:
            self._fire_timer += dt
            if self._fire_timer >= self._turret_atk_cd:
                target = self._scan_turret_target(spatial_grid)
                if target is not None:
                    self._fire_timer = 0.0
                    if projectile_callback:
                        projectile_callback(tuple(self.pos), tuple(target.pos), "piercing")
                    target.take_damage(self._turret_atk_dmg, vfx_callback)
            return None

        if self.is_hq or self._spawn_rate_secs == 0:
            return None

        self.spawn_timer += dt
        if self.spawn_timer >= self._spawn_rate_secs:
            self.spawn_timer -= self._spawn_rate_secs
            if len(self.unit_types) > 1:
                spawned = random.choice(self.unit_types)
            else:
                spawned = self.unit_type
            return (spawned, self.spawn_point, self.lane)
        return None

    def _scan_turret_target(self, spatial_grid) -> Optional["Unit"]:
        nearest, nearest_dist = None, float("inf")
        my_ally_set = _ALLY_TEAMS if self.team in _ALLY_TEAMS else frozenset({self.team})
        candidates = spatial_grid.get_in_radius(self.pos, self._turret_scan_range)
        for u in candidates:
            if u.is_dead or u.team in my_ally_set:
                continue
            d = math.hypot(self.pos[0] - u.pos[0], self.pos[1] - u.pos[1])
            if d <= self._turret_scan_range and d < nearest_dist:
                nearest, nearest_dist = u, d
        return nearest

    # ── Damage / death ────────────────────────────────────────────────────────
    def take_damage(
        self,
        amount: int,
        vfx_callback: Optional[VFXCallback] = None,
    ) -> None:
        """
        Apply *amount* damage, honouring the building's damage_reduction.

        Damage pipeline (HQ with DR = 0.70)
        ------------------------------------
          raw_amount   = 15   (marine strike)
          effective    = max(1, int(15 × (1 − 0.70)))
                       = max(1, int(15 × 0.30))  = max(1, 4) = 4
          hp_new       = max(0, hp − 4)

        Slot buildings have DR = 0.0 — they receive the full raw amount.
        Minimum 1 damage is always applied so no hit is a complete wiff.
        """
        if self.is_dead:
            return
        # Armour reduction applied BEFORE subtracting HP
        effective = max(1, int(amount * (1.0 - self.damage_reduction)))
        self.hp = max(0, self.hp - effective)
        if self.hp == 0:
            self.die(vfx_callback)

    def die(self, vfx_callback: Optional[VFXCallback] = None) -> None:
        self.is_dead = True
        if vfx_callback:
            vfx_callback(tuple(self.pos))
        # Phase 4: fire HQ-death callback immediately so GameLoop can
        # transition to VICTORY/DEFEAT without waiting for the polling check.
        if self.is_hq and self.on_hq_death is not None:
            self.on_hq_death(self.team)
        print(f"[Building] {self.kind} (team={self.team}) destroyed")

    def demolish(
        self,
        resource_mgr: ResourceManager,
        vfx_callback: Optional[VFXCallback] = None,
    ) -> int:
        """
        Player-initiated demolition of a slot building.

        Actions (in order)
        ------------------
        1. Calculate refund = floor(self._cost × 0.6)  — 60 % of original cost.
        2. Call resource_mgr.refund(refund) to credit minerals immediately.
        3. Call resource_mgr.unregister_building(self) to stop income contribution.
        4. Call self.die() to mark the sprite dead (triggers VFX if callback given).

        Returns
        -------
        int  — the refund amount credited (useful for UI flash / logging).

        Notes
        -----
        - HQ buildings (is_hq=True) cannot be demolished; returns 0 immediately.
        - After demolish the caller should remove the building from slot_buildings
          and free its slot index from _occupied_slots.
        """
        if self.is_hq or self.is_dead:
            return 0

        refund = int(self._cost * 0.6)
        resource_mgr.refund(refund)
        resource_mgr.unregister_building(self)
        self.die(vfx_callback)
        print(
            f"[Building] demolish {self.kind}({self.lane})  "
            f"cost={self._cost}  refund={refund}"
        )
        return refund

    # ── Rendering ─────────────────────────────────────────────────────────────
    def draw(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        if self.is_dead:
            return
        super().draw(screen, camera_offset)
        self._draw_hp_bar(screen, camera_offset)
        if not self.is_hq:
            self._draw_spawn_bar(screen, camera_offset)
            self._draw_lane_dot(screen, camera_offset)

    def _draw_hp_bar(self, screen: pygame.Surface, cam: tuple[int, int]) -> None:
        cx = int(self.pos[0]) - cam[0]
        cy = int(self.pos[1]) - cam[1]
        bar_w, bar_h = 80, 7
        x = cx - bar_w // 2
        y = cy - self.surface.get_height() // 2 - 22
        ratio = max(0.0, self.hp / self.max_hp)
        if self.team == 2:
            fill_col = (220, 55, 55)    # RED   — enemy
        elif self.is_player:
            fill_col = (0, 180, 255)    # BLUE  — human player
        else:
            fill_col = (60, 220, 80)    # GREEN — allied AI (team 1)
        pygame.draw.rect(screen, (40, 10, 10),    (x, y, bar_w, bar_h))
        pygame.draw.rect(screen, fill_col,         (x, y, int(bar_w * ratio), bar_h))
        pygame.draw.rect(screen, (200, 200, 200), (x, y, bar_w, bar_h), 1)

    def _draw_spawn_bar(self, screen: pygame.Surface, cam: tuple[int, int]) -> None:
        """
        Cyan progress bar below the building showing time until next spawn.
        Fills left→right; resets to 0 on each spawn.
        """
        cx = int(self.pos[0]) - cam[0]
        cy = int(self.pos[1]) - cam[1]
        bar_w, bar_h = 64, 5
        x = cx - bar_w // 2
        y = cy + self.surface.get_height() // 2 + 6
        progress = self.spawn_progress
        pygame.draw.rect(screen, (20,  40,  70), (x, y, bar_w, bar_h))
        pygame.draw.rect(screen, (60, 200, 255), (x, y, int(bar_w * progress), bar_h))
        pygame.draw.rect(screen, (80, 140, 200), (x, y, bar_w, bar_h), 1)

    def _draw_lane_dot(self, screen: pygame.Surface, cam: tuple[int, int]) -> None:
        """Small coloured dot in the top-right corner indicating which lane."""
        cx = int(self.pos[0]) - cam[0]
        cy = int(self.pos[1]) - cam[1]
        color = _LANE_COLORS.get(self.lane, (200, 200, 200))
        pygame.draw.circle(screen, color, (cx + 38, cy - 38), 6)
        pygame.draw.circle(screen, (255, 255, 255), (cx + 38, cy - 38), 6, 1)


# ── Unit ──────────────────────────────────────────────────────────────────────
class Unit(GameSprite):
    """
    Mobile combat unit with a 3-state FSM: march → combat → assault (→ dead).

    States
    ------
    "march"   : following waypoints toward enemy base
    "combat"  : stopped, attacking nearest enemy unit in scan_range
    "assault" : waypoints exhausted, attacking nearest enemy HQ building
    "dead"    : removed by BattleManager next cleanup pass

    Parameters
    ----------
    kind        : "marine" | "tank"
    speed / hp  : override UNIT_STATS defaults if provided
    team        : 0 = player, 1 = enemy
    """

    def __init__(
        self,
        kind:       str,
        manager:    AssetManager,
        pos:        tuple[float, float],
        speed:      Optional[float] = None,
        hp:         Optional[int]   = None,
        team:       int             = 0,
        scan_range: Optional[float] = None,
        atk_cd:     Optional[int]   = None,
        atk_dmg:    Optional[int]   = None,
        is_player:  bool            = False,
    ) -> None:
        stats = UNIT_STATS.get(kind, UNIT_STATS["marine"])
        super().__init__(kind, manager, pos, scale=stats["scale"])

        self.kind             = kind
        self.hp               = hp        if hp        is not None else stats["hp"]
        self.max_hp           = self.hp
        self.speed            = speed     if speed     is not None else stats["speed"]
        self.atk_dmg          = atk_dmg   if atk_dmg   is not None else stats["atk_dmg"]
        # atk_cd: stored in seconds; UNIT_STATS values are in frames → convert
        _raw_cd               = atk_cd    if atk_cd    is not None else stats["atk_cd"]
        self.atk_cd:   float  = _raw_cd / 60.0
        self.scan_range       = scan_range if scan_range is not None else stats["scan_range"]
        self.collision_radius = stats["col_radius"]
        self.team             = team
        self.is_player        = is_player  # True = human-spawned (BLUE bar)

        # ── Flight / AA / AoE flags (pulled from UNIT_STATS; override per-unit) ──
        self.is_flying:      bool  = stats.get("is_flying",      False)
        self.can_attack_air: bool  = stats.get("can_attack_air", False)
        self.splash_radius:  int   = stats.get("splash_radius",  0)

        # ── Damage matrix types ───────────────────────────────────────────────
        self.atk_type:   str = stats.get("atk_type",   "normal")
        self.armor_type: str = stats.get("armor_type", "light")

        # ── Visual hover offset (air units appear above ground tiles) ────────
        # Purely cosmetic — physics, pathing, and collision use self.pos as-is.
        self.render_offset_y: int = int(stats.get("render_offset_y", 0))

        self.state:   str               = "march"
        self.is_dead: bool              = False
        self.target:  Optional[list[float]]        = None
        self.waypoints: list[tuple[float, float]]  = []
        self.atk_timer: float           = 0.0   # accumulated seconds since last attack
        self._locked_enemy:    Optional["Unit"]     = None
        self._target_building: Optional["Building"] = None

        # 2.5D flip state — True = facing right (sprite default)
        self._facing_right: bool = True

    # ── 2.5D direction override ───────────────────────────────────────────────
    def rotate_to(self, target: tuple[float, float]) -> None:
        """
        Units in 2.5D perspective never rotate — they only flip horizontally
        based on the horizontal component of the movement direction.

        Overrides GameSprite.rotate_to() to prevent the 180° full-rotation
        that caused upside-down sprites when units faced left.
        """
        dx = target[0] - self.pos[0]
        new_facing_right = (dx >= 0)
        if new_facing_right != self._facing_right:
            self._facing_right = new_facing_right
            # Re-derive surface from base so we never chain flips
            self.surface = (
                self._base_surface
                if self._facing_right
                else pygame.transform.flip(self._base_surface, True, False)
            )

    # ── Movement ──────────────────────────────────────────────────────────────
    def move_to(self, target: tuple[float, float]) -> None:
        self.target = list(target)
        self.rotate_to(target)

    def set_waypoints(self, waypoints: list[tuple[float, float]]) -> None:
        self.waypoints = list(waypoints)
        if self.waypoints:
            self.move_to(self.waypoints[0])

    # ── Scanning ──────────────────────────────────────────────────────────────
    def scan_for_enemies(
        self,
        spatial_grid,
        enemy_buildings: Optional[list["Building"]] = None,
    ) -> "Optional[Unit | Building]":
        nearest, nearest_dist = None, float("inf")
        my_ally_set = _ALLY_TEAMS if self.team in _ALLY_TEAMS else frozenset({self.team})

        candidates = spatial_grid.get_in_radius(self.pos, self.scan_range)
        for u in candidates:
            if u is self or u.team in my_ally_set or u.is_dead:
                continue
            if u.is_flying and not self.can_attack_air:
                continue
            d = self.dist_to(u)
            if d <= self.scan_range and d < nearest_dist:
                nearest, nearest_dist = u, d
        if nearest:
            return nearest

        if enemy_buildings:
            nearest_b, nearest_b_dist = None, float("inf")
            for b in enemy_buildings:
                if b.team in my_ally_set or b.is_dead:
                    continue
                d = self.dist_to(b)
                if d <= self.scan_range and d < nearest_b_dist:
                    nearest_b, nearest_b_dist = b, d
            return nearest_b

        return None

    def scan_for_buildings(
        self, buildings: list["Building"]
    ) -> Optional["Building"]:
        """
        Returns the nearest alive enemy HQ building.
        Only targets is_hq=True buildings so slot buildings are not attacked.
        Allied buildings (teams 0+1) never targeted by each other.
        """
        nearest, nearest_dist = None, float("inf")
        my_ally_set = _ALLY_TEAMS if self.team in _ALLY_TEAMS else frozenset({self.team})
        for b in buildings:
            if b.team in my_ally_set or b.is_dead or not b.is_hq:
                continue
            d = self.dist_to(b)
            if d < nearest_dist:
                nearest, nearest_dist = b, d
        return nearest

    # ── Combat ────────────────────────────────────────────────────────────────
    def _scaled_dmg(self, target_armor: str) -> int:
        """Return atk_dmg scaled by the DAMAGE_MATRIX multiplier, minimum 1."""
        mult = DAMAGE_MATRIX.get(self.atk_type, {}).get(target_armor, 1.0)
        return max(1, int(self.atk_dmg * mult))

    def attack(
        self,
        enemy: "Unit",
        vfx_callback:        Optional[VFXCallback]        = None,
        spatial_grid                                      = None,
        projectile_callback: Optional[Callable]           = None,
    ) -> None:
        if self.atk_timer < self.atk_cd:
            return
        self.atk_timer = 0.0

        if projectile_callback:
            projectile_callback(tuple(self.pos), tuple(enemy.pos), self.atk_type)

        actual_dmg = self._scaled_dmg(enemy.armor_type)
        enemy.take_damage(actual_dmg, vfx_callback)

        if self.splash_radius > 0 and spatial_grid is not None:
            my_ally_set = _ALLY_TEAMS if self.team in _ALLY_TEAMS else frozenset({self.team})
            splash_targets = spatial_grid.get_in_radius(enemy.pos, self.splash_radius)
            for u in splash_targets:
                if u is enemy or u.is_dead or u.team in my_ally_set:
                    continue
                dist = math.hypot(u.pos[0] - enemy.pos[0], u.pos[1] - enemy.pos[1])
                if dist <= self.splash_radius:
                    splash_dmg = self._scaled_dmg(u.armor_type)
                    u.take_damage(splash_dmg, vfx_callback)

    def attack_building(
        self,
        building: "Building",
        vfx_callback:        Optional[VFXCallback] = None,
        projectile_callback: Optional[Callable]    = None,
    ) -> None:
        if self.atk_timer < self.atk_cd:
            return
        self.atk_timer = 0.0
        # Spawn projectile heading for the building
        if projectile_callback:
            projectile_callback(tuple(self.pos), tuple(building.pos), self.atk_type)
        actual_dmg = self._scaled_dmg(building.armor_type)   # always "structure"
        building.take_damage(actual_dmg, vfx_callback)

    def take_damage(
        self,
        amount: int,
        vfx_callback: Optional[VFXCallback] = None,
    ) -> None:
        if self.is_dead:
            return
        self.hp = max(0, self.hp - amount)
        if self.hp == 0:
            self.die(vfx_callback)

    def die(self, vfx_callback: Optional[VFXCallback] = None) -> None:
        if self.is_dead:
            return
        self.is_dead = True
        self.state   = "dead"
        self.target  = None
        self.waypoints.clear()
        if vfx_callback:
            vfx_callback(tuple(self.pos))
        print(f"[Unit] {self.kind} (team={self.team}) died at {self.pos}")

    # ── Per-frame update (FSM) ────────────────────────────────────────────────
    def update(
        self,
        spatial_grid                               = None,
        vfx_callback:        Optional[VFXCallback]      = None,
        enemy_buildings:     Optional[list["Building"]] = None,
        dt:                  float                      = 1 / 60,
        projectile_callback: Optional[Callable]         = None,
    ) -> None:
        if self.is_dead: return
        if self.atk_timer < self.atk_cd: self.atk_timer += dt

        if spatial_grid is not None:
            scan_result = self.scan_for_enemies(spatial_grid, enemy_buildings)

            if isinstance(scan_result, Unit):
                if self.state != "combat": self.state = "combat"
                self._locked_enemy, self._target_building = scan_result, None
                self.rotate_to(tuple(scan_result.pos))
                self.attack(scan_result, vfx_callback, spatial_grid=spatial_grid, projectile_callback=projectile_callback)
                return
            elif isinstance(scan_result, Building):
                self._target_building, self._locked_enemy = scan_result, None
                self.state = "combat"
                self.rotate_to(tuple(scan_result.pos))
                atk_range = self.collision_radius + scan_result.collision_radius + 10
                if self.dist_to(scan_result) > atk_range:
                    dx, dy = scan_result.pos[0] - self.pos[0], scan_result.pos[1] - self.pos[1]
                    dist = math.hypot(dx, dy)
                    if dist > 1e-6:
                        step = self.speed * dt * 60
                        self.pos[0] += (dx / dist) * step
                        self.pos[1] += (dy / dist) * step
                else:
                    self.attack_building(scan_result, vfx_callback, projectile_callback=projectile_callback)
                return
            else:
                if self.state == "combat":
                    self.state, self._locked_enemy, self._target_building = "march", None, None
                    if self.waypoints: self.move_to(self.waypoints[0])

        if self.target or self.waypoints:
            self._march_step(dt)
            return

        if enemy_buildings is not None:
            if self._target_building is None or self._target_building.is_dead:
                self._target_building = self.scan_for_buildings(enemy_buildings)

            if self._target_building and not self._target_building.is_dead:
                self.state = "assault"
                self.rotate_to(tuple(self._target_building.pos))
                atk_range = self.collision_radius + self._target_building.collision_radius + 10
                if self.dist_to(self._target_building) > atk_range:
                    dx, dy = self._target_building.pos[0] - self.pos[0], self._target_building.pos[1] - self.pos[1]
                    dist = math.hypot(dx, dy)
                    if dist > 1e-6:
                        step = self.speed * dt * 60
                        self.pos[0] += (dx / dist) * step
                        self.pos[1] += (dy / dist) * step
                else:
                    self.attack_building(self._target_building, vfx_callback, projectile_callback=projectile_callback)
            else:
                self._target_building = None
                self.state = "march"

    def _march_step(self, dt: float = 1 / 60) -> None:
        if not self.target:
            if self.waypoints:
                self.move_to(self.waypoints.pop(0))
            return
        dx   = self.target[0] - self.pos[0]
        dy   = self.target[1] - self.pos[1]
        dist = math.hypot(dx, dy)
        step = self.speed * dt * 60   # px/frame × frames/s × s = px/s × dt
        if dist <= step:
            self.pos[0] = self.target[0]
            self.pos[1] = self.target[1]
            self.target = None
            if self.waypoints:
                self.move_to(self.waypoints.pop(0))
        else:
            self.pos[0] += (dx / dist) * step
            self.pos[1] += (dy / dist) * step

    # ── Rendering ─────────────────────────────────────────────────────────────
    def draw(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        if self.is_dead:
            return
        # render_offset_y lifts the sprite vertically so air units hover above
        # the floor tiles while pathing/collision continue to use self.pos.
        cx = int(self.pos[0]) - camera_offset[0]
        cy = int(self.pos[1]) - camera_offset[1] - self.render_offset_y
        rect = self.surface.get_rect(center=(cx, cy))
        screen.blit(self.surface, rect)
        self._draw_hp_bar(screen, camera_offset)

    def draw_debug(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        if self.is_dead:
            return
        super().draw_debug(screen, camera_offset)
        cx = int(self.pos[0]) - camera_offset[0]
        cy = int(self.pos[1]) - camera_offset[1]
        color = {
            "march":   (80,  160, 255),
            "combat":  (255,  80,  80),
            "assault": (255, 160,   0),
            "dead":    ( 80,  80,  80),
        }.get(self.state, (200, 200, 200))
        pygame.draw.circle(screen, color, (cx, cy), int(self.scan_range), 1)

    def _draw_hp_bar(self, screen: pygame.Surface, cam: tuple[int, int]) -> None:
        cx = int(self.pos[0]) - cam[0]
        # HP bar follows the hover offset so it stays attached to the sprite
        cy = int(self.pos[1]) - cam[1] - self.render_offset_y
        bar_w, bar_h = 44, 6
        x = cx - bar_w // 2
        y = cy - self.surface.get_height() // 2 - 10
        ratio = max(0.0, self.hp / self.max_hp)
        if self.team == 2:
            fill_col = (220, 55, 55)    # RED   — enemy
        elif self.is_player:
            fill_col = (0, 180, 255)    # BLUE  — human player
        else:
            fill_col = (60, 220, 80)    # GREEN — allied AI (team 1)
        pygame.draw.rect(screen, (30, 10, 10),   (x, y, bar_w, bar_h))
        pygame.draw.rect(screen, fill_col,        (x, y, int(bar_w * ratio), bar_h))
        pygame.draw.rect(screen, (180, 180, 180), (x, y, bar_w, bar_h), 1)


# ── VFX Sprite ────────────────────────────────────────────────────────────────
class VFXSprite:
    """
    Sci-fi EMP ring impact — pure Pygame geometry, zero sprite-sheet dependency.
    WASM-safe: no Surface allocation per frame, only pygame.draw calls.

    Visual: expanding hollow ring with a solid white hit-flash core on the
    first few frames, plus a dimmer inner echo ring for depth.
    """

    def __init__(
        self,
        pos:         tuple[float, float],
        color:       tuple[int, int, int] = (255, 120, 30),   # Ember-Orange death explosion
        max_radius:  int = 80,
        growth_rate: int = 6,
    ) -> None:
        self.pos         = list(pos)
        self.color       = color
        self.radius      = 2
        self.max_radius  = max_radius
        self.growth_rate = growth_rate
        self.is_done     = False

    def update(self, dt: float = 1 / 60) -> None:
        if self.is_done:
            return
        self.radius += self.growth_rate * dt * 60   # growth_rate in px/frame → dt-scaled
        if self.radius >= self.max_radius:
            self.is_done = True

    def draw(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        if self.is_done:
            return
        sx = int(self.pos[0]) - camera_offset[0]
        sy = int(self.pos[1]) - camera_offset[1]
        r  = int(self.radius)

        # Hit flash: solid white core for the first 3 growth steps
        if self.radius < self.growth_rate * 3:
            pygame.draw.circle(screen, (255, 255, 255), (sx, sy), max(r, 4))

        # Outer ring — main colour
        pygame.draw.circle(screen, self.color, (sx, sy), r, 2)

        # Inner echo ring — dimmer, 4 px inside outer ring
        if r > 6:
            dim = (self.color[0] // 2, self.color[1] // 2, self.color[2] // 2)
            pygame.draw.circle(screen, dim, (sx, sy), r - 4, 1)


# ── Projectile ────────────────────────────────────────────────────────────────
class Projectile:
    """
    Short-lived visual projectile spawned when a unit fires.

    Visual types
    ------------
    "bullet" (piercing / normal attack):
        Fast-moving yellow-white rectangle — rifle rounds, laser bolts.
        Speed: 900 px/s.
    "shell" (siege attack):
        Slower orange circle with a bright core — artillery shell.
        Speed: 480 px/s.

    Lifecycle
    ---------
    Each frame: update(dt) moves the projectile toward its fixed target_pos.
    When it arrives, is_done=True and the optional vfx_callback fires at
    the impact point so the existing EMP-ring VFX appears on contact.
    """

    _BULLET_SPEED: float = 900.0   # px/s
    _SHELL_SPEED:  float = 480.0   # px/s

    def __init__(
        self,
        from_pos:     tuple[float, float],
        to_pos:       tuple[float, float],
        atk_type:     str,
        vfx_callback: Optional[VFXCallback] = None,
    ) -> None:
        self.pos        = list(from_pos)
        self.target_pos = list(to_pos)
        self.atk_type   = atk_type
        self.visual_type: str = (
            "shell" if atk_type == "siege"
            else "acid"  if atk_type == "acid"
            else "laser" if atk_type == "laser"
            else "bullet"
        )
        # Lasers travel faster than bullets — crisp red beams from observers.
        self.speed: float = (
            self._SHELL_SPEED if self.visual_type == "shell"
            else 1200.0       if self.visual_type == "laser"
            else self._BULLET_SPEED
        )
        self.vfx_callback = vfx_callback
        self.is_done: bool = False

        # Pre-compute travel direction (normalised) for draw orientation
        dx = to_pos[0] - from_pos[0]
        dy = to_pos[1] - from_pos[1]
        dist = math.hypot(dx, dy)
        if dist > 1e-6:
            self._nx = dx / dist
            self._ny = dy / dist
        else:
            self._nx, self._ny = 1.0, 0.0

    def update(self, dt: float = 1 / 60) -> None:
        if self.is_done:
            return
        dx   = self.target_pos[0] - self.pos[0]
        dy   = self.target_pos[1] - self.pos[1]
        dist = math.hypot(dx, dy)
        step = self.speed * dt
        if dist <= step:
            self.pos[0] = self.target_pos[0]
            self.pos[1] = self.target_pos[1]
            self.is_done = True
            # Note: impact VFX (the legacy cyan EMP ring) is intentionally
            # NOT spawned here.  Only projectiles, acid glob flight, and
            # death explosions are allowed on-screen.
        else:
            self.pos[0] += (dx / dist) * step
            self.pos[1] += (dy / dist) * step

    def draw(
        self,
        screen: pygame.Surface,
        camera_offset: tuple[int, int] = (0, 0),
    ) -> None:
        if self.is_done:
            return
        sx = int(self.pos[0]) - camera_offset[0]
        sy = int(self.pos[1]) - camera_offset[1]

        if self.visual_type == "bullet":
            # Elongated yellow-white capsule oriented along travel direction
            nx, ny = self._nx, self._ny
            L = 10   # half-length in px
            ex, ey = int(nx * L), int(ny * L)
            pygame.draw.line(screen, (255, 245, 80),
                             (sx - ex, sy - ey), (sx + ex, sy + ey), 3)
            # Bright white core dot
            pygame.draw.circle(screen, (255, 255, 220), (sx, sy), 2)
        elif self.visual_type == "acid":
            # Acid glob: neon green outer ring + bright core — corrosive spit
            nx, ny = self._nx, self._ny
            L = 7
            ex, ey = int(nx * L), int(ny * L)
            pygame.draw.line(screen, (57, 255, 20),
                             (sx - ex, sy - ey), (sx + ex, sy + ey), 4)
            pygame.draw.circle(screen, (110, 255, 60), (sx, sy), 4)
            pygame.draw.circle(screen, (200, 255, 150), (sx, sy), 2)
        elif self.visual_type == "laser":
            # Red laser beam: long hot-red line with a bright pink-white core
            nx, ny = self._nx, self._ny
            L = 14
            ex, ey = int(nx * L), int(ny * L)
            pygame.draw.line(screen, (255,  40,  40),
                             (sx - ex, sy - ey), (sx + ex, sy + ey), 3)
            pygame.draw.line(screen, (255, 180, 200),
                             (sx - ex // 2, sy - ey // 2),
                             (sx + ex // 2, sy + ey // 2), 1)
            pygame.draw.circle(screen, (255, 220, 220), (sx, sy), 2)
        else:
            # Shell: outer orange ring + bright yellow core
            pygame.draw.circle(screen, (255, 110, 20), (sx, sy), 7)
            pygame.draw.circle(screen, (255, 200, 60), (sx, sy), 4)
            pygame.draw.circle(screen, (255, 240, 180), (sx, sy), 2)
