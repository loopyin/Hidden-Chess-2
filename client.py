import math, random, time
import pygame, sys, json, os, copy
import asyncio
import traceback
from collections import deque
from chess_logic import GLYPHS, pt, pc, get_absolute_board, get_true_board, in_check, hidden_cost, check_conflict, \
    legal, serialize_state, deserialize_state, make_state, can_afford, can_afford_fakeout, exec_move, end_turn, alg, deactivate_plies, get_ui_selection, \
    process_next_queues, get_next_turn_from_queue, pop_next_turn_from_queue, compare_turns, ice_king_interaction
from mechanics import MechanicsManager
from draft_simulator import get_draft_state
from renderer import BoardRenderer
from chess_logic import fakeout_cost

SESSION_FILE = "session_token.json"

def save_session(room_code, token):
    try:
        with open(SESSION_FILE, "w") as f:
            json.dump({'room_code': room_code, 'session_token': token}, f)
    except:
        pass

def load_session():
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r") as f:
                return json.load(f)
    except:
        pass
    return None

def clear_session():
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    except:
        pass

BOARD_PX = 560
PANEL_H = 215
SIDEBAR_W = 250
WIN_W = BOARD_PX + SIDEBAR_W
WIN_H = BOARD_PX + PANEL_H
SQ = BOARD_PX // 8
FPS = 60
PORTRAIT = False
LIGHT = (240, 217, 181)
DARK = (181, 136, 99)
C_SEL = (130, 151, 105)
C_CHECK = (210, 50, 50)
C_LAST = (205, 210, 106)
C_HIDDEN = (60, 110, 220)
C_FAKEOUT = (245, 120, 20)
BG = (22, 22, 24)
PANEL_BG = (30, 30, 34)
T_MAIN = (230, 215, 185)
T_DIM = (130, 120, 100)
T_BLUE = (90, 160, 255)
T_RED = (255, 90, 80)
BTN_N = (45, 48, 55)
BTN_H = (60, 65, 75)
BTN_BLUE = (38, 70, 180)
BTN_BLUEH = (55, 95, 215)
BTN_ORANGE = (220, 95, 25)
BTN_ORANGEH = (245, 120, 40)
BTN_TXT = (245, 245, 250)
BTN_END = (50, 95, 50)
BTN_ENDH = (70, 125, 70)

def draw_fancy_btn(screen, text, font, base_color, hover_color, text_color, rect, is_hover=False, is_disabled=False, border_color=None, custom_radius=8):
    c = hover_color if is_hover else base_color
    if is_disabled:
        c = (max(0, c[0]-30), max(0, c[1]-30), max(0, c[2]-30))
        text_color = (max(0, text_color[0]-80), max(0, text_color[1]-80), max(0, text_color[2]-80))
        
    # Drop shadow
    if not is_disabled:
        s_rect = rect.copy()
        s_rect.y += min(4, max(2, rect.h // 12))
        pygame.draw.rect(screen, (15, 15, 18), s_rect, border_radius=custom_radius)
        
    pygame.draw.rect(screen, c, rect, border_radius=custom_radius)
    
    if border_color:
        pygame.draw.rect(screen, border_color, rect, 2, border_radius=custom_radius)
        
    # Top edge highlight (inner bevel effect)
    if not is_disabled:
        hl_color = (min(255, c[0]+35), min(255, c[1]+35), min(255, c[2]+35))
        pygame.draw.line(screen, hl_color, (rect.x + custom_radius, rect.y + 1), (rect.right - custom_radius, rect.y + 1), 2)
        
    ts = font.render(text, True, text_color)
    screen.blit(ts, ts.get_rect(center=rect.center))

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def load_fonts():
    font_path = resource_path(os.path.join("assets", "DejaVuSans.ttf"))

    def get_font(size, bold=False):
        try:
            f = pygame.font.Font(font_path, size)
            if bold: f.set_bold(True)
            return f
        except:
            return pygame.font.SysFont('Arial', size, bold=bold)

    try:
        piece_font = pygame.font.Font(font_path, int(SQ * 0.76))
        promo_font = pygame.font.Font(font_path, int(SQ * 0.92))
    except:
        fallback_fonts = "segoeuisymbol, applecoloremoji, arial"
        piece_font = pygame.font.SysFont(fallback_fonts, int(SQ * 0.76))
        promo_font = pygame.font.SysFont(fallback_fonts, int(SQ * 0.92))

    return dict(
        piece=piece_font, promo=promo_font,
        coord=get_font(11, True), ui=get_font(13, True),
        small=get_font(12), big=get_font(15, True),
        pts=get_font(14, True), title=get_font(40, True)
    )


def registrar_proximo_lance_auto(gs, client_state):
    # O recurso Next automático deve ser exclusivo do disable undo
    if not client_state.get('disable_undo_placeholder') and not gs.get('disable_undo_placeholder'):
        return

    h_active = client_state.get('history_active', False)
    is_local = client_state.get('is_local', False)
    active_color = gs['turn'] if is_local else client_state.get('my_color')

    if not client_state.get('drafting'):
        temp_next_en = not h_active and gs['turn'] == active_color and (gs['normal_done'] or gs.get('hidden_count', 0) > 0)
    else:
        dm = client_state.get('draft_moves', [])
        if dm and dm[-1].get('type') != 'end_turn':
            temp_next_en = not h_active and gs['turn'] == active_color and (gs['normal_done'] or gs.get('hidden_count', 0) > 0)
        else:
            temp_next_en = False

    if client_state.get('draft_moves'):
        has_real_draft = check_has_real_draft(client_state['draft_moves'])
        if not has_real_draft:
            temp_next_en = False

    if not temp_next_en:
        return

    # Execute drafting logic
    if not client_state.get('disable_undo_placeholder') and not gs.get('disable_undo_placeholder'):
        play_sound('next')
    
    save_for_undo(client_state, gs)
    if client_state.get('drafting'):
        dm = client_state.get('draft_moves', [])
        if dm and dm[-1].get('type') != 'end_turn':
            dm.append({'type': 'end_turn'})
            client_state['draft_moves'] = dm
    client_state['drafting'] = True
    client_state['draft_hidden'] = False
    client_state['draft_fakeout'] = False
    if 'draft_moves' not in client_state or client_state['draft_moves'] is None:
        client_state['draft_moves'] = []

IMAGES = {}
SOUNDS = {}

def load_assets():
    images_dir = resource_path(os.path.join("assets", "images"))
    sounds_dir = resource_path(os.path.join("assets", "sounds"))
    
    if os.path.exists(images_dir):
        for bp in ['wP', 'wR', 'wN', 'wB', 'wQ', 'wK', 'bP', 'bR', 'bN', 'bB', 'bQ', 'bK']:
            img_path = os.path.join(images_dir, f"{bp}.png")
            if os.path.exists(img_path):
                try:
                    img = pygame.image.load(img_path).convert_alpha()
                    IMAGES[bp] = pygame.transform.smoothscale(img, (SQ, SQ))
                except:
                    pass
        
        board_path = os.path.join(images_dir, "board.png")
        if os.path.exists(board_path):
            try:
                img = pygame.image.load(board_path).convert()
                IMAGES['board'] = pygame.transform.smoothscale(img, (BOARD_PX, BOARD_PX))
            except:
                pass
                    
    try:
        pygame.mixer.init()
        if os.path.exists(sounds_dir):
            for sx in ['move', 'capture', 'check', 'game_over', 'hidden', 'hidden_off', 'fakeout', 'fakeout_off', 'click', 'select', 'toggle', 'start', 'undo', 'resign', 'next', 'end', 'next_move', 'spotted', 'fakeout_spotted', 'menu', 'freeze', 'unfreeze', 'error']:
                for ext in ['.wav', '.ogg', '.raw']:
                    snd_path = os.path.join(sounds_dir, f"{sx}{ext}")
                    if os.path.exists(snd_path):
                        try:
                            SOUNDS[sx] = pygame.mixer.Sound(snd_path)
                            break
                        except:
                            pass
    except:
        pass

def play_sound(snd_name):
    if snd_name in SOUNDS:
        try:
            SOUNDS[snd_name].play()
        except:
            pass


def draw_rect_aa(surf, color, rect, radius=5, border=0):
    pygame.draw.rect(surf, color, rect, border, border_radius=radius)


def spawn_particles(x, y, color, count, client_state, size=3, speed=150, life=0.3):
    if 'particles' not in client_state:
        client_state['particles'] = []
    for _ in range(count):
        angle = random.uniform(0, 6.28)
        vel = random.uniform(speed * 0.3, speed)
        client_state['particles'].append({
            'x': x,
            'y': y,
            'vx': math.cos(angle) * vel,
            'vy': math.sin(angle) * vel,
            'color': color,
            'life': life + random.uniform(-0.1, 0.1),
            'max_life': life + 0.1,
            'size': size * random.uniform(0.5, 1.5)
        })

def trigger_piece_anim(client_state, p, fr, fc, tr, tc, is_shadow=False, is_fakeout=False, is_capture=False):
    client_state['anim'] = {
        'p': p,
        'fr': fr, 'fc': fc,
        'tr': tr, 'tc': tc,
        't': 0.0,
        'dur': 0.25,
        'is_capture': is_capture,
        'is_hidden': is_shadow,
        'is_fakeout': is_fakeout
    }
    fr_d, fc_d = 7 - fr if client_state.get('flipped') else fr, 7 - fc if client_state.get('flipped') else fc
    start_x, start_y = fc_d * SQ + SQ // 2, fr_d * SQ + SQ // 2
    if is_shadow:
        spawn_particles(start_x, start_y, (60, 110, 220), 12, client_state, size=2.5, speed=90, life=0.3)
    elif is_fakeout:
        spawn_particles(start_x, start_y, (245, 120, 20), 12, client_state, size=2.5, speed=90, life=0.3)
    else:
        spawn_particles(start_x, start_y, (180, 170, 160), 8, client_state, size=2, speed=80, life=0.2)

def trigger_square_flash(client_state, r, c, color, rtype='hidden'):
    if 'flashes' not in client_state:
        client_state['flashes'] = {}
    client_state['flashes'][(r, c)] = {'t': 0.0, 'color': color}
    r_d, c_d = 7 - r if client_state.get('flipped') else r, 7 - c if client_state.get('flipped') else c
    px, py = c_d * SQ + SQ // 2, r_d * SQ + SQ // 2
    # Spawn particle effect
    spawn_particles(px, py, color, 16, client_state, size=3.5, speed=120, life=0.35)
    # Also play a highlight sound
    if rtype == 'hidden':
        play_sound('spotted')
    elif rtype == 'fakeout':
        play_sound('fakeout_spotted')
    elif rtype == 'gesture_invalid':
        play_sound('hidden_off')
    else:
        play_sound('move')

def trigger_freeze_effect(client_state, gs, r, c):
    """Triggers the freeze visual effect with specific particles and score indicator."""
    play_sound('freeze')
    
    val = 0
    p = gs['board'][r][c]
    if p:
        pt = p[1]
        val = {'P': 1, 'N': 3, 'B': 3, 'R': 5, 'Q': 9, 'K': 0}.get(pt, 0)
        
    if 'freeze_fx' not in client_state:
        client_state['freeze_fx'] = []
    
    client_state['freeze_fx'].append({
        'r': r, 'c': c,
        't': 0.0,
        'val': val,
        'particles': []
    })

def trigger_unfreeze_effect(client_state, gs, r, c):
    """Triggers the unfreeze visual effect."""
    play_sound('unfreeze')
    
    val = 0
    p = gs['board'][r][c]
    if p:
        pt = p[1]
        val = {'P': 1, 'N': 3, 'B': 3, 'R': 5, 'Q': 9, 'K': 0}.get(pt, 0)

    if 'unfreeze_fx' not in client_state:
        client_state['unfreeze_fx'] = []
    
    client_state['unfreeze_fx'].append({
        'r': r, 'c': c,
        't': 0.0,
        'val': val,
        'particles': []
    })


def get_cached_serialized_state(client_state, target_gs, player_color):
    cache = client_state.setdefault('_serialize_cache', {})
    sig = (
        id(target_gs),
        player_color,
        len(target_gs.get('log', [])),
        target_gs.get('turn'),
        target_gs.get('hidden_count'),
        target_gs.get('pts', {}).get('w') if isinstance(target_gs.get('pts'), dict) else None,
        target_gs.get('pts', {}).get('b') if isinstance(target_gs.get('pts'), dict) else None,
        target_gs.get('gold', {}).get('w') if isinstance(target_gs.get('gold'), dict) else None,
        target_gs.get('gold', {}).get('b') if isinstance(target_gs.get('gold'), dict) else None,
        len(target_gs.get('draft_queue', {}).get('w', []) if isinstance(target_gs.get('draft_queue'), dict) else []),
        len(target_gs.get('draft_queue', {}).get('b', []) if isinstance(target_gs.get('draft_queue'), dict) else []),
        target_gs.get('hidden_mode', False),
        target_gs.get('fakeout_active', False),
        target_gs.get('game_over', False),
        target_gs.get('game_over_msg', ''),
        client_state.get('resign_confirm', False),
        client_state.get('drafting', False),
        len(client_state.get('draft_moves', []) or []),
        client_state.get('draft_hidden', False),
        client_state.get('draft_fakeout', False),
        client_state.get('show_hidden', False),
        client_state.get('flipped', False),
        client_state.get('history_active', False),
        client_state.get('history_index', 0),
    )
    if sig in cache:
        return cache[sig]
    
    res = deserialize_state(serialize_state(target_gs, player_color=player_color))
    if len(cache) > 20:
        cache.clear()
    cache[sig] = res
    return res


def serialize_game_to_dict(gs, client_state):
    # Convert sets to lists so they are JSON serializable
    captured_w_list = [list(x) for x in gs.get('captured_w', [])]
    captured_b_list = [list(x) for x in gs.get('captured_b', [])]
    
    # Fully resolve hidden pieces
    hidden_w_clean = {}
    for pos, val in gs.get('hidden_w', {}).items():
        key_str = f"{pos[0]},{pos[1]}"
        hidden_w_clean[key_str] = {
            "pub_pos": list(val.pub_pos) if val.pub_pos else None,
            "piece": val.piece,
            "path": [list(x) for x in val.path] if val.path else [],
            "is_fakeout": val.is_fakeout,
            "fakeout_path": [list(x) for x in val.fakeout_path] if val.fakeout_path else [],
            "plies": val.plies
        }
        
    hidden_b_clean = {}
    for pos, val in gs.get('hidden_b', {}).items():
        key_str = f"{pos[0]},{pos[1]}"
        hidden_b_clean[key_str] = {
            "pub_pos": list(val.pub_pos) if val.pub_pos else None,
            "piece": val.piece,
            "path": [list(x) for x in val.path] if val.path else [],
            "is_fakeout": val.is_fakeout,
            "fakeout_path": [list(x) for x in val.fakeout_path] if val.fakeout_path else [],
            "plies": val.plies
        }

    shadow_history_clean = {}
    for ply, info in gs.get('shadow_history', {}).items():
        shadow_history_clean[str(ply)] = info

    export_data = {
        "room_code": client_state.get('room_code', 'LOCAL'),
        "player_color": client_state.get('my_color', 'w'),
        "game_over_msg": gs.get('game_over_msg', ''),
        "turn_count": gs.get('turn_count', 0),
        "points": gs.get('pts', {}),
        "log": gs.get('log', []),
        "shadow_history": shadow_history_clean,
        "board": gs.get('board', []),
        "captured_w_coords": captured_w_list,
        "captured_b_coords": captured_b_list,
        "hidden_pieces_white": hidden_w_clean,
        "hidden_pieces_black": hidden_b_clean,
        "timestamp": int(time.time()),
        "date_local": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "turn_history_serialized": [serialize_state(snapshot) for snapshot in client_state.get('turn_history', [])]
    }
    return export_data


def load_replay_files():
    replay_list = []
    for f in os.listdir('.'):
        if f.endswith('.json'):
            if f.startswith('partida_') or 'replay' in f:
                try:
                    with open(f, 'r', encoding='utf-8') as file:
                        data = json.load(file)
                        if "board" in data:
                            date_str = data.get('date_local', f.replace('partida_', '').replace('.json', ''))
                            turn_count = data.get('turn_count', 0)
                            player_color = data.get('player_color', 'w')
                            col_str = "Brancas" if player_color == 'w' else "Pretas"
                            replay_list.append({
                                'filename': f,
                                'date': date_str,
                                'turns': turn_count,
                                'color': col_str,
                                'data': data
                            })
                except Exception as e:
                    pass
    replay_list.sort(key=lambda x: x.get('data', {}).get('timestamp', 0), reverse=True)
    return replay_list


def get_cached_text(fonts, font_name, text, color, client_state):
    cache = client_state.setdefault('_text_cache', {})
    key = (font_name, text, color)
    if key in cache:
        return cache[key]
    if len(cache) > 300:
        cache.clear()
    surf = fonts[font_name].render(text, True, color)
    cache[key] = surf
    return surf


def get_entry_colors(e):
    # Default colors (muted dark)
    bg = (30, 31, 35)
    border = (48, 50, 58)
    txt_col = (200, 200, 205)
    
    color_type = e.get('color_type', 'system')
    if color_type == 'system':
        bg = (18, 42, 28)
        border = (30, 75, 48)
        txt_col = (110, 222, 142)
    elif color_type == 'hidden':
        bg = (10, 25, 50)
        border = (20, 50, 100)
        txt_col = (100, 181, 246) # Blue (Hidden)
    elif color_type == 'revealed':
        bg = (10, 25, 50)
        border = (20, 50, 100)
        txt_col = (100, 181, 246) # Blue (Hidden)
    elif color_type == 'fakeout':
        bg = (52, 34, 16)
        border = (95, 62, 24)
        txt_col = (255, 183, 77) # Orange (Fakeout)
    elif color_type == 'next_cancelled':
        bg = (48, 24, 24)
        border = (85, 42, 42)
        txt_col = (229, 115, 115) # Red (Desistir)
    elif color_type == 'next':
        bg = (48, 42, 18)
        border = (85, 75, 30)
        txt_col = (255, 213, 79) # #FFD54F
    elif color_type == 'white_move':
        bg = (32, 36, 44)
        border = (54, 62, 76)
        txt_col = (235, 230, 220)
    elif color_type == 'black_move':
        bg = (22, 25, 30)
        border = (38, 42, 50)
        txt_col = (175, 175, 180)
    return bg, border, txt_col


async def ask_promo(screen, fonts, player_col, websocket, client_state):
    opts = ['Q', 'R', 'B', 'N']
    bw, bh = 84, 84
    gap = 14
    tw = len(opts) * (bw + gap) - gap
    sx = (BOARD_PX - tw) // 2
    sy = (BOARD_PX - bh) // 2
    ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 170))
    screen.blit(ov, (0, 0))
    boxes = []
    for i, o in enumerate(opts):
        x = sx + i * (bw + gap)
        rect = pygame.Rect(x, sy, bw, bh)
        boxes.append((rect, o))
        draw_rect_aa(screen, (245, 238, 220), rect, 8)
        draw_rect_aa(screen, (120, 90, 60), rect, 8, 2)
        piece_key = player_col + o
        if piece_key in IMAGES:
            promo_img = pygame.transform.smoothscale(IMAGES[piece_key], (min(bw-20, SQ), min(bh-20, SQ)))
            screen.blit(promo_img, promo_img.get_rect(center=rect.center))
        else:
            g = fonts['promo'].render(GLYPHS[piece_key], True, (30, 30, 30))
            screen.blit(g, g.get_rect(center=rect.center))
    pygame.display.flip()

    while True:
        if websocket is not None:
            try:
                msg = await asyncio.wait_for(websocket.recv(), timeout=0.01)
                client_state['msg_queue'].append(msg)
            except asyncio.TimeoutError:
                pass

        for ev in pygame.event.get():
            if ev.type == pygame.MOUSEBUTTONDOWN:
                for rect, o in boxes:
                    if rect.collidepoint(ev.pos): return o

        await asyncio.sleep(0)


def check_has_real_draft(draft_moves):
    if not draft_moves:
        return False
    start_i = 0
    for i in range(len(draft_moves)-1, -1, -1):
        if draft_moves[i].get('type') == 'end_turn':
            start_i = i + 1
            break
    cur_dm = draft_moves[start_i:]
    return any((m.get('type') == 'move' and not m.get('fakeout', False)) for m in cur_dm)

def check_draft_endable(draft_moves, base_end_en):
    if not draft_moves:
        return base_end_en
    start_i = 0
    for i in range(len(draft_moves)-1, -1, -1):
        if draft_moves[i].get('type') == 'end_turn':
            start_i = i + 1
            break
    cur_dm = draft_moves[start_i:]
    if not cur_dm:
        has_any_real = any((m.get('type') == 'move' and not m.get('fakeout', False)) for m in draft_moves)
        return base_end_en or has_any_real
    return any((m.get('type') == 'move' and not m.get('fakeout', False)) for m in cur_dm)

def save_for_undo(client_state, gs):
    if client_state.get('is_test', False):
        if 'absolute_history' not in client_state:
            client_state['absolute_history'] = []
        client_state['absolute_history'].append({
            'gs': copy.deepcopy(gs),
            'turn_history': copy.deepcopy(client_state.get('turn_history', [])),
            'history_index': client_state.get('history_index', 0),
            'turn_start_snapshot': copy.deepcopy(client_state.get('turn_start_snapshot')),
            'draft_moves': copy.deepcopy(client_state.get('draft_moves', [])),
            'drafting': client_state.get('drafting', False),
            'draft_hidden': client_state.get('draft_hidden', False),
            'draft_fakeout': client_state.get('draft_fakeout', False)
        })

def test_mode_undo(client_state, gs):
    if client_state.get('is_test', False) and client_state.get('absolute_history'):
        popped = client_state['absolute_history'].pop()
        client_state['turn_history'] = popped['turn_history']
        client_state['history_index'] = popped['history_index']
        client_state['turn_start_snapshot'] = popped['turn_start_snapshot']
        client_state['draft_moves'] = popped['draft_moves']
        client_state['drafting'] = popped['drafting']
        client_state['draft_hidden'] = popped['draft_hidden']
        client_state['draft_fakeout'] = popped['draft_fakeout']
        return popped['gs']
    return gs

def draw_board(screen, gs, fonts, client_state, mouse):
    turn = gs['turn']
    board = gs['board']
    flipped = client_state['flipped']
    sel = client_state['selected']
    legal_set = set(map(tuple, client_state['legal_sq']))
    last = gs['last_move']
    show = client_state['show_hidden']
    
    my_color = client_state['my_color']
    my_hidden = gs['hidden_w'] if my_color == 'w' else gs['hidden_b']
    is_drafting = client_state.get('drafting', False)
    hmode = (client_state.get('draft_hidden', False) if is_drafting else gs['hidden_mode']) or client_state.get('hidden_triggered', False)
    fmode = client_state.get('draft_fakeout', False) if is_drafting else gs.get('fakeout_active', False)

    if client_state.get('history_active'):
        active_idx = client_state.get('history_index', 0)
        hist = client_state.get('turn_history', [])
        live_gs = hist[-1] if hist else gs
        
        # Apply the trail rendering on the block BEFORE the shadow move (active_idx + 1 logic)
        if (active_idx + 1) in live_gs.get('shadow_history', {}):
            show = True
            info = live_gs['shadow_history'][active_idx + 1]
            c_color = info.get('color', my_color)
            if (active_idx + 1) < len(hist):
                next_gs = hist[active_idx + 1]
                my_hidden = next_gs['hidden_w'] if c_color == 'w' else next_gs['hidden_b']

    abs_b = get_absolute_board(gs)
    tb = get_true_board(gs, my_color)
    render_grid = BoardRenderer.get_render_state(gs, client_state, abs_b, tb, my_hidden, show)

    mx, my = mouse
    hover_r, hover_c = -1, -1
    if my < BOARD_PX and mx < BOARD_PX:
        hover_c = mx // SQ
        hover_r = my // SQ
        if flipped:
            hover_r = 7 - hover_r
            hover_c = 7 - hover_c

    has_custom_board = 'board' in IMAGES
    if has_custom_board:
        board_img = IMAGES['board']
        if hmode or fmode:
            board_img = board_img.copy()
            tint = pygame.Surface((BOARD_PX, BOARD_PX), pygame.SRCALPHA)
            if hmode:
                tint.fill((0, 0, 50, 60))
            else:
                tint.fill((50, 0, 0, 60))
            board_img.blit(tint, (0,0))
        screen.blit(board_img, (0, 0))

    for rr in range(8):
        for cc in range(8):
            r = 7 - rr if flipped else rr
            c = 7 - cc if flipped else cc
            x, y = cc * SQ, rr * SQ

            cell = render_grid[r][c]

            base = LIGHT if (r + c) % 2 == 0 else DARK
            if hmode:
                base = (max(0, base[0] - 40), base[1], min(255, base[2] + 30))
            elif fmode:
                base = (min(255, base[0] + 30), max(0, base[1] - 30), max(0, base[2] - 60))

            if not has_custom_board:
                pygame.draw.rect(screen, base, (x, y, SQ, SQ))
                
            if cell.is_frozen:
                dark_surf = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                dark_surf.fill((0, 0, 0, 204)) # 80% darker
                screen.blit(dark_surf, (x, y))
            
            if cell.is_next_dest:
                pygame.draw.rect(screen, (239, 68, 68), (x, y, SQ, SQ), 3)
            if cell.next_chain_alpha > 0:
                red_surf = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                red_surf.fill((239, 68, 68, cell.next_chain_alpha))
                screen.blit(red_surf, (x, y))

            if hover_r == r and hover_c == c:
                if client_state.get('is_dragging_gesture'):
                    shadow_surf = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                    pygame.draw.circle(shadow_surf, (0, 0, 0, 115), (SQ // 2, SQ // 2), SQ // 2 - 2)
                    screen.blit(shadow_surf, (x, y))
                else:
                    hover_surf = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                    hover_surf.fill((255, 255, 255, 40) if (hmode or fmode) else (255, 255, 255, 60))
                    screen.blit(hover_surf, (x, y))

            if cell.is_last_move:
                hl = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                hl.fill((*C_LAST, 100))
                screen.blit(hl, (x, y))

            if cell.is_check:
                pygame.draw.rect(screen, C_CHECK, (x, y, SQ, SQ))

            if cell.is_selected:
                pygame.draw.rect(screen, C_SEL, (x, y, SQ, SQ))
                # Pulsa a borda do quadrado selecionado
                pulse = (math.sin(pygame.time.get_ticks() / 150.0) + 1.0) / 2.0
                pulse_thickness = 2 + int(pulse * 3)
                pygame.draw.rect(screen, (220, 240, 200), (x+1, y+1, SQ-2, SQ-2), pulse_thickness)

            if cell.is_legal and not cell.is_legal_capture:
                ds = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                pygame.draw.circle(ds, (0, 0, 0, 65), (SQ // 2, SQ // 2), SQ // 7)
                screen.blit(ds, (x, y))

            if cell.is_threatened or getattr(cell, 'is_legal_capture', False):
                t = pygame.time.get_ticks() / 500.0
                target_col = (240, 220, 60) if cell.is_threatened else (240, 60, 60)
                cx, cy = x + SQ // 2, y + SQ // 2
                
                # Corner brackets
                bracket_len = 16
                bracket_thick = 4
                margin = 4 + int(math.sin(t * math.pi) * 3) # Pulsing margin
                
                # Top-Left
                pygame.draw.line(screen, target_col, (x + margin, y + margin), (x + margin + bracket_len, y + margin), bracket_thick)
                pygame.draw.line(screen, target_col, (x + margin, y + margin), (x + margin, y + margin + bracket_len), bracket_thick)
                # Top-Right
                pygame.draw.line(screen, target_col, (x + SQ - margin - 1, y + margin), (x + SQ - margin - 1 - bracket_len, y + margin), bracket_thick)
                pygame.draw.line(screen, target_col, (x + SQ - margin - 1, y + margin), (x + SQ - margin - 1, y + margin + bracket_len), bracket_thick)
                # Bottom-Left
                pygame.draw.line(screen, target_col, (x + margin, y + SQ - margin - 1), (x + margin + bracket_len, y + SQ - margin - 1), bracket_thick)
                pygame.draw.line(screen, target_col, (x + margin, y + SQ - margin - 1), (x + margin, y + SQ - margin - 1 - bracket_len), bracket_thick)
                # Bottom-Right
                pygame.draw.line(screen, target_col, (x + SQ - margin - 1, y + SQ - margin - 1), (x + SQ - margin - 1 - bracket_len, y + SQ - margin - 1), bracket_thick)
                pygame.draw.line(screen, target_col, (x + SQ - margin - 1, y + SQ - margin - 1), (x + SQ - margin - 1, y + SQ - margin - 1 - bracket_len), bracket_thick)
                
                # Inner crosshair subtle element
                pygame.draw.circle(screen, target_col, (cx, cy), 4, 2)

            # Draw blue/orange ink trail on the path if show is True
            if show:
                if cell.blue_path_alpha > 0:
                    blue_surf = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                    blue_surf.fill((30, 110, 255, cell.blue_path_alpha))
                    screen.blit(blue_surf, (x, y))
                if cell.orange_path_alpha > 0:
                    orange_surf = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                    orange_surf.fill((245, 120, 20, cell.orange_path_alpha))
                    screen.blit(orange_surf, (x, y))

            p = cell.piece
            if client_state.get('is_dragging_gesture') and client_state.get('drag_piece_sq') == (r, c):
                p = None
            if p:
                if p in IMAGES:
                    img = IMAGES[p]
                    if cell.ghost_alpha < 255:
                        img = img.copy()
                        img.set_alpha(cell.ghost_alpha)
                    screen.blit(img, (x, y))
                else:
                    pc_col = (255, 255, 255) if pc(p) == 'w' else (25, 25, 25)
                    ps = fonts['piece'].render(GLYPHS[p], True, pc_col)
                    if cell.ghost_alpha < 255:
                        ps.set_alpha(cell.ghost_alpha)
                    screen.blit(ps, ps.get_rect(center=(x + SQ // 2, y + SQ // 2)))
                
                # --- ICE KING: Frozen piece indicator ---
                if cell.is_frozen:
                    from renderer import VisualEffectsRenderer
                    t_sec = pygame.time.get_ticks() / 1000.0
                    VisualEffectsRenderer.draw_freeze_overlay(screen, r, c, x, y, SQ, t_sec)
                # ----------------------------------------
                
                if cell.is_fake_residual and show:
                    pygame.draw.rect(screen, (245, 120, 20), (x, y, SQ, SQ), 3)

            hp = cell.ghost_piece
            if hp and show:
                animating_here = False
                if client_state.get('anim'):
                    a = client_state['anim']
                    if a['tr'] == r and a['tc'] == c and a['p'] == my_hidden[(r, c)].piece:
                        animating_here = True
                
                if not animating_here:
                    val = my_hidden[(r, c)]
                    is_f = val.is_fakeout
                    overlay_col = C_FAKEOUT if is_f else C_HIDDEN
                    ht = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                    ht.fill((*overlay_col, 75))
                    screen.blit(ht, (x, y))
                    lk = fonts['small'].render('*', True, overlay_col)
                    screen.blit(lk, (x + 3, y + 2))
                    if hp in IMAGES:
                        screen.blit(IMAGES[hp], (x, y))
                    else:
                        pc_col = (255, 255, 255) if pc(hp) == 'w' else (25, 25, 25)
                        ps = fonts['piece'].render(GLYPHS[hp], True, pc_col)
                        screen.blit(ps, ps.get_rect(center=(x + SQ // 2, y + SQ // 2)))

            if cell.is_next_dest and cell.next_dest_piece:
                next_p = cell.next_dest_piece
                next_pc_col = (255, 255, 255) if pc(next_p) == 'w' else (25, 25, 25)
                aura_surf = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                aura_text = fonts['piece'].render(GLYPHS[next_p], True, (239, 68, 68))
                for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
                    aura_surf.blit(aura_text, aura_text.get_rect(center=(SQ // 2 + dx, SQ // 2 + dy)))
                
                nps = fonts['piece'].render(GLYPHS[next_p], True, next_pc_col)
                aura_surf.blit(nps, nps.get_rect(center=(SQ // 2, SQ // 2)))
                aura_surf.set_alpha(150)
                screen.blit(aura_surf, (x, y))

            if 'flashes' in client_state and (r, c) in client_state['flashes']:
                val_flash = client_state['flashes'][(r, c)]
                if isinstance(val_flash, dict):
                    flash_time = val_flash['t']
                    flash_color = val_flash.get('color', (235, 45, 45))
                else:
                    flash_time = val_flash
                    flash_color = (235, 45, 45)
                blink_duration = 0.18
                current_blink = int(flash_time / blink_duration)
                if current_blink < 2:
                    t = flash_time % blink_duration
                    p = t / blink_duration
                    # Smooth glowing rising and fading beautifully
                    alpha = int(225 * math.sin(p * math.pi))
                    alpha = max(0, min(255, alpha))
                    if alpha > 0:
                        flash_surf = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                        flash_surf.fill((*flash_color, alpha))
                        screen.blit(flash_surf, (x, y))

            cc2 = DARK if (r + c) % 2 == 0 else LIGHT
            if hmode:
                cc2 = (max(0, cc2[0] - 40), cc2[1], min(255, cc2[2] + 30))
            elif fmode:
                cc2 = (min(255, cc2[0] + 30), max(0, cc2[1] - 30), max(0, cc2[2] - 60))
            if rr == 7:
                f = fonts['coord'].render('abcdefgh'[7 - cc if flipped else cc], True, cc2)
                screen.blit(f, (x + SQ - f.get_width() - 3, y + SQ - f.get_height() - 2))
            if cc == 0:
                rv = fonts['coord'].render(str(rr + 1 if flipped else 8 - rr), True, cc2)
                screen.blit(rv, (x + 3, y + 3))

    if show:
        for t_pos, val in my_hidden.items():
            is_f = val.is_fakeout
            hidden_path = val.path
            fakeout_path = val.fakeout_path

            # 1. Draw hidden pathway (always blue)
            if hidden_path and len(hidden_path) > 1:
                N = len(hidden_path)
                trail_surf = pygame.Surface((WIN_W, BOARD_PX), pygame.SRCALPHA)
                for i in range(N - 1):
                    p1 = hidden_path[i]
                    p2 = hidden_path[i + 1]
                    
                    fr_disp = 7 - p1[0] if flipped else p1[0]
                    fc_disp = 7 - p1[1] if flipped else p1[1]
                    tr_disp = 7 - p2[0] if flipped else p2[0]
                    tc_disp = 7 - p2[1] if flipped else p2[1]
                    
                    start_pos = (fc_disp * SQ + SQ // 2, fr_disp * SQ + SQ // 2)
                    end_pos = (tc_disp * SQ + SQ // 2, tr_disp * SQ + SQ // 2)
                    
                    ratio = (i + 1) / (N - 1)
                    line_alpha = int(45 + 135 * ratio)
                    color = (30, 110, 255, line_alpha)
                    
                    pygame.draw.line(trail_surf, color, start_pos, end_pos, 4)
                    pygame.draw.circle(trail_surf, color, start_pos, 5)
                    if i == N - 2:
                        pygame.draw.circle(trail_surf, color, end_pos, 5)
                        
                screen.blit(trail_surf, (0, 0))

            # 2. Draw fakeout pathway (always orange)
            if is_f:
                f_path = fakeout_path if fakeout_path else hidden_path
                if f_path and len(f_path) > 1:
                    N = len(f_path)
                    trail_surf = pygame.Surface((WIN_W, BOARD_PX), pygame.SRCALPHA)
                    for i in range(N - 1):
                        p1 = f_path[i]
                        p2 = f_path[i + 1]
                        
                        fr_disp = 7 - p1[0] if flipped else p1[0]
                        fc_disp = 7 - p1[1] if flipped else p1[1]
                        tr_disp = 7 - p2[0] if flipped else p2[0]
                        tc_disp = 7 - p2[1] if flipped else p2[1]
                        
                        start_pos = (fc_disp * SQ + SQ // 2, fr_disp * SQ + SQ // 2)
                        end_pos = (tc_disp * SQ + SQ // 2, tr_disp * SQ + SQ // 2)
                        
                        ratio = (i + 1) / (N - 1)
                        line_alpha = int(45 + 135 * ratio)
                        color = (245, 120, 20, line_alpha)
                        
                        pygame.draw.line(trail_surf, color, start_pos, end_pos, 4)
                        pygame.draw.circle(trail_surf, color, start_pos, 5)
                        if i == N - 2:
                            pygame.draw.circle(trail_surf, color, end_pos, 5)
                            
                    screen.blit(trail_surf, (0, 0))

    if last:
        fr, fc, tr, tc = last
        if flipped:
            fr, fc = 7 - fr, 7 - fc
            tr, tc = 7 - tr, 7 - tc

        start_pos = (fc * SQ + SQ // 2, fr * SQ + SQ // 2)
        end_pos = (tc * SQ + SQ // 2, tr * SQ + SQ // 2)

        arrow_surf = pygame.Surface((WIN_W, BOARD_PX), pygame.SRCALPHA)
        pygame.draw.line(arrow_surf, (*C_LAST, 140), start_pos, end_pos, 5)
        pygame.draw.circle(arrow_surf, (*C_LAST, 140), start_pos, 6)
        screen.blit(arrow_surf, (0, 0))

    if client_state.get('anim'):
        a = client_state['anim']
        fr, fc = 7 - a['fr'] if flipped else a['fr'], 7 - a['fc'] if flipped else a['fc']
        tr, tc = 7 - a['tr'] if flipped else a['tr'], 7 - a['tc'] if flipped else a['tc']
        
        start_x, start_y = fc * SQ, fr * SQ
        end_x, end_y = tc * SQ, tr * SQ
        
        progress = min(1.0, a['t'] / a['dur'])
        # Simple ease out curve
        ease = 1.0 - (1.0 - progress) ** 3
        
        cur_x = start_x + (end_x - start_x) * ease
        cur_y = start_y + (end_y - start_y) * ease
        
        p = a['p']
        pc_col = (255, 255, 255) if pc(p) == 'w' else (25, 25, 25)
        
        # Motion blur trail
        trail_steps = 5
        for step in range(1, trail_steps + 1):
            t_progress = max(0.0, progress - (step * 0.04))
            t_ease = 1.0 - (1.0 - t_progress) ** 3
            tx = start_x + (end_x - start_x) * t_ease
            ty = start_y + (end_y - start_y) * t_ease
            
            trail_alpha = int(140 * (1.0 - (step / trail_steps)))
            if p in IMAGES:
                trail_img = IMAGES[p].copy()
                trail_img.set_alpha(trail_alpha)
                screen.blit(trail_img, (tx, ty))
                if a.get('is_hidden') or a.get('is_fakeout'):
                    is_h, is_f = a.get('is_hidden'), a.get('is_fakeout')
                    MechanicsManager.draw_modifier_glow(screen, tx, ty, SQ, is_h, is_f, multiplier=trail_alpha * 0.55 / 45)
            else:
                ts = fonts['piece'].render(GLYPHS[p], True, pc_col)
                ts.set_alpha(trail_alpha)
                screen.blit(ts, ts.get_rect(center=(tx + SQ // 2, ty + SQ // 2)))
                if a.get('is_hidden') or a.get('is_fakeout'):
                    is_h, is_f = a.get('is_hidden'), a.get('is_fakeout')
                    MechanicsManager.draw_modifier_text_glow(screen, fonts, GLYPHS[p], pc_col, tx, ty, SQ, is_h, is_f, trail_alpha=trail_alpha)

        if p in IMAGES:
            screen.blit(IMAGES[p], (cur_x, cur_y))
            if a.get('is_hidden') or a.get('is_fakeout'):
                is_h, is_f = a.get('is_hidden'), a.get('is_fakeout')
                MechanicsManager.draw_modifier_glow(screen, cur_x, cur_y, SQ, is_h, is_f)
        else:
            ps = fonts['piece'].render(GLYPHS[p], True, pc_col)
            screen.blit(ps, ps.get_rect(center=(cur_x + SQ // 2, cur_y + SQ // 2)))
            if a.get('is_hidden') or a.get('is_fakeout'):
                is_h, is_f = a.get('is_hidden'), a.get('is_fakeout')
                MechanicsManager.draw_modifier_text_glow(screen, fonts, GLYPHS[p], pc_col, cur_x, cur_y, SQ, is_h, is_f)

    if client_state.get('particles'):
        for p in client_state['particles']:
            alpha = int(255 * (p['life'] / p['max_life']))
            size = max(1, int(p['size'] * (p['life'] / p['max_life'])))
            psurf = pygame.Surface((size*2, size*2), pygame.SRCALPHA)
            pygame.draw.circle(psurf, (*p['color'], alpha), (size, size), size)
            screen.blit(psurf, (int(p['x'] - size), int(p['y'] - size)))

    if client_state.get('is_dragging_gesture') and 'drag_pos' in client_state:
        mx, my = client_state['drag_pos']
        p = client_state.get('drag_piece_name')
        if p:
            is_hid = client_state.get('hidden_triggered', False)
            is_fake = client_state.get('fakeout_triggered', False)
            
            if is_fake or is_hid:
                radius = (SQ // 2) + int(5 * math.sin(pygame.time.get_ticks() / 100.0))
                glow_surf = pygame.Surface((SQ + 60, SQ + 60), pygame.SRCALPHA)
                
                if is_fake:
                    # Fakeout intense orange aura
                    pygame.draw.circle(glow_surf, (255, 120, 20, 120), (SQ // 2 + 30, SQ // 2 + 30), radius + 18)
                    pygame.draw.circle(glow_surf, (255, 140, 30, 200), (SQ // 2 + 30, SQ // 2 + 30), radius + 5)
                    pygame.draw.circle(glow_surf, (255, 170, 50, 255), (SQ // 2 + 30, SQ // 2 + 30), radius - 4)
                elif is_hid:
                    # More intense blue aura
                    pygame.draw.circle(glow_surf, (20, 80, 255, 120), (SQ // 2 + 30, SQ // 2 + 30), radius + 18)
                    pygame.draw.circle(glow_surf, (40, 110, 255, 200), (SQ // 2 + 30, SQ // 2 + 30), radius + 5)
                    pygame.draw.circle(glow_surf, (80, 150, 255, 255), (SQ // 2 + 30, SQ // 2 + 30), radius - 4)
                
                screen.blit(glow_surf, (mx - SQ // 2 - 30, my - SQ // 2 - 30))

            if p in IMAGES:
                img = IMAGES[p]
                rect = img.get_rect(center=(mx, my))
                screen.blit(img, rect)
            else:
                pc_col = (255, 255, 255) if pc(p) == 'w' else (25, 25, 25)
                ps = fonts['piece'].render(GLYPHS.get(p, p), True, pc_col)
                screen.blit(ps, ps.get_rect(center=(mx, my)))
                
            if not is_fake:
                hold_p = min(1.0, client_state.get('gesture_timer', 0.0) / 6.0)
                if hold_p > 0.01:
                    bar_w = 40
                    bar_h = 5
                    bar_x = mx - bar_w // 2
                    bar_y = my - SQ // 2 - 10
                    pygame.draw.rect(screen, (30, 30, 30), (bar_x, bar_y, bar_w, bar_h), border_radius=2)
                    pygame.draw.rect(screen, (255, 255, 255), (bar_x, bar_y, int(bar_w * hold_p), bar_h), border_radius=2)

    if client_state.get('shockwaves'):
        sw_surf = pygame.Surface((BOARD_PX, BOARD_PX), pygame.SRCALPHA)
        for sw in client_state['shockwaves']:
            progress = sw['t'] / sw['duration']
            # Explosive easing function
            e_progress = 1.0 - (1.0 - progress)**4
            radius = int(5 + (sw['max_radius'] - 5) * e_progress)
            
            # Vibrant fade-out alpha curve
            alpha = int(245 * (1.0 - progress)**1.5)
            if alpha < 0: alpha = 0
            
            # Color logic
            type = sw.get('type')
            is_hidden_sw = type == 'hidden'
            is_fakeout_sw = type == 'fakeout'
            
            if is_hidden_sw:
                c1, c2, c3, c4, c5 = (30, 100, 235), (40, 110, 255), (210, 230, 255), (15, 75, 185), (80, 150, 255)
            elif is_fakeout_sw:
                c1, c2, c3, c4, c5 = (235, 100, 30), (255, 110, 40), (255, 230, 210), (185, 75, 15), (255, 150, 80)
            else:
                c1, c2, c3, c4, c5 = (30, 235, 100), (40, 255, 110), (210, 255, 230), (15, 185, 75), (80, 255, 150)
            
            # 1. Base vibrant ambient glow
            pygame.draw.circle(sw_surf, (*c1[:3], int(0.22 * alpha)), (sw['cx'], sw['cy']), radius)
            
            # 2. Main neon shock ring
            ring_w = max(2, int(22 * (1.0 - progress)))
            if radius > ring_w:
                pygame.draw.circle(sw_surf, (*c2[:3], alpha), (sw['cx'], sw['cy']), radius, ring_w)
            else:
                pygame.draw.circle(sw_surf, (*c2[:3], alpha), (sw['cx'], sw['cy']), radius)
                
            # 3. Secondary hot white-leading-edge ring
            lead_progress = min(1.0, progress * 1.06)
            e_lead = 1.0 - (1.0 - lead_progress)**4
            lead_radius = int(5 + (sw['max_radius'] - 5) * e_lead)
            lead_alpha = int(alpha * 0.7)
            lead_ring_w = max(1, int(5 * (1.0 - lead_progress)))
            if lead_radius > lead_ring_w:
                pygame.draw.circle(sw_surf, (*c3[:3], lead_alpha), (sw['cx'], sw['cy']), lead_radius, lead_ring_w)
                
            # 4. Third trailing deep energetic wave
            trail_progress = max(0.0, progress - 0.12) / 0.88
            e_trail = 1.0 - (1.0 - trail_progress)**2
            trail_radius = int(5 + (sw['max_radius'] - 5) * e_trail)
            trail_alpha = int(alpha * 0.45)
            trail_ring_w = max(1, int(26 * (1.0 - trail_progress)))
            if trail_radius > trail_ring_w:
                pygame.draw.circle(sw_surf, (*c4[:3], trail_alpha), (sw['cx'], sw['cy']), trail_radius, trail_ring_w)

            # 5. Radiating high-speed energy spikes
            num_spikes = 16
            for i in range(num_spikes):
                angle = (i * 2.0 * math.pi) / num_spikes
                cos_a = math.cos(angle)
                sin_a = math.sin(angle)
                
                sp_start = int(radius * 0.78)
                sp_end = int(radius * 1.04)
                
                x1 = int(sw['cx'] + cos_a * sp_start)
                y1 = int(sw['cy'] + sin_a * sp_start)
                x2 = int(sw['cx'] + cos_a * sp_end)
                y2 = int(sw['cy'] + sin_a * sp_end)
                
                spike_alpha = int(alpha * 0.6)
                spike_w = max(1, int(3 * (1.0 - progress)))
                pygame.draw.line(sw_surf, (*c5[:3], spike_alpha), (x1, y1), (x2, y2), spike_w)
                
        screen.blit(sw_surf, (0, 0))

    from renderer import VisualEffectsRenderer
    VisualEffectsRenderer.draw_active_freeze_effects(screen, client_state, SQ, BOARD_PX)

def draw_panel(screen, gs, fonts, mouse, client_state):
    pygame.draw.rect(screen, PANEL_BG, (0, BOARD_PX, BOARD_PX, PANEL_H))
    pygame.draw.line(screen, (40, 40, 45), (0, BOARD_PX), (BOARD_PX, BOARD_PX), 2)

    turn = gs['turn']
    my_color = client_state['my_color']
    hmode = MechanicsManager.is_hidden_on(gs, client_state)
    fmode = MechanicsManager.is_fakeout_on(gs, client_state)

    turn_hist = client_state.get('turn_history', [])
    total_plys = len(turn_hist)
    active_idx = client_state.get('history_index', 0)
    history_active = total_plys > 0 and active_idx < total_plys - 1

    if history_active:
        status = f"HISTÓRICO: Lance {active_idx} de {total_plys - 1}"
        sc = (160, 160, 160)
    elif client_state['waiting']:
        status = "Aguardando Oponente..."
        sc = T_RED
    elif gs['game_over']:
        if client_state.get('export_success_msg'):
            status = client_state['export_success_msg']
            sc = (110, 220, 110)
        else:
            status = gs['game_over_msg']
            sc = T_RED
    elif turn != my_color:
        status = "Turno do Oponente"
        sc = T_DIM
    elif hmode:
        cost = hidden_cost(gs)
        avail = gs['pts'][turn]
        seq_val = gs.get('hidden_seq', {'w': 0, 'b': 0})
        seq = seq_val.get(turn, 0) if isinstance(seq_val, dict) else seq_val
        if seq > 0:
            status = f'Modo oculto | custo: {cost}pt | possui: {avail}pt (Seq: {seq})'
        else:
            status = f'Modo oculto | custo: {cost}pt | possui: {avail}pt'
        sc = (150, 200, 255)
    elif fmode:
        cost = fakeout_cost(gs)
        avail = gs['pts'][turn]
        status = f'Modo fakeout | custo: {cost}pt | possui: {avail}pt'
        sc = (245, 120, 20)
    elif gs['normal_done']:
        status = 'Seu Turno — aguardando encerramento'
        sc = T_MAIN
    else:
        status = 'Seu Turno — movimento normal ou aperte H'
        sc = T_MAIN

    st = fonts['big'].render(status, True, sc)
    st_rect = st.get_rect(midleft=(15, BOARD_PX + 28))
    pill_rect = st_rect.inflate(24, 12)

    draw_rect_aa(screen, (20, 20, 24), pill_rect, 12)
    if hmode:
        draw_rect_aa(screen, (80, 120, 220), pill_rect, 12, 1)
    elif fmode:
        draw_rect_aa(screen, (245, 120, 20), pill_rect, 12, 1)
    elif turn == my_color and not client_state['waiting'] and not history_active:
        draw_rect_aa(screen, (80, 80, 90), pill_rect, 12, 1)
    screen.blit(st, st_rect)

    wb_rect = pygame.Rect(BOARD_PX - 185, BOARD_PX + 25, 80, 36)
    bb_rect = pygame.Rect(BOARD_PX - 95, BOARD_PX + 25, 80, 36)

    draw_rect_aa(screen, (240, 240, 235), wb_rect, 6)
    draw_rect_aa(screen, (30, 30, 34), bb_rect, 6)
    draw_rect_aa(screen, (70, 70, 75), bb_rect, 6, 1)

    w_col = (30, 30, 30) if gs['turn'] == 'w' else (120, 120, 120)
    b_col = (230, 230, 230) if gs['turn'] == 'b' else (120, 120, 120)

    is_drafting = client_state.get('drafting', False)
    if is_drafting or client_state.get('draft_moves'):
        pts_state = get_draft_state(gs, client_state.get('draft_moves', []))
    else:
        pts_state = gs

    wlbl = fonts['pts'].render(f"B: {pts_state['pts']['w']} pt", True, w_col)
    blbl = fonts['pts'].render(f"P: {pts_state['pts']['b']} pt", True, b_col)
    screen.blit(wlbl, wlbl.get_rect(center=wb_rect.center))
    screen.blit(blbl, blbl.get_rect(center=bb_rect.center))

    if client_state.get('draft_moves'):
        has_real_draft = check_has_real_draft(client_state['draft_moves'])
        log = gs['log'][-3:]
    else:
        log = gs['log'][-3:]
    log_rect = pygame.Rect(12, BOARD_PX + 42, BOARD_PX - 210, 50)
    draw_rect_aa(screen, (15, 15, 18), log_rect, 6)

    lx, ly = 20, BOARD_PX + 46
    
    raw_log = gs.get('log', [])
    clog = gs.get('classified_log', [])
    start_idx = max(0, len(raw_log) - 3)
    display_entries = []
    
    for i in range(start_idx, len(raw_log)):
        entry_raw = raw_log[i]
        c_entry = clog[i] if i < len(clog) else None
        
        text = str(entry_raw)
        ct = 'system'
        
        if c_entry:
            text = c_entry['text']
            ct = c_entry.get('color_type', 'system')
        else:
            parts = text.split('|')
            if len(parts) >= 2:
                cmd = parts[0]
                if cmd == 'HIDDEN':
                    text = f"{parts[2]} (-{parts[3]}pt)" if len(parts) > 3 else parts[2]
                    ct = 'hidden'
                elif cmd == 'FAKEOUT':
                    text = parts[2]
                    ct = 'fakeout'
                elif cmd == 'NEXT':
                    text = parts[2]
                    ct = 'next'
                elif cmd == 'NORMAL':
                    text = parts[2]
                elif cmd == 'SYS_HIDDEN':
                    text = parts[1]
                    ct = 'hidden'
                elif cmd == 'SYS_FAKEOUT':
                    text = parts[1]
                    ct = 'fakeout'
                elif cmd == 'ICE':
                    text = parts[2]
                    ct = 'system'
        display_entries.append((text, ct))

    for i, (text, ct) in enumerate(display_entries):
        a = 255 - (len(display_entries) - 1 - i) * 60
        cl = (a, a, a) # System lines fade into gray
        if ct in ('next_cancelled', ) or "Lance inválido" in text or "Sequência quebrada" in text:
            cl = (229, 115, 115) # Red (#E57373)
            ls = fonts['small'].render(text, True, cl)
            screen.blit(ls, (lx, ly + i * 14))
        elif ct in ('hidden', 'revealed'):
            cl = (100, 181, 246) # Blue (#64B5F6)
            ls = fonts['small'].render(text, True, cl)
            screen.blit(ls, (lx, ly + i * 14))
        elif ct == 'fakeout':
            cl = (255, 183, 77) # Orange (#FFB74D)
            ls = fonts['small'].render(text, True, cl)
            screen.blit(ls, (lx, ly + i * 14))
        elif ct == 'next':
            cl = (255, 213, 79) # Yellow (#FFD54F)
            ls = fonts['small'].render(text, True, cl)
            screen.blit(ls, (lx, ly + i * 14))
        else:
            ls = fonts['small'].render(text, True, cl)
            screen.blit(ls, (lx, ly + i * 14))

    by2 = BOARD_PX + 112
    bh = 32
    btns = {}

    def draw_btn(x, w, key, text, is_enabled, is_active, base_color, hover_color, y_override=None):
        y_pos = y_override if y_override is not None else by2
        rect = pygame.Rect(x, y_pos, w, bh)
        is_hover = rect.collidepoint(mouse) and is_enabled
        
        # Slight press down effect
        if is_hover or is_active:
            rect.y += 1
            
        b_color = None
        if is_active:
            b_color = (245, 120, 20) if key == 'fakeout' else (80, 120, 220)
            
        draw_fancy_btn(screen, text, fonts['ui'], base_color, hover_color, BTN_TXT, rect, is_hover=is_hover, is_disabled=not is_enabled, border_color=b_color, custom_radius=6)
        btns[key] = rect

    if client_state.get('is_replay'):
        draw_btn(12, 180, 'exit_replay', 'Voltar ao Menu', True, False, (140, 50, 50), (180, 70, 70))
        draw_btn(200, 60, 'flip', 'Girar', True, False, BTN_N, BTN_H)
    elif gs['game_over']:
        draw_btn(12, 120, 'menu', 'Voltar ao Menu', True, False, BTN_N, BTN_H)
        draw_btn(BOARD_PX - 185, 170, 'export_json', 'Salvar Replay', True, False, BTN_BLUE, BTN_BLUEH, y_override=BOARD_PX + 75)

        req_by = gs.get('rematch_requested_by')
        declined = gs.get('rematch_declined')
        opp_left = gs.get('opponent_left')

        if opp_left:
            rem_st = fonts['ui'].render("O oponente saiu da sala.", True, T_RED)
            screen.blit(rem_st, (150, by2 + 6))
        elif declined:
            rem_st = fonts['ui'].render("O oponente recusou a revanche.", True, T_RED)
            screen.blit(rem_st, (150, by2 + 6))
        elif req_by == my_color:
            rem_st = fonts['ui'].render("Aguardando oponente...", True, T_DIM)
            screen.blit(rem_st, (150, by2 + 6))
        elif req_by and req_by != my_color:
            draw_btn(150, 120, 'accept', 'Aceitar Revanche', True, False, BTN_END, BTN_ENDH)
            draw_btn(280, 90, 'decline', 'Recusar', True, False, (140, 50, 50), (180, 70, 70))
        else:
            draw_btn(150, 130, 'rematch', 'Pedir Revanche', True, False, BTN_BLUE, BTN_BLUEH)

    else:
        draw_btn(8, 60, 'flip', 'Girar', True, False, BTN_N, BTN_H)

        # Check if hidden and fakeout can be enabled
        is_drafting = client_state.get('drafting', False)
        if is_drafting:
            dgs = get_draft_state(gs, client_state.get('draft_moves', []))
            henabled = not history_active and turn == my_color and not dgs.get('normal_done') and can_afford(dgs) and dgs['hidden_count'] == 0
            fake_enabled = not history_active and turn == my_color and not dgs['game_over'] and dgs.get('fakeout_mode_enabled', False) and can_afford_fakeout(dgs) and not dgs['normal_done'] and not dgs.get('fakeout_used', False)
        else:
            henabled = not history_active and turn == my_color and not gs['normal_done'] and can_afford(gs) and gs['hidden_count'] == 0
            fake_enabled = not history_active and turn == my_color and not gs['game_over'] and gs.get('fakeout_mode_enabled', False) and can_afford_fakeout(gs) and not gs['normal_done'] and not gs.get('fakeout_used', False)

        draw_btn(74, 66, 'hidden', 'Ocultar', henabled, hmode, BTN_BLUE, BTN_BLUEH)

        fake_active = client_state.get('draft_fakeout', False) if is_drafting else gs.get('fakeout_active', False)
        if fake_enabled:
            f_col, f_hov = BTN_ORANGE, BTN_ORANGEH
        else:
            f_col, f_hov = BTN_N, BTN_H
        draw_btn(146, 68, 'fakeout', 'Fakeout', fake_enabled, fake_active, f_col, f_hov)

        show_active = client_state.get('show_hidden', False)
        stxt_s = 'Esconder' if show_active else 'Sombra'
        draw_btn(220, 64, 'show', stxt_s, True, show_active, BTN_N, BTN_H)

        undo_bloqueado = gs.get('disable_undo_placeholder', False)
        if client_state.get('is_test', False):
            undo_en = len(client_state.get('absolute_history', [])) > 0
        else:
            undo_en = not history_active and turn == my_color and (gs['normal_done'] or gs['hidden_count'] > 0 or len(client_state.get('draft_moves', [])) > 0 or client_state.get('drafting', False))
            
        if undo_bloqueado:
            undo_en = False
            
        draw_btn(290, 68, 'undo', 'Desfazer', undo_en, False, (120, 90, 40), (150, 110, 50))
    
        is_confirm = client_state.get('resign_confirm', False)
        r_txt = "Confirma?" if is_confirm else "Desistir"
        r_col = (180, 40, 40) if is_confirm else (140, 50, 50)
        r_hov = (220, 60, 60) if is_confirm else (180, 70, 70)
        draw_btn(364, 68, 'resign', r_txt, not history_active, is_confirm, r_col, r_hov)

        base_next = not history_active and turn == my_color and (gs['normal_done'] or gs['hidden_count'] > 0)
        
        if not is_drafting:
            next_en = base_next
        else:
            dm = client_state.get('draft_moves', [])
            if dm and dm[-1].get('type') != 'end_turn':
                next_en = base_next
            else:
                next_en = False

        if client_state.get('draft_moves'):
            has_real_draft = check_has_real_draft(client_state['draft_moves'])
            if not has_real_draft:
                next_en = False
        draw_btn(438, 44, 'next', 'Next', next_en, False, (210, 163, 44), (234, 180, 10))

        end_en = not history_active and turn == my_color and (gs['normal_done'] or gs['hidden_count'] > 0 or gs.get(f'next_queue_{turn}'))
        if client_state.get('draft_moves'):
            end_en = check_draft_endable(client_state['draft_moves'], end_en)
        draw_btn(488, 64, 'end', 'Encerrar', end_en, False, BTN_END, BTN_ENDH)

    # Replay button and log buttons removed during mid-game.

    # ------------------ Fila de Plys (Queue of Plys) ------------------
    ply_y = BOARD_PX + 160
    ply_h = 42

    container_rect = pygame.Rect(12, ply_y, BOARD_PX - 24, ply_h)
    draw_rect_aa(screen, (15, 15, 18), container_rect, 6)
    draw_rect_aa(screen, (40, 40, 45), container_rect, 6, 1)

    # Left arrow button
    left_btn_rect = pygame.Rect(12, ply_y, 35, ply_h)
    left_enabled = active_idx > 0 and total_plys > 0
    left_hover = left_btn_rect.collidepoint(mouse) and left_enabled
    draw_fancy_btn(screen, "<", fonts['big'], BTN_N, BTN_H, BTN_TXT, left_btn_rect, is_hover=left_hover, is_disabled=not left_enabled, custom_radius=6)
    btns['left_ply'] = left_btn_rect

    # Right arrow button
    right_btn_rect = pygame.Rect(BOARD_PX - 12 - 35, ply_y, 35, ply_h)
    right_enabled = active_idx < total_plys - 1 and total_plys > 0
    right_hover = right_btn_rect.collidepoint(mouse) and right_enabled
    draw_fancy_btn(screen, ">", fonts['big'], BTN_N, BTN_H, BTN_TXT, right_btn_rect, is_hover=right_hover, is_disabled=not right_enabled, custom_radius=6)
    btns['right_ply'] = right_btn_rect

    # Build logical visual queue, allowing for Next blocks
    draw_blocks = []
    for i in range(total_plys):
        draw_blocks.append({'type': 'history', 'idx': i})
    
    # If there are Next moves queued from either us or opponent, they appear physically in the queue
    # with white placeholders.
    future_moves = []
    if turn == 'w' and gs.get('next_queue_b'):
        future_moves = gs['next_queue_b']
    elif turn == 'b' and gs.get('next_queue_w'):
        future_moves = gs['next_queue_w']
        
    if client_state.get('draft_moves'):
        future_moves = client_state['draft_moves']

    future_moves = [m for m in future_moves if m.get('type') != 'end_turn']

    next_idx_w = total_plys
    for fnm in future_moves:
        draw_blocks.append({'type': 'placeholder', 'idx': next_idx_w})
        draw_blocks.append({'type': 'next', 'idx': next_idx_w + 1, 'move': fnm})
        next_idx_w += 2

    if not draw_blocks:
        empty_lbl = fonts['small'].render("Nenhum lance registrado", True, T_DIM)
        screen.blit(empty_lbl, empty_lbl.get_rect(center=container_rect.center))
    else:
        num_visible = 6
        total_draws = len(draw_blocks)
        
        # Calculate start and end indices
        if total_draws <= num_visible:
            start_i = 0
            end_i = total_draws
        else:
            # Show up to active_idx natively, or scroll
            # If draft mode or next exists, the queue extends to the right
            start_i = active_idx - num_visible // 2
            if start_i < 0:
                start_i = 0
            end_i = start_i + num_visible
            if end_i > total_draws:
                end_i = total_draws
                start_i = end_i - num_visible
                
        # Force scrolling to the end if we're not browsing history and not at the very start
        if not history_active and total_draws > num_visible:
            end_i = total_draws
            start_i = end_i - num_visible

        middle_width = 450
        block_w = 64
        block_h = 32
        gap = 8
        total_blocks_w = (end_i - start_i) * block_w + (end_i - start_i - 1) * gap
        middle_offset_x = 12 + 35 + (middle_width - total_blocks_w) // 2 + 8

        for draw_offset in range(end_i - start_i):
            idx_draw = start_i + draw_offset
            blk = draw_blocks[idx_draw]
            real_idx = blk['idx']
            
            bx = middle_offset_x + draw_offset * (block_w + gap)
            by = ply_y + (ply_h - block_h) // 2
            block_rect = pygame.Rect(bx, by, block_w, block_h)

            col = (42, 42, 48)
            txt_col = (190, 190, 195)
            border_color = (52, 52, 58)
            b_hover = block_rect.collidepoint(mouse)
            
            if blk['type'] == 'history':
                # Check if this ply has a shadow that has disappeared
                live_gs = turn_hist[-1] if total_plys > 0 else gs
                live_shadow_history = live_gs.get('shadow_history', {})
                info = live_shadow_history.get(real_idx)
                is_revealed_shadow = info is not None and not info.get('active', True)

                if real_idx == 0:
                    text_label = "Início"
                else:
                    p_num = (real_idx + 1) // 2
                    p_col = "W" if real_idx % 2 != 0 else "B"
                    if is_revealed_shadow:
                        s_suffix = " [O]" if info['type'] == 'HIDDEN' else " [F]"
                        text_label = f"{p_num}.{p_col}{s_suffix}"
                    else:
                        text_label = f"{p_num}.{p_col}"

                is_active_block = (real_idx == active_idx)
                is_present_block = (real_idx == total_plys - 1)

                if is_active_block:
                    col = (120, 120, 120) if b_hover else (90, 90, 90)
                    txt_col = (255, 255, 255)
                    border_color = (160, 160, 160)
                elif is_present_block:
                    col = (45, 50, 48) if b_hover else (32, 36, 34)
                    txt_col = (110, 220, 110)
                    border_color = (60, 150, 75)
                else:
                    col = (42, 42, 48) if b_hover else (28, 28, 34)
                    txt_col = (190, 190, 195)
                    border_color = (52, 52, 58)
            elif blk['type'] == 'placeholder':
                p_num = (real_idx + 1) // 2
                p_col = "W" if real_idx % 2 != 0 else "B"
                text_label = f"{p_num}.{p_col}"
                col = (255, 255, 255) if b_hover else (240, 240, 240)
                txt_col = (50, 50, 50)
                border_color = (200, 200, 200)
            elif blk['type'] == 'next':
                p_num = (real_idx + 1) // 2
                p_col = "W" if real_idx % 2 != 0 else "B"
                text_label = f"{p_num}.{p_col}"
                col = (200, 60, 60) if b_hover else (170, 40, 40)
                txt_col = (255, 255, 255)
                border_color = (220, 80, 80)

            draw_rect_aa(screen, col, block_rect, 5)
            draw_rect_aa(screen, border_color, block_rect, 5, 1)

            block_txt = fonts['small'].render(text_label, True, txt_col)
            screen.blit(block_txt, block_txt.get_rect(center=block_rect.center))

            btns[f'ply_block_{real_idx}'] = block_rect

    return btns


def draw_sidebar(screen, gs, fonts, client_state, mouse):
    if PORTRAIT:
        bg_rect = pygame.Rect(0, BOARD_PX + PANEL_H, BOARD_PX, WIN_H - (BOARD_PX + PANEL_H))
        pygame.draw.rect(screen, (22, 22, 26), bg_rect)
        pygame.draw.line(screen, (45, 45, 52), (0, BOARD_PX + PANEL_H), (BOARD_PX, BOARD_PX + PANEL_H), 2)
    else:
        bg_rect = pygame.Rect(BOARD_PX, 0, SIDEBAR_W, WIN_H)
        pygame.draw.rect(screen, (22, 22, 26), bg_rect)
        pygame.draw.line(screen, (45, 45, 52), (BOARD_PX, 0), (BOARD_PX, WIN_H), 2)


def draw_text_center(screen, text, font, color, y_pos, cx=None):
    surf = font.render(text, True, color)
    center_x = cx if cx is not None else (WIN_W // 2)
    rect = surf.get_rect(center=(center_x, y_pos))
    screen.blit(surf, rect)
    return rect


async def perform_undo_action(client_state, gs, is_local, websocket):
    if gs.get('disable_undo_placeholder', False):
        return gs

    now = pygame.time.get_ticks()
    if now - client_state.get('last_undo_time', 0) < 200:
        return gs
    client_state['last_undo_time'] = now

    h_active = client_state.get('history_active', False)
    
    if gs.get('game_over'):
        can_undo = client_state.get('is_test') and len(client_state.get('absolute_history', [])) > 0
    else:
        if client_state.get('is_test'):
            can_undo = len(client_state.get('absolute_history', [])) > 0
        else:
            can_undo = not h_active and (gs.get('normal_done') or gs.get('hidden_count', 0) > 0 or len(client_state.get('draft_moves', [])) > 0 or client_state.get('drafting', False))

    if can_undo:
        old_gs = gs
        if client_state.get('drafting') or client_state.get('draft_moves'):
            old_gs = get_draft_state(gs, client_state.get('draft_moves', []))
            
        if client_state.get('is_test') or gs.get('game_over'):
            play_sound('undo')
            gs = test_mode_undo(client_state, gs)
            if old_gs.get('last_move'):
                fr_u, fc_u, tr_u, tc_u = old_gs['last_move']
                p_anim = old_gs['board'][tr_u][tc_u]
                if not p_anim:
                    for h_key in ['hidden_w', 'hidden_b']:
                        h_dict = old_gs.get(h_key, {})
                        if (tr_u, tc_u) in h_dict:
                            p_anim = h_dict[(tr_u, tc_u)].piece
                            break
                if p_anim:
                    trigger_piece_anim(client_state, p_anim, tr_u, tc_u, fr_u, fc_u, False, False, False)
            client_state['selected'] = None
            client_state['legal_sq'] = []
        elif client_state.get('drafting') or client_state.get('draft_moves'):
            play_sound('undo')
            if client_state.get('draft_moves'):
                popped = client_state['draft_moves'][-1]
                client_state['draft_moves'].pop()
                p_anim = old_gs['board'][popped['tr']][popped['tc']]
                if not p_anim:
                    for h_key in ['hidden_w', 'hidden_b']:
                        h_dict = old_gs.get(h_key, {})
                        if (popped['tr'], popped['tc']) in h_dict:
                            p_anim = h_dict[(popped['tr'], popped['tc'])].piece
                            break
                if p_anim:
                    trigger_piece_anim(client_state, p_anim, popped['tr'], popped['tc'], popped['fr'], popped['fc'], False, False, False)
                if not client_state['draft_moves']:
                    client_state['drafting'] = False
                else:
                    client_state['drafting'] = True
            else:
                client_state['drafting'] = False
                if is_local:
                    gs = copy.deepcopy(client_state['turn_start_snapshot'])
                    if old_gs.get('last_move'):
                        fr_u, fc_u, tr_u, tc_u = old_gs['last_move']
                        p_anim = old_gs['board'][tr_u][tc_u]
                        if not p_anim:
                            for h_key in ['hidden_w', 'hidden_b']:
                                h_dict = old_gs.get(h_key, {})
                                if (tr_u, tc_u) in h_dict:
                                    p_anim = h_dict[(tr_u, tc_u)].piece
                                    break
                        if p_anim:
                            trigger_piece_anim(client_state, p_anim, tr_u, tc_u, fr_u, fc_u, False, False, False)
                else:
                    await websocket.send(json.dumps({"type": "action", "action": "undo"}))
            client_state['selected'] = None
            client_state['legal_sq'] = []
        else:
            play_sound('undo')
            if is_local:
                gs = copy.deepcopy(client_state['turn_start_snapshot'])
                if old_gs.get('last_move'):
                    fr_u, fc_u, tr_u, tc_u = old_gs['last_move']
                    p_anim = old_gs['board'][tr_u][tc_u]
                    if not p_anim:
                        for h_key in ['hidden_w', 'hidden_b']:
                            h_dict = old_gs.get(h_key, {})
                            if (tr_u, tc_u) in h_dict:
                                p_anim = h_dict[(tr_u, tc_u)].piece
                                break
                    if p_anim:
                        trigger_piece_anim(client_state, p_anim, tr_u, tc_u, fr_u, fc_u, False, False, False)
            else:
                await websocket.send(json.dumps({"type": "action", "action": "undo"}))
            client_state['selected'] = None
            client_state['legal_sq'] = []
    else:
        client_state['undo_holding'] = False
    return gs


async def handle_gesture_release(mx, my, client_state, gs, is_local, websocket, screen, fonts):
    if not client_state.get('is_dragging_gesture'):
        return gs

    sr, sc = client_state['drag_piece_sq']
    
    if mx < BOARD_PX and my < BOARD_PX:
        cc2 = mx // SQ
        rr2 = my // SQ
        r = 7 - rr2 if client_state['flipped'] else rr2
        c = 7 - cc2 if client_state['flipped'] else cc2
        
        if (r, c) == (sr, sc):
            # ... existing source click logic ...
            client_state['selected'] = None
            client_state['legal_sq'] = []
            client_state['is_dragging_gesture'] = False
            if client_state.get('fakeout_triggered'):
                await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
            elif client_state.get('hidden_triggered'):
                await MechanicsManager.execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound, None)
            client_state['hidden_triggered'] = False
            client_state['fakeout_triggered'] = False
            return gs
        
        # --- ICE KING CHECK ---
        else:
            curr_dgs_k = get_draft_state(gs, client_state.get('draft_moves', [])) if client_state.get('drafting') else gs
            tb_k = get_true_board(curr_dgs_k, gs['turn'])
            p_king = tb_k[sr][sc]
            p_target = tb_k[r][c]
            
            if p_king and pt(p_king) == 'K' and p_target and pc(p_target) == gs['turn'] and pt(p_target) != 'K' and gs.get('disable_undo_placeholder', False) and gs.get('ice_king_enabled', False):
                # Interaction returns 'frozen', 'unfrozen' or None
                res = ice_king_interaction(gs, sr, sc, r, c)
                if res:
                    if res == 'frozen':
                        trigger_freeze_effect(client_state, gs, r, c)
                    else:
                        trigger_unfreeze_effect(client_state, gs, r, c)
                    
                    if not is_local:
                        await websocket.send(json.dumps({
                            "type": "action", "action": "ice_king",
                            "kr": sr, "kc": sc, "tr": r, "tc": c
                        }))
                    
                    client_state['is_dragging_gesture'] = False
                    client_state['selected'] = None
                    client_state['legal_sq'] = []
                    client_state['hidden_triggered'] = False
                    client_state['fakeout_triggered'] = False
                    return gs
        # --- END ICE KING CHECK ---

        if (r, c) in client_state['legal_sq']:
            # Release on valid target concludes the move!
            promo = None
            curr_dgs = get_draft_state(gs, client_state.get('draft_moves', [])) if client_state.get('drafting') else gs
            tb = get_true_board(curr_dgs, gs['turn'])
            p = tb[sr][sc]
            if p and pt(p) == 'P' and r in (0, 7):
                promo = await ask_promo(screen, fonts, gs['turn'], websocket, client_state)

            if client_state.get('drafting'):
                is_hidden_move = client_state.get('draft_hidden', False) or client_state.get('hidden_triggered', False)
            else:
                is_hidden_move = gs.get('hidden_mode', False) or client_state.get('hidden_triggered', False)

            if client_state.get('drafting'):
                d_moves = client_state.get('draft_moves', [])
                dgs = get_draft_state(gs, d_moves)
                dgs['fakeout_active'] = client_state.get('draft_fakeout', False)
                dgs['hidden_mode'] = is_hidden_move
                legals = legal(dgs, sr, sc)
                if (r, c) in legals:
                    save_for_undo(client_state, gs)
                    d_moves.append({
                        'type': 'move',
                        'fr': sr, 'fc': sc, 'tr': r, 'tc': c,
                        'hidden': is_hidden_move,
                        'fakeout': client_state.get('draft_fakeout', False),
                        'promo': promo,
                        'drafted_turn': (gs['turn_count'] + 1) // 2
                    })
                    client_state['draft_moves'] = d_moves
                    play_sound('next_move')
                    client_state['draft_hidden'] = False
                    client_state['draft_fakeout'] = False
                client_state['selected'] = None
                client_state['legal_sq'] = []
            else:
                if is_local:
                    save_for_undo(client_state, gs)
                    old_game_over = gs.get('game_over', False)
                    old_last = gs.get('last_move')
                    n_cap_w = len(gs.get('captured_w', []))
                    n_cap_b = len(gs.get('captured_b', []))
                    
                    has_captured_piece_on_square = False
                    if gs.get('board') and 0 <= r < 8 and 0 <= c < 8:
                        has_captured_piece_on_square = gs['board'][r][c] is not None
                        
                    is_fakeout = gs.get('fakeout_active', False)
                    res = exec_move(gs, sr, sc, r, c, hidden_move=is_hidden_move, promo=promo)
                    if res:
                        if 'current_turn_actions' not in gs: gs['current_turn_actions'] = []
                        gs['current_turn_actions'].append({
                            'type': 'move', 'fr': sr, 'fc': sc, 'tr': r, 'tc': c,
                            'promo': promo, 'hidden': is_hidden_move, 'fakeout': is_fakeout
                        })
                    
                    new_last = gs.get('last_move')
                    
                    cap_w = len(gs.get('captured_w', [])) > n_cap_w
                    cap_b = len(gs.get('captured_b', [])) > n_cap_b
                    
                    if res and old_last != new_last and new_last:
                        nfr, nfc, ntr, ntc = new_last
                        
                        is_capture_by_log = False
                        if gs.get('log'):
                            norm_last_log = gs['log'][-1].lower()
                            if "capturado" in norm_last_log or "capturada" in norm_last_log:
                                is_capture_by_log = True
                            elif 'x' in norm_last_log:
                                without_xeque = norm_last_log.replace("xeque", "")
                                if 'x' in without_xeque:
                                    is_capture_by_log = True
                        
                        is_capture = cap_w or cap_b or has_captured_piece_on_square or res == "ghost_capture" or is_capture_by_log
                        
                        p_anim = gs['board'][ntr][ntc]
                        if not p_anim:
                            for h_dict in [gs.get('hidden_w', {}), gs.get('hidden_b', {})]:
                                if (ntr, ntc) in h_dict:
                                    target_val = h_dict[(ntr, ntc)]
                                    p_anim = target_val.piece if hasattr(target_val, 'piece') else target_val[1]
                                    break
                        if p_anim:
                            trigger_piece_anim(client_state, p_anim, nfr, nfc, ntr, ntc, is_hidden_move, gs.get('fakeout_active', False), is_capture)
                        
                        is_fakeout = gs.get('fakeout_used', False)
                        is_shadow = gs.get('hidden_count', 0) > 0
                        if gs.get('game_over', False) and not old_game_over:
                            play_sound('game_over')
                        elif is_capture: play_sound('capture')
                        else: play_sound('move')
                        
                    if res == "ghost_capture":
                        gc_type = gs.get('ghost_capture_type', 'standard')
                        col = (245, 120, 20) if gc_type == 'fakeout' else (60, 110, 220)
                        trigger_square_flash(client_state, r, c, col, gc_type)
                        gs['ghost_capture_flash'] = None
                        gs['ghost_capture_type'] = None

                    if gs.get('reveal_flashes'):
                        for r_fl in gs['reveal_flashes']:
                            rr, rc = r_fl[0], r_fl[1]
                            rtype = r_fl[2] if len(r_fl) > 2 else 'hidden'
                            col = (245, 120, 20) if rtype == 'fakeout' else (60, 110, 220)
                            trigger_square_flash(client_state, rr, rc, col, rtype)
                        gs['reveal_flashes'] = []

                    client_state['selected'] = None
                    client_state['legal_sq'] = []
                    gs['hidden_mode'] = False
                else:
                    move_cmd = {
                        "type": "action", "action": "move",
                        "fr": sr, "fc": sc, "tr": r, "tc": c, "promo": promo, "gesture_hidden": is_hidden_move
                    }
                    await websocket.send(json.dumps(move_cmd))
                    client_state['selected'] = None
                    client_state['legal_sq'] = []
            
            client_state['is_dragging_gesture'] = False
            client_state['hidden_triggered'] = False
            client_state['fakeout_triggered'] = False
        else:
            # Release on an invalid square -> Red pulse
            trigger_square_flash(client_state, r, c, (230, 60, 60), 'gesture_invalid')
            client_state['is_dragging_gesture'] = False
            # ADDED: Reset triggers
            if client_state.get('fakeout_triggered'):
                await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
            elif client_state.get('hidden_triggered'):
                await MechanicsManager.execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound, None)
            client_state['hidden_triggered'] = False
            client_state['fakeout_triggered'] = False
            
            client_state['selected'] = None
            client_state['legal_sq'] = []
    else:
        # Released outside the board -> Reset state
        client_state['is_dragging_gesture'] = False
        client_state['hidden_triggered'] = False
        # ADDED: Reset triggers
        if client_state.get('fakeout_triggered'):
            await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
        elif client_state.get('hidden_triggered'):
            await MechanicsManager.execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound, None)
        client_state['hidden_triggered'] = False
        client_state['fakeout_triggered'] = False
        
        client_state['selected'] = None
        client_state['legal_sq'] = []

    return gs


async def wake_up_server(uri):
    pass

async def connect_and_join(uri, action, room_code=None, token=None):
    from firebase_transport import MockWebsocket
    try:
        ws = MockWebsocket()
        if action == "create_room":
            await ws.send(json.dumps({"type": "create_room"}))
        elif action == "join_room":
            await ws.send(json.dumps({"type": "join_room", "room": room_code, "session_token": token}))
        return ws
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("Connection error:", e)
        return e

async def game_loop():
    global WIN_W, WIN_H, PORTRAIT
    pygame.init()
    pygame.key.set_repeat(0)

    try:
        info = pygame.display.Info()
        if info.current_h > info.current_w and info.current_w > 0:
            PORTRAIT = True
            WIN_W = BOARD_PX
            ratio = info.current_h / info.current_w
            WIN_H = max(int(WIN_W * ratio), BOARD_PX + PANEL_H + 200)
        else:
            PORTRAIT = False
            WIN_W = BOARD_PX + SIDEBAR_W
            WIN_H = BOARD_PX + PANEL_H
    except Exception:
        PORTRAIT = False
        WIN_W = BOARD_PX + SIDEBAR_W
        WIN_H = BOARD_PX + PANEL_H

    is_android = hasattr(sys, 'getandroidapilevel')
    flags = pygame.SCALED
    if is_android:
        import os
        os.environ['SDL_RENDER_SCALE_QUALITY'] = '1'
        flags |= pygame.FULLSCREEN
    else:
        flags |= pygame.RESIZABLE

    screen = pygame.display.set_mode((WIN_W, WIN_H), flags)
    try:
        pygame.scrap.init()
    except:
        pass
    pygame.display.set_caption('Hidden Chess')
    fonts = load_fonts()
    load_assets()
    title_font = fonts['title']

    uri = ""
    
    # Try to wake up server immediately in background
    asyncio.create_task(wake_up_server(uri))

    error_msg = ""
    running = True

    app_state = "INTRO_ANIM"
    gs = make_state()
    client_state = {
        'intro_start': pygame.time.get_ticks(),
        'my_color': None,
        'waiting': True,
        'flipped': False,
        'selected': None,
        'legal_sq': [],
        'room_code': None,
        'is_typing': False,
        'msg_queue': deque(),
        'show_hidden': False,
        'resign_confirm': False,
        'panel_btns': {},
        'is_local': False,
        'turn_start_snapshot': None,
        'turn_history': [],
        'history_index': 0,
        'score_to_win': False
    }
    input_text = ""
    websocket = None
    clock = pygame.time.Clock()

    menu_y_start = (WIN_H // 2) - 100
    btn_create = pygame.Rect(WIN_W // 2 - 100, menu_y_start, 200, 50)
    btn_join = pygame.Rect(WIN_W // 2 - 100, menu_y_start + 70, 200, 50)
    btn_local = pygame.Rect(WIN_W // 2 - 100, menu_y_start + 140, 200, 50)
    btn_test = pygame.Rect(WIN_W // 2 - 100, menu_y_start + 210, 200, 50)
    btn_replays = pygame.Rect(WIN_W // 2 - 100, menu_y_start + 280, 200, 50)

    def start_local_game(is_test=False):
        nonlocal gs, client_state, app_state
        gs = make_state()
        gs['game_started'] = True
        gs['fakeout_mode_enabled'] = True
        gs['disable_undo_placeholder'] = True
        gs['score_to_win'] = True
        gs['ice_king_enabled'] = True
        client_state = {
            'my_color': 'w',
            'waiting': False,
            'flipped': False,
            'selected': None,
            'legal_sq': [],
            'room_code': "TEST" if is_test else "LOCAL",
            'is_typing': False,
            'msg_queue': deque(),
            'show_hidden': True,
            'resign_confirm': False,
            'panel_btns': {},
            'is_local': True,
            'is_test': is_test,
            'turn_start_snapshot': copy.deepcopy(gs),
            'turn_history': [copy.deepcopy(gs)],
            'history_index': 0,
            'fakeout_mode_enabled': True,
            'disable_undo_placeholder': True,
            'score_to_win': True,
            'ice_king_enabled': True,
            'absolute_history': [copy.deepcopy(gs)]
        }
        app_state = "PLAYING"
        play_sound('start')
        if is_test:
            pygame.display.set_caption("Hidden Chess - Partida Teste")
        else:
            pygame.display.set_caption("Hidden Chess - Partida Local")

    while running:
        dt = clock.tick(FPS) / 1000.0
        await asyncio.sleep(0) # yield control so websocket background task won't drop pong packets
        
        if client_state.get('is_dragging_gesture'):
            client_state['gesture_timer'] = client_state.get('gesture_timer', 0.0) + dt
            if not client_state.get('hidden_triggered'):
                 if client_state['gesture_timer'] >= 2.0:
                    if MechanicsManager.can_toggle_hidden(gs, client_state):
                        client_state['hidden_triggered'] = True
                        # Trigger hidden logic (async)
                        mx, my = client_state.get('drag_pos', (0,0))
                        await MechanicsManager.execute_toggle_hidden(gs, client_state, client_state.get('is_local', False), websocket, play_sound, None, click_pos=(mx, my), force_shockwave=True)
                        
                        # UPDATE LEGAL SQUARES
                        sr, sc = client_state['drag_piece_sq']
                        gs_temp = copy.copy(gs)
                        gs_temp['drafting_active'] = client_state.get('drafting', False)
                        if client_state.get('drafting'):
                            gs_temp['fakeout_active'] = client_state.get('draft_fakeout', False)
                            gs_temp['hidden_mode'] = client_state.get('draft_hidden', False)
                        sel, legs = get_ui_selection(gs_temp, sr, sc, draft_moves=client_state.get('draft_moves', []))
                        if sel is not None:
                            client_state['selected'] = sel
                            client_state['legal_sq'] = legs
                        else:
                            client_state['legal_sq'] = []
                    else:
                        # Cannot afford or toggle hidden, let timer continue if we can afford fakeout
                        if not MechanicsManager.can_toggle_fakeout(gs, client_state):
                            client_state['gesture_timer'] = 2.0

            if client_state['gesture_timer'] >= 6.0 and not client_state.get('fakeout_triggered'):
                if MechanicsManager.can_toggle_fakeout(gs, client_state):
                    client_state['fakeout_triggered'] = True
                    # Trigger fakeout logic (async)
                    mx, my = client_state.get('drag_pos', (0,0))
                    await MechanicsManager.execute_toggle_fakeout(gs, client_state, client_state.get('is_local', False), websocket, play_sound, None, click_pos=(mx, my), force_shockwave=True)
                    
                    # UPDATE LEGAL SQUARES
                    sr, sc = client_state['drag_piece_sq']
                    gs_temp = copy.copy(gs)
                    gs_temp['drafting_active'] = client_state.get('drafting', False)
                    if client_state.get('drafting'):
                        gs_temp['fakeout_active'] = client_state.get('draft_fakeout', False)
                        gs_temp['hidden_mode'] = client_state.get('draft_hidden', False)
                    sel, legs = get_ui_selection(gs_temp, sr, sc, draft_moves=client_state.get('draft_moves', []))
                    if sel is not None:
                        client_state['selected'] = sel
                        client_state['legal_sq'] = legs
                    else:
                        client_state['legal_sq'] = []
                else:
                    client_state['gesture_timer'] = 6.0

        if client_state.get('undo_holding'):
            is_local = client_state.get('is_local', False)
            client_state['undo_hold_timer'] = client_state.get('undo_hold_timer', 0.0) + dt
            # Ativa o desfazer de ação após segurar o botão por 0.3 segundos para maior fluidez
            if client_state['undo_hold_timer'] >= 0.3:
                gs = await perform_undo_action(client_state, gs, is_local, websocket)
                client_state['undo_hold_timer'] = 0.0

        if client_state.get('anim'):
            client_state['anim']['t'] += dt
            a = client_state['anim']
            
            if a.get('is_hidden') or a.get('is_fakeout'):
                flipped = client_state.get('flipped', False)
                fr, fc = 7 - a['fr'] if flipped else a['fr'], 7 - a['fc'] if flipped else a['fc']
                tr, tc = 7 - a['tr'] if flipped else a['tr'], 7 - a['tc'] if flipped else a['tc']
                start_x, start_y = fc * SQ, fr * SQ
                end_x, end_y = tc * SQ, tr * SQ
                
                progress = min(1.0, a['t'] / a['dur'])
                ease = 1.0 - (1.0 - progress) ** 3
                cur_x = start_x + (end_x - start_x) * ease + SQ // 2
                cur_y = start_y + (end_y - start_y) * ease + SQ // 2
                
                p_color = (60, 110, 220) if a.get('is_hidden') else (245, 120, 20)
                if 'particles' not in client_state:
                    client_state['particles'] = []
                for _ in range(2):
                    angle = random.uniform(0, 6.28)
                    vel = random.uniform(15, 45)
                    client_state['particles'].append({
                        'x': cur_x,
                        'y': cur_y,
                        'vx': math.cos(angle) * vel,
                        'vy': math.sin(angle) * vel,
                        'color': p_color,
                        'life': 0.15 + random.uniform(0, 0.15),
                        'max_life': 0.3,
                        'size': random.uniform(2.5, 5.5)
                    })

            if client_state['anim']['t'] >= client_state['anim']['dur']:
                fr_d, fc_d = 7 - a['tr'] if client_state.get('flipped') else a['tr'], 7 - a['tc'] if client_state.get('flipped') else a['tc']
                end_x, end_y = fc_d * SQ + SQ // 2, fr_d * SQ + SQ // 2
                
                is_cap = a.get('is_capture', False)
                if is_cap:
                    spawn_particles(end_x, end_y, (230, 60, 60), 20, client_state, size=4, speed=200, life=0.4)
                elif a.get('is_hidden'):
                    spawn_particles(end_x, end_y, (60, 110, 220), 16, client_state, size=3.5, speed=120, life=0.35)
                elif a.get('is_fakeout'):
                    spawn_particles(end_x, end_y, (245, 120, 20), 16, client_state, size=3.5, speed=120, life=0.35)
                else:
                    spawn_particles(end_x, end_y, (180, 170, 160), 12, client_state, size=3, speed=100, life=0.25)
                
                client_state['anim'] = None

        if client_state.get('particles'):
            for p in client_state['particles']:
                p['x'] += p['vx'] * dt
                p['y'] += p['vy'] * dt
                p['life'] -= dt
            client_state['particles'] = [p for p in client_state['particles'] if p['life'] > 0]

        # Update shockwaves
        if client_state.get('shockwaves'):
            for sw in client_state['shockwaves']:
                sw['t'] += dt
            client_state['shockwaves'] = [sw for sw in client_state['shockwaves'] if sw['t'] < sw['duration']]

        if client_state.get('freeze_fx'):
            for fx in client_state['freeze_fx']:
                fx['t'] += dt
            client_state['freeze_fx'] = [fx for fx in client_state['freeze_fx'] if fx['t'] < 2.0]

        if client_state.get('unfreeze_fx'):
            for fx in client_state['unfreeze_fx']:
                fx['t'] += dt
            client_state['unfreeze_fx'] = [fx for fx in client_state['unfreeze_fx'] if fx['t'] < 1.0]

        mouse = pygame.mouse.get_pos()
        if client_state.get('is_dragging_gesture'):
            client_state['drag_pos'] = mouse

        # Update flashes
        if 'flashes' in client_state:
            finished_flashes = []
            for sq in list(client_state['flashes'].keys()):
                val = client_state['flashes'][sq]
                if isinstance(val, dict):
                    val['t'] += dt
                    t_val = val['t']
                else:
                    client_state['flashes'][sq] += dt
                    t_val = client_state['flashes'][sq]
                if t_val >= 0.36:  # 2 blinks of 0.18s each
                    finished_flashes.append(sq)
            for sq in finished_flashes:
                del client_state['flashes'][sq]

        # Check if we have a pending connection task
        if client_state.get('conn_task'):
            t = client_state['conn_task']
            if t.done():
                res = t.result()
                client_state['conn_task'] = None
                if isinstance(res, Exception):
                    error_msg = f"Falha na conexão. Tente novamente."
                    app_state = "MENU"
                    websocket = None
                else:
                    websocket = res

        # A. Websocket message parsing (multiplayer only)
        if websocket is not None and not client_state.get('is_local', False):
            try:
                if client_state['msg_queue']:
                    msg = client_state['msg_queue'].popleft()
                else:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=0.005)

                data = json.loads(msg)

                if data['type'] == 'room_created':
                    client_state['room_code'] = data['room']
                    client_state['my_color'] = data['color']
                    app_state = "LOBBY"
                    save_session(data['room'], data.get('session_token'))

                elif data['type'] == 'room_joined':
                    client_state['room_code'] = data['room']
                    client_state['my_color'] = data['color']
                    client_state['flipped'] = (data['color'] == 'b')
                    save_session(data['room'], data.get('session_token'))
                    if data.get('reconnected'):
                        app_state = "GAME"
                        client_state['waiting'] = True # Will be cleared by state_update
                    else:
                        app_state = "LOBBY"

                elif data['type'] == 'state_update':
                    client_state['waiting'] = False
                    new_gs = deserialize_state(data['state'])
                    
                    if new_gs.get('game_over') and not gs.get('game_over'):
                        play_sound('game_over')
                    elif gs.get('last_move') != new_gs.get('last_move') and new_gs.get('last_move') or len(new_gs.get('log', [])) > len(gs.get('log', [])) or gs.get('turn') != new_gs.get('turn'):
                        fr, fc, tr, tc = new_gs.get('last_move', (None, None, None, None))
                        
                        # Detect any captured piece on destination square before the move
                        has_captured_piece_on_square = False
                        if gs.get('board') and tr is not None and tc is not None and 0 <= tr < 8 and 0 <= tc < 8:
                            has_captured_piece_on_square = gs['board'][tr][tc] is not None
                        
                        # Robust check of all new log entries to see if any represent a capture
                        new_log_entries = []
                        if gs.get('log') and len(new_gs.get('log', [])) > len(gs['log']):
                            new_log_entries = new_gs['log'][len(gs['log']):]
                        elif new_gs.get('log'):
                            new_log_entries = [new_gs['log'][-1]]
                        
                        is_capture_by_log = False
                        for entry in new_log_entries:
                            norm_entry = entry.lower()
                            if "capturado" in norm_entry or "capturada" in norm_entry:
                                is_capture_by_log = True
                                break
                            if 'x' in norm_entry:
                                without_xeque = norm_entry.replace("xeque", "")
                                if 'x' in without_xeque:
                                    is_capture_by_log = True
                                    break
                        
                        cap_w = len(new_gs.get('captured_w', [])) > len(gs.get('captured_w', []))
                        cap_b = len(new_gs.get('captured_b', [])) > len(gs.get('captured_b', []))
                        is_capture = cap_w or cap_b or has_captured_piece_on_square or is_capture_by_log
                        
                        last_log = new_gs['log'][-1] if new_gs.get('log') else ""
                        is_shadow = "HIDDEN" in last_log
                        is_fakeout = "FAKEOUT" in last_log
                        
                        is_next_move = "[next]" in last_log.lower() if last_log else False
                        
                        abs_b_new = get_absolute_board(new_gs)
                        if new_gs.get('game_over', False) and not gs.get('game_over', False):
                            pass # Handled below by play_sound('game_over') ? Wait, no
                            
                        if in_check(abs_b_new, new_gs['turn']):
                            play_sound('check')
                        elif is_capture:
                            play_sound('capture')
                        elif is_next_move:
                            play_sound('next_move')
                        else:
                            play_sound('move')
                        
                        is_undo = new_gs.get('turn_count', 0) < gs.get('turn_count', 0) or (new_gs.get('turn_count', 0) == gs.get('turn_count', 0) and len(new_gs.get('log', [])) < len(gs.get('log', [])))

                        if is_undo:
                            if gs.get('last_move'):
                                fr_u, fc_u, tr_u, tc_u = gs['last_move']
                                p_anim = gs['board'][tr_u][tc_u]
                                if not p_anim:
                                    for h_key in ['hidden_w', 'hidden_b']:
                                        h_dict = gs.get(h_key, {})
                                        pos_key = (tr_u, tc_u)
                                        if pos_key in h_dict:
                                            p_anim = h_dict[pos_key].piece
                                            break
                                if p_anim:
                                    trigger_piece_anim(client_state, p_anim, tr_u, tc_u, fr_u, fc_u, is_shadow=False, is_fakeout=False, is_capture=False)
                        else:
                            if new_gs.get('last_move'):
                                fr, fc, tr, tc = new_gs['last_move']
                                p_anim = new_gs['board'][tr][tc]
                                if not p_anim:
                                    for h_key in ['hidden_w', 'hidden_b']:
                                        h_dict = new_gs.get(h_key, {})
                                        pos_key = (tr, tc)
                                        if pos_key in h_dict:
                                            p_anim = h_dict[pos_key].piece
                                            break
                                if p_anim:
                                    trigger_piece_anim(client_state, p_anim, fr, fc, tr, tc, is_shadow, is_fakeout, is_capture)
                    
                    client_state['drafting'] = False
                    client_state['draft_moves'] = []

                    if 'turn_history' not in client_state:
                        client_state['turn_history'] = []
                        client_state['history_index'] = 0

                    if new_gs.get('game_started', False):
                        if not client_state['turn_history']:
                            client_state['turn_history'] = [copy.deepcopy(new_gs)]
                            client_state['history_index'] = 0
                        else:
                            last_gs = client_state['turn_history'][-1]
                            if (last_gs['game_over'] and not new_gs['game_over']) or (new_gs['turn_count'] == 1 and last_gs['turn_count'] > 1):
                                client_state['turn_history'] = [copy.deepcopy(new_gs)]
                                client_state['history_index'] = 0
                                client_state.pop('export_success_msg', None)
                            elif (new_gs['turn'] != last_gs['turn'] or 
                                  new_gs['turn_count'] != last_gs['turn_count'] or 
                                  (new_gs['game_over'] and not last_gs['game_over'])):
                                client_state['turn_history'].append(copy.deepcopy(new_gs))
                                if client_state.get('history_index', 0) == len(client_state['turn_history']) - 2:
                                    client_state['history_index'] = len(client_state['turn_history']) - 1

                    if new_gs.get('ghost_capture_flash'):
                        gr, gc_pos = new_gs['ghost_capture_flash']
                        gctype = new_gs.get('ghost_capture_type')
                        col = (245, 120, 20) if gctype == 'fakeout' else (60, 110, 220)
                        trigger_square_flash(client_state, gr, gc_pos, col, gctype)

                    if new_gs.get('reveal_flashes'):
                        for rf in new_gs['reveal_flashes']:
                            rr, rc = rf[0], rf[1]
                            rtype = rf[2] if len(rf) > 2 else 'hidden'
                            col = (245, 120, 20) if rtype == 'fakeout' else (60, 110, 220)
                            trigger_square_flash(client_state, rr, rc, col, rtype)

                    if new_gs['turn'] != gs['turn']:
                        client_state['resign_confirm'] = False

                    if client_state['selected']:
                        r, c = client_state['selected']
                        tb = get_true_board(new_gs, client_state['my_color'])
                        p = tb[r][c]

                        if p and pc(p) == client_state['my_color'] and new_gs['turn'] == client_state[
                            'my_color']:
                            client_state['legal_sq'] = legal(new_gs, r, c)
                        else:
                            client_state['selected'] = None
                            client_state['legal_sq'] = []

                    gs = new_gs
                    if gs.get('game_started', False):
                        if app_state != "PLAYING":
                            play_sound('start')
                        app_state = "PLAYING"
                        pygame.display.set_caption(
                            f"Hidden Chess - Jogando de {'Brancas' if client_state['my_color'] == 'w' else 'Pretas'} (Sala: {client_state['room_code']})")
                    else:
                        app_state = "LOBBY"
                        client_state['fakeout_mode_enabled'] = gs.get('fakeout_mode_enabled', True)
                        client_state['disable_undo_placeholder'] = gs.get('disable_undo_placeholder', True)
                        client_state['score_to_win'] = gs.get('score_to_win', True)
                        client_state['ice_king_enabled'] = gs.get('ice_king_enabled', True)

                elif data['type'] == 'error':
                    error_msg = data['message']
                    if error_msg == "Room not found or full." or error_msg == "Room not found or full":
                        error_msg = "Sala não encontrada ou cheia."
                    elif error_msg == "Room not found." or error_msg == "Room not found":
                        error_msg = "Sala não encontrada."
                    app_state = "MENU"
                    if websocket:
                        await websocket.close()
                        websocket = None

            except asyncio.TimeoutError:
                pass
            except Exception as e:
                print("Websocket error:", e)


        # C. Handle local and remote pygame events
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
                break
                
            if ev.type == pygame.VIDEORESIZE:
                if not is_android:
                    WIN_W, WIN_H = ev.w, ev.h
                    screen = pygame.display.set_mode((WIN_W, WIN_H), flags)
            elif ev.type == getattr(pygame, 'APP_DIDENTERFOREGROUND', None) or (ev.type == getattr(pygame, 'WINDOWEVENT', None) and getattr(ev, 'window_event', getattr(ev, 'event', None)) == getattr(pygame, 'WINDOWEVENT_RESTORED', None)):
                if is_android:
                    screen = pygame.display.set_mode((WIN_W, WIN_H), flags)
                
            if app_state == "MENU":
                if ev.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = ev.pos
                    if btn_create.collidepoint((mx, my)):
                        play_sound('click')
                        app_state = "CONNECTING"
                        gs = make_state()
                        client_state = {
                            'my_color': None,
                            'waiting': True,
                            'flipped': False,
                            'selected': None,
                            'legal_sq': [],
                            'room_code': None,
                            'is_typing': False,
                            'msg_queue': deque(),
                            'show_hidden': False,
                            'resign_confirm': False,
                            'panel_btns': {},
                            'is_local': False,
                            'fakeout_mode_enabled': False,
                            'disable_undo_placeholder': False,
                            'score_to_win': False
                        }
                        try:
                            client_state['conn_task'] = asyncio.create_task(connect_and_join(uri, "create_room"))
                        except Exception as e:
                            error_msg = f"Falha ao conectar."
                            app_state = "MENU"
                            
                    elif btn_join.collidepoint((mx, my)):
                        play_sound('click')
                        app_state = "JOINING"
                        session_data = load_session()
                        input_text = session_data.get('room_code', "") if session_data else ""
                        error_msg = ""

                    elif btn_local.collidepoint((mx, my)):
                        play_sound('click')
                        start_local_game(is_test=False)
                    elif btn_test.collidepoint((mx, my)):
                        play_sound('click')
                        start_local_game(is_test=True)
                    elif btn_replays.collidepoint((mx, my)):
                        play_sound('menu')
                        app_state = "REPLAY_LIST"
                        client_state['replay_list'] = load_replay_files()
                        client_state['replay_page'] = 0

            elif app_state == "JOINING":
                if ev.type == pygame.TEXTINPUT and len(input_text) < 4:
                    if ev.text and ev.text.isalnum():
                        input_text += ev.text.upper()
                
                if ev.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = ev.pos
                    if 'join_btn_enter' in client_state and client_state['join_btn_enter'].collidepoint((mx, my)):
                        if len(input_text) == 4:
                            app_state = "CONNECTING"
                            try: pygame.key.stop_text_input()
                            except: pass
                            gs = make_state()
                            client_state = {
                                'my_color': None, 'waiting': True, 'flipped': False,
                                'selected': None, 'legal_sq': [], 'room_code': None,
                                'is_typing': False, 'msg_queue': deque(),
                                'show_hidden': False, 'resign_confirm': False,
                                'panel_btns': {}, 'is_local': False, 'score_to_win': False,
                                'fakeout_mode_enabled': False, 'disable_undo_placeholder': False
                            }
                            try:
                                token = None
                                session_data = load_session()
                                if session_data and session_data.get('room_code') == input_text:
                                    token = session_data.get('session_token')
                                client_state['conn_task'] = asyncio.create_task(connect_and_join(uri, "join_room", input_text, token))
                            except Exception as e:
                                error_msg = f"Falha ao conectar."
                                app_state = "MENU"
                    elif 'join_btn_back' in client_state and client_state['join_btn_back'].collidepoint((mx, my)):
                        input_text = input_text[:-1]
                    elif 'join_btn_esc' in client_state and client_state['join_btn_esc'].collidepoint((mx, my)):
                        app_state = "MENU"
                        try: pygame.key.stop_text_input()
                        except: pass
                    elif 'join_input_rect' in client_state and client_state['join_input_rect'].collidepoint((mx, my)):
                        try: pygame.key.start_text_input()
                        except: pass
                    elif 'join_kbt' in client_state:
                        for char, rect in client_state['join_kbt'].items():
                            if rect.collidepoint((mx, my)):
                                if len(input_text) < 4:
                                    input_text += char
                                break

                if ev.type == pygame.KEYDOWN:
                    if (ev.key == pygame.K_RETURN or ev.key == pygame.K_KP_ENTER) and len(input_text) == 4:
                        app_state = "CONNECTING"
                        try: pygame.key.stop_text_input()
                        except: pass
                        gs = make_state()
                        client_state = {
                            'my_color': None,
                            'waiting': True,
                            'flipped': False,
                            'selected': None,
                            'legal_sq': [],
                            'room_code': None,
                            'is_typing': False,
                            'msg_queue': deque(),
                            'show_hidden': False,
                            'resign_confirm': False,
                            'panel_btns': {},
                            'is_local': False,
                            'fakeout_mode_enabled': False,
                            'disable_undo_placeholder': False,
                            'score_to_win': False
                        }
                        try:
                            token = None
                            session_data = load_session()
                            if session_data and session_data.get('room_code') == input_text:
                                token = session_data.get('session_token')
                            client_state['conn_task'] = asyncio.create_task(connect_and_join(uri, "join_room", input_text, token))
                        except Exception as e:
                            error_msg = f"Falha ao conectar."
                            app_state = "MENU"
                    elif ev.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif ev.key == pygame.K_ESCAPE:
                        app_state = "MENU"
                        try: pygame.key.stop_text_input()
                        except: pass
                    elif len(input_text) < 4:
                        if ev.unicode and ev.unicode.isalnum():
                            input_text += ev.unicode.upper()
                        elif pygame.K_a <= ev.key <= pygame.K_z:
                            input_text += chr(ev.key).upper()
                        elif pygame.K_0 <= ev.key <= pygame.K_9:
                            input_text += chr(ev.key)

            elif app_state == "REPLAY_LIST":
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        play_sound('click')
                        app_state = "MENU"
                        client_state.pop('replay_list', None)
                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = ev.pos
                    if 'replay_rects' in client_state:
                        for global_idx, rect in client_state['replay_rects'].items():
                            if rect.collidepoint((mx, my)):
                                play_sound('click')
                                replays = client_state['replay_list']
                                rep = replays[global_idx]
                                data = rep['data']
                                try:
                                    th_serialized = data.get("turn_history_serialized", [])
                                    if th_serialized:
                                        loaded_history = [deserialize_state(snap) for snap in th_serialized]
                                    else:
                                        loaded_history = [deserialize_state(data)]
                                except Exception as err:
                                    print("Erro ao carregar o replay:", err)
                                    loaded_history = [deserialize_state(data)]
                                gs = loaded_history[0] if loaded_history else deserialize_state(data)
                                client_state = {
                                    'my_color': data.get('player_color', 'w'),
                                    'waiting': False,
                                    'flipped': False,
                                    'selected': None,
                                    'legal_sq': [],
                                    'room_code': data.get('room_code', 'LOCAL'),
                                    'is_typing': False,
                                    'msg_queue': deque(),
                                    'show_hidden': True,
                                    'resign_confirm': False,
                                    'panel_btns': {},
                                    'is_local': True,
                                    'is_replay': True,
                                    'turn_start_snapshot': copy.deepcopy(gs),
                                    'turn_history': loaded_history,
                                    'history_index': 0,
                                    'fakeout_mode_enabled': False,
                                    'disable_undo_placeholder': False,
                                    'score_to_win': False,
                                    'absolute_history': [copy.deepcopy(gs)]
                                }
                                app_state = "REPLAY_VIEW"
                                break
                    if 'replay_btn_back' in client_state and client_state['replay_btn_back'].collidepoint((mx, my)):
                        play_sound('click')
                        app_state = "MENU"
                        client_state.pop('replay_list', None)
                    elif client_state.get('replay_prev_page') and client_state['replay_prev_page'].collidepoint((mx, my)):
                        play_sound('click')
                        client_state['replay_page'] = max(0, client_state.get('replay_page', 0) - 1)
                    elif client_state.get('replay_next_page') and client_state['replay_next_page'].collidepoint((mx, my)):
                        play_sound('click')
                        replays = client_state['replay_list']
                        max_page = (len(replays) - 1) // 5
                        client_state['replay_page'] = min(max_page, client_state.get('replay_page', 0) + 1)

            elif app_state == "REPLAY_VIEW":
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        play_sound('click')
                        app_state = "REPLAY_LIST"
                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = ev.pos
                    if mx < BOARD_PX and BOARD_PX <= my < BOARD_PX + PANEL_H:
                        btns = client_state['panel_btns']
                        if btns.get('left_ply') and btns['left_ply'].collidepoint((mx, my)):
                            idx = client_state.get('history_index', 0)
                            if idx > 0:
                                client_state['history_index'] = idx - 1
                                play_sound('select')
                        elif btns.get('right_ply') and btns['right_ply'].collidepoint((mx, my)):
                            idx = client_state.get('history_index', 0)
                            if idx < len(client_state.get('turn_history', [])) - 1:
                                client_state['history_index'] = idx + 1
                                play_sound('select')
                        elif btns.get('exit_replay') and btns['exit_replay'].collidepoint((mx, my)):
                            play_sound('click')
                            app_state = "REPLAY_LIST"
                        elif btns.get('flip') and btns['flip'].collidepoint((mx, my)):
                            play_sound('click')
                            client_state['flipped'] = not client_state['flipped']
                        else:
                            for key, b_rect in btns.items():
                                if key.startswith('ply_block_') and b_rect.collidepoint((mx, my)):
                                    target_idx = int(key.split('_')[-1])
                                    client_state['history_index'] = target_idx
                                    play_sound('select')

            elif app_state == "LOBBY":
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        if websocket:
                            await websocket.send(json.dumps({"type": "leave_room"}))
                            await websocket.close()
                            websocket = None
                        app_state = "MENU"
                        client_state['room_code'] = None

                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = ev.pos
                    play_btn_y = WIN_H // 2 - 20
                    play_btn_rect = pygame.Rect((WIN_W - 240) // 2, play_btn_y, 240, 52)
                    
                    back_btn_y = play_btn_y + 80
                    back_btn_rect = pygame.Rect((WIN_W - 160) // 2, back_btn_y, 160, 44)

                    if back_btn_rect.collidepoint((mx, my)):
                        play_sound('click')
                        if websocket:
                            await websocket.send(json.dumps({"type": "leave_room"}))
                            await websocket.close()
                            websocket = None
                        app_state = "MENU"
                        client_state['room_code'] = None

                    if client_state.get('my_color') != 'b':
                        if play_btn_rect.collidepoint((mx, my)):
                            if client_state.get('is_local', False):
                                gs['game_started'] = True
                                gs['fakeout_mode_enabled'] = True
                                gs['disable_undo_placeholder'] = True
                                gs['score_to_win'] = True
                                gs['ice_king_enabled'] = True
                                client_state['turn_start_snapshot'] = copy.deepcopy(gs)
                                client_state['turn_history'] = [copy.deepcopy(gs)]
                                client_state['history_index'] = 0
                                if client_state.get('is_test'):
                                    client_state['absolute_history'] = []
                                app_state = "PLAYING"
                                play_sound('start')
                                if client_state.get('is_test'):
                                    pygame.display.set_caption("Hidden Chess - Partida Teste")
                                else:
                                    pygame.display.set_caption("Hidden Chess - Partida Local")
                            else:
                                if gs.get('opponent_joined', False):
                                    if websocket:
                                        await websocket.send(json.dumps({
                                            "type": "action",
                                            "action": "start_game"
                                        }))

            elif app_state == "PLAYING":
                is_local = client_state.get('is_local', False)
                active_color = gs['turn'] if is_local else client_state['my_color']

                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_LEFT:
                        idx = client_state.get('history_index', 0)
                        if idx > 0:
                            reverted_gs = client_state['turn_history'][idx]
                            client_state['history_index'] = idx - 1
                            client_state['selected'] = None
                            client_state['legal_sq'] = []
                            if reverted_gs.get('last_move'):
                                fr_u, fc_u, tr_u, tc_u = reverted_gs['last_move']
                                p_anim = reverted_gs['board'][tr_u][tc_u]
                                if not p_anim:
                                    for h_key in ['hidden_w', 'hidden_b']:
                                        h_dict = reverted_gs.get(h_key, {})
                                        pos_key = (tr_u, tc_u)
                                        if pos_key in h_dict:
                                            p_anim = h_dict[pos_key].piece
                                            break
                                if p_anim:
                                    last_log = reverted_gs['log'][-1] if reverted_gs.get('log') else ""
                                    is_sh = "HIDDEN" in last_log
                                    is_fk = "FAKEOUT" in last_log
                                    trigger_piece_anim(client_state, p_anim, tr_u, tc_u, fr_u, fc_u, is_shadow=is_sh, is_fakeout=is_fk, is_capture=False)
                    elif ev.key == pygame.K_RIGHT:
                        idx = client_state.get('history_index', 0)
                        if idx < len(client_state.get('turn_history', [])) - 1:
                            target_gs = client_state['turn_history'][idx + 1]
                            client_state['history_index'] = idx + 1
                            client_state['selected'] = None
                            client_state['legal_sq'] = []
                            if target_gs.get('last_move'):
                                fr, fc, tr, tc = target_gs['last_move']
                                p_anim = target_gs['board'][tr][tc]
                                if not p_anim:
                                    for h_key in ['hidden_w', 'hidden_b']:
                                        h_dict = target_gs.get(h_key, {})
                                        pos_key = (tr, tc)
                                        if pos_key in h_dict:
                                            p_anim = h_dict[pos_key].piece
                                            break
                                if p_anim:
                                    last_log = target_gs['log'][-1] if target_gs.get('log') else ""
                                    is_sh = "HIDDEN" in last_log
                                    is_fk = "FAKEOUT" in last_log
                                    trigger_piece_anim(client_state, p_anim, fr, fc, tr, tc, is_shadow=is_sh, is_fakeout=is_fk, is_capture=False)
                    elif ev.key == pygame.K_f:
                        client_state['flipped'] = not client_state['flipped']
                    elif ev.key == pygame.K_h and gs['turn'] == active_color and not gs.get('disable_undo_placeholder', False):
                        turn = gs['turn']
                        my_color = client_state['my_color']
                        total_plys = len(client_state.get('turn_history', []))
                        active_idx = client_state.get('history_index', 0)
                        history_active = total_plys > 0 and active_idx < total_plys - 1
                        if client_state.get('drafting'):
                            dgs = get_draft_state(gs, client_state.get('draft_moves', []))
                            can_toggle = not history_active and turn == my_color and dgs['turn_count'] > 1 and can_afford(dgs) and dgs['hidden_count'] == 0
                            is_currently_on = client_state.get('draft_hidden', False)
                        else:
                            can_toggle = not history_active and turn == my_color and not gs['normal_done'] and gs['turn_count'] > 1 and can_afford(gs) and gs['hidden_count'] == 0
                            is_currently_on = gs.get('hidden_mode', False)

                        if can_toggle:
                            if is_currently_on:
                                play_sound('hidden_off')
                            else:
                                play_sound('hidden')

                        client_state['selected'] = None
                        client_state['legal_sq'] = []
                        if is_local:
                            if not gs['game_over']:
                                if client_state.get('drafting'):
                                    dgs = get_draft_state(gs, client_state.get('draft_moves', []))
                                    if dgs['turn_count'] > 1 and can_afford(dgs) and dgs['hidden_count'] == 0:
                                        save_for_undo(client_state, gs)
                                        client_state['draft_hidden'] = not client_state.get('draft_hidden', False)
                                        if client_state['draft_hidden']:
                                            client_state['draft_fakeout'] = False
                                elif not gs['normal_done'] and gs['hidden_count'] == 0:
                                    if gs['turn_count'] > 1 and can_afford(gs):
                                        save_for_undo(client_state, gs)
                                        gs['hidden_mode'] = not gs.get('hidden_mode', False)
                        else:
                            if client_state.get('drafting'):
                                dgs = get_draft_state(gs, client_state.get('draft_moves', []))
                                if dgs['turn_count'] > 1 and can_afford(dgs) and dgs['hidden_count'] == 0:
                                    client_state['draft_hidden'] = not client_state.get('draft_hidden', False)
                                    if client_state['draft_hidden']:
                                        client_state['draft_fakeout'] = False
                            else:
                                await websocket.send(json.dumps({"type": "action", "action": "toggle_hidden"}))
                    elif ev.key == pygame.K_u and gs['turn'] == active_color and not gs.get('disable_undo_placeholder', False):
                        gs = await perform_undo_action(client_state, gs, is_local, websocket)
                    elif ev.key in (pygame.K_RETURN, pygame.K_SPACE) and gs['turn'] == active_color and not gs.get('disable_undo_placeholder', False):
                        h_active = client_state.get('history_active', False)
                        q_key = f'next_queue_{gs["turn"]}'
                        temp_end_en = not h_active and (gs['normal_done'] or gs.get('hidden_count', 0) > 0 or gs.get(q_key))
                        if client_state.get('draft_moves'):
                            temp_end_en = check_draft_endable(client_state['draft_moves'], temp_end_en)
                        
                        if temp_end_en:
                            if is_local:
                                dm = client_state.get('draft_moves', [])
                                dm_copy = []
                                for m in dm:
                                    m_dict = copy.deepcopy(m)
                                    if 'type' not in m_dict:
                                        m_dict['type'] = 'move'
                                    dm_copy.append(m_dict)
                                if dm_copy and dm_copy[-1].get('type') != 'end_turn':
                                    dm_copy.append({'type': 'end_turn'})
                                save_for_undo(client_state, gs)
                                q_key_kb = f"next_queue_{gs['turn']}"
                                
                                if gs.get('normal_done') or gs.get('hidden_count', 0) > 0:
                                    # Manual move was made, check for matching
                                    next_a = get_next_turn_from_queue(gs, gs['turn'])
                                    if next_a:
                                        if compare_turns(gs.get('current_turn_actions', []), next_a):
                                            gs['pts'][gs['turn']] += 1
                                        else:
                                            gs['pts'][gs['turn']] -= 1
                                        pop_next_turn_from_queue(gs, gs['turn'])
                                    
                                    # Invalidate existing queue turns if any? 
                                    # Actually users said "limpa Next A e mantém Next B".
                                    # The pop_next_turn_from_queue already does that if called.

                                    if dm_copy and dm:
                                        if q_key_kb not in gs: gs[q_key_kb] = []
                                        gs[q_key_kb].extend(dm_copy)
                                        for m in dm_copy:
                                            if m.get('type') == 'move':
                                                htxt = "[Fakeout] " if m.get('fakeout') else "[Sombra] " if m.get('hidden') else ""
                                                note_msg = f"{htxt}{alg(m['fc'], m['fr'])} -> {alg(m['tc'], m['tr'])}"
                                                gs['log'].append(f"NEXT|{gs['turn']}|{note_msg}")
                                    end_turn(gs)
                                else:
                                    # No manual move, append new drafts to existing queue
                                    if dm_copy and dm:
                                        if q_key_kb not in gs: gs[q_key_kb] = []
                                        gs[q_key_kb].extend(dm_copy)
                                        for m in dm_copy:
                                            if m.get('type') == 'move':
                                                htxt = "[Fakeout] " if m.get('fakeout') else "[Sombra] " if m.get('hidden') else ""
                                                note_msg = f"{htxt}{alg(m['fc'], m['fr'])} -> {alg(m['tc'], m['tr'])}"
                                                gs['log'].append(f"NEXT|{gs['turn']}|{note_msg}")
                                    
                                    if gs.get(q_key_kb):
                                        process_next_queues(gs)
                                    else:
                                        end_turn(gs)
                                if in_check(get_absolute_board(gs), gs['turn']):
                                    play_sound('check')
                                if gs.get('reveal_flashes'):
                                    for rf in gs['reveal_flashes']:
                                        rr, rc = rf[0], rf[1]
                                        rtype = rf[2] if len(rf) > 2 else 'hidden'
                                        col = (245, 120, 20) if rtype == 'fakeout' else (60, 110, 220)
                                        trigger_square_flash(client_state, rr, rc, col, rtype)
                                    gs['reveal_flashes'] = []
                                gs['hidden_mode'] = False
                                client_state['turn_start_snapshot'] = copy.deepcopy(gs)
                                client_state['turn_history'].append(copy.deepcopy(gs))
                                client_state['history_index'] = len(client_state['turn_history']) - 1
                                client_state['selected'] = None
                                client_state['legal_sq'] = []
                            else:
                                dm = client_state.get('draft_moves', [])
                                dm_copy = []
                                for m in dm:
                                    m_dict = copy.deepcopy(m)
                                    if 'type' not in m_dict:
                                        m_dict['type'] = 'move'
                                    dm_copy.append(m_dict)
                                if dm_copy and dm_copy[-1].get('type') != 'end_turn':
                                    dm_copy.append({'type': 'end_turn'})
                                    await websocket.send(json.dumps({"type": "action", "action": "end_turn", "draft_moves": dm_copy}))
                                else:
                                    await websocket.send(json.dumps({"type": "action", "action": "end_turn"}))
                            client_state['drafting'] = False
                            client_state['draft_moves'] = []
                            client_state['selected'] = None
                            client_state['legal_sq'] = []

                elif ev.type == pygame.MOUSEBUTTONUP:
                    client_state['undo_holding'] = False
                    if client_state.get('is_dragging_gesture') and not client_state.get('waiting'):
                        mx, my = ev.pos
                        gs = await handle_gesture_release(mx, my, client_state, gs, is_local, websocket, screen, fonts)
                elif ev.type == pygame.MOUSEMOTION:
                    if client_state.get('is_dragging_gesture'):
                        client_state['drag_pos'] = ev.pos
                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = ev.pos
                    if ev.button in (4, 5):
                        continue

                    if client_state['waiting']: continue

                    if mx < BOARD_PX and BOARD_PX <= my < BOARD_PX + PANEL_H:
                        btns = client_state['panel_btns']

                        if btns.get('left_ply') and btns['left_ply'].collidepoint((mx, my)):
                            idx = client_state.get('history_index', 0)
                            if idx > 0:
                                client_state['history_index'] = idx - 1
                                client_state['selected'] = None
                                client_state['legal_sq'] = []
                            continue
                        elif btns.get('right_ply') and btns['right_ply'].collidepoint((mx, my)):
                            idx = client_state.get('history_index', 0)
                            if idx < len(client_state.get('turn_history', [])) - 1:
                                client_state['history_index'] = idx + 1
                                client_state['selected'] = None
                                client_state['legal_sq'] = []
                            continue
                        else:
                            ply_hit = False
                            for key, b_rect in btns.items():
                                if key.startswith('ply_block_') and b_rect.collidepoint((mx, my)):
                                    target_idx = int(key.split('_')[-1])
                                    client_state['history_index'] = target_idx
                                    client_state['selected'] = None
                                    client_state['legal_sq'] = []
                                    ply_hit = True
                                    break
                            if ply_hit:
                                continue

                        if gs['game_over']:
                            if btns.get('menu') and btns['menu'].collidepoint((mx, my)):
                                if is_local:
                                    app_state = "MENU"
                                    client_state['room_code'] = None
                                else:
                                    await websocket.send(json.dumps({"type": "leave_room"}))
                                    if websocket:
                                        await websocket.close()
                                        websocket = None
                                    app_state = "MENU"
                                    client_state['room_code'] = None
                            elif btns.get('rematch') and btns['rematch'].collidepoint((mx, my)):
                                if is_local:
                                    is_test_mode = client_state.get('is_test', False)
                                    start_local_game(is_test=is_test_mode)
                                else:
                                    await websocket.send(
                                        json.dumps({"type": "action", "action": "rematch_request"}))
                            elif btns.get('accept') and btns['accept'].collidepoint((mx, my)):
                                if not is_local:
                                    await websocket.send(
                                        json.dumps({"type": "action", "action": "rematch_accept"}))
                            elif btns.get('decline') and btns['decline'].collidepoint((mx, my)):
                                if not is_local:
                                    await websocket.send(
                                        json.dumps({"type": "action", "action": "rematch_decline"}))
                            elif btns.get('export_json') and btns['export_json'].collidepoint((mx, my)):
                                try:
                                    export_data = serialize_game_to_dict(gs, client_state)
                                    filename = f"partida_{int(time.time())}.json"
                                    with open(filename, "w", encoding="utf-8") as f_out:
                                        json.dump(export_data, f_out, indent=4, ensure_ascii=False)
                                    client_state['export_success_msg'] = f"Exportado com sucesso para {filename}!"
                                    gs['log'].append(f"Replay exportado com sucesso para {filename}!")
                                except Exception as e:
                                    client_state['export_success_msg'] = f"Erro no export: {str(e)}"
                            elif btns.get('undo') and btns['undo'].collidepoint((mx, my)):
                                client_state['undo_holding'] = True
                                client_state['undo_hold_timer'] = 0.0
                                gs = await perform_undo_action(client_state, gs, is_local, websocket)
                            continue

                        if btns.get('flip') and btns['flip'].collidepoint((mx, my)):
                            client_state['flipped'] = not client_state['flipped']
                        elif btns['show'].collidepoint((mx, my)):
                            client_state['show_hidden'] = not client_state['show_hidden']
                        elif btns.get('export_json') and btns['export_json'].collidepoint((mx, my)):
                            try:
                                export_data = serialize_game_to_dict(gs, client_state)
                                filename = f"partida_{int(time.time())}.json"
                                with open(filename, "w", encoding="utf-8") as f_out:
                                    json.dump(export_data, f_out, indent=4, ensure_ascii=False)
                                client_state['export_success_msg'] = f"Exportado com sucesso para {filename}!"
                                gs['log'].append(f"Replay exportado com sucesso para {filename}!")
                            except Exception as e:
                                client_state['export_success_msg'] = f"Erro no export: {str(e)}"

                        pass
                        
                        if btns.get('resign') and btns['resign'].collidepoint((mx, my)):
                            if not client_state.get('resign_confirm'):
                                client_state['resign_confirm'] = True
                                play_sound('resign')
                            else:
                                if is_local:
                                    save_for_undo(client_state, gs)
                                    gs['game_over'] = True
                                    winner = 'Pretas' if gs['turn'] == 'w' else 'Brancas'
                                    resigner = 'Brancas' if gs['turn'] == 'w' else 'Pretas'
                                    gs['game_over_msg'] = f"As {resigner} desistiram. As {winner} venceram!"
                                    client_state['resign_confirm'] = False
                                    client_state['_serialize_cache'] = {}
                                    play_sound('game_over')
                                else:
                                    await websocket.send(json.dumps({"type": "action", "action": "resign"}))
                                    client_state['resign_confirm'] = False
                                    client_state['_serialize_cache'] = {}
                        else:
                            client_state['resign_confirm'] = False

                        if gs['turn'] == active_color:
                            if btns.get('hidden') and btns['hidden'].collidepoint((mx, my)):
                                await MechanicsManager.execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound, save_for_undo, None)
                            elif btns.get('fakeout') and btns['fakeout'].collidepoint((mx, my)):
                                await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, save_for_undo, None)
                            elif btns.get('undo') and btns['undo'].collidepoint((mx, my)):
                                client_state['undo_holding'] = True
                                client_state['undo_hold_timer'] = 0.0
                                gs = await perform_undo_action(client_state, gs, is_local, websocket)
                            elif btns.get('end') and btns['end'].collidepoint((mx, my)):
                                h_active = client_state.get('history_active', False)
                                q_key = f'next_queue_{gs["turn"]}'
                                temp_end_en = not h_active and gs['turn'] == active_color and (gs['normal_done'] or gs.get('hidden_count', 0) > 0 or gs.get(q_key))
                                if client_state.get('draft_moves'):
                                    temp_end_en = check_draft_endable(client_state['draft_moves'], temp_end_en)
                                if not temp_end_en:
                                    continue

                                play_sound('end')

                                dm = client_state.get('draft_moves', [])
                                dm_copy = []
                                for m in dm:
                                    m_dict = copy.deepcopy(m)
                                    if 'type' not in m_dict:
                                        m_dict['type'] = 'move'
                                    dm_copy.append(m_dict)
                                if dm_copy and dm_copy[-1].get('type') != 'end_turn':
                                    dm_copy.append({'type': 'end_turn'})
                                    
                                if is_local:
                                    q_key_btn = f'next_queue_{gs["turn"]}'
                                    if gs['normal_done'] or gs['hidden_count'] > 0 or gs.get(q_key_btn):
                                        save_for_undo(client_state, gs)
                                        
                                        if gs.get('normal_done') or gs.get('hidden_count', 0) > 0:
                                            # Manual move was made
                                            next_a = get_next_turn_from_queue(gs, gs['turn'])
                                            if next_a:
                                                if compare_turns(gs.get('current_turn_actions', []), next_a):
                                                    gs['pts'][gs['turn']] += 1
                                                else:
                                                    gs['pts'][gs['turn']] -= 1
                                                pop_next_turn_from_queue(gs, gs['turn'])

                                            if dm_copy and dm:
                                                if q_key_btn not in gs: gs[q_key_btn] = []
                                                gs[q_key_btn].extend(dm_copy)
                                            end_turn(gs)
                                        else:
                                            # No manual move, append new drafts
                                            if dm_copy and dm:
                                                if q_key_btn not in gs: gs[q_key_btn] = []
                                                gs[q_key_btn].extend(dm_copy)
                                            
                                            if gs.get(q_key_btn):
                                                process_next_queues(gs)
                                            else:
                                                end_turn(gs)
                                        if in_check(get_absolute_board(gs), gs['turn']):
                                            play_sound('check')
                                        if gs.get('reveal_flashes'):
                                            for rf in gs['reveal_flashes']:
                                                rr, rc = rf[0], rf[1]
                                                rtype = rf[2] if len(rf) > 2 else 'hidden'
                                                col = (245, 120, 20) if rtype == 'fakeout' else (60, 110, 220)
                                                trigger_square_flash(client_state, rr, rc, col, rtype)
                                            gs['reveal_flashes'] = []
                                        gs['hidden_mode'] = False
                                        client_state['turn_start_snapshot'] = copy.deepcopy(gs)
                                        client_state['turn_history'].append(copy.deepcopy(gs))
                                        client_state['history_index'] = len(client_state['turn_history']) - 1
                                else:
                                    if dm_copy:
                                        await websocket.send(json.dumps({"type": "action", "action": "end_turn", "draft_moves": dm_copy}))
                                    else:
                                        await websocket.send(json.dumps({"type": "action", "action": "end_turn"}))
                                client_state['drafting'] = False
                                client_state['draft_moves'] = []
                                client_state['selected'] = None
                                client_state['legal_sq'] = []
                            elif btns.get('next') and btns['next'].collidepoint((mx, my)):
                                h_active = client_state.get('history_active', False)
                                
                                base_next = not h_active and gs['turn'] == active_color and (gs['normal_done'] or gs.get('hidden_count', 0) > 0)
                                if not client_state.get('drafting'):
                                    temp_next_en = base_next
                                else:
                                    dm = client_state.get('draft_moves', [])
                                    if dm and dm[-1].get('type') != 'end_turn':
                                        temp_next_en = base_next
                                    else:
                                        temp_next_en = False

                                if client_state.get('draft_moves'):
                                    has_real_draft = check_has_real_draft(client_state['draft_moves'])
                                    if not has_real_draft:
                                        temp_next_en = False
                                if not temp_next_en:
                                    continue

                                if not client_state.get('disable_undo_placeholder') and not gs.get('disable_undo_placeholder'):
                                    play_sound('next')

                                if (gs['normal_done'] or gs.get('hidden_count', 0) > 0):
                                    save_for_undo(client_state, gs)
                                    if client_state.get('drafting'):
                                        dm = client_state.get('draft_moves', [])
                                        if dm and dm[-1].get('type') != 'end_turn':
                                            dm.append({'type': 'end_turn'})
                                            client_state['draft_moves'] = dm
                                    client_state['drafting'] = True
                                    client_state['draft_hidden'] = False
                                    client_state['draft_fakeout'] = False
                                    if 'draft_moves' not in client_state or client_state['draft_moves'] is None:
                                        client_state['draft_moves'] = []
                        continue

                    if mx < BOARD_PX and my < BOARD_PX:
                        now = time.time()
                        cc2 = mx // SQ
                        rr2 = my // SQ
                        r = 7 - rr2 if client_state['flipped'] else rr2
                        c = 7 - cc2 if client_state['flipped'] else cc2
                        prev_time = client_state.get('last_sq_click_time', 0.0)
                        prev_coord = client_state.get('last_sq_click_coord')
                        
                        client_state['last_sq_click_time'] = now
                        client_state['last_sq_click_coord'] = (r, c)
                        
                        if gs.get('disable_undo_placeholder', False) and prev_coord == (r, c) and (now - prev_time) <= 0.35:
                            h_active = client_state.get('history_active', False)
                            q_key_dc = f'next_queue_{gs["turn"]}'
                            temp_end_en = not h_active and gs['turn'] == active_color and (gs['normal_done'] or gs.get('hidden_count', 0) > 0 or gs.get(q_key_dc))
                            if client_state.get('draft_moves'):
                                temp_end_en = check_draft_endable(client_state['draft_moves'], temp_end_en)
                                    
                            if temp_end_en:
                                if 'shockwaves' not in client_state:
                                    client_state['shockwaves'] = []
                                sq_center_x = (cc2 * SQ) + SQ // 2
                                sq_center_y = (rr2 * SQ) + SQ // 2
                                client_state['shockwaves'].append({
                                    'cx': sq_center_x,
                                    'cy': sq_center_y,
                                    't': 0.0,
                                    'duration': 0.6,
                                    'max_radius': BOARD_PX * 1.4
                                })
                                spawn_particles(sq_center_x, sq_center_y, (50, 245, 105), 30, client_state, size=4.0, speed=240, life=0.5)
                                play_sound('end')
                                
                                dm = client_state.get('draft_moves', [])
                                dm_copy = []
                                for m in dm:
                                    m_dict = copy.deepcopy(m)
                                    if 'type' not in m_dict:
                                        m_dict['type'] = 'move'
                                    dm_copy.append(m_dict)
                                if dm_copy and dm_copy[-1].get('type') != 'end_turn':
                                    dm_copy.append({'type': 'end_turn'})
                                    
                                if is_local:
                                    q_key_sq = f'next_queue_{gs["turn"]}'
                                    if gs['normal_done'] or gs['hidden_count'] > 0 or gs.get(q_key_sq):
                                        save_for_undo(client_state, gs)
                                        
                                        if gs.get('normal_done') or gs.get('hidden_count', 0) > 0:
                                            # Manual move was made
                                            next_a = get_next_turn_from_queue(gs, gs['turn'])
                                            if next_a:
                                                if compare_turns(gs.get('current_turn_actions', []), next_a):
                                                    gs['pts'][gs['turn']] += 1
                                                else:
                                                    gs['pts'][gs['turn']] -= 1
                                                pop_next_turn_from_queue(gs, gs['turn'])

                                            if dm_copy and dm:
                                                if q_key_sq not in gs: gs[q_key_sq] = []
                                                gs[q_key_sq].extend(dm_copy)
                                            end_turn(gs)
                                        else:
                                            # No manual move
                                            if dm_copy and dm:
                                                if q_key_sq not in gs: gs[q_key_sq] = []
                                                gs[q_key_sq].extend(dm_copy)
                                            
                                            if gs.get(q_key_sq):
                                                process_next_queues(gs)
                                            else:
                                                end_turn(gs)
                                        if in_check(get_absolute_board(gs), gs['turn']):
                                            play_sound('check')
                                        if gs.get('reveal_flashes'):
                                            for rf in gs['reveal_flashes']:
                                                rr, rc = rf[0], rf[1]
                                                rtype = rf[2] if len(rf) > 2 else 'hidden'
                                                col = (245, 120, 20) if rtype == 'fakeout' else (60, 110, 220)
                                                trigger_square_flash(client_state, rr, rc, col, rtype)
                                            gs['reveal_flashes'] = []
                                        gs['hidden_mode'] = False
                                        client_state['turn_start_snapshot'] = copy.deepcopy(gs)
                                        client_state['turn_history'].append(copy.deepcopy(gs))
                                        client_state['history_index'] = len(client_state['turn_history']) - 1
                                else:
                                    if dm_copy:
                                        await websocket.send(json.dumps({"type": "action", "action": "end_turn", "draft_moves": dm_copy}))
                                    else:
                                        await websocket.send(json.dumps({"type": "action", "action": "end_turn"}))
                                client_state['drafting'] = False
                                client_state['draft_moves'] = []
                                client_state['selected'] = None
                                client_state['legal_sq'] = []
                                continue

                        if client_state.get('history_active', False): continue
                        if gs['turn'] != active_color: continue
                        if not gs.get('fakeout_active', False):
                            if (gs['normal_done'] or gs.get('hidden_count', 0) > 0) and not client_state.get('drafting'): continue
                            if gs['hidden_mode'] and not can_afford(gs): continue

                        cc2 = mx // SQ
                        rr2 = my // SQ
                        r = 7 - rr2 if client_state['flipped'] else rr2
                        c = 7 - cc2 if client_state['flipped'] else cc2
                        curr_dgs = get_draft_state(gs, client_state.get('draft_moves', [])) if client_state.get('drafting') else gs
                        tb = get_true_board(curr_dgs, gs['turn'])

                        p_on_sq = tb[r][c]
                        if p_on_sq is not None and pc(p_on_sq) == gs['turn']:
                            if client_state.get('selected') == (r, c):
                                client_state['selected'] = None
                                client_state['legal_sq'] = []
                                play_sound('select')
                                continue
                            gs_temp = copy.copy(gs)
                            gs_temp['drafting_active'] = client_state.get('drafting', False)
                            if client_state.get('drafting'):
                                gs_temp['fakeout_active'] = client_state.get('draft_fakeout', False)
                                gs_temp['hidden_mode'] = client_state.get('draft_hidden', False)
                            sel, legs = get_ui_selection(gs_temp, r, c, draft_moves=client_state.get('draft_moves', []))
                            if sel is not None:
                                client_state['selected'] = sel
                                client_state['legal_sq'] = legs
                                play_sound('select')
                                if client_state.get('disable_undo_placeholder', gs.get('disable_undo_placeholder', False)):
                                    client_state['is_dragging_gesture'] = True
                                    client_state['drag_piece_sq'] = (r, c)
                                    client_state['drag_piece_name'] = p_on_sq
                                    client_state['drag_pos'] = (mx, my)
                                    client_state['gesture_timer'] = 0.0
                                    client_state['hidden_triggered'] = False
                                    client_state['fakeout_triggered'] = False
                                continue

                        if client_state['selected']:
                            sr, sc = client_state['selected']
                            target_p = tb[r][c]
                            
                            # --- ICE KING CHECK (Standard) ---
                            if target_p and pt(tb[sr][sc]) == 'K' and pc(target_p) == gs['turn'] and pt(target_p) != 'K' and gs.get('disable_undo_placeholder', False) and gs.get('ice_king_enabled', False):
                                res = ice_king_interaction(gs, sr, sc, r, c)
                                if res:
                                    if res == 'frozen':
                                        trigger_freeze_effect(client_state, gs, r, c)
                                    else:
                                        trigger_unfreeze_effect(client_state, gs, r, c)
                                    
                                    if not is_local:
                                        await websocket.send(json.dumps({
                                            "type": "action", "action": "ice_king",
                                            "kr": sr, "kc": sc, "tr": r, "tc": c
                                        }))
                                    
                                    client_state['selected'] = None
                                    client_state['legal_sq'] = []
                                    continue
                            # --- END ICE KING CHECK ---

                            if target_p and pt(tb[sr][sc]) == 'K' and pt(target_p) == 'R' and pc(
                                    target_p) == gs['turn']:
                                c = 6 if c == 7 else 2

                        if client_state['selected']:
                            if (r, c) in client_state['legal_sq']:
                                sr, sc = client_state['selected']
                                conflict = check_conflict(gs, sr, sc, r, c)
                                if conflict:
                                    if is_local:
                                        save_for_undo(client_state, gs)
                                        kind, cr2, cc3 = conflict
                                        if kind == 'src':
                                            gs['board'][cr2][cc3] = None
                                            my_cap = gs['captured_w'] if gs['turn'] == 'w' else gs['captured_b']
                                            my_cap.discard((cr2, cc3))
                                            ghost_type = 'hidden'
                                            
                                            for h_dict in [gs.get('hidden_w', {}), gs.get('hidden_b', {})]:
                                                to_remove = []
                                                for tp, val in list(h_dict.items()):
                                                    pub_pos = val.pub_pos
                                                    is_f = val.is_fakeout
                                                    if pub_pos == (cr2, cc3) or tp == (cr2, cc3):
                                                         if is_f:
                                                             ghost_type = 'fakeout'
                                                         deactivate_plies(gs, val.plies)
                                                         if is_f:
                                                             to_remove.append(tp)
                                                for tp in to_remove:
                                                    h_dict.pop(tp, None)
                                            if ghost_type == 'fakeout':
                                                gs['log'].append(f"SYS_FAKEOUT|Peça desapareceu em {alg(cc3, cr2)}!")
                                            else:
                                                gs['log'].append(f"SYS_HIDDEN|Peça desapareceu em {alg(cc3, cr2)}!")
                                            if 'reveal_flashes' not in gs:
                                                gs['reveal_flashes'] = []
                                            gs['reveal_flashes'].append([cr2, cc3, ghost_type])
                                        elif kind == 'dst':
                                            enemy_hid = gs['hidden_b'] if gs['turn'] == 'w' else gs['hidden_w']
                                            val = enemy_hid.pop((cr2, cc3), None)
                                            if val:
                                                pub_pos, hp = val.pub_pos, val.piece
                                                is_f = val.is_fakeout
                                                if pub_pos: gs['board'][pub_pos[0]][pub_pos[1]] = None
                                                gs['board'][cr2][cc3] = hp
                                                enemy_cap = gs['captured_w'] if gs['turn'] == 'w' else gs['captured_b']
                                                enemy_cap.discard((cr2, cc3))
                                                if is_f:
                                                    gs['log'].append(f"SYS_FAKEOUT|Peça revelada em {alg(cc3, cr2)}!")
                                                else:
                                                    gs['log'].append(f"SYS_HIDDEN|Peça revelada em {alg(cc3, cr2)}!")
                                                
                                                deactivate_plies(gs, val.plies)
                                                if 'reveal_flashes' not in gs:
                                                    gs['reveal_flashes'] = []
                                                gs['reveal_flashes'].append([cr2, cc3, 'fakeout' if is_f else 'hidden'])
                                        
                                        if gs.get('reveal_flashes'):
                                            for rf in gs['reveal_flashes']:
                                                rr, rc = rf[0], rf[1]
                                                rtype = rf[2] if len(rf) > 2 else 'hidden'
                                                col = (245, 120, 20) if rtype == 'fakeout' else (60, 110, 220)
                                                trigger_square_flash(client_state, rr, rc, col, rtype)
                                            gs['reveal_flashes'] = []
                                        
                                        client_state['selected'] = None
                                        client_state['legal_sq'] = []
                                    else:
                                        await websocket.send(json.dumps(
                                            {"type": "action", "action": "conflict_resolve",
                                             "conflict": conflict}))
                                        client_state['selected'] = None
                                        client_state['legal_sq'] = []
                                else:
                                    promo = None
                                    p = tb[sr][sc]
                                    if pt(p) == 'P' and r in (0, 7):
                                        promo = await ask_promo(screen, fonts, active_color, websocket, client_state)

                                    if client_state.get('drafting'):
                                        d_moves = client_state.get('draft_moves', [])
                                        dgs = get_draft_state(gs, d_moves)
                                        dgs['fakeout_active'] = client_state.get('draft_fakeout', False)
                                        dgs['hidden_mode'] = client_state.get('draft_hidden', False)
                                        legals = legal(dgs, sr, sc)
                                        if (r, c) in legals:
                                            save_for_undo(client_state, gs)
                                            is_hid = client_state.get('draft_hidden', False)
                                            is_fake = client_state.get('draft_fakeout', False)
                                            d_moves.append({
                                                'type': 'move',
                                                'fr': sr, 'fc': sc, 'tr': r, 'tc': c,
                                                'hidden': is_hid,
                                                'fakeout': is_fake,
                                                'promo': promo,
                                                'drafted_turn': (gs['turn_count'] + 1) // 2
                                            })
                                            client_state['draft_moves'] = d_moves
                                            play_sound('next_move')
                                            client_state['draft_hidden'] = False
                                            client_state['draft_fakeout'] = False
                                        client_state['selected'] = None
                                        client_state['legal_sq'] = []
                                    else:
                                        if is_local:
                                            save_for_undo(client_state, gs)
                                            old_game_over = gs.get('game_over', False)
                                            old_last = gs.get('last_move')
                                            n_cap_w = len(gs.get('captured_w', []))
                                            n_cap_b = len(gs.get('captured_b', []))
                                            
                                            has_captured_piece_on_square = False
                                            if gs.get('board') and 0 <= r < 8 and 0 <= c < 8:
                                                has_captured_piece_on_square = gs['board'][r][c] is not None
                                                
                                            is_fakeout = gs.get('fakeout_active', False)
                                            res = exec_move(gs, sr, sc, r, c, hidden_move=gs.get('hidden_mode', False), promo=promo)
                                            if res:
                                                if 'current_turn_actions' not in gs: gs['current_turn_actions'] = []
                                                gs['current_turn_actions'].append({
                                                    'type': 'move', 'fr': sr, 'fc': sc, 'tr': r, 'tc': c,
                                                    'promo': promo, 'hidden': gs.get('hidden_mode', False),
                                                    'fakeout': is_fakeout
                                                })
                                            
                                            new_last = gs.get('last_move')
                                            
                                            cap_w = len(gs.get('captured_w', [])) > n_cap_w
                                            cap_b = len(gs.get('captured_b', [])) > n_cap_b
                                            
                                            if res and old_last != new_last and new_last:
                                                nfr, nfc, ntr, ntc = new_last
                                                
                                                is_capture_by_log = False
                                                if gs.get('log'):
                                                    norm_last_log = gs['log'][-1].lower()
                                                    if "capturado" in norm_last_log or "capturada" in norm_last_log:
                                                        is_capture_by_log = True
                                                    elif 'x' in norm_last_log:
                                                        without_xeque = norm_last_log.replace("xeque", "")
                                                        if 'x' in without_xeque:
                                                            is_capture_by_log = True
                                                
                                                is_capture = cap_w or cap_b or has_captured_piece_on_square or res == "ghost_capture" or is_capture_by_log
                                                
                                                p_anim = gs['board'][ntr][ntc]
                                                if not p_anim:
                                                    for h_dict in [gs.get('hidden_w', {}), gs.get('hidden_b', {})]:
                                                        if (ntr, ntc) in h_dict:
                                                            target_val = h_dict[(ntr, ntc)]
                                                            p_anim = target_val.piece if hasattr(target_val, 'piece') else target_val[1]
                                                            break
                                                if p_anim:
                                                    trigger_piece_anim(client_state, p_anim, nfr, nfc, ntr, ntc, gs.get('hidden_mode', False), gs.get('fakeout_active', False), is_capture)
                                                
                                                is_fakeout = gs.get('fakeout_used', False)
                                                is_shadow = gs.get('hidden_count', 0) > 0
                                                if gs.get('game_over', False) and not old_game_over:
                                                    play_sound('game_over')
                                                elif is_capture: play_sound('capture')
                                                else: play_sound('move')
                                                
                                            if res == "ghost_capture":
                                                gc_type = gs.get('ghost_capture_type', 'standard')
                                                col = (245, 120, 20) if gc_type == 'fakeout' else (60, 110, 220)
                                                trigger_square_flash(client_state, r, c, col, gc_type)
                                                gs['ghost_capture_flash'] = None
                                                gs['ghost_capture_type'] = None

                                            if gs.get('reveal_flashes'):
                                                for r_fl in gs['reveal_flashes']:
                                                    rr, rc = r_fl[0], r_fl[1]
                                                    rtype = r_fl[2] if len(r_fl) > 2 else 'hidden'
                                                    col = (245, 120, 20) if rtype == 'fakeout' else (60, 110, 220)
                                                    trigger_square_flash(client_state, rr, rc, col, rtype)
                                                gs['reveal_flashes'] = []

                                            client_state['selected'] = None
                                            client_state['legal_sq'] = []
                                            gs['hidden_mode'] = False
                                        else:
                                            move_cmd = {
                                                "type": "action", "action": "move",
                                                "fr": sr, "fc": sc, "tr": r, "tc": c, "promo": promo
                                            }
                                            await websocket.send(json.dumps(move_cmd))
                                            client_state['selected'] = None
                                            client_state['legal_sq'] = []
                            else:
                                gs_temp = copy.copy(gs)
                                gs_temp['drafting_active'] = client_state.get('drafting', False)
                                if client_state.get('drafting'):
                                    gs_temp['fakeout_active'] = client_state.get('draft_fakeout', False)
                                    gs_temp['hidden_mode'] = client_state.get('draft_hidden', False)
                                sel, legs = get_ui_selection(gs_temp, r, c, draft_moves=client_state.get('draft_moves', []))
                                if sel is not None:
                                    client_state['selected'] = sel
                                    client_state['legal_sq'] = legs
                                    play_sound('select')
                                else:
                                    client_state['selected'] = None
                                    client_state['legal_sq'] = []
                        else:
                            gs_temp = copy.copy(gs)
                            gs_temp['drafting_active'] = client_state.get('drafting', False)
                            if client_state.get('drafting'):
                                gs_temp['fakeout_active'] = client_state.get('draft_fakeout', False)
                                gs_temp['hidden_mode'] = client_state.get('draft_hidden', False)
                            sel, legs = get_ui_selection(gs_temp, r, c, draft_moves=client_state.get('draft_moves', []))
                            if sel is not None:
                                client_state['selected'] = sel
                                client_state['legal_sq'] = legs
                                play_sound('select')
                            # do not clear selection if clicking empty square when not selected

        if not running:
            break

        screen.fill(BG)

        if app_state == "INTRO_ANIM":
            screen.fill((0, 0, 0))
            if 'intro_start' not in client_state:
                client_state['intro_start'] = pygame.time.get_ticks()
            t_ms = pygame.time.get_ticks() - client_state['intro_start']
            cx, cy = WIN_W // 2, WIN_H // 2
            
            p_str = 'wP'
            img = IMAGES.get(p_str)
            if img:
                base_img = pygame.transform.smoothscale(img, (SQ, SQ))
            else:
                base_img = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                t_surf = fonts['piece'].render(GLYPHS[p_str], True, (255, 255, 255))
                base_img.blit(t_surf, t_surf.get_rect(center=(SQ//2, SQ//2)))

            if t_ms < 1500:
                p = t_ms / 1500.0
                alpha = int(255 * p)
                scale = 1.3 - 0.3 * p
                size = int(SQ * scale)
                s_img = pygame.transform.smoothscale(base_img, (size, size))
                s_img.set_alpha(alpha)
                screen.blit(s_img, s_img.get_rect(center=(cx, cy)))

            elif t_ms < 3500:
                s_img = pygame.transform.smoothscale(base_img, (SQ, SQ))
                screen.blit(s_img, s_img.get_rect(center=(cx, cy)))
                
                bar_w = 80
                bar_h = 2
                bx = cx - bar_w // 2
                by = cy + SQ // 2 + 10
                p_bar = (t_ms - 1500) / 2000.0
                draw_rect_aa(screen, (30, 30, 35), pygame.Rect(bx, by, bar_w, bar_h))
                draw_rect_aa(screen, (240, 240, 245), pygame.Rect(bx, by, int(bar_w * p_bar), bar_h))

            elif t_ms < 5300:
                if not client_state.get('intro_hidden_snd'):
                    play_sound('hidden')
                    client_state['intro_hidden_snd'] = True

                s_img = pygame.transform.smoothscale(base_img, (SQ, SQ))
                
                radius = (SQ // 2) + int(5 * math.sin(pygame.time.get_ticks() / 100.0))
                glow_surf = pygame.Surface((SQ + 60, SQ + 60), pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, (20, 80, 255, 120), (SQ // 2 + 30, SQ // 2 + 30), radius + 18)
                pygame.draw.circle(glow_surf, (40, 110, 255, 200), (SQ // 2 + 30, SQ // 2 + 30), radius + 5)
                pygame.draw.circle(glow_surf, (80, 150, 255, 255), (SQ // 2 + 30, SQ // 2 + 30), radius - 4)
                screen.blit(glow_surf, (cx - SQ // 2 - 30, cy - SQ // 2 - 30))

                screen.blit(s_img, s_img.get_rect(center=(cx, cy)))

            elif t_ms < 5500:
                flash_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
                flash_alpha = int(255 * ((t_ms - 5300) / 200.0))
                flash_alpha = max(0, min(255, flash_alpha))
                flash_surf.fill((255, 255, 255, flash_alpha))
                screen.blit(flash_surf, (0, 0))

            if t_ms >= 5500:
                app_state = "MENU"

        if app_state == "MENU":
            if 'menu_anim_t' not in client_state or client_state.get('menu_anim_state') != app_state:
                client_state['menu_anim_t'] = pygame.time.get_ticks()
                client_state['menu_anim_state'] = app_state
                client_state['menu_anim_flash'] = False

            m_ms = pygame.time.get_ticks() - client_state['menu_anim_t']
            
            cx = WIN_W // 2
            cy = menu_y_start - 160
            
            if not client_state['menu_anim_flash'] and m_ms > 200:
                play_sound('move')
                spawn_particles(cx, cy, (60, 110, 220), 16, client_state, size=3.5, speed=120, life=0.35)
                client_state['menu_anim_flash'] = True
               
            if 200 < m_ms < 700:
                flash_alpha = max(0, int(180 * (1.0 - (m_ms - 200) / 500.0)))
                f_surf = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                f_surf.fill((60, 110, 220, flash_alpha))
                screen.blit(f_surf, (cx - SQ//2, cy - SQ//2))
            
            p_str = 'wK'
            if p_str in IMAGES:
                k_img = pygame.transform.smoothscale(IMAGES[p_str], (SQ, SQ))
            else:
                k_img = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                k_surf = fonts['piece'].render(GLYPHS[p_str], True, (255, 255, 255))
                k_img.blit(k_surf, k_surf.get_rect(center=(SQ//2, SQ//2)))

            if m_ms > 200:
                anim_dur = 400
                progress = min(1.0, (m_ms - 200) / anim_dur)
                k_alpha = int(255 * progress)
                current_y = (cy - 40) + 40 * progress
                
                if progress < 1.0:
                    trail = k_img.copy()
                    trail.fill((255, 255, 255, 120), special_flags=pygame.BLEND_RGBA_MULT)
                    for step in range(1, 4):
                        prev_y = (cy - 40) + 40 * max(0, progress - step*0.1)
                        if prev_y < current_y:
                            trail_alpha = int(120 * (1.0 - step/4.0) * progress)
                            trail.set_alpha(trail_alpha)
                            screen.blit(trail, trail.get_rect(center=(cx, int(prev_y))))
                
                drawn_k = k_img.copy()
                drawn_k.set_alpha(k_alpha)
                
                if progress >= 1.0:
                    radius = (SQ // 2) + int(5 * math.sin(pygame.time.get_ticks() / 100.0))
                    glow_surf = pygame.Surface((SQ + 60, SQ + 60), pygame.SRCALPHA)
                    pygame.draw.circle(glow_surf, (20, 80, 255, 120), (SQ // 2 + 30, SQ // 2 + 30), radius + 18)
                    pygame.draw.circle(glow_surf, (40, 110, 255, 200), (SQ // 2 + 30, SQ // 2 + 30), radius + 5)
                    pygame.draw.circle(glow_surf, (80, 150, 255, 255), (SQ // 2 + 30, SQ // 2 + 30), radius - 4)
                    screen.blit(glow_surf, (cx - SQ // 2 - 30, int(current_y) - SQ // 2 - 30))
                
                screen.blit(drawn_k, drawn_k.get_rect(center=(cx, int(current_y))))
                
            if client_state.get('particles'):
                for p in client_state['particles']:
                    alpha = max(0, min(255, int(255 * (p['life'] / p['max_life']))))
                    size = max(1, int(p['size'] * (p['life'] / p['max_life'])))
                    psurf = pygame.Surface((size*2, size*2), pygame.SRCALPHA)
                    pygame.draw.circle(psurf, (*p['color'], alpha), (size, size), size)
                    screen.blit(psurf, (int(p['x'] - size), int(p['y'] - size)))

            draw_text_center(screen, "Hidden Chess", title_font, T_MAIN, menu_y_start - 80)
            draw_text_center(screen, "v1.5.2.1", fonts['small'], T_DIM, menu_y_start - 40)
            
            draw_fancy_btn(screen, "Criar Jogo", fonts['big'], BTN_N, BTN_H, BTN_TXT, btn_create, is_hover=btn_create.collidepoint(mouse))
            draw_fancy_btn(screen, "Entrar no Jogo", fonts['big'], BTN_N, BTN_H, BTN_TXT, btn_join, is_hover=btn_join.collidepoint(mouse))
            draw_fancy_btn(screen, "Jogar Localmente", fonts['big'], BTN_N, BTN_H, BTN_TXT, btn_local, is_hover=btn_local.collidepoint(mouse))
            draw_fancy_btn(screen, "Modo Teste", fonts['big'], BTN_N, BTN_H, BTN_TXT, btn_test, is_hover=btn_test.collidepoint(mouse))
            draw_fancy_btn(screen, "Replays", fonts['big'], BTN_N, BTN_H, BTN_TXT, btn_replays, is_hover=btn_replays.collidepoint(mouse))

            if error_msg:
                if 'last_error_msg' not in client_state or client_state['last_error_msg'] != error_msg:
                    client_state['last_error_msg'] = error_msg
                    client_state['error_time'] = pygame.time.get_ticks()
                elif pygame.time.get_ticks() - client_state.get('error_time', 0) > 4000:
                    error_msg = ""
                    client_state['last_error_msg'] = ""
                
                if error_msg:
                    draw_text_center(screen, error_msg, fonts['small'], T_RED, menu_y_start + 350)
                
            draw_text_center(screen, "By Loopyin", fonts['small'], (150, 150, 150), WIN_H - 30)

            if 'intro_start' in client_state:
                t_ms = pygame.time.get_ticks() - client_state['intro_start']
                if 5500 <= t_ms < 6500:
                    flash_alpha = int(255 * (1.0 - (t_ms - 5500) / 1000.0))
                    flash_alpha = max(0, min(255, flash_alpha))
                    if flash_alpha > 0:
                        flash_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
                        flash_surf.fill((255, 255, 255, flash_alpha))
                        screen.blit(flash_surf, (0, 0))

        elif app_state == "CONNECTING":
            draw_text_center(screen, "CONECTANDO AO SERVIDOR...", fonts['big'], T_MAIN, WIN_H // 2 - 25)
            draw_text_center(screen, "Por favor, aguarde.", fonts['small'], T_DIM, WIN_H // 2 + 25)

        elif app_state == "JOINING":
            draw_text_center(screen, "DIGITE O CÓDIGO DA SALA:", fonts['big'], T_MAIN, WIN_H // 2 - 80)
            box_w = 160
            input_rect = pygame.Rect(WIN_W // 2 - box_w // 2, WIN_H // 2 - 40, box_w, 60)
            client_state['join_input_rect'] = input_rect
            
            draw_rect_aa(screen, (40, 40, 45), input_rect, 5)
            draw_rect_aa(screen, (80, 120, 220), input_rect, 5, 2)
            draw_text_center(screen, input_text, title_font, (255, 255, 255), input_rect.centery)

            btn_gap = 10
            bw = 100
            bx_center = WIN_W // 2
            
            # Apagar btn
            btn_apagar = pygame.Rect(bx_center - bw // 2 - bw - btn_gap, WIN_H // 2 + 65, bw, 40)
            is_hover_a = btn_apagar.collidepoint(mouse)
            has_text = len(input_text) > 0
            draw_fancy_btn(screen, "Apagar", fonts['small'], (120, 50, 50), (150, 60, 60), (255, 255, 255), btn_apagar, is_hover=has_text and is_hover_a, is_disabled=not has_text, custom_radius=6)
            client_state['join_btn_back'] = btn_apagar
            
            # Entrar btn
            btn_entrar = pygame.Rect(bx_center - bw // 2, WIN_H // 2 + 65, bw, 40)
            is_hover_e = btn_entrar.collidepoint(mouse)
            can_enter = len(input_text) == 4
            draw_fancy_btn(screen, "Entrar", fonts['small'], (30, 110, 200), (50, 130, 230), (255, 255, 255), btn_entrar, is_hover=can_enter and is_hover_e, is_disabled=not can_enter, custom_radius=6)
            client_state['join_btn_enter'] = btn_entrar

            # Voltar btn
            btn_voltar = pygame.Rect(bx_center + bw // 2 + btn_gap, WIN_H // 2 + 65, bw, 40)
            draw_fancy_btn(screen, "Cancelar", fonts['small'], BTN_N, BTN_H, BTN_TXT, btn_voltar, is_hover=btn_voltar.collidepoint(mouse), custom_radius=6)
            client_state['join_btn_esc'] = btn_voltar

            keyboard_y = WIN_H // 2 + 130
            key_w = min(36, (WIN_W - 20) // 10 - 4)
            key_h = 44
            key_gap = 4
            rows = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
            client_state['join_kbt'] = {}
            for r, row in enumerate(rows):
                row_w = len(row) * key_w + (len(row) - 1) * key_gap
                start_x = WIN_W // 2 - row_w // 2
                for i, char in enumerate(row):
                    kval = pygame.Rect(start_x + i * (key_w + key_gap), keyboard_y + r * (key_h + key_gap), key_w, key_h)
                    client_state['join_kbt'][char] = kval
                    draw_fancy_btn(screen, char, fonts['small'], (50, 50, 55), (70, 70, 75), (255, 255, 255), kval, is_hover=kval.collidepoint(mouse), custom_radius=4)

        elif app_state == "LOBBY":
            draw_text_center(screen, "Aguardando", title_font, T_MAIN, WIN_H // 2 - 240)
            
            if client_state.get('is_local', False):
                pass
            else:
                room_type = "Online"
                draw_text_center(screen, room_type, fonts['small'], T_DIM, WIN_H // 2 - 200)
                draw_text_center(screen, f"CÓDIGO DA SALA: {client_state.get('room_code', '').upper()}", fonts['small'], T_BLUE, WIN_H // 2 - 175)
                if gs.get('opponent_joined', False):
                    draw_text_center(screen, "OPONENTE CONECTADO!", fonts['small'], (100, 220, 100), WIN_H // 2 - 150)
                else:
                    draw_text_center(screen, "AGUARDANDO OPONENTE...", fonts['small'], T_DIM, WIN_H // 2 - 150)

            play_btn_y = WIN_H // 2 - 20
            play_btn_rect = pygame.Rect((WIN_W - 240) // 2, play_btn_y, 240, 52)

            if client_state.get('my_color') == 'b':
                draw_text_center(screen, "AGUARDANDO O ANFITRIÃO INICIAR...", fonts['big'], (200, 200, 200), play_btn_rect.centery)
            else:
                can_play = client_state.get('is_local', False) or gs.get('opponent_joined', False)
                play_hover = play_btn_rect.collidepoint(mouse) and can_play
                if can_play:
                    draw_fancy_btn(screen, "Play", title_font, (35, 130, 65), (50, 160, 85), (255, 255, 255), play_btn_rect, is_hover=play_hover, custom_radius=8)
                else:
                    draw_fancy_btn(screen, "Play", title_font, (45, 45, 48), (45, 45, 48), (120, 120, 125), play_btn_rect, is_disabled=True, custom_radius=8)

            # Voltar botão
            back_btn_y = play_btn_y + 80
            back_btn_rect = pygame.Rect((WIN_W - 160) // 2, back_btn_y, 160, 44)
            draw_fancy_btn(screen, "Voltar", fonts['small'], (70, 70, 75), (90, 90, 95), (255, 255, 255), back_btn_rect, is_hover=back_btn_rect.collidepoint(mouse), custom_radius=6)

        elif app_state == "REPLAY_LIST":
            draw_text_center(screen, "REPLAYS SALVOS", title_font, T_MAIN, menu_y_start - 70)
            
            if 'replay_list' not in client_state:
                client_state['replay_list'] = load_replay_files()
                client_state['replay_page'] = 0

            replays = client_state['replay_list']
            page = client_state.get('replay_page', 0)
            items_per_page = 5
            start_idx = page * items_per_page
            end_idx = min(start_idx + items_per_page, len(replays))
            
            visible_replays = replays[start_idx:end_idx]
            
            current_y = menu_y_start - 20
            client_state['replay_rects'] = {}
            
            if not replays:
                draw_text_center(screen, "Nenhum replay salvo encontrado.", fonts['big'], T_DIM, WIN_H // 2 - 20)
            else:
                for idx, rep in enumerate(visible_replays):
                    rep_rect = pygame.Rect(WIN_W // 2 - 250, current_y, 500, 50)
                    is_hover = rep_rect.collidepoint(mouse)
                    
                    name_text = f"{rep['date']} - {rep['turns']} lances ({rep['color']})"
                    room = rep['data'].get('room_code', 'LOCAL')
                    if room != 'LOCAL':
                        name_text += f" [Sala: {room}]"
                    
                    b_col = (80, 120, 220) if is_hover else None
                    draw_fancy_btn(screen, name_text, fonts['big'], BTN_N, BTN_H, BTN_TXT, rep_rect, is_hover=is_hover, border_color=b_col, custom_radius=6)
                    
                    global_idx = start_idx + idx
                    client_state['replay_rects'][global_idx] = rep_rect
                    current_y += 65
            
            client_state['replay_prev_page'] = None
            client_state['replay_next_page'] = None
            
            if len(replays) > items_per_page:
                btn_py = current_y + 10
                if page > 0:
                    prev_rect = pygame.Rect(WIN_W // 2 - 250, btn_py, 120, 36)
                    is_h = prev_rect.collidepoint(mouse)
                    draw_fancy_btn(screen, "Anterior", fonts['small'], BTN_N, BTN_H, BTN_TXT, prev_rect, is_hover=is_h, custom_radius=6)
                    client_state['replay_prev_page'] = prev_rect
                
                if end_idx < len(replays):
                    next_rect = pygame.Rect(WIN_W // 2 + 130, btn_py, 120, 36)
                    is_h = next_rect.collidepoint(mouse)
                    draw_fancy_btn(screen, "Próximo", fonts['small'], BTN_N, BTN_H, BTN_TXT, next_rect, is_hover=is_h, custom_radius=6)
                    client_state['replay_next_page'] = next_rect
                    
                page_text = f"Pág {page + 1} de {((len(replays) - 1) // items_per_page) + 1}"
                draw_text_center(screen, page_text, fonts['small'], T_DIM, btn_py + 18)
            
            btn_voltar_replay = pygame.Rect(WIN_W // 2 - 100, WIN_H - 100, 200, 44)
            is_hover_voltar = btn_voltar_replay.collidepoint(mouse)
            b_col_voltar = (100, 100, 105) if is_hover_voltar else None
            draw_fancy_btn(screen, "Voltar", fonts['big'], BTN_N, BTN_H, BTN_TXT, btn_voltar_replay, is_hover=is_hover_voltar, border_color=b_col_voltar, custom_radius=6)
            client_state['replay_btn_back'] = btn_voltar_replay

        elif app_state == "REPLAY_VIEW":
            turn_hist = client_state.get('turn_history', [])
            active_idx = client_state.get('history_index', 0)
            if turn_hist:
                h_gs = turn_hist[active_idx]
            else:
                h_gs = gs
            
            draw_board(screen, h_gs, fonts, client_state, mouse)
            client_state['panel_btns'] = draw_panel(screen, h_gs, fonts, mouse, client_state)
            draw_sidebar(screen, h_gs, fonts, client_state, mouse)

        elif app_state == "PLAYING":
            registrar_proximo_lance_auto(gs, client_state)
            
            turn_hist = client_state.get('turn_history', [])
            active_idx = client_state.get('history_index', 0)
            history_active = len(turn_hist) > 0 and active_idx < len(turn_hist) - 1
            client_state['history_active'] = history_active

            if history_active:
                h_gs = turn_hist[active_idx]
            else:
                h_gs = gs

            if client_state.get('is_local', False):
                display_gs = get_cached_serialized_state(client_state, h_gs, h_gs['turn'])
                if not history_active:
                    client_state['my_color'] = gs['turn']
                draw_board(screen, display_gs, fonts, client_state, mouse)
                client_state['panel_btns'] = draw_panel(screen, display_gs, fonts, mouse, client_state)
                draw_sidebar(screen, display_gs, fonts, client_state, mouse)
            else:
                draw_board(screen, h_gs, fonts, client_state, mouse)
                client_state['panel_btns'] = draw_panel(screen, h_gs, fonts, mouse, client_state)
                draw_sidebar(screen, h_gs, fonts, client_state, mouse)

            # Log modal rendering removed

        pygame.display.flip()
        await asyncio.sleep(1 / FPS)

    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    asyncio.run(game_loop())
