#!/usr/bin/env python3
"""Take out the tracks KiCad's DRC calls dangling, one layer of them at a time, for as long as nothing
comes unconnected: $KPY tools/trim_dangling.py     (keeps the last good board if a removal opens a net)"""
import json
import os
import shutil
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_board as rb

CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
REPORT = os.path.join(rb.WORK, 'trim_drc.json')
GOOD = os.path.join(rb.WORK, 'trim_good.kicad_pcb')


def drc():
    env = dict(os.environ, KICAD_DOCUMENTS_HOME=os.path.join(rb.ROOT, 'kicad-user'))
    subprocess.run([CLI, 'pcb', 'drc', '--format', 'json', '--severity-all', '-o', REPORT, rb.BOARD], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    d = json.load(open(REPORT))
    loose = [(i['pos']['x'], i['pos']['y']) for v in d['violations'] if v['type'] in ('track_dangling', 'via_dangling') for i in v['items']]
    return len(d['unconnected_items']), loose


opens, loose = drc()
start = opens
total = 0
for _ in range(12):
    if not loose:
        break
    shutil.copy(rb.BOARD, GOOD)
    board = pcbnew.LoadBoard(rb.BOARD)
    n = 0
    for t in list(board.GetTracks()):
        x, y = pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y)
        if t.GetNetname() != 'GND' and any(abs(x - a) < 0.002 and abs(y - b) < 0.002 for a, b in loose):
            board.RemoveNative(t)
            n += 1
    pcbnew.SaveBoard(rb.BOARD, board)
    opens, loose = drc()
    if opens > start or not n:
        shutil.copy(GOOD, rb.BOARD)
        print('stopped: taking out the next %d would open a connection' % n)
        opens, loose = drc()
        break
    total += n
print('dangling tracks taken out: %d; still flagged: %d; unconnected: %d' % (total, len(loose), opens))
