#!/usr/bin/env python3
"""Write bldc.kicad_sym: the three custom schematic symbols of the BLDC board.

    python3 lib/gen_symbols.py        (then re-run ../gen_schematic.py)

The symbols are drawn by function, not by package order, so that a circuit
reads left to right with supply at the top and ground at the bottom:

  DRV8313PWP          logic inputs left, power stage right, VM top, every
                      ground (PGND, GND, PowerPAD, unused comparator) bottom
  XIAO_ESP32S3_Plus   I/O pads down each side in the module's physical pad
                      order, 5V and 3V3 on top, GND underneath
  74HC139             decoder 1 above decoder 2, inputs left, outputs right

Pin numbers, names and electrical types are the ones the first (package
order) symbols had; only the positions changed.  Everything sits on the
2.54 mm grid.  gen_schematic.py embeds these symbols in the schematic, so
after changing anything here re-run it, or ERC reports the library and the
schematic copies as different.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
P = 2.54            # pin pitch and pin length


def fmt(v):
    s = f'{v:.4f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def prop(name, value, x, y, hide=False, justify=None):
    j = f' (justify {justify})' if justify else ''
    h = ' (hide yes)' if hide else ''
    return (f'\t\t(property "{name}" "{value}" (at {fmt(x)} {fmt(y)} 0) '
            f'(show_name no) (do_not_autoplace no){h} '
            f'(effects (font (size 1.27 1.27)){j}))\n')


def symbol(name, footprint, datasheet, description, keywords, half_w, top,
           bottom, left=(), right=(), top_pins=(), bottom_pins=(), extra='',
           side_len=P):
    """half_w, top, bottom: body rectangle (bottom is negative).
    left / right:  (number, name, type, y[, shape]) at the body edge.
    top_pins / bottom_pins: (number, name, type, x[, shape]).
    side_len: length of the left and right pins (longer leaves room for the
    pin number beside an inversion bubble)."""
    out = [f'\t(symbol "{name}"\n',
           '\t\t(pin_names (offset 0.508))\n',
           '\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n',
           '\t\t(in_pos_files yes)\n',
           '\t\t(duplicate_pin_numbers_are_jumpers no)\n',
           prop('Reference', 'U', -half_w, top + 3.81, justify='left'),
           prop('Value', name, -half_w, top + 1.27, justify='left'),
           prop('Footprint', footprint, 0, 0, hide=True),
           prop('Datasheet', datasheet, 0, 0, hide=True),
           prop('Description', description, 0, 0, hide=True),
           prop('ki_keywords', keywords, 0, 0, hide=True),
           f'\t\t(symbol "{name}_0_1"\n',
           f'\t\t\t(rectangle (start {fmt(-half_w)} {fmt(top)}) '
           f'(end {fmt(half_w)} {fmt(bottom)}) '
           '(stroke (width 0.254) (type default)) (fill (type background)))\n',
           extra,
           '\t\t)\n',
           f'\t\t(symbol "{name}_1_1"\n']

    def pin(num, pname, etype, x, y, angle, length, shape='line'):
        out.append(
            f'\t\t\t(pin {etype} {shape} (at {fmt(x)} {fmt(y)} {angle}) '
            f'(length {fmt(length)}) '
            f'(name "{pname}" (effects (font (size 1.27 1.27)))) '
            f'(number "{num}" (effects (font (size 1.27 1.27)))))\n')

    for num, pname, etype, y, *shape in left:
        pin(num, pname, etype, -half_w - side_len, y, 0, side_len, *shape)
    for num, pname, etype, y, *shape in right:
        pin(num, pname, etype, half_w + side_len, y, 180, side_len, *shape)
    for num, pname, etype, x, *shape in top_pins:
        pin(num, pname, etype, x, top + P, 270, P, *shape)
    for num, pname, etype, x, *shape in bottom_pins:
        pin(num, pname, etype, x, bottom - P, 90, P, *shape)
    out += ['\t\t)\n', '\t\t(embedded_fonts no)\n', '\t)\n']
    return ''.join(out)


def rows(top_y, *names):
    """y for consecutive rows from top_y downwards; None leaves a row empty."""
    return {n: top_y - P * i for i, n in enumerate(names) if n}


# ------------------------------------------------------------------ DRV8313
def drv8313():
    ly = rows(7 * P, 'IN1', 'IN2', 'IN3', None, None, None,
              'EN1', 'EN2', 'EN3', 'nSLEEP', None, 'nRESET')
    ry = rows(7 * P, 'CPL', None, None, 'CPH', None, 'VCP', None,
              'OUT1', 'OUT2', 'OUT3', None, 'nFAULT', None, 'V3P3', None, 'NC')
    left = [('27', 'IN1', 'input'), ('25', 'IN2', 'input'),
            ('23', 'IN3', 'input'), ('26', 'EN1', 'input'),
            ('24', 'EN2', 'input'), ('22', 'EN3', 'input'),
            ('17', 'nSLEEP', 'input'), ('16', 'nRESET', 'input')]
    right = [('1', 'CPL', 'passive'), ('2', 'CPH', 'passive'),
             ('3', 'VCP', 'passive'), ('5', 'OUT1', 'output'),
             ('8', 'OUT2', 'output'), ('9', 'OUT3', 'output'),
             ('18', 'nFAULT', 'open_collector'), ('15', 'V3P3', 'power_out'),
             ('21', 'NC', 'no_connect')]
    bottom = [('12', 'COMPP', 'input'), ('13', 'COMPN', 'input'),
              ('19', 'nCOMPO', 'passive'), ('6', 'PGND1', 'power_in'),
              ('7', 'PGND2', 'power_in'), ('10', 'PGND3', 'power_in'),
              ('14', 'GND', 'power_in'), ('20', 'GND', 'power_in'),
              ('28', 'GND', 'power_in'), ('29', 'EP', 'power_in')]
    return symbol(
        'DRV8313PWP',
        'Package_SO:HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP2.85x5.4mm_ThermalVias',
        'https://www.ti.com/lit/ds/symlink/drv8313.pdf',
        'TI DRV8313 triple half-bridge driver, 8-60 V, 2.5 A peak, HTSSOP-28 '
        'PowerPAD (pin 29 = thermal pad)',
        'BLDC motor driver half bridge DRV8313 SimpleFOC',
        half_w=6 * P, top=8 * P, bottom=-9 * P,
        left=[(n, p, t, ly[p]) for n, p, t in left],
        right=[(n, p, t, ry[p]) for n, p, t in right],
        top_pins=[('4', 'VM', 'power_in', -2 * P),
                  ('11', 'VM', 'power_in', 2 * P)],
        bottom_pins=[(n, p, t, (i - 5) * P)
                     for i, (n, p, t) in enumerate(bottom)])


# --------------------------------------------------------------------- XIAO
def xiao():
    left = [('1', 'D0/GPIO1'), ('15', 'D11/GPIO38'), ('2', 'D1/GPIO2'),
            ('16', 'D12/GPIO39'), ('3', 'D2/GPIO3'), ('17', 'D13/GPIO40'),
            ('4', 'D3/GPIO4'), ('18', 'D14/GPIO41'), ('5', 'D4/GPIO5/SDA'),
            ('19', 'D15/GPIO42'), ('6', 'D5/GPIO6/SCL'), ('20', 'D16/GPIO10'),
            ('7', 'D6/GPIO43/TX')]
    # the right-hand edge starts with 5V, GND, 3V3 (drawn top and bottom),
    # so its I/O pads line up with the lower seven on the left
    right = [('11', 'D10/GPIO9'), ('23', 'D17/GPIO13'), ('10', 'D9/GPIO8'),
             ('22', 'D18/GPIO12'), ('9', 'D8/GPIO7'), ('21', 'D19/GPIO11'),
             ('8', 'D7/GPIO44/RX')]
    return symbol(
        'XIAO_ESP32S3_Plus', 'bldc:XIAO-ESP32-S3-Plus-SMD',
        'https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/',
        'Seeed Studio XIAO ESP32-S3 Plus, 23-pad castellated module. Pads '
        '1-14 edge castellations, 15-23 small pads between them (numbering '
        'per Seeed XIAO-HALF-HOLE-23P). I/O pins follow the physical pad '
        'order along each edge.',
        'XIAO ESP32-S3 Plus Seeed module',
        half_w=7 * P, top=7 * P, bottom=-9 * P,
        left=[(n, p, 'bidirectional', (6 - i) * P)
              for i, (n, p) in enumerate(left)],
        right=[(n, p, 'bidirectional', -i * P)
               for i, (n, p) in enumerate(right)],
        top_pins=[('14', '5V/VBUS', 'passive', 2 * P),
                  ('12', '3V3', 'power_out', 5 * P)],
        bottom_pins=[('13', 'GND', 'power_in', 4 * P)])


# ------------------------------------------------------------------ 74HC139
def hc139():
    divider = ('\t\t\t(polyline (pts (xy -7.62 0) (xy 7.62 0)) '
               '(stroke (width 0) (type dash)) (fill (type none)))\n')
    return symbol(
        '74HC139', 'Package_SO:SOIC-16_3.9x9.9mm_P1.27mm',
        'https://assets.nexperia.com/documents/data-sheet/74HC_HCT139.pdf',
        'Dual 2-to-4 line decoder, active-low outputs, single-unit symbol '
        'with power pins',
        '74HC139 decoder demultiplexer chip select',
        half_w=3 * P, top=5 * P, bottom=-6 * P,
        left=[('2', '1A0', 'input', 4 * P), ('3', '1A1', 'input', 3 * P),
              ('1', '1E', 'input', 2 * P, 'inverted'),
              ('15', '2E', 'input', -2 * P, 'inverted'),
              ('14', '2A0', 'input', -3 * P), ('13', '2A1', 'input', -4 * P)],
        right=[('4', '1Y0', 'output', 4 * P, 'inverted'),
               ('5', '1Y1', 'output', 3 * P, 'inverted'),
               ('6', '1Y2', 'output', 2 * P, 'inverted'),
               ('7', '1Y3', 'output', 1 * P, 'inverted'),
               ('12', '2Y0', 'output', -2 * P, 'inverted'),
               ('11', '2Y1', 'output', -3 * P, 'inverted'),
               ('10', '2Y2', 'output', -4 * P, 'inverted'),
               ('9', '2Y3', 'output', -5 * P, 'inverted')],
        top_pins=[('16', 'VCC', 'power_in', 0)],
        bottom_pins=[('8', 'GND', 'power_in', 0)],
        extra=divider, side_len=2 * P)


if __name__ == '__main__':
    text = ('(kicad_symbol_lib\n\t(version 20251024)\n'
            '\t(generator "gen_symbols")\n\t(generator_version "10.0")\n'
            + drv8313() + xiao() + hc139() + ')\n')
    path = os.path.join(HERE, 'bldc.kicad_sym')
    with open(path, 'w') as f:
        f.write(text)
    print('wrote', path)
