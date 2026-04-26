"""
input_handler.py — Star Raise Input Controller

Extracts all event-loop and tap-begin logic from main.py into a dedicated
InputHandler class so main.py stays lean.

State owned here (not on GameLoop):
  lmb_down               — left-mouse / touch is currently held
  lmb_down_pos           — screen position when it was pressed
  _touch_down_ui_handled — iOS WebKit guard (FINGERDOWN already handled tap)
  _nuke_just_armed       — suppress the detonation on the same frame the nuke was armed
"""

from __future__ import annotations
import math
import random

import pygame

from src.logic    import BuildState, GameState, BUILDING_SPECS
from src.commands import BuildCommand, DemolishCommand, NukeCommand, UpgradeCommand


def _main_consts():
    """Lazy fetch of module-level constants from main to avoid circular import."""
    import sys
    m = sys.modules.get("__main__") or sys.modules.get("main")
    return (
        getattr(m, "SCREEN_W",   2556),
        getattr(m, "SCREEN_H",   1179),
        getattr(m, "WORLD_W",    11502),
        getattr(m, "ALL_SLOTS",  []),
        getattr(m, "CARD_COSTS", {}),
    )


class InputHandler:
    def __init__(self) -> None:
        self.lmb_down:               bool           = False
        self.lmb_down_pos:           tuple[int,int] = (0, 0)
        self._touch_down_ui_handled: bool           = False
        self._nuke_just_armed:       bool           = False

    # ── Coordinate helper ─────────────────────────────────────────────────────
    def _evt_pos(self, event, game) -> tuple[int, int]:
        """
        Return screen-pixel (x, y) for any pointer event.

        FINGER* events carry normalised floats (0.0–1.0); multiply by the
        actual display-surface size so the result is correct even when pygbag
        scales the WebGL canvas to fit the browser window.
        MOUSE* events already carry integer pixel coords in event.pos.
        """
        SCREEN_W, SCREEN_H, _, _, _ = _main_consts()
        if event.type in (pygame.FINGERDOWN, pygame.FINGERUP, pygame.FINGERMOTION):
            surf = pygame.display.get_surface()
            sw, sh = (surf.get_width(), surf.get_height()) if surf else (SCREEN_W, SCREEN_H)
            return int(event.x * sw), int(event.y * sh)
        mx, my = event.pos
        s = getattr(game, "_scale", 1.0)
        if s < 1.0:
            return int(mx / s), int(my / s)
        return event.pos

    # ── Tap-begin ─────────────────────────────────────────────────────────────
    def do_tap_begin(self, game, mx: int, my: int) -> None:
        """
        All 'activate on tap' UI logic — called from both FINGERDOWN/
        MOUSEBUTTONDOWN (normal path) and FINGERUP fallback (iOS WebKit).

        Only pure state-transition / mode-entry logic lives here.
        Placement / detonation / demolish finalisation stay in the UP handler.
        """
        SCREEN_W, SCREEN_H, WORLD_W, ALL_SLOTS, CARD_COSTS = _main_consts()

        # Reset the "this tap landed on the minimap" flag for every new tap.
        game._tap_was_minimap = False

        # ── Main menu ─────────────────────────────────────────────────────────
        if game.game_state == GameState.MAIN_MENU:
            hit = game.ui.main_menu_hit_test(mx, my)
            if hit == "1v1":
                game.pending_game_mode = "1v1"
                game.game_state = GameState.FACTION_SELECT
            elif hit == "2v2":
                game.pending_game_mode = "2v2"
                game.game_state = GameState.FACTION_SELECT
            elif hit == "pvp":
                game.pending_game_mode = "pvp"
                game.game_state = GameState.FACTION_SELECT
            elif hit == "unit_info":
                game.game_state = GameState.UNIT_INFO
            elif hit == "settings":
                game.game_state = GameState.SETTINGS

        # ── Settings overlay ──────────────────────────────────────────────────
        elif game.game_state == GameState.SETTINGS:
            hit = game.ui.settings_hit_test(mx, my)
            if hit == "sfx":
                game.sfx_on = not game.sfx_on
                game.ui.push_notif(
                    f"音效  {'ON ✓' if game.sfx_on else 'OFF'}", mx, my,
                    color=(0, 220, 120) if game.sfx_on else (180, 100, 100),
                )
            elif hit == "close":
                game.game_state = GameState.MAIN_MENU

        # ── Faction select ────────────────────────────────────────────────────
        elif game.game_state == GameState.FACTION_SELECT:
            action = game.ui.faction_select_hit_test(mx, my)
            if action == "back":
                game.game_state = GameState.MAIN_MENU
            elif action in ("federation", "swarm", "rogue_ai"):
                game.selected_faction = action
            elif action == "start":
                game.ai_faction  = random.choice(["federation", "swarm", "rogue_ai"])
                game.game_mode   = game.pending_game_mode
                game._init_scene()

        # ── Unit info screen ──────────────────────────────────────────────────
        elif game.game_state == GameState.UNIT_INFO:
            if game.ui.unit_info_hit_test(mx, my):
                game.game_state = GameState.MAIN_MENU

        # ── Result screen ─────────────────────────────────────────────────────
        elif game.game_state in (GameState.VICTORY, GameState.DEFEAT):
            hit = game.ui.result_hit_test(mx, my)
            if hit == "restart":
                game._init_scene()
            elif hit == "home":
                game.game_state = GameState.MAIN_MENU

        # ── Playing: card / demolish / nuke activation ────────────────────────
        elif game.game_state == GameState.PLAYING:
            # Minimap click-to-pan (checked FIRST so it beats everything).
            # Returns (target_cam_x, target_cam_y) when inside the minimap rect.
            _mm_target = game.ui.handle_minimap_click(mx, my)
            if _mm_target is not None:
                target_cam_x, _target_cam_y = _mm_target
                game.camera.cam_x = max(
                    0.0, min(target_cam_x, float(WORLD_W - SCREEN_W))
                )
                game.camera.on_mouse_up()
                game._tap_was_minimap = True
                return   # consume the tap — don't fall through to card hit-test

            # ── Upgrade button click (supports branching) ────────────────
            sel_slot = getattr(game, 'selected_slot', None)
            if sel_slot is not None and game.build_state == BuildState.NONE:
                surf = pygame.display.get_surface()
                _h = surf.get_height() if surf else SCREEN_H
                if (_h - 70) <= my <= (_h - 30):
                    if 20 <= mx <= 150:   # left button — branch 0 (or only option)
                        UpgradeCommand(0, sel_slot, branch_idx=0).execute(game)
                        return
                    elif 160 <= mx <= 290:  # right button — branch 1
                        UpgradeCommand(0, sel_slot, branch_idx=1).execute(game)
                        return

            _active_kinds, _active_rects = game.ui.get_card_layout(
                getattr(game, "player_faction", "federation")
            )
            for i, rect in enumerate(_active_rects):
                if rect.collidepoint(mx, my):
                    kind = _active_kinds[i]
                    # Entering any build mode clears building selection
                    if hasattr(game, 'selected_slot'):
                        game.selected_slot = None
                    if kind is None:
                        # 安全開關 — demolish toggle
                        if game.build_state == BuildState.DEMOLISHING:
                            game.build_state = BuildState.NONE
                        else:
                            game.build_state = BuildState.DEMOLISHING
                            game.ghost_kind  = None
                    elif kind == "nuke":
                        if game.res.nuke_available:
                            game.build_state      = BuildState.NUKING
                            game.ghost_kind       = "nuke"
                            game.ghost_pos        = (mx, my)
                            game.ghost_slot       = None
                            game.ghost_valid      = True
                            self._nuke_just_armed = True   # suppress immediate detonation
                    else:
                        cost = BUILDING_SPECS[kind]["cost"]
                        if game.res.minerals >= cost:
                            game.build_state = BuildState.CONSTRUCTING
                            game.ghost_kind  = kind
                            game.ghost_pos   = (mx, my)
                            game.ghost_slot  = None
                            game.ghost_valid = False
                    break   # at most one card can be hit per tap

            # ── Slot selection (NONE build state, tap on world) ───────────────
            # Only activate when no card was tapped (checked here so card clicks
            # are consumed first by the loop above).
            if game.build_state == BuildState.NONE and not game._tap_was_minimap:
                # Convert screen → world coords for slot lookup
                wx = mx + game.camera.cam_x
                wy = my
                slot_idx, _ = game._find_nearest_slot(wx, wy)
                if slot_idx is not None and slot_idx in game._occupied_slots:
                    game.selected_slot = slot_idx
                else:
                    game.selected_slot = None

    # ── Event loop ────────────────────────────────────────────────────────────
    def process_events(self, game) -> bool:
        """
        Drain the pygame event queue and apply all inputs to *game*.

        Returns False when the application should quit; True otherwise.
        """
        SCREEN_W, SCREEN_H, WORLD_W, ALL_SLOTS, CARD_COSTS = _main_consts()

        for event in pygame.event.get():

            # ── Quit ──────────────────────────────────────────────────────────
            if event.type == pygame.QUIT:
                return False

            # ── Keyboard ──────────────────────────────────────────────────────
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # ESC on overlay screens → back to main menu
                    if game.game_state in (GameState.UNIT_INFO,
                                           GameState.FACTION_SELECT,
                                           GameState.SETTINGS):
                        game.game_state = GameState.MAIN_MENU
                    # ESC cancels build/demolish mode first; second press quits
                    elif game.build_state != BuildState.NONE:
                        game.build_state = BuildState.NONE
                        game.ghost_kind  = None
                        game.ghost_slot  = None
                    else:
                        return False
                elif event.key in (pygame.K_r, pygame.K_F5):
                    game._init_scene()
                elif event.key == pygame.K_d:
                    # D key → toggle DEMOLISHING mode
                    if game.build_state == BuildState.DEMOLISHING:
                        game.build_state = BuildState.NONE
                    else:
                        game.build_state = BuildState.DEMOLISHING
                        game.ghost_kind  = None
                elif event.key == pygame.K_F1:
                    game.debug_mode = not game.debug_mode
                elif (event.key == pygame.K_n
                        and game.game_state == GameState.PLAYING
                        and game.res.nuke_available):
                    game.build_state      = BuildState.NUKING
                    game.ghost_kind       = "nuke"
                    game.ghost_pos        = (SCREEN_W // 2, SCREEN_H // 2)
                    game.ghost_slot       = None
                    game.ghost_valid      = True
                    self._nuke_just_armed = True
                elif game.game_state == GameState.PLAYING:
                    _num_key_map = {
                        pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2,
                        pygame.K_4: 3, pygame.K_5: 4, pygame.K_6: 5,
                    }
                    _card_idx = _num_key_map.get(event.key)
                    if _card_idx is not None:
                        _kinds, _ = game.ui.get_card_layout(
                            getattr(game, "player_faction", "federation")
                        )
                        if _card_idx < len(_kinds):
                            _kind = _kinds[_card_idx]
                            if _kind is not None and _kind != "nuke":
                                _cost = CARD_COSTS.get(_kind, 0)
                                if game.res.minerals >= _cost:
                                    game.build_state = BuildState.CONSTRUCTING
                                    game.ghost_kind  = _kind
                                    game.ghost_pos   = (SCREEN_W // 2, SCREEN_H // 2)
                                    game.ghost_slot  = None
                                    game.ghost_valid = False

            # ── Pointer DOWN ──────────────────────────────────────────────────
            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                mx, my = self._evt_pos(event, game)
                btn    = 1 if event.type == pygame.FINGERDOWN else event.button
                if btn == 1:
                    self.lmb_down     = True
                    self.lmb_down_pos = (mx, my)

                    # ── Two-tap build: second click on slot finalises placement ──
                    if (game.build_state == BuildState.CONSTRUCTING
                            and game.game_state == GameState.PLAYING
                            and not getattr(game, "_tap_was_minimap", False)):
                        wx_dn, wy_dn = game.camera.screen_to_world(mx, my)
                        snap_idx, snap_ok = game._find_nearest_slot(wx_dn, wy_dn)
                        if snap_idx is not None and snap_ok:
                            cost = CARD_COSTS[game.ghost_kind]
                            if game.res.spend(cost):
                                game._place_building(snap_idx, game.ghost_kind, team=0)
                                print(
                                    f"[Build] placed {game.ghost_kind} "
                                    f"at slot {snap_idx}  "
                                    f"minerals={game.res.minerals}"
                                )
                        # Any second click (valid or not) exits CONSTRUCTING
                        game.build_state = BuildState.NONE
                        game.ghost_kind  = None
                        game.ghost_slot  = None
                        self.lmb_down = False
                        if event.type == pygame.FINGERDOWN:
                            self._touch_down_ui_handled = True
                        continue   # consume — don't fall through to do_tap_begin

                    _state_before = game.build_state
                    self.do_tap_begin(game, mx, my)

                    # Mark that touch DOWN was handled so FINGERUP knows it
                    # doesn't need to fire the fallback hit-test.
                    if event.type == pygame.FINGERDOWN:
                        self._touch_down_ui_handled = True

                    # Camera drag: only start if tap didn't activate a UI mode
                    # (and didn't land on the minimap — those clicks should
                    # pan instantly, not begin a drag).
                    if (game.build_state == BuildState.NONE
                            and _state_before == BuildState.NONE
                            and game.game_state == GameState.PLAYING
                            and not getattr(game, "_tap_was_minimap", False)):
                        game.camera.on_mouse_down(mx)

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    # RMB only (no touch equivalent): cancel build/demolish; or move debug unit
                    if game.build_state != BuildState.NONE:
                        game.build_state = BuildState.NONE
                        game.ghost_kind  = None
                        game.ghost_slot  = None
                    else:
                        wx, wy = game.camera.screen_to_world(mx, my)
                        if game.units:
                            u = game.units[0]
                            u.waypoints.clear()
                            u.move_to((wx, wy))

            # ── Pointer MOTION ────────────────────────────────────────────────
            elif event.type in (pygame.MOUSEMOTION, pygame.FINGERMOTION):
                mx, my = self._evt_pos(event, game)
                if game.game_state == GameState.MAIN_MENU:
                    pass   # no ghost or camera tracking on the title screen
                elif game.build_state == BuildState.CONSTRUCTING:
                    # Update ghost position and snap to nearest slot
                    game.ghost_pos = (mx, my)
                    wx, wy = game.camera.screen_to_world(mx, my)
                    game.ghost_slot, game.ghost_valid = game._find_nearest_slot(wx, wy)
                elif game.build_state == BuildState.NUKING:
                    # Free-aim cursor — no slot snapping needed
                    game.ghost_pos = (mx, my)
                elif game.build_state == BuildState.DEMOLISHING:
                    # Track hovered slot for refund preview
                    wx, wy = game.camera.screen_to_world(mx, my)
                    snap_idx, _ = game._find_nearest_slot(wx, wy)
                    game.ghost_slot = snap_idx
                    game.ghost_pos  = (mx, my)
                elif game.build_state == BuildState.NONE and self.lmb_down:
                    game.camera.on_mouse_move(mx)

            # ── Pointer UP ────────────────────────────────────────────────────
            elif event.type in (pygame.MOUSEBUTTONUP, pygame.FINGERUP):
                mx, my = self._evt_pos(event, game)
                btn    = 1 if event.type == pygame.FINGERUP else event.button
                if btn == 1:

                    # ── Minimap tap consumes DOWN *and* UP ────────────────────
                    # If DOWN landed on the minimap we've already panned the
                    # camera; swallow the matching UP so it can't finalise a
                    # placement / nuke / demolish at the minimap screen position.
                    if getattr(game, "_tap_was_minimap", False):
                        game._tap_was_minimap       = False
                        self.lmb_down               = False
                        self._touch_down_ui_handled = False
                        continue

                    # ── iOS WebKit fallback ───────────────────────────────────
                    # If FINGERDOWN was suppressed (common on iOS Safari),
                    # FINGERUP is the only event we receive for a tap.
                    # Run do_tap_begin() here so all UI interactions still work.
                    # MOUSEBUTTONUP never needs this — desktop always fires DOWN first.
                    if event.type == pygame.FINGERUP and not self._touch_down_ui_handled:
                        self.do_tap_begin(game, mx, my)

                        # If tap-begin entered CONSTRUCTING or NUKING, the next
                        # FINGERUP will finalise the placement / detonation.
                        # Do NOT run the UP-finalisation code this frame.
                        if game.build_state in (BuildState.CONSTRUCTING,
                                                BuildState.NUKING):
                            self.lmb_down               = False
                            self._touch_down_ui_handled = False
                            continue   # skip rest of UP logic for this event

                        # DEMOLISHING entered: fall through to UP logic — it
                        # will try to find a building at the tap position.

                    # Reset guard for the next tap cycle.
                    self._touch_down_ui_handled = False

                    if game.game_state == GameState.MAIN_MENU:
                        # Ignore mouse-up on title screen (hit-test handled in DOWN)
                        self.lmb_down = False

                    elif game.build_state == BuildState.CONSTRUCTING:
                        # 支援拖曳放置 (Drag-and-Drop) 與 雙擊點按 (Two-Tap)
                        dist = math.hypot(
                            mx - self.lmb_down_pos[0], my - self.lmb_down_pos[1]
                        )
                        if dist > 20:
                            # 距離大於 20px 視為拖曳。若放開時在有效欄位上，則直接建造
                            if game.ghost_valid and game.ghost_slot is not None:
                                BuildCommand(0, game.ghost_slot, game.ghost_kind).execute(game)
                                print(
                                    f"[Build-Drag] placed {game.ghost_kind} "
                                    f"at slot {game.ghost_slot}"
                                )
                            # 拖曳結束後，無論成功與否都退出建造模式
                            game.build_state = BuildState.NONE
                            game.ghost_kind  = None
                            game.ghost_slot  = None
                        else:
                            # 距離極短，視為單純「點擊卡牌」。保留游標，等待第二次點擊 (Two-Tap)
                            pass

                    elif game.build_state == BuildState.NUKING:
                        # If this UP is the same click that armed the nuke, skip it
                        if self._nuke_just_armed:
                            self._nuke_just_armed = False
                            self.lmb_down = False
                            continue
                        # Detonate nuke at world cursor position
                        wx, wy = game.camera.screen_to_world(mx, my)
                        NukeCommand(0, wx, wy).execute(game)
                        game.build_state = BuildState.NONE
                        game.ghost_kind  = None
                        game.ghost_slot  = None

                    elif game.build_state == BuildState.DEMOLISHING:
                        # Find slot building under cursor and demolish it
                        wx, wy = game.camera.screen_to_world(mx, my)
                        slot_idx, _ = game._find_nearest_slot(wx, wy)
                        if slot_idx is not None and slot_idx in game._occupied_slots:
                            DemolishCommand(0, slot_idx).execute(game)
                        # Stay in DEMOLISHING so player can keep clicking

                    else:
                        game.camera.on_mouse_up()

                    self.lmb_down = False

        return True
