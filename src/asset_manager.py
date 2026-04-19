"""
asset_manager.py — Star Raise Game
AssetManager: 統一管理所有遊戲圖片素材
- 支援 Vercel / 本地 雙模式路徑解析
- Placeholder 機制: 檔案不存在時自動產生代表色塊
- Sprite Sheet 切割: 爆炸特效分格
"""

import asyncio
import math
import pygame
from typing import Optional

# ── 素材規格表 ────────────────────────────────────────────────────────────────
ASSET_SPEC: dict[str, dict] = {
    # ── Units ──
    "marine": {
        "path":        "assets/units/marine.png",
        "size":        (32, 32),
        "placeholder": (30, 100, 220),    # 藍色
    },
    "tank": {
        "path":        "assets/units/tank.png",
        "size":        (64, 64),
        "placeholder": (50, 180, 50),     # 綠色
    },
    "jackal": {
        "path":        "assets/units/jackal.png",
        "size":        (52, 60),
        "placeholder": (210, 160, 40),    # 金黃色 (fast vehicle)
    },
    "ghost": {
        "path":        "assets/units/ghost.png",
        "size":        (44, 60),
        "placeholder": (50, 55, 70),      # 深藍灰 (stealth)
    },
    "hellfire": {
        "path":        "assets/units/hellfire.png",
        "size":        (60, 76),
        "placeholder": (160, 60, 30),     # 深紅橙 (heavy artillery)
    },
    "valkyrie": {
        "path":        "assets/units/valkyrie.png",
        "size":        (64, 56),
        "placeholder": (70, 120, 200),    # 天藍色 (gunship)
    },
    # ── Buildings ──
    "barracks": {
        "path":        "assets/buildings/barracks.png",
        "size":        (128, 128),
        "placeholder": (180, 120, 40),    # 橘棕色
    },
    "refinery": {
        "path":        "assets/buildings/refinery.png",
        "size":        (128, 128),
        "placeholder": (160, 60, 200),    # 紫色
    },
    "rover_bay": {
        "path":        "assets/buildings/rover_bay.png",
        "size":        (128, 128),
        "placeholder": (210, 160, 40),    # 金黃色
    },
    "spec_ops": {
        "path":        "assets/buildings/spec_ops.png",
        "size":        (128, 128),
        "placeholder": (50, 55, 90),      # 深藍
    },
    "heavy_factory": {
        "path":        "assets/buildings/heavy_factory.png",
        "size":        (128, 128),
        "placeholder": (160, 60, 30),     # 深紅
    },
    "starport": {
        "path":        "assets/buildings/starport.png",
        "size":        (128, 128),
        "placeholder": (70, 120, 200),    # 天藍
    },
    # ── Swarm faction buildings ──
    "swarm_hq": {
        "path":        "assets/buildings/swarm_hq.png",
        "size":        (128, 128),
        "placeholder": (80, 20, 120),     # deep purple
    },
    "acid_pool": {
        "path":        "assets/buildings/acid_pool.png",
        "size":        (96, 96),
        "placeholder": (40, 160, 20),     # slime green
    },
    "toxin_chamber": {
        "path":        "assets/buildings/toxin_chamber.png",
        "size":        (96, 96),
        "placeholder": (120, 30, 90),     # fleshy violet spire
    },
    # ── Swarm faction units ──
    "crawler": {
        "path":        "assets/units/crawler.png",
        "size":        (32, 32),
        "placeholder": (50, 20, 70),      # dark purple chitin
    },
    "spitter": {
        "path":        "assets/units/spitter.png",
        "size":        (32, 32),
        "placeholder": (40, 180, 30),     # acid green
    },
    # ── Rogue AI faction units ──
    "observer": {
        "path":        "assets/units/observer.png",
        "size":        (32, 32),
        "placeholder": (220, 40, 40),     # red optic drone
    },
    "ravager": {
        "path":        "assets/units/ravager.png",
        "size":        (32, 32),
        "placeholder": (120, 60, 180),    # violet alloy bruiser
    },
    "coder": {
        "path":        "assets/units/coder.png",
        "size":        (32, 32),
        "placeholder": (40, 220, 180),    # cyan-green hacker aura
    },
    "splitter": {
        "path":        "assets/units/splitter.png",
        "size":        (32, 32),
        "placeholder": (80, 40, 140),     # deep indigo siege shell
    },
    # ── Rogue AI faction buildings ──
    "logic_core": {
        "path":        "assets/buildings/logic_core.png",
        "size":        (96, 96),
        "placeholder": (40, 80, 160),     # cool electric-blue processor
    },
    "data_node": {
        "path":        "assets/buildings/data_node.png",
        "size":        (96, 96),
        "placeholder": (0, 180, 160),     # teal/cyan coder relay station
    },
    "quantum_array": {
        "path":        "assets/buildings/quantum_array.png",
        "size":        (96, 96),
        "placeholder": (140, 60, 200),    # deep violet quantum spires
    },
    "assembly_matrix": {
        "path":        "assets/buildings/assembly_matrix.png",
        "size":        (96, 96),
        "placeholder": (80, 40, 140),     # indigo splitter forge
    },
    "plasma_tower": {
        "path":        "assets/buildings/plasma_tower.png",
        "size":        (64, 64),
        "placeholder": (200, 40, 40),     # glowing red defence turret
    },
    # ── Special buildings ──
    "hq": {
        "path":        "assets/buildings/hq.png",
        "size":        (128, 128),
        "placeholder": (100, 180, 255),   # 藍色 HQ
    },
    "rogue_hq": {
        "path":        "assets/buildings/rogue_hq.png",
        "size":        (128, 128),
        "placeholder": (200, 40, 60),     # 赤紅叛變AI 核心主機
    },
    "turret": {
        "path":        "assets/buildings/turret.png",
        "size":        (96, 96),
        "placeholder": (60, 80, 110),     # 深藍灰 turret
    },
    # ── Background ──
    "background": {
        "path":        "assets/background.png",
        "size":        None,          # loaded at native resolution (256×256)
        "placeholder": (8, 4, 18),   # deep-space near-black fallback
    },
    # ── UI ──
    "resource_icon": {
        "path":        "assets/ui/resource_icon.png",
        "size":        (32, 32),
        "placeholder": (240, 200, 20),    # 金黃色
    },
    "nuke_button": {
        "path":        "assets/ui/nuke_button.png",
        "size":        (64, 64),
        "placeholder": (220, 30, 30),     # 紅色
    },
}


class AssetManager:
    """
    統一讀取、快取、回退所有遊戲素材。

    使用方式
    --------
    manager = AssetManager()
    surface = manager.get("marine")          # 取得單一 Surface
    frames  = manager.get_frames("explosion_sheet")  # 取得動畫幀列表
    """

    def __init__(self) -> None:
        if not pygame.display.get_init():
            # Use explicit sub-module init to avoid triggering pygame.mixer
            pygame.display.init()
            pygame.font.init()
            pygame.event.init()
        self._cache: dict[str, pygame.Surface] = {}

    # ── 核心讀取 ──────────────────────────────────────────────────────────────
    def get(self, key: str, scale: Optional[tuple[int, int]] = None) -> pygame.Surface:
        """
        取得素材 Surface，優先從快取返回。
        若檔案不存在，自動回傳代表色塊。

        Parameters
        ----------
        key   : ASSET_SPEC 中定義的素材名稱
        scale : 若傳入 (w, h) 則覆蓋規格表預設尺寸
        """
        cache_key = f"{key}@{scale}" if scale else key
        if cache_key in self._cache:
            return self._cache[cache_key]

        spec = ASSET_SPEC.get(key)
        if spec is None:
            raise KeyError(f"[AssetManager] 未知素材 key: '{key}'")

        surface = self._load_or_placeholder(spec)

        # ── 縮放 ──
        target_size = scale or spec.get("size")
        if target_size:
            surface = pygame.transform.scale(surface, target_size)

        self._cache[cache_key] = surface
        return surface

    def _load_or_placeholder(self, spec: dict) -> pygame.Surface:
        """Load image via pure relative path — ALWAYS returns a Surface."""
        path = spec["path"]   # e.g. "assets/units/marine.png"
        print(f"DEBUG: Loading {path}")

        # Attempt 1: pygbag patched loader — pure relative path, no leading slash
        try:
            surface = pygame.image.load(path).convert_alpha()
            return surface
        except Exception as e:
            print(f"[AssetManager] Load failed for {path}: {e}")

        # Attempt 2: Coloured placeholder — CRITICAL: must not return None
        print(f"[AssetManager] Using placeholder for: {path}")
        size  = spec.get("size") or (64, 64)
        color = spec.get("placeholder", (200, 200, 200))
        try:
            surf = pygame.Surface(size, pygame.SRCALPHA)
            surf.fill((*color, 200))
            pygame.draw.rect(surf, (255, 255, 255), surf.get_rect(), 2)
            return surf
        except Exception as e:
            print(f"[AssetManager] Placeholder failed: {e}")

        # Absolute last resort: 1x1 transparent surface
        return pygame.Surface((1, 1), pygame.SRCALPHA)


    def preload_all(self) -> None:
        """預先讀取所有素材（在載入畫面使用）。"""
        for key in ASSET_SPEC:
            self.get(key)

    async def preload_all_async(self) -> None:
        """Async version — yields to browser after each asset so WASM doesn't freeze."""
        for key in ASSET_SPEC:
            self.get(key)
            await asyncio.sleep(0)   # yield to browser event loop

    def clear_cache(self) -> None:
        """清除快取（切換場景時呼叫）。"""
        self._cache.clear()
        print("[AssetManager] 🗑  快取已清除")

    @staticmethod
    def resolve_path(*parts: str) -> str:
        """Return a pure relative path joined with '/' for WASM compatibility."""
        return "/".join(str(p).strip("/") for p in parts)
