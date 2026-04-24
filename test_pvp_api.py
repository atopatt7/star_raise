import requests
import time

BASE_URL = "http://127.0.0.1:8000"

def test_build(player_id: int, slot: int, kind: str):
    player_label = "Player 1 (本機)" if player_id == 0 else "Player 2 (對手)"
    print(f"[{player_label}] 嘗試建造: {kind} 於位置 {slot}")
    
    payload = {
        "player_id": player_id,
        "slot": slot,
        "kind": kind
    }
    
    try:
        res = requests.post(f"{BASE_URL}/api/action/build", json=payload)
        print(f"狀態碼: {res.status_code}")
        print(f"回應內容: {res.json()}\n")
    except requests.exceptions.ConnectionError:
        print("錯誤：無法連線到伺服器。請確認您已經啟動了 python main.py\n")

if __name__ == "__main__":
    print("=== Star Raise API 雙人對戰測試腳本 ===\n")
    
    # 玩家 1 在左側 (Slot 2) 蓋步兵營
    test_build(player_id=0, slot=2, kind="barracks")
    
    time.sleep(0.5)
    
    # 玩家 2 在右側 (Slot 29，敵方區域) 蓋蟲族酸池
    test_build(player_id=1, slot=29, kind="acid_pool")
    
    # 玩家 2 嘗試發射核彈
    print("[Player 2 (對手)] 嘗試發射核彈")
    try:
        res = requests.post(f"{BASE_URL}/api/action/nuke", json={"player_id": 1, "x": 800, "y": 600})
        print(f"回應內容: {res.json()}\n")
    except Exception as e:
        print(f"核彈測試失敗: {e}")