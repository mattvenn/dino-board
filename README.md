# DinoLight

A mosasaurus-shaped light-up circuit board: 20 side-firing addressable LEDs along the spine, a glowing
eye, capacitive touch pads on the bare front face, an accelerometer, a rechargeable LiPo and USB-C.
The brain is an ESP32-S3 module intended to run CircuitPython. Designed in KiCad 10 for assembly by JLCPCB.

**Status:** work in progress. Read [NOTES.md](NOTES.md) first: it has the current state, every design
decision and its reason, the parts list with stock checks, the review findings, and the pin map.

## What is where

| Path | What it is |
|---|---|
| `NOTES.md` | The running record. Start here |
| `output/schematic.pdf` | The schematic to read (also `schematic_p1..3.png`) |
| `dinolight.kicad_sch`, `mcu.kicad_sch`, `leds.kicad_sch` | The schematic, generated: do not edit by hand without reading the note below |
| `dinolight.kicad_pcb` | The board, generated from the schematic's netlist |
| `tools/design_spec.py` | Every part and net, declared once. The source of truth |
| `tools/schematic.py` | Draws the schematic from the spec |
| `tools/build_board.py` | Builds the board: outline, placement, nets |
| `outline/` | The outline generator and its SVG / PNG |
| `lib/` | Project symbols and footprints |
| `datasheets/` | Maker datasheets, named by JLCPCB part number |
| `draft/` | An early quote-only board and its JLCPCB upload files. Not for ordering |

## Regenerating

The schematic and board are written by scripts, so a change is made in `tools/` and the files are
regenerated. Anything edited by hand in KiCad is overwritten the next time a script runs.

```bash
export KICAD_DOCUMENTS_HOME="$PWD/kicad-user"
python3 tools/schematic.py export        # schematic files, PDF and PNGs, and build/sch/netlist.net
$KPY tools/build_board.py               # the board, from that netlist (KPY = KiCad's own Python)
```

`tools/schematic.py` needs `schdraw.py`, a small drawing library that is not in this repository yet;
`tools/design_spec.py` looks for it in `~/.claude/skills/pcb-for-assembly/scripts`. The board scripts
need KiCad's own Python (for `pcbnew`).
