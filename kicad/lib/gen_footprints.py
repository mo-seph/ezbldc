"""Generate the three custom footprints for the BLDC driver board.

    python3 gen_footprints.py      ->  bldc.pretty/*.kicad_mod

XIAO-ESP32-S3-Plus-SMD: pad numbers, positions and sizes are those of
Seeed's own footprint of the same name (Seeed-Studio/OPL_Kicad_Library,
"Seeed Studio XIAO Series Library", read 2026-11-10). Pads 1-14 are the
edge castellations, 15-23 the small pads between them, 24-34 the module's
underside pads (not connected on this board, kept so the module solders
down the way Seeed intends). +X is the USB end.

XKB_DC-005-5A-2.0: same pad and slot geometry as the Eagle package of
that name on the Node board ("Peripheral PCB Layout.brd"), so the jacks
drop onto the same holes. Pad 1 = centre pin (+), 2 = sleeve, 3 = switch.
"""
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bldc.pretty')
os.makedirs(OUT, exist_ok=True)


def text(kind, value, x, y, layer, hide=False, size=1.0):
    h = ' (hide yes)' if hide else ''
    return (f'  (property "{kind}" "{value}" (at {x} {y} 0) (layer "{layer}"){h}\n'
            f'    (effects (font (size {size} {size}) (thickness {size * 0.15:.3f}))))\n')


def line(x1, y1, x2, y2, layer, w=0.12):
    return (f'  (fp_line (start {x1} {y1}) (end {x2} {y2}) '
            f'(stroke (width {w}) (type solid)) (layer "{layer}"))\n')


def rect(x1, y1, x2, y2, layer, w=0.1):
    return (f'  (fp_rect (start {x1} {y1}) (end {x2} {y2}) '
            f'(stroke (width {w}) (type solid)) (fill no) (layer "{layer}"))\n')


def smd(num, shape, x, y, rot, w, h, rr=None):
    # No paste layer: the XIAO is the only user of this, and it is soldered
    # by hand after JLCPCB's assembly, so its lands must stay free of
    # reflowed solder.
    r = f' (roundrect_rratio {rr})' if rr is not None else ''
    return (f'  (pad "{num}" smd {shape} (at {x} {y} {rot}) (size {w} {h}) '
            f'(layers "F.Cu" "F.Mask"){r})\n')


def slot(num, x, y, w, h, dw, dh):
    return (f'  (pad "{num}" thru_hole oval (at {x} {y}) (size {w} {h}) '
            f'(drill oval {dw} {dh}) (layers "*.Cu" "*.Mask"))\n')


# ---------------------------------------------------------------- XIAO Plus
def xiao():
    s = '(footprint "XIAO-ESP32-S3-Plus-SMD"\n  (version 20240108)\n  (generator "gen_footprints")\n  (layer "F.Cu")\n'
    s += '  (descr "Seeed Studio XIAO ESP32-S3 Plus, soldered flat. Pad geometry from Seeed OPL_Kicad_Library. +X is the USB end.")\n'
    s += '  (tags "XIAO ESP32-S3 Plus Seeed module")\n'
    s += text('Reference', 'REF**', -6.0, -10.6, 'F.SilkS')
    s += text('Value', 'XIAO-ESP32-S3-Plus', 0, 0, 'F.Fab')
    s += text('Footprint', '', 0, 0, 'F.Fab', hide=True)
    s += text('Datasheet', '', 0, 0, 'F.Fab', hide=True)
    s += text('Description', '', 0, 0, 'F.Fab', hide=True)
    s += '  (attr smd)\n'
    # module body 21 x 17.8 mm, USB-C overhangs at +X
    s += rect(-10.5, -8.9, 10.5, 8.9, 'F.Fab')
    s += rect(8.0, -4.5, 12.05, 4.5, 'F.Fab')            # USB-C connector
    s += rect(-10.75, -10.4, 12.3, 10.4, 'F.CrtYd', 0.05)
    # silkscreen: end lines and corner ticks (the long edges are all pads)
    s += line(-10.65, -7.0, -10.65, 7.0, 'F.SilkS')
    s += line(10.65, -7.0, 10.65, -4.7, 'F.SilkS')
    s += line(10.65, 4.7, 10.65, 7.0, 'F.SilkS')
    s += line(9.3, -9.9, 10.9, -9.9, 'F.SilkS', 0.2)    # pin-1 mark beside pad 1
    # Edge pads. Seeed's own lands end 0.37 mm outside the module's edge,
    # which suits reflow. This module is soldered by hand, so every edge pad
    # is lengthened outward by TOE: the inner ends stay where Seeed has them.
    TOE = 0.8
    # castellations 1-14
    for i in range(7):
        x = round(7.62 - 2.54 * i, 3)
        s += smd(i + 1, 'roundrect', x, -8.255 - TOE / 2, 90, 2.032 + TOE, 0.95, 0.1)
    for i in range(7):
        x = round(-7.62 + 2.54 * i, 3)
        s += smd(i + 8, 'roundrect', x, 8.255 + TOE / 2, 270, 2.032 + TOE, 0.95, 0.1)
    # small pads 15-20 (between 1..7) and 21-23 (between 8..11)
    for i in range(6):
        x = round(6.35 - 2.54 * i, 3)
        s += smd(i + 15, 'roundrect', x, -8.655 - TOE / 2, 90, 1.232 + TOE, 0.95, 0.1)
    for i in range(3):
        x = round(-6.35 + 2.54 * i, 3)
        s += smd(i + 21, 'roundrect', x, 8.655 + TOE / 2, 270, 1.232 + TOE, 0.95, 0.1)
    # The module's underside pads (Seeed's 24-34) are deliberately left out:
    # nothing here connects to them, an iron cannot reach them, and solder
    # or HASL bumps on them would stop the module sitting flat. The board
    # under the module is plain solder mask (build_board.py keeps tracks and
    # vias out of it).
    s += ')\n'
    open(os.path.join(OUT, 'XIAO-ESP32-S3-Plus-SMD.kicad_mod'), 'w').write(s)


# --------------------------------------------------------------- barrel jack
def jack():
    s = '(footprint "XKB_DC-005-5A-2.0"\n  (version 20240108)\n  (generator "gen_footprints")\n  (layer "F.Cu")\n'
    s += '  (descr "XKB DC-005-5A-2.0 barrel jack 5.5 x 2.0 mm, right angle. Same pads and slots as the Node board package. Jack mouth at -X, flush with the board edge when pad 2 is 7.62 mm in.")\n'
    s += '  (tags "barrel jack DC-005 5.5mm 2.0mm")\n'
    s += text('Reference', 'REF**', -1.0, -5.6, 'F.SilkS')
    s += text('Value', 'DC-005-5A-2.0', -0.6, 0, 'F.Fab')
    s += text('Footprint', '', 0, 0, 'F.Fab', hide=True)
    s += text('Datasheet', '', 0, 0, 'F.Fab', hide=True)
    s += text('Description', '', 0, 0, 'F.Fab', hide=True)
    s += '  (attr through_hole)\n'
    s += rect(-7.7, -4.5, 6.5, 4.5, 'F.Fab')
    s += rect(-7.95, -4.75, 7.4, 6.05, 'F.CrtYd', 0.05)
    s += line(-7.5, -4.62, 6.62, -4.62, 'F.SilkS')
    s += line(6.62, -4.62, 6.62, -2.6, 'F.SilkS')
    s += line(6.62, 2.6, 6.62, 4.62, 'F.SilkS')
    s += line(6.62, 4.62, 5.3, 4.62, 'F.SilkS')
    s += line(0.7, 4.62, -7.5, 4.62, 'F.SilkS')
    s += slot(1, 6, 0, 2.2, 4.4, 1.0, 3.5)       # centre pin (+)
    s += slot(2, 0, 0, 2.0, 4.0, 1.0, 3.0)       # sleeve
    s += slot(3, 3, 4.7, 4.0, 2.0, 3.0, 1.0)     # switch contact
    s += ')\n'
    open(os.path.join(OUT, 'XKB_DC-005-5A-2.0.kicad_mod'), 'w').write(s)


def sip3():
    """SIP-3_K7805_or_TO-220: KiCad's own footprint for the Recom R-78E
    (the K7805-500R3 is the same size and pinout), with the three holes
    opened from 1.0 mm to 1.1 mm, the size KiCad's TO-220 footprint uses.
    A linear 7805 in TO-220 has the same pin order (IN, GND, OUT) at the
    same 2.54 mm pitch, so either part fits these holes."""
    stock = ('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/'
             'Converter_DCDC.pretty/Converter_DCDC_RECOM_R-78E-0.5_THT.kicad_mod')
    name = 'SIP-3_K7805_or_TO-220'
    s = open(stock).read()
    assert s.count('(drill 1)') == 3
    s = s.replace('(drill 1)', '(drill 1.1)')
    s = s.replace('"Converter_DCDC_RECOM_R-78E-0.5_THT"', f'"{name}"')
    s = s.replace('(descr "DCDC-Converter, RECOM, RECOM_R-78E-0.5, SIP-3,',
                  '(descr "K7805-500R3 / Recom R-78E DC-DC module, or a TO-220 '
                  '78xx regulator: holes 1.1 mm. SIP-3,')
    open(os.path.join(OUT, name + '.kicad_mod'), 'w').write(s)


if __name__ == '__main__':
    xiao()
    jack()
    sip3()
    print('wrote', sorted(os.listdir(OUT)))
