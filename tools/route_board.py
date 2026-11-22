#!/usr/bin/env python3
"""Route the DinoLight board. Run with KiCad's Python, one stage at a time, after tools/build_board.py:

    $KPY tools/route_board.py strip     LED strip by rule: supply rail, ground strip and vias, data hops
    $KPY tools/route_board.py dsn       write build/pcb/route.dsn for the autorouter (ground left out)
    java -jar ~/.kicad-mcp/freerouting.jar -de build/pcb/route.dsn -do build/pcb/route.ses -mp 40
    $KPY tools/route_board.py ses       bring the autorouter's tracks back into the board
    $KPY tools/route_board.py pour      ground pours on both faces, pour-free areas, fill

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


def band_polygon(d0, d1, s0=0.0, s1=None, step=1.5):
    """a strip following the spine edge, in BOARD mm"""
    s1 = mo.spine_len if s1 is None else s1
    n = max(2, int((s1 - s0) / step))
    top = [mo.at(mo.SPINE, s0 + (s1 - s0) * k / n, d0)[:2] for k in range(n + 1)]
    bot = [mo.at(mo.SPINE, s0 + (s1 - s0) * k / n, d1)[:2] for k in range(n, -1, -1)]
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
    areas = [band_polygon(BAND[0] - grow, BAND[1] + grow, 0.0, mo.spine_len)]
    areas += [ellipse(cx, cy, rx, ry, rot, grow) for cx, cy, rx, ry, rot in bb.PADS.values()]
    return areas


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
def stage_dsn():
    """A copy of the board for the autorouter only: ground pads carry no net (ground is made by pours
    afterwards), and the show face is closed to it wherever there is touch copper or the ground strip."""
    board = pcbnew.LoadBoard(BOARD)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == 'GND':
                p.SetNetCode(0)
    for t in list(board.GetTracks()):
        if t.GetNetname() == 'GND':
            t.SetNetCode(0)
    both = (pcbnew.F_Cu, pcbnew.B_Cu)
    rule_area(board, band_polygon(0.2, BAND[1] + 0.6, 0.0, mo.spine_len), (pcbnew.B_Cu,), tracks=True, name='spine show face')
    rule_area(board, band_polygon(BAND[0] - 0.4, BAND[1] + 0.6, 0.0, mo.spine_len), both, vias=True, name='slider no vias')
    rule_area(board, band_polygon(0.2, STRIP[1] + 0.3, 0.0, mo.spine_len), both, vias=True, name='strip no vias')
    for poly in touch_areas(0.6)[1:]:
        rule_area(board, poly, (pcbnew.B_Cu,), tracks=True, name='touch pad')
        rule_area(board, poly, both, vias=True, name='touch pad no vias')
    rule_area(board, antenna_area(board), both, tracks=True, vias=True, name='antenna')
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
    open(dsn, 'w').write(t)
    print('DSN written, %d supply nets at %.2f mm: %s' % (len(power), W_POWER, dsn))


# ------------------------------------------------------------------------------------ stage: ses
def stage_ses():
    board = pcbnew.LoadBoard(BOARD)
    before = len(board.GetTracks())
    ok = pcbnew.ImportSpecctraSES(board, os.path.join(WORK, 'route.ses'))
    if not ok:
        raise SystemExit('session import failed')
    pcbnew.SaveBoard(BOARD, board)
    print('imported: %d tracks and vias before, %d after' % (before, len(board.GetTracks())))


# ------------------------------------------------------------------------------------ stage: pour
def stage_pour():
    board = pcbnew.LoadBoard(BOARD)
    gnd = board.FindNet('GND')
    outline = [B(*p) for p in mo.OUTLINE]
    both = (pcbnew.F_Cu, pcbnew.B_Cu)
    # pour-free areas: behind the touch copper on the parts side, round it on the show face, and the antenna
    for poly in touch_areas(0.3):
        rule_area(board, poly, (pcbnew.F_Cu,), pour=True, name='no pour behind touch')
    for poly in touch_areas(1.5):
        rule_area(board, poly, (pcbnew.B_Cu,), pour=True, name='no pour round touch')
    rule_area(board, antenna_area(board), both, tracks=True, vias=True, pour=True, name='antenna')
    for layer, clearance in ((pcbnew.F_Cu, 0.3), (pcbnew.B_Cu, 0.5)):
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
    pcbnew.SaveBoard(BOARD, board)
    print('ground poured on both faces')


if __name__ == '__main__':
    stage = sys.argv[1] if len(sys.argv) > 1 else ''
    {'strip': stage_strip, 'dsn': stage_dsn, 'ses': stage_ses, 'pour': stage_pour}.get(stage, lambda: sys.exit(__doc__))()
