with open('client.py', 'r') as f:
    content = f.read()

target = """    revealed_trails = gs.get('revealed_trails', [])
    if revealed_trails:
        trail_surf = pygame.Surface((WIN_W, BOARD_PX), pygame.SRCALPHA)
        for trail in revealed_trails:
            if not isinstance(trail, dict):
                continue
            raw_path = trail.get('path', [])
            path = expand_path(raw_path)
            if not path or len(path) <= 1:
                continue

            is_f = trail.get('is_fakeout', False)
            color_rgb = (245, 120, 20) if is_f else (30, 110, 255)
            trail_anchor = trail.get('pub_pos')
            is_highlighted = False
            if active_trail_sq:
                is_highlighted = (
                    active_trail_sq in path or
                    (trail_anchor is not None and active_trail_sq == tuple(trail_anchor))
                )
            alpha_mod = 1.0 if not is_any_trail_highlighted else (1.0 if is_highlighted else 0.25)
            thickness = pulse_thickness if is_highlighted else 5
            N = len(path)

            for i in range(N - 1):
                p1 = path[i]
                p2 = path[i + 1]
                fr_disp = 7 - p1[0] if flipped else p1[0]
                fc_disp = 7 - p1[1] if flipped else p1[1]
                tr_disp = 7 - p2[0] if flipped else p2[0]
                tc_disp = 7 - p2[1] if flipped else p2[1]
                start_pos = (fc_disp * SQ + SQ // 2, fr_disp * SQ + SQ // 2)
                end_pos = (tc_disp * SQ + SQ // 2, tr_disp * SQ + SQ // 2)
                ratio = (i + 1) / max(1, N - 1)
                line_alpha = int((90 + 130 * ratio) * alpha_mod)
                color = (*color_rgb, line_alpha)
                pygame.draw.line(trail_surf, color, start_pos, end_pos, thickness)
                pygame.draw.circle(trail_surf, color, start_pos, thickness + 1)
                if i == N - 2:
                    pygame.draw.circle(trail_surf, color, end_pos, thickness + 1)

            # Traveling sphere, matching the hidden/fakeout trails.
            t = (pygame.time.get_ticks() % 2250) / 2250.0
            total_segs = len(path) - 1
            seg = max(0, min(int(t * total_segs), total_segs - 1))
            sub_t = t * total_segs - seg
            p1 = path[seg]
            p2 = path[seg + 1]
            fr_disp = 7 - p1[0] if flipped else p1[0]
            fc_disp = 7 - p1[1] if flipped else p1[1]
            tr_disp = 7 - p2[0] if flipped else p2[0]
            tc_disp = 7 - p2[1] if flipped else p2[1]
            start_pos = (fc_disp * SQ + SQ // 2, fr_disp * SQ + SQ // 2)
            end_pos = (tc_disp * SQ + SQ // 2, tr_disp * SQ + SQ // 2)
            dot_x = int(start_pos[0] + (end_pos[0] - start_pos[0]) * sub_t)
            dot_y = int(start_pos[1] + (end_pos[1] - start_pos[1]) * sub_t)
            dot_radius = 4
            dot_surf = pygame.Surface((40, 40), pygame.SRCALPHA)
            pygame.draw.circle(dot_surf, (*color_rgb, int(60 * alpha_mod)), (20, 20), dot_radius + 8)
            pygame.draw.circle(dot_surf, (*color_rgb, int(150 * alpha_mod)), (20, 20), dot_radius + 4)
            pygame.draw.circle(dot_surf, (*color_rgb, int(255 * alpha_mod)), (20, 20), dot_radius)
            pygame.draw.circle(dot_surf, (100, 180, 255, int(255 * alpha_mod)) if not is_f else (255, 160, 50, int(255 * alpha_mod)), (20, 20), dot_radius - 2)
            screen.blit(dot_surf, (dot_x - 20, dot_y - 20))

        screen.blit(trail_surf, (0, 0))"""

replacement = """    revealed_trails = gs.get('revealed_trails', [])
    if revealed_trails:
        for trail in revealed_trails:
            if not isinstance(trail, dict):
                continue
            raw_path = trail.get('path', [])
            path = expand_path(raw_path)
            if not path or len(path) <= 1:
                continue

            is_f = trail.get('is_fakeout', False)
            trail_anchor = trail.get('pub_pos')
            is_highlighted = False
            if active_trail_sq:
                is_highlighted = (
                    active_trail_sq in path or
                    (trail_anchor is not None and active_trail_sq == tuple(trail_anchor))
                )
            alpha_mod = 1.0 if not is_any_trail_highlighted else (1.0 if is_highlighted else 0.25)
            thickness = pulse_thickness if is_highlighted else 4
            N = len(path)
            
            trail_surf = pygame.Surface((WIN_W, BOARD_PX), pygame.SRCALPHA)
            for i in range(N - 1):
                p1 = path[i]
                p2 = path[i + 1]
                fr_disp = 7 - p1[0] if flipped else p1[0]
                fc_disp = 7 - p1[1] if flipped else p1[1]
                tr_disp = 7 - p2[0] if flipped else p2[0]
                tc_disp = 7 - p2[1] if flipped else p2[1]
                start_pos = (fc_disp * SQ + SQ // 2, fr_disp * SQ + SQ // 2)
                end_pos = (tc_disp * SQ + SQ // 2, tr_disp * SQ + SQ // 2)
                ratio = (i + 1) / (N - 1)
                line_alpha = int((45 + 135 * ratio) * alpha_mod)
                color = (245, 120, 20, line_alpha) if is_f else (30, 110, 255, line_alpha)
                pygame.draw.line(trail_surf, color, start_pos, end_pos, thickness)
                pygame.draw.circle(trail_surf, color, start_pos, thickness + 1)
                if i == N - 2:
                    pygame.draw.circle(trail_surf, color, end_pos, thickness + 1)

            screen.blit(trail_surf, (0, 0))

            # Traveling sphere, matching the hidden/fakeout trails.
            t = (pygame.time.get_ticks() % 2250) / 2250.0
            total_segs = len(path) - 1
            seg = max(0, min(int(t * total_segs), total_segs - 1))
            sub_t = t * total_segs - seg
            p1 = path[seg]
            p2 = path[seg + 1]
            fr_disp = 7 - p1[0] if flipped else p1[0]
            fc_disp = 7 - p1[1] if flipped else p1[1]
            tr_disp = 7 - p2[0] if flipped else p2[0]
            tc_disp = 7 - p2[1] if flipped else p2[1]
            start_pos = (fc_disp * SQ + SQ // 2, fr_disp * SQ + SQ // 2)
            end_pos = (tc_disp * SQ + SQ // 2, tr_disp * SQ + SQ // 2)
            dot_x = int(start_pos[0] + (end_pos[0] - start_pos[0]) * sub_t)
            dot_y = int(start_pos[1] + (end_pos[1] - start_pos[1]) * sub_t)
            dot_radius = 4
            dot_surf = pygame.Surface((40, 40), pygame.SRCALPHA)
            
            if is_f:
                pygame.draw.circle(dot_surf, (200, 100, 0, int(60 * alpha_mod)), (20, 20), dot_radius + 8)
                pygame.draw.circle(dot_surf, (245, 120, 20, int(150 * alpha_mod)), (20, 20), dot_radius + 4)
                pygame.draw.circle(dot_surf, (245, 120, 20, int(255 * alpha_mod)), (20, 20), dot_radius)
                pygame.draw.circle(dot_surf, (255, 160, 50, int(255 * alpha_mod)), (20, 20), dot_radius - 2)
            else:
                pygame.draw.circle(dot_surf, (0, 100, 255, int(60 * alpha_mod)), (20, 20), dot_radius + 8)
                pygame.draw.circle(dot_surf, (0, 150, 255, int(150 * alpha_mod)), (20, 20), dot_radius + 4)
                pygame.draw.circle(dot_surf, (0, 100, 255, int(255 * alpha_mod)), (20, 20), dot_radius)
                pygame.draw.circle(dot_surf, (100, 180, 255, int(255 * alpha_mod)), (20, 20), dot_radius - 2)
                
            screen.blit(dot_surf, (dot_x - 20, dot_y - 20))"""

if target in content:
    with open('client.py', 'w') as f:
        f.write(content.replace(target, replacement))
    print("Patched trails!")
else:
    print("Not found trails!")
