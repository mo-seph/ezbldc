"""Lay out the BLDC driver board from design_spec.py: footprints and nets,
stackup, outline, placement, driver-cell routing, power copper, planes,
keep-outs, silkscreen.

Run with KiCad's own Python (it needs pcbnew):

    KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $KPY tools/build_board.py            # everything
    $KPY tools/build_board.py place      # placement and outline only

then `python3 tools/autoroute.py` for the logic nets.

It builds the board from nothing every time and OVERWRITES
bldc_driver_board.kicad_pcb. Anything routed by hand or by the autorouter
is lost on a re-run. (Nothing is ever removed from a loaded board: doing
that through pcbnew's Python API leaves it handing back unusable objects.)

The board does not need the schematic to be built, but if a current KiCad
netlist is at build/netlist.net, link_schematic() ties each footprint to
its symbol and takes KiCad's own net names, so that KiCad sees board and
schematic as one design.

Coordinates in this file are the BOARD FRAME: millimetres, origin at the
lower-left corner of the board, x right, y up. That is the frame of the
Node board's Gerbers, so jack, Qwiic and hole positions can be compared
directly. to_k() converts to KiCad's page coordinates (y down).
"""
import json
import math
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
sys.path.insert(0, PRJ)
import design_spec as spec      # noqa: E402

PCB = os.path.join(PRJ, 'bldc_driver_board.kicad_pcb')
PRO = os.path.join(PRJ, 'bldc_driver_board.kicad_pro')
PRL = os.path.join(PRJ, 'bldc_driver_board.kicad_prl')
NETLIST = os.path.join(PRJ, 'build', 'netlist.net')
SYSFP = '/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints'

W, H = 80.0, 62.05          # Node board: 80.000 x 62.055
CORNER_R = 4.4
OX, OY = 100.0, 100.0 + H   # KiCad page position of the board's lower-left
HOLES = [(4, 4), (76, 4), (4, 58), (76, 58)]

mm = pcbnew.FromMM
F, B, IN1, IN2 = pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu


def to_k(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY - y))


# ------------------------------------------------------------- placement
CELL_X = {1: 21.4, 2: 33.8, 3: 46.2, 4: 58.6}     # driver cell centres
CELL_Y = 29.2

PLACE = {       # ref: (x, y, KiCad rotation in degrees)
    'U1': (40.0, 10.5, 270),            # XIAO, USB at the bottom edge
    'J1': (7.62, 45.72, 0),             # 12V_IN,  same place as the Node
    'J2': (72.39, 45.72, 180),          # 12V_OUT, same place as the Node
    'J3': (3.2, 31.75, 270),            # I2C_IN,  same height as the Node
    'J4': (76.8, 30.48, 90),            # I2C_OUT, same height as the Node
    'H1': (4, 4, 0), 'H2': (76, 4, 0), 'H3': (4, 58, 0), 'H4': (76, 58, 0),
    'D1': (11.3, 53.0, 0),              # reverse-polarity diode, K left
    'D4': (11.3, 56.9, 0),              # 12 V clamp, K left
    'C3': (68.9, 56.6, 90),             # input bulk, + pad down
    'U7': (9.5, 13.0, 90),              # 5 V module: pins 1-2-3 upward, body left
    'C4': (9.0, 8.2, 0),
    'C5': (10.5, 22.9, 0),              # above the module: both sides of its
                                        # pin row stay clear for the body
    'D2': (25.3, 4.6, 90),              # cathode down, next to the XIAO 5V pad
    'C6': (28.3, 6.69, 270),            # 3V3 bulk at the XIAO's 3V3 / GND pads
    'U6': (67.5, 15.0, 0),
    'C1': (67.5, 21.6, 180),
    'R3': (56.0, 8.9, 0),
    'R5': (56.7, 13.1, 180),            # 0.7 mm right of R3: SDA's via is at its left
    'R6': (52.2, 14.31, 0),             # DO series resistor, at the XIAO's pad
    'D3': (54.4, 18.2, 180),
    'C2': (59.6, 17.0, 90),
    'JP1': (70.5, 37.5, 0),
    'R1': (69.5, 27.0, 180),            # SDA / SCL pads on the left,
    'R2': (69.5, 24.9, 180),            # next to their test pads
    # test pads: supplies and enable, bottom left
    'TP1': (10.0, 3.2, 0), 'TP2': (13.0, 3.2, 0), 'TP3': (16.0, 3.2, 0),
    'TP4': (19.0, 3.2, 0), 'TP5': (22.0, 3.2, 0),
    # channel 1's key nodes, beside driver 1
    'TP6': (9.5, 37.0, 0), 'TP7': (12.5, 37.0, 0),
    'TP8': (9.5, 33.5, 0), 'TP9': (12.5, 33.5, 0),
    # I2C, beside the pull-up footprints
    'TP10': (66.3, 27.4, 0), 'TP11': (66.3, 24.5, 0),
    # a ground pad beside the channel-1 pads; the encoder bus, right edge
    'TP12': (12.5, 30.6, 0), 'TP13': (77.2, 22.6, 0), 'TP14': (77.2, 18.6, 0),
}

# parts of one driver cell, relative to the driver's centre: (u, v, rotation)
# Bottom to top: fault LED row, DRV8313, decoupling, bulk cap (on the left,
# over pin 11's supply, clear of the phases), then the connector zone on the
# board edge: encoder socket (left) and motor header (right) side by side,
# the fuse under the header, the encoder's two passives in the strip to the
# right of the header. The three phase traces run straight up the middle.
XH_U = -2.4         # encoder socket's pin column
CELL = {
    'U':  (0.0, 0.0, 270),      # pins 1-14 (power, outputs) on top, 15-28 below
    'C1': (6.2, 3.3, 90),       # charge-pump flying cap, off the pin-1 end
    'C2': (3.0, 5.4, 180),      # VCP-VM
    'C3': (3.0, 7.5, 0),        # VM decoupling at pin 4
    'C4': (-3.225, 5.0, 180),   # VM decoupling at pin 11
    'C5': (-2.45, 11.45, 90),   # bulk, turned on end, + pad down onto C4's VM
    'C6': (-6.2, -1.3, 90),     # V3P3 cap, off the pin-15 end, V3P3 pad down
    'F':  (3.3, 19.2, 90),      # polyfuse, +12V pad down, VM pad up
    'J':  (2.6, 24.6, 180),     # motor header, pin 1 at the bottom
    'E':  (XH_U, 29.3, 270),    # encoder socket, pin 1 (3V3) at the top
    'R2': (5.25, 24.2, 90),     # encoder clock series resistor, bus pad down
    'C7': (5.25, 27.6, 90),     # encoder 3V3 decoupling, +3V3 pad down
    'D':  (-1.6, -6.55, 180),   # fault LED, cathode right
    'R':  (-5.3, -6.55, 0),     # its resistor
}
for n, cx in CELL_X.items():
    names = {'U': f'U{n + 1}', 'C1': f'C{n}1', 'C2': f'C{n}2', 'C3': f'C{n}3',
             'C4': f'C{n}4', 'C5': f'C{n}5', 'F': f'F{n}', 'J': f'J1{n}',
             'E': f'J2{n}', 'C6': f'C{n}6', 'D': f'D{n}1', 'R': f'R{n}1',
             'R2': f'R{n}2', 'C7': f'C{n}7'}
    for k, (u, v, rot) in CELL.items():
        PLACE[names[k]] = (cx + u, CELL_Y + v, rot)

FIDUCIALS = [(6.0, 8.1), (74.0, 8.4), (4.4, 53.0)]     # > 3.85 mm from any edge

SILK = [        # text, x, y, size[, angle]
    ('BLDC x4 v0.4', 16.0, 6.9, 1.0),
    ('12V', 10.0, 5.2, 0.8), ('GND', 13.0, 5.2, 0.8), ('5V', 16.0, 5.2, 0.8),
    ('3V3', 19.0, 5.2, 0.8), ('EN', 22.0, 5.2, 0.8),
    ('SDA', 66.3, 29.1, 0.8), ('SCL', 66.3, 22.9, 0.8),
    ('VM1', 9.5, 38.8, 0.8), ('VCP', 12.5, 38.8, 0.8),
    ('V3P3', 9.3, 35.25, 0.8), ('FLT', 12.6, 35.25, 0.8),
    ('12V IN', 4.3, 55.2, 0.9), ('CENTRE +', 4.3, 51.1, 0.8),
    ('GND', 12.5, 28.9, 0.8), ('CLK', 77.2, 24.4, 0.8), ('DO', 77.2, 20.4, 0.8),
    ('12V OUT', 76.2, 51.6, 0.9), ('CENTRE +', 76.0, 53.1, 0.8),
    ('I2C', 8.6, 30.2, 0.9), ('I2C', 71.0, 29.5, 0.9),
    ('QWIIC PWR', 70.5, 40.1, 0.8),
    ('5V', 4.0, 22.7, 0.9),
    ('ENC  1:3V3  2:GND', 7.5, 26.2, 0.8),
    ('3:CLK  4:DO  5:CS', 7.5, 24.9, 0.8),
]
for _n, _cx in CELL_X.items():       # above the motor header, under the bracket
    SILK.append((f'M{_n}', _cx + 2.6, CELL_Y + 31.75, 0.8))

# 3D models for footprints whose library entry has none (or names a file
# KiCad does not ship): ref -> (model, offset in mm). Stand-ins with the
# right body size, for the STEP export.
KI3D = '${KICAD10_3DMODEL_DIR}/'
MODELS = {
    'U1': ('${KIPRJMOD}/lib/bldc.3dshapes/XIAO-ESP32-S3-Plus.step', (0, 0, 0)),
    'J1': (KI3D + 'Connector_BarrelJack.3dshapes/BarrelJack_Horizontal.step',
           (6, 0, 0)),          # stock model's origin is the rear (centre) pin
    'J2': (KI3D + 'Connector_BarrelJack.3dshapes/BarrelJack_Horizontal.step',
           (6, 0, 0)),
    # the fitted part is a TO-220 7805 (tab towards the module outline's
    # deep side); the footprint's own model is the switching module
    'U7': (KI3D + 'Package_TO_SOT_THT.3dshapes/TO-220-3_Vertical.step',
           (0, 0, 0)),
}
for _n in range(1, 5):
    MODELS[f'U{_n + 1}'] = (KI3D + 'Package_SO.3dshapes/'
                            'HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.5mm.step',
                            (0, 0, 0))
    MODELS[f'F{_n}'] = (KI3D + 'Resistor_SMD.3dshapes/R_1812_4532Metric.step',
                        (0, 0, 0))


# ------------------------------------------------------------- primitives
class Builder:
    def __init__(self, board):
        self.b = board
        self.nets = {}

    def net(self, name):
        return self.nets[name]

    def track(self, net, pts, width, layer=F):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(to_k(x1, y1))
            t.SetEnd(to_k(x2, y2))
            t.SetWidth(mm(width))
            t.SetLayer(layer)
            t.SetNet(self.net(net))
            self.b.Add(t)

    def via(self, net, x, y, dia=0.6, drill=0.3):
        v = pcbnew.PCB_VIA(self.b)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(F, B)
        v.SetPosition(to_k(x, y))
        v.SetWidth(F, mm(dia))
        v.SetDrill(mm(drill))
        v.SetNet(self.net(net))
        self.b.Add(v)

    def _outline(self, z, pts):
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            p = to_k(x, y)
            ol.Append(p.x, p.y)

    def zone(self, net, layer, pts, priority=0, solid=False, clearance=0.25):
        z = pcbnew.ZONE(self.b)
        z.SetLayer(layer)
        z.SetNet(self.net(net))
        z.SetAssignedPriority(priority)
        z.SetLocalClearance(mm(clearance))
        z.SetMinThickness(mm(0.25))
        z.SetThermalReliefGap(mm(0.3))
        z.SetThermalReliefSpokeWidth(mm(0.5))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if solid
                           else pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        self._outline(z, pts)
        self.b.Add(z)
        return z

    def keepout(self, layer, pts, name, tracks=True, vias=True):
        """Rule area: no tracks and/or no vias (copper pour and pads allowed)."""
        z = pcbnew.ZONE(self.b)
        z.SetIsRuleArea(True)
        z.SetLayer(layer)
        z.SetZoneName(name)
        z.SetDoNotAllowTracks(tracks)
        z.SetDoNotAllowVias(vias)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetDoNotAllowZoneFills(False)
        self._outline(z, pts)
        self.b.Add(z)

    def text(self, s, x, y, size, angle=0, layer=pcbnew.F_SilkS):
        t = pcbnew.PCB_TEXT(self.b)
        t.SetText(s)
        t.SetPosition(to_k(x, y))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(max(0.15, size * 0.15)))      # JLCPCB: 0.15 minimum
        if angle:
            t.SetTextAngleDegrees(angle)
        self.b.Add(t)

    def edge_line(self, a, b, layer=pcbnew.Edge_Cuts, width=0.05):
        s = pcbnew.PCB_SHAPE(self.b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(to_k(*a))
        s.SetEnd(to_k(*b))
        s.SetLayer(layer)
        s.SetWidth(mm(width))
        self.b.Add(s)

    def edge_arc(self, start, mid, end):
        s = pcbnew.PCB_SHAPE(self.b)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(to_k(*start), to_k(*mid), to_k(*end))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.05))
        self.b.Add(s)


# ------------------------------------------------------------- stages
def setup(board):
    board.SetCopperLayerCount(4)
    board.SetLayerName(IN1, 'In1.Cu')
    board.SetLayerName(IN2, 'In2.Cu')
    board.SetLayerType(IN1, pcbnew.LT_POWER)     # GND plane
    board.SetLayerType(IN2, pcbnew.LT_POWER)     # +3V3 plane
    ds = board.GetDesignSettings()
    ds.SetAuxOrigin(to_k(0, 0))
    ds.SetGridOrigin(to_k(0, 0))
    ds.m_CopperEdgeClearance = mm(0.4)
    ds.m_MinClearance = mm(0.15)
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_ViasMinSize = mm(0.5)
    ds.m_MinThroughDrill = mm(0.3)
    ds.m_ViasMinAnnularWidth = mm(0.13)
    ds.m_HoleClearance = mm(0.25)
    ds.m_HoleToHoleMin = mm(0.25)


def load_fp(lib_id):
    lib, name = lib_id.split(':')
    path = (os.path.join(PRJ, 'lib', 'bldc.pretty') if lib == 'bldc'
            else os.path.join(SYSFP, lib + '.pretty'))
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise KeyError(f'footprint not found: {lib_id}')
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def populate(board, bd):
    """Footprints and nets straight from design_spec.py."""
    for name in spec.NETS:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        bd.nets[name] = n
    pin_net = {(ref, pin): name for name, pins in spec.NETS.items()
               for ref, pin in pins}
    for c in spec.COMPONENTS:
        ref = c['ref']
        if ref.startswith('#'):
            continue                    # power flags: schematic only
        fp = load_fp(c['footprint'])
        fp.SetReference(ref)
        fp.SetValue(c['value'])
        attrs = fp.GetAttributes()
        if c['dnp']:
            attrs |= pcbnew.FP_DNP
        if c['nobom']:
            attrs |= pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
        fp.SetAttributes(attrs)
        # too dense for designators on the silkscreen; they stay on F.Fab
        fp.Reference().SetVisible(False)
        if ref in MODELS:
            path, offset = MODELS[ref]
            models = fp.Models()
            models.clear()
            m = pcbnew.FP_3DMODEL()
            m.m_Filename = path
            m.m_Offset = pcbnew.VECTOR3D(*[float(v) for v in offset])
            models.push_back(m)
        board.Add(fp)
        for pad in fp.Pads():
            name = pin_net.get((ref, pad.GetNumber()))
            if name:
                pad.SetNet(bd.nets[name])
    for i, (x, y) in enumerate(FIDUCIALS, start=1):
        fp = load_fp('Fiducial:Fiducial_1mm_Mask2mm')
        fp.SetReference(f'FID{i}')
        fp.SetValue('Fiducial')
        fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_BOARD_ONLY
                         | pcbnew.FP_EXCLUDE_FROM_BOM
                         | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        fp.Reference().SetVisible(False)
        board.Add(fp)
        PLACE[f'FID{i}'] = (x, y, 0)


def outline(bd):
    r = CORNER_R
    k = r * (1 - math.sqrt(0.5))        # arc midpoint inset from the corner
    bd.edge_line((r, 0), (W - r, 0))
    bd.edge_line((W, r), (W, H - r))
    bd.edge_line((W - r, H), (r, H))
    bd.edge_line((0, H - r), (0, r))
    bd.edge_arc((0, r), (k, k), (r, 0))
    bd.edge_arc((W - r, 0), (W - k, k), (W, r))
    bd.edge_arc((W, H - r), (W - k, H - k), (W - r, H))
    bd.edge_arc((r, H), (k, H - k), (0, H - r))


def place(board):
    seen = set()
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref not in PLACE:
            raise KeyError(f'{ref} has no position in PLACE')
        x, y, rot = PLACE[ref]
        fp.SetPosition(to_k(x, y))
        fp.SetOrientationDegrees(rot)
        seen.add(ref)
    missing = set(PLACE) - seen
    if missing:
        raise KeyError(f'not on the board: {sorted(missing)}')
    # the jacks carry the daisy-chain current: solid plane connections
    for ref in ('J1', 'J2'):
        for pad in board.FindFootprintByReference(ref).Pads():
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    # the 5 V module's ground pin has tracks close on two sides, which
    # starves a thermal relief: connect it solidly
    for pad in board.FindFootprintByReference('U7').Pads():
        if pad.GetNumber() == '2':
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    # the drivers' exposed pads and their thermal vias: solid into every
    # ground layer (thermal reliefs there would defeat the point)
    for n in CELL_X:
        for pad in board.FindFootprintByReference(f'U{n + 1}').Pads():
            if pad.GetNumber() == '29':
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    # the XIAO is fitted by hand: keep it out of the pick-and-place file
    u1 = board.FindFootprintByReference('U1')
    u1.SetAttributes(u1.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_POS_FILES)


def route_cell(bd, n):
    cx, y0 = CELL_X[n], CELL_Y
    P = f'M{n}_'
    VM = f'VM{n}'

    def tr(net, pts, w, layer=F):
        bd.track(net, [(cx + u, y0 + v) for u, v in pts], w, layer)

    def via(net, u, v):
        bd.via(net, cx + u, y0 + v)

    # charge pump: flying cap off the end of the row, VCP cap above pins 3-4
    tr(P + 'CPL', [(4.225, 2.6), (6.2, 2.6)], 0.25)
    tr(P + 'CPH', [(3.575, 3.3), (3.575, 4.25), (6.2, 4.25)], 0.25)
    tr(P + 'VCP', [(2.925, 3.3), (2.925, 5.4), (3.95, 5.4)], 0.25)

    # VM, right-hand half: fuse (top pad) -> down the right-hand edge ->
    # C3 -> C2 -> pin 4, on the top layer
    tr(VM, [(4.7, 21.34), (5.3, 21.34), (5.7, 20.94), (5.7, 9.7), (5.3, 9.3),
            (2.05, 9.3), (2.05, 7.5)], 0.8)
    tr(VM, [(2.05, 7.5), (2.05, 5.4)], 0.6)
    tr(VM, [(2.275, 3.3), (2.275, 5.2)], 0.3)
    # VM, left-hand half: pin 11 -> C4 -> straight up into the bulk cap's +
    # pad, which sits right above it
    tr(VM, [(-2.275, 3.3), (-2.275, 4.8)], 0.3)
    tr(VM, [(-2.275, 5.0), (-2.275, 7.4)], 0.8)
    # the two halves are joined underneath (the phases run between them on
    # top): two vias at each end, a 0.8 mm track on the bottom layer
    for v in (8.0, 9.0):
        tr(VM, [(-3.0, v), (-3.9, v)], 0.5)
        via(VM, -3.9, v)
    for u in (3.2, 4.2):
        via(VM, u, 9.3)
    tr(VM, [(-3.9, 8.0), (-3.9, 9.0), (-3.6, 9.3), (4.2, 9.3)], 0.8, B)

    # +12V into the fuse's lower pad, from the bottom-layer supply strip
    for u in (2.4, 4.2):
        tr('+12V', [(u, 16.8), (u, 15.9)], 0.5)
        via('+12V', u, 15.9)

    # ground: power grounds into the exposed pad, signal grounds to vias
    for u in (0.975, 0.325, -1.625):
        tr('GND', [(u, 2.862), (u, 1.0)], 0.3)
    for u in (-1.625, -0.975):
        tr('GND', [(u, -2.862), (u, -1.0)], 0.3)
    tr('GND', [(-4.225, 2.862), (-2.925, 2.862)], 0.3)
    tr('GND', [(-4.225, 3.3), (-4.225, 4.7)], 0.3)
    tr('GND', [(-4.175, 5.0), (-4.175, 6.45)], 0.5)
    via('GND', -4.175, 6.45)
    tr('GND', [(3.95, 7.5), (5.25, 7.5)], 0.5)
    via('GND', 5.25, 7.5)
    for u in (-2.9, -2.0):          # bulk cap's - pad: vias between its pads
        tr('GND', [(u, 12.6), (u, 11.45)], 0.5)
        via('GND', u, 11.45)
    tr('GND', [(4.225, -3.3), (4.225, -5.4)], 0.25)
    via('GND', 4.225, -5.4)
    tr('GND', [(-6.2, -0.35), (-6.2, 0.95)], 0.5)
    via('GND', -6.2, 0.95)

    # Phases: 0.3 mm for the first millimetre off the 0.65 mm-pitch pins,
    # then three 0.65 mm traces (0.25 mm apart) straight up the middle of
    # the cell to the header: between C4 / the bulk cap on the left and
    # C2 / C3 on the right, then between the encoder socket's pins and the
    # fuse. 0.65 mm is what that 3.05 mm corridor allows.
    PW = 0.65
    tr(P + 'OUT1', [(1.625, 3.3), (1.625, 3.75), (0.95, 4.425)], 0.3)
    tr(P + 'OUT1', [(0.95, 4.425), (0.95, 22.95), (2.6, 24.6)], PW)
    tr(P + 'OUT2', [(-0.325, 3.3), (-0.325, 3.8), (0.05, 4.175)], 0.3)
    tr(P + 'OUT2', [(0.05, 4.175), (0.05, 24.59), (2.6, 27.14)], PW)
    tr(P + 'OUT3', [(-0.975, 3.3), (-0.975, 4.15), (-0.85, 4.275)], 0.3)
    tr(P + 'OUT3', [(-0.85, 4.275), (-0.85, 26.23), (2.6, 29.68)], PW)

    # Encoder socket passives, in the strip right of the motor header.
    # Clock: bus on the bottom layer -> via -> Rn2 -> via -> under the
    # header (between its pins 1 and 2) and the phases -> socket pin 3.
    E = f'ENC{n}_CLK'
    via('ENC_CLK', 4.2, 23.05)
    tr('ENC_CLK', [(4.2, 23.05), (4.525, 23.375), (5.25, 23.375)], 0.2)
    tr(E, [(5.25, 25.025), (4.405, 25.87), (4.25, 25.87)], 0.2)
    via(E, 4.25, 25.87)
    tr(E, [(4.25, 25.87), (1.2, 25.87), (0.88, 25.55), (-1.0, 25.55),
           (-2.25, 24.3), (XH_U, 24.3)], 0.2, B)
    # Decoupling: straight into the planes
    tr('+3V3', [(5.25, 26.825), (4.3, 26.825)], 0.3)
    via('+3V3', 4.3, 26.825)
    tr('GND', [(5.25, 28.375), (4.3, 28.375)], 0.3)
    via('GND', 4.3, 28.375)

    # +3V3: a bar under the body ties EN1-3, leaves round the pin-28 end
    tr('+3V3', [(0.325, -2.5), (0.325, -1.77), (4.95, -1.77), (4.95, -4.3)],
       0.2)
    tr('+3V3', [(1.625, -2.5), (1.625, -1.77)], 0.2)
    tr('+3V3', [(2.925, -2.5), (2.925, -1.77)], 0.2)
    via('+3V3', 4.95, -4.3)
    tr('+3V3', [(-2.925, -3.3), (-2.925, -5.3)], 0.2)     # nSLEEP
    via('+3V3', -2.925, -5.3)
    tr('+3V3', [(-6.21, -6.55), (-7.55, -6.55)], 0.4)     # LED resistor
    via('+3V3', -7.55, -6.55)

    tr(P + 'V3P3', [(-4.225, -2.5), (-6.2, -2.5)], 0.25)
    tr(P + 'FAULT', [(-2.275, -3.3), (-2.275, -3.9), (-0.9, -5.275),
                     (-0.9, -6.2)], 0.2)
    tr(P + 'LED', [(-2.54, -6.55), (-4.39, -6.55)], 0.25)

    # shared enable (nRESET): through to the bus, which runs on the bottom
    # layer under the ICs' lower pin row. (Run below the fault LEDs it fenced
    # the bottom layer off between the XIAO and the two middle drivers.)
    tr('DRV_EN', [(-3.575, -3.3), (-3.575, -4.4)], 0.2)
    via('DRV_EN', -3.575, -4.4)
    tr('DRV_EN', [(-3.575, -4.4), (-3.575, -2.6)], 0.2, B)


# The Qwiic cable's three wires cross the board on inner 2, side by side
# in the one strip that no via touches: between the DRV8313s' exposed-pad
# vias (y 28.08) and the vias below their lower pin row (y <= 24.9). Both
# outer layers are fenced right across the board (phases and VM on top;
# enable bus, chip selects and 12 V underneath); the +3V3 plane simply
# clears round the three tracks and stays joined round both ends.
I2C_Y = {'SCL': 25.7, 'SDA': 26.4, 'QWIIC_3V3': 27.3}


def qwiic_link(bd):
    """The Qwiic 3V3 pass-through wire (J3 pin 2 to J4 pin 2 / JP1). It
    carries only what a Qwiic device on the cable would draw."""
    y = I2C_Y['QWIIC_3V3']
    bd.track('QWIIC_3V3', [(5.2, 32.25), (7.0, 32.25)], 0.3)
    bd.via('QWIIC_3V3', 7.0, 32.25)
    bd.track('QWIIC_3V3', [(7.0, 32.25), (8.6, 32.25), (8.6, y + 0.3),
                           (8.9, y), (71.7, y), (72.3, y + 0.6), (72.3, 29.3),
                           (72.98, 29.98), (73.3, 29.98)], 0.4, IN2)
    bd.via('QWIIC_3V3', 73.3, 29.98)
    bd.track('QWIIC_3V3', [(73.3, 29.98), (74.8, 29.98)], 0.3)
    # branch to the jumper JP1 (pin 1, a through-hole pad), also on inner 2
    bd.track('QWIIC_3V3', [(72.3, 29.3), (72.3, 37.0), (71.8, 37.5),
                           (70.5, 37.5)], 0.3, IN2)


def i2c_bus(bd):
    """SDA and SCL: J3 -> XIAO -> J4, on inner 2, with a via at each
    connector, at the XIAO and at the test pad / pull-up footprint.
    SDA is one straight run with a stem down to the XIAO's pad. SCL cannot
    also be a tee without crossing it, so SCL is two inner-layer pieces
    (J3 to the XIAO, the XIAO to J4) joined on the top layer, where its
    track from the XIAO's pad runs on past the first via to a second.
    (Looping SCL round the end of SDA's stem on inner 2 instead cut a
    patch of the +3V3 plane off from the rest: the plane has to be able to
    get in between the two stems' ends.)"""
    ys, yd = I2C_Y['SCL'], I2C_Y['SDA']
    w = 0.2
    # --- J3 (left): pads at x = 5.2; SCL pin 4 (y 30.25), SDA pin 3 (y 31.25)
    bd.track('SCL', [(5.2, 30.25), (7.0, 30.25)], w)
    bd.via('SCL', 7.0, 30.25)
    bd.track('SDA', [(5.2, 31.25), (7.7, 31.25)], w)
    bd.via('SDA', 7.7, 31.25)
    # --- XIAO: SCL is pad 6 (y 15.58), SDA pad 5 (y 13.04). Vias sit just
    # outside the bottom-layer PWM / enable lanes that run beside the module.
    xs, xd = 53.6, 54.3                 # the two stems
    x2, y2 = 57.0, 15.18                # SCL's second via, for the J4 half
    bd.track('SCL', [(49.5, 15.58), (xs, 15.58), (x2 - 0.4, 15.58),
                     (x2, y2)], w)
    bd.via('SCL', xs, 15.58)
    bd.via('SCL', x2, y2)
    bd.track('SDA', [(49.5, 13.04), (xd, 13.04)], w)
    bd.via('SDA', xd, 13.04)
    # --- J4 (right): pads at x = 74.8; SDA pin 3 (y 30.98), SCL pin 4 (y 31.98)
    bd.via('SDA', 73.3, 30.98)
    bd.track('SDA', [(73.3, 30.98), (74.8, 30.98)], w)
    bd.via('SCL', 73.3, 31.98)
    bd.track('SCL', [(73.3, 31.98), (74.8, 31.98)], w)
    # --- inner 2 (every via and junction is a vertex of its polyline)
    xt = 67.57                          # taps for the test pads / pull-ups
    bd.track('SDA', [(7.7, 31.25), (7.7, yd + 0.5), (8.2, yd), (xd, yd),
                     (xt, yd), (73.5, yd), (74.0, yd + 0.5), (74.0, 30.68),
                     (73.7, 30.98), (73.3, 30.98)], w, IN2)
    bd.track('SDA', [(xd, yd), (xd, 13.04)], w, IN2)
    bd.track('SCL', [(7.0, 30.25), (7.0, ys + 0.5), (7.5, ys), (xs - 0.5, ys),
                     (xs, ys - 0.5), (xs, 15.58)], w, IN2)
    bd.track('SCL', [(x2, y2), (x2, ys - 0.5), (x2 + 0.5, ys), (xt, ys),
                     (74.1, ys), (74.6, ys + 0.5), (74.6, 31.68),
                     (74.3, 31.98), (73.3, 31.98)], w, IN2)
    # --- test pads TP10 / TP11 and the (unfitted) pull-ups R1 / R2: a via
    # between the test pad and the resistor pad, onto the top-layer track
    # that joins those two (laid in route_power)
    bd.via('SDA', xt, yd)
    bd.track('SDA', [(xt, yd), (xt, 26.73), (67.3, 27.0)], w)
    bd.via('SCL', xt, 24.9)
    bd.track('SCL', [(xt, 24.9), (xt, ys)], w, IN2)


def route_power(bd):
    for n in CELL_X:
        route_cell(bd, n)
    qwiic_link(bd)
    i2c_bus(bd)
    # enable bus joining the four drivers
    y = CELL_Y - 2.6
    bd.track('DRV_EN', [(CELL_X[1] - 3.575, y), (CELL_X[4] - 3.575, y)], 0.2, B)

    # input: jack -> D1 -> +12V (four vias to the bottom-layer supply), D4
    # clamps it to ground
    # (as wide as the jack's pad: this short link carries the whole board,
    # and at 1.2 mm it was the narrowest copper on the input side)
    bd.track('12V_JACK', [(13.6, 46.0), (13.6, 52.8)], 2.2)
    bd.track('+12V', [(9.3, 53.0), (9.3, 56.9)], 1.2)
    bd.track('+12V', [(8.3, 54.95), (10.7, 54.95)], 0.8)
    for x in (8.3, 9.1, 9.9, 10.7):
        bd.via('+12V', x, 54.95)
    for x in (12.7, 13.9):
        bd.track('GND', [(x, 56.9), (x, 58.5)], 0.6)
        bd.via('GND', x, 58.5)
    # input bulk cap, top right, on the far end of the supply strip
    for y in (53.5, 54.3):
        bd.track('+12V', [(68.9, y), (67.2, y)], 0.6)
        bd.via('+12V', 67.2, y)
    for x in (67.3, 70.5):
        bd.track('GND', [(68.9, 59.3), (x, 59.3)], 0.8)
        bd.via('GND', x, 59.3)

    # 5 V module: fed down the left edge on the bottom layer
    bd.track('+12V', [(7.9, 54.95), (5.2, 52.25), (5.2, 14.2), (6.4, 13.0),
                      (9.5, 13.0)], 0.8, B)
    bd.track('+12V', [(9.5, 13.0), (8.05, 11.55), (8.05, 8.2)], 0.6)
    bd.track('GND', [(9.95, 8.2), (11.3, 8.2)], 0.5)
    bd.via('GND', 11.3, 8.2)
    bd.track('+5V', [(9.5, 18.08), (9.5, 22.9)], 0.6)
    bd.track('GND', [(11.45, 22.9), (12.8, 22.9)], 0.5)
    bd.via('GND', 12.8, 22.9)
    bd.track('+5V', [(9.5, 18.08), (10.47, 19.05), (14.6, 19.05),
                     (15.4, 18.25), (15.4, 9.6), (16.2, 8.8), (24.5, 8.8),
                     (25.3, 8.0), (25.3, 7.0)], 0.6)
    bd.track('XIAO_5V', [(25.3, 2.88), (31.3, 2.88)], 0.6)

    # XIAO supply pads, with the 3V3 bulk cap right beside them
    bd.track('+3V3', [(31.3, 7.96), (29.6, 7.96), (29.28, 7.64),
                      (28.3, 7.64)], 0.4)
    bd.track('+3V3', [(28.3, 7.64), (28.3, 9.2), (27.5, 9.2)], 0.4)
    bd.via('+3V3', 28.3, 9.2)       # the whole +3V3 plane hangs off this pad:
    bd.via('+3V3', 27.5, 9.2)       # two vias
    bd.track('GND', [(31.3, 5.42), (29.6, 5.42), (29.28, 5.74),
                     (28.3, 5.74)], 0.4)
    bd.track('GND', [(28.3, 5.74), (28.3, 4.25)], 0.4)
    bd.via('GND', 28.3, 4.25)

    # channel 1's VM test pad: from the upper via beside the bulk cap, along
    # the bottom layer (the autorouter would not route this one; its class
    # is 0.8 mm)
    bd.track('VM1', [(CELL_X[1] - 3.9, CELL_Y + 9.0), (9.2, CELL_Y + 9.0),
                     (8.0, 37.0)], 0.3, B)
    bd.via('VM1', 8.0, 37.0)
    bd.track('VM1', [(8.0, 37.0), (9.5, 37.0)], 0.3)

    # supply test pads
    bd.track('+12V', [(8.05, 8.2), (8.05, 6.9), (10.0, 4.95), (10.0, 3.2)], 0.4)
    bd.track('GND', [(13.0, 3.2), (13.0, 1.6)], 0.4)
    bd.via('GND', 13.0, 1.6)
    bd.track('+5V', [(16.4, 8.8), (16.0, 8.4), (16.0, 3.2)], 0.4)
    bd.track('+3V3', [(19.0, 3.2), (19.0, 1.6)], 0.4)
    bd.via('+3V3', 19.0, 1.6)

    # decoder
    bd.track('+3V3', [(69.975, 18.175), (69.975, 19.445), (71.75, 19.445)], 0.3)
    bd.via('+3V3', 71.75, 19.445)
    bd.track('+3V3', [(68.45, 21.6), (69.975, 20.075), (69.975, 19.445)], 0.3)
    bd.track('GND', [(66.55, 21.6), (65.025, 20.075), (65.025, 19.445),
                     (63.6, 19.445)], 0.3)
    bd.via('GND', 63.6, 19.445)
    bd.track('GND', [(65.025, 10.555), (63.6, 10.555)], 0.3)
    bd.via('GND', 63.6, 10.555)
    bd.track('GND', [(69.975, 15.635), (69.975, 16.905)], 0.3)
    bd.track('GND', [(69.975, 16.27), (71.75, 16.27)], 0.3)
    bd.via('GND', 71.75, 16.27)

    # enable pull-down, DO pull-up, status LED and its cap
    bd.track('GND', [(56.91, 8.9), (58.4, 8.9)], 0.3)
    bd.via('GND', 58.4, 8.9)
    bd.track('+3V3', [(57.61, 13.1), (58.7, 13.1)], 0.3)
    bd.via('+3V3', 58.7, 13.1)
    bd.track('+3V3', [(58.7, 13.1), (58.7, 15.15), (59.6, 16.05)], 0.4)
    bd.track('+3V3', [(56.85, 16.55), (58.5, 16.55), (59.0, 16.2)], 0.4)
    # (the LED's ground via sits right of the SDA / SCL stems on inner 2)
    bd.track('GND', [(51.95, 19.85), (55.4, 19.85)], 0.4)
    bd.via('GND', 55.4, 19.85)
    bd.track('GND', [(59.6, 17.95), (59.6, 19.3)], 0.4)
    bd.via('GND', 59.6, 19.3)

    # Encoder clock and data buses, on the bottom layer with the ground
    # plane between them and the motor phases. Each runs between two pin
    # rows of the four sockets (0.3 mm clear of the pads), then round the
    # right-hand edge and back in to the XIAO. Data has a stub up to pin 4
    # of each socket; the clock is tapped in each cell through that
    # socket's own series resistor (route_cell).
    xs = [CELL_X[n] + XH_U for n in CELL_X]             # socket pin columns
    for x in xs:
        bd.track('ENC_DO', [(x, 49.75), (x, 51.0)], 0.2, B)     # pin 4
    # (the two run 1 mm apart down the edge so each can carry a via to a
    # test pad there; they come in below U6's pins)
    bd.track('ENC_CLK', [(CELL_X[1] + 4.2, 52.25), (75.0, 52.25), (75.0, 9.9),
                         (74.5, 9.4), (60.0, 9.4), (58.4, 11.0)], 0.2, B)
    bd.via('ENC_CLK', 58.4, 11.0)
    bd.track('ENC_DO', [(xs[0], 49.75), (63.0, 49.75), (65.07, 51.82),
                        (74.0, 51.82), (74.0, 10.4), (73.5, 9.9), (62.6, 9.9),
                        (60.15, 12.35), (57.46, 12.35), (55.5, 14.31)], 0.2, B)
    bd.via('ENC_DO', 55.5, 14.31)
    bd.track('ENC_DO', [(55.5, 14.31), (55.79, 14.02), (55.79, 13.4)], 0.2)  # pull-up R5
    bd.track('ENC_DO', [(53.11, 14.31), (55.5, 14.31)], 0.2)    # series R6
    bd.via('ENC_CLK', 75.0, 22.6)                       # test pad TP13
    bd.track('ENC_CLK', [(75.0, 22.6), (77.2, 22.6)], 0.2)
    bd.via('ENC_DO', 74.0, 18.6)                        # test pad TP14
    bd.track('ENC_DO', [(74.0, 18.6), (77.2, 18.6)], 0.2)
    # the XIAO ends of the encoder and LED signals: short, direct, top layer
    # (data runs straight out along its own pad's row into R6: a diagonal
    # here once boxed in the SDA pad below it)
    bd.track('ENC_DO_MCU', [(49.5, 14.31), (51.29, 14.31)], 0.2)
    bd.track('ENC_CLK', [(58.4, 11.0), (54.67, 11.0), (53.9, 11.77),
                         (49.5, 11.77)], 0.2)
    bd.track('LED_DATA', [(49.5, 16.85), (51.0, 16.85), (51.3, 16.55),
                          (51.95, 16.55)], 0.2)

    # PWM inputs of the two drivers above the XIAO (2 and 3). The autorouter
    # gets these right only some of the time, and when it does it wanders
    # (65 mm round the 5 V module for an 11 mm connection). So, by hand:
    # out from the pad to a via, up the bottom layer beside the XIAO, in
    # over its far end, up through a via below each pin.
    for cell, side, x_via, lanes in ((3, 1, 50.7, (50.7, 51.4, 52.1)),
                                     (2, -1, 29.3, (29.3, 28.6, 27.9))):
        cx = CELL_X[cell]
        # pads top to bottom on that side of the XIAO; the top one takes the
        # inner lane, turns first and ends at the pin furthest across
        order = ((3, 9.23), (2, 7.96), (1, 6.69)) if cell == 3 else \
                ((1, 16.85), (2, 15.58), (3, 14.31))
        pins = {3: cx + 0.975, 2: cx + 2.275, 1: cx + 3.575}
        yvia = {3: 24.4, 2: 23.5, 1: 22.9}
        turn = {k: 20.9 + 0.5 * i for i, (k, _) in enumerate(order)}
        for (k, y_pad), lane in zip(order, lanes):
            net = f'M{cell}_IN{k}'
            x_pin = pins[k]
            bd.track(net, [(40.0 + side * 9.5, y_pad), (x_via, y_pad)], 0.2)
            bd.via(net, x_via, y_pad)
            pts = [(x_via, y_pad)]
            if lane != x_via:
                pts += [(lane - side * 0.3, y_pad), (lane, y_pad + 0.3)]
            d = -1 if x_pin < lane else 1           # which way it turns
            pts += [(lane, turn[k] - 0.5), (lane + d * 0.5, turn[k]),
                    (x_pin - d * 0.5, turn[k]), (x_pin, turn[k] + 0.5),
                    (x_pin, yvia[k])]
            bd.track(net, pts, 0.2, B)
            bd.via(net, x_pin, yvia[k])
            bd.track(net, [(x_pin, yvia[k]), (x_pin, CELL_Y - 3.3)], 0.2)

    # Enable: XIAO D3 -> via -> R3 on top; up the bottom layer to the bus's
    # right-hand end; from the bus's left-hand end down to test pad TP5
    bd.track('DRV_EN', [(49.5, 10.5), (52.95, 10.5)], 0.2)
    bd.via('DRV_EN', 52.95, 10.5)
    bd.track('DRV_EN', [(52.95, 10.5), (53.4, 10.5), (54.6, 9.3),
                        (55.09, 8.9)], 0.2)
    bd.track('DRV_EN', [(52.95, 10.5), (52.95, CELL_Y - 3.1),
                        (53.45, CELL_Y - 2.6)], 0.2, B)
    x1 = CELL_X[1] - 3.575
    bd.track('DRV_EN', [(x1, CELL_Y - 4.4), (x1, 6.5), (20.5, 3.825),
                        (20.5, 3.2)], 0.2, B)
    bd.via('DRV_EN', 20.5, 3.2)
    bd.track('DRV_EN', [(20.5, 3.2), (22.0, 3.2)], 0.2)

    # Chip selects, by hand (the autorouter left two of them open once it
    # was made to keep clear of joints). From each socket's pin 5 down the
    # top layer along its cell's left boundary, through a via above the
    # decoupling caps, then along a bottom-layer corridor that crosses all
    # four drivers between their exposed-pad vias and their VM links, and
    # down the right-hand side to U6. Lane order keeps them from crossing.
    for n, cx in CELL_X.items():
        net = f'CS{n}'
        xp, xn = cx + XH_U, cx - 5.3
        ly, lx = 32.0 + 0.65 * (n - 1), 64.5 + 0.65 * (n - 1)
        py = 15.635 - 1.27 * (n - 1)                    # U6 pins 4..7
        # the via sits above the neighbouring cell's charge-pump cap; cell 1
        # has no neighbour, so its via goes straight onto its lane, which
        # leaves the bottom layer above it free for the VCP test pad's track
        yv = ly if n == 1 else 36.9
        bd.track(net, [(xp, 48.5), (xn + 0.5, 48.5), (xn, 48.0), (xn, yv)], 0.2)
        bd.via(net, xn, yv)
        start = [(xn, ly)] if n == 1 else [(xn, yv), (xn, ly + 0.5), (xn + 0.5, ly)]
        bd.track(net, start + [(lx - 0.5, ly), (lx, ly - 0.5), (lx, py + 0.5),
                               (lx - 0.5, py), (63.0, py)], 0.2, B)
        bd.via(net, 63.0, py)
        bd.track(net, [(63.0, py), (65.025, py)], 0.2)

    # channel 1's VCP test pad: from the VCP cap's pad through a via, west
    # along the bottom layer between the chip-select lanes and the VM link
    c1 = CELL_X[1]
    bd.track('M1_VCP', [(c1 + 3.95, CELL_Y + 5.4), (c1 + 4.6, CELL_Y + 5.4),
                        (c1 + 5.2, CELL_Y + 5.7)], 0.25)
    bd.via('M1_VCP', c1 + 5.2, CELL_Y + 5.7)
    bd.track('M1_VCP', [(c1 + 5.2, CELL_Y + 5.7), (14.5, CELL_Y + 5.7),
                        (14.0, CELL_Y + 6.2), (14.0, 36.6)], 0.2, B)
    bd.via('M1_VCP', 14.0, 36.6)
    bd.track('M1_VCP', [(14.0, 36.6), (13.0, 36.6), (12.6, 37.0)], 0.2)

    # ground pad beside the channel-1 test pads
    bd.track('GND', [(12.5, 30.6), (11.0, 30.6)], 0.4)
    bd.via('GND', 11.0, 30.6)

    # I2C pull-up supply, Qwiic grounds
    bd.track('+3V3', [(70.41, 24.9), (70.41, 27.0), (70.41, 28.4)], 0.3)
    bd.via('+3V3', 70.41, 28.4)
    bd.track('SDA', [(68.59, 27.0), (67.3, 27.0), (66.9, 27.4),
                     (66.3, 27.4)], 0.2)                       # test pad TP10
    bd.track('SCL', [(68.59, 24.9), (67.57, 24.9), (67.3, 24.9), (66.9, 24.5),
                     (66.3, 24.5)], 0.2)                       # test pad TP11
    bd.track('GND', [(5.2, 33.25), (6.9, 33.25)], 0.3)
    bd.via('GND', 6.9, 33.25)
    bd.track('GND', [(74.8, 28.98), (73.1, 28.98)], 0.3)
    bd.via('GND', 73.1, 28.98)


def planes(bd):
    e = 0.2
    full = [(e, e), (W - e, e), (W - e, H - e), (e, H - e)]
    bd.zone('GND', IN1, full)
    bd.zone('+3V3', IN2, full)
    # Bottom layer, the band between the jacks:
    #  12V_JACK: the daisy-chain pass-through, jack pin to jack pin
    bd.zone('12V_JACK', B, [(11.6, 41.3), (68.4, 41.3), (68.4, 48.2),
                            (65.0, 48.2), (65.0, 44.2), (15.0, 44.2),
                            (15.0, 48.2), (11.6, 48.2)], priority=2, solid=True)
    #  +12V (after D1): strip under the four fuses, with an arm up to D1 / D4
    #  at the top left
    bd.zone('+12V', B, [(7.6, 55.6), (7.6, 54.3), (15.4, 54.3), (15.4, 44.6),
                        (64.7, 44.6), (64.7, 46.4), (17.2, 46.4), (17.2, 55.6)],
            priority=2, solid=True)
    #  Both are doubled on inner 2 (half-ounce copper, joined by the jack
    #  pins and by every +12V via), which takes the pass-through from "just
    #  enough for 5 A" to having margin. The inner +12V copper also has an
    #  arm to the bulk cap C3 at the top right; the bottom layer there is
    #  left for the encoder bus.
    bd.zone('12V_JACK', IN2, [(11.6, 41.3), (68.4, 41.3), (68.4, 48.2),
                              (65.0, 48.2), (65.0, 44.2), (15.0, 44.2),
                              (15.0, 48.2), (11.6, 48.2)], priority=1, solid=True)
    bd.zone('+12V', IN2, [(7.6, 55.6), (7.6, 54.3), (15.4, 54.3), (15.4, 44.6),
                          (64.7, 44.6), (64.7, 53.0), (67.9, 53.0),
                          (67.9, 54.9), (62.9, 54.9), (62.9, 46.4),
                          (17.2, 46.4), (17.2, 55.6)], priority=1, solid=True)
    #  top-layer copper round D1's and D4's cathodes: D1 drops 0.4 V at the
    #  board's whole current and needs somewhere to put the heat
    bd.zone('+12V', F, [(8.0, 51.9), (10.9, 51.9), (10.9, 57.9), (8.0, 57.9)],
            priority=1, solid=True)
    bd.zone('GND', B, full)
    bd.zone('GND', F, full)


def keepouts(bd):
    # nothing routed on the top layer under the XIAO (between its pad rows),
    # and no vias there or under its far end: that copper could never be
    # inspected or reworked
    bd.keepout(F, [(32.95, 0.3), (47.05, 0.3), (47.05, 20.9), (32.95, 20.9)],
               'under XIAO')
    bd.keepout(F, [(30.3, 18.9), (49.7, 18.9), (49.7, 21.3), (30.3, 21.3)],
               'XIAO end, no vias', tracks=False)
    # no vias among the XIAO's hand-soldered lands either
    bd.keepout(F, [(29.7, 0.3), (32.95, 0.3), (32.95, 18.9), (29.7, 18.9)],
               'XIAO lands, no vias', tracks=False)
    bd.keepout(F, [(47.05, 0.3), (50.3, 0.3), (50.3, 18.9), (47.05, 18.9)],
               'XIAO lands, no vias', tracks=False)
    # the bottom-layer supply copper must not be cut by signal tracks
    for i, pts in enumerate([
            [(11.5, 41.2), (68.5, 41.2), (68.5, 46.5), (11.5, 46.5)],
            [(11.5, 46.5), (15.1, 46.5), (15.1, 48.3), (11.5, 48.3)],
            [(64.9, 46.5), (68.5, 46.5), (68.5, 48.3), (64.9, 48.3)],
            [(15.3, 46.5), (17.3, 46.5), (17.3, 55.7), (9.0, 55.7),
             (9.0, 54.2), (15.3, 54.2)]]):   # (x < 9: the 5 V module's feed leaves here)
        bd.keepout(B, pts, f'12 V copper {i + 1}', vias=False)
    # room for a screw head, washer or standoff round each mounting hole
    r = 4.2
    for hx, hy in HOLES:
        ring = [(hx + r * math.cos(math.radians(22.5 + 45 * k)),
                 hy + r * math.sin(math.radians(22.5 + 45 * k)))
                for k in range(8)]
        bd.keepout(F, ring, 'mounting hole')
        bd.keepout(B, ring, 'mounting hole')


# Which way round the 7805 goes: its metal tab stands on the left, inside
# the module's outline. Fitted the other way round it would put 12 V on
# the 5 V rail. (TO-220: tab face 3.15 mm behind the pin row, 1.27 mm
# thick, body 10 mm wide centred on pin 2.)
U7_TAB = [(6.35, 10.54), (7.62, 10.54), (7.62, 20.54), (6.35, 20.54)]
U7_SILK_TEXT = ('7805 TAB', 5.2, 15.54, 0.9, 90)


def u7_silk(bd):
    for a, b in zip(U7_TAB, U7_TAB[1:] + U7_TAB[:1]):
        bd.edge_line(a, b, pcbnew.F_SilkS, 0.2)
    bd.text(*U7_SILK_TEXT)


def labels(bd):
    for item in SILK:
        bd.text(*item)
    u7_silk(bd)
    # a bracket along the board edge over each channel's socket + header,
    # so it is plain which encoder socket belongs to which motor header
    y = H - 0.38
    for cx in CELL_X.values():
        bd.edge_line((cx - 6.0, y), (cx + 6.0, y), pcbnew.F_SilkS, 0.15)
        for x in (cx - 6.0, cx + 6.0):
            bd.edge_line((x, y), (x, y - 0.35), pcbnew.F_SilkS, 0.15)


# ------------------------------------------------------- schematic link
def link_schematic(board):
    """Tie footprints to symbols and take KiCad's net names, from the KiCad
    netlist. Returns a one-line status."""
    if not os.path.exists(NETLIST):
        return 'no netlist: board not linked to the schematic'
    txt = open(NETLIST).read()
    comps_txt, nets_txt = txt.split('(nets', 1) if '(nets' in txt else (txt, '')
    comps_txt = comps_txt.split('(libparts')[0]
    comps = {}
    for chunk in re.split(r'\(comp\s', comps_txt)[1:]:
        ref = re.search(r'\(ref "([^"]+)"\)', chunk)
        if ref:
            comps[ref.group(1)] = chunk
    refs = {fp.GetReference() for fp in board.GetFootprints()
            if not fp.GetReference().startswith('FID')}
    if refs - set(comps):
        return ('netlist is out of date (missing %s ...): board not linked'
                % sorted(refs - set(comps))[:4])
    for fp in board.GetFootprints():
        chunk = comps.get(fp.GetReference())
        if not chunk:
            continue
        sheet = re.search(r'\(sheetpath\s+\(names "([^"]*)"\)\s+\(tstamps "([^"]*)"\)',
                          chunk)
        sym = re.search(r'\(tstamps\s+"([^"]+)"\)\s*\)?\s*$', chunk.strip())
        sym = sym or re.search(r'\)\s*\(tstamps\s+"([^"/]+)"\)', chunk)
        if sheet and sym:
            fp.SetPath(pcbnew.KIID_PATH(sheet.group(2) + sym.group(1)))
            fp.SetSheetname(sheet.group(1))
        sf = re.search(r'\(property\s+\(name "Sheetfile"\)\s+\(value "([^"]*)"\)',
                       chunk)
        if sf:
            fp.SetSheetfile(sf.group(1))
        for name, value in re.findall(
                r'\(field\s+\(name "([^"]+)"\)\s*(?:"([^"]*)")?\s*\)', chunk):
            if name not in ('Footprint', 'Reference', 'Value') and value:
                fp.SetField(name, value)
        for key, field in (('description', 'Description'),
                           ('datasheet', 'Datasheet')):
            m = re.search(r'\(%s "([^"]*)"\)' % key, chunk)
            if m and m.group(1):
                fp.SetField(field, m.group(1))
        # fields created here (LCSC ...) would otherwise print on the silkscreen
        for f in fp.GetFields():
            if f.GetName() not in ('Reference', 'Value'):
                f.SetVisible(False)
    # net names as KiCad gives them, pad by pad
    pads = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pads.setdefault((fp.GetReference(), pad.GetNumber()), []).append(pad)
    renamed = 0
    for m in re.finditer(r'\(net\s+\(code\s+"?\d+"?\)\s+\(name\s+"([^"]*)"\)(.*?)'
                         r'(?=\n\s*\(net\s+\(code|\Z)', nets_txt, re.S):
        name = m.group(1)
        nodes = re.findall(r'\(node\s+\(ref\s+"([^"]+)"\)\s+\(pin\s+"([^"]+)"\)',
                           m.group(2))
        if name.startswith('unconnected-'):
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
            for key in nodes:
                for pad in pads.get(key, []):
                    pad.SetNet(net)
            continue
        for key in nodes:
            if pads.get(key):
                net = pads[key][0].GetNet()
                if net and net.GetNetname() != name:
                    net.SetNetname(name)
                    renamed += 1
                break
    return f'linked to the schematic ({len(comps)} symbols, {renamed} nets renamed)'


# Patterns are given bare; both 'NAME' and '/NAME' are assigned, so the
# classes hold whether the schematic names a net globally or on the root sheet.
NETCLASSES = [      # name, colour, track, clearance, patterns
    ('Power12V', 'rgb(220, 40, 40)', 0.8, 0.25, ['12V_JACK', '+12V', 'VM?']),
    ('PowerLogic', 'rgb(240, 150, 30)', 0.4, 0.2,
     ['+5V', 'XIAO_5V', '+3V3', 'QWIIC_3V3', 'M?_V3P3']),
    ('Ground', 'rgb(90, 110, 140)', 0.4, 0.2, ['GND']),
    ('MotorPhase', 'rgb(200, 60, 200)', 0.65, 0.2, ['M?_OUT?']),
    ('ChargePump', 'rgb(140, 90, 220)', 0.25, 0.2,
     ['M?_CPL', 'M?_CPH', 'M?_VCP']),
    ('PWM', 'rgb(40, 170, 80)', 0.2, 0.2, ['M?_IN?', 'DRV_EN']),
    ('Bus', 'rgb(30, 170, 200)', 0.2, 0.2,
     ['SDA', 'SCL', 'ENC*', 'CS?', 'LED_DATA', 'M?_FAULT', 'M?_LED']),
]


def project_settings(pro_text, prl_text):
    """Net classes (with colours) and manufacturing rules, into the .kicad_pro.
    pro_text / prl_text: the project files as they were before pcbnew saved
    the board (it may rewrite them)."""
    pro = json.loads(pro_text)
    ns = pro.setdefault('net_settings', {})
    default = None
    for c in ns.get('classes', []):
        if c.get('name') == 'Default':
            default = c
    if default is None:
        default = {'name': 'Default', 'bus_width': 12, 'wire_width': 6,
                   'line_style': 0, 'diff_pair_gap': 0.25,
                   'diff_pair_via_gap': 0.25, 'diff_pair_width': 0.2,
                   'microvia_diameter': 0.3, 'microvia_drill': 0.1,
                   'pcb_color': 'rgba(0, 0, 0, 0.000)',
                   'schematic_color': 'rgba(0, 0, 0, 0.000)',
                   'priority': 2147483647}
    default.update(clearance=0.2, track_width=0.2, via_diameter=0.6,
                   via_drill=0.3)
    classes, patterns = [default], []
    for i, (name, colour, width, clr, pats) in enumerate(NETCLASSES):
        c = dict(default)
        c.update(name=name, pcb_color=colour, schematic_color=colour,
                 track_width=width, clearance=clr, priority=i)
        classes.append(c)
        for p in pats:
            patterns += [{'netclass': name, 'pattern': p},
                         {'netclass': name, 'pattern': '/' + p}]
    ns['classes'] = classes
    ns['netclass_patterns'] = patterns
    ns.setdefault('meta', {'version': 4})
    rules = pro.setdefault('board', {}).setdefault(
        'design_settings', {}).setdefault('rules', {})
    rules.update({          # JLCPCB multilayer capability, with margin
        'min_clearance': 0.15, 'min_track_width': 0.15,
        'min_via_diameter': 0.5, 'min_through_hole_diameter': 0.3,
        'min_via_annular_width': 0.13, 'min_copper_edge_clearance': 0.4,
        'min_hole_clearance': 0.25, 'min_hole_to_hole': 0.25,
    })
    with open(PRO, 'w') as f:
        json.dump(pro, f, indent=2)
        f.write('\n')
    # local view settings: colour tracks and pads by net class, not just the
    # ratsnest (Appearance > Nets > net colour mode "All")
    if prl_text:
        prl = json.loads(prl_text)
        prl.setdefault('board', {})['net_color_mode'] = 2
        with open(PRL, 'w') as f:
            json.dump(prl, f, indent=2)
            f.write('\n')


def main(stage):
    pro_text = open(PRO).read()
    prl_text = open(PRL).read() if os.path.exists(PRL) else ''
    if os.path.exists(PCB):
        os.remove(PCB)
    board = pcbnew.NewBoard(PCB)
    bd = Builder(board)
    setup(board)
    populate(board, bd)
    outline(bd)
    place(board)
    labels(bd)
    if stage != 'place':
        route_power(bd)
        planes(bd)
        keepouts(bd)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    status = link_schematic(board)
    pcbnew.SaveBoard(PCB, board)
    hand = os.path.join(PRJ, 'build', 'handrouted.json')
    if os.path.exists(hand):
        os.remove(hand)         # lock_tracks.py re-lists this board's tracks
    project_settings(pro_text, prl_text)
    print(f'{stage}: {len(board.GetFootprints())} footprints, '
          f'{len(board.GetTracks())} tracks and vias, '
          f'{len(board.Zones())} zones; {status}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'all')
