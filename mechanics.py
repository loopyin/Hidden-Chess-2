import json
import pygame
from chess_logic import can_afford, can_afford_fakeout
from draft_simulator import get_draft_state

class MechanicsManager:
    """
    Centraliza e encapsula as lógicas, condições e execuções das mecânicas 
    especiais de jogo: Hidden e Fakeout.
    Isola a mecânica de eventos UI, facilitando a adoção de novas mecânicas 
    e atualizações sem introduzir bugs.
    """

    @staticmethod
    def _is_active_turn(gs, client_state):
        turn = gs['turn']
        my_color = client_state.get('my_color')
        total_plys = len(client_state.get('turn_history', []))
        active_idx = client_state.get('history_index', 0)
        history_active = total_plys > 0 and active_idx < total_plys - 1
        return (not history_active) and (turn == my_color)

    @staticmethod
    def get_eval_state(gs, client_state):
        if client_state.get('drafting'):
            return get_draft_state(gs, client_state.get('draft_moves', []))
        return gs

    @staticmethod
    def can_toggle_hidden(gs, client_state, ignore_restrictions=False):
        if ignore_restrictions:
            return True
        # If toggling off, allow it without restriction
        if MechanicsManager.is_hidden_on(gs, client_state):
            return True
        if not MechanicsManager._is_active_turn(gs, client_state):
            return False
        state = MechanicsManager.get_eval_state(gs, client_state)
        if state.get('game_over') or state.get('normal_done', False):
            return False
        return can_afford(state) and state.get('hidden_count', 0) == 0

    @staticmethod
    def is_hidden_on(gs, client_state):
        if client_state.get('drafting'):
            return client_state.get('draft_hidden', False)
        return gs.get('hidden_mode', False)

    @staticmethod
    def can_toggle_fakeout(gs, client_state, ignore_restrictions=False):
        if ignore_restrictions:
            return True
        # If toggling off, allow it without restriction
        if MechanicsManager.is_fakeout_on(gs, client_state):
            return True
        if not MechanicsManager._is_active_turn(gs, client_state):
            return False
        state = MechanicsManager.get_eval_state(gs, client_state)
        if state.get('game_over') or state.get('normal_done', False):
            return False
        return state.get('fakeout_mode_enabled', False) and can_afford_fakeout(state) and not state.get('fakeout_used', False)

    @staticmethod
    def is_fakeout_on(gs, client_state):
        if client_state.get('drafting'):
            return client_state.get('draft_fakeout', False)
        return gs.get('fakeout_active', False)

    @staticmethod
    def get_mechanic_colors():
        return {
            'hidden': (60, 110, 220),
            'fakeout': (245, 120, 20)
        }
    
    @staticmethod
    def draw_modifier_glow(screen, tx, ty, SQ, is_hidden, is_fakeout, multiplier=1.0):
        if not is_hidden and not is_fakeout:
            return
            
        colors = MechanicsManager.get_mechanic_colors()
        color = colors['hidden'] if is_hidden else colors['fakeout']
        alpha = int(45 * multiplier)
        
        glow = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
        glow.fill((*color, alpha))
        screen.blit(glow, (tx, ty), special_flags=pygame.BLEND_RGBA_ADD)

    @staticmethod
    def draw_modifier_text_glow(screen, fonts, glyph, pc_col, tx, ty, SQ, is_hidden, is_fakeout, trail_alpha=None):
        if not is_hidden and not is_fakeout:
            return
            
        colors = MechanicsManager.get_mechanic_colors()
        col = colors['hidden'] if is_hidden else colors['fakeout']
        
        ts_glow = fonts['piece'].render(glyph, True, col)
        
        if trail_alpha is not None:
            ts_glow.set_alpha(int(trail_alpha * 0.75))
        else:
            ts_glow.set_alpha(160)
            
        screen.blit(ts_glow, ts_glow.get_rect(center=(tx + SQ // 2, ty + SQ // 2)))

    @staticmethod
    def _execute_toggle_hidden_sync(gs, client_state, is_local, play_sound_fn, save_undo_fn, click_pos=None, force_shockwave=False):
        if not MechanicsManager.can_toggle_hidden(gs, client_state, ignore_restrictions=False):
            return False
            
        # Audio feedback
        is_now_hidden = not MechanicsManager.is_hidden_on(gs, client_state)
        if MechanicsManager.is_hidden_on(gs, client_state):
            play_sound_fn('hidden_off')
        else:
            play_sound_fn('hidden')
            
        client_state['selected'] = None
        client_state['legal_sq'] = []
        
        if save_undo_fn:
            save_undo_fn(client_state, gs)
        
        if client_state.get('drafting') or not is_local:
            if not client_state.get('drafting'):
                client_state['drafting'] = True
                if 'draft_moves' not in client_state or client_state['draft_moves'] is None:
                    client_state['draft_moves'] = []
            
            client_state['draft_hidden'] = not client_state.get('draft_hidden', False)
            if client_state['draft_hidden']:
                client_state['draft_fakeout'] = False
        else:
            if is_local:
                gs['hidden_mode'] = not gs.get('hidden_mode', False)
                if gs.get('hidden_mode'):
                    gs['fakeout_active'] = False
        
        # Trigger shockwave if activating hidden
        if (is_now_hidden or force_shockwave) and click_pos:
            if 'shockwaves' not in client_state:
                client_state['shockwaves'] = []
            
            # Snap to square center
            mx, my = click_pos
            sq_size = 50 
            sq_center_x = (mx // sq_size) * sq_size + sq_size // 2
            sq_center_y = (my // sq_size) * sq_size + sq_size // 2
            
            client_state['shockwaves'].append({
                'cx': sq_center_x,
                'cy': sq_center_y,
                't': 0.0,
                'duration': 0.6,
                'max_radius': 600,
                'type': 'hidden'
            })
        return True

    @staticmethod
    async def execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound_fn, save_undo_fn, click_pos=None, force_shockwave=False, skip_ws=False):
        if not MechanicsManager._execute_toggle_hidden_sync(gs, client_state, is_local, play_sound_fn, save_undo_fn, click_pos, force_shockwave):
            return

        if not skip_ws and not is_local and websocket:
            await websocket.send(json.dumps({"type": "action", "action": "toggle_hidden"}))

    @staticmethod
    def _execute_toggle_fakeout_sync(gs, client_state, is_local, play_sound_fn, save_undo_fn, click_pos=None, force_shockwave=False):
        if not MechanicsManager.can_toggle_fakeout(gs, client_state, ignore_restrictions=False):
            return False
            
        is_now_fakeout = not MechanicsManager.is_fakeout_on(gs, client_state)
        if MechanicsManager.is_fakeout_on(gs, client_state):
            play_sound_fn('fakeout_off')
        else:
            play_sound_fn('fakeout')
            
        client_state['selected'] = None
        client_state['legal_sq'] = []
        
        if save_undo_fn:
            save_undo_fn(client_state, gs)
        
        if client_state.get('drafting') or not is_local:
            if not client_state.get('drafting'):
                client_state['drafting'] = True
                if 'draft_moves' not in client_state or client_state['draft_moves'] is None:
                    client_state['draft_moves'] = []
            
            client_state['draft_fakeout'] = not client_state.get('draft_fakeout', False)
            if client_state['draft_fakeout']:
                client_state['draft_hidden'] = False
        else:
            if is_local:
                gs['fakeout_active'] = not gs.get('fakeout_active', False)
                if gs.get('fakeout_active'):
                    gs['hidden_mode'] = False
        
        # Trigger shockwave if activating fakeout
        if (is_now_fakeout or force_shockwave) and click_pos:
            if 'shockwaves' not in client_state:
                client_state['shockwaves'] = []
            
            # Snap to square center
            mx, my = click_pos
            sq_size = 50 
            sq_center_x = (mx // sq_size) * sq_size + sq_size // 2
            sq_center_y = (my // sq_size) * sq_size + sq_size // 2
            
            client_state['shockwaves'].append({
                'cx': sq_center_x,
                'cy': sq_center_y,
                't': 0.0,
                'duration': 0.6,
                'max_radius': 600,
                'type': 'fakeout'
            })
        return True

    @staticmethod
    async def execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound_fn, save_undo_fn, click_pos=None, force_shockwave=False, skip_ws=False):
        if not MechanicsManager._execute_toggle_fakeout_sync(gs, client_state, is_local, play_sound_fn, save_undo_fn, click_pos, force_shockwave):
            return

        if not skip_ws and not is_local and websocket:
            await websocket.send(json.dumps({"type": "action", "action": "toggle_fakeout"}))
