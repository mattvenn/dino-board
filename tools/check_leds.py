"""Check every side LED on a board: the emitting face points off the board (or into a hole), how far the
face is from that edge, and that each chain runs in order (D1..D20 spine, D21..D22 eye)."""
import sys, math, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
outline, holes = None, []
for d in b.GetDrawings():
    if d.GetLayer() != pcbnew.Edge_Cuts:
        continue
    if d.GetShape() == pcbnew.SHAPE_T_POLY:
        outline = d.GetPolyShape()
    elif d.GetShape() == pcbnew.SHAPE_T_CIRCLE:
        c = d.GetCenter()
        holes.append((c.x, c.y, d.GetRadius()))

def on_board(x, y):
    if not outline.Contains(pcbnew.VECTOR2I(int(x), int(y))):
        return False
    return not any(math.hypot(x - hx, y - hy) < r for hx, hy, r in holes)

num = lambda f: int(f.GetReference()[1:])
leds = sorted([f for f in b.GetFootprints() if f.GetValue() == 'SK6812SIDE-A'], key=num)
bad, gaps = 0, []
for f in leds:
    th = math.radians(f.GetOrientationDegrees())
    n = (math.sin(th), math.cos(th))
    p = f.GetPosition()
    at = lambda m: (p.x + n[0] * pcbnew.FromMM(m), p.y + n[1] * pcbnew.FromMM(m))
    ok = on_board(*at(1.36)) and not on_board(*at(2.5)) and on_board(*at(-2.5))
    lo, hi = 0.0, 2.5
    for _ in range(30):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if on_board(*at(m)) else (lo, m)
    gaps.append(lo - 1.36)
    if not ok:
        bad += 1
        print('CHECK', f.GetReference(), 'does not face an edge')
chain = 0
pad = lambda fp, k: [q for q in fp.Pads() if q.GetNumber() == k][0].GetPosition()
dist = lambda u, v: math.hypot(u.x - v.x, u.y - v.y)
for a, c in zip(leds, leds[1:]):
    if num(a) == 20:
        continue                                           # D20 ends the spine; D21 starts the eye
    if dist(pad(a, '3'), pad(c, '1')) > dist(pad(a, '1'), pad(c, '1')):
        chain += 1
        print('CHAIN', a.GetReference(), 'DOUT is further from', c.GetReference(), 'than its DIN')
print('%d LEDs, %d facing wrong, %d chain-direction problems; emitting face %.2f to %.2f mm inside its edge'
      % (len(leds), bad, chain, min(gaps), max(gaps)))
