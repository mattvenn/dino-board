#!/usr/bin/env python3
"""Summarise a KiCad DRC report (JSON): tools/drc_summary.py build/pcb/drc.json [-v]"""
import collections
import json
import re
import sys

d = json.load(open(sys.argv[1]))
verbose = '-v' in sys.argv
QUIET = ('silk_edge_clearance', 'silk_overlap', 'silk_over_copper', 'lib_footprint_mismatch', 'lib_footprint_issues')
print('violations:', dict(collections.Counter(v['type'] for v in d['violations'])))
if 'schematic_parity' in d:
    print('parity:', dict(collections.Counter(v['type'] for v in d['schematic_parity'])))
u = d['unconnected_items']


def net(x):
    m = re.search(r'\[([^\]]+)\]', x['items'][0]['description'])
    return m.group(1) if m else '?'


nets = collections.Counter(net(x) for x in u)
print('%d unconnected: GND %d, others %d' % (len(u), nets['GND'], len(u) - nets['GND']))
for x in u:
    if net(x) != 'GND' or verbose:
        print('  open', net(x), [(i['description'][:48], round(i['pos']['x'], 2), round(i['pos']['y'], 2)) for i in x['items']])
for v in d['violations']:
    if v['type'] not in QUIET:
        print(' ', v['type'], [(i['description'][:52], round(i['pos']['x'], 2), round(i['pos']['y'], 2)) for i in v['items']])
