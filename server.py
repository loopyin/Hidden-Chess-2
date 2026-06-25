import asyncio
import json
import websockets
import random
import string
import os
import time
import copy
import traceback
from chess_logic import make_state, exec_move, end_turn, legal, serialize_state, can_afford, alg, deactivate_plies, \
    get_next_turn_from_queue, compare_turns, pop_next_turn_from_queue, process_next_queues, ice_king_interaction
from draft_simulator import get_draft_state

games = {}
players = {}
room_timers = {}
active_timers = set()


def generate_room_code():
    """Generates a random 4-letter uppercase code."""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase, k=4))
        if code not in games:
            return code


async def room_timer(room_code):
    """Background task, timing is removed so this is a no-op."""
    while room_code in games:
        await asyncio.sleep(10)


async def cleanup_stale_rooms():
    """Background task to remove abandoned, unstarted rooms to prevent memory leaks."""
    while True:
        await asyncio.sleep(300)
        now = time.time()

        stale = [
            code for code, gs in list(games.items())
            if not gs['game_started'] and (now - gs.get('created_at', now)) > 600
        ]
        
        # Also clean up games older than 72 hours even if started
        stale_started = [
            code for code, gs in list(games.items())
            if gs['game_started'] and (now - gs.get('created_at', now)) > 259200
        ]

        for code in stale + stale_started:
            del games[code]
            print(f"Cleaned up stale room: {code}")


async def broadcast_state(room_code):
    from debug_utils import check_invariants, log_minimal_snapshot
    try:
        state = games[room_code]
        log_minimal_snapshot(state, "broadcast")
        check_invariants(state)
        for ws, info in list(players.items()):
            if info[0] == room_code:
                target_color = info[1]

                if state['turn'] != target_color and 'turn_start_snapshot' in state:
                    safe_state = copy.deepcopy(state['turn_start_snapshot'])
                    safe_state['time_left'] = state['time_left']
                    safe_state['game_over'] = state['game_over']
                    safe_state['game_over_msg'] = state['game_over_msg']
                    safe_state['rematch_requested_by'] = state.get('rematch_requested_by')
                    safe_state['rematch_declined'] = state.get('rematch_declined')
                    safe_state['opponent_left'] = state.get('opponent_left', False)
                    safe_state['game_started'] = state['game_started']

                    serialized = serialize_state(safe_state, player_color=target_color)
                else:
                    queue_moves = state.get(f'next_queue_{target_color}', [])
                    dgs = get_draft_state(state, queue_moves) if target_color == state['turn'] else None
                    serialized = serialize_state(state, player_color=target_color, dgs=dgs)

                msg = {"type": "state_update", "state": serialized}
                try:
                    await ws.send(json.dumps(msg))

                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception as e:
                    print(f"Failed to send state to a player in {room_code}:")
                    traceback.print_exc()

    except Exception as e:
        print(f"Broadcast error safely caught in room {room_code}:")
        traceback.print_exc()


async def handler(websocket):
    try:
        async for message in websocket:
            try:
                data = json.loads(message)

                if data['type'] == 'create_room':
                    room_code = generate_room_code()
                    new_state = make_state()
                    new_state['created_at'] = time.time()
                    new_state['turn_start_snapshot'] = copy.deepcopy(new_state)
                    games[room_code] = new_state
                    session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
                    games[room_code]['tokens'] = {'w': session_token}
                    games[room_code]['online'] = {'w': True, 'b': False}
                    players[websocket] = (room_code, 'w')
                    await websocket.send(json.dumps({"type": "room_created", "room": room_code, "color": "w", "session_token": session_token}))

                elif data['type'] == 'join_room':
                    room_code = data['room'].upper()
                    token = data.get('session_token')
                    
                    if room_code in games:
                        gs = games[room_code]
                        if gs.get('is_live_mode'):
                            await websocket.send(json.dumps({"type": "error", "message": "Esta é uma Sala Live. Entre pelo Modo Live."}))
                            continue
                        
                        # Reconnection logic
                        if token and 'tokens' in gs:
                            if gs['tokens'].get('w') == token:
                                players[websocket] = (room_code, 'w')
                                gs['online']['w'] = True
                                gs['opponent_left'] = False
                                await websocket.send(json.dumps({"type": "room_joined", "room": room_code, "color": "w", "session_token": token, "reconnected": True}))
                                await broadcast_state(room_code)
                                continue
                            elif gs['tokens'].get('b') == token:
                                players[websocket] = (room_code, 'b')
                                gs['online']['b'] = True
                                gs['opponent_left'] = False
                                await websocket.send(json.dumps({"type": "room_joined", "room": room_code, "color": "b", "session_token": token, "reconnected": True}))
                                await broadcast_state(room_code)
                                continue
                        
                        # Normal join if room isn't full (doesn't have 'b' token yet)
                        if 'b' not in gs.get('tokens', {}):
                            session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
                            players[websocket] = (room_code, 'b')
                            if 'tokens' not in gs: gs['tokens'] = {}
                            if 'online' not in gs: gs['online'] = {}
                            gs['tokens']['b'] = session_token
                            gs['online']['b'] = True
                            gs['opponent_joined'] = True
                            if room_code in room_timers:
                                room_timers[room_code].cancel()
                                active_timers.discard(room_timers[room_code])
                            await websocket.send(json.dumps({"type": "room_joined", "room": room_code, "color": "b", "session_token": session_token}))
                            await broadcast_state(room_code)
                        else:
                            await websocket.send(json.dumps({"type": "error", "message": "Sala não encontrada ou cheia."}))
                    else:
                        await websocket.send(json.dumps({"type": "error", "message": "Sala não encontrada ou cheia."}))

                elif data['type'] == 'create_live_room':
                    room_code = generate_room_code()
                    new_state = make_state()
                    new_state['created_at'] = time.time()
                    new_state['turn_start_snapshot'] = copy.deepcopy(new_state)
                    new_state['is_live_mode'] = True
                    games[room_code] = new_state
                    session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
                    games[room_code]['tokens'] = {'live_1': session_token}
                    games[room_code]['online'] = {'live_1': True}
                    players[websocket] = (room_code, 'live')
                    await websocket.send(json.dumps({"type": "room_created", "room": room_code, "color": "live", "session_token": session_token}))

                elif data['type'] == 'join_live_room':
                    room_code = data['room'].upper()
                    if room_code in games and games[room_code].get('is_live_mode'):
                        gs = games[room_code]
                        session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
                        token_key = f'live_{len(gs.get("tokens", {})) + 1}'
                        players[websocket] = (room_code, 'live')
                        if 'tokens' not in gs: gs['tokens'] = {}
                        if 'online' not in gs: gs['online'] = {}
                        gs['tokens'][token_key] = session_token
                        gs['online'][token_key] = True
                        gs['opponent_joined'] = True
                        await websocket.send(json.dumps({"type": "room_joined", "room": room_code, "color": "live", "session_token": session_token}))
                        await broadcast_state(room_code)
                    else:
                        await websocket.send(json.dumps({"type": "error", "message": "Sala Live não encontrada."}))

                elif data['type'] == 'leave_room':
                    room_code, color = players.get(websocket, (None, None))
                    if room_code and room_code in games:
                        gs = games[room_code]
                        in_room = [ws for ws, p in players.items() if p[0] == room_code and ws != websocket]
                        if not gs['game_started']:
                            if gs.get('is_live_mode'):
                                if len(in_room) == 0:
                                    del games[room_code]
                                    if room_code in room_timers:
                                        room_timers[room_code].cancel()
                                        active_timers.discard(room_timers[room_code])
                                        del room_timers[room_code]
                                else:
                                    pass # People are still in the live room lobby
                            else:
                                for opp_ws in in_room:
                                    try:
                                        await opp_ws.send(
                                            json.dumps({"type": "error", "message": "O oponente saiu do lobby."}))
                                    except websockets.exceptions.ConnectionClosed:
                                        pass
                                del games[room_code]

                                if room_code in room_timers:
                                    room_timers[room_code].cancel()
                                    active_timers.discard(room_timers[room_code])
                                    del room_timers[room_code]
                        else:
                            if 'online' in gs and color:
                                # For live mode, color is 'live', which marks all live viewers offline? 
                                # Better to just not care for live mode since reconnect works nicely.
                                gs['online'][color] = False
                            
                            if not gs.get('is_live_mode'):
                                gs['opponent_left'] = True
                            await broadcast_state(room_code)
                    players.pop(websocket, None)

                elif data['type'] == 'action':
                    room_code, color = players.get(websocket, (None, None))
                    if not room_code or room_code not in games:
                        continue

                    gs = games[room_code]
                    action = data['action']

                    if action == 'set_fakeout_mode':
                        if color == 'w' or gs.get('is_live_mode'):
                            gs['fakeout_mode_enabled'] = data.get('fakeout_mode_enabled', False)
                            await broadcast_state(room_code)
                        continue

                    elif action == 'set_disable_undo':
                        if color == 'w' or gs.get('is_live_mode'):
                            gs['disable_undo_placeholder'] = data.get('disable_undo_placeholder', False)
                            await broadcast_state(room_code)
                        continue

                    elif action == 'set_score_to_win':
                        if color == 'w' or gs.get('is_live_mode'):
                            gs['score_to_win'] = data.get('score_to_win', False)
                            await broadcast_state(room_code)
                        continue

                    elif action == 'set_ice_king':
                        if color == 'w' or gs.get('is_live_mode'):
                            gs['ice_king_enabled'] = data.get('ice_king_enabled', False)
                            await broadcast_state(room_code)
                        continue

                    elif action == 'start_game':
                        if (color == 'w' or gs.get('is_live_mode')) and (gs.get('opponent_joined', False) or gs.get('is_live_mode')):
                            gs['game_started'] = True
                            if room_code in room_timers:
                                room_timers[room_code].cancel()
                                active_timers.discard(room_timers[room_code])
                            timer_task = asyncio.create_task(room_timer(room_code))
                            room_timers[room_code] = timer_task
                            active_timers.add(timer_task)
                            timer_task.add_done_callback(active_timers.discard)
                            await broadcast_state(room_code)
                        continue

                    if action == 'rematch_request':
                        gs['rematch_requested_by'] = color
                        await broadcast_state(room_code)
                        continue

                    elif action == 'rematch_accept':
                        new_state = make_state()
                        new_state['created_at'] = gs.get('created_at', time.time())
                        new_state['tokens'] = gs.get('tokens', {})
                        new_state['online'] = gs.get('online', {'w': True, 'b': True})
                        new_state['opponent_joined'] = True
                        new_state['game_started'] = True
                        new_state['turn_start_snapshot'] = copy.deepcopy(new_state)
                        games[room_code] = new_state

                        if room_code in room_timers:
                            room_timers[room_code].cancel()
                            active_timers.discard(room_timers[room_code])

                        timer_task = asyncio.create_task(room_timer(room_code))
                        room_timers[room_code] = timer_task
                        active_timers.add(timer_task)
                        timer_task.add_done_callback(active_timers.discard)
                        await broadcast_state(room_code)
                        continue

                    elif action == 'rematch_decline':
                        gs['rematch_declined'] = True
                        await broadcast_state(room_code)
                        continue

                    if action == 'resign':
                        if not gs['game_over']:
                            gs['game_over'] = True
                            if gs.get('is_live_mode'):
                                gs['game_over_msg'] = "Jogo encerrado!"
                            else:
                                winner = "Pretas" if color == 'w' else "Brancas"
                                resigner = "As Brancas" if color == 'w' else "As Pretas"
                                gs['game_over_msg'] = f"{resigner} abandonaram. As {winner} venceram!"
                            await broadcast_state(room_code)
                        continue

                    if not gs.get('is_live_mode') and gs['turn'] != color:
                        continue

                    if gs.get('is_live_mode'):
                        effective_color = gs['turn']
                    else:
                        effective_color = color

                    if action == 'undo' and gs.get('disable_undo_placeholder', False):
                        continue

                    if action == 'undo':
                        if 'turn_start_snapshot' in gs:
                            current_time = gs['time_left'].copy()
                            restored_state = copy.deepcopy(gs['turn_start_snapshot'])
                            restored_state['turn_start_snapshot'] = copy.deepcopy(gs['turn_start_snapshot'])
                            restored_state['time_left'] = current_time

                            games[room_code] = restored_state
                            await broadcast_state(room_code)

                    elif action == 'end_turn':
                        if gs.get('disable_undo_placeholder', False):
                            pass
                        dm = data.get('draft_moves', [])
                        q_key = f'next_queue_{effective_color}'

                        if gs.get('normal_done') or gs.get('hidden_count', 0) > 0:
                            # Manual move was made. Check for matching with queue.
                            next_a = get_next_turn_from_queue(gs, effective_color)
                            if next_a:
                                if compare_turns(gs.get('current_turn_actions', []), next_a):
                                    gs['pts'][effective_color] += 1
                                else:
                                    gs['pts'][effective_color] -= 1
                                pop_next_turn_from_queue(gs, effective_color)
                            
                            # Invalidate everything before additions if we want strictly Next B to remain?
                            # User said: "limpa Next A e mantém o resto da fila (Next B)".
                            # So I pop Next A and then maybe clear the rest if they didn't match?
                            # Wait: "Se você decidir fazer um movimento manual... limpa sua fila... limpa Next A e mantém o resto da fila (Next B)."
                            # This means Next A is GONE, Next B remains.
                            
                            if dm:
                                # Add new drafts after processing the queue invalidation
                                if q_key not in gs: gs[q_key] = []
                                gs[q_key].extend(dm)
                                for m in dm:
                                    if m.get('type') == 'move':
                                        htxt = "[Fakeout] " if m.get('fakeout') else "[Sombra] " if m.get('hidden') else ""
                                        note_msg = f"{htxt}{alg(m['fc'], m['fr'])} -> {alg(m['tc'], m['tr'])}"
                                        gs['log'].append(f"NEXT|{effective_color}|{note_msg}")
                            
                            end_turn(gs)
                        else:
                            # No manual move, execute from queue
                            if dm:
                                if q_key not in gs: gs[q_key] = []
                                gs[q_key].extend(dm)
                                for m in dm:
                                    if m.get('type') == 'move':
                                        htxt = "[Fakeout] " if m.get('fakeout') else "[Sombra] " if m.get('hidden') else ""
                                        note_msg = f"{htxt}{alg(m['fc'], m['fr'])} -> {alg(m['tc'], m['tr'])}"
                                        gs['log'].append(f"NEXT|{effective_color}|{note_msg}")
                            
                            if gs.get(q_key):
                                process_next_queues(gs)
                            else:
                                end_turn(gs)
                        
                        clean_snapshot = copy.deepcopy(gs)
                        clean_snapshot.pop('turn_start_snapshot', None)
                        games[room_code]['turn_start_snapshot'] = clean_snapshot
                        await broadcast_state(room_code)
                        gs['ghost_capture_flash'] = None
                        gs['ghost_capture_type'] = None
                        gs['reveal_flashes'] = []

                    elif action == 'toggle_hidden':
                        if not gs['game_over']:
                            if not gs['normal_done'] and gs['hidden_count'] == 0:
                                if gs['turn_count'] > 1 and can_afford(gs):
                                    gs['hidden_mode'] = not gs.get('hidden_mode', False)
                                    if gs.get('hidden_mode'):
                                        gs['fakeout_active'] = False
                                    await broadcast_state(room_code)

                    elif action == 'toggle_fakeout':
                        from chess_logic import can_afford_fakeout
                        if not gs['normal_done'] and not gs['game_over'] and gs.get('fakeout_mode_enabled', False) and can_afford_fakeout(gs) and not gs.get('fakeout_used', False):
                            gs['fakeout_active'] = not gs.get('fakeout_active', False)
                            if gs['fakeout_active']:
                                gs['hidden_mode'] = False
                            await broadcast_state(room_code)

                    elif action == 'conflict_resolve':
                        kind, cr2, cc3 = data['conflict']
                        if kind == 'src':
                            gs['board'][cr2][cc3] = None
                            my_cap = gs['captured_w'] if effective_color == 'w' else gs['captured_b']
                            my_cap.discard((cr2, cc3))
                            ghost_type = 'hidden'
                            # Deactivate and clean associated fakeout/shadow plies
                            for h_dict in [gs.get('hidden_w', {}), gs.get('hidden_b', {})]:
                                to_remove = []
                                for tp, val in list(h_dict.items()):
                                    pub_pos = val.pub_pos if hasattr(val, 'pub_pos') else val[0]
                                    is_f = val.is_fakeout if hasattr(val, 'is_fakeout') else (val[3] if len(val) > 3 else False)
                                    if pub_pos == (cr2, cc3) or tp == (cr2, cc3):
                                        deactivate_plies(gs, val.plies if hasattr(val, 'plies') else (val[5] if len(val) > 5 else []))
                                        if is_f:
                                            ghost_type = 'fakeout'
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
                            enemy_hid = gs['hidden_b'] if effective_color == 'w' else gs['hidden_w']
                            val = enemy_hid.pop((cr2, cc3), None)
                            if val:
                                if hasattr(val, 'pub_pos'):
                                    pub_pos, hp = val.pub_pos, val.piece
                                    is_f = val.is_fakeout
                                    plies = val.plies 
                                else:
                                    pub_pos, hp = val[0], val[1]
                                    is_f = val[3] if len(val) > 3 else False
                                    plies = val[5] if len(val) > 5 else []
                                if pub_pos: gs['board'][pub_pos[0]][pub_pos[1]] = None
                                gs['board'][cr2][cc3] = hp
                                enemy_cap = gs['captured_w'] if color == 'w' else gs['captured_b']
                                enemy_cap.discard((cr2, cc3))
                                if is_f:
                                    gs['log'].append(f"SYS_FAKEOUT|Peça revelada em {alg(cc3, cr2)}!")
                                else:
                                    gs['log'].append(f"SYS_HIDDEN|Peça revelada em {alg(cc3, cr2)}!")
                                
                                deactivate_plies(gs, plies)
                                if 'reveal_flashes' not in gs:
                                    gs['reveal_flashes'] = []
                                gs['reveal_flashes'].append([cr2, cc3, 'fakeout' if is_f else 'hidden'])
                        await broadcast_state(room_code)
                        gs['ghost_capture_flash'] = None
                        gs['ghost_capture_type'] = None
                        gs['reveal_flashes'] = []

                    elif action == 'move':
                        fr, fc = data['fr'], data['fc']
                        tr, tc = data['tr'], data['tc']
                        promo = data.get('promo')

                        if not gs.get('normal_done'):
                            legals = legal(gs, fr, fc)
                            if (tr, tc) in legals:
                                if gs.get('hidden_mode') and not can_afford(gs):
                                    continue

                                gesture_hidden = data.get('gesture_hidden', False) and gs.get('disable_undo_placeholder', False)
                                is_hidden = gs.get('hidden_mode', False) or gesture_hidden
                                is_fakeout = gs.get('fakeout_active', False)
                                res = exec_move(gs, fr, fc, tr, tc, hidden_move=is_hidden, promo=promo)
                                if res:
                                    if 'current_turn_actions' not in gs: gs['current_turn_actions'] = []
                                    gs['current_turn_actions'].append({
                                        'type': 'move',
                                        'fr': fr, 'fc': fc, 'tr': tr, 'tc': tc,
                                        'promo': promo, 'hidden': is_hidden,
                                        'fakeout': is_fakeout
                                    })
                                await broadcast_state(room_code)
                                gs['ghost_capture_flash'] = None
                                gs['ghost_capture_type'] = None
                                gs['reveal_flashes'] = []

                    elif action == 'ice_king' and gs.get('ice_king_enabled', False) and gs.get('disable_undo_placeholder', False):
                        kr, kc = data['kr'], data['kc']
                        tr, tc = data['tr'], data['tc']
                        res = ice_king_interaction(gs, kr, kc, tr, tc)
                        if res:
                            await broadcast_state(room_code)
                            gs['ghost_capture_flash'] = None
                            gs['ghost_capture_type'] = None
                            gs['reveal_flashes'] = []

            except json.JSONDecodeError:
                pass
            except Exception as e:
                print(f"Action processing error safely caught:")
                traceback.print_exc()

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        room_code, color = players.pop(websocket, (None, None))
        if room_code and room_code in games:
            gs = games[room_code]
            if 'online' in gs and color:
                gs['online'][color] = False
                
            in_room = [p for p in players.values() if p[0] == room_code]
            if not in_room and not gs.get('game_started', False):
                del games[room_code]

                if room_code in room_timers:
                    room_timers[room_code].cancel()
                    active_timers.discard(room_timers[room_code])
                    del room_timers[room_code]
            elif gs.get('game_started', False):
                gs['opponent_left'] = True
                asyncio.create_task(broadcast_state(room_code))


async def main():
    port = int(os.environ.get("WS_PORT", 3000))
    print(f"Starting Shadow Chess websocket server on 0.0.0.0:{port}")
    asyncio.create_task(cleanup_stale_rooms())
    async with websockets.serve(
            handler, "0.0.0.0", port,
            ping_interval=259200, ping_timeout=259200,
            max_size=65536,  # 64KB
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
