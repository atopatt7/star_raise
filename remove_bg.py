"""
remove_bg.py — 從 assets/generated/ 重新去背，輸出到 assets/buildings/ 和 assets/units/
用法：python remove_bg.py

演算法：
  BFS flood fill 從圖片四角 + 多個邊緣點出發，
  判定「是背景」的條件：
    1. R ≈ G ≈ B（純灰）：三通道最大差值 < 22
    2. 亮度 80–220：涵蓋棋盤的深灰(~129)和淺灰(~177)
  兩個條件同時成立才標記為透明，避免誤傷有色的 sprite。
  從 assets/generated/ 讀取原始圖，避免處理已被修改過的版本。
"""
from PIL import Image
import numpy as np
from collections import deque
import os, shutil

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


def remove_bg(path: str) -> Image.Image:
    """
    從四角及多個邊緣種子點做 BFS，
    把純灰（R≈G≈B）且亮度 80-220 的連通區域設為透明。
    """
    img = Image.open(path).convert("RGBA")
    data = np.array(img, dtype=np.int32)
    h, w = data.shape[:2]

    visited = np.zeros((h, w), dtype=bool)
    mask    = np.zeros((h, w), dtype=bool)

    def is_gray_bg(y: int, x: int) -> bool:
        # 已透明的像素直接跳過（第一次處理過後的圖可能有這種情況）
        if data[y, x, 3] == 0:
            return False
        r, g, b = int(data[y, x, 0]), int(data[y, x, 1]), int(data[y, x, 2])
        if max(abs(r - g), abs(g - b), abs(r - b)) >= 22:
            return False
        brightness = (r + g + b) // 3
        return 80 <= brightness <= 220

    # 密集邊緣種子：沿四條邊每隔 8px 一個點
    seeds = set()
    for x in range(0, w, 8):
        seeds.add((0, x))
        seeds.add((h - 1, x))
    for y in range(0, h, 8):
        seeds.add((y, 0))
        seeds.add((y, w - 1))

    queue = deque()
    for sy, sx in seeds:
        if 0 <= sy < h and 0 <= sx < w and not visited[sy, sx]:
            visited[sy, sx] = True
            queue.append((sy, sx))

    while queue:
        y, x = queue.popleft()
        if not is_gray_bg(y, x):
            continue
        mask[y, x] = True
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                visited[ny, nx] = True
                queue.append((ny, nx))

    result = np.array(img)
    result[mask, 3] = 0
    return Image.fromarray(result, "RGBA")


def process_all() -> None:
    targets = (
        [("assets/generated", "assets/buildings", name) for name in BUILDINGS] +
        [("assets/generated", "assets/units",     name) for name in UNITS]
    )

    ok = fail = 0
    for src_dir, dst_dir, name in targets:
        src = os.path.join(src_dir, f"{name}.png")
        dst = os.path.join(dst_dir, f"{name}.png")

        if not os.path.exists(src):
            print(f"  ⚠  找不到原始圖 {src}，跳過")
            continue

        os.makedirs(dst_dir, exist_ok=True)
        try:
            img = remove_bg(src)
            img.save(dst)

            arr = np.array(img)
            total = arr.shape[0] * arr.shape[1]
            pct   = 100 * (arr[:, :, 3] == 0).sum() / total
            print(f"  ✅  {dst_dir}/{name}.png  透明 {pct:.0f}%")
            ok += 1
        except Exception as e:
            print(f"  ❌  {name}：{e}")
            fail += 1

    print(f"\n完成！成功 {ok} / {ok + fail}  失敗 {fail}")
    if fail:
        print("提示：重新執行此腳本可重試失敗的圖片。")


if __name__ == "__main__":
    process_all()
