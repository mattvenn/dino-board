#!/usr/bin/env python3
"""Build the DRAFT DinoLight board for a JLCPCB quote: the outline, every part roughly placed,
touch pads on the show face, no tracks. Not built from a schematic and not for ordering.

Run with KiCad's Python from the project folder:
    export KICAD_DOCUMENTS_HOME="$PWD/kicad-user"
    $KPY tools/build_draft.py
Writes draft/dinolight_draft.kicad_pcb and draft/bom_jlcpcb.csv.

Coordinates below are given on the SHOW face (head left, as in outline/make_outline.py).
Parts sit on the other side, which is KiCad's front, so x is mirrored: X = MIRROR - x.
"""
import csv, math, os, sys
import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'outline'))
import make_outline as mo

KFP = '/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/'
MYLIB = os.path.join(ROOT, 'lib', 'DinoLight.pretty')
OUT = os.path.join(ROOT, 'draft', 'dinolight_draft.kicad_pcb')
MIRROR, YOFF = 232.0, 10.0
mm = pcbnew.FromMM


def B(x, y):
    """show-face mm -> board mm"""
    return (MIRROR - x, y + YOFF)


def vec(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


# ---------------------------------------------------------------- parts list
R, C4, C8 = 'Resistor_SMD:R_0402_1005Metric', 'Capacitor_SMD:C_0402_1005Metric', 'Capacitor_SMD:C_0805_2012Metric'
SOT23 = 'Package_TO_SOT_SMD:SOT-23'
LED = MYLIB + ':LED_SK6812SIDE-A_4.0x1.6mm'
PARTS = {}          # ref -> (value, footprint, LCSC)


def part(refs, value, fp, lcsc):
    for r in refs.split():
        PARTS[r] = (value, fp, lcsc)


part('J1', 'USB-C 16P', 'Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12', 'C165948')
part('J2', 'JST-PH 2P', 'Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal', 'C295747')
part('J3', 'Qwiic', 'Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal', 'C160404')
part('U1', 'USBLC6-2SC6', 'Package_TO_SOT_SMD:SOT-23-6', 'C7519')
part('U2', 'MCP73831T-2ACI/OT', 'Package_TO_SOT_SMD:SOT-23-5', 'C424093')
part('U3', 'RT9080-33GJ5', 'Package_TO_SOT_SMD:TSOT-23-5', 'C841192')
part('U4', 'ESP32-S3-MINI-1-N8', 'RF_Module:ESP32-S2-MINI-1', 'C2913206')
part('U5', 'LIS2DH12TR', 'Package_LGA:LGA-12_2x2mm_P0.5mm', 'C110926')
part('Q1 Q2', 'AO3401A', SOT23, 'C15127')
part('Q3', '2N7002', SOT23, 'C8545')
part('F1', 'PTC 1.1A', 'Fuse:Fuse_1812_4532Metric', 'C21000')
part('SW1', 'MSK12C02', 'Button_Switch_SMD:SW_SPDT_Shouhan_MSK12C02', 'C431540')
part('SW2 SW3', 'TS-1187A-B-A-B', 'Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A', 'C318884')
part(' '.join('D%d' % i for i in range(1, 21)), 'SK6812SIDE-A', LED, 'C5378721')
part('D21', 'SK6812MINI-E', 'LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount', 'C5149201')
part('R1 R2', '5.1k', R, 'C25905')
part('R3 R17 R18', '4.7k', R, 'C25900')
part('R4 R5 R8 R9 R11 R12', '100k', R, 'C25741')
part('R6 R7', '1M', R, 'C26083')
part('R10 R13 R16', '10k', R, 'C25744')
part('R14 R15', '330R', R, 'C25104')
part('C1 C2 C5 C8 C9 C34', '10uF', C8, 'C15850')
part('C3 C4 C32', '1uF', C4, 'C52923')
part('C6 C7 C10 C33 ' + ' '.join('C%d' % i for i in range(11, 32)), '100nF', C4, 'C1525')

# ---------------------------------------------------------------- placement (show-face mm, rotation in board degrees)
PLACE = {
    # module in the neck, antenna end at the throat edge
    'U4': (61, 48.0, 180),
    # eye
    'D21': (40, 38.5, 0), 'C31': (45.5, 42.5, 0),
    # LED rail switch and module support, between the module and the battery
    'Q2': (74, 38, 0), 'Q3': (74, 43, 0), 'C8': (74, 48, 0),
    'R11': (78, 37, 0), 'R12': (78, 39.5, 0), 'R13': (78, 42, 0), 'C10': (78, 44.5, 0), 'R14': (78, 47, 0), 'R15': (78, 49.5, 0),
    'C5': (83.5, 37, 0), 'C6': (83.5, 40, 0), 'R16': (83.5, 42.5, 0), 'C32': (83.5, 45, 0),
    'SW2': (79, 55.5, 0), 'SW3': (87.5, 55.5, 0),
    # USB at the belly
    'R1': (108.5, 63.2, 0), 'R2': (121.5, 63.2, 0), 'U1': (126, 64.5, 0),
    # power and sensing, tail side of the battery
    'J2': (137, 46, 90), 'F1': (146, 37.5, 0), 'Q1': (146, 43, 0), 'U2': (146, 48.5, 0), 'C2': (146, 53.5, 0),
    'R3': (150.5, 47, 0), 'C1': (151, 53.5, 0), 'U3': (152.5, 40.5, 0),
    'C3': (156.5, 38.5, 0), 'C4': (156.5, 41, 0), 'R4': (156.5, 43.5, 0), 'R5': (156.5, 46, 0), 'R10': (156.5, 48.5, 0),
    'R6': (160, 40, 0), 'R7': (160, 42.5, 0), 'C7': (160, 45, 0), 'R8': (160, 47.5, 0), 'R9': (160, 50, 0),
    'R17': (163.5, 40.5, 0), 'R18': (163.5, 43, 0), 'U5': (167.5, 42.5, 0), 'C33': (167.5, 46, 0), 'C34': (171.5, 46, 0),
    'J3': (176, 42.5, 90), 'C9': (181, 40, 0),
}
HOLES = [(47, 51), (143, 62.5), (183, 46)]          # 2.7 mm, M2.5
BATTERY = (94, 34, 130, 60)                          # keep this area free of parts


def edge_at(seg_index, x):
    """point and outward normal where outline segment seg_index crosses show-face x"""
    pts = mo.polyline([mo.P[seg_index]], 400)
    i = min(range(len(pts) - 1), key=lambda k: abs(pts[k][0] - x))
    (x0, y0), (x1, y1) = pts[i], pts[i + 1]
    L = math.hypot(x1 - x0, y1 - y0)
    tx, ty = (x1 - x0) / L, (y1 - y0) / L
    return pts[i], (ty, -tx)                         # outline runs clockwise on the show face


def angle_for(nx, ny):
    """board rotation that turns a footprint's +Y to point along (nx, ny) in board coordinates"""
    return math.degrees(math.atan2(nx, ny))


def main():
    board = pcbnew.NewBoard(OUT)
    libcache = {}

    def add(ref, x, y, rot):
        value, fpid, lcsc = PARTS[ref]
        lib, name = fpid.rsplit(':', 1)
        path = lib if lib.startswith('/') else KFP + lib + '.pretty'
        fp = pcbnew.FootprintLoad(path, name)
        if fp is None:
            raise SystemExit('footprint not found: ' + fpid)
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.Reference().SetVisible(False)
        fp.SetPosition(vec(x, y))
        fp.SetOrientationDegrees(rot)
        board.Add(fp)
        return fp

    # outline
    pts = [B(*p) for p in mo.polyline(mo.P, 40)[:-1]]
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_POLY)
    v = pcbnew.VECTOR_VECTOR2I()
    for p in pts:
        v.append(vec(*p))
    s.SetPolyPoints(v)
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetFilled(False)
    s.SetWidth(mm(0.1))
    board.Add(s)

    def copper(points, layer=pcbnew.B_Cu):
        g = pcbnew.PCB_SHAPE(board)
        g.SetShape(pcbnew.SHAPE_T_POLY)
        vv = pcbnew.VECTOR_VECTOR2I()
        for p in points:
            vv.append(vec(*B(*p)))
        g.SetPolyPoints(vv)
        g.SetLayer(layer)
        g.SetFilled(True)
        g.SetWidth(0)
        board.Add(g)

    # touch pads on the show face (KiCad back copper), under solder mask
    segs, _ = mo.along(mo.spine, 6.0, (mo.spine_len - 12.0) / 8, 9)
    for a, b in zip(segs, segs[1:]):
        ca, sa, cb, sb = (math.cos(math.radians(a[2])), math.sin(math.radians(a[2])),
                          math.cos(math.radians(b[2])), math.sin(math.radians(b[2])))
        ax, ay, bx, by = a[0] + 0.6 * ca, a[1] + 0.6 * sa, b[0] - 0.6 * cb, b[1] - 0.6 * sb
        copper([(ax - sa * 4, ay + ca * 4), (bx - sb * 4, by + cb * 4), (bx - sb * 11, by + cb * 11), (ax - sa * 11, ay + ca * 11)])
    for cx, cy, rx, ry, rot in [(24, 46.5, 9, 3.2, 8), (89, 78, 5.5, 9, -28), (151, 68, 4.5, 7, -30), (206, 52, 3.5, 11, -18)]:
        c, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        copper([(cx + rx * math.cos(t) * c - ry * math.sin(t) * sn, cy + rx * math.cos(t) * sn + ry * math.sin(t) * c)
                for t in [2 * math.pi * k / 48 for k in range(48)]])

    # spine LEDs, D1 at the head, each with its capacitor just inboard
    for i, (x, y, a) in enumerate(mo.leds, 1):
        nxs, nys = math.sin(math.radians(a)), -math.cos(math.radians(a))      # outward normal, show face
        nx, ny = -nxs, nys                                                    # mirrored for the board
        ex, ey = B(x, y)
        rot = angle_for(nx, ny)
        add('D%d' % i, ex - nx * 1.46, ey - ny * 1.46, rot)                   # emitting face 0.1 mm inside the edge
        add('C%d' % (10 + i), ex - nx * 3.7, ey - ny * 3.7, rot)

    # edge parts at the belly
    (ux, uy), _n = edge_at(13, 115)
    add('J1', *B(ux, uy - 2.9), 0)
    (sx, sy), _n = edge_at(13, 101)
    add('SW1', *B(sx, sy - 1.45), 0)

    for ref, (x, y, rot) in PLACE.items():
        add(ref, *B(x, y), rot)

    for i, (x, y) in enumerate(HOLES, 1):
        fp = pcbnew.FootprintLoad(KFP + 'MountingHole.pretty', 'MountingHole_2.7mm_M2.5')
        fp.SetReference('H%d' % i)
        fp.Reference().SetVisible(False)
        fp.SetPosition(vec(*B(x, y)))
        board.Add(fp)

    # battery area and a label, for the reader
    x0, y0, x1, y1 = BATTERY
    r = pcbnew.PCB_SHAPE(board)
    r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetStart(vec(*B(x1, y0)))
    r.SetEnd(vec(*B(x0, y1)))
    r.SetLayer(pcbnew.F_SilkS)
    r.SetWidth(mm(0.15))
    board.Add(r)
    for text, (x, y), layer, mirrored in [('BATTERY', (112, 47), pcbnew.F_SilkS, False),
                                          ('DinoLight DRAFT 2026-11-22', (112, 56), pcbnew.B_SilkS, True)]:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetPosition(vec(*B(x, y)))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(mm(1.5), mm(1.5)))
        t.SetTextThickness(mm(0.2))
        t.SetMirrored(mirrored)
        board.Add(t)

    missing = [r for r in PARTS if board.FindFootprintByReference(r) is None]
    if missing:
        raise SystemExit('not placed: ' + ' '.join(missing))
    pcbnew.SaveBoard(OUT, board)

    # BOM in JLCPCB's format
    rows = {}
    for ref, (value, fpid, lcsc) in PARTS.items():
        rows.setdefault((value, fpid.rsplit(':', 1)[1], lcsc), []).append(ref)
    key = lambda r: (''.join(c for c in r if c.isalpha()), int(''.join(c for c in r if c.isdigit())))
    with open(os.path.join(ROOT, 'draft', 'bom_jlcpcb.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
        for (value, fpname, lcsc), refs in sorted(rows.items(), key=lambda kv: key(sorted(kv[1], key=key)[0])):
            w.writerow([value, ','.join(sorted(refs, key=key)), fpname, lcsc])
    print('wrote', OUT, '|', len(PARTS), 'parts,', len(rows), 'BOM lines')


if __name__ == '__main__':
    main()
