class Action:
    def execute(self, gs):
        raise NotImplementedError
    
    def post_execute(self, gs, client_state, play_sound_fn):
        pass
    
    def to_dict(self):
        raise NotImplementedError

class MovePiece(Action):
    def __init__(self, fr, fc, tr, tc, hidden=False, promo=None, fakeout=False):
        self.fr = fr
        self.fc = fc
        self.tr = tr
        self.tc = tc
        self.hidden = hidden
        self.promo = promo
        self.fakeout = fakeout

    def execute(self, gs):
        from chess_logic import exec_move
        if self.fakeout:
            gs['fakeout_active'] = True
        return exec_move(gs, self.fr, self.fc, self.tr, self.tc, hidden_move=self.hidden, promo=self.promo)
    
    def post_execute(self, gs, client_state, play_sound_fn):
        # Auto-trigger next if it's a Normal or Hidden move, NOT a Fakeout
        if not self.fakeout:
            # Replicating the "Next" button click logic
            # This logic needs to be available here, or in a shared utility.
            # For now, let's assume we can trigger the logic.
            # Wait, I cannot call end_turn here, as requested.
            pass

    def to_dict(self):
        return {
            'type': 'move',
            'fr': self.fr,
            'fc': self.fc,
            'tr': self.tr,
            'tc': self.tc,
            'hidden': self.hidden,
            'promo': self.promo,
            'fakeout': self.fakeout
        }

class EndTurn(Action):
    def execute(self, gs):
        from chess_logic import end_turn
        end_turn(gs)
        return True

    def to_dict(self):
        return {'type': 'end_turn'}

def deserialize_action(data):
    tipo = data.get('type')
    if tipo == 'move':
        return MovePiece(
            fr=data['fr'], fc=data['fc'], tr=data['tr'], tc=data['tc'],
            hidden=data.get('hidden', False),
            promo=data.get('promo'),
            fakeout=data.get('fakeout', False)
        )
    elif tipo == 'end_turn':
        return EndTurn()
    return None
