#!/usr/bin/env python3
"""Close the connections the autorouter left open, without moving anything drawn by script.

    $KPY tools/patch_route.py [--rounds 12] [--margin 10] [NET ...]     signals and supplies
    $KPY tools/patch_route.py --ground                                  then ground, pad to pad, before the pours
    $KPY tools/patch_route.py --no-rip                                  only clear paths: nothing is pushed out
    $KPY tools/patch_route.py --tidy                                    dead ends, scripted or not (then tools/trim_dangling.py)

Each round: run KiCad's DRC for the list of open (non-ground) connections, then for each one search a
0.05 mm grid, on both faces, for a path between the two pieces of copper. Pads, scripted tracks (those in
build/pcb/strip.kicad_pcb), the board edge, the antenna zone and the touch copper's keep-outs are fixed
obstacles at the board's clearance. If there is no path, the search is repeated with the autorouter's
tracks made passable at a price; whatever the new path crosses is taken out (with any dead ends that
leaves) and comes back as an open connection in the next round. Tracks are 45-degree; a via costs about
3 mm of track and the show face costs more than the parts side.
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
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
KICAD_CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
SOFT, SOFT_MINE = 15.0, 45.0            # price per grid cell of crossing an autorouted track, or one of ours


def key(t):
    """identifies a track or via by where it is, to 0.02 mm"""
    r = lambda v: round(v / 20000)
    a, b = sorted([(r(t.GetStart().x), r(t.GetStart().y)), (r(t.GetEnd().x), r(t.GetEnd().y))])
    return ('via' if t.Type() == pcbnew.PCB_VIA_T else board_layer_name(t.GetLayer()), a, b)


def board_layer_name(layer):
    return 'F.Cu' if layer == pcbnew.F_Cu else 'B.Cu'


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
            out.append(((0, 1), n, 'seg', (to_mm(p.x), to_mm(p.y), to_mm(p.x), to_mm(p.y), to_mm(t.GetWidth(pcbnew.F_Cu)) / 2), 'via', price, t))
        else:
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
                    out.append(((0, 1), '', 'seg', (to_mm(c.x), to_mm(c.y), to_mm(c.x), to_mm(c.y), to_mm(p.GetDrillSize().x) / 2), 'hole', 0.0, None))
                continue
            for i in on:
                ps = p.GetEffectivePolygon(LAYERS[i], pcbnew.ERROR_INSIDE)
                out.append(((i,), p.GetNetname(), 'poly', (poly_points(ps.Outline(0)), (to_mm(c.x), to_mm(c.y))), 'pth' if len(on) == 2 else 'smd', 0.0, None))
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
            out.append(((0, 1), '', 'seg', (a[0], a[1], b[0], b[1], 0.0), 'edge', 0.0, None))
    # keep-outs, the same ones the autorouter is given
    out.append(((1,), '', 'poly', (rb.band_polygon(0.2, rb.BAND[1] + 0.6, 0.0, rb.mo.spine_len), None), 'keepT', 0.0, None))
    out.append(((0, 1), '', 'poly', (rb.band_polygon(rb.BAND[0] - 0.4, rb.BAND[1] + 0.6, 0.0, rb.mo.spine_len), None), 'keepV', 0.0, None))
    out.append(((0, 1), '', 'poly', (rb.band_polygon(0.2, rb.STRIP[1] + 0.3, 0.0, rb.mo.spine_len), None), 'keepV', 0.0, None))
    for poly in rb.touch_areas(0.6)[1:]:
        out.append(((1,), '', 'poly', (poly, None), 'keepT', 0.0, None))
        out.append(((0, 1), '', 'poly', (poly, None), 'keepV', 0.0, None))
    for poly in rb.hole_areas(board):
        out.append(((0, 1), '', 'poly', (poly, None), 'keepT', 0.0, None))
        out.append(((0, 1), '', 'poly', (poly, None), 'keepV', 0.0, None))
    for outer, inner in rb.quiet_areas(board):
        out.append(((1,), '', 'poly', (outer, None), 'keepT', 0.0, None))
        out.append(((0, 1), '', 'poly', (outer, None), 'keepV', 0.0, None))
        out.append(((0,), '', 'poly', (inner, None), 'keepT', 0.0, None))
    ant = rb.antenna_area(board)
    out.append(((0, 1), '', 'poly', (ant, None), 'keepT', 0.0, None))
    out.append(((0, 1), '', 'poly', (ant, None), 'keepV', 0.0, None))
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
                out.append(((0, 1), '', 'poly', (pts, None), 'keepV', 0.0, None))
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


def route(board, shapes, outline, net, pa, pb, la, lb, width, margin, allow_rip, mine, bcost=1.5, via_mm=3.0, greed=1.15):
    """returns (message, number of board items taken out)"""
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
    blockT = [np.zeros((H, W), bool), np.zeros((H, W), bool)]
    blockV = np.zeros((H, W), bool)
    softT = [np.zeros((H, W), np.float32), np.zeros((H, W), np.float32)]
    softV = np.zeros((H, W), np.float32)
    own = [np.zeros((H, W), bool), np.zeros((H, W), bool)]
    core = [np.zeros((H, W), bool), np.zeros((H, W), bool)]
    through = np.zeros((H, W), bool)
    pads_own, soft_shapes, own_segs = [], [], []
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
        elif n == net:
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
                blockV[sl] |= d < VIA / 2
                pads_own.append((layers[0], data))
        elif price and allow_rip:
            soft_shapes.append(shape)
            for L in layers:
                np.maximum(softT[L][sl], np.where(d < clr + width / 2 + EPS, price, 0).astype(np.float32), out=softT[L][sl])
            hole = 0.25 + DRILL / 2 + EPS if cls == 'via' else 0.0
            np.maximum(softV[sl], np.where(d < max(clr + VIA / 2 + EPS, hole), price, 0).astype(np.float32), out=softV[sl])
        else:
            for L in layers:
                blockT[L][sl] |= d < clr + width / 2 + EPS
            blockV[sl] |= d < clr + VIA / 2 + EPS
            if cls in ('via', 'pth', 'hole'):                       # hole to hole
                blockV[sl] |= d < 0.25 + DRILL / 2 + EPS
    blockV |= blockT[0] | blockT[1]
    blockV_base = blockV
    # the two islands of this net's copper
    eight = np.ones((3, 3), bool)
    lab = [ndimage.label(own[L], structure=eight)[0] for L in (0, 1)]
    nF, nB = int(lab[0].max()), int(lab[1].max())
    parent = list(range(nF + nB + 1))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    tj, ti = np.nonzero(through & (lab[0] > 0) & (lab[1] > 0))
    for j, i in zip(tj, ti):
        a, b_ = find(int(lab[0][j, i])), find(int(lab[1][j, i]) + nF)
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
                best = (dd[k], find(int(lab[L][js[k], is_[k]]) + (nF if L else 0)))
        if best is None or best[0] > 1.0:
            return None
        return best[1]

    ia, ib = island(pa, la), island(pb, lb)
    if ia is None or ib is None:
        return 'no copper of this net found at one end', 0
    if ia == ib:
        return 'the two ends already touch', 0
    roots = [np.array([0] + [find(k) for k in range(1, nF + 1)]), np.array([0] + [find(k + nF) for k in range(1, nB + 1)])]
    isl = [roots[L][lab[L]] for L in (0, 1)]
    src = [(isl[L] == ia) & core[L] & ~blockT[L] for L in (0, 1)]
    dst = [(isl[L] == ib) & core[L] & ~blockT[L] for L in (0, 1)]
    if not (src[0].any() or src[1].any()) or not (dst[0].any() or dst[1].any()):
        return 'one end has no copper a %.2f mm track may start from' % width, 0
    # no via within 0.35 mm of either end unless it sits on the end itself: a via a step or two away
    # leaves a fragment of track too short for KiCad to count as joined
    ends = src[0] | src[1] | dst[0] | dst[1]
    blockV = blockV_base | (ndimage.binary_dilation(ends, structure=eight, iterations=int(0.35 / RES)) & ~ends)
    tj = np.concatenate([np.nonzero(dst[L])[0] for L in (0, 1)])
    ti = np.concatenate([np.nonzero(dst[L])[1] for L in (0, 1)])
    bj0, bj1, bi0, bi1 = int(tj.min()), int(tj.max()), int(ti.min()), int(ti.max())

    def h(j, i):
        dj = bj0 - j if j < bj0 else (j - bj1 if j > bj1 else 0)
        di = bi0 - i if i < bi0 else (i - bi1 if i > bi1 else 0)
        return (max(dj, di) + 0.4142 * min(dj, di)) * greed

    via_cost = via_mm / RES
    lcost = (1.0, bcost)
    best, came, heap = {}, {}, []
    for L in (0, 1):
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
        if not blockV[j, i]:
            ns = (1 - L, j, i)
            nc = c + via_cost + 8 * float(max(softV[j, i], softT[1 - L][j, i]))
            if nc < best.get(ns, 1e18):
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
    # what the path crosses comes out
    ripped = 0
    if soft_shapes:
        pts = [np.array([g.xy(j, i) for L_, j, i in cells if L_ == L] or [(1e9, 1e9)]) for L in (0, 1)]
        vp = np.array([g.xy(j, i) for _, j, i in vias] or [(1e9, 1e9)])

        def dist(P, xa, ya, xb, yb):
            dx, dy = xb - xa, yb - ya
            L2 = dx * dx + dy * dy
            tt = np.clip(((P[:, 0] - xa) * dx + (P[:, 1] - ya) * dy) / L2, 0, 1) if L2 else 0
            return np.hypot(P[:, 0] - xa - tt * dx, P[:, 1] - ya - tt * dy)

        for layers, n, kind, (xa, ya, xb, yb, r), cls, price, item in soft_shapes:
            hit = any((dist(pts[L], xa, ya, xb, yb) - r < clr + width / 2 + EPS).any() for L in layers)
            hit = hit or (dist(vp, xa, ya, xb, yb) - r < max(clr + VIA / 2 + EPS, 0.25 + DRILL / 2 + EPS if cls == 'via' else 0)).any()
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
        return (round(best[1][0], 4), round(best[1][1], 4)) if best else p

    for L, pts in chains:
        if len(pts) > 2 and math.dist(pts[0], pts[1]) < 0.12:
            del pts[1]
        if len(pts) > 2 and math.dist(pts[-1], pts[-2]) < 0.12:
            del pts[-2]
    first, last = g.xy(cells[0][1], cells[0][2]), g.xy(cells[-1][1], cells[-1][2])
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


def prune(board, scripted, static):
    """take out dead ends: unscripted tracks with a free end, and vias with copper on one face only.
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
                    ok = touched(xa, ya, 0, s) and touched(xa, ya, 1, s)
                else:
                    ok = touched(xa, ya, s[0][0], s) and touched(xb, yb, s[0][0], s)
                if not ok:
                    dead.append(s[6])
        if not dead:
            return removed
        for item in dead:
            board.RemoveNative(item)
        removed += len(dead)


def layers_of(description):
    if 'PTH' in description or 'F.Cu - B.Cu' in description:
        return (0, 1)
    return (1,) if 'B.Cu' in description else (0,)


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


def drop(board, scripted, bad):
    """take out the unscripted, non-ground tracks and vias that start at these points"""
    n = 0
    for t in list(board.GetTracks()):
        if t.GetNetname() == 'GND' or key(t) in scripted:
            continue
        x, y = to_mm(t.GetStart().x), to_mm(t.GetStart().y)
        if any(abs(x - bx) < 0.002 and abs(y - by) < 0.002 for bx, by in bad):
            board.RemoveNative(t)
            n += 1
    return n


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
    n = prune(board, set() if tidy else scripted, static)
    if tidy:
        print('dead ends taken out: %d' % n)
        pcbnew.SaveBoard(rb.BOARD, board)
        sys.exit()
    for rnd in range(1, rounds + 1):
        todo, bad = open_connections(only, ground)
        dropped = drop(board, scripted, bad) if bad else 0
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
            for rip, m in tries:
                for width in widths:
                    shapes = static + collect_tracks(board, scripted, mine)
                    res = route(board, shapes, outline, net, pa, pb, la, lb, width, m, rip, mine)
                    if res[0] == 'search gave up':
                        res = route(board, shapes, outline, net, pa, pb, la, lb, width, m, rip, mine, greed=3.0)
                    if res[0].startswith(('routed', 'the two ends')):
                        break
                if res[0].startswith(('routed', 'the two ends')):
                    break
            print('  %-12s (%.1f, %.1f) to (%.1f, %.1f): %s' % (net, pa[0], pa[1], pb[0], pb[1], res[0]), flush=True)
            if res[1]:
                prune(board, scripted, static)
        prune(board, scripted, static)
        pcbnew.SaveBoard(rb.BOARD, board)
