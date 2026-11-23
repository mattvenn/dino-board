#!/usr/bin/env python3
"""Mosasaurus outline for DinoLight. Units: mm, y down, show face (front), head left.

The outline is a closed run of cubic Bezier segments, P, clockwise from the snout tip. Edit P to change
the shape; everything that sits on an edge is computed from it:

    OUTLINE   dense closed polyline of the board edge
    SPINE     the part of the top edge the LEDs run along (back of the skull to the tail base), head first
    SLIDER    the part of the top edge the touch slider follows: the same run, so touch covers every LED
    FLAT      the straight stretch of belly for the USB socket and the slide switch: (x0, y, x1, y)
    EYE       centre of the eye hole
    leds      (x, y, tangent angle) for each spine LED

Running it writes mosasaurus_outline.svg (outline only) and mosasaurus_concept.svg (with the layout idea).
An open-mouthed outline traced from a reference illustration was tried on 2026-11-22 and set aside;
it is in the git history of this file.
"""
import math

N_LED = 20

# (p0, c1, c2, p1) for each segment
P = [
    ((6, 44), (18, 38), (34, 33), (50, 30)),            # 0  top of skull
    ((50, 30), (70, 24), (100, 19), (125, 22)),         # 1  back, rising to its highest point
    ((125, 22), (152, 25), (178, 33), (200, 38)),       # 2  back, falling to the tail base
    ((200, 38), (207, 36), (215, 30), (221, 22)),       # 3  upper tail lobe, leading edge
    ((221, 22), (224, 19), (226, 22), (224, 26)),       # 4  upper lobe tip
    ((224, 26), (220, 34), (218, 41), (219, 47)),       # 5  notch
    ((219, 47), (221, 55), (225, 63), (229, 70)),       # 6  lower lobe, trailing edge
    ((229, 70), (231, 75), (227, 76), (224, 73)),       # 7  lower lobe tip
    ((224, 73), (214, 65), (202, 56), (190, 52)),       # 8  underside of tail
    ((190, 52), (178, 51.5), (163, 53), (152, 56)),     # 9
    ((152, 56), (156, 62), (160, 69), (163, 74)),       # 10 rear flipper, trailing edge
    ((163, 74), (165, 80), (159, 82), (155, 79)),       # 11 rear flipper tip
    ((155, 79), (147, 75), (140, 69), (138, 62)),       # 12 rear flipper, leading edge
    ((138, 62), (132, 65.5), (127, 68.5), (122, 68.5)), # 13 belly
    ((122, 68.5), (113, 68.5), (105, 68.5), (96, 68.5)),   # 14 belly FLAT for the connectors
    ((96, 68.5), (94.5, 68.5), (93, 68), (92, 67)),     # 15
    ((92, 67), (96, 74), (101, 82), (105, 87)),         # 16 front flipper, trailing edge
    ((105, 87), (108, 93), (102, 95), (98, 92)),        # 17 front flipper tip
    ((98, 92), (86, 87), (76, 76), (72, 64)),           # 18 front flipper, leading edge
    ((72, 64), (64, 63), (57, 61), (50, 58)),           # 19 throat
    ((50, 58), (38, 57), (22, 54), (8, 49)),            # 20 lower jaw
    ((8, 49), (3, 48), (3, 45), (6, 44)),               # 21 snout
]
SPINE_SEGS, FLAT_SEG = (1, 2), 14
EYE = (38.0, 41.0)


def bez(seg, t):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = seg
    u = 1 - t
    return (u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3,
            u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3)


def polyline(segs, n):
    pts = []
    for s in segs:
        pts += [bez(s, i / n) for i in range(n)]
    pts.append(bez(segs[-1], 1))
    return pts


OUTLINE = polyline(P, 60)[:-1]
SPINE = polyline([P[i] for i in SPINE_SEGS], 300)
SLIDER = SPINE
FLAT = (P[FLAT_SEG][3][0], P[FLAT_SEG][3][1], P[FLAT_SEG][0][0], P[FLAT_SEG][0][1])


def length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def at(pts, s, depth=0.0):
    """point at distance s along a top-edge polyline, `depth` mm in from the edge; also the tangent angle"""
    d = 0.0
    last = len(pts) - 2
    for k, (a, b) in enumerate(zip(pts, pts[1:])):
        L = math.dist(a, b)
        if d + L >= s or k == last:
            f = min(max((s - d) / L, 0.0), 1.0) if L else 0.0
            tx, ty = ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L else (1.0, 0.0)
            return (a[0] + f * (b[0] - a[0]) - ty * depth, a[1] + f * (b[1] - a[1]) + tx * depth,
                    math.degrees(math.atan2(ty, tx)))
        d += L


spine_len = slider_len = length(SPINE)
LED_MARGIN = 3.0
leds = [at(SPINE, LED_MARGIN + (spine_len - 2 * LED_MARGIN) * i / (N_LED - 1)) for i in range(N_LED)]


def inside(x, y, poly=None):
    poly = poly or OUTLINE
    hit = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


if __name__ == '__main__':
    xs, ys = [p[0] for p in OUTLINE], [p[1] for p in OUTLINE]
    W, H = math.ceil(max(xs)) + 6, math.ceil(max(ys)) + 6
    d = 'M ' + ' L '.join('%.3f %.3f' % p for p in OUTLINE) + ' Z'
    open('mosasaurus_outline.svg', 'w').write(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">'
        f'<path d="{d}" fill="none" stroke="#000" stroke-width="0.2"/>'
        f'<circle cx="{EYE[0]:.2f}" cy="{EYE[1]:.2f}" r="3.5" fill="none" stroke="#000" stroke-width="0.2"/></svg>\n')
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*6}" height="{H*6}" viewBox="0 0 {W} {H}" font-family="Helvetica,Arial,sans-serif">',
         '<rect width="100%" height="100%" fill="#f4f1ea"/>',
         f'<path d="{d}" fill="#1d3b34" stroke="#0d201c" stroke-width="0.4"/>']
    for gx in range(0, W, 10):
        s.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{H}" stroke="#000" stroke-opacity="0.08" stroke-width="0.2"/>')
        if gx % 20 == 0:
            s.append(f'<text x="{gx+0.5}" y="3.2" font-size="2.6" fill="#888">{gx}</text>')
    for gy in range(0, H, 10):
        s.append(f'<line x1="0" y1="{gy}" x2="{W}" y2="{gy}" stroke="#000" stroke-opacity="0.08" stroke-width="0.2"/>')
    band = [at(SLIDER, slider_len * i / 80, 4.5)[:2] for i in range(81)] + \
           [at(SLIDER, slider_len * i / 80, 10.5)[:2] for i in range(80, -1, -1)]
    s.append('<path d="M ' + ' L '.join('%.2f %.2f' % p for p in band) + ' Z" fill="#d9b25a" opacity="0.9"/>')
    for x, y, a in leds:
        s.append(f'<rect x="{x-2:.2f}" y="{y+0.1:.2f}" width="4" height="1.6" transform="rotate({a:.1f} {x:.2f} {y:.2f})" fill="#fff59a" stroke="#806a00" stroke-width="0.15"/>')
        nx, ny = math.sin(math.radians(a)), -math.cos(math.radians(a))
        s.append(f'<line x1="{x+nx:.2f}" y1="{y+ny:.2f}" x2="{x+nx*5:.2f}" y2="{y+ny*5:.2f}" stroke="#e8b800" stroke-width="0.5" stroke-linecap="round"/>')
    s.append(f'<circle cx="{EYE[0]:.2f}" cy="{EYE[1]:.2f}" r="3.5" fill="#fff59a" stroke="#806a00" stroke-width="0.3"/>')
    s.append(f'<line x1="{FLAT[0]:.2f}" y1="{FLAT[1]:.2f}" x2="{FLAT[2]:.2f}" y2="{FLAT[3]:.2f}" stroke="#ff5a36" stroke-width="0.8"/>')
    s.append('</svg>')
    open('mosasaurus_concept.svg', 'w').write('\n'.join(s))
    print('bbox %.1f x %.1f mm; LED and slider run %.1f mm, %d LEDs at %.2f mm pitch; flat %.1f mm at y=%.1f'
          % (max(xs) - min(xs), max(ys) - min(ys), spine_len, N_LED, math.dist(leds[0][:2], leds[1][:2]),
             FLAT[2] - FLAT[0], FLAT[1]))
