#!/usr/bin/env python3
"""Draft mosasaurus outline for DinoLight. Units: mm, y down, show face (front), head left.
Writes mosasaurus_outline.svg (outline only) and mosasaurus_concept.svg (with the layout idea)."""
import math

# Outline as cubic Bezier segments: (p0, c1, c2, p1). Clockwise from the snout tip.
P = [
 ((6,44),(18,38),(34,33),(50,30)),        # top of skull
 ((50,30),(70,24),(100,19),(125,22)),     # back, rising to its highest point
 ((125,22),(150,25),(170,32),(186,37)),   # back, falling to the tail base
 ((186,37),(193,35),(201,29),(207,21)),   # upper tail lobe, leading edge
 ((207,21),(210,18),(212,21),(210,25)),   # upper lobe tip
 ((210,25),(206,33),(204,40),(205,46)),   # notch
 ((205,46),(207,54),(211,62),(215,69)),   # lower lobe, trailing edge
 ((215,69),(217,74),(213,75),(210,72)),   # lower lobe tip
 ((210,72),(200,64),(190,55),(180,51)),   # underside of tail
 ((180,51),(170,51),(160,53),(152,56)),
 ((152,56),(156,62),(160,69),(163,74)),   # rear flipper, trailing edge
 ((163,74),(165,80),(159,82),(155,79)),   # rear flipper tip
 ((155,79),(147,75),(140,69),(138,62)),   # rear flipper, leading edge
 ((138,62),(124,68),(106,70),(92,67)),    # belly
 ((92,67),(96,74),(101,82),(105,87)),     # front flipper, trailing edge
 ((105,87),(108,93),(102,95),(98,92)),    # front flipper tip
 ((98,92),(86,87),(76,76),(72,64)),       # front flipper, leading edge
 ((72,64),(64,63),(57,61),(50,58)),       # throat
 ((50,58),(38,57),(22,54),(8,49)),        # lower jaw
 ((8,49),(3,48),(3,45),(6,44)),           # snout
]
def bez(seg,t):
    (x0,y0),(x1,y1),(x2,y2),(x3,y3)=seg; u=1-t
    return (u**3*x0+3*u*u*t*x1+3*u*t*t*x2+t**3*x3, u**3*y0+3*u*u*t*y1+3*u*t*t*y2+t**3*y3)
def path():
    d='M %g %g '%P[0][0]
    for s in P: d+='C %g %g %g %g %g %g '%(s[1]+s[2]+s[3])
    return d+'Z'
def polyline(segs,n=200):
    pts=[]
    for s in segs:
        for i in range(n): pts.append(bez(s,i/n))
    pts.append(bez(segs[-1],1)); return pts
def along(pts,start,pitch,count):
    """points every `pitch` mm along a polyline, with the local tangent angle"""
    out=[]; d=0; target=start
    for a,b in zip(pts,pts[1:]):
        L=math.dist(a,b)
        while d+L>=target and len(out)<count:
            f=(target-d)/L; x=a[0]+f*(b[0]-a[0]); y=a[1]+f*(b[1]-a[1])
            out.append((x,y,math.degrees(math.atan2(b[1]-a[1],b[0]-a[0])))); target+=pitch
        d+=L
    return out,d
spine=polyline(P[1:3])
N_LED=20
leds,spine_len=along(spine,4.0,(sum(math.dist(a,b) for a,b in zip(spine,spine[1:]))-8.0)/(N_LED-1),N_LED)

if __name__=='__main__':
    W,H=222,102
    open('mosasaurus_outline.svg','w').write(
      f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">'
      f'<path d="{path()}" fill="none" stroke="#000" stroke-width="0.2"/></svg>\n')
    s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*6}" height="{H*6}" viewBox="0 0 {W} {H}" font-family="Helvetica,Arial,sans-serif">',
       '<rect width="100%" height="100%" fill="#f4f1ea"/>',
       f'<path d="{path()}" fill="#1d3b34" stroke="#0d201c" stroke-width="0.4"/>']
    # touch: spine strip of 8 segments just below the LED edge, on the show face
    segs,_=along(spine,6.0,(spine_len-12.0)/8,9)
    for a,b in zip(segs,segs[1:]):
        nx,ny=-math.sin(math.radians(a[2])),math.cos(math.radians(a[2]))
        mx,my=-math.sin(math.radians(b[2])),math.cos(math.radians(b[2]))
        g=0.6
        ax,ay=a[0]+g*math.cos(math.radians(a[2])),a[1]+g*math.sin(math.radians(a[2]))
        bx,by=b[0]-g*math.cos(math.radians(b[2])),b[1]-g*math.sin(math.radians(b[2]))
        s.append('<path d="M %.2f %.2f L %.2f %.2f L %.2f %.2f L %.2f %.2f Z" fill="#d9b25a" opacity="0.9"/>'%(
            ax+nx*3,ay+ny*3,bx+mx*3,by+my*3,bx+mx*10,by+my*10,ax+nx*10,ay+ny*10))
    for (cx,cy,rx,ry,rot,name) in [(24,46.5,9,3.2,8,'snout'),(89,78,5.5,9,-28,'front flipper'),(151,68,4.5,7,-30,'rear flipper'),(206,52,3.5,11,-18,'tail')]:
        s.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" transform="rotate({rot} {cx} {cy})" fill="#d9b25a" opacity="0.9"/>')
    # LEDs (they sit on the back, firing out of the top edge)
    for x,y,a in leds:
        s.append(f'<rect x="{x-2:.2f}" y="{y-0.2:.2f}" width="4" height="1.6" transform="rotate({a:.1f} {x:.2f} {y:.2f})" fill="#fff59a" stroke="#806a00" stroke-width="0.15"/>')
        nx,ny=math.sin(math.radians(a)),-math.cos(math.radians(a))
        s.append(f'<line x1="{x+nx*1:.2f}" y1="{y+ny*1:.2f}" x2="{x+nx*5:.2f}" y2="{y+ny*5:.2f}" stroke="#e8b800" stroke-width="0.5" stroke-linecap="round"/>')
    s.append('<circle cx="40" cy="38.5" r="3" fill="#fff59a" stroke="#806a00" stroke-width="0.3"/><circle cx="40" cy="38.5" r="1.1" fill="#0d201c"/>')
    # parts on the back, shown dashed
    D='fill="none" stroke="#9fd0c4" stroke-width="0.35" stroke-dasharray="1.2 0.8"'
    s.append(f'<rect x="94" y="34" width="36" height="28" rx="1.5" {D}/><text x="112" y="49" font-size="3.4" fill="#9fd0c4" text-anchor="middle">battery (back)</text>')
    s.append(f'<rect x="70" y="36" width="15.4" height="20.5" {D}/><text x="77.7" y="47.5" font-size="2.6" fill="#9fd0c4" text-anchor="middle">ESP32</text>')
    s.append(f'<rect x="110" y="62.5" width="9" height="7.4" {D}/><text x="114.5" y="76" font-size="2.6" fill="#555" text-anchor="middle">USB-C (back)</text>')
    s.append('<text x="6" y="8" font-size="4.2" fill="#333">DinoLight draft outline, show face, 1 square = 10 mm</text>')
    for gx in range(0,W,10): s.append(f'<line x1="{gx}" y1="12" x2="{gx}" y2="{H}" stroke="#000" stroke-opacity="0.07" stroke-width="0.2"/>')
    for gy in range(20,H,10): s.append(f'<line x1="0" y1="{gy}" x2="{W}" y2="{gy}" stroke="#000" stroke-opacity="0.07" stroke-width="0.2"/>')
    s.append('</svg>')
    open('mosasaurus_concept.svg','w').write('\n'.join(s))
    xs=[p[0] for p in polyline(P)]; ys=[p[1] for p in polyline(P)]
    print('bbox %.1f x %.1f mm; spine %.1f mm; %d LEDs at %.2f mm pitch'%(max(xs)-min(xs),max(ys)-min(ys),spine_len,len(leds),math.dist(leds[0][:2],leds[1][:2])))
