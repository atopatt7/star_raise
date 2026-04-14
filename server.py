"""
server.py — Star Raise FastAPI Backend  (v5+: Player Action API)

GET  /                      → health check
GET  /api/game_state        → full game snapshot
GET  /api/units             → unit list only
GET  /api/buildings         → building status

POST /api/action/build      → place a building  {"slot": int, "kind": str}
POST /api/action/demolish   → demolish a slot   {"slot": int}
POST /api/action/nuke       → fire nuke         {"x": float, "y": float}
"""
from __future__ import annotations
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.shared import read as read_state, push_action

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Star Raise Game API",
    description="Real-time game state + player action API",
    version="0.6.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Request models ────────────────────────────────────────────────────────────

class BuildAction(BaseModel):
    slot: int = Field(..., ge=0, le=31, description="Slot index 0–31")
    kind: str = Field(..., pattern="^(barracks|refinery)$")

class DemolishAction(BaseModel):
    slot: int = Field(..., ge=0, le=31, description="Slot index 0–31")

class NukeAction(BaseModel):
    x: float = Field(..., description="World X coordinate")
    y: float = Field(..., description="World Y coordinate")

# ── GET Endpoints ─────────────────────────────────────────────────────────────

@app.get("/", tags=["health"])
def root() -> dict:
    return {"status": "ok", "service": "star_raise_api", "version": "0.6.0"}

@app.get("/api/game_state", tags=["game"])
def game_state() -> JSONResponse:
    return JSONResponse(content=read_state())

@app.get("/api/units", tags=["game"])
def units() -> JSONResponse:
    state = read_state()
    return JSONResponse(content={
        "frame":      state["frame"],
        "unit_count": state["unit_count"],
        "units":      state["units"],
    })

@app.get("/api/buildings", tags=["game"])
def buildings() -> JSONResponse:
    state = read_state()
    return JSONResponse(content={
        "frame":          state["frame"],
        "game_result":    state["game_result"],
        "slot_buildings": state["slot_buildings"],
        "income_rate":    state["income_rate"],
        "buildings":      state["buildings"],
    })

# ── POST Action Endpoints ─────────────────────────────────────────────────────

@app.post("/api/action/build", tags=["action"])
def action_build(body: BuildAction) -> dict:
    """
    Place a building at the given slot index.
    The game loop will validate minerals and slot availability.
    Returns 409 if the game is already over.
    """
    state = read_state()
    if state.get("game_result") not in (None, "PLAYING"):
        raise HTTPException(status_code=409, detail="Game is already over")

    push_action({"type": "build", "slot": body.slot, "kind": body.kind})
    return {"queued": True, "action": "build", "slot": body.slot, "kind": body.kind}

@app.post("/api/action/demolish", tags=["action"])
def action_demolish(body: DemolishAction) -> dict:
    """
    Demolish the building at the given slot index (60% refund).
    Silently ignored if slot is empty — game loop handles validation.
    """
    state = read_state()
    if state.get("game_result") not in (None, "PLAYING"):
        raise HTTPException(status_code=409, detail="Game is already over")

    push_action({"type": "demolish", "slot": body.slot})
    return {"queued": True, "action": "demolish", "slot": body.slot}

@app.post("/api/action/nuke", tags=["action"])
def action_nuke(body: NukeAction) -> dict:
    """
    Fire the one-time tactical nuke at world coordinates (x, y).
    Returns 409 if nuke already expended or game is over.
    """
    state = read_state()
    if state.get("game_result") not in (None, "PLAYING"):
        raise HTTPException(status_code=409, detail="Game is already over")
    if not state.get("nuke_available", True):
        raise HTTPException(status_code=409, detail="Nuke already expended")

    push_action({"type": "nuke", "x": body.x, "y": body.y})
    return {"queued": True, "action": "nuke", "x": body.x, "y": body.y}

# ── Direct run ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)