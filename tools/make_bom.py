#!/usr/bin/env python3
"""Write a JLCPCB-format BOM from the schematic's netlist (build/sch/netlist.net): one row per distinct
part, only parts with an LCSC number (board features such as test points and jumpers have none).
    python3 tools/make_bom.py [out.csv]      default build/pcb/bom_jlcpcb.csv"""
import csv, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
text = open(os.path.join(ROOT, 'build', 'sch', 'netlist.net'), encoding='utf-8').read()
rows = {}
for block in re.split(r'\(comp\s', text)[1:]:
    ref = re.search(r'\(ref "([^"]+)"\)', block).group(1)
    value = re.search(r'\(value "([^"]*)"\)', block).group(1)
    fp = re.search(r'\(footprint "([^"]*)"\)', block).group(1).split(':')[-1]
    m = re.search(r'\(name "LCSC"\)\s*"([^"]*)"', block)
    if m and m.group(1):
        rows.setdefault((value, fp, m.group(1)), []).append(ref)
key = lambda r: (re.sub(r'\d+$', '', r), int(re.search(r'\d+$', r).group()))
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'pcb', 'bom_jlcpcb.csv')
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
    for (value, fp, lcsc), refs in sorted(rows.items(), key=lambda kv: key(sorted(kv[1], key=key)[0])):
        w.writerow([value, ','.join(sorted(refs, key=key)), fp, lcsc])
print('%d BOM lines, %d parts -> %s' % (len(rows), sum(len(v) for v in rows.values()), os.path.relpath(out, ROOT)))
