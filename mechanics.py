import json
import pygame
from chess_logic import can_afford, can_afford_fakeout, pt, get_true_board
from draft_simulator import get_draft_state

class MechanicsManager:
    @staticmethod
    def _is_active_turn(gs, client_state):
        if client_state.get('predicting_mode'):
            return False
        if gs.get('game_over'):
            return False
        my_c = client_state.get('my_color')
        if not my_c:
            return False
        return gs.get('turn') == my_c

    @staticmethod
    def get_eval_state(gs, client_state):
        if client_state.get('drafting'):
            return get_draft_state(gs, client_state.get('draft_moves', []))
        return gs

    @staticmethod
    def can_toggle_hidden(gs, client_state, ignore_restrictions=False):
        if ignore_restrictions: return True
        if MechanicsManager.is_hidden_on(gs, client_state): return True
        if not MechanicsManager._is_active_turn(gs, client_state): return False
        state = MechanicsManager.get_eval_state(gs, client_state)
        if state.get('game_over') or state.get('normal_done', False): return False
        
        hs = state.get('hidden_seq') or {}
        S_prev = hs if isinstance(hs, int) else hs.get(state.get('turn', 'w'), 0)
        if S_prev + state.get('hidden_count', 0) >= 4:
            return False
            
        afford = can_afford(state)
        if not afford:
            if client_state.get('is_dragging_gesture'):
                client_state['flash_hidden_pts_continuous'] = True
            else:
                import time
                client_state['flash_hidden_pts_until'] = time.time() + 0.3
        return afford

    @staticmethod
    def is_hidden_on(gs, client_state):
        if client_state.get('drafting'):
            return client_state.get('draft_hidden', False)
        return gs.get('hidden_mode', False)

    @staticmethod
    def can_toggle_fakeout(gs, client_state, ignore_restrictions=False):
        if ignore_restrictions: return True
        if MechanicsManager.is_fakeout_on(gs, client_state): return True
        if not MechanicsManager._is_active_turn(gs, client_state): return False
        state = MechanicsManager.get_eval_state(gs, client_state)
        if state.get('game_over'): return False
        
        can_do = state.get('fakeout_mode_enabled', False) and not state.get('fakeout_used', False) and state.get('hidden_count', 0) == 1
        if not can_do: return False
        
        fs = state.get('fakeout_seq') or {}
        S_fake_prev = fs if isinstance(fs, int) else fs.get(state.get('turn', 'w'), 0)
        if S_fake_prev + state.get('fakeout_count', 0) >= 4:
            return False
            
        afford = can_afford_fakeout(state)
        if not afford:
            if client_state.get('is_dragging_gesture'):
                client_state['flash_fakeout_pts_continuous'] = True
            else:
                import time
                client_state['flash_fakeout_pts_until'] = time.time() + 0.3
        return afford

    @staticmethod
    def is_fakeout_on(gs, client_state):
        if client_state.get('drafting'):
            return client_state.get('draft_fakeout', False)
        return gs.get('fakeout_active', False)

    @staticmethod
    def get_mechanic_colors(gs, client_state):
        return (100, 100, 255), (255, 150, 50)

    @staticmethod
    def draw_modifier_glow(screen, tx, ty, SQ, is_h, is_f, multiplier=1.0):
        if not is_h and not is_f: return
        surf = pygame.Surface((int(SQ*3), int(SQ*3)), pygame.SRCALPHA)
        color = (255, 150, 50, int(100 * multiplier)) if is_f else (100, 100, 255, int(100 * multiplier))
        pygame.draw.circle(surf, color, (int(SQ*1.5), int(SQ*1.5)), int(SQ*0.8))
        screen.blit(surf, (tx - int(SQ*1.5) + int(SQ/2), ty - int(SQ*1.5) + int(SQ/2)), special_flags=pygame.BLEND_RGBA_ADD)

    @staticmethod
    def draw_modifier_text_glow(screen, fonts, glyph, pc_col, tx, ty, SQ, is_h, is_f, trail_alpha=255):
        if not is_h and not is_f: return
        try:
            font = fonts.get(int(SQ * 0.8))
            if not font and fonts:
                font = fonts[list(fonts.keys())[0]]
            if not font: return
            color = (255, 150, 50, trail_alpha) if is_f else (100, 100, 255, trail_alpha)
            surf = font.render(glyph, True, color)
            surf.set_alpha(trail_alpha)
            cx = tx + int(SQ / 2) - surf.get_width() // 2
            cy = ty + int(SQ / 2) - surf.get_height() // 2
            screen.blit(surf, (cx - 1, cy))
            screen.blit(surf, (cx + 1, cy))
            screen.blit(surf, (cx, cy - 1))
            screen.blit(surf, (cx, cy + 1))
        except Exception:
            pass

    @staticmethod
    def _execute_toggle_hidden_sync(gs, client_state, is_local, play_sound_fn, save_undo_fn, click_pos=None, force_shockwave=False):
        if not MechanicsManager.can_toggle_hidden(gs, client_state):
            if not MechanicsManager.is_hidden_on(gs, client_state):
                return False
        
        is_now_hidden = not MechanicsManager.is_hidden_on(gs, client_state)
        if MechanicsManager.is_hidden_on(gs, client_state):
            if play_sound_fn: play_sound_fn('hidden_off')
        else:
            if play_sound_fn: play_sound_fn('hidden')
            
        client_state['selected'] = None
        client_state['legal_sq'] = []
        if save_undo_fn:
            save_undo_fn(client_state, gs)
            
        if client_state.get('drafting'):
            client_state['draft_hidden'] = not client_state.get('draft_hidden', False)
            if client_state['draft_hidden']:
                client_state['draft_fakeout'] = False
        else:
            gs['hidden_mode'] = not gs.get('hidden_mode', False)
            if gs.get('hidden_mode'):
                gs['fakeout_active'] = False
                    
        if (is_now_hidden or force_shockwave) and click_pos:
            if 'shockwaves' not in client_state: client_state['shockwaves'] = []
            mx, my = click_pos
            sq_size = 50
            sq_center_x = (mx // sq_size) * sq_size + sq_size // 2
            sq_center_y = (my // sq_size) * sq_size + sq_size // 2
            client_state['shockwaves'].append({
                'cx': sq_center_x, 'cy': sq_center_y, 't': 0.0,
                'duration': 0.6, 'max_radius': 600, 'type': 'hidden'
            })
        return True

    @staticmethod
    async def execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound_fn, save_undo_fn, click_pos=None, force_shockwave=False):
        if MechanicsManager._execute_toggle_hidden_sync(gs, client_state, is_local, play_sound_fn, save_undo_fn, click_pos, force_shockwave):
            if not is_local and websocket:
                await websocket.send(json.dumps({"type": "action", "action": "toggle_hidden"}))

    @staticmethod
    def _execute_toggle_fakeout_sync(gs, client_state, is_local, play_sound_fn, save_undo_fn, click_pos=None, force_shockwave=False):
        if not MechanicsManager.can_toggle_fakeout(gs, client_state):
            if not MechanicsManager.is_fakeout_on(gs, client_state):
                return False
                
        is_now_fakeout = not MechanicsManager.is_fakeout_on(gs, client_state)
        if MechanicsManager.is_fakeout_on(gs, client_state):
            if play_sound_fn: play_sound_fn('fakeout_off')
        else:
            if play_sound_fn: play_sound_fn('fakeout')
            
        client_state['selected'] = None
        client_state['legal_sq'] = []
        if save_undo_fn:
            save_undo_fn(client_state, gs)
            
        if client_state.get('drafting'):
            client_state['draft_fakeout'] = not client_state.get('draft_fakeout', False)
            if client_state['draft_fakeout']:
                client_state['draft_hidden'] = False
        else:
            gs['fakeout_active'] = not gs.get('fakeout_active', False)
            if gs.get('fakeout_active'):
                gs['hidden_mode'] = False
                    
        if (is_now_fakeout or force_shockwave) and click_pos:
            if 'shockwaves' not in client_state: client_state['shockwaves'] = []
            mx, my = click_pos
            sq_size = 50
            sq_center_x = (mx // sq_size) * sq_size + sq_size // 2
            sq_center_y = (my // sq_size) * sq_size + sq_size // 2
            client_state['shockwaves'].append({
                'cx': sq_center_x, 'cy': sq_center_y, 't': 0.0,
                'duration': 0.6, 'max_radius': 600, 'type': 'fakeout'
            })
        return True

    @staticmethod
    async def execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound_fn, save_undo_fn, click_pos=None, force_shockwave=False):
        if MechanicsManager._execute_toggle_fakeout_sync(gs, client_state, is_local, play_sound_fn, save_undo_fn, click_pos, force_shockwave):
            if not is_local and websocket:
                await websocket.send(json.dumps({"type": "action", "action": "toggle_fakeout"}))
