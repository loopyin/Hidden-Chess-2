with open('client.py', 'r') as f:
    content = f.read()

target = """                            if is_piece_double_click:
                                is_hidden = client_state.get('draft_hidden') if client_state.get('drafting') else gs.get('hidden_mode')
                                is_fakeout = client_state.get('draft_fakeout') if client_state.get('drafting') else gs.get('fakeout_active')
                                
                                if is_my_casca:
                                    if not is_fakeout:
                                        if is_hidden:
                                            await MechanicsManager.execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound, None)
                                        await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                        client_state['selected'] = (r, c)
                                    elif is_fakeout:
                                        await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                        client_state['selected'] = (r, c)
                                else:
                                    if not is_hidden and not is_fakeout:
                                        await MechanicsManager.execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound, None)
                                        client_state['selected'] = (r, c)
                                    elif is_hidden:
                                        await MechanicsManager.execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound, None)
                                        await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                        client_state['selected'] = (r, c)
                                    elif is_fakeout:
                                        await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                        client_state['selected'] = (r, c)
                            elif is_piece_triple_click:
                                is_hidden = client_state.get('draft_hidden') if client_state.get('drafting') else gs.get('hidden_mode')
                                is_fakeout = client_state.get('draft_fakeout') if client_state.get('drafting') else gs.get('fakeout_active')
                                
                                if is_hidden:
                                    await MechanicsManager.execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound, None)
                                    await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                    client_state['selected'] = (r, c)
                                elif is_fakeout:
                                    if not is_my_casca:
                                        await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                    client_state['selected'] = (r, c)
                                elif not is_hidden and not is_fakeout:
                                    await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                    client_state['selected'] = (r, c)"""

replacement = """                            if is_piece_double_click:
                                is_hidden = client_state.get('draft_hidden') if client_state.get('drafting') else gs.get('hidden_mode')
                                is_fakeout = client_state.get('draft_fakeout') if client_state.get('drafting') else gs.get('fakeout_active')
                                
                                if is_my_casca:
                                    if not is_fakeout:
                                        if is_hidden:
                                            await MechanicsManager.execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound, None)
                                        await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                    client_state['selected'] = (r, c)
                                else:
                                    if not is_hidden and not is_fakeout:
                                        await MechanicsManager.execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound, None)
                                        client_state['selected'] = (r, c)
                                    elif is_hidden:
                                        await MechanicsManager.execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound, None)
                                        await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                        client_state['selected'] = (r, c)
                                    elif is_fakeout:
                                        await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                        client_state['selected'] = (r, c)
                            elif is_piece_triple_click:
                                is_hidden = client_state.get('draft_hidden') if client_state.get('drafting') else gs.get('hidden_mode')
                                is_fakeout = client_state.get('draft_fakeout') if client_state.get('drafting') else gs.get('fakeout_active')
                                
                                if is_hidden:
                                    await MechanicsManager.execute_toggle_hidden(gs, client_state, is_local, websocket, play_sound, None)
                                    await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                    client_state['selected'] = (r, c)
                                elif is_fakeout:
                                    if not is_my_casca:
                                        await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                    client_state['selected'] = (r, c)
                                elif not is_hidden and not is_fakeout:
                                    await MechanicsManager.execute_toggle_fakeout(gs, client_state, is_local, websocket, play_sound, None)
                                    client_state['selected'] = (r, c)"""

if target in content:
    with open('client.py', 'w') as f:
        f.write(content.replace(target, replacement))
    print("Patched click logic!")
else:
    print("Not found click logic!")
