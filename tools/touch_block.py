#!/usr/bin/env python3
"""The touch controller block: where U7 and its parts sit, and how the eight slider lines leave it.
Shared by build_board.py (placement) and route_board.py (tracks). All numbers are BOARD mm.

U7 (MPR121, QFN-20) is turned so ELE3..ELE7 (pins 11..15) face the spine. Seen on the parts side:

    top    (left to right)  pins 15 14 13 12 11   = ELE7 6 5 4 3        resistors R27..R23 fanned above
    right  (top to bottom)  pins 10  9  8  7  6   = ELE2 1 0, REXT, VSS R22 R21 R20 further right; R33, C38
    bottom (left to right)  pins  1  2  3  4  5   = IRQ SCL SDA ADDR VREG   (ADDR bridged to SDA)
    left   (top to bottom)  pins 16 17 18 19 20   = ELE8 9 10 11, VDD   R28..R31 and C37 fanned to the left

The eight slider lines then leave upward in the order ELE7..ELE0 from left to right, turn towards the
spine as a nested bundle, and run along the touch band in lanes on the parts side. ELE0 (the electrode
nearest the head) takes the lane nearest the edge and drops out first, so nothing crosses.

The three long pad lines (ELE9 tail, ELE10 rear flipper, ELE11 front flipper) leave R29..R31 to the left,
go up past R28 and take three more lanes just below the slider's: tail nearest the edge, front flipper
deepest, so each can leave its lane towards the belly without crossing another. Each ends in a short
stub below the band; the routers take it from there to the pad's plated hole. They are on the parts
side all the way: a touch line on the show face would answer to a finger anywhere along it.
"""
MIRROR, YOFF = 240.0, 10.0
XC, YC = MIRROR - 46.2, 49.7 + YOFF          # chip centre
U7_ROT = 90

FAN = 1.1                                     # pitch of the fanned parts
TOP_Y = YC - 3.93                             # centre line of the resistors above the chip
TOP = {15: ('R27', -2.2), 14: ('R26', -1.1), 13: ('R25', 0.0), 12: ('R24', 1.1), 11: ('R23', 2.2)}     # pin: (part, x offset)
RIGHT = {10: ('R22', 3.3), 9: ('R21', 4.4), 8: ('R20', 5.5)}
LEFT_X = XC - 3.98
LEFT = {16: ('R28', -2.2), 17: ('R29', -1.1), 18: ('R30', 0.0), 19: ('R31', 1.1), 20: ('C37', 2.2)}  # pin: (part, y offset)
C38_AT = (XC + 1.78, YC + 2.6)
R33_AT = (XC + 4.35, YC + 1.6)

# slider line k (0..7) is ELE k, electrode E(k+1), resistor R(20+k)
LEVEL0, LEVEL_PITCH = 42.6 + YOFF, 0.3       # where each line turns towards the spine (BOARD y), k = 0 highest
CORRIDOR0, CORRIDOR_PITCH = MIRROR - 46.3, -0.3   # where each line runs up past the eye (BOARD x), k = 0 nearest the eye
LANE0, LANE_PITCH = 7.1, 0.3                 # depth of each lane in from the spine edge, k = 0 nearest the edge
LANE_ENTRY = 0.6                              # distance along the spine where the lanes begin
ANCHOR_DEPTH = 6.5                            # the plated hole of each slider electrode
W = 0.13                                      # JLCPCB's minimum on two layers is 0.127

# long pad lines: (resistor, BOARD x of its run up from the resistor, lane depth, show-face x where it leaves
# its lane; None = at the tail end of the spine)
LONG = [('R29', XC - 5.1, 9.5, None), ('R30', XC - 5.4, 9.8, 150.0), ('R31', XC - 5.7, 10.1, 95.0)]
LONG_STUB_DEPTH = 12.7                        # where each stub ends: below the band and its no-via strip
# A grounded guard track just below the deepest touch lane, so the I2C bus and everything else the routers
# lay along the body stays off the touch lines. It starts past the module's corner pad (BOARD x) and is
# broken where a long line leaves its lane.
GUARD_DEPTH, GUARD_W, GUARD_START_X, GUARD_GAP = 10.5, 0.2, MIRROR - 57.0, 0.7


def placements():
    """[(ref, x, y, 'h' or 'v', point pad 1 should be nearest to)]"""
    out = [(ref, XC + dx, TOP_Y, 'v', (XC + dx, YC)) for ref, dx in list(TOP.values()) + list(RIGHT.values())]
    out += [(ref, LEFT_X, YC + dy, 'h', (XC, YC + dy)) for ref, dy in LEFT.values()]
    out.append(('C38', C38_AT[0], C38_AT[1], 'h', (XC + 0.8, YC + 1.45)))
    out.append(('R33', R33_AT[0], R33_AT[1], 'h', (XC, R33_AT[1])))
    return out
