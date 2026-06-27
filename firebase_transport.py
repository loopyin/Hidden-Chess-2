import asyncio
import json
import time
import copy
import random
import string
import threading
from chess_logic import make_state, exec_move, end_turn, legal, serialize_state, can_afford, alg, deactivate_plies, \
    get_next_turn_from_queue, compare_turns, pop_next_turn_from_queue, process_next_queues, ice_king_interaction
from draft_simulator import get_draft_state
from firebase_db import firebase_client

class MockWebsocket:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.loop = asyncio.get_running_loop()
        self.room_code = None
        self.color = None
        self.token = None
        self.gs = None
        
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
            initial_state_json = json.dumps(serialize_state(self.gs, 'w'))
            success = await firebase_client.create_room(self.room_code, self.token, initial_state_json)
            if not success:
                await self.queue.put(json.dumps({"type": "error", "message": "Erro 403: Permissão negada no banco de dados."}))
                return
            
            # Start listening to firebase
            self._start_listening()
            
            await self.queue.put(json.dumps({
                "type": "room_created", "room": self.room_code, "color": "w", "session_token": self.token
            }))

        elif data['type'] == 'join_room':
            self.room_code = data['room'].upper()
            self.token = data.get('session_token') or ''.join(random.choices(string.ascii_letters + string.digits, k=16))
            
            success, result = await firebase_client.join_room(self.room_code, self.token)
            if success:
                self.color = result['color']
                self._start_listening()
                # Join will be completed when the first state arrives or we can trigger it immediately
                await self.queue.put(json.dumps({
                    "type": "room_joined", "room": self.room_code, "color": self.color, 
                    "session_token": self.token, "reconnected": result.get('reconnected', False)
                }))
            else:
                await self.queue.put(json.dumps({"type": "error", "message": result}))

        elif data['type'] == 'leave_room':
            firebase_client.stop_polling()
            await self.queue.put(None)

        elif data['type'] == 'action':
            if not self.gs: return
            action = data['action']
            color = self.color
            gs = self.gs
            needs_broadcast = False
            
            # Apply exactly the same logic as server.py
            if action == 'set_fakeout_mode' and color == 'w':
                gs['fakeout_mode_enabled'] = data.get('fakeout_mode_enabled', False)
                needs_broadcast = True
            elif action == 'set_disable_undo' and color == 'w':
                gs['disable_undo_placeholder'] = data.get('disable_undo_placeholder', False)
                needs_broadcast = True
            elif action == 'set_score_to_win' and color == 'w':
                gs['score_to_win'] = data.get('score_to_win', False)
                needs_broadcast = True
            elif action == 'set_ice_king' and color == 'w':
                gs['ice_king_enabled'] = data.get('ice_king_enabled', False)
                needs_broadcast = True
            elif action == 'start_game' and color == 'w' and gs.get('opponent_joined', False):
                gs['game_started'] = True
                gs['fakeout_mode_enabled'] = True
                gs['disable_undo_placeholder'] = True
                gs['score_to_win'] = True
                gs['ice_king_enabled'] = True
                needs_broadcast = True
            elif action == 'rematch_request':
                gs['rematch_requested_by'] = color
                needs_broadcast = True
            elif action == 'rematch_accept':
                new_state = make_state()
                new_state['created_at'] = gs.get('created_at', time.time())
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
                if action == 'undo' and gs.get('disable_undo_placeholder', False):
                    pass
                elif action == 'undo':
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

                    if gs.get('normal_done') or gs.get('hidden_count', 0) > 0:
                        next_a = get_next_turn_from_queue(gs, color)
                        if next_a:
                            if compare_turns(gs.get('current_turn_actions', []), next_a):
                                gs['pts'][color] += 1
                            else:
                                gs['pts'][color] -= 1
                            pop_next_turn_from_queue(gs, color)
                        
                        if dm:
                            if q_key not in gs: gs[q_key] = []
                            gs[q_key].extend(dm)
                            for m in dm:
                                if m.get('type') == 'move':
                                    htxt = "[Fakeout] " if m.get('fakeout') else "[Sombra] " if m.get('hidden') else ""
                                    note_msg = f"{htxt}{alg(m['fc'], m['fr'])} -> {alg(m['tc'], m['tr'])}"
                                    gs['log'].append(f"NEXT|{color}|{note_msg}")
                        
                        end_turn(gs)
                    else:
                        if dm:
                            if q_key not in gs: gs[q_key] = []
                            gs[q_key].extend(dm)
                            for m in dm:
                                if m.get('type') == 'move':
                                    htxt = "[Fakeout] " if m.get('fakeout') else "[Sombra] " if m.get('hidden') else ""
                                    note_msg = f"{htxt}{alg(m['fc'], m['fr'])} -> {alg(m['tc'], m['tr'])}"
                                    gs['log'].append(f"NEXT|{color}|{note_msg}")
                        
                        if gs.get(q_key):
                            process_next_queues(gs)
                        else:
                            end_turn(gs)
                    
                    clean_snapshot = copy.deepcopy(gs)
                    clean_snapshot.pop('turn_start_snapshot', None)
                    gs['turn_start_snapshot'] = clean_snapshot
                    needs_broadcast = True
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
                            if 'reveal_flashes' not in gs:
                                gs['reveal_flashes'] = []
                            gs['reveal_flashes'].append([cr2, cc3, 'fakeout' if is_f else 'hidden'])
                    needs_broadcast = True
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
                                pass
                            else:
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
                                needs_broadcast = True
                                gs['ghost_capture_flash'] = None
                                gs['ghost_capture_type'] = None
                                gs['reveal_flashes'] = []

                elif action == 'ice_king' and gs.get('ice_king_enabled', False) and gs.get('disable_undo_placeholder', False):
                    kr, kc = data['kr'], data['kc']
                    tr, tc = data['tr'], data['tc']
                    res = ice_king_interaction(gs, kr, kc, tr, tc)
                    if res:
                        needs_broadcast = True
                        gs['ghost_capture_flash'] = None
                        gs['ghost_capture_type'] = None
                        gs['reveal_flashes'] = []
            
            if needs_broadcast:
                self._broadcast_state()

    def _broadcast_state(self):
        # Update Firebase and local queue
        state_json = json.dumps(serialize_state(self.gs, self.color))
        asyncio.create_task(firebase_client.update_state(self.room_code, state_json, self.token, self.color))
        asyncio.create_task(self.queue.put(json.dumps({
            "type": "state_update",
            "state": serialize_state(self.gs, self.color)
        })))
        
    def _start_listening(self):
        def on_update(state_str):
            try:
                from chess_logic import deserialize_state
                state_dict = json.loads(state_str)
                # If the state from Firebase has changes we need (like opponent moved, or joined)
                # We deserialize and update our gs
                new_gs = deserialize_state(state_dict)
                self.gs = new_gs
                # Push to asyncio queue for the client to process
                asyncio.create_task(
                    self.queue.put(json.dumps({
                        "type": "state_update",
                        "state": state_dict
                    }))
                )
            except Exception as e:
                print("Error in on_update", e)
                
        firebase_client.start_polling(on_update)

    async def close(self):
        firebase_client.stop_polling()
        await self.queue.put(None)
