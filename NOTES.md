# DinoLight v0.1 (started 2026-11-22), about 212 x 74 mm

Mosasaurus-shaped light-up PCB, a toy for a young child.
20 side-emitting addressable LEDs along the spine, a one-LED eye shining through the board, ESP32-S3 module running CircuitPython,
accelerometer, 12 capacitive touch zones on the bare front face read by an MPR121 touch controller,
LiPo, USB-C.
JLCPCB Standard assembly, parts on one side. 2 layers.

Decisions marked "owner" are the owner's; those marked "mine" were made by the AI assistant doing the
design work and are open to change.

## State

- 2026-11-22: architecture agreed by the owner. Parts chosen and checked at JLCPCB. Draft outline drawn,
  NOT approved (the owner will change it later).
- 2026-11-22: quote-only DRAFT board uploaded by the owner to JLCPCB (`draft/`). Result: EUR 143 before tax
  and shipping for 5 assembled; Standard assembly only (expected); every BOM line matched; the
  accelerometer was accepted; the reverse-mount eye LED came back with quantity 0 ("hard to place").
  The preview shows USB, switch, battery connector and module facing as intended. The draft predates
  the schematic and must not be ordered.
- 2026-11-22: schematic drawn from `tools/design_spec.py` by `tools/schematic.py`: 3 pages, 146 parts,
  85 nets. KiCad's netlist matches the declared nets with 0 differences. ERC: 1 warning, accepted
  (U5 SA0 tied to 3V3; KiCad calls the pin bidirectional). Pages rendered and looked at.
- Review 1 (netlist against datasheets) done 2026-11-22: no blocker, four should-fix, all acted on.
  Re-review of those changes done 2026-11-22: it found one regression and one should-fix, both fixed as
  the reviewer specified (D23, R32, C32). Those last three edits were checked by my own arithmetic and
  the netlist comparison, not by a third independent pass. See Reviews.
- 2026-11-22: DRAFT of the real board built from the schematic's netlist by `tools/build_board.py`
  (`dinolight.kicad_pcb`): draft outline, 146 footprints placed and linked to their symbols, every pad
  on its net, touch electrodes on the back copper on their nets, eye hole. NO TRACKS. Placement is a
  first pass on an outline the owner will replace; it has not had mechanical sign-off. See "Placement draft".
- 2026-11-22: FIRST ROUTING PASS, NOT FINISHED. See "Routing draft". The LED strip is routed by script
  and is clean; the autorouter did most of the rest but left 26 signal connections open, and ground is
  only partly joined up (79 ground items still unconnected after the pours). Not for ordering.
  Upload set for a second quote: `fab/draft2/`.
- Git repository set up 2026-11-22 (branch `main`, local only, no remote).
- Tools: kicad-cli 10.0.8 runs with `KICAD_DOCUMENTS_HOME=<project>/kicad-user` (checked 2026-11-22).
- Not done: the owner has not read the schematic; routing; mechanical sign-off; JLCPCB's edge rails and tab
  positions; silkscreen; mounting-hole and antenna keepouts.

## Deadline

- The finished toy is needed in the second half of December 2026, with a slow outbound shipping leg
  after assembly and testing.
- Target order date Fri 27 Nov; latest sensible Mon 30 Nov. Standard assembly is 4 days or more after
  2 to 3 days of fabrication (JLCPCB lead-time article).
- No second spin. Module not bare chip, test points, hard switch as well as soft sleep.

## Decisions

| Decision | Why | Whose |
|---|---|---|
| Mosasaurus, head left on the show face, about 212 x 74 mm | The recipient's favourite; no thin legs, so robust | owner |
| Bare PCB front is the show face: artwork and touch pads, no cover | "Clearly a made thing" | owner |
| CircuitPython | Easy to change later: edit `code.py` on the USB drive | owner |
| Battery bought locally at the destination, not shipped with the toy | Lithium cells are restricted in the post | owner |
| ESP32-S3-MINI-1-N8 module | Native USB (no bridge chip), deep sleep, Bluetooth, in stock. Cheaper modules checked 2026-11-22: ESP32-S2-MINI-2 ($2.89) loses Bluetooth and the two LED data pins; ESP32-C3-MINI-1 ($3.05) is no better. Saving about $9 on five boards: not worth it | mine, open |
| Dedicated touch controller U7 (MPR121, 12 channels, I2C 0x5A), not the module's own touch pins | The owner has not had good results with the ESP32's built-in touch. The MPR121 has a CircuitPython library, an interrupt that can wake the module, and gives per-electrode readings, so the eight spine pads can be read as a slider. Others checked at JLCPCB on 2026-11-22: AT42QT2120 (in-chip slider, but only across three channels, SOIC-20, no library), CAP1188 / CAP1298 (8 channels, low stock), Azoteq IQS7222 (none in stock) | owner |
| The touch slider runs the whole length of the LED run | So a light can follow the finger: touch with no LED above it, or LEDs with no touch below, would spoil that | owner |
| Slider electrodes interleave with long teeth: 8 segments, each with one central tooth reaching to the next segment's centre between two half-teeth of its neighbour | Atmel AT11805 (in `datasheets/`) calls this spatial interpolation: touch area passes linearly from one electrode to the next, so position can be interpolated. Its figures followed here: tooth sections 3 to 4 mm tall (3 mm used), tips no thinner than 0.25 mm (0.3 used). The note's own long-slider circuits are mutual-capacitance designs for Atmel's PTC, and its resistor-interpolated version does not apply to a self-capacitance chip like the MPR121; the electrode shape does. Segment pitch is 20.7 mm, wider than the 8 mm keys the note's standard slider uses, which is what the long teeth compensate for | mine, open |
| 470R in series with each touch electrode | Static and noise protection; electrodes are under solder mask only | mine, open |
| Eye = one reverse-mount SK6812MINI-E (D21) on the parts side, shining through its slot to the show face | The owner wants a real part rather than edge-lighting a hole. JLCPCB's page for C5149201 says "Standard Only, Assembly Difficulty High": a rating, not a refusal, and this board is on Standard already. In the owner's first quote it came back with quantity 0, so it must be selected by hand in the BOM step. Its sister SK6812MINI-EA (C5378731) is rated for both services with no difficulty flag, but JLCPCB's symbol for it numbers the pins differently from its own datasheet, so it is the fallback, not the choice | owner |
| LEDs powered from the battery only, never from USB 5 V | LED input high threshold is 0.65 x VDD (datasheet): 2.73 V at 4.2 V, fine for 3.3 V logic; 3.25 V at 5 V, not fine. Avoids a level shifter | mine, open |
| LED rail behind a P-FET switch (Q2, driven by Q3), off by default | 0.6 mA per LED when dark (datasheet), 21 LEDs = 13 mA standing drain | mine, open |
| Slide switch works the regulator's enable pin, not the battery current | The switch is rated 50 mA. Off state is regulator shutdown (0.1 uA typ) with the LED rail off | mine, open |
| USB plugged in also enables the regulator (D23, then R4 / R5, 200k each) | Plugging in wakes it to show charging and makes it programmable whatever the switch says. 200k, not 1M: with 1M a 10 M leak across the switch (its own after-humidity spec) would reach the enable threshold and the toy would not turn off. Costs about 21 uA while switched on. D23 (1N4148W) stops the battery feeding back onto VBUS through R4, which otherwise leaves VBUS_DET at an undefined level and may stop a USB-C charger from starting | mine, after reviews |
| Supervisor U6 (TLV803S, 2.93 V, open drain) on the module's EN through R32 1k; EN pull-up R16 100k, C32 100 nF | Below 2.79 V the charger only trickles 21 mA, less than an awake module draws, so a deeply flat cell would never recover with USB always waking the module. U6 keeps the module off until the rail is up, and supplies the 200 ms start-up delay. R32 keeps U6's output within its 5 mA limit when it discharges C32. Adds about 12 uA | mine, after reviews |
| Fuse F1 in series with the battery connector pin, ahead of the polarity jumpers | A half-done or blobbed jumper change would otherwise short the cell with no fuse in the path | mine, after review 1 |
| C10 from gate to drain of Q2 (was gate to source) | Sets the LED rail's rise to about 1.5 ms and the inrush to about 60 mA, instead of an estimated 2 A spike that could dip the battery and reset the module when the LEDs come on | mine, after review 1 |
| CHG_STAT and VBUS_DET dividers 100k over 200k (2/3) | Half of a sagging 4.4 V USB supply is 2.2 V, under the module's guaranteed high level of 2.475 V | mine, after review 1 |
| C3, C4 at the regulator are 10 uF 0805 (were 1 uF 0402) | A 1 uF 0402 loses much of its value with 3 to 4 V across it; the regulator wants 1 uF effective | mine, after review 1 |
| No USB power path: board runs from the battery, charger tops it up | Fewer parts; needs a battery fitted to run | mine, open |
| RT9080-33 regulator | 2 uA quiescent, enable pin, 600 mA | mine, open |
| MCP73831 charger at 213 mA (4.7k) | Gentle on a 500 mAh cell | mine, open |
| Charger STAT through a 100k / 100k divider | STAT is three-state and drives to VBUS (5 V) when charge completes; the module's pins are 3.3 V | mine |
| Polarity jumpers SJ1, SJ2 on the battery connector | JST-PH LiPos come in both polarities and the cell is bought separately, unseen. Default: J2 pin 1 = + (SparkFun's stated convention; whether that is the footprint's pad 1 is unverified) | mine, open |
| Reverse-polarity P-FET Q1 and a 1.1 A polyfuse F1 at the battery | A wrong-way cell then does nothing rather than damage; a child's toy | mine, open |
| Eye LEDs on their own data pin (IO48), spine on IO47 | IO48 is the status-LED pin of the DevKitM-1 board, whose stock CircuitPython build should run on this module (from memory, unverified) | mine, open |
| Qwiic connector on the I2C bus | Add-on projects later; part used before | mine, open |
| 2 layers | An inner ground plane 0.2 mm behind the touch electrodes would swamp them | mine, open |

## Parts

Stock read from each JLCPCB part page on 2026-11-22. Datasheets are in `datasheets/<C-number>.pdf`.
The owner's upload on 2026-11-22 matched every line by C-number.

| Part | C-number | Stock | Class | Lib | Price | KiCad footprint | Unverified |
|---|---|---|---|---|---|---|---|
| OPSCO SK6812SIDE-A side LED x20 | C5378721 | 137,956 | Economic and Standard | ext | $0.11 | DinoLight:LED_SK6812SIDE-A_4.0x1.6mm (own; matches JLCPCB's to 0.02 mm) | page says MSL 3, linked datasheet is the -012 variant and says MSL 5a |
| ESP32-S3-MINI-1-N8 | C2913206 | 14,793 | Standard Only, X-ray | ext | $4.73 | RF_Module:ESP32-S2-MINI-1 (73 of 73 pads match JLCPCB's, 0.03 mm) | antenna keepout |
| OPSCO SK6812MINI-E reverse-mount LED (eye) | C5149201 | 157,116 | Standard Only, assembly difficulty high | ext | $0.08 | LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount (4 of 4 pads, 0.04 mm) | select it by hand in JLCPCB's BOM step; its pads sit closer to its own slot than the board's edge rule |
| LIS2DH12TR accelerometer | C110926 | 9,994 | Standard Only | ext | $0.89 | LGA-12_2x2mm_P0.5mm | JLCPCB's footprint service has none for it; pin 1 in the preview |
| TYPE-C-31-M-12 USB-C, 16 pin | C165948 | 482,527 | Economic and Standard | ext | $0.19 | USB_C_Receptacle_HRO_TYPE-C-31-M-12 (0.12 mm) | board-edge line |
| MCP73831T-2ACI/OT charger | C424093 | 4,058 | Economic and Standard | ext | $0.79 | SOT-23-5 | |
| RT9080-33GJ5 regulator | C841192 | 25,016 | Economic and Standard | ext | $0.12 | TSOT-23-5 | |
| AO3401A P-FET x2 | C15127 | 1,198,551 | Economic and Standard | basic | $0.08 | SOT-23 (0.28 mm) | pinout G1 S2 D3 from the KiCad symbol, not yet from the datasheet |
| 2N7002 N-FET | C8545 | 6,087,828 | Economic and Standard | basic | $0.02 | SOT-23 | same |
| MSK12C02 slide switch | C431540 | 178,549 | Economic and Standard | ext | $0.05 | SW_SPDT_Shouhan_MSK12C02 (0.20 mm) | |
| JST S2B-PH-SM4-TB battery connector | C295747 | 14,733 | Economic and Standard | ext | $0.20 | JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal | which pad is +, against the cell bought |
| USBLC6-2SC6 ESD | C7519 | 41,992 | Economic and Standard | ext | $0.16 | SOT-23-6 | |
| TS-1187A-B-A-B tact switch x2 | C318884 | 712,048 | Economic and Standard | basic | $0.02 | SW_Push_1P1T_XKB_TS-1187A | |
| JST SM04B-SRSS-TB (Qwiic) | C160404 | 4,603 | Economic and Standard | ext | $0.21 | JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal | used before |
| Polyfuse 1.1 A 1812 | C21000 | 38,340 | Economic and Standard | ext | $0.15 | Fuse_1812 (0.28 mm) | used before |
| TLV803SDBZR supervisor | C132016 | 31,902 | Economic and Standard | ext | $0.19 | SOT-23 (0.08 mm) | |
| MPR121QR2 touch controller | C91322 | 662 | Economic and Standard | ext | $2.69 | UQFN-20_3x3mm_P0.4mm (20 of 20 pads, 0.00 mm) | stock is modest: re-check before ordering |
| 75k 1 % 0603 (MPR121 reference) | C23242 | 630,247 | Economic and Standard | basic | | 0603 | 75k in 0402 is an extended part |
| 1N4148W diode | C81598 | 4,479,389 | Economic and Standard | basic | $0.01 | D_SOD-123 | which pad is the cathode, KiCad against JLCPCB (polarised: check in the preview) |
| 0402 R: 330R, 470R, 1k, 4.7k, 5.1k, 10k, 100k, 200k, 1M | C25104, C25117, C11702, C25900, C25905, C25744, C25741, C25764, C26083 | millions | Economic and Standard | basic | | 0402 | 150k, 470k, 68k in 0402 are extended parts: avoided |
| 100 nF 0402, 10 uF 0805 | C1525, C15850 | millions | Economic and Standard | basic | | 0402 / 0805 | |

Avoid: SK6812SIDE-A-RVS
C2890037 (Standard Only, MSL 5a); LIS3DHTR C15134 (pre-order).

Cost: the owner's quote for the draft on 2026-11-22: EUR 143 before tax and shipping, 5 assembled. Parts were
$51.78 of that (ESP32 $23.67, side LEDs $9.40, accelerometer $4.44, charger $3.95). The rest is fees.
14 extended part types now (the eye LED, supervisor and touch controller are each one; the diode and new resistor values
are basic parts). The breakdown between board, setup
and extended-part fees is not known.

**TLV803SDBZR (C132016).** TI datasheet: DBZ package 1 GND, 2 RESET (open drain, active low), 3 VDD.
Threshold 2.93 V, hysteresis 40 mV typ, 200 ms delay, 9 uA typ. Drawn with KiCad's TPS3839DBZ symbol
(same pin numbers).

**MPR121QR2 (C91322).** NXP datasheet (rev 4): QFN-20, no exposed pad, 1 IRQ (open collector, active low), 2 SCL, 3 SDA,
4 ADDR (to VSS = address 0x5A), 5 VREG (0.1 uF to VSS when VDD is 2.0 to 3.6 V), 6 VSS, 7 REXT (75k 1 %
to VSS), 8 to 19 ELE0 to ELE11, 20 VDD (0.1 uF). VDD 1.71 to 3.6 V. Supply current (datasheet table 5,
read by the reviewer): 3 uA stopped, which is its state after power-on; 8 / 11 / 17 / 29 uA running at
128 / 64 / 32 / 16 ms sample intervals. Electrode capacitance range 10 pF to over 2000 pF.

**AO3401A (C15127), 2N7002 (C8545).** Both 1 gate, 2 source, 3 drain (AOS datasheet read by the reviewer;
Changjing datasheet text read by me). 2N7002 threshold 1 to 2.5 V.

### Ground truth, per part

**SK6812SIDE-A (C5378721).** Datasheet SK6812SIDE-A-012 rev B/2. Body 4.0 long, 1.6 deep, 2.0 tall; it
stands on the board and fires sideways out of the 4.0 x 2.0 face. Pads in a row: 1 DIN, 2 VDD, 3 DOUT,
4 GND. Looking down on the board with the light firing towards you (down the page), the pads read
DIN, VDD, DOUT, GND from left to right, and sit behind the emitting face. JLCPCB's footprint
(LED-SMD_4P-L4.0-W1.6-L) agrees: pads at x = -1.80, -0.45, +0.575, +1.80, body from 0.24 behind the pad
centres to 1.36 in front, window drawn on the front. So with the LEDs firing up out of the spine edge,
data runs right to left in the component-side view. VDD 3.7 to 5.5 V; VIH 0.65 VDD; 12 mA per colour;
0.6 mA static; maker says use 70 % when all three colours are lit. Not verified: operation below 3.7 V
(a LiPo spends much of its life at 3.6 to 3.8 V; expect blue to fade first).

**ESP32-S3-MINI-1-N8 (C2913206).** Espressif datasheet v1.7 (`datasheets/ESP32-S3-MINI-1_en.pdf`).
65 pins. TOUCH1 to 14 are GPIO1 to 14. ADC1 is GPIO1 to 10. RTC (wake-capable) GPIOs are 0 to 21.
USB D- is GPIO19, D+ is GPIO20. Strapping: GPIO0 (pull-up, boot), GPIO3 (floating), GPIO45, GPIO46
(pull-down). EN must not float. Deep sleep 7 to 8 uA; 18 uA with touch wake at 1 % duty.

**LIS2DH12 (C110926).** LGA-12: 1 SCL, 2 CS (tie high for I2C), 3 SA0 (internal pull-up; address 0x19
high, 0x18 low), 4 SDA, 5 Res (to GND), 6 to 8 GND, 9 Vdd, 10 Vdd_IO, 11 INT2, 12 INT1.

**RT9080-33GJ5 (C841192).** TSOT-23-5: 1 VIN, 2 GND, 3 EN, 4 NC, 5 VOUT. VIN 1.2 to 5.5 V. EN high
above 0.9 V, low below 0.4 V, absolute max 6.5 V. Shutdown 0.1 uA typ. Drawn with KiCad's XC6220B331MR
symbol, which has the same pin numbers.

**MCP73831T-2ACI/OT (C424093).** SOT-23-5: 1 STAT, 2 VSS, 3 VBAT, 4 VDD, 5 PROG. 4.7 uF minimum on VDD.
Charge current 1000 V / RPROG. STAT is a three-state output (datasheet section 3).

**MSK12C02 (C431540).** Maker's drawing: pin 2 is the common, joined to 1 or 3 by the slider; 4 is the
frame. Signal pins are on the side away from the knob. Rated 50 mA at 12 V.

## Check before ordering

| Item | What to check |
|---|---|
| LIS2DH12 footprint | JLCPCB's footprint service returned nothing for C110926, so its placement row is KiCad's own position and rotation. The upload accepted it; look at pin 1 in the preview |
| Parts matched by position | J1, J2, J3, SW1, SW2, SW3, U4 in the placement preview (pad names differ between the libraries) |
| Side LED direction | In JLCPCB's placement preview: every spine LED's window faces off the board, and the two eye LEDs face into the hole |
| Parts at the edge of an irregular board | From a web search of JLCPCB's help pages on 2026-11-22 (figures differ between their pages; not read in full): Standard assembly requires edge rails and fiducials; JLCPCB adds 5 mm rails if asked; part bodies should be 2.5 mm or more from the board edge unless rails provide the clearance; irregular outlines are held to the rails by tabs or mouse bites (4 to 5 mm wide); parts overhanging the outline need a slot in the rail. Consequences to settle at placement: where the tabs may attach (not on the spine edge between LEDs, not at the USB socket or switch), whether to draw our own panel to control that, and which order-form option the owner picks for rails. the owner's draft upload raised nothing he mentioned |
| LiPo connector polarity | The cell actually bought, against the + pad of the footprint. Jumpers SJ1, SJ2 swap it. Silkscreen + and - at J2, and "unplug cell; cut both, then bridge both" at the jumpers |
| The cell itself | Must be a protected cell (its own cut-off circuit), JST-PH 2 mm, 500 mAh or more: the charger's 213 mA is too much for cells under about 250 mAh |
| Qwiic pin 1 | Footprint pad 1 against a real Qwiic cable: 1 GND, 2 3V3, 3 SDA, 4 SCL |
| Antenna | Module antenna end at a board edge with the keepout the datasheet asks for |
| FET pinouts | AO3401A and 2N7002 gate, source, drain against their datasheets |

## Reviews

### Review 1, 2026-11-22: netlist against datasheets (independent reader)

Verdict: no blocker. Every IC and connector pin matched its datasheet; every netlist pin has a pad.

Fixed:

| Finding | Fix |
|---|---|
| A deeply flat cell could never recharge: the charger trickles 21 mA below 2.79 V and USB always wakes the module, which draws more | U6 TLV803S holds EN low below 2.93 V; R16 to 100k so that state draws 30 uA |
| Polarity jumpers could short the cell ahead of the fuse (one changed and not the other, or three pads blobbed) | F1 moved to the connector pin, ahead of the jumpers |
| CHG_STAT and VBUS_DET highs not guaranteed at low USB voltage (VBUS / 2 against VIH 2.475 V) | R9, R19 to 200k: 2.93 V at 4.4 V, 3.5 V at 5.25 V |
| LED rail turn-on: estimated 2 A, 100 us inrush with C10 gate to source | C10 moved gate to drain: about 60 mA over 1.5 ms |
| Off state held by 1M against switch leakage | R4, R5 to 200k (reviewer suggested 470k, which is an extended part) |
| C3, C4 1 uF 0402 under bias give less than the regulator's 1 uF | Both to 10 uF 0805 |
| Few test points for a board with no second spin | TP12 EN, TP13 LED_EN, TP14 LDO_EN, TP15 CHG_STAT, TP16 EYE_DIN |
| 2N7002 pinout unverified | Read from the datasheet: 1 G, 2 S, 3 D |

Left as is:

| Finding | Why |
|---|---|
| No hardware under-voltage cut-off; over-discharge protection is firmware plus the cell's own circuit | U6 stops the module below about 2.95 V but the cell can rebound and restart it, so it is not a true cut-off. The cell must be a protected one: now a purchase requirement |
| Reversed cell with USB plugged in is drained at 21 mA through Q1 rather than blocked | No cheap fix. Nothing is damaged. Silkscreen + and - at J2; check with a meter before the first USB plug |
| Full-white current (about 0.8 A plus the module) is at the fuse's hold rating and sags VLED by 0.3 to 0.5 V | Firmware cap: about 0.3 A total for the LEDs |
| Charger dissipates about 0.5 W at the start of fast charge and will fold back | Harmless; give U2 pin 2 copper and keep it away from the cell (layout) |
| VBAT_SENSE feeds about 4 uA into GPIO10 when the regulator is off | Harmless |
| VBUS_DET stays high 1 to 2 s after unplugging | Firmware debounce |

Needs a decision: none. The owner approved the supervisor U6 on 2026-11-22.

Not verified by the reviewer: Qwiic pad-1 side against a cable; polyfuse figures (from the LCSC page);
module current between 2.4 and 2.8 V; the inrush figure (hand estimate); CircuitPython behaviours.

### Review 3, 2026-11-22: the touch controller change (same reviewer, changed items only)

Verdict: no blocker and no should-fix. U7 is wired as the datasheet's 2.0 to 3.6 V circuit; its package has
no exposed pad and matches the footprint; address 0x5A does not clash with the accelerometer (0x19); 470R
in series is negligible to a constant-current measurement; D23, R32 and C32 were applied correctly and
VBUS_DET now reads a clean low with the switch on and no USB.

Fixed:

| Finding | Fix |
|---|---|
| No test point on TOUCH_IRQ | TP17 added |

Left as is:

| Finding | Why |
|---|---|
| IRQ stays low until the touch status is read; sleeping with it low draws 33 uA through R34 and wakes at once | Firmware: read the status before sleeping; wake on GPIO1 low |
| MPR121 scans on its own clock, so it cannot be synchronised with LED frames; supply steps out of regulation can look like touches | Firmware: 10 or more first-filter samples, debounce, ignore touch when the battery is low. Layout: keep LED data and VLED tracks from running under or beside electrode tracks |
| Unplugging USB takes 1.6 to 3.7 s to read low on VBUS_DET (C1 discharging through 300k) | Firmware debounce. Lower divider values would need extended parts |
| Several Qwiic add-ons also use 0x5A | ADDR could go to +3V3 for 0x5B if it ever matters |
| U7 has no reset pin | Firmware sends the soft reset (register 0x80) at start-up |
| The module's former touch pins are open pads | Harmless; firmware can park them with a pull |
| Electrode tracks up to 150 mm are themselves touch-sensitive, and a moving LiPo pouch next to an electrode reads as touch | Layout: thin electrode tracks away from other zones, electrodes and their tracks clear of the battery area |

Not verified by the reviewer: electrode capacitance (hand estimates); the supply-step and LED-coupling
effects (reasoning, not measured); CircuitPython's wake rules.

### Re-review of the changes above, 2026-11-22 (same reviewer, changed items only)

Fixed:

| Finding | Fix |
|---|---|
| Regression from my own change: with SW1 on and no USB, R4 (200k) fed the battery back onto VBUS, leaving VBUS at about 2 V and VBUS_DET between the module's guaranteed low and high. "USB present" could read true with nothing plugged in, and a USB-C charger might refuse to start | D23 1N4148W in series with R4, anode on VBUS. USB alone still gives about 1.9 to 2.4 V on LDO_EN against a 0.9 V threshold |
| U6 discharged C32 (1 uF) through its open-drain output on every trip: estimated 10 to 25 mA peak against a 5 mA limit | C32 to 100 nF, R32 1k in series with U6's output (peak 3.3 mA). EN now rises in about 10 ms after U6's own 200 ms delay |

Left as is:

| Finding | Why |
|---|---|
| Standing current with SW1 on and the module asleep is about 45 to 50 uA (was about 22 to 25 uA before the review fixes) | Buys a firm off state and the supervisor. About a year from a full 500 mAh cell. 470k for R4 / R5 would save 12 uA but is an extended part |
| U6 now decides where the toy cuts out under load: about 3.0 to 3.1 V idle, 3.2 to 3.45 V in a Wi-Fi burst, higher with bright LEDs. Hysteresis is only 40 mV, so a firmware that re-applies the load reboots about 3 times a second | Firmware: read VBAT_SENSE at start-up before lighting anything and sleep below about 3.5 V; keep the LED cap |
| Plugging the cell in (or USB with no cell) turns Q2 on for 40 to 50 ms through C10 | Harmless; a brief random flash is possible because the data pins float then |
| Rail turn-off is slow (about 60 ms) with Q2 in its linear region | About 15 mJ worst case, fine for SOT-23. Firmware: blank the LEDs first |
| VBUS_DET and CHG_STAT reach 3.67 V at a 5.5 V supply, 70 mV over the module's limit | Through 67k: under 1 uA |
| TP13 (LED_EN) is the gate of Q3 behind 100k while the module is asleep | Keep it on the parts side under the cover (all test points are) |

Checked and found correct by the reviewer: TLV803 DBZ pinout and open-drain output from its datasheet;
the moved fuse covers every jumper state; C10 gate-to-drain in every transition; 2N7002 and AO3401A
pinouts from their datasheets; pad names for all parts.

Not verified: how real USB-C chargers react to voltage on VBUS (now moot with D23); the Q2 transition
figures are hand calculations; SK6812 behaviour during the plug-in blip; the last three edits (D23, R32,
C32) have not had a third independent pass.

## Placement draft (2026-11-22)

Where things are, seen from the parts side (head on the right):

| Area | What is there |
|---|---|
| Spine edge | D1 to D20, firing off the edge, D1 at the head; each LED's 100 nF 3.7 mm inboard |
| Head | Eye LED D21 in its slot; LED rail switch (Q2, Q3) below it; RESET and BOOT buttons in the snout |
| Neck | Module U4, antenna end at the throat edge |
| Between module and battery | Supervisor, EN parts, the 12 touch resistors, battery and USB sense dividers |
| Mid body | Battery area 36 x 26 mm, kept free of parts |
| Belly edge | USB-C J1 and slide switch SW1, with the USB protection beside them |
| Tail side of the battery | Battery connector J2 (opening towards the battery), polarity jumpers, fuse, charger, regulator |
| Rear flipper root | Accelerometer |
| Tail | Qwiic J3, opening at the underside edge |

Checks on this draft, 2026-11-22:

- DRC with schematic parity: no missing or extra footprints and no net conflicts (146 field-difference
  warnings, which are noise); no courtyard overlaps, shorts or clearance errors; 333 unconnected items
  (there are no tracks); no edge-clearance errors now that the connectors sit on a belly flat.
- `tools/check_leds.py`: 20 spine LEDs, all facing their edge, chains in order, faces 0.10 mm
  inside the edge.
- `jlc_cpl.py`: every footprint matches JLCPCB's within 0.28 mm, including the supervisor and diode.
  Still to look at in the preview: D23 (polarised), U5 (no JLCPCB footprint data), the connectors.
- USB-C: board edge 2.66 mm in front of the footprint origin, from the maker's drawing (5.79 mm from
  the rear shell slots). The connector overhangs the edge by about 1 mm.
- Slide switch: wholly on the board; its knob overhangs the edge by about 0.85 mm.

Known weaknesses, to settle with the new outline:

- The spine electrodes (back copper, 4.5 to 10.5 mm from the edge) sit behind the LED supply and data
  tracks, and the flipper and snout electrodes sit behind parts (buttons, accelerometer). Each adds
  stray capacitance and noise to that touch channel. The electrode shapes are placeholders.
- A mounting hole could not go in the rear flipper without cutting its electrode; all three holes
  (snout, belly behind the battery connector, tail) are placeholders until the case exists.
- Antenna: the module footprint carries its own keep-out (no tracks, vias or parts on either face) from
  the antenna root to 14 mm beyond its end and 22.7 mm either side. It is clear of parts, the throat
  edge is in front of it, and the ground pours are kept out of it too. The case is plastic. Expect it to
  be usable for Wi-Fi and Bluetooth at room range; this is not measured.
- No room has been reserved for JLCPCB's tabs. The owner asked on 2026-11-22 whether a rectangular
  board with the outline held by tabs would make it eligible for Economic assembly: no. The service is
  decided by the parts (the module, the accelerometer and the eye LED are Standard only), not the
  outline. A frame with our own tabs is still worth drawing for Standard assembly, so the tabs land
  where we choose and not on the LED edge or the USB socket.

## Routing draft (2026-11-22)

How it is made (all regenerated by script, in this order):

1. `tools/build_board.py`: placement, nets, electrodes.
2. `tools/route_board.py strip`: the LED strip by rule. Each LED's 100 nF stands radially under its VDD
   pad. Supply: LED to capacitor to a stub to a 0.6 mm rail on the parts side, 5.6 mm in from the edge.
   Ground: one via at each LED's ground pad and one at each capacitor, into a ground strip on the show
   face that runs between the board edge and the touch slider. Data: LED to LED on the parts side.
   214 tracks, 40 vias, no rule violations.
3. `tools/route_board.py dsn`, then Freerouting 2.1.0 (GUI on, 40 passes), then `route_board.py ses`.
   The autorouter gets a copy of the board with ground left out and the show face closed to it wherever
   there is touch copper, the ground strip or the antenna zone. Signals 0.15 mm, supplies 0.4 mm,
   clearance 0.15 mm, vias 0.5 / 0.3 mm.
4. `tools/route_board.py pour`: ground pours on both faces; no pour behind or within 1.5 mm of touch
   copper, none in the antenna zone.

Where it stands:

- Autorouter: first run (0.2 mm tracks, 0.6 mm vias, parts 0.4 mm apart) left 43 signal connections
  open; second run (finer rules, parts 0.65 mm apart) left 26. It oscillates rather than converges, and
  its log shows internal errors, so more passes will not finish it.
- Open signal connections: mostly the touch lines (pad to resistor to controller), plus single links on
  +3V3 at U5 and U7, SDA, MPR_REXT, BAT_P1, CHG_STAT, CHG_STAT_5V, CHG_PROG, VBAT_SENSE, EYE_DATA,
  EYE_DIN, IO3 and ACC_INT1. Several are a few millimetres long: the fine-pitch chips U5 and U7 are
  boxed in by their neighbours.
- Ground: 79 items unconnected. The pours are in fragments; it needs stitching vias and probably a
  ground via beside each ground pad.
- DRC on this draft: no shorts and no clearance errors. 9 edge-clearance errors (4 are the eye LED's
  own pads beside its slot, by design of the library footprint; the rest are autorouter tracks too near
  the slot or the board edge), 17 starved thermals, 21 dangling vias or track ends from the autorouter.
- Not run: `board_audit.py` (pointless until the connections are complete); no independent layout review.

To finish it: give U5 and U7 clear space and fan their pins out by script (as the LED strip was done),
route the touch lines by script along the body, re-run the autorouter for what is left, then stitch
ground and re-check.

## Outline

- `outline/make_outline.py` writes `mosasaurus_outline.svg` (outline only, mm) and
  `mosasaurus_concept.svg/png` (outline with LEDs, touch zones and the big parts sketched in).
- Current draft: 225.6 x 72.6 mm. Closed mouth (jaw line and teeth are to be artwork or part of the
  printed case, not outline), tail 14 mm longer than the first draft, and a 26 mm flat on the belly for
  the USB socket and slide switch, which the case will hide. LED and slider run 152.6 mm, 20 LEDs at
  7.7 mm pitch.
- An open-mouthed outline traced from a reference illustration (214.6 x 107 mm, tall upswept tail) was
  tried on 2026-11-22; the owner preferred this one. It is in the git history of `make_outline.py`.
- The owner's guidance, 2026-11-22: the PCB only has to carry the shape, since detail can go in the 3D
  print; one flipper front and one rear is enough.

## For the case

- Parts, battery and connectors on the back, under a printed cover; the front stays bare.
- Translucent ridge along the spine as the light guide. The side LEDs stand 2.0 mm off the board.
- Eye: the LED sits in a 3.4 x 3 mm slot with its lens facing the show face; a printed dome or lens
  can go over it.
- `output/dinolight.step` is the board for the case design (most small parts have no 3D model in it).
- Battery space sketched as 36 x 28 mm (a 500 to 600 mAh cell). Keep that area of the board free of
  parts: a pouch cell must not rest on solder joints.
- USB-C and the slide switch must be reachable; BOOT and RESET by a pin hole at least.
- Fixing the board to the case is undecided (the owner, 2026-11-22: press fit has no loose small parts, but
  what goes in can be pulled out). The board has three 2.7 mm (M2.5) holes H1 to H3 at placeholder
  positions. My
  recommendation: keep holes and use screws, because the thing to keep a child out of is the LiPo.
  Alternative with no holes: back shell plus a front rim screwed together from behind.

## For firmware

Pin map (as in the schematic):

| GPIO | Use |
|---|---|
| 0 | BOOT button |
| 1 | TOUCH_IRQ from the MPR121: low when a touch or release is waiting; can wake the module |
| 2, 4 to 9, 11 to 14 | Spare, not brought out |
| 3 | Not used (strapping pin); test point |
| 10 | VBAT_SENSE: battery / 2 (ADC1) |
| 15, 16 | Accelerometer INT1 (wake), INT2 |
| 17 | CHG_STAT: high = charge complete; low = charging, or no USB |
| 18 | VBUS_DET: high = USB present |
| 19, 20 | USB D-, D+ |
| 21 | LED_EN: high = LED rail on; pulled down |
| 41, 42 | I2C SDA, SCL: accelerometer (0x19) and Qwiic |
| 47 | Spine LED data, 20 LEDs, first LED at the head |
| 48 | Eye LED data, 1 LED |
| 43, 44 | UART0 TX, RX on test points |

- Turn the LED rail off before sleeping. Drive both LED data pins low (or release them) before taking
  LED_EN low: a high data pin back-feeds the dead rail through the LED's input, about 8 mA per line.
- Cap total LED current at about 0.3 A: the maker allows 70 % with all colours lit, 21 LEDs at full
  white would be about 0.8 A, and the fuse holds 1.1 A.
- After LED_EN goes high the rail takes about 2 ms to rise; wait 5 ms before sending data. Blank the
  LEDs before taking LED_EN low: the rail takes about 60 ms to fall.
- At start-up read VBAT_SENSE before lighting anything, and go back to sleep below about 3.5 V: the
  supervisor resets the module if the 3.3 V rail dips under 2.93 V, and a load that is re-applied on
  every boot becomes a reboot loop.
- After releasing RESET the module starts about 0.2 s later (U6's delay).
- CHG_STAT reads "charging" with no cell fitted, and VBUS_DET stays high for 1 to 2 s after unplugging.
- Deep-sleep wake: use the accelerometer's INT1 on GPIO15. Touch wake is limited (reviewer, from memory:
  one pad).
- CircuitPython's status LED is IO48, the eye; it stays dark unless the build names GPIO21 as its
  power pin (from memory, unverified).
- Touch: MPR121 at I2C 0x5A. ELE0 to ELE7 are spine 1 to 8 (head to tail), ELE8 snout, ELE9 front
  flipper, ELE10 rear flipper, ELE11 tail. Adafruit's CircuitPython MPR121 library should drive it
  (from memory, unverified). For the slider, take each spine electrode's baseline minus its filtered
  reading and compute the weighted centre.
- LED data and supply tracks run behind the spine electrodes: expect to tune thresholds with the LEDs
  running. Use 10 or more first-filter samples and some debounce.
- MPR121: send the soft reset (0x80) at start-up. Read the touch status before sleeping, or IRQ stays
  low. For touch-to-wake leave it running at a 32 to 64 ms sample interval (11 to 17 uA) and wake on
  GPIO1 low; otherwise stop it (3 uA).
- Ignore touch when the battery is low: readings shift when the 3.3 V rail drops out of regulation.
- Sleep at about 3.5 V so the cell's own protection never has to act.
- With USB plugged in and the charge finished, the charger never sees its termination current while the
  board is awake (the board's own draw exceeds it), so it holds the cell at 4.2 V. Sleep when CHG_STAT
  goes high or after a time limit.

## Not fitted by the assembler

- LiPo cell (bought separately).
- Nothing else: SJ1, SJ2, test points, touch electrodes and holes are board features.

## Files

| File | What it is |
|---|---|
| `NOTES.md` | this |
| `tools/design_spec.py` | the parts and nets, declared once: the source of truth |
| `tools/schematic.py` | draws the schematic from the spec (overwrites the `.kicad_sch` files) |
| `dinolight.kicad_sch`, `mcu.kicad_sch`, `leds.kicad_sch` | the schematic: power; module, touch, accelerometer; LEDs |
| `output/schematic.pdf`, `output/schematic_p1..3.png` | the schematic to read |
| `tools/flat_netlist.py`, `build/sch/netlist_flat.txt` | flattened netlist for review |
| `tools/build_board.py` | builds `dinolight.kicad_pcb` from the netlist: outline, placement, nets. Overwrites the board |
| `dinolight.kicad_pcb`, `dinolight.kicad_pro` | the board (draft placement, no tracks) |
| `output/board_parts_side.png`, `board_show_face.png`, `board_1to1_parts_side.pdf`, `dinolight.step` | renders, a 1:1 print and a STEP of the board |
| `tools/make_bom.py` | JLCPCB-format BOM from the netlist |
| `tools/route_board.py` | routing stages: LED strip by rule, autorouter in and out, ground pours |
| `tools/make_upload.sh` | exports Gerbers, BOM and placement file into `fab/<name>/` |
| `fab/draft2/` | upload set from the first routing pass, for a quote only |
| `lib/DinoLight.kicad_sym`, `lib/DinoLight.pretty/` | own symbols (side LED, slide switch, VLED rail) and footprints (side LED, touch anchor) |
| `datasheets/` | maker datasheets, named by C-number, plus Espressif's English module datasheet |
| `outline/` | outline generator and its SVG / PNG output |
| `tools/build_draft.py`, `draft/` | the quote-only draft board, its renders and upload set (`draft/jlc/`) |
| `tools/check_leds.py` | checks spine LED direction, edge distance and chain order on any board |
| `tools/fpinfo.py` | prints pad and courtyard extents of library footprints |
| `kicad-user/` | KiCad's documents folder for this project (set `KICAD_DOCUMENTS_HOME` to it) |
