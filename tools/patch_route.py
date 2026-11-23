#!/usr/bin/env python3
"""Close the connections the autorouter left open, without moving anything drawn by script.

    $KPY tools/patch_route.py [--rounds 12] [--margin 10] [NET ...]     signals and supplies
    $KPY tools/patch_route.py --ground                                  then ground, pad to pad, before the pours
    $KPY tools/patch_route.py --no-rip                                  only clear paths: nothing is pushed out
    $KPY tools/patch_route.py --plane-vias 2.0                          a via to the ground plane within 2 mm of every ground pad
    $KPY tools/patch_route.py --fatten                                  widen supply tracks on the inner layer where there is room
    $KPY tools/patch_route.py --tidy                                    dead ends, scripted or not (then tools/trim_dangling.py)

Each round: run KiCad's DRC for the list of open (non-ground) connections, then for each one search a
0.05 mm grid, on every track layer (route_board.ROUTE_LAYERS), for a path between the two pieces of copper.
Pads, scripted tracks (those in build/pcb/strip.kicad_pcb), the board edge, the antenna zone, footprint
keep-outs and the touch copper's keep-outs are fixed obstacles at the board's clearance. A clear path is
looked for first, then further afield; only if there is none is the search repeated with the autorouter's
tracks made passable at a price: whatever the new path crosses is taken out (with any dead ends that
leaves) and comes back as an open connection in the next round. Tracks are 45-degree; a via costs about
3 mm of track; the inner layer costs a little more than the parts side and the show face four times as much.
The board is saved every round. This script proves nothing by itself: run the DRC afterwards.
"""
import heapq
import json
import math
import os
import re
import subprocess
import sys

import numpy as np
import pcbnew
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_board as rb

RES, EPS = 0.05, 0.04
CORE = 0.03                              # a path must start and end this far inside copper
VIA, DRILL = rb.VIA, rb.DRILL
mm, to_mm = pcbnew.FromMM, pcbnew.ToMM
LAYERS = rb.ROUTE_LAYERS                # parts side, inner signal layer, show face: the layers tracks may go on
NL = len(LAYERS)
ALL = tuple(range(NL))
SHOW = tuple(i for i, lid in enumerate(LAYERS) if lid != pcbnew.F_Cu)   # the layers near the touch copper
LCOST = tuple(1.0 if lid == pcbnew.F_Cu else (4.0 if lid == pcbnew.B_Cu and NL > 2 else 1.3) for lid in LAYERS)
LAYER_NAMES = {pcbnew.F_Cu: 'F.Cu', pcbnew.In1_Cu: 'In1.Cu', pcbnew.In2_Cu: 'In2.Cu', pcbnew.B_Cu: 'B.Cu'}
KICAD_CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
SOFT, SOFT_MINE = 15.0, 45.0            # price per grid cell of crossing an autorouted track, or one of ours
TOUCH_GAP = 0.5                         # between a touch line and any track or via that carries a signal (layout review:
                                        # the buzzer line ran 0.23 mm beside the snout's for 7 mm). Ground and the supplies
                                        # are exempt: they add a fixed capacitance, not noise. Pads keep the board's clearance.


def touchy(net):
    return net.startswith('PAD_')


def steady(net):
    return net == 'GND' or net in rb.POWER_NETS


def key(t):
    """identifies a track or via by where it is, to 0.02 mm"""
    r = lambda v: round(v / 20000)
    a, b = sorted([(r(t.GetStart().x), r(t.GetStart().y)), (r(t.GetEnd().x), r(t.GetEnd().y))])
    return ('via' if t.Type() == pcbnew.PCB_VIA_T else board_layer_name(t.GetLayer()), a, b)


def board_layer_name(layer):
    return LAYER_NAMES[layer]


def scripted_keys():
    """the same keys for everything in build/pcb/strip.kicad_pcb, read as text: loading a second board
    in the same process upsets KiCad's Python binding"""
    text = open(os.path.join(rb.WORK, 'strip.kicad_pcb')).read()
    r = lambda v: round(float(v) * 50)
    keys = set()
    for m in re.finditer(r'\(segment\s+\(start ([-\d.]+) ([-\d.]+)\)\s+\(end ([-\d.]+) ([-\d.]+)\)\s+\(width [\d.]+\)\s+(?:\(locked \w+\)\s+)?\(layer "([^"]+)"', text):
        a, b = sorted([(r(m.group(1)), r(m.group(2))), (r(m.group(3)), r(m.group(4)))])
        keys.add((m.group(5), a, b))
    for m in re.finditer(r'\(via\s+(?:\(type \w+\)\s+)?(?:\(locked \w+\)\s+)?\(at ([-\d.]+) ([-\d.]+)\)', text):
        a = (r(m.group(1)), r(m.group(2)))
        keys.add(('via', a, a))
    return keys


def poly_points(chain_):
    return [(to_mm(chain_.CPoint(i).x), to_mm(chain_.CPoint(i).y)) for i in range(chain_.PointCount())]


def collect_tracks(board, scripted, mine):
    """tracks and vias: (layers, net, kind, data, cls, price to cross or 0 if fixed, board item)"""
    out = []
    for t in board.GetTracks():
        n = t.GetNetname()
        k = key(t)
        price = 0.0 if k in scripted or n == 'GND' else (SOFT_MINE if k in mine else SOFT)
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            out.append((ALL, n, 'seg', (to_mm(p.x), to_mm(p.y), to_mm(p.x), to_mm(p.y), to_mm(t.GetWidth(pcbnew.F_Cu)) / 2), 'via', price, t))
        elif t.GetLayer() in LAYERS:
            a, b = t.GetStart(), t.GetEnd()
            out.append(((LAYERS.index(t.GetLayer()),), n, 'seg', (to_mm(a.x), to_mm(a.y), to_mm(b.x), to_mm(b.y), to_mm(t.GetWidth()) / 2), 'track', price, t))
    return out


def collect_static(board):
    """pads, copper shapes, board edge and keep-outs, in the same form; and the board outline"""
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            on = tuple(i for i, lid in enumerate(LAYERS) if p.IsOnLayer(lid))
            c = p.GetPosition()
            if not on or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                if p.GetDrillSize().x:
                    out.append((ALL, '', 'seg', (to_mm(c.x), to_mm(c.y), to_mm(c.x), to_mm(c.y), to_mm(p.GetDrillSize().x) / 2), 'hole', 0.0, None))
                continue
            for i in on:
                ps = p.GetEffectivePolygon(LAYERS[i], pcbnew.ERROR_INSIDE)
                out.append(((i,), p.GetNetname(), 'poly', (poly_points(ps.Outline(0)), (to_mm(c.x), to_mm(c.y))), 'pth' if len(on) == NL else 'smd', 0.0, None))
    for d in board.GetDrawings():
        if d.GetLayer() in LAYERS and d.GetShape() == pcbnew.SHAPE_T_POLY:
            ps = d.GetPolyShape()
            for k in range(ps.OutlineCount()):
                out.append(((LAYERS.index(d.GetLayer()),), d.GetNetname(), 'poly', (poly_points(ps.Outline(k)), None), 'shape', 0.0, None))
    edge = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(edge, False)
    outline = poly_points(edge.Outline(0))
    rings = [outline] + [poly_points(edge.Hole(0, k)) for k in range(edge.HoleCount(0))]
    for ring in rings:
        for a, b in zip(ring, ring[1:] + ring[:1]):
            out.append((ALL, '', 'seg', (a[0], a[1], b[0], b[1], 0.0), 'edge', 0.0, None))
    # keep-outs, the same ones the autorouter is given
    out.append((SHOW, '', 'poly', (rb.band_polygon(0.2, rb.BAND[1] + 0.6, 0.0, rb.mo.spine_len, ext=0.6), None), 'keepT', 0.0, None))
    out.append((ALL, '', 'poly', (rb.band_polygon(rb.BAND[0] - 0.4, rb.BAND[1] + 0.6, 0.0, rb.mo.spine_len, ext=0.6), None), 'keepV', 0.0, None))
    for poly in rb.stem_areas(board):
        out.append(((0,), '', 'poly', (poly, None), 'keepT', 0.0, None))
    out.append((ALL, '', 'poly', (rb.band_polygon(0.2, rb.STRIP[1] + 0.3, 0.0, rb.mo.spine_len), None), 'keepV', 0.0, None))
    for poly in rb.touch_areas(0.6)[1:]:
        out.append((SHOW, '', 'poly', (poly, None), 'keepT', 0.0, None))
        out.append((ALL, '', 'poly', (poly, None), 'keepV', 0.0, None))
    for poly in rb.hole_areas(board):
        out.append((ALL, '', 'poly', (poly, None), 'keepT', 0.0, None))
        out.append((ALL, '', 'poly', (poly, None), 'keepV', 0.0, None))
    for ref, outer, inner in rb.quiet_areas(board):
        out.append((SHOW, '', 'poly', (outer, None), 'keepT', 0.0, None))
        out.append((ALL, '', 'poly', (outer, None), 'keepV', 0.0, None))
        out.append(((0,), '', 'poly', (inner, None), 'keepT', 0.0, None))
    ant = rb.antenna_area(board)
    out.append((ALL, '', 'poly', (ant, None), 'keepT', 0.0, None))
    out.append((ALL, '', 'poly', (ant, None), 'keepV', 0.0, None))
    # no touch line under the battery, or within 0.6 mm of its area: a foil pouch lying on one reads as a touch
    import build_board as bb
    x0, y0, x1, y1 = bb.BATTERY
    (bx0, by0), (bx1, by1) = rb.B(x1 + 0.6, y0 - 0.6), rb.B(x0 - 0.6, y1 + 0.6)
    out.append((ALL, '', 'poly', ([(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)], None), 'keepTouch', 0.0, None))
    # keep-outs that come with a footprint (the SHT40's no-copper area under its body, the module's antenna)
    for fp in board.GetFootprints():
        for z in fp.Zones():
            if not z.GetIsRuleArea():
                continue
            on = tuple(i for i, lid in enumerate(LAYERS) if z.IsOnLayer(lid))
            pts = poly_points(z.Outline().Outline(0))
            if on and z.GetDoNotAllowTracks():
                out.append((on, '', 'poly', (pts, None), 'keepT', 0.0, None))
            if on and z.GetDoNotAllowVias():
                out.append((ALL, '', 'poly', (pts, None), 'keepV', 0.0, None))
    return out, outline


class Grid:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0 = x0, y0
        self.W, self.H = int((x1 - x0) / RES) + 1, int((y1 - y0) / RES) + 1
        self.gx = x0 + RES * np.arange(self.W)
        self.gy = y0 + RES * np.arange(self.H)

    def box(self, xa, ya, xb, yb):
        i0, i1 = max(0, int((xa - self.x0) / RES)), min(self.W, int((xb - self.x0) / RES) + 2)
        j0, j1 = max(0, int((ya - self.y0) / RES)), min(self.H, int((yb - self.y0) / RES) + 2)
        return (slice(j0, j1), slice(i0, i1)) if i1 > i0 and j1 > j0 else None

    def cell(self, x, y):
        return int(round((y - self.y0) / RES)), int(round((x - self.x0) / RES))

    def xy(self, j, i):
        return round(self.x0 + i * RES, 4), round(self.y0 + j * RES, 4)

    def seg_dist(self, sl, x1, y1, x2, y2):
        X, Y = self.gx[sl[1]][None, :], self.gy[sl[0]][:, None]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 == 0:
            return np.hypot(X - x1, Y - y1)
        t = np.clip(((X - x1) * dx + (Y - y1) * dy) / L2, 0, 1)
        return np.hypot(X - x1 - t * dx, Y - y1 - t * dy)

    def poly_dist(self, pts, M):
        """(slices, signed distance) over the polygon's box grown by M"""
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        sl = self.box(min(xs) - M, min(ys) - M, max(xs) + M, max(ys) + M)
        if sl is None:
            return None, None
        j0, i0 = sl[0].start, sl[1].start
        d = np.full((sl[0].stop - j0, sl[1].stop - i0), 1e9)
        inside = np.zeros(d.shape, bool)
        X = self.gx[sl[1]]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            e = self.box(min(ax, bx) - M, min(ay, by) - M, max(ax, bx) + M, max(ay, by) + M)
            if e is not None:
                loc = (slice(e[0].start - j0, e[0].stop - j0), slice(e[1].start - i0, e[1].stop - i0))
                d[loc] = np.minimum(d[loc], self.seg_dist(e, ax, ay, bx, by))
            if ay != by:
                r0 = max(j0, int(math.ceil((min(ay, by) - self.y0) / RES)))
                r1 = min(sl[0].stop, int(math.ceil((max(ay, by) - self.y0) / RES)))
                if r1 > r0:
                    Y = self.gy[r0:r1][:, None]
                    inside[r0 - j0:r1 - j0, :] ^= X[None, :] < ax + (Y - ay) * (bx - ax) / (by - ay)
        return sl, np.where(inside, -d, d)                    # negative inside: minus the distance to the outline


def route(board, shapes, outline, net, pa, pb, la, lb, width, margin, allow_rip, mine, via_mm=3.0, greed=1.15, drop_via=False):
    """returns (message, number of board items taken out). With drop_via, pb is ignored: the path runs from the
    copper at pa, on the parts side, to the nearest place a via fits, and ends in a via there (for a pad that
    should reach the ground plane)."""
    clr = max(to_mm(board.GetDesignSettings().m_MinClearance), 0.15)
    edge_clr = max(to_mm(board.GetDesignSettings().m_CopperEdgeClearance), 0.3)
    hole_clr = max(to_mm(board.GetDesignSettings().m_HoleClearance), edge_clr)
    bb = board.GetBoardEdgesBoundingBox()
    x0 = max(min(pa[0], pb[0]) - margin, to_mm(bb.GetLeft()))
    y0 = max(min(pa[1], pb[1]) - margin, to_mm(bb.GetTop()))
    x1 = min(max(pa[0], pb[0]) + margin, to_mm(bb.GetRight()))
    y1 = min(max(pa[1], pb[1]) + margin, to_mm(bb.GetBottom()))
    g = Grid(x0, y0, x1, y1)
    H, W = g.H, g.W
    blockT = [np.zeros((H, W), bool) for _ in ALL]
    blockV = np.zeros((H, W), bool)
    softT = [np.zeros((H, W), np.float32) for _ in ALL]
    softV = np.zeros((H, W), np.float32)
    own = [np.zeros((H, W), bool) for _ in ALL]
    core = [np.zeros((H, W), bool) for _ in ALL]
    through = np.zeros((H, W), bool)
    pads_own, soft_shapes, soft_gap, own_segs = [], [], [], []

    def gap_to(n, cls):
        """clearance wanted between this net's new copper and a track or via of net n"""
        if cls in ('track', 'via') and n and ((touchy(n) and not touchy(net) and not steady(net)) or
                                               (touchy(net) and not touchy(n) and not steady(n))):
            return max(clr, TOUCH_GAP)
        return clr

    M = 0.8
    sl, d = g.poly_dist(outline, 0.0)
    off = np.ones((H, W), bool)
    if sl is not None:
        off[sl] = d > 0
    for b_ in blockT:
        b_ |= off
    blockV |= off
    for shape in shapes:
        layers, n, kind, data, cls, price, item = shape
        if kind == 'seg':
            xa, ya, xb, yb, r = data
            sl = g.box(min(xa, xb) - r - M, min(ya, yb) - r - M, max(xa, xb) + r + M, max(ya, yb) + r + M)
            if sl is None:
                continue
            d = g.seg_dist(sl, xa, ya, xb, yb) - r
        else:
            sl, d = g.poly_dist(data[0], M)
            if sl is None:
                continue
        if cls in ('edge', 'hole'):
            c_ = hole_clr if cls == 'hole' else edge_clr
            for L in layers:
                blockT[L][sl] |= d < c_ + width / 2 + EPS
            blockV[sl] |= d < c_ + VIA / 2 + EPS
        elif cls == 'keepT':
            for L in layers:
                blockT[L][sl] |= d < width / 2 + EPS
        elif cls == 'keepV':
            blockV[sl] |= d < VIA / 2 + EPS
        elif cls == 'keepTouch':
            if touchy(net):
                for L in layers:
                    blockT[L][sl] |= d < width / 2 + EPS
                blockV[sl] |= d < VIA / 2 + EPS
        elif n == net:
            # a new via keeps clear of this net's own holes too: 0.25 mm from a plated pad's copper (its
            # hole or slot is inside that), hole to hole from a via; and when dropping a via to the plane,
            # 0.8 mm centre to centre from one already there
            if cls == 'pth':
                blockV[sl] |= d < VIA / 2 + 0.25
            elif cls == 'via':
                blockV[sl] |= d < (0.55 if drop_via else 0.3 + EPS)
            if kind == 'seg':
                own_segs.append((layers, data, cls))
            if cls == 'via':
                d = d + data[4] - 0.06            # KiCad joins a track to a via only near the via's centre
            for L in layers:
                own[L][sl] |= d <= 0
                core[L][sl] |= d <= -CORE
            if cls in ('via', 'pth'):
                through[sl] |= d <= 0
            if cls == 'smd':
                blockV[sl] |= d < VIA / 2 + 0.1       # a via stands 0.1 mm off the pad it serves, not against it
                pads_own.append((layers[0], data))
        elif price and allow_rip:
            c_ = gap_to(n, cls)
            soft_shapes.append(shape)
            soft_gap.append(c_)
            for L in layers:
                np.maximum(softT[L][sl], np.where(d < c_ + width / 2 + EPS, price, 0).astype(np.float32), out=softT[L][sl])
            hole = 0.25 + DRILL / 2 + EPS if cls == 'via' else 0.0
            np.maximum(softV[sl], np.where(d < max(c_ + VIA / 2 + EPS, hole), price, 0).astype(np.float32), out=softV[sl])
        else:
            c_ = gap_to(n, cls)
            for L in layers:
                blockT[L][sl] |= d < c_ + width / 2 + EPS
            blockV[sl] |= d < c_ + VIA / 2 + EPS
            if cls in ('via', 'pth', 'hole'):                       # hole to hole
                blockV[sl] |= d < 0.25 + DRILL / 2 + EPS
    for b_ in blockT:
        blockV |= b_
    blockV_base = blockV
    # the two islands of this net's copper
    eight = np.ones((3, 3), bool)
    lab = [ndimage.label(own[L], structure=eight)[0] for L in ALL]
    count = [int(l.max()) for l in lab]
    base = [sum(count[:L]) for L in ALL]              # island numbers of layer L start after base[L]
    parent = list(range(sum(count) + 1))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for La in ALL:                                     # a via or a plated hole joins the layers it is on
        for Lb in ALL[La + 1:]:
            tj, ti = np.nonzero(through & (lab[La] > 0) & (lab[Lb] > 0))
            for j, i in zip(tj, ti):
                a, b_ = find(int(lab[La][j, i]) + base[La]), find(int(lab[Lb][j, i]) + base[Lb])
                parent[a] = b_

    def island(p, layers_):
        best = None
        for L in layers_:
            js, is_ = np.nonzero(own[L])
            if not len(js):
                continue
            dd = np.hypot(g.gx[is_] - p[0], g.gy[js] - p[1])
            k = int(dd.argmin())
            if best is None or dd[k] < best[0]:
                best = (dd[k], find(int(lab[L][js[k], is_[k]]) + base[L]))
        if best is None or best[0] > 1.0:
            return None
        return best[1]

    ia, ib = island(pa, la), (-1 if drop_via else island(pb, lb))
    if ia is None or ib is None:
        return 'no copper of this net found at one end', 0
    if ia == ib:
        return 'the two ends already touch', 0
    roots = [np.array([0] + [find(k + base[L]) for k in range(1, count[L] + 1)]) for L in ALL]
    isl = [roots[L][lab[L]] for L in ALL]
    src = [(isl[L] == ia) & core[L] & ~blockT[L] for L in ALL]
    dst = [(isl[L] == ib) & core[L] & ~blockT[L] for L in ALL]
    if drop_via:
        near = np.hypot(g.gx[None, :] - pa[0], g.gy[:, None] - pa[1]) < 0.9
        src = [src[0] & near] + [np.zeros((H, W), bool) for _ in ALL[1:]]
        away = ~ndimage.binary_dilation(src[0], structure=np.ones((3, 3), bool), iterations=int(0.45 / RES))
        dst = [~blockV & ~blockT[0] & away] + [np.zeros((H, W), bool) for _ in ALL[1:]]
    if not any(m.any() for m in src) or not any(m.any() for m in dst):
        return 'one end has no copper a %.2f mm track may start from' % width, 0
    # no via within 0.35 mm of either end unless it sits on the end itself: a via a step or two away
    # leaves a fragment of track too short for KiCad to count as joined
    ends = np.zeros((H, W), bool)
    for m in src + dst:
        ends |= m
    if not drop_via:
        blockV = blockV_base | (ndimage.binary_dilation(ends, structure=eight, iterations=int(0.35 / RES)) & ~ends)
    tj = np.concatenate([np.nonzero(dst[L])[0] for L in ALL])
    ti = np.concatenate([np.nonzero(dst[L])[1] for L in ALL])
    bj0, bj1, bi0, bi1 = int(tj.min()), int(tj.max()), int(ti.min()), int(ti.max())

    def h(j, i):
        dj = bj0 - j if j < bj0 else (j - bj1 if j > bj1 else 0)
        di = bi0 - i if i < bi0 else (i - bi1 if i > bi1 else 0)
        return (max(dj, di) + 0.4142 * min(dj, di)) * greed

    via_cost = via_mm / RES
    lcost = LCOST
    softAny = softT[0].copy()                          # a via goes through every layer
    for m in softT[1:]:
        np.maximum(softAny, m, out=softAny)
    best, came, heap = {}, {}, []
    for L in ALL:
        for j, i in zip(*np.nonzero(src[L])):
            s = (L, int(j), int(i))
            best[s] = 0.0
            came[s] = (None, -1)
            heapq.heappush(heap, (h(int(j), int(i)), 0.0, s))
    moves = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    end = None
    pops = 0
    while heap:
        f, c, s = heapq.heappop(heap)
        if c > best.get(s, 1e18):
            continue
        L, j, i = s
        if dst[L][j, i]:
            end = s
            break
        pops += 1
        if pops > 6_000_000:
            return 'search gave up', 0
        pd = came[s][1]
        bT, sT = blockT[L], softT[L]
        for k, (dj, di) in enumerate(moves):
            nj, ni = j + dj, i + di
            if nj < 0 or ni < 0 or nj >= H or ni >= W or bT[nj, ni]:
                continue
            nc = c + (1.0 if k < 4 else 1.4142) * lcost[L] + (0.0 if pd in (k, -1) else 0.6) + float(sT[nj, ni])
            ns = (L, nj, ni)
            if nc < best.get(ns, 1e18):
                best[ns] = nc
                came[ns] = (s, k)
                heapq.heappush(heap, (nc + h(nj, ni), nc, ns))
        if not blockV[j, i] and not drop_via:
            nc = c + via_cost + 8 * float(max(softV[j, i], softAny[j, i]))
            for L2 in ALL:
                ns = (L2, j, i)
                if L2 != L and nc < best.get(ns, 1e18):
                    best[ns] = nc
                    came[ns] = (s, -1)
                    heapq.heappush(heap, (nc + h(j, i), nc, ns))
    if end is None:
        return 'no path', 0
    cells = []
    s = end
    while s is not None:
        cells.append(s)
        s = came[s][0]
    cells.reverse()
    # cells -> straight runs and vias
    runs, vias = [], []
    start = cells[0]
    for a, b_, c_ in zip(cells, cells[1:], cells[2:] + [None]):
        if a[0] != b_[0]:
            if a != start:
                runs.append((start, a))
            vias.append(a)
            start = b_
            continue
        if c_ is None or c_[0] != b_[0] or (b_[1] - a[1], b_[2] - a[2]) != (c_[1] - b_[1], c_[2] - b_[2]):
            runs.append((start, b_))
            start = b_
    if drop_via:
        vias.append(cells[-1])
    # what the path crosses comes out
    ripped = 0
    if soft_shapes:
        pts = [np.array([g.xy(j, i) for L_, j, i in cells if L_ == L] or [(1e9, 1e9)]) for L in ALL]
        vp = np.array([g.xy(j, i) for _, j, i in vias] or [(1e9, 1e9)])

        def dist(P, xa, ya, xb, yb):
            dx, dy = xb - xa, yb - ya
            L2 = dx * dx + dy * dy
            tt = np.clip(((P[:, 0] - xa) * dx + (P[:, 1] - ya) * dy) / L2, 0, 1) if L2 else 0
            return np.hypot(P[:, 0] - xa - tt * dx, P[:, 1] - ya - tt * dy)

        for (layers, n, kind, (xa, ya, xb, yb, r), cls, price, item), c_ in zip(soft_shapes, soft_gap):
            hit = any((dist(pts[L], xa, ya, xb, yb) - r < c_ + width / 2 + EPS).any() for L in layers)
            hit = hit or (dist(vp, xa, ya, xb, yb) - r < max(c_ + VIA / 2 + EPS, 0.25 + DRILL / 2 + EPS if cls == 'via' else 0)).any()
            if hit:
                board.RemoveNative(item)
                ripped += 1
    netinfo = board.FindNet(net)
    before = set(key(t) for t in board.GetTracks())
    length = 0.0
    # runs -> chains of corner points between vias; a first or last leg under 0.12 mm is folded into the next
    chains = []
    for a, b_ in runs:
        pa_, pb_ = g.xy(a[1], a[2]), g.xy(b_[1], b_[2])
        if chains and chains[-1][0] == a[0] and chains[-1][1][-1] == pa_:
            chains[-1][1].append(pb_)
        else:
            chains.append((a[0], [pa_, pb_]))
    def snap(p, L):
        """an end that lands in one of this net's tracks or vias moves onto its centre line"""
        best = None
        for layers, (xa, ya, xb, yb, r), cls in own_segs:
            if L not in layers:
                continue
            dx, dy = xb - xa, yb - ya
            L2 = dx * dx + dy * dy
            u = max(0.0, min(1.0, ((p[0] - xa) * dx + (p[1] - ya) * dy) / L2)) if L2 else 0.0
            q = (xa + u * dx, ya + u * dy)
            dq = math.dist(p, q)
            if dq <= (0.08 if cls == 'via' else r) and (best is None or dq < best[0]):
                best = (dq, q)
        if not best:
            return p
        q = (round(best[1][0], 4), round(best[1][1], 4))
        # the move must not bring the end, or a via on it, nearer to other copper than the search allowed
        j, i = g.cell(q[0], q[1])
        if not (0 <= j < H and 0 <= i < W) or blockT[L][j, i] or (p in via_at and blockV_base[j, i]):
            return p
        return q

    for L, pts in chains:
        if len(pts) > 2 and math.dist(pts[0], pts[1]) < 0.12:
            del pts[1]
        if len(pts) > 2 and math.dist(pts[-1], pts[-2]) < 0.12:
            del pts[-2]
    first, last = g.xy(cells[0][1], cells[0][2]), g.xy(cells[-1][1], cells[-1][2])
    via_at = set(g.xy(v[1], v[2]) for v in vias)
    moved = {first: snap(first, cells[0][0]), last: snap(last, cells[-1][0])}
    for L, pts in chains:
        pts[:] = [moved.get(q, q) for q in pts]
        for pa_, pb_ in zip(pts, pts[1:]):
            rb.track(board, pa_, pb_, width, netinfo, LAYERS[L])
            length += math.dist(pa_, pb_)
    for v in vias:
        q = g.xy(v[1], v[2])
        rb.via(board, moved.get(q, q), netinfo)
    # where the path starts or ends on one of this net's surface pads, run on to the pad's centre
    for s in (cells[0], cells[-1]):
        p = g.xy(s[1], s[2])
        for L, (pts_, centre) in pads_own:
            if L == s[0] and centre and math.dist(p, centre) < 1.2 and inside(p, pts_):
                rb.track(board, p, centre, min(width, 0.2), netinfo, LAYERS[L])
    mine.update(key(t) for t in board.GetTracks() if key(t) not in before)
    return 'routed %.1f mm, %d via%s%s' % (length, len(vias), '' if len(vias) == 1 else 's',
                                           ', %d items pushed out' % ripped if ripped else ''), ripped


def inside(p, pts):
    hit = False
    for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):
        if (ya > p[1]) != (yb > p[1]) and p[0] < xa + (p[1] - ya) * (xb - xa) / (yb - ya):
            hit = not hit
    return hit


def prune(board, scripted, static, keep_joined=()):
    """take out dead ends: unscripted tracks with a free end, and vias with copper on one face only.
    keep_joined: keys of tracks that stay if anything of their net ends on them part-way along (the scripted
    lanes when tidying: a line that joins a lane before its end must not cost the whole lane).
    (Plain arithmetic on purpose: KiCad's Python binding stops returning points after a few thousand
    HitTest calls in one process.)"""
    removed = 0
    pads = {}
    for layers, n, kind, data, cls, price, item in static:
        if n and cls in ('smd', 'pth', 'shape'):
            pads.setdefault(n, []).append((layers, data[0]))
    while True:
        by = {}
        for s in collect_tracks(board, scripted, set()):
            by.setdefault(s[1], []).append(s)
        dead = []
        for n, items in by.items():
            if not n or n == 'GND':
                continue

            def touched(x, y, L, me):
                for layers, pts in pads.get(n, ()):
                    if L in layers and inside((x, y), pts):
                        return True
                for s in items:
                    if s is me or L not in s[0]:
                        continue
                    xa, ya, xb, yb, r = s[3]
                    dx, dy = xb - xa, yb - ya
                    L2 = dx * dx + dy * dy
                    u = max(0.0, min(1.0, ((x - xa) * dx + (y - ya) * dy) / L2)) if L2 else 0.0
                    if math.hypot(x - xa - u * dx, y - ya - u * dy) <= r + 0.002:
                        return True
                return False

            for s in items:
                if not s[5]:
                    continue                                   # scripted
                xa, ya, xb, yb, r = s[3]
                if s[4] == 'via':
                    ok = sum(touched(xa, ya, L, s) for L in ALL) >= 2
                else:
                    ok = touched(xa, ya, s[0][0], s) and touched(xb, yb, s[0][0], s)
                    if not ok and key(s[6]) in keep_joined:
                        dx, dy = xb - xa, yb - ya
                        L2 = dx * dx + dy * dy
                        for o in items:
                            if o is s or s[0][0] not in o[0]:
                                continue
                            for px, py in ((o[3][0], o[3][1]), (o[3][2], o[3][3])):
                                u = ((px - xa) * dx + (py - ya) * dy) / L2 if L2 else 0.0
                                if 0.0 <= u <= 1.0 and math.hypot(px - xa - u * dx, py - ya - u * dy) <= r + 0.002:
                                    ok = True
                if not ok:
                    dead.append(s[6])
        if not dead:
            return removed
        for item in dead:
            board.RemoveNative(item)
        removed += len(dead)


def layers_of(description):
    if 'PTH' in description or 'F.Cu - B.Cu' in description:
        return ALL
    for i, lid in enumerate(LAYERS):
        if LAYER_NAMES[lid] in description:
            return (i,)
    return (0,)


def open_connections(only, ground=False):
    report = os.path.join(rb.WORK, 'patch_drc.json')
    env = dict(os.environ, KICAD_DOCUMENTS_HOME=os.path.join(rb.ROOT, 'kicad-user'))
    subprocess.run([KICAD_CLI, 'pcb', 'drc', '--format', 'json', '--severity-all', '-o', report, rb.BOARD],
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    out = []
    data = json.load(open(report))
    for u in data['unconnected_items']:
        a, b = u['items'][0], u['items'][1]
        net = re.search(r'\[([^\]]+)\]', a['description']).group(1)
        if (net == 'GND') == ground and (not only or net in only):
            out.append((net, (a['pos']['x'], a['pos']['y']), (b['pos']['x'], b['pos']['y']),
                        layers_of(a['description']), layers_of(b['description'])))
    # tracks and vias that break a spacing rule (the autorouter's own, mostly): where they start
    bad = []
    for v in data['violations']:
        if v['type'] in ('copper_edge_clearance', 'clearance', 'hole_clearance', 'shorting_items', 'tracks_crossing', 'items_not_allowed'):
            bad += [(i['pos']['x'], i['pos']['y']) for i in v['items'] if i['description'].startswith(('Track', 'Via'))]
    # what KiCad itself calls a dead end, and the first of any two holes drilled too close together
    loose = []
    for v in data['violations']:
        if v['type'] in ('track_dangling', 'via_dangling'):
            loose += [(i['pos']['x'], i['pos']['y']) for i in v['items']]
        elif v['type'] in ('hole_to_hole', 'holes_co_located'):
            loose.append((v['items'][0]['pos']['x'], v['items'][0]['pos']['y']))
    open_connections.loose = loose
    return out, bad


def drop(board, scripted, bad, ground=False):
    """take out the unscripted tracks and vias that start at these points: ground ones when ground is being
    routed, the others otherwise"""
    n = 0
    for t in list(board.GetTracks()):
        if (t.GetNetname() == 'GND') != ground or key(t) in scripted:
            continue
        x, y = to_mm(t.GetStart().x), to_mm(t.GetStart().y)
        if any(abs(x - bx) < 0.002 and abs(y - by) < 0.002 for bx, by in bad):
            board.RemoveNative(t)
            n += 1
    return n


def fatten_supplies(board, scripted):
    """Supply tracks on the inner layer are half-ounce copper: make each as wide as KiCad's DRC allows, trying
    0.8, 0.6, 0.4, 0.25 and 0.2 mm in turn. A track never ends up wider than DRC accepts, whatever it was."""
    def supply_tracks():
        return [t for t in board.GetTracks() if t.Type() != pcbnew.PCB_VIA_T and t.GetLayer() == rb.INNER
                and t.GetNetname() in rb.POWER_NETS and key(t) not in scripted]

    # cut long tracks into pieces of 2 mm or so first, so that one tight spot does not hold a whole run at 0.4 mm
    for t in supply_tracks():
        a, b = t.GetStart(), t.GetEnd()
        ax, ay, bx, by = to_mm(a.x), to_mm(a.y), to_mm(b.x), to_mm(b.y)
        n = int(math.dist((ax, ay), (bx, by)) / 2.0)
        if n >= 2:
            pts = [(round(ax + (bx - ax) * k / n, 4), round(ay + (by - ay) * k / n, 4)) for k in range(n + 1)]
            w, net_, layer = to_mm(t.GetWidth()), t.GetNet(), t.GetLayer()
            board.RemoveNative(t)
            for p_, q_ in zip(pts, pts[1:]):
                rb.track(board, p_, q_, w, net_, layer)
    inner = supply_tracks()
    # not beside a mounting hole's keep-out or the antenna's: those rule areas go on with the pours, after this
    # step's DRC, and a widened track's edge would end up inside one
    holes = [(to_mm(fp.GetPosition().x), to_mm(fp.GetPosition().y)) for ref, fp in rb.fps(board).items()
             if ref.startswith('H') and ref[1:].isdigit()]
    ant = rb.antenna_area(board)
    ax0, ay0, ax1, ay1 = min(p[0] for p in ant), min(p[1] for p in ant), max(p[0] for p in ant), max(p[1] for p in ant)

    def near_keepout(t):
        a, b = t.GetStart(), t.GetEnd()
        for k in (0.0, 0.5, 1.0):
            x, y = to_mm(a.x) + (to_mm(b.x) - to_mm(a.x)) * k, to_mm(a.y) + (to_mm(b.y) - to_mm(a.y)) * k
            if any(math.dist((x, y), h) < rb.HOLE_KEEP + 0.5 for h in holes) or \
                    (ax0 - 0.5 < x < ax1 + 0.5 and ay0 - 0.5 < y < ay1 + 0.5):
                return True
        return False

    todo = []
    for t in inner:
        if near_keepout(t):
            t.SetWidth(min(t.GetWidth(), mm(rb.W_POWER)))
        else:
            todo.append(t)
    for width in (0.8, 0.6, 0.4, 0.25, 0.2):
        for t in todo:
            t.SetWidth(mm(width))
        pcbnew.SaveBoard(rb.BOARD, board)
        report = os.path.join(rb.WORK, 'patch_drc.json')
        env = dict(os.environ, KICAD_DOCUMENTS_HOME=os.path.join(rb.ROOT, 'kicad-user'))
        subprocess.run([KICAD_CLI, 'pcb', 'drc', '--format', 'json', '--severity-all', '-o', report, rb.BOARD],
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
        bad = []
        for v in json.load(open(report))['violations']:
            if v['type'] in ('clearance', 'hole_clearance', 'shorting_items', 'tracks_crossing', 'copper_edge_clearance', 'items_not_allowed'):
                bad += [(i['pos']['x'], i['pos']['y']) for i in v['items']]
        # KiCad reports a track by where it starts
        hit = lambda t: any(abs(to_mm(t.GetStart().x) - x) < 0.002 and abs(to_mm(t.GetStart().y) - y) < 0.002 for x, y in bad)
        todo = [t for t in todo if hit(t)]
        if not todo:
            break
    if todo:
        print('WARNING: %d supply tracks on the inner layer still break a rule at 0.2 mm' % len(todo), flush=True)
    count = {}
    for t in inner:
        count[to_mm(t.GetWidth())] = count.get(to_mm(t.GetWidth()), 0) + to_mm(t.GetLength())
    print('supply tracks on the inner layer, mm of length by width: %s' % ', '.join('%.2f mm: %.0f' % (w, l) for w, l in sorted(count.items())), flush=True)


def plane_vias(board, scripted, static, outline, mine, reach):
    """A via beside every surface ground pad that has no ground via or plated hole within reach (mm), so each
    one reaches the inner ground plane by a short path of its own and not along a track or a piece of pour.
    Rule breaks are taken out again, checked by KiCad's DRC."""
    todo = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == 'GND' and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and p.IsOnLayer(pcbnew.F_Cu):
                c = p.GetPosition()
                todo.append(('%s.%s' % (fp.GetReference(), p.GetNumber()), (to_mm(c.x), to_mm(c.y))))
    holes = [c for (pts, c) in [(s[3][0], s[3][1]) for s in static if s[1] == 'GND' and s[4] == 'pth'] if c]
    added = failed = 0
    for rnd in range(3):
        vias = [(to_mm(t.GetPosition().x), to_mm(t.GetPosition().y)) for t in board.GetTracks()
                if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == 'GND'] + holes
        failed = 0
        for name, pa in todo:
            if min(math.dist(pa, v) for v in vias) <= reach:
                continue
            res = ('', 0)
            for width in (0.3, 0.2):
                shapes = static + collect_tracks(board, scripted, mine)
                res = route(board, shapes, outline, 'GND', pa, pa, (0,), (0,), width, 3.0, False, mine, drop_via=True)
                if res[0].startswith('routed'):
                    break
            if res[0].startswith('routed'):
                added += 1
                vias = [(to_mm(t.GetPosition().x), to_mm(t.GetPosition().y)) for t in board.GetTracks()
                        if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == 'GND'] + holes
            else:
                failed += 1
                print('  %-8s (%.1f, %.1f): %s' % (name, pa[0], pa[1], res[0]), flush=True)
        pcbnew.SaveBoard(rb.BOARD, board)
        _, bad = open_connections([], True)
        dropped = drop(board, scripted, bad, True) if bad else 0
        print('ground vias to the plane: %d added so far, %d pads without one, %d rule-breaking items taken out' % (added, failed, dropped), flush=True)
        if not dropped:
            break
        pcbnew.SaveBoard(rb.BOARD, board)


if __name__ == '__main__':
    argv = sys.argv[1:]

    def option(name, default):
        if name in argv:
            v = float(argv[argv.index(name) + 1])
            del argv[argv.index(name):argv.index(name) + 2]
            return v
        return default

    rounds, margin = int(option('--rounds', 12)), option('--margin', 10.0)
    RES = option('--res', RES)                  # a coarser grid (0.1) for a very long connection
    EPS = 0.8 * RES
    ground, tidy, no_rip = '--ground' in argv, '--tidy' in argv, '--no-rip' in argv
    reach = option('--plane-vias', 0.0)        # give every ground pad a via to the plane within this many mm
    fatten = '--fatten' in argv
    only = [a for a in argv if not a.startswith('--')]
    board = pcbnew.LoadBoard(rb.BOARD)
    scripted = scripted_keys()
    print('%d scripted tracks and vias are fixed' % len(scripted))
    mine = set()
    static, outline = collect_static(board)
    seen = set()
    for t in list(board.GetTracks()):                    # exact duplicates (same place, same layer)
        k = (key(t), t.GetNetname())
        if k in seen:
            board.RemoveNative(t)
        seen.add(k)
    n = prune(board, set() if tidy else scripted, static, scripted if tidy else ())
    if tidy:
        print('dead ends taken out: %d' % n)
        pcbnew.SaveBoard(rb.BOARD, board)
        sys.exit()
    if reach:
        plane_vias(board, scripted, static, outline, mine, reach)
        sys.exit()
    if fatten:
        fatten_supplies(board, scripted)
        sys.exit()
    for rnd in range(1, rounds + 1):
        todo, bad = open_connections(only, ground)
        dropped = drop(board, scripted, bad, ground) if bad else 0
        print('round %d: %d open%s' % (rnd, len(todo), ', %d rule-breaking tracks taken out' % dropped if dropped else ''), flush=True)
        if dropped:
            prune(board, scripted, static)
        if not todo and not dropped:
            break
        for net, pa, pb, la, lb in todo:
            widths = [rb.W_POWER, 0.25, 0.2] if net in rb.POWER_NETS else ([0.3, 0.2] if ground else [rb.W_SIGNAL_AUTO])
            res = ('', 0)
            # a clear path first, looking further afield before anything is pushed out: pushing out is
            # what makes neighbouring connections take turns undoing each other
            tries = ((False, margin), (False, margin * 3)) if no_rip else ((False, margin), (False, margin * 3), (True, margin), (True, margin * 2.5))
            # a supply keeps its full width if any of those finds a way, pushing others out if it must;
            # only then is a narrower track tried. Everything else has one width.
            attempts = [(rip, m, width) for width in widths for rip, m in tries] if net in rb.POWER_NETS else \
                       [(rip, m, width) for rip, m in tries for width in widths]
            for rip, m, width in attempts:
                shapes = static + collect_tracks(board, scripted, mine)
                vmm = 10.0 if net in rb.POWER_NETS else 3.0      # supplies stay on one layer if they can
                res = route(board, shapes, outline, net, pa, pb, la, lb, width, m, rip, mine, via_mm=vmm)
                if res[0] == 'search gave up':
                    res = route(board, shapes, outline, net, pa, pb, la, lb, width, m, rip, mine, via_mm=vmm, greed=3.0)
                if res[0].startswith(('routed', 'the two ends')):
                    break
            print('  %-12s (%.1f, %.1f) to (%.1f, %.1f): %s' % (net, pa[0], pa[1], pb[0], pb[1], res[0]), flush=True)
            if res[1]:
                prune(board, scripted, static)
        prune(board, scripted, static)
        pcbnew.SaveBoard(rb.BOARD, board)
