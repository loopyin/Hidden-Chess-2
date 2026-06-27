import time
from gesture import default_gesture_state, normalize_gesture_state

GLYPHS = {
    'wK': '♚', 'wQ': '♛', 'wR': '♜', 'wB': '♝', 'wN': '♞', 'wP': '♟',
    'bK': '♚', 'bQ': '♛', 'bR': '♜', 'bB': '♝', 'bN': '♞', 'bP': '♟',
}
VALUES = {'P': 1, 'N': 3, 'B': 3, 'R': 5, 'Q': 9, 'K': 999}

INIT = [
    ['bR', 'bN', 'bB', 'bQ', 'bK', 'bB', 'bN', 'bR'],
    ['bP', 'bP', 'bP', 'bP', 'bP', 'bP', 'bP', 'bP'],
    [None] * 8, [None] * 8, [None] * 8, [None] * 8,
    ['wP', 'wP', 'wP', 'wP', 'wP', 'wP', 'wP', 'wP'],
    ['wR', 'wN', 'wB', 'wQ', 'wK', 'wB', 'wN', 'wR'],
]


from dataclasses import dataclass, field
from typing import List, Tuple, Optional

@dataclass
class PieceMetaModifier:
    pub_pos: Optional[Tuple[int, int]]
    piece: str
    path: List[Tuple[int, int]] = field(default_factory=list)
    is_fakeout: bool = False
    fakeout_path: List[Tuple[int, int]] = field(default_factory=list)
    plies: List[int] = field(default_factory=list)

    def to_tuple(self):
        return (self.pub_pos, self.piece, self.path, self.is_fakeout, self.fakeout_path, self.plies)

    def to_dict(self):
        return self.__dict__

def pc(p): return p[0] if p else None


def pt(p): return p[1] if p else None


def opp(c): return 'b' if c == 'w' else 'w'


def cpb(b): return [r[:] for r in b]


def cpcr(cr): return dict(cr)


def find_king(b, c):
    for r in range(8):
        for cc in range(8):
            if b[r][cc] == c + 'K': return (r, cc)
    return None


def attacked(b, row, col, by):
    for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
        r, c = row + dr, col + dc
        while 0 <= r < 8 and 0 <= c < 8:
            p = b[r][c]
            if p:
                if pc(p) == by:
                    t = pt(p)
                    d = abs(dr) == abs(dc)
                    if t == 'Q': return True
                    if t == 'R' and not d: return True
                    if t == 'B' and d: return True
                    if t == 'K' and abs(r - row) <= 1 and abs(c - col) <= 1: return True
                break
            r += dr
            c += dc
    for dr, dc in [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]:
        r, c = row + dr, col + dc
        if 0 <= r < 8 and 0 <= c < 8 and b[r][c] == by + 'N': return True
    pd = 1 if by == 'w' else -1
    for dc in [-1, 1]:
        r, c = row + pd, col + dc
        if 0 <= r < 8 and 0 <= c < 8 and b[r][c] == by + 'P': return True
    return False


def in_check(b, c):
    k = find_king(b, c)
    return attacked(b, k[0], k[1], opp(c)) if k else False


def pseudo(b, abs_b, row, fc, ep, cr):
    p = b[row][fc]
    if not p: return []
    c, t = pc(p), pt(p)
    mv = []

    def add(r, cc):
        if 0 <= r < 8 and 0 <= cc < 8: mv.append((r, cc))

    if t == 'P':
        d = -1 if c == 'w' else 1
        sr = 6 if c == 'w' else 1
        if not b[row + d][fc]:
            add(row + d, fc)
            if row == sr and not b[row + 2 * d][fc]: add(row + 2 * d, fc)
        for dc in [-1, 1]:
            nr, nc = row + d, fc + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                if b[nr][nc] and pc(b[nr][nc]) != c: add(nr, nc)
                if ep and ep == (nr, nc) and row == (3 if c == 'w' else 4): add(nr, nc)
    elif t == 'N':
        for dr, dc in [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]:
            nr, nc = row + dr, fc + dc
            if 0 <= nr < 8 and 0 <= nc < 8 and pc(b[nr][nc]) != c: add(nr, nc)
    elif t == 'K':
        for dr, dc in [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]:
            nr, nc = row + dr, fc + dc
            if 0 <= nr < 8 and 0 <= nc < 8 and pc(b[nr][nc]) != c: add(nr, nc)
        hr = 7 if c == 'w' else 0
        if row == hr and fc == 4:
            if cr.get(c + 'K') and not b[hr][5] and not b[hr][6]:
                if not attacked(abs_b, hr, 4, opp(c)) and not attacked(abs_b, hr, 5, opp(c)) and not attacked(abs_b, hr,
                                                                                                              6,
                                                                                                              opp(c)):
                    add(hr, 6)
            if cr.get(c + 'Q') and not b[hr][3] and not b[hr][2] and not b[hr][1]:
                if not attacked(abs_b, hr, 4, opp(c)) and not attacked(abs_b, hr, 3, opp(c)) and not attacked(abs_b, hr,
                                                                                                              2,
                                                                                                              opp(c)):
                    add(hr, 2)
    else:
        dirs = []
        if t in ('R', 'Q'): dirs += [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if t in ('B', 'Q'): dirs += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        for dr, dc in dirs:
            r, cc = row + dr, fc + dc
            while 0 <= r < 8 and 0 <= cc < 8:
                if b[r][cc]:
                    if pc(b[r][cc]) != c: add(r, cc)
                    break
                add(r, cc)
                r += dr
                cc += dc
    return mv


def check_fakeout_collision(c, fr, fc, tr, tc, p, gs):
    abs_b = get_absolute_board(gs)
    target_piece = abs_b[tr][tc]
    if target_piece is not None and pc(target_piece) == opp(c):
        return True

    enemy_hidden = gs['hidden_b'] if c == 'w' else gs['hidden_w']
    for t_pos, h_val in enemy_hidden.items():
        if h_val.pub_pos == (tr, tc):
            return True

    def get_dir(a, b):
        return 0 if a == b else (1 if b > a else -1)

    t = pt(p)
    if t == 'K' and abs(fc - tc) == 2:
        step = 1 if tc > fc else -1
        check_cols = [fc + step, fc + 2 * step]
        if tc == 2:
            check_cols.append(1)
        for col in check_cols:
            if (fr, col) in enemy_hidden:
                return True
    elif t not in ('N', 'K'):
        dr, dc = get_dir(fr, tr), get_dir(fc, tc)
        r, cc = fr + dr, fc + dc
        while 0 <= r < 8 and 0 <= cc < 8:
            if (r, cc) in enemy_hidden:
                return True
            if (r, cc) == (tr, tc):
                break
            r += dr
            cc += dc
    else:
        if (tr, tc) in enemy_hidden:
            return True

    if t == 'P' and fc != tc:
        return True

    return False


def legal(gs, row, fc):
    p_raw = gs['board'][row][fc]
    if not p_raw: return []
    piece_color = pc(p_raw)
    if gs.get('white_controls_black', False):
        c = piece_color
    else:
        c = gs['turn']
        
    if (row, fc) in gs.get('frozen_pieces', set()):
        return []
    tb = get_true_board(gs, c)
    abs_b = get_absolute_board(gs)
    p = tb[row][fc]
    res = []
    if not p: return res
    
    my_hidden = gs['hidden_w'] if c == 'w' else gs['hidden_b']
    if gs.get('fakeout_active') and (row, fc) in my_hidden:
        val = my_hidden[(row, fc)]
        pub_pos = val.pub_pos
        if pub_pos:
            fake_tb = cpb(tb)
            fake_tb[pub_pos[0]][pub_pos[1]] = p
            fake_tb[row][fc] = None

            fake_abs = cpb(abs_b)
            fake_abs[pub_pos[0]][pub_pos[1]] = p
            fake_abs[row][fc] = None

            for tr, tc in pseudo(fake_tb, fake_abs, pub_pos[0], pub_pos[1], gs['ep'], gs['cr']):
                target = fake_abs[tr][tc]
                if target and pt(target) == 'K': continue

                if check_fakeout_collision(c, pub_pos[0], pub_pos[1], tr, tc, p, gs):
                    continue

                nb = cpb(fake_abs)
                ncr = cpcr(gs['cr'])
                do_move(nb, pub_pos[0], pub_pos[1], tr, tc, gs['ep'], ncr, 'Q')
                nb_check = cpb(nb)
                for hr, hc in my_hidden:
                    ghost = gs['board'][hr][hc]
                    if ghost and pc(ghost) == opp(c):
                        nb_check[hr][hc] = ghost
                if not in_check(nb_check, c):
                    res.append((tr, tc))
            return res

    for tr, tc in pseudo(tb, abs_b, row, fc, gs['ep'], gs['cr']):
        target = abs_b[tr][tc]
        if target and pt(target) == 'K': continue

        if gs.get('fakeout_active'):
            if check_fakeout_collision(c, row, fc, tr, tc, p, gs):
                continue

        nb = cpb(abs_b)
        ncr = cpcr(gs['cr'])
        do_move(nb, row, fc, tr, tc, gs['ep'], ncr, 'Q')
        nb_check = cpb(nb)
        for hr, hc in my_hidden:
            ghost = gs['board'][hr][hc]
            if ghost and pc(ghost) == opp(c):
                nb_check[hr][hc] = ghost
        if not in_check(nb_check, c):
            res.append((tr, tc))
    return res


def all_legal(gs):
    c = gs['turn']
    tb = get_true_board(gs, c)
    mv = []
    for r in range(8):
        for cc in range(8):
            if pc(tb[r][cc]) == c:
                for m in legal(gs, r, cc): mv.append((r, cc) + m)
    return mv


def do_move(b, fr, fc, tr, tc, ep, cr, promo):
    p = b[fr][fc]
    c, t = pc(p), pt(p)
    cap = b[tr][tc]

    if cap and pt(cap) == 'R':
        if tr == 7 and tc == 0: cr['wQ'] = False
        if tr == 7 and tc == 7: cr['wK'] = False
        if tr == 0 and tc == 0: cr['bQ'] = False
        if tr == 0 and tc == 7: cr['bK'] = False
    b[tr][tc] = p
    b[fr][fc] = None
    if t == 'P' and ep and (tr, tc) == ep: b[fr][tc] = None
    if t == 'P' and tr in (0, 7): b[tr][tc] = c + (promo or 'Q')
    if t == 'K':
        if fc == 4 and tc == 6: b[tr][5] = b[tr][7]; b[tr][7] = None
        if fc == 4 and tc == 2: b[tr][3] = b[tr][0]; b[tr][0] = None
        cr[c + 'K'] = False
        cr[c + 'Q'] = False
    if t == 'R':
        if fr == 7 and fc == 0: cr['wQ'] = False
        if fr == 7 and fc == 7: cr['wK'] = False
        if fr == 0 and fc == 0: cr['bQ'] = False
        if fr == 0 and fc == 7: cr['bK'] = False


def alg(fc, fr): return 'abcdefgh'[fc] + str(8 - fr)


def notation(b, fr, fc, tr, tc, ep, promo):
    p = b[fr][fc]
    if not p: return "error"
    t = pt(p)
    cap = b[tr][tc] or (t == 'P' and ep and (tr, tc) == ep)
    if t == 'K' and fc == 4 and tc == 6: return 'O-O'
    if t == 'K' and fc == 4 and tc == 2: return 'O-O-O'
    n = '' if t == 'P' else t
    if cap:
        if t == 'P': n += 'abcdefgh'[fc]
        n += 'x'
    n += alg(tc, tr)
    if promo: n += '=' + promo
    return n


def get_absolute_board(gs):
    b = cpb(gs['board'])
    for hidden_dict in [gs['hidden_w'], gs['hidden_b']]:
        for (tr, tc), val in hidden_dict.items():
            pub_pos, p = val.pub_pos, val.piece
            if pub_pos: b[pub_pos[0]][pub_pos[1]] = None
            b[tr][tc] = p
    return b


def get_true_board(gs, color):
    b = cpb(gs['board'])
    my_hidden = gs['hidden_w'] if color == 'w' else gs['hidden_b']
    for (tr, tc), val in my_hidden.items():
        pub_pos, p = val.pub_pos, val.piece
        if pub_pos: b[pub_pos[0]][pub_pos[1]] = None
        b[tr][tc] = p
    return b


def make_state():
    return dict(
        board=cpb(INIT),
        turn='w',
        ep=None,
        cr={'wK': True, 'wQ': True, 'bK': True, 'bQ': True},
        pts={'w': 0, 'b': 0},
        time_left={'w': 600, 'b': 600},
        game_started=False,
        hidden_w={},
        hidden_b={},
        shadow_history={},
        captured_w=set(),
        captured_b=set(),
        hidden_mode=False,
        hidden_count=0,
        hidden_seq={'w': 0, 'b': 0},
        fakeout_count=0,
        fakeout_seq={'w': 0, 'b': 0},
        normal_done=False,
        last_move=None,
        log=[],
        game_over=False,
        game_over_msg='',
        turn_count=1,
        rematch_requested_by=None,
        current_turn_actions=[],
        rematch_declined=False,
        opponent_left=False,
        created_at=time.time(),
        ghost_capture_flash=None,
        ghost_capture_type=None,
        reveal_flashes=[],
        fakeout_active=False,
        fakeout_used=False,
        fakeout_mode_enabled=True,
        score_to_win=False,
        disable_undo_placeholder=False,
        ice_king_enabled=False,
        opponent_joined=False,
        next_queue_w=[],
        next_queue_b=[],
        moved_this_turn=set(),
        frozen_pieces=set(),
        gesture_state=default_gesture_state()
    )


def hidden_cost(gs):
    hs = gs.get('hidden_seq', {'w': 0, 'b': 0})
    seq = hs if isinstance(hs, int) else hs.get(gs['turn'], 0)
    return 2 ** (seq + gs.get('hidden_count', 0))

def fakeout_cost(gs):
    fs = gs.get('fakeout_seq', {'w': 0, 'b': 0})
    seq = fs if isinstance(fs, int) else fs.get(gs['turn'], 0)
    return 2 ** (seq + gs.get('fakeout_count', 0))


def can_afford(gs):
    pts = gs['pts'][gs['turn']]
    if isinstance(pts, int):
        if pts < 0: return False
        return pts >= hidden_cost(gs)
    return False

def can_afford_fakeout(gs):
    pts = gs['pts'][gs['turn']]
    if isinstance(pts, int):
        if pts < 0: return False
        return pts >= fakeout_cost(gs)
    return False


def end_turn(gs, process_queue=False):
    if gs['game_over']: return
    # Turn must have normal move OR hidden pieces 
    if not gs['normal_done'] and gs['hidden_count'] == 0: return

    gs['current_turn_actions'] = []

    curr_color = gs['turn']

    if isinstance(gs.get('hidden_seq'), int):
        gs['hidden_seq'] = {'w': 0, 'b': 0}
        
    gs.setdefault('fakeout_seq', {'w': 0, 'b': 0})

    if gs.get('hidden_count', 0) > 0:
        gs['hidden_seq'][curr_color] = gs['hidden_seq'].get(curr_color, 0) + 1
    else:
        gs['hidden_seq'][curr_color] = 0

    if gs.get('fakeout_count', 0) > 0:
        gs['fakeout_seq'][curr_color] = gs['fakeout_seq'].get(curr_color, 0) + 1
    else:
        gs['fakeout_seq'][curr_color] = 0
        
    if gs['hidden_seq'][curr_color] == 0 and gs['fakeout_seq'][curr_color] == 0:
        my_hidden = gs['hidden_w'] if curr_color == 'w' else gs['hidden_b']
        
        enemy_captured = gs['captured_w'] if curr_color == 'b' else gs['captured_b']
        for cr, cc in list(enemy_captured):
            gs['board'][cr][cc] = None
        enemy_captured.clear()

        if my_hidden:
            if 'reveal_flashes' not in gs:
                gs['reveal_flashes'] = []
            for (tr, tc), val in list(my_hidden.items()):
                pub_pos, hp = val.pub_pos, val.piece
                is_f = val.is_fakeout
                gs['board'][tr][tc] = hp
                if pub_pos:
                    gs['board'][pub_pos[0]][pub_pos[1]] = None
                gs['captured_w'].discard((tr, tc))
                gs['captured_b'].discard((tr, tc))
                deactivate_plies(gs, val.plies)
                gs['reveal_flashes'].append([tr, tc, 'fakeout' if is_f else 'hidden'])
            my_hidden.clear()
            gs['log'].append(f"Sequência quebrada!")

    gs['turn'] = opp(gs['turn'])
    gs['hidden_mode'] = False
    gs['hidden_count'] = 0
    gs['fakeout_count'] = 0
    gs['normal_done'] = False
    gs['turn_count'] += 1
    gs['fakeout_active'] = False
    gs['fakeout_used'] = False
    gs['moved_this_turn'] = set()

    abs_b = get_absolute_board(gs)
    if in_check(abs_b, gs['turn']):
        enemy = opp(gs['turn'])
        enemy_hidden = gs['hidden_w'] if enemy == 'w' else gs['hidden_b']

        enemy_captured = gs['captured_w'] if enemy == 'b' else gs['captured_b']
        for cr, cc in list(enemy_captured):
            gs['board'][cr][cc] = None
        enemy_captured.clear()

        if enemy_hidden:
            if 'reveal_flashes' not in gs:
                gs['reveal_flashes'] = []
            for (tr, tc), val in enemy_hidden.items():
                pub_pos, hp = val.pub_pos, val.piece
                is_f = val.is_fakeout
                gs['board'][tr][tc] = hp
                if pub_pos:
                    gs['board'][pub_pos[0]][pub_pos[1]] = None

                gs['captured_w'].discard((tr, tc))
                gs['captured_b'].discard((tr, tc))
                gs['reveal_flashes'].append([tr, tc, 'fakeout' if is_f else 'hidden'])

            enemy_hidden.clear()
            gs['hidden_seq'][enemy] = 0
            abs_b = get_absolute_board(gs)

    mv = all_legal(gs)
    if not mv:
        if in_check(abs_b, gs['turn']):
            gs['game_over'] = True
            w = opp(gs['turn'])
            l = gs['turn']
            
            if gs.get('score_to_win') and gs['pts'][l] > gs['pts'][w]:
                # The one who got checkmated wins because they have more points
                winner = l
                reason = f"por maior estoque de pontos ({gs['pts'][l]} vs {gs['pts'][w]})!"
            else:
                winner = w
                reason = "por xeque-mate!"
            
            winner_name = 'As Brancas' if winner == 'w' else 'As Pretas'
            gs['game_over_msg'] = f"{winner_name} venceram {reason}"
        else:
            gs['game_over'] = True
            gs['game_over_msg'] = 'Afogamento — empate!'

    # Manual execution of next queues is now required by the user
    # if process_queue:
    #     process_next_queues(gs)


def get_next_turn_from_queue(gs, color):
    q_key = f'next_queue_{color}'
    if not gs.get(q_key):
        return None
    turn_actions = []
    for act in gs[q_key]:
        if act.get('type') == 'end_turn':
            break
        turn_actions.append(act)
    return turn_actions


def pop_next_turn_from_queue(gs, color):
    q_key = f'next_queue_{color}'
    if not gs.get(q_key):
        return
    while gs[q_key]:
        act = gs[q_key].pop(0)
        if act.get('type') == 'end_turn':
            break


def compare_turns(actions1, actions2):
    if len(actions1) != len(actions2):
        return False
    for a1, a2 in zip(actions1, actions2):
        # Compare essential fields for MovePiece
        if a1.get('type') != a2.get('type'):
            return False
        if a1.get('type', 'move') == 'move':
            fields = ['fr', 'fc', 'tr', 'tc', 'promo', 'hidden', 'fakeout']
            for f in fields:
                if a1.get(f) != a2.get(f):
                    return False
    return True


def process_next_queues(gs):
    from actions import deserialize_action, EndTurn, MovePiece
    while not gs['game_over']:
        c = gs['turn']
        q_key = f'next_queue_{c}'
        if not gs.get(q_key):
            break
        
        act_data = gs[q_key].pop(0)
        action = deserialize_action(act_data) if isinstance(act_data, dict) and 'type' in act_data else None
        
        drafted_turn = act_data.get('drafted_turn') if isinstance(act_data, dict) else None
        dt_suffix = f"|t{drafted_turn}" if drafted_turn is not None else ""

        # Legacy compatibility for plain dicts
        if not action:
            action = MovePiece(
                fr=act_data['fr'], fc=act_data['fc'], 
                tr=act_data['tr'], tc=act_data['tc'],
                hidden=act_data.get('hidden', False),
                promo=act_data.get('promo'),
                fakeout=act_data.get('fakeout', False)
            )
            # Legacy explicitly ended turn, but we'll adapt to new flow

        if isinstance(action, EndTurn):
            end_turn(gs)
            # If end_turn changes the turn, the while loop will check the next player's queue
            continue

        elif isinstance(action, MovePiece):
            old_fakeout_active = gs.get('fakeout_active', False)
            if action.fakeout:
                gs['fakeout_active'] = True
            
            is_valid_move = (action.tr, action.tc) in legal(gs, action.fr, action.fc)
            
            gs['fakeout_active'] = old_fakeout_active

            if is_valid_move:
                gs['pts'][c] += 1
                res = action.execute(gs)
                
                if not action.hidden and not action.fakeout:
                    gs['normal_done'] = True
                
                if res == "ghost_capture":
                    # Must wait for user to resolve ghost conflict manually. Turn remains active.
                    break
            else:
                gs['pts'][c] -= 1
                if action.hidden:
                    note_msg = "Lance inválido. Turno manual iniciado."
                    gs['log'].append(f"HIDDEN|{c}|{note_msg}|0{dt_suffix}")
                    ply_idx = len(gs['log'])
                    if 'shadow_history' not in gs:
                        gs['shadow_history'] = {}
                    gs['shadow_history'][ply_idx] = {
                        'type': 'HIDDEN',
                        'color': c,
                        'note': note_msg,
                        'active': True
                    }
                elif action.fakeout:
                    gs['log'].append(f"FAKEOUT|{c}|Lance inválido. Turno manual iniciado.{dt_suffix}")
                else:
                    gs['log'].append(f"NORMAL|{c}|Lance inválido. Turno manual iniciado.{dt_suffix}")

                if not action.hidden and not action.fakeout:
                    gs['normal_done'] = False
                break


def ice_king_interaction(gs, kr, kc, tr, tc):
    """
    Handles the Ice King logic: freezing/unfreezing ally pieces.
    Returns: 'frozen', 'unfrozen', or None
    """
    if not gs.get('disable_undo_placeholder', False) or not gs.get('ice_king_enabled', False):
        return None
    
    board = gs['board']
    c = gs['turn']
    p_king = board[kr][kc]
    p_target = board[tr][tc]
    
    if not p_king or pt(p_king) != 'K' or pc(p_king) != c:
        return None
    
    if not p_target or pc(p_target) != c or pt(p_target) == 'K':
        return None
    
    frozen = gs.get('frozen_pieces', set())
    val = VALUES.get(pt(p_target), 0)
    
    if (tr, tc) in frozen:
        frozen.remove((tr, tc))
        gs['pts'][c] -= val
        gs['log'].append(f"ICE|{c}| O rei descongelou {alg(tc, tr)} (-{val}pt)")
        return 'unfrozen'
    else:
        frozen.add((tr, tc))
        gs['pts'][c] += val
        gs['log'].append(f"ICE|{c}| O rei congelou {alg(tc, tr)} (+{val}pt)")
        return 'frozen'


def exec_move(gs, fr, fc, tr, tc, hidden_move=False, promo=None):
    board = gs['board']
    p_raw = board[fr][fc]
    piece_color = pc(p_raw)
    if gs.get('white_controls_black', False):
        c = piece_color
    else:
        c = gs['turn']
    my_hidden = gs['hidden_w'] if c == 'w' else gs['hidden_b']
    enemy_hidden = gs['hidden_b'] if c == 'w' else gs['hidden_w']

    abs_b = get_absolute_board(gs)
    tb = get_true_board(gs, c)
    p = tb[fr][fc]

    is_fakeout = gs.get('fakeout_active', False)
    if is_fakeout and (tr, tc) not in legal(gs, fr, fc):
        return False

    cfr, cfc = fr, fc
    if is_fakeout and (fr, fc) in my_hidden:
        val = my_hidden[(fr, fc)]
        if val.pub_pos:
            cfr, cfc = val.pub_pos

    # Check if this is a capture against the old position of an opposing piece (ghost piece)
    ghost_found = None
    for t_pos, val in enemy_hidden.items():
        p_pos, hp = val.pub_pos, val.piece
        if p_pos == (tr, tc):
            ghost_found = t_pos
            break

    if ghost_found is not None:
        # A ghost capture occurred!
        # 1. The captured piece disappears from the public board
        board[tr][tc] = None
        # 2. In enemy_hidden, clear pub_pos to None
        val = enemy_hidden[ghost_found]
        is_f = val.is_fakeout
        enemy_hidden[ghost_found] = PieceMetaModifier(pub_pos=None, piece=val.piece, path=val.path, is_fakeout=val.is_fakeout, fakeout_path=val.fakeout_path, plies=val.plies)
        # 3. Add to the log
        if is_f:
            gs['log'].append(f"SYS_FAKEOUT|Ilusão desfeita em {alg(tc, tr)}!")
        else:
            gs['log'].append(f"SYS_HIDDEN|Ilusão desfeita em {alg(tc, tr)}!")
        # 4. Set the ghost_capture_flash coordinate
        gs['ghost_capture_flash'] = (tr, tc)
        gs['ghost_capture_type'] = 'fakeout' if is_f else 'hidden'
        # 5. Return a special status "ghost_capture" and keep the active player's turn to redo their move.
        return "ghost_capture"

    def get_dir(a, b):
        return 0 if a == b else (1 if b > a else -1)

    t = pt(p)
    collision = None

    if t == 'K' and abs(cfc - tc) == 2:
        step = 1 if tc > cfc else -1

        check_cols = [cfc + step, cfc + 2 * step]

        if tc == 2:
            check_cols.append(1)

        for col in check_cols:
            if (cfr, col) in enemy_hidden:
                collision = (cfr, col)
                break

    elif t not in ('N', 'K'):
        dr, dc = get_dir(cfr, tr), get_dir(cfc, tc)
        r, cc = cfr + dr, cfc + dc

        while 0 <= r < 8 and 0 <= cc < 8:
            if (r, cc) in enemy_hidden:
                collision = (r, cc)
                break
            if (r, cc) == (tr, tc):
                break
            r += dr
            cc += dc
    else:
        if (tr, tc) in enemy_hidden:
            collision = (tr, tc)

    if collision:
        cr, cc = collision
        val = enemy_hidden.pop((cr, cc))
        pub_pos, hp = val.pub_pos, val.piece
        is_f = val.is_fakeout
        deactivate_plies(gs, val.plies)

        if pub_pos: board[pub_pos[0]][pub_pos[1]] = None
        board[cr][cc] = hp

        if is_f:
            gs['log'].append(f"SYS_FAKEOUT|Peça oculta avistada em {alg(cc, cr)}!")
        else:
            gs['log'].append(f"SYS_HIDDEN|Peça oculta avistada em {alg(cc, cr)}!")
        if 'reveal_flashes' not in gs:
            gs['reveal_flashes'] = []
        gs['reveal_flashes'].append([cr, cc, 'fakeout' if is_f else 'hidden'])
        return False

    cap_true = abs_b[tr][tc]
    if cap_true and pc(cap_true) != c:
        gs['pts'][c] += VALUES.get(pt(cap_true), 0)
        enemy_captured = gs['captured_w'] if c == 'b' else gs['captured_b']
        enemy_captured.add((tr, tc))

    board_for_notation = board if (is_fakeout and (fr, fc) in my_hidden) else tb
    note = notation(board_for_notation, cfr, cfc, tr, tc, gs['ep'], promo)
    if promo: p = p[0] + promo

    if gs.get('fakeout_active'):
        gs['fakeout_active'] = False
        gs['fakeout_used'] = True
        gs['last_move'] = (cfr, cfc, tr, tc)
        gs['last_move_visible_to'] = None
        if 'moved_this_turn' not in gs: gs['moved_this_turn'] = set()
        gs['moved_this_turn'].add((tr, tc))
        
        cost = fakeout_cost(gs)
        gs['pts'][c] -= cost
        gs['fakeout_count'] = gs.get('fakeout_count', 0) + 1

        # Clear starting spot on public board
        was_previously_hidden = (fr, fc) in my_hidden
        if was_previously_hidden:
            val = my_hidden.pop((fr, fc))
            old_pub_pos = val.pub_pos
            path = val.path if val.path else [(fr, fc)]
            prev_plies = val.plies
            if old_pub_pos:
                board[old_pub_pos[0]][old_pub_pos[1]] = None
        else:
            old_pub_pos = (fr, fc)
            path = [(fr, fc)]
            prev_plies = []
            board[fr][fc] = None

        # Place fakeout piece on target square on public board
        board[tr][tc] = p

        gs['log'].append(f'FAKEOUT|{c}|{note}')
        ply_idx = len(gs['log'])
        if 'shadow_history' not in gs:
            gs['shadow_history'] = {}
        gs['shadow_history'][ply_idx] = {
            'type': 'FAKEOUT',
            'color': c,
            'note': note,
            'active': True
        }

        # Put in my_hidden: true_pos remains at (fr, fc), pub_pos becomes (tr, tc), is_fakeout = True
        if was_previously_hidden:
            prev_f_path = val.fakeout_path if val.fakeout_path else []
            if not prev_f_path:
                prev_f_path = [old_pub_pos] if old_pub_pos else []
            new_f_path = list(prev_f_path)
            if (tr, tc) not in new_f_path:
                new_f_path.append((tr, tc))
            my_hidden[(fr, fc)] = PieceMetaModifier(pub_pos=(tr, tc), piece=p, path=path, is_fakeout=True, fakeout_path=new_f_path, plies=prev_plies + [ply_idx])
        else:
            my_hidden[(fr, fc)] = PieceMetaModifier(pub_pos=(tr, tc), piece=p, path=[], is_fakeout=True, fakeout_path=[(fr, fc), (tr, tc)], plies=prev_plies + [ply_idx])

        # Handle captured ghost/real piece at destination on public board
        for t_pos, val in enemy_hidden.items():
            p_pos = val.pub_pos
            if p_pos == (tr, tc):
                hp = val.piece
                enemy_path = val.path
                is_f = val.is_fakeout
                enemy_hidden[t_pos] = PieceMetaModifier(pub_pos=None, piece=hp, path=enemy_path, is_fakeout=is_f, fakeout_path=[], plies=[])

        gs['captured_w'].discard((tr, tc))
        gs['captured_b'].discard((tr, tc))

        # ep and castling rights updates
        gs['ep'] = None
        if pt(p) == 'P' and abs(tr - cfr) == 2: gs['ep'] = ((cfr + tr) // 2, cfc)
        if pt(p) == 'K':
            gs['cr'][c + 'K'] = False
            gs['cr'][c + 'Q'] = False
        if pt(p) == 'R':
            if cfr == (7 if c == 'w' else 0) and cfc == 0: gs['cr'][c + 'Q'] = False
            if cfr == (7 if c == 'w' else 0) and cfc == 7: gs['cr'][c + 'K'] = False
        gs['normal_done'] = False
        return True

    elif hidden_move:
        if (fr, fc) in gs.get('moved_this_turn', set()):
            return False

        cost = hidden_cost(gs)
        gs['pts'][c] -= cost
        gs['hidden_count'] += 1

        if (fr, fc) in my_hidden:
            val = my_hidden.pop((fr, fc))
            pub_pos = val.pub_pos
            path = val.path if val.path else [(fr, fc)]
            prev_plies = val.plies
            prev_is_f = val.is_fakeout
            prev_f_path = val.fakeout_path
        else:
            pub_pos = (fr, fc)
            path = [(fr, fc)]
            prev_plies = []
            prev_is_f = False
            prev_f_path = []

        new_path = list(path) + [(tr, tc)]

        gs['log'].append(f'HIDDEN|{c}|{note}|{cost}')
        ply_idx = len(gs['log'])
        if 'shadow_history' not in gs:
            gs['shadow_history'] = {}
        gs['shadow_history'][ply_idx] = {
            'type': 'HIDDEN',
            'color': c,
            'note': note,
            'active': True
        }

        my_hidden[(tr, tc)] = PieceMetaModifier(pub_pos=pub_pos, piece=p, path=new_path, is_fakeout=prev_is_f, fakeout_path=prev_f_path, plies=prev_plies + [ply_idx])
        if 'moved_this_turn' not in gs: gs['moved_this_turn'] = set()
        gs['moved_this_turn'].add((tr, tc))

        gs['last_move'] = (fr, fc, tr, tc)
        gs['last_move_visible_to'] = c

        if t == 'K' and abs(fc - tc) == 2:
            r_fc = 7 if tc == 6 else 0
            r_tc = 5 if tc == 6 else 3
            rp = tb[fr][r_fc]
            if rp:
                my_hidden[(fr, r_tc)] = PieceMetaModifier(pub_pos=(fr, r_fc), piece=rp, path=[(fr, r_fc), (fr, r_tc)], is_fakeout=False, fakeout_path=[], plies=prev_plies + [ply_idx])
    else:
        gs['normal_done'] = True
        gs['last_move'] = (fr, fc, tr, tc)
        gs['last_move_visible_to'] = None
        if 'moved_this_turn' not in gs: gs['moved_this_turn'] = set()
        gs['moved_this_turn'].add((tr, tc))

        if (fr, fc) in my_hidden:
            val = my_hidden.pop((fr, fc))
            pub_pos = val.pub_pos
            if pub_pos: board[pub_pos[0]][pub_pos[1]] = None
            deactivate_plies(gs, val.plies)

        for t_pos, val in enemy_hidden.items():
            p_pos = val.pub_pos
            if p_pos == (tr, tc):
                hp = val.piece
                path = val.path
                is_f = val.is_fakeout
                f_path = val.fakeout_path
                plies = val.plies
                enemy_hidden[t_pos] = PieceMetaModifier(pub_pos=None, piece=hp, path=path, is_fakeout=is_f, fakeout_path=f_path, plies=plies)

        gs['captured_w'].discard((tr, tc))
        gs['captured_b'].discard((tr, tc))

        board[fr][fc] = p
        do_move(board, fr, fc, tr, tc, gs['ep'], gs['cr'], promo)

        gs['log'].append(f'NORMAL|{c}|{note}')

    gs['ep'] = None
    if pt(p) == 'P' and abs(tr - fr) == 2: gs['ep'] = ((fr + tr) // 2, fc)
    if pt(p) == 'K':
        gs['cr'][c + 'K'] = False
        gs['cr'][c + 'Q'] = False
    if pt(p) == 'R':
        if fr == (7 if c == 'w' else 0) and fc == 0: gs['cr'][c + 'Q'] = False
        if fr == (7 if c == 'w' else 0) and fc == 7: gs['cr'][c + 'K'] = False
    return True


def deactivate_plies(gs, plies):
    if 'shadow_history' not in gs:
        gs['shadow_history'] = {}
    for p_i in plies:
        if p_i in gs['shadow_history']:
            gs['shadow_history'][p_i]['active'] = False


def check_conflict(gs, fr, fc, tr, tc):
    mover = gs['turn']
    enemy_hidden = gs['hidden_b'] if mover == 'w' else gs['hidden_w']
    my_captured = gs['captured_w'] if mover == 'w' else gs['captured_b']

    if (fr, fc) in my_captured: return ('src', fr, fc)
    if (tr, tc) in enemy_hidden: return ('dst', tr, tc)
    return None



def get_ui_selection(gs, r, c, draft_moves=None):
    from draft_simulator import get_draft_state
    """
    Given an attempted click on row r, col c,
    Determines if it's a valid selection, and returns
    its true position (for hidden pieces) and its legal moves.
    Returns: (selected_pos, legal_moves_list) or (None, [])
    """
    draft_moves = draft_moves or []
    is_drafting = gs.get('drafting_active', False)
    
    active_color = gs['turn']
    
    curr_dgs = get_draft_state(gs, draft_moves) if is_drafting else gs
    if curr_dgs.get('white_controls_black', False):
        tb = get_absolute_board(curr_dgs)
        my_hidden = {**curr_dgs['hidden_w'], **curr_dgs['hidden_b']}
    else:
        tb = get_true_board(curr_dgs, active_color)
        my_hidden = curr_dgs['hidden_w'] if active_color == 'w' else curr_dgs['hidden_b']
    
    can_select_anything = True
    if curr_dgs.get('fakeout_active'):
        if not can_afford_fakeout(curr_dgs):
            can_select_anything = False
    else:
        if (curr_dgs.get('normal_done') or curr_dgs.get('hidden_count', 0) > 0):
            can_select_anything = False
        if curr_dgs.get('hidden_mode') and not can_afford(curr_dgs):
            can_select_anything = False
            
    if not can_select_anything:
        return None, []
    
    target_hidden_true_pos = None
    if curr_dgs.get('fakeout_active'):
        for t_pos, val in my_hidden.items():
            if val.pub_pos == (r, c):
                target_hidden_true_pos = t_pos
                break
                
    if target_hidden_true_pos is not None:
        sel = target_hidden_true_pos
        legals = legal(curr_dgs, sel[0], sel[1])
        if not is_drafting and curr_dgs.get('hidden_count', 0) > 0 and not curr_dgs.get('fakeout_active'):
            legals = []
        return sel, legals
    else:
        if curr_dgs.get('fakeout_active') and (r, c) in my_hidden:
            return None, []
        else:
            p = tb[r][c]
            if p and pc(p) == active_color:
                legals = legal(curr_dgs, r, c)
                if not is_drafting and curr_dgs.get('hidden_count', 0) > 0 and not curr_dgs.get('fakeout_active'):
                    legals = []
                # Remove already moved pieces if not drafting
                if not is_drafting and (r, c) in curr_dgs.get('moved_this_turn', set()):
                    legals = []
                return (r, c), legals
            return None, []


def serialize_state(gs, player_color=None, dgs=None):
    def convert_hidden(hd):
        return {f"{k[0]},{k[1]}": (
            list(v.pub_pos) if v.pub_pos else None,
            v.piece,
            [list(x) for x in v.path],
            v.is_fakeout,
            [list(x) for x in v.fakeout_path],
            v.plies
        ) if isinstance(v, PieceMetaModifier) else (
            list(v[0]) if v[0] else None, 
            v[1], 
            [list(x) for x in v[2]] if len(v) > 2 else [], 
            v[3] if len(v) > 3 else False, 
            [list(x) for x in v[4]] if len(v) > 4 else [], 
            v[5] if len(v) > 5 else []
        ) for k, v in hd.items()}

    def clean_queue(q, is_author, author_color):
        if not q:
            return []
        if is_author:
            return list(q)
        
        clean = []
        for m in q:
            if hasattr(m, 'get'):
                if m.get('hidden') or m.get('fakeout'):
                    continue
            clean.append(m)
        return clean

    filtered_log = []
    classified_entries = []
    normal_moves_count = 0
    for idx, entry in enumerate(gs['log']):
        parts = entry.split('|')
        ply_idx = idx + 1
        is_active = True
        shadow_hist = gs.get('shadow_history', {})
        if ply_idx in shadow_hist:
            is_active = shadow_hist[ply_idx].get('active', True)
        elif str(ply_idx) in shadow_hist:
            is_active = shadow_hist[str(ply_idx)].get('active', True)

        drafted_turn = None
        if len(parts) > 1:
            last_part = parts[-1]
            if last_part.startswith('t') and last_part[1:].isdigit():
                drafted_turn = int(last_part[1:])
                parts.pop()

        if parts[0] == 'HIDDEN':
            color, note, cost = parts[1], parts[2], parts[3]
            if "Lance inválido. Turno manual iniciado." in note:
                if color == player_color:
                    classified_entries.append({
                        'type': 'NEXT_CANCELLED',
                        'color': color,
                        'text': note,
                        'color_type': 'next_cancelled',
                        'drafted_turn': drafted_turn
                    })
            elif color == player_color:
                txt = f"{note} (-{cost}pt)"
                classified_entries.append({
                    'type': 'HIDDEN',
                    'color': color,
                    'text': txt,
                    'color_type': 'hidden',
                    'drafted_turn': drafted_turn
                })
            elif not is_active or gs.get('game_over', False):
                txt = f"{note}"
                classified_entries.append({
                    'type': 'HIDDEN',
                    'color': color,
                    'text': txt,
                    'color_type': 'revealed',
                    'drafted_turn': drafted_turn
                })
        elif parts[0] == 'FAKEOUT':
            color, note = parts[1], parts[2]
            if "Lance inválido. Turno manual iniciado." in note:
                if color == player_color:
                    classified_entries.append({
                        'type': 'NEXT_CANCELLED',
                        'color': color,
                        'text': note,
                        'color_type': 'next_cancelled',
                        'drafted_turn': drafted_turn
                    })
            elif color == player_color:
                txt = f"{note}"
                classified_entries.append({
                    'type': 'FAKEOUT',
                    'color': color,
                    'text': txt,
                    'color_type': 'fakeout',
                    'drafted_turn': drafted_turn
                })
            else:
                display_note = note.replace("[Fakeout] ", "")
                if color == 'w':
                    normal_moves_count += 1
                    txt = f"{normal_moves_count}. {display_note}"
                    classified_entries.append({
                        'type': 'FAKEOUT',
                        'color': color,
                        'text': txt,
                        'color_type': 'white_move',
                        'move_num': normal_moves_count,
                        'drafted_turn': drafted_turn
                    })
                else:
                    txt = f"    {display_note}"
                    classified_entries.append({
                        'type': 'FAKEOUT',
                        'color': color,
                        'text': txt,
                        'color_type': 'black_move',
                        'drafted_turn': drafted_turn
                    })
        elif parts[0] == 'PRIVATE_SYS':
            color, note = parts[1], parts[2]
            if color == player_color:
                txt = f"{note}"
                classified_entries.append({
                    'type': 'PRIVATE_SYS',
                    'color': color,
                    'text': txt,
                    'color_type': 'hidden',
                    'drafted_turn': drafted_turn
                })
        elif parts[0] == 'SYS_HIDDEN':
            txt = parts[1]
            classified_entries.append({
                'type': 'SYS_HIDDEN',
                'color': player_color,
                'text': txt,
                'color_type': 'hidden',
                'drafted_turn': drafted_turn
            })
        elif parts[0] == 'SYS_FAKEOUT':
            txt = parts[1]
            classified_entries.append({
                'type': 'SYS_FAKEOUT',
                'color': player_color,
                'text': txt,
                'color_type': 'fakeout',
                'drafted_turn': drafted_turn
            })
        elif parts[0] == 'NORMAL':
            color, note = parts[1], parts[2]
            if "Lance inválido. Turno manual iniciado." in note:
                classified_entries.append({
                    'type': 'NEXT_CANCELLED',
                    'color': color,
                    'text': note,
                    'color_type': 'next_cancelled',
                    'drafted_turn': drafted_turn
                })
            else:
                if color == 'w':
                    normal_moves_count += 1
                    txt = f"{normal_moves_count}. {note}"
                    classified_entries.append({
                        'type': 'NORMAL',
                        'color': color,
                        'text': txt,
                        'color_type': 'white_move',
                        'move_num': normal_moves_count,
                        'drafted_turn': drafted_turn
                    })
                else:
                    txt = f"    {note}"
                    classified_entries.append({
                        'type': 'NORMAL',
                        'color': color,
                        'text': txt,
                        'color_type': 'black_move',
                        'drafted_turn': drafted_turn
                    })
        elif parts[0] == 'NEXT':
            color, note = parts[1], parts[2]
            classified_entries.append({
                'type': 'NEXT',
                'color': color,
                'text': note,
                'color_type': 'next',
                'drafted_turn': drafted_turn
            })
        elif parts[0] == 'ICE':
            color, note = parts[1], parts[2]
            classified_entries.append({
                'type': 'ICE',
                'color': color,
                'text': note,
                'color_type': 'system',
                'drafted_turn': drafted_turn
            })
        else:
            last_c = 'system'
            if classified_entries:
                last_c = classified_entries[-1]['color']
            classified_entries.append({
                'type': 'SYSTEM',
                'color': last_c,
                'text': entry,
                'color_type': 'system',
                'drafted_turn': drafted_turn
            })

    filtered_log = [e['text'] for e in classified_entries]

    turns = []
    current_turn = None

    def is_real_move(e):
        if e['type'] in ('SYSTEM', 'NEXT', 'NEXT_CANCELLED'):
            return False
        txt = e.get('text', '')
        if '[Next]' in txt or 'Next' in txt or '[Next Cancelado]' in txt or 'Next Cancelado' in txt:
            return False
        return True

    for entry in classified_entries:
        ent_color = entry.get('color')
        
        if current_turn is None:
            turn_num = 1
            if 'move_num' in entry:
                turn_num = entry['move_num']
            current_turn = {
                'number': turn_num,
                'entries': []
            }
        else:
            if ent_color in ('w', 'b') and is_real_move(entry):
                should_split = False
                if ent_color == 'w':
                    if any(existing.get('color') in ('w', 'b') and is_real_move(existing) for existing in current_turn['entries']):
                        should_split = True
                elif ent_color == 'b':
                    if any(existing.get('color') == 'b' and is_real_move(existing) for existing in current_turn['entries']):
                        should_split = True

                if should_split:
                    turns.append(current_turn)
                    prev_num = current_turn['number']
                    next_num = entry.get('move_num', prev_num + 1)
                    current_turn = {
                        'number': next_num,
                        'entries': []
                    }
                elif ent_color == 'w' and 'move_num' in entry:
                    current_turn['number'] = entry['move_num']

        current_turn['entries'].append(entry)

    if current_turn and current_turn['entries']:
        turns.append(current_turn)

    def is_next_entry(e):
        if e['type'] in ('NEXT', 'NEXT_CANCELLED'):
            return True
        txt = e.get('text', '')
        if '[Next]' in txt or 'Next' in txt or '[Next Cancelado]' in txt or 'Next Cancelado' in txt:
            return True
        return False

    if turns:
        turns_map = {t['number']: t['entries'] for t in turns}
        max_t = max(turns_map.keys()) if turns_map else 1
        redistributed_entries = {i: [] for i in range(1, max_t + 1)}
        
        for t in turns:
            t_num = t['number']
            for entry in t['entries']:
                draft_t = entry.get('drafted_turn')
                if draft_t is not None:
                    target_num = draft_t
                elif is_next_entry(entry):
                    target_num = max(1, t_num - 1)
                else:
                    target_num = t_num
                
                if target_num not in redistributed_entries:
                    redistributed_entries[target_num] = []
                redistributed_entries[target_num].append(entry)
                
        final_turns = []
        for t_num in sorted(redistributed_entries.keys()):
            if t_num in turns_map or redistributed_entries[t_num]:
                final_turns.append({
                    'number': t_num,
                    'entries': redistributed_entries[t_num]
                })
        turns = final_turns

    safe_pts = {'w': gs['pts']['w'], 'b': gs['pts']['b']}
    if player_color == 'w':
        safe_pts['b'] = '?'
    elif player_color == 'b':
        safe_pts['w'] = '?'

    hidden_w_safe = convert_hidden(gs['hidden_w']) if player_color == 'w' else {}
    hidden_b_safe = convert_hidden(gs['hidden_b']) if player_color == 'b' else {}

    shadow_history_safe = {}
    for ply, info in gs.get('shadow_history', {}).items():
        ply_str = str(ply)
        if info['color'] == player_color or not info['active'] or gs.get('game_over', False):
            shadow_history_safe[ply_str] = info

    ret = {
        'board': gs['board'],
        'turn': gs['turn'],
        'ep': list(gs['ep']) if gs['ep'] else None,
        'cr': gs['cr'],
        'pts': safe_pts,
        'hidden_w': hidden_w_safe,
        'hidden_b': hidden_b_safe,
        'shadow_history': shadow_history_safe,
        'captured_w': [list(x) for x in gs['captured_w']],
        'captured_b': [list(x) for x in gs['captured_b']],
        'hidden_mode': gs['hidden_mode'],
        'hidden_count': gs['hidden_count'],
        'hidden_seq': gs.get('hidden_seq', {'w': 0, 'b': 0}),
        'fakeout_count': gs.get('fakeout_count', 0),
        'fakeout_seq': gs.get('fakeout_seq', {'w': 0, 'b': 0}),
        'normal_done': gs['normal_done'],
        'last_move': list(gs['last_move']) if (gs.get('last_move') and (not gs.get('last_move_visible_to') or gs['last_move_visible_to'] == player_color or gs.get('game_over', False))) else None,
        'log': filtered_log,
        'classified_log': classified_entries,
        'log_turns': turns,
        'game_over': gs['game_over'],
        'game_over_msg': gs['game_over_msg'],
        'turn_count': gs['turn_count'],
        'time_left': gs['time_left'],
        'game_started': gs['game_started'],
        'rematch_requested_by': gs.get('rematch_requested_by'),
        'rematch_declined': gs.get('rematch_declined'),
        'opponent_left': gs.get('opponent_left', False),
        'ghost_capture_flash': list(gs['ghost_capture_flash']) if gs.get('ghost_capture_flash') else None,
        'ghost_capture_type': gs.get('ghost_capture_type'),
        'reveal_flashes': gs.get('reveal_flashes', []),
        'fakeout_active': gs.get('fakeout_active', False),
        'fakeout_used': gs.get('fakeout_used', False),
        'gesture_state': normalize_gesture_state(gs.get('gesture_state', default_gesture_state())),
        'fakeout_mode_enabled': gs.get('fakeout_mode_enabled', True),
        'score_to_win': gs.get('score_to_win', False),
        'disable_undo_placeholder': gs.get('disable_undo_placeholder', False),
        'ice_king_enabled': gs.get('ice_king_enabled', False),
        'opponent_joined': gs.get('opponent_joined', False),
        'next_queue_w': clean_queue(gs.get('next_queue_w'), player_color == 'w', 'w'),
        'next_queue_b': clean_queue(gs.get('next_queue_b'), player_color == 'b', 'b'),
        'moved_this_turn': [list(x) for x in gs.get('moved_this_turn', set())],
        'frozen_pieces': [list(p) for p in gs.get('frozen_pieces', set())],
        'white_controls_black': gs.get('white_controls_black', False)
    }

    my_legals = {}
    if player_color and player_color == gs['turn']:
        target_gs = dgs if dgs else gs
        for r in range(8):
            for c in range(8):
                if pc(get_true_board(target_gs, player_color)[r][c]) == player_color:
                    mvs = legal(target_gs, r, c)
                    if mvs:
                        my_legals[f"{r},{c}"] = [list(m) for m in mvs]
    
    ret['my_legals'] = my_legals

    return ret


def deserialize_state(data):
    def parse_hidden(hd):
        parsed = {}
        for k, v in hd.items():
            pos = tuple(map(int, k.split(',')))
            parsed[pos] = PieceMetaModifier(
                pub_pos=tuple(v[0]) if v[0] else None,
                piece=v[1],
                path=[tuple(x) for x in v[2]] if len(v) > 2 else [],
                is_fakeout=v[3] if len(v) > 3 else False,
                fakeout_path=[tuple(x) for x in v[4]] if len(v) > 4 else [],
                plies=v[5] if len(v) > 5 else []
            )
        return parsed

    shadow_hist = {}
    if 'shadow_history' in data:
        for k, v in data['shadow_history'].items():
            shadow_hist[int(k)] = v

    hs = data.get('hidden_seq', {'w': 0, 'b': 0})
    if isinstance(hs, int):
        hs = {'w': hs, 'b': hs}

    return {
        'board': data['board'],
        'turn': data['turn'],
        'ep': tuple(data['ep']) if data['ep'] else None,
        'cr': data['cr'],
        'pts': data['pts'],
        'hidden_w': parse_hidden(data['hidden_w']),
        'hidden_b': parse_hidden(data['hidden_b']),
        'shadow_history': shadow_hist,
        'captured_w': set(tuple(x) for x in data['captured_w']),
        'captured_b': set(tuple(x) for x in data['captured_b']),
        'hidden_mode': data['hidden_mode'],
        'hidden_count': data['hidden_count'],
        'hidden_seq': hs,
        'fakeout_count': data.get('fakeout_count', 0),
        'fakeout_seq': data.get('fakeout_seq', {'w': 0, 'b': 0}),
        'normal_done': data['normal_done'],
        'last_move': tuple(data['last_move']) if data['last_move'] else None,
        'log': data['log'],
        'classified_log': data.get('classified_log', []),
        'log_turns': data.get('log_turns', []),
        'game_over': data['game_over'],
        'game_over_msg': data['game_over_msg'],
        'turn_count': data['turn_count'],
        'time_left': data['time_left'],
        'game_started': data['game_started'],
        'rematch_requested_by': data.get('rematch_requested_by'),
        'rematch_declined': data.get('rematch_declined'),
        'opponent_left': data.get('opponent_left', False),
        'ghost_capture_flash': tuple(data['ghost_capture_flash']) if data.get('ghost_capture_flash') else None,
        'ghost_capture_type': data.get('ghost_capture_type'),
        'reveal_flashes': data.get('reveal_flashes', []),
        'fakeout_active': data.get('fakeout_active', False),
        'fakeout_used': data.get('fakeout_used', False),
        'gesture_state': normalize_gesture_state(data.get('gesture_state', default_gesture_state())),
        'fakeout_mode_enabled': data.get('fakeout_mode_enabled', True),
        'score_to_win': data.get('score_to_win', False),
        'disable_undo_placeholder': data.get('disable_undo_placeholder', False),
        'ice_king_enabled': data.get('ice_king_enabled', False),
        'opponent_joined': data.get('opponent_joined', False),
        'next_queue_w': data.get('next_queue_w', []),
        'next_queue_b': data.get('next_queue_b', []),
        'moved_this_turn': set(tuple(x) for x in data.get('moved_this_turn', [])),
        'frozen_pieces': set(tuple(p) for p in data.get('frozen_pieces', [])),
        'white_controls_black': data.get('white_controls_black', False)
    }
