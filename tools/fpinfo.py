import pcbnew, sys
FP='/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/'
for spec in sys.argv[1:]:
    lib,name=spec.split(':')
    path=lib if lib.startswith('/') else FP+lib+'.pretty'
    f=pcbnew.FootprintLoad(path,name)
    if f is None: print(spec,'NOT FOUND'); continue
    pads=[(p.GetNumber(),pcbnew.ToMM(p.GetPosition().x),pcbnew.ToMM(p.GetPosition().y),'TH' if p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH else ('NPTH' if p.GetAttribute()==pcbnew.PAD_ATTRIB_NPTH else 'smd')) for p in f.Pads()]
    xs=[p[1] for p in pads]; ys=[p[2] for p in pads]
    print(spec); print('  pads %d  x %.2f..%.2f  y %.2f..%.2f'%(len(pads),min(xs),max(xs),min(ys),max(ys)))
    cy=f.GetCourtyard(pcbnew.F_CrtYd).BBox()
    print('  courtyard x %.2f..%.2f y %.2f..%.2f'%tuple(pcbnew.ToMM(v) for v in (cy.GetLeft(),cy.GetRight(),cy.GetTop(),cy.GetBottom())))
    for g in f.GraphicalItems():
        if g.GetLayerName() in('Edge.Cuts','Dwgs.User','Cmts.User') :
            bb=g.GetBoundingBox(); print('  ',g.GetLayerName(),g.GetClass(),'x %.2f..%.2f y %.2f..%.2f'%tuple(pcbnew.ToMM(v) for v in (bb.GetLeft(),bb.GetRight(),bb.GetTop(),bb.GetBottom())), getattr(g,'GetText',lambda:'')() if g.GetClass()=='PCB_TEXT' else '')
    if len(pads)<=8: print('  ',pads)
