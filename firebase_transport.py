import asyncio
import json
import time
import copy
import random
import string
import hashlib
import threading
from chess_logic import make_state, exec_move, end_turn, legal, serialize_state, can_afford, alg, deactivate_plies, \
    get_next_turn_from_queue, compare_turns, pop_next_turn_from_queue, process_next_queues, ice_king_interaction, register_predict_move, _register_revealed_trail
from draft_simulator import get_draft_state
from firebase_db import firebase_client
from event_recorder import get_recorder

def get_robust_state_hash(gs):
    """
    Computes a robust hash of the game state ignoring ephemeral fields and timestamps.
    """
    if not gs:
        return ""
    core = {
        "turn": gs.get("turn"),
        "turn_count": gs.get("turn_count"),
        "log_len": len(gs.get("log", [])),
        "pts": gs.get("pts"),
        "board": gs.get("board"),
        "hidden_count": gs.get("hidden_count"),
        "fakeout_count": gs.get("fakeout_count"),
        "game_over": gs.get("game_over"),
        "opponent_joined": gs.get("opponent_joined"),
        "game_started": gs.get("game_started"),
        "rematch_requested_by": gs.get("rematch_requested_by"),
        "online": gs.get("online"),
        "fakeout_mode_enabled": gs.get("fakeout_mode_enabled"),
        "ice_king_enabled": gs.get("ice_king_enabled"),
        "score_to_win": gs.get("score_to_win"),
        "draft_seq": gs.get("draft_seq")
    }
    core_str = json.dumps(core, sort_keys=True)
    return hashlib.md5(core_str.encode('utf-8')).hexdigest()

class MockWebsocket:
    def __init__(self):
        self.recorder = get_recorder('firebase_transport')
        self.queue = asyncio.Queue()
        self.loop = asyncio.get_running_loop()
        self.room_code = None
        self.color = None
        self.token = None
        self.gs = None
        self.last_handled_hash = None
        
    async def __aiter__(self):
        return self

    async def __anext__(self):
        msg = await self.queue.get()
        if msg is None:
            raise StopAsyncIteration
        return msg

    async def recv(self):
        msg = await self.queue.get()
        if msg is None:
            raise Exception("ConnectionClosed")
        return msg

    async def send(self, message):
        # Process outgoing message locally, then update Firebase if needed
        data = json.loads(message)
        self.recorder.record('send', message_type=data.get('type'), room_code=self.room_code, color=self.color)

        try:
            if data['type'] == 'create_room':
                self.room_code = ''.join(random.choices(string.ascii_uppercase, k=4))
                self.color = 'w'
                self.token = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
                self.gs = make_state()
                self.gs['created_at'] = time.time()
                self.gs['turn_start_snapshot'] = copy.deepcopy(self.gs)
                self.gs['tokens'] = {'w': self.token}
                self.gs['online'] = {'w': True, 'b': False}

                # Save to Firebase
                initial_state_json = json.dumps(serialize_state(self.gs, 'server'))
                success = await firebase_client.create_room(self.room_code, self.token, initial_state_json)
                if not success:
                    await self.queue.put(json.dumps({"type": "error", "message": "Erro 403: Permissão negada no banco de dados."}))
                    return

                # Start listening to firebase
                self._start_listening()

                await self.queue.put(json.dumps({
                    "type": "room_created", "room": self.room_code, "color": "w", "session_token": self.token
                }))

            elif data['type'] == 'join_room' or data['type'] == 'spectate_room':
                self.room_code = data['room'].upper()
                self.token = data.get('session_token') or ''.join(random.choices(string.ascii_letters + string.digits, k=16))
                
                is_spectate = (data['type'] == 'spectate_room')
                success, result = await firebase_client.join_room(self.room_code, self.token, spectate=is_spectate)
                
                # If join failed because room is full, but user is joining normally, ask if they want to spectate?
                # Actually, the user asked to "entrar apenas para assistir se a sala tiver cheia".
                # It would be cool if "join_room" automatically falls back to spectate if room is full.
                if not success and result == "Sala cheia" and not is_spectate:
                    # Automatically fallback to spectator
                    success, result = await firebase_client.join_room(self.room_code, self.token, spectate=True)

                if success:
                    self.color = result['color']
                    self._start_listening()
                    await self.queue.put(json.dumps({
                        "type": "room_joined", "room": self.room_code, "color": self.color,
                        "session_token": self.token, "reconnected": result.get('reconnected', False),
                        "game_over": result.get('game_over', False)
                    }))
                else:
                    await self.queue.put(json.dumps({"type": "error", "message": result}))

            elif data['type'] == 'leave_room':
                firebase_client.stop_polling()
                await self.queue.put(None)

            elif data['type'] == 'action':
                if not self.gs:
                    return
                action = data['action']
                color = self.color
                gs = self.gs
                needs_broadcast = False
                self.recorder.snapshot('action_received', gs, action=action, color=color, draft_moves=len(data.get('draft_moves', []) or []))

                # Apply exactly the same logic as server.py
                if action == 'set_fakeout_mode' and color == 'w':
                    gs['fakeout_mode_enabled'] = data.get('fakeout_mode_enabled', False)
                    needs_broadcast = True
                elif action == 'set_score_to_win' and color == 'w':
                    gs['score_to_win'] = data.get('score_to_win', False)
                    needs_broadcast = True
                elif action == 'set_ice_king' and color == 'w':
                    gs['ice_king_enabled'] = data.get('ice_king_enabled', False)
                    needs_broadcast = True
                elif action == 'start_game' and color == 'w' and gs.get('opponent_joined', False):
                    gs['game_started'] = True
                    needs_broadcast = True
                elif action == 'rematch_request':
                    gs['rematch_requested_by'] = color
                    needs_broadcast = True
                elif action == 'rematch_accept':
                    new_state = make_state()
                    new_state['created_at'] = time.time()
                    new_state['tokens'] = gs.get('tokens', {})
                    new_state['online'] = gs.get('online', {'w': True, 'b': True})
                    new_state['opponent_joined'] = True
                    new_state['game_started'] = True
                    new_state['turn_start_snapshot'] = copy.deepcopy(new_state)
                    self.gs = new_state
                    gs = self.gs
                    needs_broadcast = True
                elif action == 'rematch_decline':
                    gs['rematch_declined'] = True
                    needs_broadcast = True
                elif action == 'resign':
                    if not gs['game_over']:
                        gs['game_over'] = True
                        winner = "Pretas" if color == 'w' else "Brancas"
                        resigner = "As Brancas" if color == 'w' else "As Pretas"
                        gs['game_over_msg'] = f"{resigner} abandonaram. As {winner} venceram!"
                        needs_broadcast = True

                elif gs['turn'] == color:
                    if action == 'undo':
                        if 'turn_start_snapshot' in gs:
                            current_time = gs['time_left'].copy()
                            restored = copy.deepcopy(gs['turn_start_snapshot'])
                            restored['turn_start_snapshot'] = copy.deepcopy(gs['turn_start_snapshot'])
                            restored['time_left'] = current_time
                            self.gs = restored
                            gs = self.gs
                            needs_broadcast = True

                    elif action == 'end_turn':
                        dm = data.get('draft_moves', [])
                        q_key = f'next_queue_{color}'
                        self.recorder.record('end_turn_begin', room_code=self.room_code, color=color, draft_moves=len(dm or []), queue_key=q_key)

                        if gs.get('normal_done') or gs.get('hidden_count', 0) > 0:
                            next_a = get_next_turn_from_queue(gs, color)
                            self.recorder.record('next_queue_check', room_code=self.room_code, has_next=bool(next_a), current_actions=len(gs.get('current_turn_actions', []) or []))
                            if next_a:
                                if compare_turns(gs.get('current_turn_actions', []), next_a):
                                    if not isinstance(gs.get('draft_seq'), dict):
                                        gs['draft_seq'] = {'w': 0, 'b': 0}
                                    seq = gs['draft_seq'].get(color, 0)
                                    reward = 2 ** seq
                                    gs['draft_seq'][color] = seq + 1
                                    gs['pts'][color] = round(gs['pts'][color] + reward, 2)
                                else:
                                    if not isinstance(gs.get('draft_seq'), dict):
                                        gs['draft_seq'] = {'w': 0, 'b': 0}
                                    gs['pts'][color] = round(gs['pts'][color] - 1, 2)
                                    gs['draft_seq'][color] = 0
                                pop_next_turn_from_queue(gs, color)

                            if dm:
                                gs[q_key] = dm
                                for m in dm:
                                    pass

                            end_turn(gs)
                        else:
                            if dm:
                                gs[q_key] = dm
                                for m in dm:
                                    pass

                            if gs.get(q_key):
                                process_next_queues(gs)
                            else:
                                end_turn(gs)

                        clean_snapshot = copy.deepcopy(gs)
                        clean_snapshot.pop('turn_start_snapshot', None)
                        gs['turn_start_snapshot'] = clean_snapshot
                        needs_broadcast = True
                        self.recorder.snapshot('end_turn_complete', gs, room_code=self.room_code, color=color)

                    elif action == 'toggle_hidden':
                        if not gs['game_over']:
                            if not gs['normal_done']:
                                if can_afford(gs):
                                    gs['hidden_mode'] = not gs.get('hidden_mode', False)
                                    if gs.get('hidden_mode'):
                                        gs['fakeout_active'] = False
                                    needs_broadcast = True

                    elif action == 'toggle_fakeout':
                        from chess_logic import can_afford_fakeout
                        if not gs['normal_done'] and not gs['game_over'] and gs.get('fakeout_mode_enabled', False) and can_afford_fakeout(gs) and not gs.get('fakeout_used', False):
                            gs['fakeout_active'] = not gs.get('fakeout_active', False)
                            if gs['fakeout_active']:
                                gs['hidden_mode'] = False
                            needs_broadcast = True

                    elif action == 'conflict_resolve':
                        kind, cr2, cc3 = data['conflict']
                        if kind == 'src':
                            gs['board'][cr2][cc3] = None
                            my_cap = gs['captured_w'] if color == 'w' else gs['captured_b']
                            my_cap.discard((cr2, cc3))
                            ghost_type = 'hidden'
                            for h_dict in [gs.get('hidden_w', {}), gs.get('hidden_b', {})]:
                                to_remove = []
                                for tp, val in list(h_dict.items()):
                                    pub_pos = val.pub_pos if hasattr(val, 'pub_pos') else val[0]
                                    is_f = val.is_fakeout if hasattr(val, 'is_fakeout') else (val[3] if len(val) > 3 else False)
                                    if pub_pos == (cr2, cc3) or tp == (cr2, cc3):
                                        deactivate_plies(gs, val.plies if hasattr(val, 'plies') else (val[5] if len(val) > 5 else []))
                                        _register_revealed_trail(gs, val)
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
                            enemy_hid = gs['hidden_b'] if color == 'w' else gs['hidden_w']
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
                                _register_revealed_trail(gs, val)
                                if 'reveal_flashes' not in gs:
                                    gs['reveal_flashes'] = []
                                gs['reveal_flashes'].append([cr2, cc3, 'fakeout' if is_f else 'hidden'])
                        needs_broadcast = True

                    elif action == 'move':
                        fr, fc = data['fr'], data['fc']
                        tr, tc = data['tr'], data['tc']
                        promo = data.get('promo')

                        if not gs.get('normal_done'):
                            legals = legal(gs, fr, fc)
                            if (tr, tc) in legals:
                                if gs.get('hidden_mode') and not can_afford(gs):
                                    pass
                                else:
                                    from chess_logic import check_conflict
                                    conflict = check_conflict(gs, fr, fc, tr, tc)
                                    if conflict:
                                        # Resolve conflict exactly like the conflict_resolve action
                                        kind, cr2, cc3 = conflict
                                        if kind == 'src':
                                            gs['board'][cr2][cc3] = None
                                            my_cap = gs['captured_w'] if color == 'w' else gs['captured_b']
                                            my_cap.discard((cr2, cc3))
                                            ghost_type = 'hidden'
                                            for h_dict in [gs.get('hidden_w', {}), gs.get('hidden_b', {})]:
                                                to_remove = []
                                                for tp, val in list(h_dict.items()):
                                                    pub_pos = val.pub_pos if hasattr(val, 'pub_pos') else val[0]
                                                    is_f = val.is_fakeout if hasattr(val, 'is_fakeout') else (val[3] if len(val) > 3 else False)
                                                    if pub_pos == (cr2, cc3) or tp == (cr2, cc3):
                                                        deactivate_plies(gs, val.plies if hasattr(val, 'plies') else (val[5] if len(val) > 5 else []))
                                                        _register_revealed_trail(gs, val)
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
                                            enemy_hid = gs['hidden_b'] if color == 'w' else gs['hidden_w']
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
                                                deactivate_plies(gs, plies)
                                                _register_revealed_trail(gs, val)
                                                if is_f:
                                                    gs['log'].append(f"SYS_FAKEOUT|Peça revelada em {alg(cc3, cr2)}!")
                                                else:
                                                    gs['log'].append(f"SYS_HIDDEN|Peça revelada em {alg(cc3, cr2)}!")
                                                if 'reveal_flashes' not in gs:
                                                    gs['reveal_flashes'] = []
                                                gs['reveal_flashes'].append([cr2, cc3, 'fakeout' if is_f else 'hidden'])
                                        needs_broadcast = True
                                        res = False
                                    else:
                                        gesture_hidden = data.get('gesture_hidden', False)
                                        is_hidden = gs.get('hidden_mode', False) or gesture_hidden
                                        is_fakeout = gs.get('fakeout_active', False)
                                        res = exec_move(gs, fr, fc, tr, tc, hidden_move=is_hidden, promo=promo)
                                        if res:
                                            gs['hidden_mode'] = False
                                            gs['fakeout_active'] = False
                                            if 'current_turn_actions' not in gs:
                                                gs['current_turn_actions'] = []
                                            gs['current_turn_actions'].append({
                                                'type': 'move',
                                                'fr': fr, 'fc': fc, 'tr': tr, 'tc': tc,
                                                'promo': promo, 'hidden': is_hidden,
                                                'fakeout': is_fakeout
                                            })
                                    needs_broadcast = True
                            else:
                                asyncio.create_task(self.queue.put(json.dumps({
                                    "type": "state_update",
                                    "state": serialize_state(self.gs, self.color)
                                })))

                    elif action == 'confirm_draft':
                        if gs.get('locked_for_draft'):
                            gs['locked_for_draft'] = False
                            process_next_queues(gs)
                            needs_broadcast = True

                    elif action == 'predict_move':
                        fr, fc = data['fr'], data['fc']
                        tr, tc = data['tr'], data['tc']
                        promo = data.get('promo')

                        if gs.get('turn') == color and not gs.get('game_over', False):
                            legals = legal(gs, fr, fc)
                            if (tr, tc) in legals:
                                dm = data.get('draft_moves')
                                if dm:
                                    q_key = f"next_queue_{color}"
                                    gs[q_key] = dm
                                if register_predict_move(gs, color, fr, fc, tr, tc, promo, cost=0.2):
                                    needs_broadcast = True
                            else:
                                asyncio.create_task(self.queue.put(json.dumps({
                                    "type": "state_update",
                                    "state": serialize_state(self.gs, self.color)
                                })))

                    elif action == 'ice_king':
                        kr, kc = data['kr'], data['kc']
                        tr, tc = data['tr'], data['tc']
                        res = ice_king_interaction(gs, kr, kc, tr, tc)
                        if res:
                            needs_broadcast = True

                if needs_broadcast:
                    self._broadcast_state()
        except Exception as exc:
            self.recorder.dump('send_error', exc=exc, context={'room_code': self.room_code, 'color': self.color, 'message_type': data.get('type')})
            raise
    def _broadcast_state(self):
        # Update Firebase and local queue
        self.last_handled_hash = get_robust_state_hash(self.gs)
        state_json = json.dumps(serialize_state(self.gs, 'server'))
        self.recorder.snapshot('broadcast_state', self.gs, room_code=self.room_code, color=self.color)
        asyncio.create_task(firebase_client.update_state(self.room_code, state_json, self.token, self.color))
        asyncio.create_task(self.queue.put(json.dumps({
            "type": "state_update",
            "state": serialize_state(self.gs, self.color)
        })))
        
        # Clear ephemeral state after broadcast so it doesn't leak into next state
        self.gs['ghost_capture_flash'] = None
        self.gs['ghost_capture_type'] = None
        self.gs['reveal_flashes'] = []
        
    def _start_listening(self):
        def on_update(state_str):
            try:
                from chess_logic import deserialize_state
                state_dict = json.loads(state_str)
                self.recorder.record('on_update', room_code=self.room_code, state_keys=list(state_dict.keys())[:24])
                new_gs = deserialize_state(state_dict)
                
                # Prevent stale reads from overwriting local state
                if self.gs:
                    old_tc = self.gs.get('turn_count', 0)
                    new_tc = new_gs.get('turn_count', 0)
                    old_log_len = len(self.gs.get('log', []))
                    new_log_len = len(new_gs.get('log', []))
                    is_rematch = (self.gs.get('game_over') and not new_gs.get('game_over')) or (new_gs.get('created_at', 0) > self.gs.get('created_at', 0))
                    if not is_rematch and (new_tc < old_tc or (new_tc == old_tc and new_log_len < old_log_len)):
                        # Stale state from polling, ignore
                        return

                new_hash = get_robust_state_hash(new_gs)
                if self.last_handled_hash == new_hash:
                    # Ignore echo from our own broadcast
                    return
                self.last_handled_hash = new_hash

                self.gs = new_gs
                # Push to asyncio queue for the client to process
                asyncio.run_coroutine_threadsafe(
                    self.queue.put(json.dumps({
                        "type": "state_update",
                        "state": serialize_state(self.gs, self.color)
                    })),
                    self.loop
                )
                self.gs['ghost_capture_flash'] = None
                self.gs['ghost_capture_type'] = None
                self.gs['reveal_flashes'] = []
            except Exception as e:
                self.recorder.dump('state_update_error', exc=e, context={'room_code': self.room_code})
                print("Error in on_update", e)
                
        firebase_client.start_polling(on_update)

    async def close(self):
        firebase_client.stop_polling()
        await self.queue.put(None)
