# splitting_balls_pygame_random_spawns.py
# Neutrons (fast/slow), background heatmap (speed-based), graphene bars, manual bars
# NOTE: Press 'H' to toggle heat overlay on top for debugging/visibility.

import pygame
import random
import math
import time

# --- Config ------------------------------------------------------------------
WIDTH, HEIGHT = 1280, 720
MARGIN = 40
GRID_ROWS = 20
GRID_COLS = 40

BIG_R = 12
SMALL_R = 4

# Speeds
SPEED_BASE = 250.0
FAST_MULT = 1.8          # hızlı başlangıç çarpanı
SLOW_MULT = 1.0
SLOW_CONVERT_SPEED = SPEED_BASE * 1.10  # fast -> slow eşiği
VANISH_SPEED = SPEED_BASE * 0.20        # çok yavaşsa sil

# Spawn & life
SPLIT_COUNT = 3
MAX_NEUTRONS = 10000
NEUTRON_LIFETIME = 20.0

# Active node logic
BIG_COOLDOWN = 2.0
ACTIVE_RATIO = 0.3

# NEW: Black-shield nodes
BLACK_NODE_PROB = 0.01                 # split ÜRETİLDİYSE %x ihtimalle siyah moda geç
GRID_BLACK_COLOR = (10, 10, 10)        # siyah düğüm rengi

# Periodic spawns
RANDOM_SPAWNS_ON = True
SPAWN_INTERVAL = 0.3
SPAWN_INTERVAL_MIN = 0.1
SPAWN_INTERVAL_MAX = 1.0

# Manual bars (every 4 cols)
BAR_WIDTH = 6
BAR_COLOR = (203, 213, 225)
BAR_LENGTH_FACTOR = 1.0
BAR_MANUAL_SPEED = 320.0  # px/s ( [ / ] ile değişir )

# Graphene bars (fixed, between manual bars)
G_BAR_WIDTH = 5
G_BAR_COLOR = (75, 85, 99)

# Background heatmap (water/tiles)
HEAT_TILE_SCALE = 1.05       # kare kenarı = 1.05 * max(dx,dy)
HEAT_ALPHA = 170             # ↑ görünürlük (0..255)
HEAT_GAIN_K = 0.0035         # ↑ ısı artışı: Δh = K * hız * dt
HEAT_COOL_RATE = 0.1         # ↓ daha yavaş soğuma
HEAT_ON_TOP = False          # H ile değiş: True => ısı katmanını üstte çiz

# Suda yavaşlama (px/s^2)
WATER_DECEL_FAST = 250.0
WATER_DECEL_SLOW = 50.0

# Colors
BG_COLOR =  (31, 41, 55)
GRID_COLOR = (148, 163, 184)
GRID_COOLDOWN_COLOR = (100, 116, 139)
GRID_INACTIVE_COLOR = (51, 65, 85)

NEUTRON_SLOW_COLOR = (251, 191, 36)   # slow görünümü
NEUTRON_FAST_FILL = (251, 191, 36)    # fast iç dolgu
NEUTRON_FAST_OUTLINE = (0, 0, 0)      # fast kontur

# Heatmap gradient (mavi -> açık kırmızı -> koyu kırmızı)
HEAT_COLOR_COLD = (96, 165, 250)      # mavi
HEAT_COLOR_WARM = (255, 140, 140)     # açık kırmızı
HEAT_COLOR_HOT  = (178, 34, 34)       # koyu kırmızı

HUD_COLOR = (229, 231, 235)

# -----------------------------------------------------------------------------

def build_grid():
    usable_w = WIDTH - 2 * MARGIN
    usable_h = HEIGHT - 2 * MARGIN
    dx = usable_w / (GRID_COLS - 1)
    dy = usable_h / (GRID_ROWS - 1)
    nodes = []
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            x = MARGIN + c * dx
            y = MARGIN + r * dy
            active = random.random() < ACTIVE_RATIO
            nodes.append({
                'x': x, 'y': y,
                'next_ok': 0.0,
                'active': active,
                'black_shield': 0   # NEW: tek kullanımlık siyah kalkan (0/1)
            })
    if not any(n['active'] for n in nodes):
        random.choice(nodes)['active'] = True
    return nodes, dx, dy

def compute_manual_bars(dx):
    bars = []
    bar_len = int((HEIGHT - 2 * MARGIN) * BAR_LENGTH_FACTOR)
    center_y = HEIGHT // 2
    for c in range(3, GRID_COLS - 1, 4):  # (3,4), (7,8), ...
        x_left = MARGIN + c * dx
        x_right = MARGIN + (c + 1) * dx
        x_mid = 0.5 * (x_left + x_right)
        bars.append({'x': x_mid, 'center': center_y, 'length': bar_len, 'w': BAR_WIDTH})
    return bars

def compute_graphene_bars(manual_bars):
    g = []
    top = MARGIN - 12
    bot = HEIGHT - MARGIN + 12
    if not manual_bars:
        return g

    # x'e göre sırala (garanti)
    bars = sorted(manual_bars, key=lambda b: b['x'])

    # 1) Mevcut: ardışık manuel çubukların tam ortasına graphene
    for i in range(len(bars) - 1):
        x_mid = 0.5 * (bars[i]['x'] + bars[i + 1]['x'])
        g.append({'x': x_mid, 'y0': top, 'y1': bot, 'w': G_BAR_WIDTH})

    # 2) YENİ: uçlara da graphene
    left_edge = MARGIN
    right_edge = WIDTH - MARGIN
    x_left_edge = 0.5 * (left_edge + bars[0]['x'])           # sol kenar ile ilk manuel çubuk ortası
    x_right_edge = 0.5 * (right_edge + bars[-1]['x'])        # sağ kenar ile son manuel çubuk ortası

    g.insert(0, {'x': x_left_edge, 'y0': top, 'y1': bot, 'w': G_BAR_WIDTH})
    g.append(   {'x': x_right_edge,'y0': top, 'y1': bot, 'w': G_BAR_WIDTH})

    return g

def bar_span(b, offset, idx):
    """Çift indeksler (0,2,4,...) hareketli; tekler sabit."""
    off = offset if (idx % 2 == 0) else 0.0
    y0 = b['center'] - b['length'] / 2 + off
    y1 = b['center'] + b['length'] / 2 + off
    return y0, y1

def hits_vbar(x, y, bar_x, bar_w, y0, y1):
    halfw = bar_w * 0.5
    return (bar_x - halfw) <= x <= (bar_x + halfw) and y0 <= y <= y1

def polar(angle, mag):
    return math.cos(angle) * mag, math.sin(angle) * mag

def speed(vx, vy):
    return math.hypot(vx, vy)

def set_speed(n, new_s):
    s = speed(n['vx'], n['vy'])
    if s <= 1e-6:
        ang = random.random() * math.tau
        n['vx'], n['vy'] = polar(ang, new_s)
    else:
        k = new_s / s
        n['vx'] *= k
        n['vy'] *= k

def add_neutron(lst, x, y, angle, fast=True, init_speed=None):
    # hepsi hızlı başlar (fast=True), bölünme dahil
    spd = init_speed if init_speed is not None else (SPEED_BASE * (FAST_MULT if fast else SLOW_MULT))
    vx, vy = polar(angle, spd)
    lst.append({
        'x': x, 'y': y, 'vx': vx, 'vy': vy,
        'born': time.time(),
        'fast': fast
    })

def activate_random_inactive(grid, now):
    inactives = [g for g in grid if not g['active']]
    if inactives:
        pick = random.choice(inactives)
        pick['active'] = True
        pick['next_ok'] = now + BIG_COOLDOWN

# ---- Heatmap helpers ---------------------------------------------------------
def tile_index(x, y, dx, dy):
    """Eğer oyun alanındaysa, geçtiği kare (r,c) döndür; değilse None."""
    if not (MARGIN <= x <= WIDTH - MARGIN and MARGIN <= y <= HEIGHT - MARGIN):
        return None
    c = int((x - MARGIN) / dx)
    r = int((y - MARGIN) / dy)
    if 0 <= r < GRID_ROWS - 1 and 0 <= c < GRID_COLS - 1:
        return r, c
    return None

def lerp(a, b, t):
    return a + (b - a) * t

def lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return (int(lerp(c1[0], c2[0], t)),
            int(lerp(c1[1], c2[1], t)),
            int(lerp(c1[2], c2[2], t)))

def heat_to_color(h):
    """h: 0..1 -> mavi -> açık kırmızı -> koyu kırmızı."""
    h = max(0.0, min(1.0, h))
    if h < 0.55:
        t = h / 0.55
        return lerp_color(HEAT_COLOR_COLD, HEAT_COLOR_WARM, t)
    else:
        t = (h - 0.55) / 0.45
        return lerp_color(HEAT_COLOR_WARM, HEAT_COLOR_HOT, t)

# --- Main ---------------------------------------------------------------------
def main():
    pygame.init()
    pygame.display.set_caption("Neutron Sim — Heatmap (speed-based), Graphene & Manual Bars")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 18)

    grid, dx, dy = build_grid()
    manual_bars = compute_manual_bars(dx)
    graphene_bars = compute_graphene_bars(manual_bars)

    # Heat grid
    heat = [[0.0 for _ in range(GRID_COLS - 1)] for __ in range(GRID_ROWS - 1)]
    tile_side = HEAT_TILE_SCALE * max(dx, dy)

    neutrons = []
    paused = False
    running = True

    random_spawns_on = RANDOM_SPAWNS_ON
    next_spawn_time = time.time() + SPAWN_INTERVAL
    spawn_interval = SPAWN_INTERVAL

    # Manuel bar kontrolü (serbest hareket) + ısı katmanı konum seçimi
    bar_offset = 0.0
    heat_on_top = HEAT_ON_TOP

    def reset():
        neutrons.clear()
        for r in range(GRID_ROWS - 1):
            for c in range(GRID_COLS - 1):
                heat[r][c] = 0.0

    def can_spawn_manual():
        return len(neutrons) == 0

    def seed_center():
        if can_spawn_manual():
            add_neutron(neutrons, WIDTH/2, HEIGHT/2, random.random()*math.tau, fast=True)

    # --- Loop -----------------------------------------------------------------
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: running = False
                elif event.key == pygame.K_SPACE: paused = not paused
                elif event.key == pygame.K_r: reset()
                elif event.key == pygame.K_c: seed_center()
                elif event.key == pygame.K_t: random_spawns_on = not random_spawns_on
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS):
                    spawn_interval = min(SPAWN_INTERVAL_MAX, spawn_interval + 0.2)
                elif event.key == pygame.K_MINUS:
                    spawn_interval = max(SPAWN_INTERVAL_MIN, spawn_interval - 0.2)
                elif event.key == pygame.K_LEFTBRACKET:
                    globals()['BAR_MANUAL_SPEED'] = max(20.0, BAR_MANUAL_SPEED - 20.0)
                elif event.key == pygame.K_RIGHTBRACKET:
                    globals()['BAR_MANUAL_SPEED'] = min(1200.0, BAR_MANUAL_SPEED + 20.0)
                elif event.key == pygame.K_h:
                    heat_on_top = not heat_on_top  # ısı katmanını üstte/arkada göster
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if can_spawn_manual():
                    x, y = pygame.mouse.get_pos()
                    add_neutron(neutrons, x, y, random.random()*math.tau, fast=True)

        # ↑/↓ ile manuel bar hareketi
        keys = pygame.key.get_pressed()
        if not paused:
            move_dir = 0.0
            if keys[pygame.K_UP]: move_dir -= 1.0
            if keys[pygame.K_DOWN]: move_dir += 1.0
            if move_dir != 0.0 and manual_bars:
                speed_pixels = BAR_MANUAL_SPEED * (2.0 if (pygame.key.get_mods() & pygame.KMOD_SHIFT) else 1.0)
                bar_offset += move_dir * speed_pixels * dt

        if not paused:
            now = time.time()

            # periodic random spawns (FAST)
            if random_spawns_on and now >= next_spawn_time:
                rx = random.uniform(0, WIDTH)
                ry = random.uniform(0, HEIGHT)
                add_neutron(neutrons, rx, ry, random.random()*math.tau, fast=True)
                next_spawn_time = now + spawn_interval

            next_neutrons = []
            rsum2 = (BIG_R + SMALL_R) ** 2

            # --- physics
            for n in neutrons:
                # Konum
                n['x'] += n['vx'] * dt
                n['y'] += n['vy'] * dt

                # Manuel bar: her nötron yok olur
                hit_manual = False
                for i, b in enumerate(manual_bars):
                    y0, y1 = bar_span(b, bar_offset, i)
                    if hits_vbar(n['x'], n['y'], b['x'], b['w'], y0, y1):
                        hit_manual = True
                        break
                if hit_manual:
                    continue

                # Graphene: sadece FAST -> yansıtıp slow'a dönüştür
                if n['fast']:
                    hit_g = False
                    for gb in graphene_bars:
                        if hits_vbar(n['x'], n['y'], gb['x'], gb['w'], gb['y0'], gb['y1']):
                            hit_g = True
                            break
                    if hit_g:
                        n['vx'] = -n['vx']
                        n['fast'] = False
                        set_speed(n, SPEED_BASE * SLOW_MULT)
                        n['x'] += math.copysign(2.0, n['vx'])

                # Isı: hız bazlı ısı ekle + suda yavaşla
                idx = tile_index(n['x'], n['y'], dx, dy)
                if idx is not None:
                    r, c = idx
                    s_now = speed(n['vx'], n['vy'])
                    heat[r][c] = min(1.0, heat[r][c] + HEAT_GAIN_K * s_now * dt)

                    # suda yavaşlama
                    decel = WATER_DECEL_FAST if n['fast'] else WATER_DECEL_SLOW
                    s_new = max(0.0, s_now - decel * dt)
                    set_speed(n, s_new)

                    # fast -> slow eşiği
                    if n['fast'] and s_new <= SLOW_CONVERT_SPEED:
                        n['fast'] = False
                        set_speed(n, SPEED_BASE * SLOW_MULT)

                # Ömür / sınır
                alive = (now - n['born']) < NEUTRON_LIFETIME and -60 <= n['x'] <= WIDTH + 60 and -60 <= n['y'] <= HEIGHT + 60
                if not alive:
                    continue

                # Çok yavaşsa sil
                if speed(n['vx'], n['vy']) <= VANISH_SPEED:
                    continue

                # Büyük daire ile ETKİLEŞİM sadece SLOW
                if not n['fast']:
                    hit_i = -1
                    for i, g in enumerate(grid):
                        dxg = n['x'] - g['x']
                        dyg = n['y'] - g['y']
                        if dxg*dxg + dyg*dyg <= rsum2:
                            if g['active'] and now >= g['next_ok']:
                                hit_i = i
                            break
                    if hit_i >= 0:
                        g = grid[hit_i]

                        # NEW: siyah kalkan var mı? varsa bu tetiklemede split YAPMA.
                        suppressed = False
                        if g.get('black_shield', 0) > 0:
                            suppressed = True
                            g['black_shield'] = 0  # kalkan tüketildi

                        # Her durumda bu düğümü pasifleştir ve başka bir pasifi aktifleştir
                        g['active'] = False
                        g['next_ok'] = now + BIG_COOLDOWN
                        activate_random_inactive(grid, now)

                        if not suppressed:
                            # Normal: split üret (hepsi hızlı başlar)
                            for _ in range(SPLIT_COUNT):
                                ang = random.random() * math.tau
                                add_neutron(next_neutrons, n['x'], n['y'], ang,
                                            fast=True, init_speed=SPEED_BASE * FAST_MULT)
                            # NEW: split olduysa %5 ihtimalle siyah moda geç
                            if random.random() < BLACK_NODE_PROB:
                                g['black_shield'] = 1

                        # Bu nötron tüketildi
                        continue

                next_neutrons.append(n)

            if len(next_neutrons) > MAX_NEUTRONS:
                next_neutrons = next_neutrons[:MAX_NEUTRONS]
            neutrons = next_neutrons

            # Soğuma (bütün hücreler)
            for r in range(GRID_ROWS - 1):
                row = heat[r]
                for c in range(GRID_COLS - 1):
                    if row[c] > 0.0:
                        row[c] = max(0.0, row[c] - HEAT_COOL_RATE * dt)

        # --- Draw --------------------------------------------------------------
        screen.fill(BG_COLOR)

        # Heat overlay (arkada)
        def draw_heat():
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            side = int(tile_side)
            for r in range(GRID_ROWS - 1):
                y = int(MARGIN + r * dy + dy / 2 - side / 2)
                for c in range(GRID_COLS - 1):
                    x = int(MARGIN + c * dx + dx / 2 - side / 2)
                    h = heat[r][c]
                    if h <= 0:
                        continue
                    color = heat_to_color(h)
                    pygame.draw.rect(overlay, (*color, HEAT_ALPHA), pygame.Rect(x, y, side, side))
            screen.blit(overlay, (0, 0))

        if not heat_on_top:
            draw_heat()

        # Graphene bars (sabit)
        for gb in graphene_bars:
            rect = pygame.Rect(int(gb['x'] - gb['w'] * 0.5), int(gb['y0']),
                               int(gb['w']), int(gb['y1'] - gb['y0']))
            pygame.draw.rect(screen, G_BAR_COLOR, rect, border_radius=2)

        # Manual bars (offset / half movable)
        for i, b in enumerate(manual_bars):
            y0, y1 = bar_span(b, bar_offset, i)
            rect = pygame.Rect(int(b['x'] - b['w'] * 0.5), int(y0), int(b['w']), int(y1 - y0))
            pygame.draw.rect(screen, BAR_COLOR, rect, border_radius=3)

        # Grid nodes (büyük daireler)
        tnow = time.time()
        for g in grid:
            if g.get('black_shield', 0) > 0:
                col = GRID_BLACK_COLOR
            else:
                col = GRID_INACTIVE_COLOR if not g['active'] else (GRID_COOLDOWN_COLOR if tnow < g['next_ok'] else GRID_COLOR)
            pygame.draw.circle(screen, col, (int(g['x']), int(g['y'])), BIG_R)

        # İsteyenler için: ısı overlay üstte (debug/kontrast)
        if heat_on_top:
            draw_heat()

        # Neutrons — sadece FAST ve SLOW çiziyoruz (ara hız görünmez)
        fast_cnt = slow_cnt = 0
        for n in neutrons:
            if n['fast']:
                fast_cnt += 1
                pygame.draw.circle(screen, NEUTRON_FAST_OUTLINE, (int(n['x']), int(n['y'])), SMALL_R + 2)
                pygame.draw.circle(screen, NEUTRON_FAST_FILL, (int(n['x']), int(n['y'])), SMALL_R)
            else:
                slow_cnt += 1
                pygame.draw.circle(screen, NEUTRON_SLOW_COLOR, (int(n['x']), int(n['y'])), SMALL_R)

        total = GRID_ROWS * GRID_COLS
        active_cnt = sum(1 for g in grid if g['active'])

        hud = (
            f"Fast/Slow: {fast_cnt}/{slow_cnt}  Active: {active_cnt}/{total}  "
            f"Spawn={'ON' if random_spawns_on else 'OFF'} {spawn_interval:.1f}s  "
            f"Bars(4-col): MANUAL off={bar_offset:.0f}px spd={BAR_MANUAL_SPEED:.0f}px/s  "
            f"Graphene: {len(graphene_bars)}  HeatK={HEAT_GAIN_K:.4f}  "
            f"[↑/↓ move (Shift fast) | [ ] bar speed | Click/C | T | +/- spawn | H heat top | SPACE | R]"
        )
        screen.blit(font.render(hud, True, HUD_COLOR), (10, 10))

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()
