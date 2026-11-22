#!/usr/bin/env python3
"""Build the DinoLight board from the schematic's netlist: outline, every footprint placed and linked to
its schematic symbol, every pad on its net, touch electrodes on the show face, eye hole. No tracks.

Run with KiCad's Python from the project folder, after `python3 tools/schematic.py verify`
(which writes build/sch/netlist.net):

    export KICAD_DOCUMENTS_HOME="$PWD/kicad-user"
    $KPY tools/build_board.py

Writes dinolight.kicad_pcb. IT OVERWRITES THE BOARD: once the board has tracks or hand edits, do not
run this again without asking.

Coordinates in this file are on the SHOW face in mm (head left, as in outline/make_outline.py).
Parts sit on the other side, which is KiCad's front copper, so x is mirrored: X = MIRROR - x.
The outline is a draft that will be replaced; everything along an edge is computed from it.
"""
import math
import os
import re
import sys

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'outline'))
import make_outline as mo

KFP = '/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/'
MYLIB = os.path.join(ROOT, 'lib', 'DinoLight.pretty')
NETLIST = os.path.join(ROOT, 'build', 'sch', 'netlist.net')
OUT = os.path.join(ROOT, 'dinolight.kicad_pcb')
MIRROR, YOFF = 232.0, 10.0
GAP = 0.4                                    # between courtyards when packing
mm = pcbnew.FromMM

# ---------------------------------------------------------------- where things go (show-face mm)
EYE = (42.0, 41.0, 3.5)                      # hole centre and radius; D21 on the snout side, D22 opposite
HOLES = {'H1': (30, 40.5), 'H2': (134.5, 57.5), 'H3': (193, 44)}   # placeholders until the case is designed
BATTERY = (94, 34, 130, 60)                  # keep free of parts
EXPLICIT = {                                 # ref: (x, y, board rotation)
    'U4': (61, 48.0, 180),                   # module, antenna end at the throat edge
    'J2': (137, 47.8, 90),                   # battery connector, opening towards the battery
    'J3': (175, 47.2, 0),                    # Qwiic, opening at the underside of the tail
    'C9': (181.5, 42.5, 0), 'TP11': (185.5, 43.5, 0),
    'SW3': (19.5, 45.5, 0), 'SW2': (28, 46.9, 0),      # BOOT and RESET in the snout
    'R1': (108.3, 62.4, 90), 'R2': (121.7, 62.4, 90), 'U1': (126, 63.6, 0),
}
# packed clusters: (rectangle x0, y0, x1, y1), parts in order, optional rotations
CLUSTERS = [
    ('LED rail switch, head', (33.5, 44.7, 47.4, 54.6),
     'Q2 Q3 C8 R11 R13 C10 R12 R14 R15 TP5 TP13 TP16'),
    ('module support', (71, 40, 92.6, 52.6),
     'U7 C37 C38 R33 R34 U6 C36 R32 R16 C32 TP12 R20 R21 R22 R23 R24 R25 R26 R27 R28 R29 R30 R31 R6 R7 C7 R8 R9 TP6 TP7 TP8'),
    ('battery input', (131.5, 35.3, 143.6, 42.6), 'F1 SJ1 SJ2'),
    ('charger and regulator', (143.9, 40, 152.2, 56), 'Q1 U2 R3 C1 C2 R10 R19 TP3 TP4 TP15'),
    ('regulator, enable', (152.5, 41.5, 166.3, 51.6), 'U3 C3 C4 D23 R4 R5 TP1 TP2 TP14'),
    ('accelerometer', (141, 57.4, 151.6, 64.6), 'U5 C33 R17 R18 C34 TP9 TP10'),
]


def B(x, y):
    return (MIRROR - x, y + YOFF)


def vec(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


# ---------------------------------------------------------------- the netlist
TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse(text):
    stack, cur = [], None
    for tok in TOKEN.findall(text):
        if tok == '(':
            new = []
            if cur is not None:
                cur.append(new)
                stack.append(cur)
            cur = new
        elif tok == ')':
            if not stack:
                return cur
            cur = stack.pop()
        else:
            cur.append(tok[1:-1] if tok[0] == '"' else tok)
    return cur


def kids(node, head):
    return [c for c in node if isinstance(c, list) and c and c[0] == head]


def kid(node, head):
    k = kids(node, head)
    return k[0] if k else None


def read_netlist():
    tree = parse(open(NETLIST, encoding='utf-8').read())
    comps = {}
    for c in kids(kid(tree, 'components'), 'comp'):
        ref = kid(c, 'ref')[1]
        fields = {}
        for f in kids(kid(c, 'fields') or [], 'field'):
            fields[kid(f, 'name')[1]] = f[2] if len(f) > 2 and not isinstance(f[2], list) else ''
        comps[ref] = dict(value=kid(c, 'value')[1], footprint=kid(c, 'footprint')[1],
                          path=kid(kid(c, 'sheetpath'), 'tstamps')[1] + kid(c, 'tstamps')[1],
                          lcsc=fields.get('LCSC', ''))
    nets = {}
    for n in kids(kid(tree, 'nets'), 'net'):
        name = kid(n, 'name')[1]
        nets[name] = [(kid(x, 'ref')[1], kid(x, 'pin')[1]) for x in kids(n, 'node')]
    return comps, nets


# ---------------------------------------------------------------- geometry helpers
def edge_at(seg_index, x):
    pts = mo.polyline([mo.P[seg_index]], 400)
    i = min(range(len(pts) - 1), key=lambda k: abs(pts[k][0] - x))
    return pts[i]


def angle_for(nx, ny):
    """board rotation that turns a footprint's +Y to point along (nx, ny) in board coordinates"""
    return math.degrees(math.atan2(nx, ny))


def courtyard(fp):
    """courtyard box relative to the footprint position: (left, top, right, bottom) in mm"""
    try:
        fp.BuildCourtyardCaches()
    except Exception:
        pass
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    if bb.GetWidth() == 0:
        bb = fp.GetBoundingBox(False)
    p = fp.GetPosition()
    return tuple(pcbnew.ToMM(v) for v in (bb.GetLeft() - p.x, bb.GetTop() - p.y, bb.GetRight() - p.x, bb.GetBottom() - p.y))


def main():
    comps, nets = read_netlist()
    board = pcbnew.NewBoard(OUT)
    ds = board.GetDesignSettings()
    ds.m_MinClearance = mm(0.15)                 # JLCPCB's comfortable working figure; the LGA needs it
    ds.m_NetSettings.GetDefaultNetclass().SetClearance(mm(0.15))
    placed = {}

    def load(ref):
        lib, name = comps[ref]['footprint'].rsplit(':', 1)
        path = MYLIB if lib == 'DinoLight' else KFP + lib + '.pretty'
        fp = pcbnew.FootprintLoad(path, name)
        if fp is None:
            raise SystemExit('footprint not found for %s: %s' % (ref, comps[ref]['footprint']))
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(ref)
        fp.SetValue(comps[ref]['value'])
        fp.SetPath(pcbnew.KIID_PATH(comps[ref]['path']))
        if re.match(r'(R|C|D|E|TP|H)\d', ref):
            fp.Reference().SetVisible(False)
        return fp

    def put(ref, bx, by, rot=0):
        """place at BOARD coordinates"""
        fp = load(ref)
        fp.SetPosition(vec(bx, by))
        fp.SetOrientationDegrees(rot)
        board.Add(fp)
        placed[ref] = fp
        return fp

    # ---- outline, eye hole
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_POLY)
    v = pcbnew.VECTOR_VECTOR2I()
    for p in mo.polyline(mo.P, 40)[:-1]:
        v.append(vec(*B(*p)))
    s.SetPolyPoints(v)
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetFilled(False)
    s.SetWidth(mm(0.1))
    board.Add(s)
    ex, ey, er = EYE
    c = pcbnew.PCB_SHAPE(board)
    c.SetShape(pcbnew.SHAPE_T_CIRCLE)
    c.SetCenter(vec(*B(ex, ey)))
    c.SetEnd(vec(B(ex, ey)[0] + er, B(ex, ey)[1]))
    c.SetLayer(pcbnew.Edge_Cuts)
    c.SetWidth(mm(0.1))
    board.Add(c)

    # ---- nets
    netinfo = {}
    for name in nets:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        netinfo[name] = ni

    # ---- spine LEDs, D1 at the head, each with its capacitor just inboard
    for i, (x, y, a) in enumerate(mo.leds, 1):
        nxs, nys = math.sin(math.radians(a)), -math.cos(math.radians(a))      # outward normal, show face
        nx, ny = -nxs, nys
        bx, by = B(x, y)
        rot = angle_for(nx, ny)
        put('D%d' % i, bx - nx * 1.46, by - ny * 1.46, rot)                   # emitting face 0.1 mm inside the edge
        put('C%d' % (10 + i), bx - nx * 3.7, by - ny * 3.7, rot)

    # ---- eye: two LEDs on the rim of the hole, firing at each other
    bx, by = B(ex, ey)
    for ref, cap, sx in (('D21', 'C31', +1), ('D22', 'C35', -1)):             # sx: side of the hole in BOARD x
        nx = -sx                                                              # fires towards the hole centre
        fx = bx + sx * (er + 0.1 + 1.36)
        put(ref, fx, by, angle_for(nx, 0))
        put(cap, fx + sx * 2.9, by, 90)

    # ---- edge parts at the belly: board edge is 2.66 mm in front of the USB footprint origin (maker's
    #      drawing: 5.79 from the rear shell slots). The slide switch sits wholly on the board with its knob overhanging
    ux, uy = edge_at(13, 115)
    put('J1', *B(ux, uy - 2.66), 0)
    sx_, sy_ = edge_at(13, 101)
    put('SW1', *B(sx_, sy_ - 2.0), 0)                # frame pads end 1.45 from the origin; knob reaches 2.85

    for ref, (x, y, rot) in EXPLICIT.items():
        put(ref, *B(x, y), rot)
    for ref, (x, y) in HOLES.items():
        put(ref, *B(x, y), 0)

    # ---- module decoupling next to its 3V3 pin (pad 3)
    u4 = placed['U4']
    p3 = [p for p in u4.Pads() if p.GetNumber() == '3'][0].GetPosition()
    px, py = pcbnew.ToMM(p3.x), pcbnew.ToMM(p3.y)
    side = 1 if px > pcbnew.ToMM(u4.GetPosition().x) else -1
    put('C6', px + side * 1.9, py, 90)
    put('C5', px + side * 3.9, py + 0.3, 90)

    # ---- packed clusters
    for title, (x0, y0, x1, y1), refs in CLUSTERS:
        bx0, bx1 = MIRROR - x1, MIRROR - x0
        by0, by1 = y0 + YOFF, y1 + YOFF
        cx, cy, rowh, used = bx0, by0, 0.0, 0.0
        for ref in refs.split():
            fp = load(ref)
            fp.SetPosition(vec(0, 0))
            l, t, r, b = courtyard(fp)
            w, h = r - l, b - t
            if cx + w > bx1 + 1e-6:
                cx, cy, rowh = bx0, cy + rowh + GAP, 0.0
            if cy + h > by1 + 1e-6:
                raise SystemExit('cluster "%s" is full at %s (needs %.1f more mm of height)' % (title, ref, cy + h - by1))
            fp.SetPosition(vec(cx - l, cy - t))
            board.Add(fp)
            placed[ref] = fp
            cx += w + GAP
            rowh = max(rowh, h)
            used += w * h
        print('cluster %-26s %5.0f mm2 of courtyard in %5.0f mm2' % (title, used, (bx1 - bx0) * (by1 - by0)))

    # ---- touch electrodes on the show face (KiCad back copper, under solder mask), each on its net
    inset = pcbnew.SHAPE_POLY_SET()
    ch = pcbnew.SHAPE_LINE_CHAIN()
    for p in mo.polyline(mo.P, 40)[:-1]:
        ch.Append(mm(B(*p)[0]), mm(B(*p)[1]))
    ch.SetClosed(True)
    inset.AddOutline(ch)
    inset.Inflate(-mm(1.0), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, mm(0.01))

    def electrode(ref, points, centre):
        net = netinfo['PAD_' + ref_to_stem[ref]]
        g = pcbnew.PCB_SHAPE(board)
        g.SetShape(pcbnew.SHAPE_T_POLY)
        ps = pcbnew.SHAPE_POLY_SET()
        c2 = pcbnew.SHAPE_LINE_CHAIN()
        for p in points:
            c2.Append(mm(B(*p)[0]), mm(B(*p)[1]))
        c2.SetClosed(True)
        ps.AddOutline(c2)
        ps.BooleanIntersection(inset)                      # keep copper 1 mm inside the board edge
        g.SetPolyShape(ps)
        g.SetLayer(pcbnew.B_Cu)
        g.SetFilled(True)
        g.SetWidth(0)
        g.SetNet(net)
        board.Add(g)
        put(ref, *B(*centre), 0)

    stems = ['SPINE%d' % i for i in range(1, 9)] + ['SNOUT', 'FLIP_F', 'FLIP_R', 'TAIL']
    ref_to_stem = {'E%d' % (i + 1): s_ for i, s_ in enumerate(stems)}
    # Spine: 8 electrodes in a band 4 to 11 mm in from the edge. Neighbours meet along a chevron, so a
    # finger always covers two of them and its position can be interpolated from the two readings.
    cum = [0.0]
    for a, b in zip(mo.spine, mo.spine[1:]):
        cum.append(cum[-1] + math.dist(a, b))

    def along_spine(s, depth):
        """point at distance s along the spine edge, `depth` mm in from it (show-face mm)"""
        s = min(max(s, 0.0), cum[-1] - 1e-6)
        k = max(i_ for i_ in range(len(cum) - 1) if cum[i_] <= s)
        (x0, y0), (x1, y1) = mo.spine[k], mo.spine[k + 1]
        L = cum[k + 1] - cum[k]
        f = (s - cum[k]) / L
        tx, ty = (x1 - x0) / L, (y1 - y0) / L
        return (x0 + f * (x1 - x0) - ty * depth, y0 + f * (y1 - y0) + tx * depth)

    S0, S1, D0, D1, AMP, HALF_GAP = 6.0, mo.spine_len - 6.0, 4.0, 11.0, 4.0, 0.4
    bounds = [S0 + (S1 - S0) * k / 8 for k in range(9)]

    def run(sa_, sb_, depth):
        n_ = max(2, int(abs(sb_ - sa_) / 2.0) + 1)
        return [along_spine(sa_ + (sb_ - sa_) * q / n_, depth) for q in range(n_ + 1)]

    for j in range(8):
        left, right = bounds[j], bounds[j + 1]
        dm = (D0 + D1) / 2
        if j == 0:
            l_top, l_mid, l_bot = left, None, left
        else:
            l_top, l_mid, l_bot = left + HALF_GAP - AMP, left + HALF_GAP + AMP, left + HALF_GAP - AMP
        if j == 7:
            r_top, r_mid, r_bot = right, None, right
        else:
            r_top, r_mid, r_bot = right - HALF_GAP - AMP, right - HALF_GAP + AMP, right - HALF_GAP - AMP
        poly = [along_spine(l_top, D0)]
        if l_mid is not None:
            poly.append(along_spine(l_mid, dm))
        poly += run(l_bot, r_bot, D1)
        if r_mid is not None:
            poly.append(along_spine(r_mid, dm))
        poly += run(r_top, l_top, D0)[:-1]
        electrode('E%d' % (j + 1), poly, along_spine((left + right) / 2 + (AMP / 2 if 0 < j < 7 else 0), dm))
    for ref, (cx, cy, rx, ry, rot) in zip(('E9', 'E10', 'E11', 'E12'),
                                          [(24, 46.5, 9, 3.2, 8), (89, 78, 5.5, 9, -28), (151, 68, 4.5, 7, -30), (204, 60, 3.2, 9, -38)]):
        c_, s_ = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        electrode(ref, [(cx + rx * math.cos(t) * c_ - ry * math.sin(t) * s_, cy + rx * math.cos(t) * s_ + ry * math.sin(t) * c_)
                        for t in [2 * math.pi * k / 48 for k in range(48)]], (cx, cy))

    # ---- everything placed? then pad nets
    missing = [r for r in comps if r not in placed]
    if missing:
        raise SystemExit('not placed: ' + ' '.join(sorted(missing)))
    count = 0
    for name, nodes in nets.items():
        for ref, pin in nodes:
            hit = [p for p in placed[ref].Pads() if p.GetNumber() == pin]
            if not hit:
                raise SystemExit('%s has no pad %s (net %s)' % (ref, pin, name))
            for p in hit:
                p.SetNet(netinfo[name])
                count += 1

    # ---- battery area and labels
    x0, y0, x1, y1 = BATTERY
    r = pcbnew.PCB_SHAPE(board)
    r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetStart(vec(*B(x1, y0)))
    r.SetEnd(vec(*B(x0, y1)))
    r.SetLayer(pcbnew.F_SilkS)
    r.SetWidth(mm(0.15))
    board.Add(r)
    for text, (x, y), layer, mirrored in [('BATTERY: keep clear', (112, 47), pcbnew.F_SilkS, False),
                                          ('DinoLight v0.1 DRAFT 2026-11-22', (112, 55), pcbnew.F_SilkS, False),
                                          ('DinoLight v0.1 DRAFT', (112, 52), pcbnew.B_SilkS, True)]:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetPosition(vec(*B(x, y)))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(mm(1.2), mm(1.2)))
        t.SetTextThickness(mm(0.18))
        t.SetMirrored(mirrored)
        board.Add(t)

    pcbnew.SaveBoard(OUT, board)
    print('wrote %s: %d footprints, %d nets, %d pads on nets' % (os.path.basename(OUT), len(placed), len(nets), count))


if __name__ == '__main__':
    main()
