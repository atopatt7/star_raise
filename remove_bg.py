"""
remove_bg.py — 批次移除遊戲美術圖的灰色棋盤背景
用法：python remove_bg.py
"""
from PIL import Image
import numpy as np
from collections import deque
import os

BUILDINGS = (
    "hq barracks rover_bay spec_ops refinery heavy_factory starport "
    "swarm_hq acid_pool toxin_chamber mutation_pit hive_nest spine_ridge scourge_nest "
    "rogue_hq sensor_array data_node assembly_matrix plasma_forge quantum_core oblivion_engine"
).split()

UNITS = (
    "marine jackal ghost tank hellfire valkyrie "
    "crawler spitter crusher weaver impaler scourge "
    "observer coder sentinel obliterator tracker purifier"
).split()


def remove_bg(path: str, tolerance: int = 45) -> Image.Image:
    """
    從四個角落開始 BFS flood fill，把灰色棋盤背景變成透明。
    tolerance: 顏色距離容差（越大去除越多，但可能誤傷近灰色的sprite）
    """
    img = Image.open(path).convert("RGBA")
    data = np.array(img, dtype=np.int32)
    h, w = data.shape[:2]

    # 取四角平均色作為背景色基準
    corners = [data[0, 0, :3], data[0, w-1, :3],
               data[h-1, 0, :3], data[h-1, w-1, :3]]
    bg = np.mean(corners, axis=0)

    mask = np.zeros((h, w), dtype=bool)
    visited = np.zeros((h, w), dtype=bool)

    # 多點起始種子：四角 + 四邊中點
    seeds = [
        (0, 0), (0, w-1), (h-1, 0), (h-1, w-1),
        (0, w//2), (h-1, w//2), (h//2, 0), (h//2, w-1),
    ]
    queue = deque()
    for sy, sx in seeds:
        if not visited[sy, sx]:
            visited[sy, sx] = True
            queue.append((sy, sx))

    while queue:
        y, x = queue.popleft()
        px = data[y, x, :3].astype(float)

        # 條件1：顏色接近背景色
        color_dist = float(np.sqrt(np.sum((px - bg) ** 2)))
        # 條件2：像素是灰色（R≈G≈B，棋盤格特徵）
        r, g, b = int(data[y, x, 0]), int(data[y, x, 1]), int(data[y, x, 2])
        is_gray = max(abs(r-g), abs(g-b), abs(r-b)) < 30

        if color_dist < tolerance and is_gray:
            mask[y, x] = True
            for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))

    result = np.array(img)
    result[mask, 3] = 0          # 背景像素 alpha → 0（透明）
    return Image.fromarray(result, "RGBA")


def process_all() -> None:
    targets = (
        [("assets/buildings", name) for name in BUILDINGS] +
        [("assets/units",     name) for name in UNITS]
    )

    ok = fail = 0
    for folder, name in targets:
        path = os.path.join(folder, f"{name}.png")
        if not os.path.exists(path):
            print(f"  ⚠  找不到 {path}，跳過")
            continue
        try:
            img = remove_bg(path)
            img.save(path)

            arr = np.array(img)
            pct = 100 * (arr[:, :, 3] == 0).sum() / (arr.shape[0] * arr.shape[1])
            print(f"  ✅  {folder}/{name}.png  透明 {pct:.0f}%")
            ok += 1
        except Exception as e:
            print(f"  ❌  {path}：{e}")
            fail += 1

    print(f"\n完成！成功 {ok} / {ok+fail}  失敗 {fail}")
    if fail:
        print("提示：重新執行此腳本可重試失敗的圖片。")


if __name__ == "__main__":
    process_all()
