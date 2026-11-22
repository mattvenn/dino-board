#!/usr/bin/env python3
"""DinoLight: WHAT is on the board. Parts (value, footprint, JLCPCB number) and nets, declared once.
The schematic (tools/schematic.py) draws exactly this; the board is built from the same lists.

Pin numbers come from the datasheets in datasheets/ (see NOTES.md, "Ground truth")."""
import copy
import os
import sys

SKILL = os.path.expanduser('~/.claude/skills/pcb-for-assembly/scripts')
sys.path.insert(0, SKILL)
import schdraw
from schdraw import kid, kids, q, unq

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYMLIB = os.path.join(ROOT, 'lib', 'DinoLight.kicad_sym')

N_LED = 20                      # spine LEDs D1..D20, D1 at the head
# touch channels, in MPR121 electrode order ELE0..ELE11: (net stem, what it is). ELEn is U7 pin 8 + n.
TOUCH = [('SPINE%d' % (i + 1), 'spine %d' % (i + 1)) for i in range(8)]
TOUCH += [('SNOUT', 'snout'), ('FLIP_F', 'front flipper'), ('FLIP_R', 'rear flipper'), ('TAIL', 'tail')]
TESTPOINTS = ['GND', '+3V3', '+BATT', 'VBUS', 'VLED', 'UART_TX', 'UART_RX', 'IO3', 'SDA', 'SCL', 'SPINE_OUT',
              'EN', 'LED_EN', 'LDO_EN', 'CHG_STAT', 'EYE_DIN', 'TOUCH_IRQ']


# ------------------------------------------------------------------ project symbols
def _copy_symbol(src_lib, src, new, numbers=None, names=None, add_pin=None, value=None):
    """Copy a stock symbol into the project library under a new name. numbers: {pin name: new number};
    names: {old pin name: new name}; add_pin: (number, name, x_mm, y_mm, angle) cloned from the first pin."""
    text = open(SYMLIB, encoding='utf-8').read() if os.path.exists(SYMLIB) else ''
    if '(symbol "%s"' % new in text:
        return
    stock = schdraw._lib_text(os.path.join(schdraw.STOCK, src_lib + '.kicad_sym'))
    tree = schdraw._symbol_block(stock, src, src_lib)
    if kid(tree, 'extends'):
        raise SystemExit(f'{src} is a derived symbol; copy its parent instead')

    def rename(node):
        return [rename(c) if isinstance(c, list)
                else (q(unq(c).replace(src, new)) if isinstance(c, schdraw.Q) and unq(c).startswith(src) else c)
                for c in node]
    tree = rename(tree)
    for p in kids(tree, 'property'):
        if unq(p[1]) == 'Value' and value:
            p[2] = q(value)
        if unq(p[1]) in ('Footprint', 'Datasheet', 'ki_fp_filters'):
            p[2] = q('')
    units = kids(tree, 'symbol')
    first = None
    for unit in units:
        for p in kids(unit, 'pin'):
            first = first or (unit, p)
            name = unq(kid(p, 'name')[1])
            if numbers and name in numbers:
                kid(p, 'number')[1] = q(numbers[name])
            if names and name in names:
                kid(p, 'name')[1] = q(names[name])
    if add_pin:
        unit, p = first
        new_pin = copy.deepcopy(p)
        number, name, x, y, angle = add_pin
        new_pin[1] = 'passive'
        kid(new_pin, 'at')[1:] = [schdraw.num(x), schdraw.num(y), str(angle)]
        kid(new_pin, 'name')[1] = q(name)
        kid(new_pin, 'number')[1] = q(number)
        unit.append(new_pin)
    block = schdraw.dump(tree, 1)
    if text:
        text = text.rstrip()
        text = text[:text.rindex(')')].rstrip() + '\n\t' + block + '\n)\n'
    else:
        text = ('(kicad_symbol_lib\n\t(version 20241209)\n\t(generator "schdraw")\n'
                '\t(generator_version "9.0")\n\t' + block + '\n)\n')
    os.makedirs(os.path.dirname(SYMLIB), exist_ok=True)
    with open(SYMLIB, 'w', encoding='utf-8') as f:
        f.write(text)
    schdraw._LIB_CACHE.pop(SYMLIB, None)


def ensure_symbols():
    # side LED: same drawing as the MINI-E, pins renumbered to the SIDE-A datasheet (1 DIN 2 VDD 3 DOUT 4 GND)
    _copy_symbol('LED', 'SK6812MINI', 'SK6812SIDE-A', numbers={'DIN': '1', 'VDD': '2', 'DOUT': '3', 'VSS': '4'},
                 names={'VSS': 'GND'}, value='SK6812SIDE-A')
    # slide switch: SPDT plus its metal frame (datasheet circuit: 2 is the common, 4 the frame)
    _copy_symbol('Switch', 'SW_SPDT', 'MSK12C02', add_pin=('SH', 'SH', 0, -5.08, 90), value='MSK12C02')
    schdraw.make_power_symbol(SYMLIB, 'VLED', like='+3V3')


# ------------------------------------------------------------------ parts and nets
R0603 = 'Resistor_SMD:R_0603_1608Metric'
R0402, C0402, C0805 = 'Resistor_SMD:R_0402_1005Metric', 'Capacitor_SMD:C_0402_1005Metric', 'Capacitor_SMD:C_0805_2012Metric'
SOT23 = 'Package_TO_SOT_SMD:SOT-23'
RES = {'1k': 'C11702', '330R': 'C25104', '470R': 'C25117', '4.7k': 'C25900', '5.1k': 'C25905', '10k': 'C25744', '100k': 'C25741',
       '200k': 'C25764', '1M': 'C26083'}
CAP = {'100nF': (C0402, 'C1525'), '10uF': (C0805, 'C15850')}


def declare(d):
    ensure_symbols()
    d.power_net('VBUS')
    d.power_net('+BATT')
    d.power_net('VLED', 'DinoLight:VLED')

    def r(refs, value):
        for ref in refs.split():
            d.comp(ref, 'Device:R', value, R0402, lcsc=RES[value])

    def c(refs, value):
        for ref in refs.split():
            d.comp(ref, 'Device:C', value, CAP[value][0], lcsc=CAP[value][1])

    # connectors
    d.comp('J1', 'Connector:USB_C_Receptacle_USB2.0_16P', 'USB-C', 'Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12', lcsc='C165948')
    d.comp('J2', 'Connector_Generic_MountingPin:Conn_01x02_MountingPin', 'LiPo JST-PH',
           'Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal', lcsc='C295747')
    d.comp('J3', 'Connector_Generic_MountingPin:Conn_01x04_MountingPin', 'Qwiic',
           'Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal', lcsc='C160404')
    # ICs
    d.comp('U1', 'Power_Protection:USBLC6-2SC6', 'USBLC6-2SC6', 'Package_TO_SOT_SMD:SOT-23-6', lcsc='C7519')
    d.comp('U2', 'Battery_Management:MCP73831-2-OT', 'MCP73831T-2ACI/OT', 'Package_TO_SOT_SMD:SOT-23-5', lcsc='C424093')
    d.comp('U3', 'Regulator_Linear:XC6220B331MR', 'RT9080-33GJ5', 'Package_TO_SOT_SMD:TSOT-23-5', lcsc='C841192')
    d.comp('U4', 'RF_Module:ESP32-S3-MINI-1', 'ESP32-S3-MINI-1-N8', 'RF_Module:ESP32-S2-MINI-1', lcsc='C2913206')
    # touch controller: 12 channels on I2C (0x5A), interrupt can wake the module
    d.comp('U7', 'Sensor_Touch:MPR121QR2', 'MPR121QR2', 'Package_DFN_QFN:UQFN-20_3x3mm_P0.4mm', lcsc='C91322')
    d.comp('R33', 'Device:R', '75k 1%', R0603, lcsc='C23242')      # MPR121 reference current; 0603 is the basic part
    # supervisor: holds the module in reset below 2.93 V so a flat cell can take the charger's trickle
    d.comp('U6', 'Power_Supervisor:TPS3839DBZ', 'TLV803SDBZR', SOT23, lcsc='C132016')
    d.comp('U5', 'Sensor_Motion:LIS2DE12', 'LIS2DH12TR', 'Package_LGA:LGA-12_2x2mm_P0.5mm', lcsc='C110926')
    d.comp('Q1', 'Transistor_FET:AO3401A', 'AO3401A', SOT23, lcsc='C15127')
    d.comp('Q2', 'Transistor_FET:AO3401A', 'AO3401A', SOT23, lcsc='C15127')
    d.comp('Q3', 'Transistor_FET:2N7002', '2N7002', SOT23, lcsc='C8545')
    # stops the battery feeding back onto VBUS through R4 when SW1 is on
    d.comp('D23', 'Device:D', '1N4148W', 'Diode_SMD:D_SOD-123', lcsc='C81598')
    d.comp('F1', 'Device:Polyfuse', '1.1A', 'Fuse:Fuse_1812_4532Metric', lcsc='C21000')
    d.comp('SW1', 'DinoLight:MSK12C02', 'MSK12C02', 'Button_Switch_SMD:SW_SPDT_Shouhan_MSK12C02', lcsc='C431540')
    d.comp('SW2', 'Switch:SW_Push', 'RESET', 'Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A', lcsc='C318884')
    d.comp('SW3', 'Switch:SW_Push', 'BOOT', 'Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A', lcsc='C318884')
    for i in range(1, N_LED + 1):
        d.comp('D%d' % i, 'DinoLight:SK6812SIDE-A', 'SK6812SIDE-A', 'DinoLight:LED_SK6812SIDE-A_4.0x1.6mm', lcsc='C5378721')
    # the eye: a reverse-mount LED on the parts side, shining through a slot to the show face.
    # JLCPCB rates it 'assembly difficulty high, Standard only'. Pins 1 GND, 2 DIN, 3 VDD, 4 DOUT.
    d.comp('D21', 'LED:SK6812MINI-E', 'SK6812MINI-E', 'LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount', lcsc='C5149201')
    # passives
    r('R1 R2', '5.1k')
    r('R3 R17 R18', '4.7k')
    r('R6 R7', '1M')
    r('R4 R5 R9 R19', '200k')
    r('R8 R10 R11 R12 R16 R34', '100k')
    r('R13', '10k')
    r('R32', '1k')
    r('R14 R15', '330R')
    r(' '.join('R%d' % (20 + i) for i in range(len(TOUCH))), '470R')
    c('C1 C2 C3 C4 C5 C8 C9 C34', '10uF')
    c('C6 C7 C10 C32 C33 C36 C37 C38 ' + ' '.join('C%d' % (10 + i) for i in range(1, N_LED + 2)), '100nF')
    # board features with nothing to buy
    for ref in ('SJ1', 'SJ2'):
        d.comp(ref, 'Jumper:SolderJumper_3_Bridged12', 'polarity',
               'Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm', nobom=True)
    for i, (stem, what) in enumerate(TOUCH, 1):
        d.comp('E%d' % i, 'Connector:TestPoint', what, 'DinoLight:TouchAnchor', nobom=True)
    for i, net in enumerate(TESTPOINTS, 1):
        d.comp('TP%d' % i, 'Connector:TestPoint', net, 'TestPoint:TestPoint_Pad_D1.5mm', nobom=True)
    for i in (1, 2, 3):
        d.comp('H%d' % i, 'Mechanical:MountingHole', 'M2.5', 'MountingHole:MountingHole_2.7mm_M2.5', nobom=True)

    n = d.net
    u4_gnd = ['U4.%d' % p for p in (1, 2, 42, 43) + tuple(range(46, 66))]
    n('GND', 'J1.A1', 'J1.A12', 'J1.B1', 'J1.B12', 'J1.SH', 'R1.2', 'R2.2', 'U1.2', 'C1.2', 'U2.2', 'R3.2', 'C2.2', 'R19.2',
      'J2.MP', 'SJ1.3', 'SJ2.1', 'Q1.1', 'C3.2', 'U3.2', 'C4.2', 'SW1.SH', 'R5.2', 'R7.2', 'C7.2', 'R9.2',
      *u4_gnd, 'C5.2', 'C6.2', 'C32.2', 'SW2.2', 'SW3.2', 'U6.1', 'C36.2', 'U7.6', 'U7.4', 'C37.2', 'C38.2', 'R33.2', 'U5.5', 'U5.6', 'U5.7', 'U5.8', 'C33.2', 'C34.2',
      'J3.1', 'J3.MP', 'Q3.2', 'R12.2', 'C8.2', 'C9.2', 'D21.1', 'C31.2', 'TP1.1',
      *['D%d.4' % i for i in range(1, N_LED + 1)], *['C%d.2' % (10 + i) for i in range(1, N_LED + 1)])
    n('VBUS', 'J1.A4', 'J1.A9', 'J1.B4', 'J1.B9', 'U1.5', 'C1.1', 'U2.4', 'D23.2', 'R8.1', 'TP4.1')
    n('EN_USB', 'D23.1', 'R4.1')
    n('+BATT', 'Q1.2', 'U2.3', 'C2.1', 'SW1.1', 'U3.1', 'C3.1', 'R6.1', 'Q2.2', 'R11.1', 'TP3.1')
    n('+3V3', 'U3.5', 'C4.1', 'U4.3', 'C5.1', 'C6.1', 'R16.1', 'U5.2', 'U5.3', 'U5.9', 'U5.10', 'C33.1', 'C34.1',
      'R17.1', 'R18.1', 'J3.2', 'TP2.1', 'U6.3', 'C36.1', 'U7.20', 'C37.1', 'R34.1')
    n('VLED', 'Q2.3', 'C8.1', 'C9.1', 'C10.2', 'D21.3', 'C31.1', 'TP5.1',
      *['D%d.2' % i for i in range(1, N_LED + 1)], *['C%d.1' % (10 + i) for i in range(1, N_LED + 1)])
    # battery input
    n('BAT_P1', 'J2.1', 'F1.1')            # the fuse is in series with the connector pin, ahead of the jumpers
    n('BAT_P1F', 'F1.2', 'SJ1.2')
    n('BAT_P2', 'J2.2', 'SJ2.2')
    n('BAT_RAW', 'SJ1.1', 'SJ2.3', 'Q1.3')
    # USB and charger
    n('CC1', 'J1.A5', 'R1.1')
    n('CC2', 'J1.B5', 'R2.1')
    n('USB_DM', 'J1.A7', 'J1.B7', 'U1.1', 'U1.6', 'U4.23')
    n('USB_DP', 'J1.A6', 'J1.B6', 'U1.3', 'U1.4', 'U4.24')
    n('CHG_PROG', 'U2.5', 'R3.1')
    n('CHG_STAT_5V', 'U2.1', 'R10.1')
    n('CHG_STAT', 'R10.2', 'R19.1', 'U4.21', 'TP15.1')
    # on/off and monitoring
    n('LDO_EN', 'U3.3', 'SW1.2', 'R4.2', 'R5.1', 'TP14.1')
    n('VBAT_SENSE', 'R6.2', 'R7.1', 'C7.1', 'U4.14')
    n('VBUS_DET', 'R8.2', 'R9.1', 'U4.22')
    # module
    n('EN', 'U4.45', 'R16.2', 'C32.1', 'SW2.1', 'R32.2', 'TP12.1')
    n('RST_OD', 'U6.2', 'R32.1')
    n('BOOT', 'U4.4', 'SW3.1')
    n('IO3', 'U4.7', 'TP8.1')
    n('UART_TX', 'U4.39', 'TP6.1')
    n('UART_RX', 'U4.40', 'TP7.1')
    for i, (stem, what) in enumerate(TOUCH):
        n('T_' + stem, 'U7.%d' % (8 + i), 'R%d.1' % (20 + i))
        n('PAD_' + stem, 'R%d.2' % (20 + i), 'E%d.1' % (i + 1))
    n('TOUCH_IRQ', 'U7.1', 'R34.2', 'U4.5', 'TP17.1')        # open collector, active low; GPIO1 can wake the module
    n('MPR_VREG', 'U7.5', 'C38.1')
    n('MPR_REXT', 'U7.7', 'R33.1')
    # accelerometer and I2C
    n('SDA', 'U4.37', 'U5.4', 'U7.3', 'R17.2', 'J3.3', 'TP9.1')
    n('SCL', 'U4.38', 'U5.1', 'U7.2', 'R18.2', 'J3.4', 'TP10.1')
    n('ACC_INT1', 'U4.19', 'U5.12')
    n('ACC_INT2', 'U4.20', 'U5.11')
    # LEDs
    n('LED_EN', 'U4.25', 'Q3.1', 'R12.1', 'TP13.1')
    n('LED_PULL', 'Q3.3', 'R13.2')
    n('LED_GATE', 'R13.1', 'Q2.1', 'R11.2', 'C10.1')   # C10 gate to drain: sets the rail's rise rate
    n('SPINE_DATA', 'U4.27', 'R14.1')
    n('SPINE_DIN', 'R14.2', 'D1.1')
    for i in range(1, N_LED):
        n('SPINE_%d' % i, 'D%d.3' % i, 'D%d.1' % (i + 1))
    n('SPINE_OUT', 'D%d.3' % N_LED, 'TP11.1')
    n('EYE_DATA', 'U4.30', 'R15.1')
    n('EYE_DIN', 'R15.2', 'D21.2', 'TP16.1')
    # deliberately open
    d.nc('J1.A8', 'J1.B8', 'SW1.3', 'D21.4', 'U3.4',
         *['U4.%d' % p for p in (6, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 26, 28, 29, 31, 32, 33, 34, 35, 36, 41, 44)])
