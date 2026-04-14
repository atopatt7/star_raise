"""
asset_manager.py — Star Raise Game
AssetManager: 統一管理所有遊戲圖片素材
- 支援 Vercel / 本地 雙模式路徑解析
- Placeholder 機制: 檔案不存在時自動產生代表色塊
- Sprite Sheet 切割: 爆炸特效分格
"""

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
    # ── VFX ──
    "explosion_sheet": {
        "path":        os.path.join(_ASSETS_DIR, "vfx", "explosion_sheet.png"),
        "size":        None,              # 保留原始尺寸 (Sprite Sheet)
        "placeholder": (255, 120, 0),     # 橘色
    },
}

# ── Sprite Sheet 切割設定 ─────────────────────────────────────────────────────
EXPLOSION_SHEET_COLS = 4   # 每列幾格
EXPLOSION_SHEET_ROWS = 4   # 共幾列
EXPLOSION_FRAME_W    = 64
EXPLOSION_FRAME_H    = 64


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
        if not pygame.get_init():
            pygame.init()
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

    # ── Sprite Sheet 切割 ────────────────────────────────────────────────────
    def get_frames(
        self,
        key: str,
        cols: int = EXPLOSION_SHEET_COLS,
        rows: int = EXPLOSION_SHEET_ROWS,
        frame_w: int = EXPLOSION_FRAME_W,
        frame_h: int = EXPLOSION_FRAME_H,
    ) -> list[pygame.Surface]:
        """
        將 Sprite Sheet 切割為動畫幀列表。

        Parameters
        ----------
        key     : 素材名稱 (預設用 "explosion_sheet")
        cols    : Sheet 橫向格數
        rows    : Sheet 縱向格數
        frame_w : 單格寬度
        frame_h : 單格高度

        Returns
        -------
        list[pygame.Surface]: 依序排列的動畫幀
        """
        cache_key = f"{key}:frames:{cols}x{rows}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        spec = ASSET_SPEC.get(key)
        if spec is None:
            raise KeyError(f"[AssetManager] 未知素材 key: '{key}'")

        sheet = self._load_or_placeholder(spec)
        sheet_w, sheet_h = sheet.get_size()

        # 若 sheet 尺寸不足，自動調整
        actual_cols = min(cols, sheet_w  // max(frame_w, 1))
        actual_rows = min(rows, sheet_h  // max(frame_h, 1))
        actual_cols = max(actual_cols, 1)
        actual_rows = max(actual_rows, 1)

        frames: list[pygame.Surface] = []
        for row in range(actual_rows):
            for col in range(actual_cols):
                rect   = pygame.Rect(col * frame_w, row * frame_h, frame_w, frame_h)
                frame  = pygame.Surface((frame_w, frame_h), pygame.SRCALPHA)
                frame.blit(sheet, (0, 0), rect)
                frames.append(frame)

        print(f"[AssetManager] 🎞  切割 '{key}': {len(frames)} 幀 ({actual_cols}×{actual_rows})")
        self._cache[cache_key] = frames
        return frames

    # ── 工具方法 ─────────────────────────────────────────────────────────────
    def preload_all(self) -> None:
        """預先讀取所有素材（在載入畫面使用）。"""
        for key in ASSET_SPEC:
            if key == "explosion_sheet":
                self.get_frames(key)
            else:
                self.get(key)

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
