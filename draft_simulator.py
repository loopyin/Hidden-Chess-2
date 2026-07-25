from chess_logic import exec_move, opp

def transition_draft_turn(dgs):
    c = dgs['turn']
    
    if not isinstance(dgs.get('hidden_seq'), dict): dgs['hidden_seq'] = {'w': 0, 'b': 0}
    if not isinstance(dgs.get('fakeout_seq'), dict): dgs['fakeout_seq'] = {'w': 0, 'b': 0}
    
    if dgs.get('hidden_count', 0) > 0:
        dgs['hidden_seq'][c] = dgs['hidden_seq'].get(c, 0) + 1
    else:
        dgs['hidden_seq'][c] = 0
        
    if dgs.get('fakeout_count', 0) > 0:
        dgs['fakeout_seq'][c] = dgs['fakeout_seq'].get(c, 0) + 1
    else:
        dgs['fakeout_seq'][c] = 0

    # Simulate two-turn gap to return to the player's subsequent turn
    dgs['turn'] = opp(dgs['turn'])
    dgs['turn_count'] += 1
    
    # Neutralize game state flags for the opponent's simulated turn
    dgs['normal_done'] = False
    dgs['hidden_count'] = 0
    dgs['fakeout_count'] = 0
    dgs['fakeout_used'] = False
    dgs['fakeout_active'] = False
    dgs['hidden_mode'] = False
    dgs['moved_this_turn'] = set()
    
    dgs['turn'] = opp(dgs['turn'])
    dgs['turn_count'] += 1
    
    # Neutralize game state flags for the player's new simulated turn
    dgs['normal_done'] = False
    dgs['hidden_count'] = 0
    dgs['fakeout_count'] = 0
    dgs['fakeout_used'] = False
    dgs['fakeout_active'] = False
    dgs['hidden_mode'] = False
    dgs['moved_this_turn'] = set()

def get_draft_state(gs, draft_moves):
    """
    Receives the real game state and a list of draft moves.
    Produces a simulated future state without modifying the real one.
    """
    import copy
    dgs = copy.deepcopy(gs)
    
    # If the player finished their real actions, the draft
    # represents actions starting from their SUBSEQUENT turn.
    can_fakeout = dgs.get('hidden_count', 0) == 1 and dgs.get('fakeout_count', 0) == 0 and not dgs.get('fakeout_used', False)
    cond = (dgs.get('normal_done', False) or (dgs.get('hidden_count', 0) > 0 and not can_fakeout))
    if cond or dgs.get('fakeout_count', 0) > 0:
        transition_draft_turn(dgs)
        
    from actions import deserialize_action, EndTurn, MovePiece
    
    for dm in draft_moves:
        action = deserialize_action(dm)
        if not action:
            action = MovePiece(
                fr=dm['fr'], fc=dm['fc'], tr=dm['tr'], tc=dm['tc'],
                hidden=dm.get('hidden', False), promo=dm.get('promo'),
                fakeout=dm.get('fakeout', False)
            )
            
        if isinstance(action, EndTurn):
            transition_draft_turn(dgs)
            continue
            
        if isinstance(action, MovePiece):
            if dgs.get('hidden_count', 0) > 0 and getattr(action, 'fakeout', False) == False:
                transition_draft_turn(dgs)
            action.execute(dgs)
            
            if not action.hidden and not action.fakeout:
                dgs['normal_done'] = True
            
    dgs['drafting_mode'] = True
    return dgs
