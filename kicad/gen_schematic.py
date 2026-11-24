#!/usr/bin/env python3
"""Draw the BLDC driver board schematic from design_spec.py.

    python3 gen_schematic.py            write the .kicad_sch files
    python3 gen_schematic.py check      ... then run KiCad's ERC and compare
                                        KiCad's netlist with design_spec.py
    python3 gen_schematic.py export     ... then also write output/schematic.pdf
                                        and output/schematic_pN.png

design_spec.py says WHAT is on the board (parts, values, footprints, nets).
This file says WHERE it is drawn: every position and wire below is layout
only.  A wire that joins the wrong pins is caught before anything is written,
because the nets formed by the drawing are compared with the spec's.

Pages (both A3):
  1  bldc_driver_board.kicad_sch   the four motor driver channels (root sheet)
  2  power_mcu_io.kicad_sch        power input and 5 V, MCU, encoder decoder
                                   and ports, I2C and status LED, test points

The driver page is the root sheet on purpose.  KiCad names a net after a
plain (local) label only on the root sheet; inside a sub-sheet the name gets
the sheet's name in front of it and would no longer match design_spec.py.
The driver channels have many nets that need a name but go nowhere else
(M1_CPL, M1_VCP ...), so they sit on the root where a plain label is enough.
Everything on page 2 is named by a global label or a power symbol.

The three custom symbols come from lib/bldc.kicad_sym (lib/gen_symbols.py),
the rest from KiCad's own libraries; all are embedded in the schematic.

Coordinates are in grid units of 1.27 mm (50 mil): 2 units = 0.1 inch.
Only text positions use fractions.  Standard library only.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import uuid

import design_spec as spec

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = 'bldc_driver_board'
ROOT_FILE = PROJECT + '.kicad_sch'
ROOT_UUID = '3d8e7281-3701-4497-b619-e206a713a3c6'   # as in the first schematic
SUB_FILE = 'power_mcu_io.kicad_sch'
SUB_NAME = 'Power MCU IO'
DRIVERS_PAGE, SYSTEM_PAGE = '1', '2'
STOCK = os.environ.get(
    'KICAD_SYMBOL_DIR',
    '/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols')
KICAD_CLI = os.environ.get(
    'KICAD_CLI', '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
RSVG = shutil.which('rsvg-convert') or '/opt/homebrew/bin/rsvg-convert'
FORMAT = '20260306'         # schematic file version KiCad 10.0.8 writes
DATE = '2026-11-11'
REV = 'draft 1'
U = 1.27                    # one grid unit in mm
PAGE_W, PAGE_H = 420 / U, 297 / U       # A3 in grid units
WORD_W = 0.93               # width of a character / text size, names and values
PROSE_W = 0.85              # ... and of running text (spaces are narrow)
NOTE = 1.5                  # text size of the notes, mm
SMALL = 1.27                # text size of the hints beside flags, mm


# =========================================================== s-expressions
class Q(str):
    """A quoted string token, kept with its quotes."""


def q(s):
    return Q('"' + str(s).replace('\\', '\\\\').replace('"', '\\"')
             .replace('\n', '\\n') + '"')


def unq(tok):
    return re.sub(r'\\(.)', lambda m: {'n': '\n'}.get(m.group(1), m.group(1)),
                  tok[1:-1])


TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse(text):
    stack, cur = [], None
    for tok in TOKEN.findall(text):
        if tok == '(':
            new = []
            if cur is not None:
                cur.append(new)
                stack.append(cur)
            cur = new
        elif tok == ')':
            if not stack:
                return cur
            cur = stack.pop()
        else:
            cur.append(Q(tok) if tok[0] == '"' else tok)
    return cur


def dump(node, depth=0):
    if not isinstance(node, list):
        return str(node)
    if not any(isinstance(c, list) for c in node):
        return '(' + ' '.join(node) + ')'
    i = 0
    while not isinstance(node[i], list):
        i += 1
    pad = '\n' + '\t' * (depth + 1)
    return ('(' + ' '.join(node[:i])
            + ''.join(pad + dump(c, depth + 1) for c in node[i:])
            + '\n' + '\t' * depth + ')')


def kids(node, head):
    return [c for c in node if isinstance(c, list) and c and c[0] == head]


def kid(node, head):
    k = kids(node, head)
    return k[0] if k else None


def num(v):
    """A length in mm as KiCad writes it."""
    s = f'{v:.4f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def mm(u):
    return num(u * U)


def uid(*key):
    return q(uuid.uuid5(uuid.UUID(ROOT_UUID), '/'.join(str(k) for k in key)))


# ========================================================= symbol libraries
class LibSymbol:
    """One library symbol, flattened and renamed for embedding, with its pin
    positions in grid units (y down, as on the sheet)."""

    def __init__(self, lib_id):
        self.lib_id = lib_id
        lib, name = lib_id.split(':')
        path = (os.path.join(HERE, 'lib', 'bldc.kicad_sym') if lib == 'bldc'
                else os.path.join(STOCK, lib + '.kicad_sym'))
        text = _lib_text(path)
        tree = _symbol_block(text, name, path)
        parent = kid(tree, 'extends')
        if parent:                      # derived symbol: parent's body, own fields
            pname = unq(parent[1])
            body = [c for c in _symbol_block(text, pname, path)[2:]
                    if c[0] != 'property']
            units = []
            for unit in kids(body, 'symbol'):
                unit = list(unit)
                unit[1] = q(name + unq(unit[1])[len(pname):])
                units.append(unit)
            tree = (['symbol', q(name)]
                    + [c for c in body if c[0] not in ('symbol', 'embedded_fonts')]
                    + kids(tree, 'property') + units
                    + kids(body, 'embedded_fonts'))
        tree[1] = q(lib_id)
        self.tree = tree
        self.power = kid(tree, 'power') is not None
        self.props = {unq(p[1]): unq(p[2]) for p in kids(tree, 'property')}
        self.pins = {}      # number -> (x, y, angle, length, name, type), units
        box = []
        for unit in kids(tree, 'symbol'):
            for p in kids(unit, 'pin'):
                at = kid(p, 'at')
                x, y = float(at[1]) / U, -float(at[2]) / U
                if abs(x - round(x)) < 1e-6 and abs(y - round(y)) < 1e-6:
                    x, y = round(x), round(y)
                self.pins[unq(kid(p, 'number')[1])] = (
                    x, y, int(at[3]), float(kid(p, 'length')[1]) / U,
                    unq(kid(p, 'name')[1]), p[1])
            for g in unit[2:]:
                if g[0] == 'rectangle':
                    box += [kid(g, 'start')[1:3], kid(g, 'end')[1:3]]
                elif g[0] in ('polyline', 'bezier'):
                    box += [xy[1:3] for xy in kids(kid(g, 'pts'), 'xy')]
                elif g[0] == 'arc':
                    box += [kid(g, k)[1:3] for k in ('start', 'mid', 'end')]
                elif g[0] == 'circle':
                    cx, cy = map(float, kid(g, 'center')[1:3])
                    r = float(kid(g, 'radius')[1])
                    box += [(cx - r, cy - r), (cx + r, cy + r)]
        xs = [float(p[0]) / U for p in box] or [0]
        ys = [-float(p[1]) / U for p in box] or [0]
        self.box = (min(xs), min(ys), max(xs), max(ys))


_LIB_CACHE = {}


def _lib_text(path):
    if path not in _LIB_CACHE:
        with open(path, encoding='utf-8') as f:
            _LIB_CACHE[path] = f.read()
    return _LIB_CACHE[path]


def _symbol_block(text, name, path):
    """Parse one top-level symbol out of a library without parsing the rest."""
    m = re.search(r'\n\s*\(symbol "%s"\s' % re.escape(name), text)
    if not m:
        raise SystemExit(f'symbol {name} not found in {path}')
    i = text.index('(', m.start())
    depth, j, in_str = 0, i, False
    while True:
        ch = text[j]
        if in_str:
            if ch == '\\':
                j += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return parse(text[i:j + 1])
        j += 1


_SYMS = {}


def libsym(lib_id):
    if lib_id not in _SYMS:
        _SYMS[lib_id] = LibSymbol(lib_id)
    return _SYMS[lib_id]


def turn(x, y, rot, mirror=None):
    """Symbol-local (y down) to sheet-relative, as KiCad does it: mirror
    first, then rotate anticlockwise on the screen."""
    if mirror == 'x':
        y = -y
    elif mirror == 'y':
        x = -x
    return {0: (x, y), 90: (y, -x), 180: (-x, -y), 270: (-y, x)}[rot]


# ================================================================== drawing
COMP = {c['ref']: c for c in spec.COMPONENTS if not c['ref'].startswith('#')}
PLACED = {}                 # ref -> Part, across all sheets
COUNTER = {'#PWR': 0, '#FLG': 0}

# where reference and value go, as offsets from the symbol origin:
# (dx, dy, justify) with justify l / c / r as it should look on the sheet
RIGHT = dict(ref=(2.4, -1, 'l'), val=(2.4, 1, 'l'))      # beside an upright part
LEFT = dict(ref=(-2.4, -1, 'r'), val=(-2.4, 1, 'r'))
ACROSS = dict(ref=(0, -2.3, 'c'), val=(0, 2.3, 'c'))     # above / below, lying


def net_of(ref, pin='1'):
    return next(n for n, pins in spec.NETS.items() if (ref, str(pin)) in pins)


class Part:
    def __init__(self, sheet, ref, lib_id, x, y, rot, mirror):
        self.sheet, self.ref, self.lib = sheet, ref, libsym(lib_id)
        self.x, self.y, self.rot, self.mirror = x, y, rot, mirror

    def p(self, pin):
        """Sheet position of the connection end of a pin."""
        px, py = self.lib.pins[str(pin)][:2]
        dx, dy = turn(px, py, self.rot, self.mirror)
        return (self.x + dx, self.y + dy)

    def body(self):
        x0, y0, x1, y1 = self.lib.box
        (ax, ay), (bx, by) = (turn(x0, y0, self.rot, self.mirror),
                              turn(x1, y1, self.rot, self.mirror))
        return (self.x + min(ax, bx), self.y + min(ay, by),
                self.x + max(ax, bx), self.y + max(ay, by))


class Sheet:
    def __init__(self, name, filename, title, page, path):
        self.name, self.filename, self.title = name, filename, title
        self.page, self.path = page, path
        self.root = path == '/' + ROOT_UUID
        self.uuid = q(ROOT_UUID) if self.root else uid('file', filename)
        self.parts, self.wires, self.items = [], [], []
        self.labels, self.ncs, self.texts = [], [], []     # for the checks
        self.used = {}

    # ---------------------------------------------------------------- parts
    def _fields(self, part, lines, ref, val):
        """Reference and value, then the hidden fields."""
        rot, mirror = part.rot, part.mirror
        angle = 0 if rot in (0, 180) else 90
        out = []
        for name, text, pos in (('Reference', lines[0], ref),
                                ('Value', lines[1], val)):
            dx, dy, just = pos or (0, 0, 'c')
            stored = just
            if just != 'c':            # KiCad turns the justification with the symbol
                ex = turn(*((1, 0) if angle == 0 else (0, -1)), rot, mirror)[0]
                if ex < 0:
                    stored = {'l': 'r', 'r': 'l'}[just]
            eff = ['effects', ['font', ['size', '1.27', '1.27']]]
            if stored != 'c':
                eff.append(['justify', {'l': 'left', 'r': 'right'}[stored]])
            p = ['property', q(name), q(text),
                 ['at', mm(part.x + dx), mm(part.y + dy), str(angle)]]
            if pos is None:
                p.append(['hide', 'yes'])
            else:
                w = len(text) * WORD_W
                x0 = part.x + dx - {'l': 0, 'c': w / 2, 'r': w}[just]
                self.texts.append((f'{lines[0]} {name.lower()}', x0,
                                   part.y + dy - 0.5, x0 + w, part.y + dy + 0.5))
            out.append(p + [['show_name', 'no'], ['do_not_autoplace', 'no'], eff])
        for name, text in lines[2:]:
            out.append(['property', q(name), q(text),
                        ['at', mm(part.x), mm(part.y), '0'], ['hide', 'yes'],
                        ['show_name', 'no'], ['do_not_autoplace', 'no'],
                        ['effects', ['font', ['size', '1.27', '1.27']]]])
        return out

    def _symbol(self, part, fields, in_bom='yes', dnp='no'):
        node = ['symbol', ['lib_id', q(part.lib.lib_id)],
                ['at', mm(part.x), mm(part.y), str(part.rot)]]
        if part.mirror:
            node.append(['mirror', part.mirror])
        node += [['unit', '1'], ['body_style', '1'], ['exclude_from_sim', 'no'],
                 ['in_bom', in_bom], ['on_board', 'yes'], ['in_pos_files', 'yes'],
                 ['dnp', dnp], ['uuid', uid('symbol', part.ref)]]
        node += fields
        node += [['pin', q(n), ['uuid', uid('pin', part.ref, n)]]
                 for n in part.lib.pins]
        node.append(['instances', ['project', q(PROJECT),
                                   ['path', q(self.path),
                                    ['reference', q(part.ref)], ['unit', '1']]]])
        self.items.append(node)
        self.used[part.lib.lib_id] = part.lib
        self.parts.append(part)
        return part

    def part(self, name, x, y, rot=0, mirror=None, ref=RIGHT['ref'],
             val=RIGHT['val']):
        """Place component `name` of design_spec.COMPONENTS.  ref and val say
        where its reference and value text go (see RIGHT, ACROSS ...)."""
        c = COMP[name]
        if name in PLACED:
            raise SystemExit(f'{name} placed twice')
        part = Part(self, name, c['symbol'], x, y, rot, mirror)
        PLACED[name] = part
        lib = part.lib.props
        extra = [('Footprint', c['footprint']),
                 ('Datasheet', lib.get('Datasheet', '')),
                 ('Description', lib.get('Description', ''))]
        if c['lcsc']:
            extra.append(('LCSC', c['lcsc']))
        fields = self._fields(part, [name, c['value']] + extra, ref, val)
        return self._symbol(part, fields, in_bom='no' if c['nobom'] else 'yes',
                            dnp='yes' if c['dnp'] else 'no')

    def power(self, name, x, y, rot=0):
        """A power symbol (GND, +3V3, +5V, +12V) or a PWR_FLAG with its pin at
        (x, y).  rot 180 hangs it upside down."""
        kind = '#FLG' if name == 'PWR_FLAG' else '#PWR'
        COUNTER[kind] += 1
        ref = f'{kind}{COUNTER[kind]:02d}'
        part = Part(self, ref, 'power:' + name, x, y, rot, None)
        below = (name == 'GND') != (rot == 180)
        dy = 3.2 if name == 'PWR_FLAG' else 3.1 if name == 'GND' else 3.0
        fields = self._fields(
            part, [ref, name, ('Footprint', ''), ('Datasheet', ''),
                   ('Description', part.lib.props.get('Description', ''))],
            None, (0, dy if below else -dy, 'c'))
        return self._symbol(part, fields)

    # ---------------------------------------------------------------- wires
    def wire(self, *pts):
        """A wire through the given points; each leg must be straight."""
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            if a[0] != b[0] and a[1] != b[1]:
                raise SystemExit(f'{self.name}: slanted wire {a} -> {b}')
            self.wires.append((tuple(a), tuple(b)))

    def label(self, name, x, y):
        """Plain net label, text to the right of (x, y), which must lie on a
        wire.  Only names a net correctly on the root sheet."""
        self.items.append(['label', q(name), ['at', mm(x), mm(y), '0'],
                           ['effects', ['font', ['size', '1.27', '1.27']],
                            ['justify', 'left', 'bottom']],
                           ['uuid', uid(self.name, 'label', name, x, y)]])
        self.labels.append(('local', name, (x, y)))
        self.texts.append((f'label {name}', x, y - 1.4,
                           x + len(name) * WORD_W, y - 0.3))

    def glabel(self, name, x, y, rot=0, shape='passive'):
        """Global label with its connection point at (x, y); rot 0 puts the
        flag to the right of that point, 180 to the left."""
        just = {0: 'left', 180: 'right'}[rot]
        self.items.append(
            ['global_label', q(name), ['shape', shape],
             ['at', mm(x), mm(y), str(rot)],
             ['effects', ['font', ['size', '1.27', '1.27']], ['justify', just]],
             ['uuid', uid(self.name, 'glabel', name, x, y)],
             ['property', q('Intersheetrefs'), q('${INTERSHEET_REFS}'),
              ['at', mm(x), mm(y), '0'], ['hide', 'yes'], ['show_name', 'no'],
              ['do_not_autoplace', 'no'],
              ['effects', ['font', ['size', '1.27', '1.27']]]]])
        self.labels.append(('global', name, (x, y)))
        w = len(name) * WORD_W + 2.4
        x0 = x if rot == 0 else x - w
        self.texts.append((f'flag {name}', x0, y - 0.9, x0 + w, y + 0.9))

    def nc(self, pt):
        self.items.append(['no_connect', ['at', mm(pt[0]), mm(pt[1])],
                           ['uuid', uid(self.name, 'nc', *pt)]])
        self.ncs.append(tuple(pt))

    # ------------------------------------------------------------- graphics
    def text(self, s, x, y, size=NOTE, bold=False, just='left', valign='top'):
        """Free text.  (x, y) is the top corner on the `just` side, or with
        valign='center' the middle of that side."""
        font = ['font', ['size', num(size), num(size)]]
        if bold:
            font += [['thickness', num(size / 5)], ['bold', 'yes']]
        justify = ['justify', just] + (['top'] if valign == 'top' else [])
        self.items.append(['text', q(s), ['exclude_from_sim', 'no'],
                           ['at', mm(x), mm(y), '0'], ['effects', font, justify],
                           ['uuid', uid(self.name, 'text', s, x, y)]])
        lines = s.split('\n')
        w = (max(len(ln) for ln in lines) * size / U
             * (WORD_W * 1.08 if bold else PROSE_W))
        h = len(lines) * size / U * 1.62
        x0 = x if just == 'left' else x - w
        y0 = y if valign == 'top' else y - h / 2
        self.texts.append((f'text "{lines[0][:28]}"', x0, y0, x0 + w, y0 + h))

    def note(self, x, y, *lines):
        self.text('\n'.join(lines), x, y)

    def hint(self, s, x, y, just='left'):
        """Small text level with a pin row: where the signal goes."""
        self.text(s, x, y, size=SMALL, just=just, valign='center')

    def frame(self, x0, y0, x1, y1, title):
        """A titled dashed box round one functional block."""
        self.items.append(['rectangle', ['start', mm(x0), mm(y0)],
                           ['end', mm(x1), mm(y1)],
                           ['stroke', ['width', '0.15'], ['type', 'dash']],
                           ['fill', ['type', 'none']],
                           ['uuid', uid(self.name, 'frame', title)]])
        self.text(title, x0 + 1.5, y0 + 1.2, size=2.2, bold=True)

    def subsheet(self, child, x, y, w, h):
        self.items.append(
            ['sheet', ['at', mm(x), mm(y)], ['size', mm(w), mm(h)],
             ['exclude_from_sim', 'no'], ['in_bom', 'yes'], ['on_board', 'yes'],
             ['dnp', 'no'], ['stroke', ['width', '0.1524'], ['type', 'solid']],
             ['fill', ['color', '0', '0', '0', '0']],
             ['uuid', uid('sheet', child.filename)],
             ['property', q('Sheetname'), q(child.name),
              ['at', mm(x), mm(y - 0.6), '0'],
              ['show_name', 'no'], ['do_not_autoplace', 'no'],
              ['effects', ['font', ['size', '1.27', '1.27']],
               ['justify', 'left', 'bottom']]],
             ['property', q('Sheetfile'), q(child.filename),
              ['at', mm(x), mm(y + h + 0.6), '0'],
              ['show_name', 'no'], ['do_not_autoplace', 'no'],
              ['effects', ['font', ['size', '1.27', '1.27']],
               ['justify', 'left', 'top']]],
             ['instances', ['project', q(PROJECT),
                            ['path', q(self.path), ['page', q(child.page)]]]]])
        self.texts.append((f'sheet box {child.name}', x, y - 2, x + w, y + h + 2))

    # --------------------------------------------------------------- output
    def tidy_wires(self):
        """Cut every wire where a pin or another wire's end touches it, so
        that things connect only at wire ends, and say where the junction
        dots go.  Labels are left sitting on an unbroken stretch of wire."""
        cuts = {pt for seg in self.wires for pt in seg}
        cuts |= {p.p(n) for p in self.parts for n in p.lib.pins}
        segs = set()
        for a, b in self.wires:
            (x0, y0), (x1, y1) = sorted((a, b))
            on = sorted(c for c in cuts
                        if x0 <= c[0] <= x1 and y0 <= c[1] <= y1)
            segs |= {(on[i], on[i + 1]) for i in range(len(on) - 1)}
        self.segs = sorted(segs)
        ends = {}
        for seg in self.segs:
            for pt in seg:
                ends[pt] = ends.get(pt, 0) + 1
        for p in self.parts:
            for n in p.lib.pins:
                if p.p(n) in ends:
                    ends[p.p(n)] += 1
        self.junctions = sorted(pt for pt, n in ends.items() if n >= 3)

    def write(self, comment):
        self.tidy_wires()
        tree = ['kicad_sch', ['version', FORMAT], ['generator', q('eeschema')],
                ['generator_version', q('10.0')], ['uuid', self.uuid],
                ['paper', q('A3')],
                ['title_block', ['title', q(self.title)], ['date', q(DATE)],
                 ['rev', q(REV)], ['comment', '1', q(comment)]],
                ['lib_symbols'] + [s.tree for _, s in sorted(self.used.items())]]
        for pt in self.junctions:
            tree.append(['junction', ['at', mm(pt[0]), mm(pt[1])],
                         ['diameter', '0'], ['color', '0', '0', '0', '0'],
                         ['uuid', uid(self.name, 'junction', *pt)]])
        for a, b in self.segs:
            tree.append(['wire', ['pts', ['xy', mm(a[0]), mm(a[1])],
                                  ['xy', mm(b[0]), mm(b[1])]],
                         ['stroke', ['width', '0'], ['type', 'default']],
                         ['uuid', uid(self.name, 'wire', *a, *b)]])
        tree += self.items
        if self.root:
            tree.append(['sheet_instances', ['path', q('/'), ['page', q(self.page)]]])
        with open(os.path.join(HERE, self.filename), 'w', encoding='utf-8') as f:
            f.write(dump(tree) + '\n')


# ========================================================== page 1: drivers
def channel_centre(x0, y0):
    """Where the DRV8313 sits in the driver box with top left corner (x0, y0)."""
    return x0 + 80, y0 + 48


def driver_channel(sh, n, x0, y0):
    """One DRV8313 channel in the cell whose top left corner is (x0, y0).
    All four are drawn by this one function, so they are identical apart
    from the names."""
    sh.frame(x0, y0, x0 + 154, y0 + 84,
             f'Motor {n}: driver U{n + 1}, connector J1{n}')
    X, Y = channel_centre(x0, y0)
    u = sh.part(f'U{n + 1}', X, Y, ref=(-12, -17.2, 'l'), val=(5.5, -17.2, 'l'))
    rail = Y - 30                                   # the VMn rail

    # ---- supply: +12V, polyfuse, VMn rail with its capacitors
    f = sh.part(f'F{n}', X - 51, rail, rot=90, **ACROSS)
    sh.power('+12V', X - 58, rail)
    sh.wire((X - 58, rail), f.p(1))
    sh.wire(f.p(2), (X + 34, rail))
    sh.power('PWR_FLAG', X - 45, rail)
    sh.label(f'VM{n}', X - 43, rail)
    bulk = sh.part(f'C{n}5', X - 36, rail + 3)
    c3 = sh.part(f'C{n}3', X - 24, rail + 3)
    c4 = sh.part(f'C{n}4', X - 14, rail + 3)
    for c in (bulk, c3, c4):
        sh.wire(c.p(2), (c.x, rail + 8))
    sh.wire((bulk.x, rail + 8), (c4.x, rail + 8))
    sh.power('GND', X - 30, rail + 8)
    sh.wire(u.p(4), (u.p(4)[0], rail))              # VM
    sh.wire(u.p(11), (u.p(11)[0], rail))            # VM

    # ---- charge pump
    c1 = sh.part(f'C{n}1', X + 22, Y - 11)          # CPL - CPH
    sh.wire(u.p(1), c1.p(1))
    sh.wire(u.p(2), c1.p(2))
    sh.label(f'M{n}_CPL', X + 15, u.p(1)[1])
    sh.label(f'M{n}_CPH', X + 15, u.p(2)[1])
    c2 = sh.part(f'C{n}2', X + 34, rail + 3, rot=180)       # VCP - VM
    sh.wire(u.p(3), (X + 34, u.p(3)[1]), c2.p(1))
    sh.label(f'M{n}_VCP', X + 15, u.p(3)[1])

    # ---- motor phases
    j = sh.part(f'J1{n}', X + 46, Y + 2, ref=(2.2, -1, 'l'), val=(2.2, 1, 'l'))
    for k, pin in ((1, 5), (2, 8), (3, 9)):
        sh.wire(u.p(pin), j.p(k))
        sh.label(f'M{n}_OUT{k}', X + 15, u.p(pin)[1])

    # ---- fault LED: +3V3 - R - LED - nFAULT (open drain)
    led = sh.part(f'D{n}1', X + 37, Y + 8, ref=(-0.4, 3.4, 'r'), val=(0.4, 3.4, 'l'))
    r = sh.part(f'R{n}1', X + 51, Y + 8, rot=270, **ACROSS)
    sh.wire(u.p(18), led.p(1))
    sh.label(f'M{n}_FAULT', X + 15, Y + 8)
    sh.wire(led.p(2), r.p(2))
    sh.label(f'M{n}_LED', X + 41, Y + 8)
    sh.wire(r.p(1), (X + 58, Y + 8), (X + 58, Y + 6))
    sh.power('+3V3', X + 58, Y + 6)

    # ---- the chip's own 3.3 V regulator: decoupling only
    c6 = sh.part(f'C{n}6', X + 24, Y + 15)
    sh.wire(u.p(15), c6.p(1))
    sh.label(f'M{n}_V3P3', X + 15, Y + 12)

    # ---- every ground pin, the PowerPAD and the unused comparator
    bar = Y + 22
    for pin in (12, 13, 19, 6, 7, 10, 14, 20, 28, 29):
        sh.wire(u.p(pin), (u.p(pin)[0], bar))
    sh.wire((X - 10, bar), (X + 24, bar), c6.p(2))
    sh.power('GND', X + 16, bar)

    # ---- logic side
    for k, pin in ((1, 27), (2, 25), (3, 23)):
        x, y = u.p(pin)
        sh.wire((x, y), (x - 6, y))
        sh.glabel(f'M{n}_IN{k}', x - 6, y, 180, 'input')
        pad = next(p for r_, p in spec.NETS[f'M{n}_IN{k}'] if r_ == 'U1')
        sh.hint(f'U1 pad {pad}, {libsym(COMP["U1"]["symbol"]).pins[pad][4]}',
                x - 15.5, y, 'right')
    for pin in (26, 24, 22, 17):                    # EN1-3, nSLEEP tied high
        sh.wire(u.p(pin), (X - 18, u.p(pin)[1]))
    sh.wire((X - 18, Y + 4), (X - 18, Y - 4))
    sh.power('+3V3', X - 18, Y - 4)
    x, y = u.p(16)
    sh.wire((x, y), (x - 6, y))
    sh.glabel('DRV_EN', x - 6, y, 180, 'input')
    sh.hint('U1 pad 4, D3/GPIO4: all four drivers', x - 15.5, y, 'right')
    return X, Y


def channel1_testpoints(sh, X, Y):
    """TP6-TP9 probe driver 1 only.  They are drawn beside the channel and
    joined to it by net labels, so channel 1 looks like the other three."""
    x, y = X - 60, Y + 13
    sh.text('Test pads on this channel only:', x, y, size=1.27)
    for i, ref in enumerate(('TP6', 'TP7', 'TP8', 'TP9')):
        yy = y + 5 + 3 * i
        tp = sh.part(ref, x + 12, yy, rot=270, ref=(4.6, 0, 'l'), val=(9, 0, 'l'))
        sh.wire((x, yy), tp.p(1))
        sh.label(net_of(ref), x, yy)


def channel1_ground_pad(sh, X, Y):
    """TP12: a ground pad for the probe, under TP6-TP9."""
    x, yy = X - 60, Y + 30
    tp = sh.part('TP12', x + 12, yy, rot=270, ref=(4.6, 0, 'l'), val=(9, 0, 'l'))
    sh.wire((x, yy), tp.p(1))
    sh.power('GND', x, yy)


CELLS = {1: (10, 10), 2: (166, 10), 3: (10, 97), 4: (166, 97)}   # driver boxes


def drivers_page(sh, sub):
    for n, (x0, y0) in CELLS.items():
        centre = driver_channel(sh, n, x0, y0)
        if n == 1:
            channel1_testpoints(sh, *centre)
    sh.frame(10, 184, 234, 224, 'Notes: the four channels are identical')
    sh.note(
        12, 190,
        'Channel n: driver U(n+1), fuse Fn, capacitors Cn1-Cn6, fault LED Dn1',
        '   with Rn1, motor connector J1n.',
        f'Mn_IN1..3 are the PWM inputs from the XIAO (page {SYSTEM_PAGE}).  EN1-3 and nSLEEP',
        '   are tied high, so each OUT simply follows its IN.',
        f'DRV_EN (XIAO D3, page {SYSTEM_PAGE}) drives nRESET of all four drivers.  Low = all',
        '   outputs off; R3 holds it low through boot, reset and flashing.',
        '   A low pulse also clears a latched fault.',
        "V3P3 is the chip's own 3.3 V regulator output: Cn6 only.",
        "   Do NOT join it to the board's +3V3.",
        'Fn (1.1 A hold, 2.2 A trip polyfuse) takes a dead driver off the +12V rail.',
        'Each channel has its own 100 uF (Cn5).')
    sh.note(
        104, 190,
        'Cn1 (charge pump, CPL-CPH) must be 50 V rated.  Cn2 is VCP to VM.',
        'Cn3 / Cn4 sit right at the VM pins 4 and 11.',
        'Dn1 lights when the driver reports a fault (nFAULT pulls low).',
        '   There is no fault line back to the XIAO.',
        'COMPP, COMPN, nCOMPO: the comparator is not used and is grounded,',
        '   as in the TI data sheet.',
        'EP (pin 29) is the PowerPAD: soldered to the ground pour over vias.',
        'PWR_FLAG is not a part.  It tells the rule check that a net is',
        '   powered (a fuse does not count as a source).',
        'Names on the wires (M1_CPL ...) are the net names used on the PCB.')
    sh.subsheet(sub, 190, 194, 36, 12)
    sh.text(f'Page {SYSTEM_PAGE}: power input and 5 V, XIAO, encoders,\n'
            'I2C, status LED, test points.\nDouble-click the box to open it.',
            190, 209.5, size=1.27)


# ===================================== page 2: power, MCU and everything else
def power_block(sh, ox, oy):
    sh.frame(ox, oy, ox + 160, oy + 60, 'Power input and 5 V')
    rail = oy + 22
    j1 = sh.part('J1', ox + 14, rail + 2, ref=(-4, -5.2, 'l'), val=(1, -5.2, 'l'))
    j2 = sh.part('J2', ox + 14, rail + 20, ref=(-4, -5.2, 'l'), val=(1, -5.2, 'l'))
    d1 = sh.part('D1', ox + 39, rail, rot=180, **ACROSS)
    sh.wire(j1.p(1), d1.p(2))
    sh.wire(j2.p(1), (ox + 30, j2.p(1)[1]), (ox + 30, rail))
    sh.wire((ox + 25, rail), (ox + 25, rail - 6))
    sh.glabel('12V_JACK', ox + 25, rail - 6, 0, 'passive')
    for j in (j1, j2):
        sh.nc(j.p(3))
        x, y = j.p(2)
        sh.wire((x, y), (x + 4, y), (x + 4, y + 2))
        sh.power('GND', x + 4, y + 2)
    c3 = sh.part('C3', ox + 50, rail + 3)
    d4 = sh.part('D4', ox + 64, rail + 3, rot=270)
    c4 = sh.part('C4', ox + 92, rail + 3)
    u7 = sh.part('U7', ox + 108, rail, ref=(-4, -5.2, 'l'), val=(-4, -3.4, 'l'))
    sh.wire(d1.p(1), u7.p(1))
    sh.power('+12V', ox + 76, rail)
    sh.power('PWR_FLAG', ox + 84, rail)
    c5 = sh.part('C5', ox + 124, rail + 3)
    d2 = sh.part('D2', ox + 143, rail, rot=180, **ACROSS)
    sh.wire(u7.p(3), d2.p(2))
    sh.power('+5V', ox + 134, rail)
    sh.wire(d2.p(1), (ox + 150, rail))
    sh.glabel('XIAO_5V', ox + 150, rail, 0, 'output')
    bar = rail + 8
    for part, pin in ((c3, 2), (d4, 2), (c4, 2), (u7, 2), (c5, 2)):
        sh.wire(part.p(pin), (part.p(pin)[0], bar))
    sh.wire((ox + 44, bar), (c5.x, bar))
    sh.power('GND', ox + 100, bar)
    sh.power('PWR_FLAG', ox + 44, bar, rot=180)
    sh.note(
        ox + 42, oy + 38,
        'J1 and J2 (centre pin positive) are in parallel: 12 V passes straight through to the next board.',
        'D1 blocks a reversed 12 V lead.  D4 clamps the +12V rail: D1 stops a decelerating motor',
        '   returning energy to the supply, so the rail can only rise; the electrolytics are 25 V.',
        f'+12V feeds the four drivers through their own polyfuses F1-F4 (page {DRIVERS_PAGE}).',
        'U7 (linear 7805, TO-220) makes +5V for the XIAO; a K7805-500R3 switching module fits the',
        '   same three holes.  D2 stops USB (the XIAO VBUS pin) back-feeding +5V.',
        'PWR_FLAG is not a part: it tells the rule check that a net is powered.')


MCU_HINTS = {
    'DRV_EN': 'nRESET (pin 16) of U2-U5',
    'ENC_CLK': 'Rn2, then pin 3 of ENC1-4',
    'ENC_DO_MCU': 'R6, then pin 4 of ENC1-4',
    'SDA': 'Qwiic J3 / J4 pin 3',
    'SCL': 'Qwiic J3 / J4 pin 4',
}


def mcu_hint(net):
    """Where a XIAO signal goes, for the small text beside its flag."""
    if net in MCU_HINTS:
        return MCU_HINTS[net]
    (ref, pin), = [(r, p) for r, p in spec.NETS[net] if r != 'U1']
    return f'{ref} {libsym(COMP[ref]["symbol"]).pins[pin][4]} (pin {pin})'


def mcu_block(sh, ox, oy):
    sh.frame(ox, oy, ox + 160, oy + 78, 'MCU: Seeed XIAO ESP32-S3 Plus (hand-soldered)')
    X, Y = ox + 90, oy + 40
    u = sh.part('U1', X, Y, ref=(-13, -15.2, 'l'), val=(-13, 19.2, 'l'))
    shapes = {'SDA': 'bidirectional', 'SCL': 'bidirectional',
              'ENC_DO_MCU': 'input'}
    for pin in (1, 15, 2, 16, 3, 17, 18, 5, 19, 6, 20, 7):          # left edge
        x, y = u.p(pin)
        name = net_of('U1', pin)
        sh.wire((x, y), (x - 4, y))
        sh.glabel(name, x - 4, y, 180, shapes.get(name, 'output'))
        sh.hint(mcu_hint(name), x - 18, y, 'right')
    for pin in (11, 23, 10, 22, 9, 21, 8):                          # right edge
        x, y = u.p(pin)
        name = net_of('U1', pin)
        sh.wire((x, y), (x + 4, y))
        sh.glabel(name, x + 4, y, 0, shapes.get(name, 'output'))
        sh.hint(mcu_hint(name), x + 13, y)
    # DRV_EN with its pull-down, taken out past the other flags
    x, y = u.p(4)
    r3 = sh.part('R3', X - 62, y + 3, **LEFT)
    sh.wire((x, y), (X - 68, y))
    sh.glabel('DRV_EN', X - 68, y, 180, 'output')
    sh.hint(mcu_hint('DRV_EN'), X - 63, y - 1.8, 'right')
    sh.power('GND', *r3.p(2))
    # supply pins
    x, y = u.p(14)
    sh.wire((x, y), (x, y - 8), (x - 6, y - 8))
    sh.glabel('XIAO_5V', x - 6, y - 8, 180, 'input')
    x, y = u.p(12)
    sh.wire((x, y), (x, y - 10))
    sh.power('+3V3', x, y - 10)
    c6 = sh.part('C6', x + 10, y - 3)
    sh.wire((x, y - 6), (x + 10, y - 6))
    sh.power('GND', *c6.p(2))
    sh.power('GND', *u.p(13))
    sh.note(
        ox + 3, oy + 7.5,
        "The I/O pins are drawn in the module's pad order down each edge.",
        "Pad numbers are Seeed's: 1-14 the edge castellations,",
        '   15-23 the small pads between them.',
        "The 3V3 pin is an output: the module's own regulator",
        "   makes the board's +3V3 rail.  C6 is its bulk capacitor.")
    sh.note(
        ox + 3, oy + 59,
        'Each motor has three adjacent pads.  Any GPIO can carry any PWM,',
        '   so phases may be swapped in layout.',
        'No PWM on D6 / D7 (UART0, active at boot).',
        'DRV_EN is on D3, which is quiet at boot; R3 keeps the drivers',
        '   off until firmware raises it.',
        f'Mn_INk and DRV_EN go to page {DRIVERS_PAGE}.  All 20 GPIO are used.')


def decoder_block(sh, ox, oy):
    sh.frame(ox, oy, ox + 148, oy + 60, 'Encoder chip-select decoder and SSI bus')
    X, Y = ox + 40, oy + 34
    u = sh.part('U6', X, Y, ref=(1.5, -13.2, 'l'), val=(1.5, 15.3, 'l'))
    for pin, name in ((2, 'ENC_A0'), (3, 'ENC_A1')):
        x, y = u.p(pin)
        sh.wire((x, y), (x - 4, y))
        sh.glabel(name, x - 4, y, 180, 'input')
    x, y = u.p(1)                                   # 1E low: decoder 1 enabled
    sh.wire((x, y), (x - 4, y), (x - 4, y + 2))
    sh.power('GND', x - 4, y + 2)
    x, y = u.p(15)                                  # 2E high: decoder 2 off
    sh.wire((x, y), (x - 10, y), (x - 10, y - 2))
    sh.power('+3V3', x - 10, y - 2)
    bar = Y + 16
    x = u.p(14)[0] - 4
    sh.wire(u.p(14), (x, u.p(14)[1]))               # 2A0, 2A1 low
    sh.wire(u.p(13), (x, u.p(13)[1]))
    sh.wire((x, u.p(14)[1]), (x, bar), (X, bar), u.p(8))
    sh.power('GND', X - 6, bar)
    for k, pin in enumerate((4, 5, 6, 7), start=1):
        x, y = u.p(pin)
        sh.wire((x, y), (x + 4, y))
        sh.glabel(f'CS{k}', x + 4, y, 0, 'output')
    for pin in (12, 11, 10, 9):
        sh.nc(u.p(pin))
    x, y = u.p(16)                                  # VCC and its capacitor
    sh.wire((x, y), (x, y - 10))
    sh.power('+3V3', x, y - 10)
    c1 = sh.part('C1', x + 10, y - 5)
    sh.wire((x, y - 8), (x + 10, y - 8))
    sh.power('GND', *c1.p(2))
    # data: the shared line with its pull-up, then R6 in series to the XIAO
    # (the clock goes straight from the XIAO to a resistor at each socket)
    rx, ry = ox + 100, oy + 18
    r5 = sh.part('R5', rx, ry + 14, **LEFT)
    sh.power('+3V3', *r5.p(1))
    r6 = sh.part('R6', rx - 9, ry + 19, rot=90, **ACROSS)
    sh.wire(r6.p(1), (rx - 16, ry + 19))
    sh.glabel('ENC_DO_MCU', rx - 16, ry + 19, 180, 'output')
    sh.wire(r5.p(2), (rx, ry + 19))
    sh.wire(r6.p(2), (rx + 7, ry + 19))
    sh.glabel('ENC_DO', rx + 7, ry + 19, 0, 'bidirectional')
    sh.note(
        ox + 68, oy + 43,
        'Select (A1 A0): 00 = ENC1, 01 = ENC2, 10 = ENC3, 11 = ENC4.',
        '   One encoder is always selected; step 00, 01, 11, 10.',
        'Unused half of U6: 2E high, 2A0 / 2A1 low, outputs open.',
        'R5 pulls up the shared data line; an encoder drives it only while',
        '   selected.  R6 limits the current if two ever drive at once',
        '   or a cable is plugged in live.',
        'ENC_CLK and ENC_DO have test pads (TP13, TP14, box below).')


def ports_block(sh, ox, oy):
    sh.frame(ox, oy, ox + 148, oy + 50, 'Encoder ports ENC1-ENC4 (JST-XH, MT6701 in SSI mode)')
    top, bot = oy + 13, oy + 43
    xs = []
    for n in range(1, 5):
        j = sh.part(f'J2{n}', ox + 30 + 34 * (n - 1), oy + 24,
                    ref=(2.2, -1, 'l'), val=(2.2, 1, 'l'))
        x, y = j.p(1)
        sh.wire((x, y), (x - 4, y), (x - 4, top))
        # ground column on the left, with the socket's own 100n at its top
        x, y = j.p(2)
        xs.append(x)
        c = sh.part(f'C{n}7', x - 20, top + 3)
        sh.wire(c.p(2), (x - 20, bot))
        sh.wire((x, y), (x - 20, y))
        # clock: round the other two flags and down through the socket's own
        # series resistor.  The flag on the way only names the net.
        x, y = j.p(3)
        r = sh.part(f'R{n}2', x - 16, oy + 35, rot=180)
        sh.wire((x, y), (x - 16, y), r.p(2))
        sh.wire((x - 16, oy + 31), (x - 14, oy + 31))
        sh.glabel(net_of(j.ref, 3), x - 14, oy + 31, 0, 'passive')
        sh.wire(r.p(1), (x - 16, oy + 40), (x - 14, oy + 40))
        sh.glabel('ENC_CLK', x - 14, oy + 40, 0, 'input')
        for pin in (4, 5):
            x, y = j.p(pin)
            name = net_of(j.ref, pin)
            sh.wire((x, y), (x - 4, y))
            sh.glabel(name, x - 4, y, 180, 'output' if name == 'ENC_DO' else 'input')
    sh.wire((xs[0] - 20, top), (xs[-1] - 4, top))
    sh.power('+3V3', xs[0] - 12, top)
    sh.wire((xs[0] - 20, bot), (xs[-1] - 20, bot))
    sh.power('GND', xs[0] - 12, bot)
    sh.note(
        ox + 22, oy + 5.6,
        'Pin 1 +3V3, 2 GND, 3 CLK, 4 DO, 5 CSN.  Each socket has its own clock series resistor (Rn2) and its own 100n (Cn7).',
        '   DO is shared; CSn (from U6) picks the encoder that answers.  An axis with no encoder plugged in runs open loop.')


def i2c_block(sh, ox, oy):
    sh.frame(ox, oy, ox + 160, oy + 66, 'I2C (Qwiic in and out) and status LED')
    Y = oy + 30
    j3 = sh.part('J3', ox + 16, Y, rot=180, ref=(-5.6, -1, 'r'), val=(-5.6, 1, 'r'))
    j4 = sh.part('J4', ox + 92, Y, mirror='x', ref=(5.6, -1, 'l'), val=(5.6, 1, 'l'))
    for pin in (2, 3, 4):
        sh.wire(j3.p(pin), j4.p(pin))
    for j, s in ((j3, 1), (j4, -1)):        # pin 1 and the shell pins to ground
        x, y = j.p(1)
        mx, my = j.p('MP')
        sh.wire((x, y), (x + 2 * s, y), (x + 2 * s, y + 4), (mx - 4 * s, y + 4),
                (mx - 4 * s, my - 2), (mx, my - 2), (mx, my))
        sh.power('GND', mx, y + 4)
    scl, sda, v = j3.p(4)[1], j3.p(3)[1], j3.p(2)[1]
    # pull-up footprints (not fitted)
    r1 = sh.part('R1', ox + 54, sda - 11, **LEFT)
    r2 = sh.part('R2', ox + 68, scl - 9, **RIGHT)
    sh.wire((r1.x, sda), r1.p(2))
    sh.wire((r2.x, scl), r2.p(2))
    sh.wire(r1.p(1), (r1.x, scl - 14), (r2.x, scl - 14), r2.p(1))
    sh.power('+3V3', ox + 61, scl - 14)
    sh.wire((r1.x, sda - 6), (r1.x - 8, sda - 6))
    sh.glabel('SDA', r1.x - 8, sda - 6, 180, 'bidirectional')
    sh.wire((r2.x, scl - 4), (r2.x + 8, scl - 4))
    sh.glabel('SCL', r2.x + 8, scl - 4, 0, 'bidirectional')
    # Qwiic 3V3 pin: only joined to +3V3 if the jumper is fitted
    sh.wire((ox + 28, v), (ox + 28, v + 4))
    sh.glabel('QWIIC_3V3', ox + 28, v + 4, 0, 'passive')
    jp = sh.part('JP1', ox + 54, v + 12, ref=(2.2, -0.2, 'l'), val=(2.2, 1.8, 'l'))
    sh.wire((ox + 46, v), (ox + 46, v + 12), jp.p(1))
    sh.wire(jp.p(2), (ox + 42, jp.p(2)[1]), (ox + 42, v + 10))
    sh.power('+3V3', ox + 42, v + 10)
    # status LED
    d3 = sh.part('D3', ox + 132, Y + 2, ref=(-1.5, -7.4, 'r'), val=(-1.5, -5.6, 'r'))
    x, y = d3.p(4)
    sh.wire((x, y), (x - 4, y))
    sh.glabel('LED_DATA', x - 4, y, 180, 'input')
    sh.nc(d3.p(2))
    x, y = d3.p(1)
    sh.wire((x, y), (x, y - 6))
    sh.power('+3V3', x, y - 6)
    c2 = sh.part('C2', x + 10, y - 1)
    sh.wire((x, y - 4), (x + 10, y - 4))
    gy = d3.p(3)[1] + 2
    sh.wire(d3.p(3), (x, gy), (x + 10, gy), c2.p(2))
    sh.power('GND', x + 5, gy)
    sh.note(
        ox + 3, oy + 51,
        'As on Node v2: Qwiic carries GND, SDA and SCL only.  JP1 (QWIIC_PWR) stays open, so the 3V3 wire of the',
        '   cables is not driven from here.  R1 / R2 are footprints only (not fitted): the pull-ups are on the Central.',
        "D3 runs from 3.3 V on purpose, as on Node v2: below the part's 3.5 V minimum, but it works there.",
        '   Move its VDD to +5V if a batch misbehaves.  SDA and SCL also have test pads (TP10, TP11).')


def testpoint_block(sh, ox, oy):
    sh.frame(ox, oy, ox + 148, oy + 52, 'Test points and mounting holes')
    y = oy + 18
    for i, (ref, name) in enumerate((('TP1', '+12V'), ('TP3', '+5V'),
                                     ('TP4', '+3V3'))):
        x = ox + 12 + 14 * i
        tp = sh.part(ref, x, y, rot=180, ref=(0, 5.6, 'c'), val=(0, 7.4, 'c'))
        sh.wire((x, y - 4), tp.p(1))
        sh.power(name, x, y - 4)
    tp = sh.part('TP2', ox + 54, y + 5, ref=(2.4, -3.6, 'l'), val=(2.4, -1.8, 'l'))
    sh.power('GND', *tp.p(1))
    for i, ref in enumerate(('TP5', 'TP10', 'TP11')):
        yy = oy + 12 + 5 * i
        tp = sh.part(ref, ox + 96, yy, rot=270, ref=(4.6, 0, 'l'), val=(10, 0, 'l'))
        sh.wire((ox + 90, yy), tp.p(1))
        sh.glabel(net_of(ref), ox + 90, yy, 180, 'passive')
    for i, ref in enumerate(('TP13', 'TP14')):          # the encoder bus
        yy = oy + 12 + 5 * i
        tp = sh.part(ref, ox + 130, yy, rot=270, ref=(4.6, 0, 'l'), val=(9.6, 0, 'l'))
        sh.wire((ox + 124, yy), tp.p(1))
        sh.glabel(net_of(ref), ox + 124, yy, 180, 'passive')
    sh.note(
        ox + 3, oy + 30.5,
        f'TP6-TP9 and TP12 (VM1, VCP, V3P3 and nFAULT of driver 1, and a ground pad beside them) are on page {DRIVERS_PAGE},',
        '   in the Motor 1 box.')
    for i in range(1, 5):
        sh.part(f'H{i}', ox + 10 + 14 * (i - 1), oy + 43,
                ref=(2.6, -1, 'l'), val=(2.6, 1, 'l'))
    sh.note(ox + 64, oy + 42, 'H1-H4: 3.0 mm holes, same pattern as the Node board.')


def system_page(sh):
    power_block(sh, 9, 10)
    mcu_block(sh, 9, 74)
    i2c_block(sh, 9, 156)
    decoder_block(sh, 172, 10)
    ports_block(sh, 172, 74)
    testpoint_block(sh, 172, 128)


# =================================================================== checks
def drawn_nets(sheets):
    """The nets the drawing makes, {name: set of (ref, pin)}, named the way
    KiCad will name them, and a list of the faults found on the way."""
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def join(a, b):
        parent[find(a)] = find(b)

    problems = []
    for sh in sheets:
        sh.tidy_wires()
        touched = {}
        for a, b in sh.segs:
            join((sh.name, a), (sh.name, b))
            touched[a] = touched.get(a, 0) + 1
            touched[b] = touched.get(b, 0) + 1
        for part in sh.parts:
            for n in part.lib.pins:
                pt = part.p(n)
                if any(abs(c - round(c)) > 1e-6 for c in pt):
                    problems.append(f'{part.ref}.{n} is off the grid at {pt}')
                touched[pt] = touched.get(pt, 0) + 1
                join((sh.name, pt), ('pin', part.ref, n))
                if part.ref.startswith('#PWR'):
                    join((sh.name, pt), ('global', part.lib.lib_id.split(':')[1]))
        for kind, name, pt in sh.labels:
            on = [s for s in sh.segs
                  if min(s[0][0], s[1][0]) <= pt[0] <= max(s[0][0], s[1][0])
                  and min(s[0][1], s[1][1]) <= pt[1] <= max(s[0][1], s[1][1])]
            if len(on) != 1:
                problems.append(f'{sh.name}: label {name} at {pt} sits on '
                                f'{len(on)} wires (wants exactly one)')
                continue
            if kind == 'global' and pt not in on[0]:
                problems.append(f'{sh.name}: flag {name} at {pt} not at a wire end')
            if kind == 'local' and not sh.root:
                problems.append(f'{sh.name}: plain label {name} off the root sheet')
            touched[pt] = touched.get(pt, 0) + 1
            join((sh.name, on[0][0]),
                 ('global', name) if kind == 'global' else (sh.name + ':local', name))
        for pt in sh.ncs:
            touched[pt] = touched.get(pt, 0) + 1
        wire_ends = {p for s in sh.segs for p in s}
        for pt, count in touched.items():
            if count < 2 and pt in wire_ends:
                problems.append(f'{sh.name}: wire end at {pt} joins nothing')
    groups = {}
    for node in list(parent):
        groups.setdefault(find(node), []).append(node)
    nets = {}
    for members in groups.values():
        pins = {(m[1], m[2]) for m in members if m[0] == 'pin' and m[1][0] != '#'}
        names = {m[1] for m in members
                 if m[0] == 'global' or m[0].endswith(':local')}
        if len(names) > 1:
            problems.append(f'nets shorted together: {sorted(names)}')
        if pins:
            nets[names.pop() if names else 'unnamed ' + str(sorted(pins))] = pins
    return nets, problems


def check_drawing(sheets):
    nets, problems = drawn_nets(sheets)
    missing = sorted(set(COMP) - set(PLACED))
    if missing:
        problems.append(f'not drawn: {missing}')
    want = {n: {(r, p) for r, p in pins if not r.startswith('#')}
            for n, pins in spec.NETS.items()}
    nc = set(spec.NO_CONNECT)
    marked = {(part.ref, n) for sh in sheets for part in sh.parts
              for n in part.lib.pins if part.p(n) in sh.ncs}
    if marked != nc:
        problems.append(f'no-connect flags: missing {sorted(nc - marked)}, '
                        f'extra {sorted(marked - nc)}')
    for name in sorted(set(want) | set(nets)):
        w, g = want.get(name, set()), nets.get(name, set())
        if not name.startswith('unnamed'):
            if w != g:
                problems.append(f'net {name}: missing {sorted(w - g)}, '
                                f'extra {sorted(g - w)}')
        elif len(g) > 1:
            problems.append(f'unnamed net joins {sorted(g)}')
        else:
            (ref, pin), = g
            if ((ref, pin) not in nc and
                    libsym(COMP[ref]['symbol']).pins[pin][5] != 'no_connect'):
                problems.append(f'{ref}.{pin} is not connected')
    return problems


def lint(sheets):
    """Rough look for the drawing faults a rule check cannot see: a wire
    through a symbol or over text, text on text, anything off the page.
    Text sizes are estimates, so this only says where to look."""
    found = []

    def hits(a, b, box, grow=0.0):
        x0, y0, x1, y1 = box
        return (min(a[0], b[0]) < x1 + grow and max(a[0], b[0]) > x0 - grow
                and min(a[1], b[1]) < y1 + grow and max(a[1], b[1]) > y0 - grow)

    def step(a, b):
        """a moved one unit towards b."""
        return (a[0] + (b[0] > a[0]) - (b[0] < a[0]),
                a[1] + (b[1] > a[1]) - (b[1] < a[1]))

    for sh in sheets:
        strokes = list(sh.segs)                 # wires and pin strokes
        for part in sh.parts:
            for n, (px, py, ang, length, _, _) in part.lib.pins.items():
                dx, dy = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}[ang]
                ex, ey = turn(px + dx * length, py + dy * length,
                              part.rot, part.mirror)
                strokes.append((part.p(n), (part.x + ex, part.y + ey)))
        for part in sh.parts:
            x0, y0, x1, y1 = part.body()
            if x1 - x0 < 0.1 and y1 - y0 < 0.1:
                continue
            if x0 < 9 or y0 < 9 or x1 > PAGE_W - 9 or y1 > PAGE_H - 9:
                found.append(f'{sh.name}: {part.ref} is off the page')
            pins = {part.p(n) for n in part.lib.pins}
            for a, b in sh.segs:
                a2 = step(a, b) if a in pins else a
                b2 = step(b, a) if b in pins else b
                if hits(a2, b2, (x0 + 0.3, y0 + 0.3, x1 - 0.3, y1 - 0.3)):
                    found.append(f'{sh.name}: wire {a}-{b} runs through {part.ref}')
            for what, *box in sh.texts:
                if (not what.startswith(('text', 'sheet')) and
                        hits(box[:2], box[2:], (x0, y0, x1, y1), -0.2)):
                    found.append(f'{sh.name}: {what} overlaps the body of {part.ref}')
        for i, (what, *box) in enumerate(sh.texts):
            x0, y0, x1, y1 = box
            if x0 < 8.5 or y0 < 8.5 or x1 > PAGE_W - 8.5 or y1 > PAGE_H - 8.5:
                found.append(f'{sh.name}: {what} is off the page')
            for a, b in strokes:
                if hits(a, b, (x0 + 0.15, y0 + 0.15, x1 - 0.15, y1 - 0.15)):
                    found.append(f'{sh.name}: {what} is crossed by line {a}-{b}')
            for what2, *box2 in sh.texts[i + 1:]:
                if hits(box[:2], box[2:], box2, -0.1):
                    found.append(f'{sh.name}: {what} overlaps {what2}')
    return found


# ===================================================================== main
def build():
    root = Sheet('Motor drivers', ROOT_FILE,
                 'BLDC driver board: motor drivers M1-M4', DRIVERS_PAGE,
                 '/' + ROOT_UUID)
    sub = Sheet(SUB_NAME, SUB_FILE,
                'BLDC driver board: power, MCU, encoders, I2C', SYSTEM_PAGE,
                '/' + ROOT_UUID + '/' + unq(uid('sheet', SUB_FILE)))
    drivers_page(root, sub)
    system_page(sub)
    # The PCB is linked to this schematic.  Power symbols are numbered in the
    # order they are drawn and their UUIDs follow from the number, so anything
    # added later that needs one is drawn here, after everything else: the
    # existing #PWR numbers then stay as they were.
    channel1_ground_pad(root, *channel_centre(*CELLS[1]))
    return [root, sub]


def run(*cmd):
    shown = [os.path.basename(cmd[0])] + [
        os.path.relpath(c, HERE) if c.startswith(HERE) else c for c in cmd[1:]]
    print('$', ' '.join(shown), flush=True)
    return subprocess.run(cmd, cwd=HERE).returncode


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'write'
    sheets = build()
    problems = check_drawing(sheets)
    for p in problems:
        print('ERROR', p)
    if problems:
        raise SystemExit('the drawing does not match design_spec.py; nothing written')
    for p in lint(sheets):
        print('look at:', p)
    for sh in sheets:
        sh.write('Generated by gen_schematic.py from design_spec.py')
        print(f'wrote {sh.filename}: page {sh.page}, {len(sh.parts)} symbols, '
              f'{len(sh.segs)} wire segments')
        if os.path.exists(os.path.join(HERE, '~' + sh.filename + '.lck')):
            print(f'NOTE: KiCad has {sh.filename} open (lock file).  Close it '
                  'there WITHOUT saving and open it again, or the copy in the '
                  'open window overwrites this one when it is saved.')
    if mode not in ('check', 'export'):
        return
    out = os.path.join(HERE, 'build', 'sch')
    os.makedirs(os.path.join(out, 'svg'), exist_ok=True)
    run(KICAD_CLI, 'sch', 'erc', '--format', 'json', '--severity-all',
        '-o', os.path.join(out, 'erc.json'), ROOT_FILE)
    with open(os.path.join(out, 'erc.json')) as f:
        erc = [v for s in json.load(f)['sheets'] for v in s['violations']]
    for v in erc:
        print('ERC', v['severity'], v['type'], v['description'],
              [i['description'] for i in v['items']])
    run(KICAD_CLI, 'sch', 'export', 'netlist', '--format', 'kicadsexpr',
        '-o', os.path.join(out, 'netlist.net'), ROOT_FILE)
    ok = run(sys.executable, 'design_spec.py', 'check',
             os.path.join(out, 'netlist.net')) == 0 and not erc
    if mode == 'export':
        os.makedirs(os.path.join(HERE, 'output'), exist_ok=True)
        run(KICAD_CLI, 'sch', 'export', 'pdf',
            '-o', os.path.join(HERE, 'output', 'schematic.pdf'), ROOT_FILE)
        run(KICAD_CLI, 'sch', 'export', 'svg', '-o', os.path.join(out, 'svg'),
            ROOT_FILE)
        for sh in sheets:
            svg = PROJECT + ('' if sh.root else '-' + sh.name) + '.svg'
            run(RSVG, '-w', '4960', '-b', 'white', os.path.join(out, 'svg', svg),
                '-o', os.path.join(HERE, 'output', f'schematic_p{sh.page}.png'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
