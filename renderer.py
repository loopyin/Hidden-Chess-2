import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from chess_logic import in_check, attacked, pc, opp

class VisualEffectsRenderer:
    @staticmethod
    def draw_freeze_overlay(screen, r: int, c: int, x: int, y: int, SQ: int, t_sec: float) -> None:
        import pygame
        # Camada cristalina semitransparente sobre a peça (+ casa)
        piece_overlay = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
        piece_overlay.fill((160, 210, 255, 55))
        screen.blit(piece_overlay, (x, y))

        # Orbiting small hexagonal crystals and snow
        orbit_r = SQ // 2.5
        center = (x + SQ // 2, y + SQ // 2)
        
        for i in range(3):
            angle = t_sec * 1.5 + i * (2 * math.pi / 3)
            cx = center[0] + math.cos(angle) * orbit_r
            cy = center[1] + math.sin(angle) * orbit_r
            
            hex_pts = []
            hex_size = 3
            for j in range(6):
                hx = cx + math.cos(j * math.pi / 3) * hex_size
                hy = cy + math.sin(j * math.pi / 3) * hex_size
                hex_pts.append((hx, hy))
            pygame.draw.polygon(screen, (200, 240, 255, 200), hex_pts)
        
        seed = hash((r, c, int(t_sec * 2)))
        rnd = random.Random(seed)
        for _ in range(4):
            sx = x + rnd.randint(0, SQ)
            sy = y + rnd.randint(0, SQ)
            alpha = int(255 * (0.5 + 0.5 * math.sin(t_sec * 10 + sx)))
            if alpha > 0:
                pygame.draw.circle(screen, (255, 255, 255, alpha), (sx, sy), 1)

    @staticmethod
    def draw_active_freeze_effects(screen, client_state: Dict[str, Any], SQ: int, BOARD_PX: int) -> None:
        import pygame
        if client_state.get('freeze_fx'):
            for fx in client_state['freeze_fx']:
                t = fx['t']
                dur = 2.0
                r, c = fx['r'], fx['c']
                val = fx.get('val', 0)
                
                fr_d, fc_d = 7 - r if client_state.get('flipped') else r, 7 - c if client_state.get('flipped') else c
                cx = fc_d * SQ + SQ // 2
                cy = fr_d * SQ + SQ // 2
                
                p = t / dur
                
                # Shockwave (circular translucent wave)
                if t < 0.6:
                    wave_p = t / 0.6
                    wave_r = int((SQ * 1.5) * (1.0 - (1.0 - wave_p)**3))
                    wave_alpha = int(255 * (1.0 - wave_p))
                    wave_surf = pygame.Surface((BOARD_PX, BOARD_PX), pygame.SRCALPHA)
                    pygame.draw.circle(wave_surf, (150, 220, 255, wave_alpha), (cx, cy), wave_r)
                    screen.blit(wave_surf, (0, 0))
                
                # Spiral particles
                if len(fx['particles']) < max(1, min(40, int(t * 80))):
                    for _ in range(3):
                        angle = random.uniform(0, math.pi * 2)
                        dist = random.uniform(5, SQ // 2)
                        fx['particles'].append({'a': angle, 'd': dist, 't': t, 'size': random.uniform(2, 4)})
                
                for part in fx['particles']:
                    pt = t - part['t']
                    if pt < 0: continue
                    # spiral upwards
                    part_a = part['a'] + pt * 5.0
                    part_d = part['d'] + pt * 30.0
                    px = cx + math.cos(part_a) * part_d
                    py = cy + math.sin(part_a) * part_d - pt * 60.0
                    p_alpha = max(0, min(255, int(255 * (1.0 - pt / 1.0))))
                    if p_alpha > 0:
                        psurf = pygame.Surface((10, 10), pygame.SRCALPHA)
                        pygame.draw.circle(psurf, (200, 240, 255, p_alpha), (5, 5), part['size'])
                        screen.blit(psurf, (int(px - 5), int(py - 5)))
                        
                # Floating points
                if val > 0 and t < 1.0:
                    float_p = t / 1.0
                    float_y = cy - int(float_p * 60)
                    float_alpha = int(255 * (1.0 - float_p**2))
                    scale = 1.0 + math.sin(float_p * math.pi) * 0.5
                    font = pygame.font.SysFont("Verdana", int(24 * scale), bold=True)
                    txt = font.render(f"+{val}", True, (50, 245, 105))
                    txt.set_alpha(float_alpha)
                    screen.blit(txt, txt.get_rect(center=(cx, float_y)))

        if client_state.get('unfreeze_fx'):
            for fx in client_state['unfreeze_fx']:
                t = fx['t']
                r, c = fx['r'], fx['c']
                val = fx.get('val', 0)
                fr_d, fc_d = 7 - r if client_state.get('flipped') else r, 7 - c if client_state.get('flipped') else c
                cx = fc_d * SQ + SQ // 2
                cy = fr_d * SQ + SQ // 2
                p = t / 1.0
                
                # Shattering fragments and small glowing particles spreading outwards
                if len(fx['particles']) == 0 and t < 0.1:
                    for _ in range(15):
                        angle = random.uniform(0, math.pi * 2)
                        dist = random.uniform(5, SQ // 1.5)
                        fx['particles'].append({'a': angle, 'd': dist, 't': t, 'size': random.uniform(1, 4), 'speed': random.uniform(40, 100)})

                for part in fx['particles']:
                    pt = t - part['t']
                    if pt < 0: continue
                    part_d = part['d'] + pt * part['speed']
                    px = cx + math.cos(part['a']) * part_d
                    py = cy + math.sin(part['a']) * part_d - pt * 20.0
                    p_alpha = max(0, min(255, int(255 * (1.0 - pt / 0.8))))
                    if p_alpha > 0:
                        psurf = pygame.Surface((10, 10), pygame.SRCALPHA)
                        if part['size'] > 2.5:
                            # Crystalline fragments
                            hex_pts = []
                            hex_size = part['size']
                            for j in range(6):
                                hx = 5 + math.cos(j * math.pi / 3 + t * 5) * hex_size
                                hy = 5 + math.sin(j * math.pi / 3 + t * 5) * hex_size
                                hex_pts.append((hx, hy))
                            pygame.draw.polygon(psurf, (180, 230, 255, p_alpha), hex_pts)
                        else:
                            # Glowing particles
                            pygame.draw.circle(psurf, (255, 255, 255, p_alpha), (5, 5), part['size'])
                        screen.blit(psurf, (int(px - 5), int(py - 5)))

                # Translucent circular wave spreading and fading out
                if t < 0.8:
                    wave_p = t / 0.8
                    wave_r = int((SQ * 1.5) * (1.0 - (1.0 - wave_p)**3))
                    wave_alpha = int(255 * (1.0 - wave_p))
                    wave_surf = pygame.Surface((BOARD_PX, BOARD_PX), pygame.SRCALPHA)
                    pygame.draw.circle(wave_surf, (200, 240, 255, wave_alpha), (cx, cy), wave_r, max(1, wave_alpha // 20))
                    screen.blit(wave_surf, (0, 0))

                # Quick residual glow sweeping the surface
                if t > 0.2 and t < 0.6:
                    glow_p = (t - 0.2) / 0.4
                    glow_y = int((fr_d * SQ + SQ) - glow_p * SQ)
                    glow_surf = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                    line_y = glow_y - (fr_d * SQ)
                    if 0 <= line_y < SQ:
                        pygame.draw.line(glow_surf, (255, 255, 255, int(150 * (1.0 - glow_p))), (0, line_y), (SQ, line_y), 3)
                        pygame.draw.circle(glow_surf, (255, 255, 255, int(100 * (1.0 - glow_p))), (SQ//2, line_y), SQ//2)
                        screen.blit(glow_surf, (fc_d * SQ, fr_d * SQ))

                # Floating points "-X"
                if val > 0 and t < 1.0:
                    float_p = t / 1.0
                    float_y = cy - int(float_p * 60)
                    float_alpha = int(255 * (1.0 - float_p**2))
                    scale = 1.0 + math.sin(float_p * math.pi) * 0.5
                    font = pygame.font.SysFont("Verdana", int(24 * scale), bold=True)
                    txt = font.render(f"-{val}", True, (255, 120, 120))
                    txt.set_alpha(float_alpha)
                    screen.blit(txt, txt.get_rect(center=(cx, float_y)))

@dataclass
class RenderCell:
    r: int
    c: int
    piece: Optional[str] = None
    ghost_alpha: int = 255
    ghost_piece: Optional[str] = None
    overlay_color: Optional[Tuple[int, int, int]] = None
    overlay_alpha: int = 0
    is_check: bool = False
    is_last_move: bool = False
    is_selected: bool = False
    is_legal: bool = False
    is_legal_capture: bool = False
    is_threatened: bool = False
    blue_path_alpha: int = 0
    orange_path_alpha: int = 0
    is_fake_residual: bool = False
    next_chain_alpha: int = 0
    is_next_dest: bool = False
    next_dest_piece: Optional[str] = None
    is_frozen: bool = False
    
class BoardRenderer:
    @staticmethod
    def get_render_state(gs: Dict[str, Any], client_state: Dict[str, Any], abs_b, tb, my_hidden: Dict[Tuple[int, int], Any], show_hidden: bool) -> List[List[RenderCell]]:
        grid = [[RenderCell(r=r, c=c) for c in range(8)] for r in range(8)]
        
        last = gs.get('last_move')
        if last:
            grid[last[0]][last[1]].is_last_move = True
            grid[last[2]][last[3]].is_last_move = True

        my_color = client_state['my_color']
        check_sq = None
        for r in range(8):
            for c in range(8):
                if abs_b[r][c] == my_color + 'K':
                    if in_check(abs_b, my_color):
                        check_sq = (r, c)
                        grid[r][c].is_check = True

        sel = client_state.get('selected')
        if sel:
            sel_r, sel_c = sel
            # Adjust selection if fakeout is active and the selected piece is hidden
            if gs.get('fakeout_active') and sel in my_hidden:
                val = my_hidden[sel]
                if val.pub_pos:
                    grid[val.pub_pos[0]][val.pub_pos[1]].is_selected = True
            else:
                grid[sel_r][sel_c].is_selected = True

        # Legal moves
        for (lr, lc) in client_state.get('legal_sq', []):
            grid[lr][lc].is_legal = True
            grid[lr][lc].is_legal_capture = bool(tb[lr][lc] or (gs.get('ep') and gs['ep'] == (lr, lc)))

        # Threatened allied pieces
        if my_color in ('w', 'b'):
            enemy_color = opp(my_color)
            for r in range(8):
                for c in range(8):
                    if tb[r][c] and pc(tb[r][c]) == my_color:
                        if attacked(tb, r, c, enemy_color):
                            grid[r][c].is_threatened = True

        # Next queues
        all_nexts = (gs.get('next_queue_w') or []) + (gs.get('next_queue_b') or []) + (client_state.get('draft_moves') or [])
        next_chains = []
        current_loc_to_chain = {}
        next_dest_piece = {}
        for m in all_nexts:
            if m.get('type') == 'end_turn': continue
            mfr, mfc = m.get('fr'), m.get('fc')
            mtr, mtc = m.get('tr'), m.get('tc')
            if mfr is None or mfc is None: continue
            promo = m.get('promo')
            piece = None
            if (mfr, mfc) in current_loc_to_chain:
                chain = current_loc_to_chain.pop((mfr, mfc))
                chain.append((mtr, mtc))
                current_loc_to_chain[(mtr, mtc)] = chain
                piece = next_dest_piece.pop((mfr, mfc))
            else:
                chain = [(mfr, mfc), (mtr, mtc)]
                current_loc_to_chain[(mtr, mtc)] = chain
                next_chains.append(chain)
                piece = tb[mfr][mfc]
                if not piece:
                    piece = abs_b[mfr][mfc]
            if piece and promo:
                piece = piece[0] + promo
            next_dest_piece[(mtr, mtc)] = piece

        for chain in next_chains:
            if not chain: continue
            dest = chain[-1]
            grid[dest[0]][dest[1]].is_next_dest = True
            if dest in next_dest_piece:
                grid[dest[0]][dest[1]].next_dest_piece = next_dest_piece[dest]
            alpha = 127
            for pos in reversed(chain[:-1]):
                if grid[pos[0]][pos[1]].next_chain_alpha < alpha:
                    grid[pos[0]][pos[1]].next_chain_alpha = alpha
                alpha = max(10, alpha // 2)

        # Hidden & Fakeout ink trails
        if show_hidden:
            for t_pos, val in my_hidden.items():
                is_f = val.is_fakeout
                # 1. Blue path
                if val.path:
                    N_blue = len(val.path)
                    for idx, pos in enumerate(val.path):
                        ratio = (idx + 1) / N_blue
                        alpha = int(25 + 95 * ratio)
                        if alpha > grid[pos[0]][pos[1]].blue_path_alpha:
                            grid[pos[0]][pos[1]].blue_path_alpha = alpha
                # 2. Orange path
                if is_f:
                    f_path = val.fakeout_path if val.fakeout_path else val.path
                    if f_path:
                        N_orange = len(f_path)
                        for idx, pos in enumerate(f_path):
                            ratio = (idx + 1) / N_orange
                            alpha = int(25 + 95 * ratio)
                            if alpha > grid[pos[0]][pos[1]].orange_path_alpha:
                                grid[pos[0]][pos[1]].orange_path_alpha = alpha

        # Piece assignments
        board = gs['board']
        anim = client_state.get('anim')
        for r in range(8):
            for c in range(8):
                p = board[r][c]
                if p:
                    # Skip rendering if it's currently animating to this spot
                    if anim and p == anim.get('p') and anim.get('tr') == r and anim.get('tc') == c:
                        pass
                    else:
                        grid[r][c].piece = p
                        if show_hidden:
                            for t_pos, val in my_hidden.items():
                                if val.pub_pos == (r, c):
                                    grid[r][c].ghost_alpha = 76
                                    if val.is_fakeout:
                                        grid[r][c].is_fake_residual = True
                                    break
                                    
                # Set my secret pieces
                if show_hidden and (r, c) in my_hidden:
                    val = my_hidden[(r, c)]
                    grid[r][c].ghost_piece = val.piece
                    # if it's animating from here, it shouldn't be drawn, but we handle that in the drawing logic if needed.

                # Set frozen state
                if (r, c) in gs.get('frozen_pieces', set()):
                    grid[r][c].is_frozen = True

        return grid
