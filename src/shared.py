"""
shared.py — Star Raise  (v5+: Action Queue)
Thread-safe game-state snapshot + player action queue for FastAPI.

GameLoop (main thread):
  - writes every frame via write()
  - reads & clears pending actions via pop_actions()

uvicorn (daemon thread):
  - reads state via read()
  - pushes player actions via push_action()
"""
import threading
from typing import Any

_lock:  threading.Lock = threading.Lock()

# ── Game state snapshot ───────────────────────────────────────────────────────
_state: dict[str, Any] = {
    "frame":        0,
    "game_result":  None,
    "minerals":      0,
    "income_base":   10,
    "income_bonus":  0,
    "income_rate":   10,
    "unit_count":    0,
    "units":         [],
    "buildings":     [],
    "slot_buildings": 0,
}

# ── Player action queue ───────────────────────────────────────────────────────
# Each action is a dict, e.g.:
#   {"type": "build",    "slot": 3,    "kind": "barracks"}
#   {"type": "demolish", "slot": 3}
#   {"type": "nuke",     "x": 4000.0, "y": 295.0}
_action_queue: list[dict[str, Any]] = []

# ── State read/write ──────────────────────────────────────────────────────────

def write(data: dict[str, Any]) -> None:
    """GameLoop calls this every frame to update the snapshot."""
    with _lock:
        _state.update(data)

def read() -> dict[str, Any]:
    """API handler calls this; returns a shallow copy of the current snapshot."""
    with _lock:
        return dict(_state)

# ── Action queue ──────────────────────────────────────────────────────────────

def push_action(action: dict[str, Any]) -> None:
    """
    API handler calls this to enqueue a player action.
    action must have a 'type' key: 'build' | 'demolish' | 'nuke'
    """
    with _lock:
        _action_queue.append(action)

def pop_actions() -> list[dict[str, Any]]:
    """
    GameLoop calls this once per frame to drain and return all pending actions.
    Returns a list (may be empty). Clears the queue atomically.
    """
    with _lock:
        if not _action_queue:
            return []
        actions = list(_action_queue)
        _action_queue.clear()
        return actions