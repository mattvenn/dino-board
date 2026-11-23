#!/usr/bin/env python3
"""Take out what the routers laid too near a touch line, so tools/patch_route.py can lay it again further off:
    $KPY tools/clear_touch_neighbours.py
- unscripted tracks and vias of signal nets (not ground, not a supply, not a touch line) within
  patch_route.TOUCH_GAP of a touch line's track or via;
- unscripted pieces of a touch line inside the battery area or within 0.6 mm of it.
Run patch_route.py afterwards: everything removed comes back as an open connection."""
import math
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_board as bb
import patch_route as pr
import route_board as rb

board = pcbnew.LoadBoard(rb.BOARD)
scripted = pr.scripted_keys()
mm = rb.to_mm


def shape(t):
    a, b = t.GetStart(), t.GetEnd()
    via = t.Type() == pcbnew.PCB_VIA_T
    return (mm(a.x), mm(a.y), mm(b.x), mm(b.y), mm(t.GetWidth(pcbnew.F_Cu) if via else t.GetWidth()) / 2), (None if via else t.GetLayer())


def gap(s1, s2):
    best = 1e9
    for (xa, ya, xb, yb, _), (xc, yc, xd, yd, _) in ((s1, s2), (s2, s1)):
        n = max(1, int(math.hypot(xb - xa, yb - ya) / 0.05))
        dx, dy = xd - xc, yd - yc
        L2 = dx * dx + dy * dy
        for k in range(n + 1):
            x, y = xa + (xb - xa) * k / n, ya + (yb - ya) * k / n
            u = max(0.0, min(1.0, ((x - xc) * dx + (y - yc) * dy) / L2)) if L2 else 0.0
            best = min(best, math.hypot(x - xc - u * dx, y - yc - u * dy))
    return best - s1[4] - s2[4]


touch = [(shape(t), t) for t in board.GetTracks() if pr.touchy(t.GetNetname())]
x0, y0, x1, y1 = bb.BATTERY
(bx0, by0), (bx1, by1) = rb.B(x1 + 0.6, y0 - 0.6), rb.B(x0 - 0.6, y1 + 0.6)
doomed, names = [], {}
for t in board.GetTracks():
    n = t.GetNetname()
    if pr.key(t) in scripted:
        continue
    if pr.touchy(n):
        if any(bx0 < mm(p.x) < bx1 and by0 < mm(p.y) < by1 for p in (t.GetStart(), t.GetEnd())):
            doomed.append(t)
            names[n] = names.get(n, 0) + 1
        continue
    if not n or pr.steady(n):
        continue
    s, lay = shape(t)
    for (ts, tlay), tt in touch:
        if lay is not None and tlay is not None and lay != tlay:
            continue
        if min(abs(s[0] - ts[0]), abs(s[0] - ts[2]), abs(s[2] - ts[0]), abs(s[2] - ts[2])) > 60:
            continue
        if gap(s, ts) < pr.TOUCH_GAP - 0.01:
            doomed.append(t)
            names[n] = names.get(n, 0) + 1
            break
for t in doomed:
    board.RemoveNative(t)
pcbnew.SaveBoard(rb.BOARD, board)
print('taken out: %d tracks and vias (%s)' % (len(doomed), ', '.join('%s %d' % kv for kv in sorted(names.items()))))
