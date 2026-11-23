#!/usr/bin/env python3
"""Draw part of the board as a picture, for looking at routing: tools/view_region.py x0 y0 x1 y1 out.png [drc.json]
Coordinates are BOARD mm (parts side as KiCad shows it). Parts-side copper red, inner signal layer orange,
show-face copper blue,
vias green, pads grey with their net names, open connections from a DRC report as yellow lines.
Needs KiCad's Python and rsvg-convert."""
import json
import re
import subprocess
import sys

import pcbnew

x0, y0, x1, y1 = map(float, sys.argv[1:5])
out = sys.argv[5]
drc = sys.argv[6] if len(sys.argv) > 6 else None
board = pcbnew.LoadBoard('dinolight.kicad_pcb')
mm = pcbnew.ToMM
S = 1400 / (x1 - x0)                                  # pixels per mm
W, H = (x1 - x0) * S, (y1 - y0) * S


def X(v):
    return (v - x0) * S


def Y(v):
    return (v - y0) * S


def inside(x, y, m=3):
    return x0 - m <= x <= x1 + m and y0 - m <= y <= y1 + m


s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" font-family="Helvetica">' % (W, H),
     '<rect width="100%" height="100%" fill="#111"/>']
for g in range(int(x0), int(x1) + 1):
    s.append('<line x1="%.1f" y1="0" x2="%.1f" y2="%d" stroke="#fff" stroke-opacity="%s" stroke-width="1"/>' % (X(g), X(g), H, 0.25 if g % 5 == 0 else 0.08))
    if g % 5 == 0:
        s.append('<text x="%.1f" y="12" font-size="12" fill="#aaa">%d</text>' % (X(g) + 2, g))
for g in range(int(y0), int(y1) + 1):
    s.append('<line x1="0" y1="%.1f" x2="%d" y2="%.1f" stroke="#fff" stroke-opacity="%s" stroke-width="1"/>' % (Y(g), W, Y(g), 0.25 if g % 5 == 0 else 0.08))
    if g % 5 == 0:
        s.append('<text x="2" y="%.1f" font-size="12" fill="#aaa">%d</text>' % (Y(g) - 2, g))
for d in board.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts and d.GetShape() == pcbnew.SHAPE_T_POLY:
        pts = d.GetPolyShape().Outline(0)
        s.append('<polygon points="%s" fill="none" stroke="#ee0" stroke-width="2"/>' % ' '.join(
            '%.1f,%.1f' % (X(mm(pts.CPoint(i).x)), Y(mm(pts.CPoint(i).y))) for i in range(pts.PointCount())))
for z in board.Zones():
    if z.GetIsRuleArea():
        continue
    if z.GetLayer() == pcbnew.B_Cu and z.GetNetname() != 'GND':
        o = z.Outline().Outline(0)
        s.append('<polygon points="%s" fill="#26a" fill-opacity="0.25" stroke="none"/>' % ' '.join(
            '%.1f,%.1f' % (X(mm(o.CPoint(i).x)), Y(mm(o.CPoint(i).y))) for i in range(o.PointCount())))
for layer, colour in ((pcbnew.B_Cu, '#39f'), (pcbnew.In2_Cu, '#fa0'), (pcbnew.F_Cu, '#e33')):
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T or t.GetLayer() != layer:
            continue
        a, b = t.GetStart(), t.GetEnd()
        if inside(mm(a.x), mm(a.y)) or inside(mm(b.x), mm(b.y)):
            s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-opacity="0.8" stroke-width="%.1f" stroke-linecap="round"><title>%s</title></line>'
                     % (X(mm(a.x)), Y(mm(a.y)), X(mm(b.x)), Y(mm(b.y)), colour, mm(t.GetWidth()) * S, t.GetNetname()))
for fp in board.GetFootprints():
    for p in fp.Pads():
        c = p.GetPosition()
        if not inside(mm(c.x), mm(c.y)):
            continue
        bb = p.GetBoundingBox()
        s.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#999" fill-opacity="0.6"/>'
                 % (X(mm(bb.GetLeft())), Y(mm(bb.GetTop())), mm(bb.GetWidth()) * S, mm(bb.GetHeight()) * S))
        n = p.GetNetname()
        if n and n != 'GND':
            s.append('<text x="%.1f" y="%.1f" font-size="%.1f" fill="#fff" text-anchor="middle">%s</text>'
                     % (X(mm(c.x)), Y(mm(c.y)) + 3, min(9, 0.28 * S), n[:9]))
    c = fp.GetPosition()
    if inside(mm(c.x), mm(c.y), 0):
        s.append('<text x="%.1f" y="%.1f" font-size="11" fill="#6f6" text-anchor="middle">%s</text>'
                 % (X(mm(c.x)), Y(mm(c.y)) - 6, fp.GetReference()))
for t in board.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        c = t.GetStart()
        if inside(mm(c.x), mm(c.y)):
            s.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#3c3" fill-opacity="0.8"><title>%s</title></circle>'
                     % (X(mm(c.x)), Y(mm(c.y)), mm(t.GetWidth(pcbnew.F_Cu)) * S / 2, t.GetNetname()))
if drc:
    for u in json.load(open(drc))['unconnected_items']:
        a, b = u['items'][0], u['items'][1]
        net = re.search(r'\[([^\]]+)\]', a['description']).group(1)
        if net == 'GND':
            continue
        pa, pb = a['pos'], b['pos']
        if inside(pa['x'], pa['y'], 0) or inside(pb['x'], pb['y'], 0):
            s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#ff0" stroke-width="2" stroke-dasharray="6 4"/>'
                     % (X(pa['x']), Y(pa['y']), X(pb['x']), Y(pb['y'])))
            s.append('<text x="%.1f" y="%.1f" font-size="13" fill="#ff0">%s</text>' % (X(pa['x']) + 4, Y(pa['y']) - 4, net))
s.append('</svg>')
svg = out.rsplit('.', 1)[0] + '.svg'
open(svg, 'w').write('\n'.join(s))
subprocess.run(['rsvg-convert', svg, '-o', out], check=True)
print('wrote', out)
