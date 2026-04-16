"""
asset_manager.py — Star Raise Game
AssetManager: 統一管理所有遊戲圖片素材
- 支援 Vercel / 本地 雙模式路徑解析
- Placeholder 機制: 檔案不存在時自動產生代表色塊
- Sprite Sheet 切割: 爆炸特效分格
"""

import asyncio
import os
import math
import pygame
from typing import Optional

# ── 路徑常數 ──────────────────────────────────────────────────────────────────
# __file__ 所在目錄 → 往上一層到專案根目錄 → assets/
_SRC_DIR    = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR   = os.path.dirname(_SRC_DIR)
_ASSETS_DIR = os.path.join(_ROOT_DIR, "assets")

# ── 素材規格表 ────────────────────────────────────────────────────────────────
ASSET_SPEC: dict[str, dict] = {
    # ── Units ──
    "marine": {
        "path":        os.path.join(_ASSETS_DIR, "units", "marine.png"),
        "size":        (32, 32),
        "placeholder": (30, 100, 220),    # 藍色
    },
    "tank": {
        "path":        os.path.join(_ASSETS_DIR, "units", "tank.png"),
        "size":        (64, 64),
        "placeholder": (50, 180, 50),     # 綠色
    },
    "jackal": {
        "path":        os.path.join(_ASSETS_DIR, "units", "jackal.png"),
        "size":        (52, 60),
        "placeholder": (210, 160, 40),    # 金黃色 (fast vehicle)
    },
    "ghost": {
        "path":        os.path.join(_ASSETS_DIR, "units", "ghost.png"),
        "size":        (44, 60),
        "placeholder": (50, 55, 70),      # 深藍灰 (stealth)
    },
    "hellfire": {
        "path":        os.path.join(_ASSETS_DIR, "units", "hellfire.png"),
        "size":        (60, 76),
        "placeholder": (160, 60, 30),     # 深紅橙 (heavy artillery)
    },
    "valkyrie": {
        "path":        os.path.join(_ASSETS_DIR, "units", "valkyrie.png"),
        "size":        (64, 56),
        "placeholder": (70, 120, 200),    # 天藍色 (gunship)
    },
    # ── Buildings ──
    "barracks": {
        "path":        os.path.join(_ASSETS_DIR, "buildings", "barracks.png"),
        "size":        (128, 128),
        "placeholder": (180, 120, 40),    # 橘棕色
    },
    "refinery": {
        "path":        os.path.join(_ASSETS_DIR, "buildings", "refinery.png"),
        "size":        (128, 128),
        "placeholder": (160, 60, 200),    # 紫色
    },
    "rover_bay": {
        "path":        os.path.join(_ASSETS_DIR, "buildings", "rover_bay.png"),
        "size":        (128, 128),
        "placeholder": (210, 160, 40),    # 金黃色
    },
    "spec_ops": {
        "path":        os.path.join(_ASSETS_DIR, "buildings", "spec_ops.png"),
        "size":        (128, 128),
        "placeholder": (50, 55, 90),      # 深藍
    },
    "heavy_factory": {
        "path":        os.path.join(_ASSETS_DIR, "buildings", "heavy_factory.png"),
        "size":        (128, 128),
        "placeholder": (160, 60, 30),     # 深紅
    },
    "starport": {
        "path":        os.path.join(_ASSETS_DIR, "buildings", "starport.png"),
        "size":        (128, 128),
        "placeholder": (70, 120, 200),    # 天藍
    },
    # ── UI ──
    "resource_icon": {
        "path":        os.path.join(_ASSETS_DIR, "ui", "resource_icon.png"),
        "size":        (32, 32),
        "placeholder": (240, 200, 20),    # 金黃色
    },
    "nuke_button": {
        "path":        os.path.join(_ASSETS_DIR, "ui", "nuke_button.png"),
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
        """嘗試讀取檔案；失敗時產生代表色塊。"""
        path = spec["path"]
        if os.path.isfile(path):
            try:
                surface = pygame.image.load(path).convert_alpha()
                print(f"[AssetManager] ✅ 讀取: {path}")
                return surface
            except pygame.error as e:
                print(f"[AssetManager] ⚠️  讀取失敗 ({e})，使用 placeholder: {path}")
        else:
            print(f"[AssetManager] ⚠️  檔案不存在，使用 placeholder: {path}")

        # Placeholder: 用規格尺寸或預設 64×64
        size  = spec.get("size") or (64, 64)
        color = spec.get("placeholder", (200, 200, 200))
        surf  = pygame.Surface(size, pygame.SRCALPHA)
        surf.fill((*color, 200))          # 帶透明度的色塊

        # 畫邊框，方便辨識
        pygame.draw.rect(surf, (255, 255, 255), surf.get_rect(), 2)
        return surf

    # ── 工具方法 ─────────────────────────────────────────────────────────────
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
        """
        組合路徑，確保 Vercel 靜態資源路徑正確。
        Vercel 部署時根目錄為 /var/task，可透過環境變數覆蓋。

        範例
        ----
        path = AssetManager.resolve_path("assets", "units", "marine.png")
        """
        vercel_root = os.environ.get("VERCEL_ASSET_ROOT", _ROOT_DIR)
        return os.path.join(vercel_root, *parts)
