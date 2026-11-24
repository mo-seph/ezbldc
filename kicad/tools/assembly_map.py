"""Draw where every part is: the board carries no designators (too dense
for silkscreen), so this is the drawing to solder and debug from.

    KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $KPY tools/assembly_map.py      ->  output/assembly_top.svg

Each part is a box (its courtyard) with its designator; a dot marks pad 1
(the cathode of a diode or LED, the + of an electrolytic). Parts that are
not fitted are drawn dashed. Colour says who fits the part: JLCPCB by
machine, through-hole (JLCPCB by hand, or you), or you only.
"""
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_board import OX, OY, W, H, PCB, PRJ   # noqa: E402

S = 40.0            # pixels per mm
PAD = 4.0           # margin, mm
KIND = {            # fill, stroke
    'smd': ('#dbe9f6', '#2a6aa8'),
    'tht': ('#fbe3c8', '#b5651d'),
    'hand': ('#e4dcf4', '#6a4bb0'),
    'none': ('#eeeeea', '#8a8a82'),
}


def xy(p):
    return ((PAD + pcbnew.ToMM(p.x) - OX) * S,
            (PAD + H - (OY - pcbnew.ToMM(p.y))) * S)


def main():
    b = pcbnew.LoadBoard(PCB)
    out = []
    wpx, hpx = (W + 2 * PAD) * S, (H + 2 * PAD + 7) * S
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{wpx:.0f}" '
               f'height="{hpx:.0f}" viewBox="0 0 {wpx:.0f} {hpx:.0f}" '
               f'font-family="Helvetica, Arial, sans-serif">')
    out.append(f'<rect width="{wpx:.0f}" height="{hpx:.0f}" fill="#ffffff"/>')
    out.append(f'<rect x="{PAD * S}" y="{PAD * S}" width="{W * S}" '
               f'height="{H * S}" rx="{4.4 * S}" fill="#fafaf7" stroke="#333" '
               f'stroke-width="3"/>')
    boxes = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        a = fp.GetAttributes()
        if ref.startswith('FID'):
            continue
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        bb = cy.BBox() if cy.OutlineCount() else None
        if bb is None or bb.GetWidth() == 0:
            bb = fp.GetBoundingBox(False)
        x0, y0 = xy(pcbnew.VECTOR2I(bb.GetLeft(), bb.GetTop()))
        w, h = pcbnew.ToMM(bb.GetWidth()) * S, pcbnew.ToMM(bb.GetHeight()) * S
        if ref.startswith(('TP', 'H')):
            kind = 'none'
        elif ref == 'U1':
            kind = 'hand'
        elif a & pcbnew.FP_THROUGH_HOLE:
            kind = 'tht'
        else:
            kind = 'smd'
        boxes.append((w * h, ref, x0, y0, w, h, kind, bool(a & pcbnew.FP_DNP), fp))
    for _area, ref, x0, y0, w, h, kind, dnp, fp in sorted(boxes, reverse=True):
        fill, stroke = KIND[kind]
        dash = ' stroke-dasharray="10 8"' if dnp else ''
        out.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" '
                   f'height="{h:.1f}" rx="6" fill="{fill}" stroke="{stroke}" '
                   f'stroke-width="2.5"{dash}/>')
        pads = [p for p in fp.Pads() if p.GetNumber() == '1']
        if pads and fp.GetPadCount() > 1 and kind != 'none':
            px, py = xy(pads[0].GetPosition())
            r = (0.32 if min(w, h) > 2.5 * S else 0.2) * S
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r:.1f}" '
                       f'fill="{stroke}"/>')
    for _area, ref, x0, y0, w, h, kind, dnp, fp in boxes:
        # designator: as large as the box allows, turned if the box is tall
        tall = h > w * 1.3
        long_side, short_side = (h, w) if tall else (w, h)
        size = min(short_side * 0.62, long_side / (0.62 * len(ref)), 1.9 * S)
        size = max(size, 0.75 * S)
        cx, cy = x0 + w / 2, y0 + h / 2
        turn = f' transform="rotate(-90 {cx:.1f} {cy:.1f})"' if tall else ''
        out.append(f'<text x="{cx:.1f}" y="{cy + size * 0.35:.1f}" '
                   f'font-size="{size:.1f}" font-weight="600" fill="#111" '
                   f'text-anchor="middle"{turn}>{ref}</text>')
    # legend
    ly = (PAD + H + 4.4) * S        # below the XIAO's overhang
    items = [('smd', 'surface mount: JLCPCB'), ('tht', 'through-hole'),
             ('hand', 'XIAO: hand-soldered'), ('none', 'test pad / hole')]
    lx = PAD * S
    for kind, label in items:
        fill, stroke = KIND[kind]
        out.append(f'<rect x="{lx:.0f}" y="{ly - 30:.0f}" width="56" height="36" '
                   f'rx="6" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>')
        out.append(f'<text x="{lx + 70:.0f}" y="{ly - 3:.0f}" font-size="30" '
                   f'fill="#222">{label}</text>')
        lx += 70 + len(label) * 17 + 60
    out.append(f'<text x="{PAD * S:.0f}" y="{ly + 55:.0f}" font-size="30" fill="#222">'
               f'dot = pad 1 (cathode of a diode or LED, + of an electrolytic); '
               f'dashed = not fitted. Top side; there are no parts underneath.</text>')
    out.append('</svg>')
    path = os.path.join(PRJ, 'output', 'assembly_top.svg')
    open(path, 'w').write('\n'.join(out))
    print('wrote', path, len(boxes), 'parts')


if __name__ == '__main__':
    main()
