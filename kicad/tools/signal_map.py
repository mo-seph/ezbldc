"""Draw the board's copper coloured by signal kind (net class).

    KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $KPY tools/signal_map.py      ->  output/signal_map.svg

Tracks, vias and pads take their net class colour from build_board.py's
NETCLASSES table (the same colours KiCad shows); plane outlines are drawn
dashed. Top-layer copper is solid, bottom-layer copper is drawn lighter,
tracks on the inner layers are drawn as dashed lines.
"""
import fnmatch
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_board import NETCLASSES, OX, OY, W, H, PCB, PRJ   # noqa: E402

S = 20.0                    # pixels per mm
PAD = 12.0                  # margin, mm
LEGEND_W = 34.0             # mm
NO_CLASS = 'rgb(150, 150, 150)'


def colour(netname):
    netname = netname.lstrip('/')       # per-channel nets are '/VM1' etc.
    for name, col, _w, _c, pats in NETCLASSES:
        if any(fnmatch.fnmatchcase(netname, p) for p in pats):
            return col
    return NO_CLASS


def xy(p):
    """KiCad position -> SVG pixels (board frame, y up, drawn y down)."""
    x = pcbnew.ToMM(p.x) - OX
    y = OY - pcbnew.ToMM(p.y)
    return (PAD + x) * S, (PAD + H - y) * S


def main():
    b = pcbnew.LoadBoard(PCB)
    out = []
    wpx, hpx = (W + 2 * PAD + LEGEND_W) * S, (H + 2 * PAD) * S
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{wpx:.0f}" '
               f'height="{hpx:.0f}" viewBox="0 0 {wpx:.0f} {hpx:.0f}" '
               f'font-family="Helvetica, Arial, sans-serif">')
    out.append(f'<rect width="{wpx:.0f}" height="{hpx:.0f}" fill="#fcfcfb"/>')
    r = 4.4 * S
    out.append(f'<rect x="{PAD * S}" y="{PAD * S}" width="{W * S}" '
               f'height="{H * S}" rx="{r}" fill="#f1efe8" stroke="#555" '
               f'stroke-width="2"/>')

    # plane outlines
    layer_name = {pcbnew.F_Cu: 'top', pcbnew.In1_Cu: 'inner 1',
                  pcbnew.In2_Cu: 'inner 2', pcbnew.B_Cu: 'bottom'}
    for z in b.Zones():
        ol = z.Outline().Outline(0)
        pts = ' '.join('%.1f,%.1f' % xy(ol.CPoint(i))
                       for i in range(ol.PointCount()))
        c = colour(z.GetNetname())
        full = ol.PointCount() == 4 and z.GetAssignedPriority() == 0
        if not full:
            out.append(f'<polygon points="{pts}" fill="{c}" fill-opacity="0.10" '
                       f'stroke="{c}" stroke-width="2" stroke-dasharray="8 6"/>')

    def seg(t, opacity, dash=''):
        x1, y1 = xy(t.GetStart())
        x2, y2 = xy(t.GetEnd())
        w = max(pcbnew.ToMM(t.GetWidth()) * S, 2.0)
        cap = 'butt' if dash else 'round'
        dash = f' stroke-dasharray="{dash}"' if dash else ''
        out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                   f'stroke="{colour(t.GetNetname())}" stroke-width="{w:.1f}" '
                   f'stroke-linecap="{cap}" stroke-opacity="{opacity}"{dash}/>')

    tracks = [t for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK']
    vias = [t for t in b.GetTracks() if t.GetClass() == 'PCB_VIA']
    for t in tracks:
        if t.GetLayer() == pcbnew.B_Cu:
            seg(t, 0.45)
    for t in tracks:                    # tracks on the inner plane layers
        if t.GetLayer() in (pcbnew.In1_Cu, pcbnew.In2_Cu):
            seg(t, 0.9, '10 5')
    for fp in b.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            x, y = xy(pcbnew.VECTOR2I(bb.GetLeft(), bb.GetTop()))
            w, h = pcbnew.ToMM(bb.GetWidth()) * S, pcbnew.ToMM(bb.GetHeight()) * S
            name = p.GetNetname()
            c = colour(name) if name else '#c9c6bb'
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                       f'height="{h:.1f}" rx="2" fill="{c}" fill-opacity="0.85"/>')
    for t in tracks:
        if t.GetLayer() == pcbnew.F_Cu:
            seg(t, 1.0)
    for v in vias:
        x, y = xy(v.GetPosition())
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{0.3 * S:.1f}" '
                   f'fill="#fcfcfb" stroke="{colour(v.GetNetname())}" '
                   f'stroke-width="3"/>')

    # component designators
    for fp in b.GetFootprints():
        x, y = xy(fp.GetPosition())
        ref = fp.GetReference()
        if ref[0] in 'UJ' or ref in ('D1', 'D2', 'D3', 'C3'):
            out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="18" '
                       f'fill="#222" text-anchor="middle">{ref}</text>')

    # legend
    lx, ly = (PAD + W + 6) * S, (PAD + 2) * S
    out.append(f'<text x="{lx}" y="{ly}" font-size="26" fill="#222">'
               f'Signal kinds</text>')
    rows = [(n, c, ', '.join(p.lstrip('/') for p in pats))
            for n, c, _w, _c, pats in NETCLASSES]
    for i, (name, c, pats) in enumerate(rows):
        y = ly + 40 + i * 62
        out.append(f'<rect x="{lx}" y="{y - 16}" width="34" height="20" fill="{c}"/>')
        out.append(f'<text x="{lx + 46}" y="{y}" font-size="22" fill="#222">{name}</text>')
        out.append(f'<text x="{lx + 46}" y="{y + 22}" font-size="14" fill="#555">'
                   f'{pats[:48]}</text>')
    y = ly + 40 + len(rows) * 62 + 10
    for j, line in enumerate(['solid line: top layer', 'faint line: bottom layer',
                              'dashed line: track on inner 2',
                              'ring: via', 'dashed outline: plane or pour',
                              'inner 1: ground plane (whole board)',
                              'inner 2: +3V3 plane, +12V where outlined']):
        out.append(f'<text x="{lx}" y="{y + j * 24}" font-size="16" fill="#444">'
                   f'{line}</text>')
    out.append('</svg>')
    path = os.path.join(PRJ, 'output', 'signal_map.svg')
    open(path, 'w').write('\n'.join(out))
    print('wrote', path, len(tracks), 'tracks', len(vias), 'vias')


if __name__ == '__main__':
    main()
