# Debugging utilities for invariant checks and logging of game state
def check_invariants(gs):
    # 1. Turn is valid
    assert gs.get('turn') in ('w', 'b'), f"Invalid turn: {gs.get('turn')}"

    turn = gs.get('turn')
    turn_count = gs.get('turn_count', 0)
    
    # 2. Points are valid
    for c in ('w', 'b'):
        if 'pts' in gs and c in gs['pts']:
            assert gs['pts'][c] >= 0, f"Negative points for {c}: {gs['pts'][c]}"

    # Kings exist validation
    from chess_logic import get_true_board
    tb_w = get_true_board(gs, 'w')
    tb_b = get_true_board(gs, 'b')
    
    w_king_found = any('wK' in str(p) for row in tb_w for p in row)
    b_king_found = any('bK' in str(p) for row in tb_b for p in row)
    
    if not w_king_found:
        print(f"WARNING [Invariant]: White King missing in turn {turn_count}")
    if not b_king_found:
        print(f"WARNING [Invariant]: Black King missing in turn {turn_count}")

    # 3. Hidden invariants: If a piece is actively hiding (not fakeout), its true position should not be on the public board.
    # Actually 'pub_pos' is where the fake/shadow piece is left.
    public_board = gs['board']
    for color, hidden_dict in [('w', gs.get('hidden_w', {})), ('b', gs.get('hidden_b', {}))]:
        for true_pos, val in hidden_dict.items():
            pub_pos = val[0]
            hp = val[1]
            # If public position exists, it was a shadow move (or fakeout shadow).
            # The true position on public board should generally not contain this piece,
            # UNLESS it's the exact same as pub_pos (which shouldn't happen for hidden).
            if pub_pos:
                pass


def log_minimal_snapshot(gs, action_name):
    turn = gs.get('turn', '?')
    turn_count = gs.get('turn_count', '?')
    pts_w = gs.get('pts', {}).get('w', '?')
    pts_b = gs.get('pts', {}).get('b', '?')
    hidden_count = gs.get('hidden_count', 0)
    draft_count = len(gs.get(f'next_queue_{turn}', []))
    
    print(f"[DEBUG] Turn={turn_count}({turn}) Action={action_name} " 
          f"PTS={{w:{pts_w}, b:{pts_b}}} HiddenCount={hidden_count} DraftCount={draft_count}")
