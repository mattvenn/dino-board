#!/usr/bin/env python3
"""Route the DinoLight board. Run with KiCad's Python, one stage at a time, after tools/build_board.py:

    $KPY tools/route_board.py strip     LED strip by rule: supply rail, ground strip and vias, data hops
    $KPY tools/route_board.py dsn       write build/pcb/route.dsn for the autorouter (ground left out)
    java -jar ~/.kicad-mcp/freerouting.jar -de build/pcb/route.dsn -do build/pcb/route.ses -mp 40
    $KPY tools/route_board.py ses       bring the autorouter's tracks back into the board
    $KPY tools/route_board.py dsn-ground   the same again with ground included, then the autorouter and ses again
    $KPY tools/route_board.py pour      ground plane and pours on all four layers, pour-free areas, fill

The LED strip cell, in each LED's own frame (x along the edge towards the next LED, d = depth in from the edge):

    LED pads at d 1.46: DIN x -1.8, VDD -0.45, DOUT +0.575, GND +1.8
    100 nF standing radially under the VDD pad: supply pad at d 3.0, ground pad at d 3.96
    VDD pad -> capacitor -> stub at x -1.25 -> supply rail on the parts side at d 5.6
    GND pad -> via at d 2.65; capacitor ground -> via at d 4.62; both into a ground strip on the show face
    DOUT -> down to d 3.35 -> along to the next LED's DIN
"""
import math
import os
import sys

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'outline'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import make_outline as mo
import touch_block as tb

BOARD = os.path.join(ROOT, 'dinolight.kicad_pcb')
WORK = os.path.join(ROOT, 'build', 'pcb')
MIRROR, YOFF = 240.0, 10.0
mm, to_mm = pcbnew.FromMM, pcbnew.ToMM
RAIL_D, DATA_D, GND_VIA_D, CAP_VIA_D, STUB_X = 5.6, 3.35, 2.65, 4.62, -1.25
STRIP = (0.6, 5.05)                      # ground strip on the show face, depth range
BAND = (5.5, 11.5)                       # the touch slider's band (as in build_board.py)
W_SIGNAL, W_LINK, W_RAIL, VIA, DRILL = 0.2, 0.4, 0.6, 0.5, 0.3
POWER_NETS = ['+3V3', '+BATT', 'VBUS', 'VLED', 'BAT_P1', 'BAT_P1F', 'BAT_P2', 'BAT_RAW']
W_POWER = 0.4
N_LED = mo.N_LED
W_SIGNAL_AUTO = 0.15                     # the board's default track width, used by the autorouter
STITCH = 4.0                             # grid for the vias that join the ground pours
# Four layers: parts side / ground plane / inner signals / show face. Tracks go on the parts side and the
# inner signal layer; the show face is left to the touch copper, the LED ground strip and ground pour, and
# takes a track only where the patch router finds no other way.
PLANE, INNER = pcbnew.In1_Cu, pcbnew.In2_Cu
OUTER = (pcbnew.F_Cu, pcbnew.B_Cu)
ALL_CU = (pcbnew.F_Cu, PLANE, INNER, pcbnew.B_Cu)
ROUTE_LAYERS = (pcbnew.F_Cu, INNER, pcbnew.B_Cu)
NEAR_SHOW = (INNER, pcbnew.B_Cu)         # the show face and the layer 0.2 mm behind it


def B(x, y):
    return (MIRROR - x, y + YOFF)


def vec(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def chain(points):
    ch = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in points:
        ch.Append(mm(x), mm(y))
    ch.SetClosed(True)
    return ch


def fps(board):
    return {f.GetReference(): f for f in board.GetFootprints()}


def pad(fp, number):
    p = [q for q in fp.Pads() if q.GetNumber() == number][0].GetPosition()
    return (to_mm(p.x), to_mm(p.y))


def track(board, a, b, width, net, layer=pcbnew.F_Cu):
    if math.dist(a, b) < 1e-4:
        return
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(vec(*a))
    t.SetEnd(vec(*b))
    t.SetWidth(mm(width))
    t.SetLayer(layer)
    t.SetNet(net)
    board.Add(t)


def via(board, at, net):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(vec(*at))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    try:
        v.SetWidth(pcbnew.F_Cu, mm(VIA))
    except TypeError:
        v.SetWidth(mm(VIA))
    v.SetDrill(mm(DRILL))
    v.SetNet(net)
    board.Add(v)


def band_polygon(d0, d1, s0=0.0, s1=None, step=1.5, ext=0.0):
    """a strip following the spine edge, in BOARD mm; ext carries it on past both ends, along the edge"""
    s1 = mo.spine_len if s1 is None else s1
    n = max(2, int((s1 - s0) / step))

    def end(s, d, e):
        x, y, ang = mo.at(mo.SPINE, s, d)
        return (x + e * math.cos(math.radians(ang)), y + e * math.sin(math.radians(ang)))

    top = [mo.at(mo.SPINE, s0 + (s1 - s0) * k / n, d0)[:2] for k in range(n + 1)]
    bot = [mo.at(mo.SPINE, s0 + (s1 - s0) * k / n, d1)[:2] for k in range(n, -1, -1)]
    if ext:
        top = [end(s0, d0, -ext)] + top + [end(s1, d0, ext)]
        bot = [end(s1, d1, ext)] + bot + [end(s0, d1, -ext)]
    return [B(*p) for p in top + bot]


# ------------------------------------------------------------------------------------ stage: strip
def stage_strip():
    board = pcbnew.LoadBoard(BOARD)
    if len(board.GetTracks()):
        raise SystemExit('the board already has tracks: rebuild it with build_board.py first')
    f = fps(board)
    net = lambda name: board.FindNet(name)
    vled, gnd = net('VLED'), net('GND')
    frames = []
    for i in range(1, N_LED + 1):
        led = f['D%d' % i]
        th = math.radians(led.GetOrientationDegrees())
        ex, n = (math.cos(th), -math.sin(th)), (math.sin(th), math.cos(th))
        o = led.GetPosition()
        ox, oy = to_mm(o.x), to_mm(o.y)
        frames.append(lambda x, d, ox=ox, oy=oy, ex=ex, n=n: (ox + n[0] * (1.46 - d) + ex[0] * x, oy + n[1] * (1.46 - d) + ex[1] * x))
    for i in range(N_LED):
        L = frames[i]
        led, cap = f['D%d' % (i + 1)], f['C%d' % (11 + i)]
        c1, c2 = pad(cap, '1'), pad(cap, '2')
        # supply: LED VDD -> capacitor -> stub -> rail
        track(board, pad(led, '2'), c1, W_LINK, vled)
        track(board, c1, L(STUB_X, 3.0), W_LINK, vled)
        track(board, L(STUB_X, 3.0), L(STUB_X, RAIL_D), W_LINK, vled)
        if i + 1 < N_LED:
            track(board, L(STUB_X, RAIL_D), frames[i + 1](STUB_X, RAIL_D), W_RAIL, vled)
        # ground: one via at the LED's ground pad, one at the capacitor
        track(board, pad(led, '4'), L(1.8, GND_VIA_D), W_LINK, gnd)
        via(board, L(1.8, GND_VIA_D), gnd)
        track(board, c2, L(-0.45, CAP_VIA_D), W_LINK, gnd)
        via(board, L(-0.45, CAP_VIA_D), gnd)
        # data out to the next LED
        if i + 1 < N_LED:
            dnet = net('SPINE_%d' % (i + 1))
            nxt = frames[i + 1]
            pts = [pad(led, '3'), L(0.575, DATA_D), L(2.75, DATA_D), nxt(-2.6, DATA_D), nxt(-1.8, DATA_D), pad(f['D%d' % (i + 2)], '1')]
            for a, b in zip(pts, pts[1:]):
                track(board, a, b, W_SIGNAL, dnet)
    # the LED ground vias chained together on the show face, so the strip is one connected piece of ground
    # whatever else is known about it
    chain_pts = []
    for i in range(N_LED):
        chain_pts += [frames[i](-0.45, CAP_VIA_D), frames[i](1.8, GND_VIA_D)]
    for a, b in zip(chain_pts, chain_pts[1:]):
        track(board, a, b, 0.3, gnd, pcbnew.B_Cu)
    touch_block(board, f)
    tail_link(board, f)
    accelerometer(board, f)
    pressure(board, f)
    snout_link(board, f)
    # ground strip on the show face, under the LED row and outboard of the touch slider
    g = pcbnew.PCB_SHAPE(board)
    g.SetShape(pcbnew.SHAPE_T_POLY)
    ps = pcbnew.SHAPE_POLY_SET()
    ps.AddOutline(chain(band_polygon(STRIP[0], STRIP[1], 0.3, mo.spine_len - 0.3)))
    g.SetPolyShape(ps)
    g.SetLayer(pcbnew.B_Cu)
    g.SetFilled(True)
    g.SetWidth(0)
    g.SetNet(gnd)
    board.Add(g)
    pcbnew.SaveBoard(BOARD, board)
    print('LED strip routed: %d tracks, %d vias' % (sum(1 for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK'),
                                                     sum(1 for t in board.GetTracks() if t.GetClass() == 'PCB_VIA')))


def path(board, pts, width, net, layer=pcbnew.F_Cu):
    for a, b in zip(pts, pts[1:]):
        track(board, a, b, width, net, layer)


def touch_block(board, f):
    """U7 to its parts, the eight slider lines from their resistors along the spine to their electrodes,
    and the three long pad lines along the spine to where they leave for the tail and the flippers."""
    u7 = f['U7']
    P = {n: pad(u7, str(n)) for n in range(1, 21)}
    net_of = lambda fp, n: [q for q in fp.Pads() if q.GetNumber() == n][0].GetNet()
    XC, YC, W = tb.XC, tb.YC, tb.W
    gnd = board.FindNet('GND')
    for pin, (ref, dx) in tb.TOP.items():                       # fan upwards
        r1 = pad(f[ref], '1')
        path(board, [P[pin], (P[pin][0], YC - 1.9), (r1[0], YC - 1.9 - abs(r1[0] - P[pin][0])), r1], W, net_of(u7, str(pin)))   # 45 degrees
    for pin, (ref, dx) in tb.RIGHT.items():                     # out to the right, then up
        r1 = pad(f[ref], '1')
        path(board, [P[pin], (r1[0], P[pin][1]), r1], W, net_of(u7, str(pin)))
    for pin, (ref, dy) in tb.LEFT.items():                      # fan to the left
        t1 = pad(f[ref], '1')
        path(board, [P[pin], (XC - 1.95, P[pin][1]), (XC - 1.95 - abs(t1[1] - P[pin][1]), t1[1]), t1], W, net_of(u7, str(pin)))
    c38_1, c38_2 = pad(f['C38'], '1'), pad(f['C38'], '2')
    path(board, [P[5], (P[5][0], YC + 1.95), c38_1], W, net_of(u7, '5'))                 # VREG
    path(board, [P[6], (c38_2[0], P[6][1]), c38_2, (c38_2[0], c38_2[1] + 0.85)], 0.2, gnd)  # VSS and C38 ground
    via(board, (c38_2[0], c38_2[1] + 0.85), gnd)
    r33_1, r33_2 = pad(f['R33'], '1'), pad(f['R33'], '2')
    path(board, [P[7], (r33_1[0], P[7][1]), r33_1], W, net_of(u7, '7'))                  # REXT
    path(board, [r33_2, (r33_2[0] + 0.95, r33_2[1])], 0.2, gnd)
    via(board, (r33_2[0] + 0.95, r33_2[1]), gnd)
    c37_1, c37_2 = pad(f['C37'], '1'), pad(f['C37'], '2')
    path(board, [c37_2, (c37_2[0], c37_2[1] + 0.9)], 0.2, gnd)
    via(board, (c37_2[0], c37_2[1] + 0.9), gnd)
    path(board, [c37_1, (c37_1[0], YC + 3.3)], 0.2, net_of(u7, '20'))                    # a place to pick up 3V3
    path(board, [P[3], P[4]], W, net_of(u7, '3'))                                        # ADDR bridged to SDA
    path(board, [P[1], (P[1][0], YC + 2.2), (XC - 1.7, YC + 2.9)], W, net_of(u7, '1'))   # IRQ, SCL, SDA: stubs to pick up
    path(board, [P[2], (P[2][0], YC + 2.2), (XC - 0.85, YC + 2.9)], W, net_of(u7, '2'))
    path(board, [P[3], (P[3][0], YC + 2.9)], W, net_of(u7, '3'))
    # slider lines
    centres = [4.0 + (mo.slider_len - 8.0) * k / 7 for k in range(8)]
    for k in range(8):
        r = f['R%d' % (20 + k)]
        start, net = pad(r, '2'), net_of(r, '2')
        level = tb.LEVEL0 + tb.LEVEL_PITCH * k
        xv = tb.CORRIDOR0 + tb.CORRIDOR_PITCH * k
        depth = tb.LANE0 + tb.LANE_PITCH * k
        entry = B(*mo.at(mo.SLIDER, tb.LANE_ENTRY, depth)[:2])
        pts = [start, (start[0], level), (xv, level), (xv, entry[1]), entry]
        n = max(1, int((centres[k] - tb.LANE_ENTRY) / 1.5))
        pts += [B(*mo.at(mo.SLIDER, tb.LANE_ENTRY + (centres[k] - tb.LANE_ENTRY) * q / n, depth)[:2]) for q in range(1, n + 1)]
        pts.append(pad(f['E%d' % (k + 1)], '1'))
        path(board, pts, W, net)
    # the three long pad lines: up from R29..R31, along their lanes, and a stub below the band to pick up
    def along(depth, want, coord):
        """distance along the spine at which the lane at this depth reaches BOARD x (coord 0) = want"""
        lo, hi = 0.0, mo.slider_len
        for _ in range(50):
            mid = (lo + hi) / 2
            if B(*mo.at(mo.SLIDER, mid, depth)[:2])[coord] > want:      # board x falls towards the tail
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    for ref, xv, depth, leave in tb.LONG:
        r = f[ref]
        start, net = pad(r, '2'), net_of(r, '2')
        s0 = tb.LANE_ENTRY
        s1 = mo.slider_len - 1.0 if leave is None else along(depth, MIRROR - leave, 0)
        n = max(1, int((s1 - s0) / 1.5))
        entry = B(*mo.at(mo.SLIDER, s0, depth)[:2])
        pts = [start, (xv, start[1]), (xv, entry[1])]
        pts += [B(*mo.at(mo.SLIDER, s0 + (s1 - s0) * q / n, depth)[:2]) for q in range(n + 1)]
        pts.append(B(*mo.at(mo.SLIDER, s1, tb.LONG_STUB_DEPTH)[:2]))
        path(board, pts, W, net)
    # the guard track below the lanes, in pieces between the places where a long line leaves
    gd = tb.GUARD_DEPTH
    cuts = sorted(along(gd, MIRROR - leave, 0) for ref, xv, depth, leave in tb.LONG if leave is not None)
    edges = [along(gd, tb.GUARD_START_X, 0)] + [c + sign * tb.GUARD_GAP for c in cuts for sign in (-1, 1)] + [mo.slider_len - 1.0 - tb.GUARD_GAP]
    for s0, s1 in zip(edges[0::2], edges[1::2]):
        n = max(1, int((s1 - s0) / 1.5))
        path(board, [B(*mo.at(mo.SLIDER, s0 + (s1 - s0) * q / n, gd)[:2]) for q in range(n + 1)], tb.GUARD_W, gnd)


def tail_link_points(f):
    """the tail line's run from the stub below its lane straight to the tail pad's plated hole, BOARD mm"""
    return [B(*mo.at(mo.SLIDER, mo.slider_len - 1.0, tb.LONG_STUB_DEPTH)[:2]), pad(f['E12'], '1')]


def tail_link(board, f):
    a, b = tail_link_points(f)
    track(board, a, b, tb.W, list(f['E12'].Pads())[0].GetNet())


def stem_areas(board):
    """a corridor round the tail line's run to its pad, for a parts-side keep-out: other tracks cross on In2"""
    a, b = tail_link_points(fps(board))
    L = math.dist(a, b)
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    c = tb.STEM_CLEAR
    a2, b2 = (a[0] - ux * 0.1, a[1] - uy * 0.1), (b[0] - ux * 1.2, b[1] - uy * 1.2)      # stops short of the pad's hole
    return [[(a2[0] - uy * c, a2[1] + ux * c), (b2[0] - uy * c, b2[1] + ux * c), (b2[0] + uy * c, b2[1] - ux * c), (a2[0] + uy * c, a2[1] - ux * c)]]


def accelerometer(board, f):
    """U5's neighbouring pads that share a net, joined directly: SA0, SDx and SCx (all grounded) and the two grounds."""
    u5 = f['U5']
    for a, b in (('1', '2'), ('2', '3'), ('6', '7')):
        net = [q for q in u5.Pads() if q.GetNumber() == a][0].GetNet()
        other = [q for q in u5.Pads() if q.GetNumber() == b][0].GetNet()
        if net.GetNetname() != other.GetNetname():
            raise SystemExit('U5 pads %s and %s are not on one net: accelerometer() is out of date' % (a, b))
        track(board, pad(u5, a), pad(u5, b), 0.2, net)


def pressure(board, f):
    """U11 (BMP580, 2 x 2 mm, ten pads round the edge). Its three supply pads are not together: VDD (10) and
    VDDIO (1) share a corner, CSB (6, tied high for I2C) is on the far side between two grounded pads. Left
    to the routers, SDA and 3.3 V took turns under the body and neither stayed. So: 10 to 1 round the corner,
    1 to 6 straight through the middle (0.24 mm clear of SCK's pad, the nearest), and the grounded pads that
    are neighbours joined (INT 7, VSS 8, VSS 9). Bosch's datasheet (section 8.2) gives only the landing
    pattern and says nothing against copper under the part; its separate handling note has not been read."""
    u = f['U11']
    net = lambda n: [q for q in u.Pads() if q.GetNumber() == n][0].GetNet()
    for a, b in (('10', '1'), ('1', '6'), ('7', '8'), ('8', '9')):
        if net(a).GetNetname() != net(b).GetNetname():
            raise SystemExit('U11 pads %s and %s are not on one net: pressure() is out of date' % (a, b))
        track(board, pad(u, a), pad(u, b), 0.15, net(a))


def snout_link(board, f):
    """The snout pad's plated hole sits at the tip of the snout, clear of the two buttons, just outside
    the pad itself: join the two on the show face."""
    e9 = f['E9']
    track(board, pad(e9, '1'), B(17.0, 46.3), 0.4, list(e9.Pads())[0].GetNet(), pcbnew.B_Cu)


# ------------------------------------------------------------------------------------ keep-outs
def rule_area(board, points, layers, tracks=False, vias=False, pour=False, name=''):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetZoneName(name)
    z.SetDoNotAllowTracks(tracks)
    z.SetDoNotAllowVias(vias)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    for setter in ('SetDoNotAllowZoneFills', 'SetDoNotAllowCopperPour'):
        if hasattr(z, setter):
            getattr(z, setter)(pour)
    ls = pcbnew.LSET()
    for layer in layers:
        ls.AddLayer(layer)
    z.SetLayerSet(ls)
    z.Outline().AddOutline(chain(points))
    board.Add(z)
    return z


def ellipse(cx, cy, rx, ry, rot, grow=0.0, n=40):
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    return [B(cx + (rx + grow) * math.cos(t) * c - (ry + grow) * math.sin(t) * s, cy + (rx + grow) * math.cos(t) * s + (ry + grow) * math.sin(t) * c)
            for t in [2 * math.pi * k / n for k in range(n)]]


def touch_areas(grow):
    import build_board as bb
    areas = [band_polygon(BAND[0] - grow, BAND[1] + grow, 0.0, mo.spine_len, ext=grow)]
    areas += [ellipse(cx, cy, rx, ry, rot, grow) for cx, cy, rx, ry, rot in bb.PADS.values()]
    return areas


HOLE_KEEP = 2.8                          # no copper this near a mounting hole's centre: an M2.5 screw head and a margin


def hole_areas(board, n=28):
    """a circle round each mounting hole (footprints H1, H2, ...), in board mm"""
    out = []
    for ref, fp in fps(board).items():
        if ref.startswith('H') and ref[1:].isdigit():
            c = fp.GetPosition()
            out.append([(to_mm(c.x) + HOLE_KEEP * math.cos(2 * math.pi * k / n), to_mm(c.y) + HOLE_KEEP * math.sin(2 * math.pi * k / n)) for k in range(n)])
    return out


QUIET = {'U8': 2.0, 'U9': 2.2}           # no pour, no vias, no show-face or In2 tracks within this of the part's centre
PLANE_STAYS = ('U8',)                    # ...except that the ground plane carries on under the compass: it sits in the
                                         # tail stem, and a hole in the plane there would cut the tail's ground off
UNDER = {'U8': (0.85, 0.85), 'U9': (0.3, 0.75)}   # and no parts-side tracks under the body, between its pads


def quiet_areas(board):
    """[(ref, square round the magnetometer or the temperature sensor, the smaller box under its body)], board mm"""
    out = []
    f = fps(board)
    for ref, half in QUIET.items():
        if ref in f:
            c = f[ref].GetPosition()
            x, y = to_mm(c.x), to_mm(c.y)
            ux, uy = UNDER[ref]
            out.append((ref, [(x - half, y - half), (x + half, y - half), (x + half, y + half), (x - half, y + half)],
                        [(x - ux, y - uy), (x + ux, y - uy), (x + ux, y + uy), (x - ux, y + uy)]))
    return out


def antenna_area(board):
    """the module footprint's own keep-out, as a rectangle in board mm"""
    u4 = fps(board)['U4']
    for z in u4.Zones():
        if z.GetIsRuleArea():
            bb = z.GetBoundingBox()
            x0, y0, x1, y1 = to_mm(bb.GetLeft()), to_mm(bb.GetTop()), to_mm(bb.GetRight()), to_mm(bb.GetBottom())
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    raise SystemExit('U4 has no keep-out zone')


# ------------------------------------------------------------------------------------ stage: dsn
def stage_dsn(with_ground=False):
    """A copy of the board for the autorouter only: ground pads carry no net (ground is made by pours
    afterwards), and the show face is closed to it wherever there is touch copper or the ground strip."""
    board = pcbnew.LoadBoard(BOARD)
    if not with_ground:
        # Ground pads that the scripted tracks already reach keep their net, so the autorouter sees that
        # copper as an obstacle; every other ground pad is left for the pours.
        ends = []
        for t in board.GetTracks():
            if t.GetNetname() == 'GND':
                ends += [t.GetStart()] if t.Type() == pcbnew.PCB_VIA_T else [t.GetStart(), t.GetEnd()]
        kept = 0
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetNetname() == 'GND':
                    if any(p.HitTest(e) for e in ends):
                        kept += 1
                    else:
                        p.SetNetCode(0)
        print('ground pads kept on their net for the autorouter: %d' % kept)
    rule_area(board, band_polygon(0.2, BAND[1] + 0.6, 0.0, mo.spine_len, ext=0.6), NEAR_SHOW, tracks=True, name='spine show face')
    rule_area(board, band_polygon(BAND[0] - 0.4, BAND[1] + 0.6, 0.0, mo.spine_len, ext=0.6), ALL_CU, vias=True, name='slider no vias')
    for poly in stem_areas(board):
        rule_area(board, poly, (pcbnew.F_Cu,), tracks=True, name='touch line corridor')
    rule_area(board, band_polygon(0.2, STRIP[1] + 0.3, 0.0, mo.spine_len), ALL_CU, vias=True, name='strip no vias')
    for poly in touch_areas(0.6)[1:]:
        rule_area(board, poly, NEAR_SHOW, tracks=True, name='touch pad')
        rule_area(board, poly, ALL_CU, vias=True, name='touch pad no vias')
    rule_area(board, antenna_area(board), ALL_CU, tracks=True, vias=True, name='antenna')
    for poly in hole_areas(board):
        rule_area(board, poly, ALL_CU, tracks=True, vias=True, name='mounting hole')
    for ref, outer, inner in quiet_areas(board):
        rule_area(board, outer, ALL_CU, vias=True, name='quiet sensor: no vias')
        rule_area(board, outer, NEAR_SHOW, tracks=True, name='quiet sensor: show face')
        rule_area(board, inner, (pcbnew.F_Cu,), tracks=True, name='quiet sensor: under the body')
    # the autorouter gets the parts side and the inner signal layer only
    whole = [B(*p) for p in mo.OUTLINE]
    rule_area(board, whole, (PLANE, pcbnew.B_Cu), tracks=True, name='not for the autorouter')
    os.makedirs(WORK, exist_ok=True)
    tmp = os.path.join(WORK, 'route_in.kicad_pcb')
    pcbnew.SaveBoard(tmp, board)
    board = pcbnew.LoadBoard(tmp)
    dsn = os.path.join(WORK, 'route.dsn')
    ok = pcbnew.ExportSpecctraDSN(board, dsn)
    if not ok:
        raise SystemExit('DSN export failed')
    # give the supply nets their own, wider class
    t = open(dsn).read()
    i = t.index('(class kicad_default')
    j = t.index('(circuit', i)
    k = t.index('\n    )', j) + 6
    names = t[i + len('(class kicad_default'):j].split()
    power = [n for n in names if n.strip('"') in POWER_NETS]
    rest = [n for n in names if n.strip('"') not in POWER_NETS]
    body = t[j:k]
    wide = body.replace('(width %d)' % round(W_SIGNAL_AUTO * 1000), '(width %d)' % round(W_POWER * 1000))
    if wide == body:
        raise SystemExit('could not find the default width in the DSN class block')
    t = t[:i] + '(class kicad_default ' + ' '.join(rest) + '\n      ' + body + '\n    (class power ' + ' '.join(power) + '\n      ' + wide + t[k:]
    # everything already on the board was drawn by script: the autorouter may join to it, not move it
    t = t.replace('(type route)', '(type protect)')
    open(dsn, 'w').write(t)
    print('DSN written, %d supply nets at %.2f mm: %s' % (len(power), W_POWER, dsn))


# ------------------------------------------------------------------------------------ stage: ses
def stage_ses():
    board = pcbnew.LoadBoard(BOARD)
    before = len(board.GetTracks())
    # The import replaces every track with what the session file holds. Ground was left out of the
    # autorouter's copy, so the scripted ground tracks and vias are not in the session: carry them over.
    ground = [t.Duplicate() for t in board.GetTracks() if t.GetNetname() == 'GND']
    ok = pcbnew.ImportSpecctraSES(board, os.path.join(WORK, 'route.ses'))
    if not ok:
        raise SystemExit('session import failed (is build/pcb/route.ses there?)')
    def key(t):
        r = lambda v: round(v / 20000)          # 0.02 mm: the session file rounds coordinates
        a, b = sorted([(r(t.GetStart().x), r(t.GetStart().y)), (r(t.GetEnd().x), r(t.GetEnd().y))])
        return (t.Type(), t.GetLayer(), a, b)
    have = set(key(t) for t in board.GetTracks())
    for t in ground:
        if key(t) not in have:
            board.Add(t)
    pcbnew.SaveBoard(BOARD, board)
    print('imported: %d tracks and vias before, %d after' % (before, len(board.GetTracks())))


# ------------------------------------------------------------------------------------ stage: pour
def stage_pour():
    board = pcbnew.LoadBoard(BOARD)
    gnd = board.FindNet('GND')
    outline = [B(*p) for p in mo.OUTLINE]
    # pour-free areas: behind the touch copper on the parts side and the ground plane (both about 1.4 mm
    # from it), round it on the show face and on the inner signal layer 0.2 mm behind it, and the antenna
    for poly in touch_areas(0.3):
        rule_area(board, poly, (pcbnew.F_Cu, PLANE), pour=True, name='no pour behind touch')
    for poly in touch_areas(1.5):
        rule_area(board, poly, NEAR_SHOW, pour=True, name='no pour round touch')
    rule_area(board, antenna_area(board), ALL_CU, tracks=True, vias=True, pour=True, name='antenna')
    for poly in hole_areas(board):
        rule_area(board, poly, ALL_CU, tracks=True, vias=True, pour=True, name='mounting hole')
    for ref, outer, inner in quiet_areas(board):
        rule_area(board, outer, tuple(l for l in ALL_CU if not (l == PLANE and ref in PLANE_STAYS)), pour=True, name='quiet sensor')
        rule_area(board, outer, ALL_CU, vias=True, name='quiet sensor: no vias')
    # through-hole ground pads (the USB shell, connector lugs) join the pour solidly: they are tied in by
    # track already, and a thermal there has no room for its spokes
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == 'GND' and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    for layer, clearance in ((pcbnew.F_Cu, 0.3), (PLANE, 0.25), (INNER, 0.3), (pcbnew.B_Cu, 0.5)):
        z = pcbnew.ZONE(board)
        z.SetNet(gnd)
        z.SetLayer(layer)
        z.SetZoneName('GND')
        z.Outline().AddOutline(chain(outline))
        z.SetLocalClearance(mm(clearance))
        z.SetMinThickness(mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(mm(0.25))
        z.SetThermalReliefSpokeWidth(mm(0.3))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(z)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # Stitch the pours together on a grid. A via goes where the ground plane and the show-face pour are both
    # present and each of the other two layers either has ground there too or has no copper near; never
    # near a plated or unplated hole of any part (a slot is longer than its pad's centre suggests).
    fills = {}
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.GetNetname() == 'GND':
            fills[z.GetLayer()] = z.GetFilledPolysList(z.GetLayer())
    copper = {pcbnew.F_Cu: [], INNER: []}          # (x1, y1, x2, y2, half width) of every track and pad there
    drilled = []
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T and t.GetLayer() in copper:
            a, b = t.GetStart(), t.GetEnd()
            copper[t.GetLayer()].append((to_mm(a.x), to_mm(a.y), to_mm(b.x), to_mm(b.y), to_mm(t.GetWidth()) / 2))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            box = (to_mm(bb.GetLeft()), to_mm(bb.GetTop()), to_mm(bb.GetRight()), to_mm(bb.GetBottom()))
            if p.GetDrillSize().x:
                drilled.append(box)
            for layer in copper:
                if p.IsOnLayer(layer):
                    c = p.GetPosition()
                    copper[layer].append((to_mm(c.x), to_mm(c.y), to_mm(c.x), to_mm(c.y), math.hypot(box[2] - box[0], box[3] - box[1]) / 2))

    def clear_of(layer, x, y, gap=0.6):
        for xa, ya, xb, yb, r in copper[layer]:
            dx, dy = xb - xa, yb - ya
            L2 = dx * dx + dy * dy
            u = max(0.0, min(1.0, ((x - xa) * dx + (y - ya) * dy) / L2)) if L2 else 0.0
            if math.hypot(x - xa - u * dx, y - ya - u * dy) < r + gap:
                return False
        return True

    def ring(x, y):
        return [(x, y)] + [(x + rr * math.cos(a), y + rr * math.sin(a)) for rr in (0.45, 0.75) for a in [k * math.pi / 6 for k in range(12)]]

    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    taken = [(to_mm(t.GetStart().x), to_mm(t.GetStart().y)) for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    added = 0
    y = min(ys) + 2.0
    while y < max(ys):
        x = min(xs) + 2.0
        while x < max(xs):
            pts = ring(x, y)
            ok = all(fills[layer].Contains(vec(px, py)) for layer in (PLANE, pcbnew.B_Cu) for px, py in pts)
            ok = ok and all(all(fills[layer].Contains(vec(px, py)) for px, py in pts) or clear_of(layer, x, y) for layer in copper)
            ok = ok and not any(x0 - 1.0 < x < x1 + 1.0 and y0 - 1.0 < y < y1 + 1.0 for x0, y0, x1, y1 in drilled)
            if ok and all(math.hypot(x - vx, y - vy) > 2.0 for vx, vy in taken):
                via(board, (x, y), gnd)
                taken.append((x, y))
                added += 1
            x += STITCH
        y += STITCH
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(BOARD, board)
    print('ground poured on four layers, %d stitching vias' % added)


if __name__ == '__main__':
    stage = sys.argv[1] if len(sys.argv) > 1 else ''
    {'strip': stage_strip, 'dsn': stage_dsn, 'dsn-ground': lambda: stage_dsn(True), 'ses': stage_ses,
     'pour': stage_pour}.get(stage, lambda: sys.exit(__doc__))()
