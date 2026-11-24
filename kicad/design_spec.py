"""Single source of truth for the BLDC driver board: parts and nets.

The KiCad schematic is built from this (payloads for the KiCad MCP server's
batch tools), and the netlist KiCad exports is checked back against it:

    python3 design_spec.py payload            -> build/*.json for the MCP calls
    python3 design_spec.py check <netlist>    -> compare a KiCad netlist (kicadsexpr)
    python3 design_spec.py bom                -> BOM rows (ref, value, footprint, LCSC)

Motors are numbered left to right across the board, M1..M4; driver for
motor n is U(n+1).  XIAO pads are Seeed's numbers (1-23).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

FP = {
    'C0805': 'Capacitor_SMD:C_0805_2012Metric',
    'R0805': 'Resistor_SMD:R_0805_2012Metric',
    'LED0805': 'LED_SMD:LED_0805_2012Metric',
    'CAN': 'Capacitor_SMD:CP_Elec_6.3x7.7',
    'SMA': 'Diode_SMD:D_SMA',
    'F1812': 'Fuse:Fuse_1812_4532Metric',
    'DRV': 'Package_SO:HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP2.85x5.4mm_ThermalVias',
    'SOIC16': 'Package_SO:SOIC-16_3.9x9.9mm_P1.27mm',
    'XIAO': 'bldc:XIAO-ESP32-S3-Plus-SMD',
    'JACK': 'bldc:XKB_DC-005-5A-2.0',
    'QWIIC': 'Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal',
    'XH5': 'Connector_JST:JST_XH_B5B-XH-A_1x05_P2.50mm_Vertical',
    'HDR3': 'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical',
    'HDR2': 'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',
    # KiCad's Recom R-78E footprint with 1.1 mm holes, so that a TO-220
    # 7805 fits as well (lib/gen_footprints.py)
    'SIP3': 'bldc:SIP-3_K7805_or_TO-220',
    'WS2812': 'LED_SMD:LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm',
    'HOLE': 'MountingHole:MountingHole_3mm',     # 3.0 mm, as on the Node board
    'TP': 'TestPoint:TestPoint_Pad_D1.5mm',
    'C0603': 'Capacitor_SMD:C_0603_1608Metric',
    'R0603': 'Resistor_SMD:R_0603_1608Metric',
}

COMPONENTS = []     # dicts: ref, symbol, value, footprint, x, y, lcsc, dnp, tht
NETS = {}           # net -> [(ref, pin)]
NO_CONNECT = []     # (ref, pin)


def part(ref, symbol, value, fp, x, y, lcsc='', dnp=False, tht=False, rot=0,
         nobom=False):
    """x, y, rot are schematic positions from the first, machine-placed
    schematic; gen_schematic.py has its own layout and ignores them.
    nobom: a board feature with no component (test pad, mounting hole)."""
    COMPONENTS.append(dict(ref=ref, symbol=symbol, value=value,
                           footprint=FP.get(fp, fp), x=x, y=y, lcsc=lcsc,
                           dnp=dnp, tht=tht, rot=rot, nobom=nobom))


def net(name, *pins):
    for p in pins:
        ref, pin = p.split('.')
        NETS.setdefault(name, []).append((ref, pin))


# ---------------------------------------------------------------- MCU
part('U1', 'bldc:XIAO_ESP32S3_Plus', 'XIAO-ESP32-S3-Plus', 'XIAO', 63.5, 71.12,
     tht=True)   # hand-soldered: JLCPCB does not stock it
part('R3', 'Device:R', '10k', 'R0805', 30.48, 132.08, 'C17414')

# motor n -> (IN1, IN2, IN3) XIAO pads, chosen so each bundle reaches its
# driver without crossing (see WORKING.md)
MOTOR_PADS = {1: ('10', '23', '11'),    # D9,  D17, D10
              2: ('21', '9', '22'),     # D19, D8,  D18
              3: ('16', '3', '17'),     # D12, D2,  D13
              4: ('1', '15', '2')}      # D0,  D11, D1
for n, pads in MOTOR_PADS.items():
    for k, pad in enumerate(pads, start=1):
        net(f'M{n}_IN{k}', f'U1.{pad}')
net('DRV_EN', 'U1.4', 'R3.1')
net('GND', 'R3.2', 'U1.13')
net('ENC_CLK', 'U1.18')
net('SDA', 'U1.5')
net('ENC_DO_MCU', 'U1.19')
net('SCL', 'U1.6')
net('LED_DATA', 'U1.20')
net('ENC_A0', 'U1.7')
net('ENC_A1', 'U1.8')
net('+3V3', 'U1.12')
net('XIAO_5V', 'U1.14')

# ---------------------------------------------------------------- drivers
CENTRES = {1: (170.18, 71.12), 2: (276.86, 71.12),
           3: (170.18, 203.2), 4: (276.86, 203.2)}
for n, (cx, cy) in CENTRES.items():
    u = f'U{n + 1}'
    part(u, 'bldc:DRV8313PWP', 'DRV8313PWPR', 'DRV', cx, cy, 'C92482')
    L, R = cx - 38.1, cx + 38.1
    # 1.1 A hold / 2.2 A trip / 33 V (SMD1812P110TF/33). Four of them hold
    # 4.4 A, inside the 5 A the jacks and the input diode are rated for.
    # 2 A hold / 24 V (SMD1812P200TF/24, C434887) fits the same pads.
    part(f'F{n}', 'Device:Polyfuse', '1.1A', 'F1812', L, cy - 38.1, 'C21000')
    part(f'C{n}1', 'Device:C', '10n 50V', 'C0805', L, cy - 22.86, 'C1710')
    part(f'C{n}2', 'Device:C', '100n', 'C0805', L, cy - 7.62, 'C49678')
    part(f'C{n}3', 'Device:C', '100n', 'C0805', L, cy + 7.62, 'C49678')
    part(f'C{n}4', 'Device:C', '100n', 'C0805', L, cy + 22.86, 'C49678')
    part(f'C{n}5', 'Device:C_Polarized', '100u 25V', 'CAN', L, cy + 38.1,
         'C2836443')
    part(f'R{n}1', 'Device:R', '1k', 'R0805', R, cy - 22.86, 'C17513')
    part(f'D{n}1', 'Device:LED', 'FAULT', 'LED0805', R, cy - 7.62, 'C84256')
    part(f'C{n}6', 'Device:C', '470n', 'C0805', R, cy + 7.62, 'C13967')
    part(f'J1{n}', 'Connector_Generic:Conn_01x03', f'MOTOR{n}', 'HDR3',
         R, cy + 27.94, 'C2937625', tht=True)    # XFCN PZ254V-11-03P

    vm = f'VM{n}'
    net('+12V', f'F{n}.1')
    net(vm, f'F{n}.2', f'{u}.4', f'{u}.11', f'C{n}2.2', f'C{n}3.1',
        f'C{n}4.1', f'C{n}5.1')
    net(f'M{n}_CPL', f'{u}.1', f'C{n}1.1')
    net(f'M{n}_CPH', f'{u}.2', f'C{n}1.2')
    net(f'M{n}_VCP', f'{u}.3', f'C{n}2.1')
    net('GND', f'C{n}3.2', f'C{n}4.2', f'C{n}5.2', f'C{n}6.2',
        f'{u}.6', f'{u}.7', f'{u}.10', f'{u}.12', f'{u}.13', f'{u}.14',
        f'{u}.19', f'{u}.20', f'{u}.28', f'{u}.29')
    for k, pin in ((1, 5), (2, 8), (3, 9)):
        net(f'M{n}_OUT{k}', f'{u}.{pin}', f'J1{n}.{k}')
    for k, pin in ((1, 27), (2, 25), (3, 23)):
        net(f'M{n}_IN{k}', f'{u}.{pin}')
    net('+3V3', f'{u}.26', f'{u}.24', f'{u}.22', f'{u}.17', f'R{n}1.1')
    net('DRV_EN', f'{u}.16')
    net(f'M{n}_V3P3', f'{u}.15', f'C{n}6.1')
    net(f'M{n}_FAULT', f'{u}.18', f'D{n}1.1')        # LED cathode at nFAULT
    net(f'M{n}_LED', f'D{n}1.2', f'R{n}1.2')

# ---------------------------------------------------------------- power
part('J1', 'Connector:Barrel_Jack_Switch', '12V_IN', 'JACK', 30.48, 170.18,
     'C381116', tht=True)
part('J2', 'Connector:Barrel_Jack_Switch', '12V_OUT', 'JACK', 30.48, 198.12,
     'C381116', tht=True)
part('D1', 'Device:D_Schottky', 'SS54', 'SMA', 63.5, 165.1, 'C22452')
part('C3', 'Device:C_Polarized', '100u 25V', 'CAN', 86.36, 177.8, 'C2836443')
# Linear 7805 in TO-220: enough for the XIAO, to be swapped if testing says
# otherwise. The K7805-500R3 switching module (C2992390) has the same pin
# order and pitch and fits the same footprint.
part('U7', 'Regulator_Linear:L7805', 'L7805CV', 'SIP3', 55.88, 236.22,
     'C111887', tht=True)
part('C4', 'Device:C', '10u 25V', 'C0805', 27.94, 246.38, 'C15850')
part('C5', 'Device:C', '22u 25V', 'C0805', 83.82, 246.38, 'C45783')
part('D2', 'Device:D_Schottky', 'SS14', 'SMA', 104.14, 231.14, 'C2480')
net('12V_JACK', 'J1.1', 'J2.1', 'D1.2')            # anode
net('+12V', 'D1.1', 'C3.1', 'U7.1', 'C4.1')
net('GND', 'J1.2', 'J2.2', 'C3.2', 'U7.2', 'C4.2', 'C5.2')
net('+5V', 'U7.3', 'C5.1', 'D2.2')
net('XIAO_5V', 'D2.1')
NO_CONNECT += [('J1', '3'), ('J2', '3')]

# ---------------------------------------------------------------- encoders
part('U6', 'bldc:74HC139', '74HC139D', 'SOIC16', 358.14, 40.64, 'C5603')
part('C1', 'Device:C', '100n', 'C0805', 398.78, 38.1, 'C49678')
# Encoder port hardening (2026-11-11). The cables run beside motor wires
# carrying 12 V PWM edges.
#  - The clock: ENC_CLK is the bus from the XIAO; each socket has its own
#    series resistor Rn2 (47R), so every cable is driven through its own
#    termination and a reflection from one cable does not go straight into
#    the other three. (The single R4 at the XIAO is gone.)
#  - The data line: R6 (100R) between the shared ENC_DO line and the XIAO
#    pin limits the current if two encoders ever drive at once or a cable
#    is plugged in live. R5 pulls the shared line up.
#  - Cn7 (100n) from +3V3 to GND for each socket, so noise picked up on a
#    cable does not get onto the board's 3V3 rail.
# Rn2 and Cn7 are 0603: the only free ground near the sockets is a strip
# 1.75 mm wide beside each motor header.
part('R5', 'Device:R', '10k', 'R0805', 365.76, 81.28, 'C17414')
part('R6', 'Device:R', '100R', 'R0805', 342.9, 81.28, 'C17408')
net('GND', 'U6.1', 'U6.8', 'U6.13', 'U6.14', 'C1.2')
net('+3V3', 'U6.16', 'U6.15', 'C1.1', 'R5.1')
net('ENC_A0', 'U6.2')
net('ENC_A1', 'U6.3')
net('ENC_DO', 'R5.2', 'R6.2')
net('ENC_DO_MCU', 'R6.1')
NO_CONNECT += [('U6', p) for p in ('9', '10', '11', '12')]
for n, (x, y) in {1: (347.98, 109.22), 2: (391.16, 109.22),
                  3: (347.98, 139.7), 4: (391.16, 139.7)}.items():
    j = f'J2{n}'
    part(j, 'Connector_Generic:Conn_01x05', f'ENC{n}', 'XH5', x, y, 'C157991',
         tht=True)
    part(f'R{n}2', 'Device:R', '47R', 'R0603', x - 12.7, y, 'C23182')
    part(f'C{n}7', 'Device:C', '100n', 'C0603', x - 12.7, y + 10.16, 'C14663')
    net('+3V3', f'{j}.1', f'C{n}7.1')
    net('GND', f'{j}.2', f'C{n}7.2')
    net('ENC_CLK', f'R{n}2.1')
    net(f'ENC{n}_CLK', f'R{n}2.2', f'{j}.3')
    net('ENC_DO', f'{j}.4')
    net(f'CS{n}', f'{j}.5', f'U6.{3 + n}')

# ---------------------------------------------------------------- I2C, LED
for j, name, x in (('J3', 'I2C_IN', 347.98), ('J4', 'I2C_OUT', 391.16)):
    part(j, 'Connector_Generic_MountingPin:Conn_01x04_MountingPin', name,
         'QWIIC', x, 172.72, 'C160404')
    net('GND', f'{j}.1', f'{j}.MP')
    net('QWIIC_3V3', f'{j}.2')
    net('SDA', f'{j}.3')
    net('SCL', f'{j}.4')
part('JP1', 'Connector_Generic:Conn_01x02', 'QWIIC_PWR', 'HDR2', 347.98, 200.66,
     'C492401', tht=True)                        # XFCN PZ254V-11-02P
part('R1', 'Device:R', '4k7', 'R0805', 375.92, 200.66, 'C17673', dnp=True)
part('R2', 'Device:R', '4k7', 'R0805', 396.24, 200.66, 'C17673', dnp=True)
net('QWIIC_3V3', 'JP1.1')
net('+3V3', 'JP1.2', 'R1.1', 'R2.1')
net('SDA', 'R1.2')
net('SCL', 'R2.2')
part('D3', 'LED:WS2812B', 'WS2812B', 'WS2812', 353.06, 231.14, 'C2843785')
part('C2', 'Device:C', '100n', 'C0805', 393.7, 228.6, 'C49678')
net('+3V3', 'D3.1', 'C2.1')
net('GND', 'D3.3', 'C2.2')
net('LED_DATA', 'D3.4')
NO_CONNECT += [('D3', '2')]

# ------------------------------------------- added by the 2026-11-10 review
# D4: clamp on the 12 V rail. D1 stops a decelerating motor returning energy
#     to the supply, so the rail can only rise; the electrolytics are 25 V.
# C6: bulk on +3V3, which leaves the board on four encoder cables.
# TP1-5: probe pads; none existed.
part('D4', 'Device:D_Zener', 'SMAJ15A', 'SMA', 63.5, 185.42, 'C86819')
net('+12V', 'D4.1')                                 # cathode
net('GND', 'D4.2')
part('C6', 'Device:C', '10u 25V', 'C0805', 96.52, 96.52, 'C15850')
net('+3V3', 'C6.1')
net('GND', 'C6.2')
# TP6-9: the key nodes of one driver channel (channel 1);
# TP10-11: the I2C bus, which is otherwise only on the Qwiic connectors.
for i, (netname, label) in enumerate((('+12V', 'TP_12V'), ('GND', 'TP_GND'),
                                      ('+5V', 'TP_5V'), ('+3V3', 'TP_3V3'),
                                      ('DRV_EN', 'TP_EN'), ('VM1', 'TP_VM1'),
                                      ('M1_VCP', 'TP_VCP1'),
                                      ('M1_V3P3', 'TP_V3P3_1'),
                                      ('M1_FAULT', 'TP_FAULT1'),
                                      ('SDA', 'TP_SDA'), ('SCL', 'TP_SCL'),
                                      # round 2 of the review: a ground pad
                                      # beside the channel-1 pads, and the
                                      # encoder bus
                                      ('GND', 'TP_GND2'),
                                      ('ENC_CLK', 'TP_CLK'),
                                      ('ENC_DO', 'TP_DO')),
                                     start=1):
    part(f'TP{i}', 'Connector:TestPoint', label, 'TP', 320.04 + 12.7 * i,
         276.86, nobom=True)
    net(netname, f'TP{i}.1')

# ---------------------------------------------------------------- mechanical
for i, x in enumerate((340.36, 358.14, 375.92, 393.7), start=1):
    part(f'H{i}', 'Mechanical:MountingHole', 'M3', 'HOLE', x, 256.54, tht=True,
         nobom=True)

# power flags so ERC knows these nets are driven
FLAGS = ['12V_JACK', '+12V', 'GND', 'VM1', 'VM2', 'VM3', 'VM4']
for i, name in enumerate(FLAGS, start=1):
    ref = f'#FLG0{i}'
    part(ref, 'power:PWR_FLAG', 'PWR_FLAG', '', 20.32 + 15.24 * (i - 1), 276.86)
    net(name, f'{ref}.1')


# ====================================================================== tools
def payload():
    out = os.path.join(HERE, 'build')
    os.makedirs(out, exist_ok=True)
    comps = []
    for c in COMPONENTS:
        d = dict(symbol=c['symbol'], reference=c['ref'], value=c['value'],
                 position=dict(x=c['x'], y=c['y']))
        if c['footprint']:
            d['footprint'] = c['footprint']
        if c['rot']:
            d['rotation'] = c['rot']
        comps.append(d)
    conns = {}
    for name, pins in NETS.items():
        for ref, pin in pins:
            if pin in conns.setdefault(ref, {}):
                raise SystemExit(f'pin used twice: {ref}.{pin}')
            conns[ref][pin] = name
    json.dump(comps, open(os.path.join(out, 'components.json'), 'w'))
    json.dump(conns, open(os.path.join(out, 'connections.json'), 'w'))
    json.dump([dict(componentRef=r, pinName=p) for r, p in NO_CONNECT],
              open(os.path.join(out, 'no_connects.json'), 'w'))
    npins = sum(len(v) for v in NETS.values())
    print(f'{len(comps)} components, {len(NETS)} nets, {npins} pin connections, '
          f'{len(NO_CONNECT)} no-connects')
    return comps, conns


def parse_kicad_netlist(path):
    """net name -> set of (ref, pin) from a KiCad s-expression netlist."""
    txt = open(path).read()
    nets = {}
    for m in re.finditer(r'\(net\s+\(code\s+"?\d+"?\)\s+\(name\s+"([^"]*)"\)(.*?)'
                         r'(?=\n\s*\(net\s+\(code|\Z)', txt, re.S):
        name = m.group(1).lstrip('/')
        pins = set(re.findall(r'\(node\s+\(ref\s+"([^"]+)"\)\s+\(pin\s+"([^"]+)"\)',
                              m.group(2)))
        nets[name] = pins
    return nets


def check(path):
    got = parse_kicad_netlist(path)
    # power flags (#FLG..) are schematic-only: KiCad leaves them out of netlists
    want = {n: {(r, p) for r, p in pins if not r.startswith('#')}
            for n, pins in NETS.items()}
    ok = True
    for n in sorted(set(want) | set(got)):
        w, g = want.get(n, set()), got.get(n, set())
        if n.startswith('unconnected-') or (n not in want and len(g) <= 1):
            continue
        if w != g:
            ok = False
            print(f'MISMATCH {n}: missing {sorted(w - g)}  extra {sorted(g - w)}')
    npins = sum(len(v) for v in want.values())
    print(f'spec: {len(want)} nets / {npins} pins;  netlist: {len(got)} nets')
    print('NETLIST MATCHES SPEC' if ok else 'NETLIST DIFFERS FROM SPEC')
    return ok


def bom():
    rows = {}
    for c in COMPONENTS:
        if c['ref'].startswith('#') or c['nobom']:
            continue
        key = (c['value'], c['footprint'], c['lcsc'], c['dnp'], c['tht'])
        rows.setdefault(key, []).append(c['ref'])
    for (value, fp, lcsc, dnp, tht), refs in sorted(rows.items(),
                                                   key=lambda kv: kv[1][0]):
        print(f'{len(refs):2}  {value:20} {lcsc:9} {"DNP" if dnp else "   "} '
              f'{"THT" if tht else "SMT"}  {",".join(refs)}')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'payload'
    if cmd == 'payload':
        payload()
    elif cmd == 'check':
        sys.exit(0 if check(sys.argv[2]) else 1)
    elif cmd == 'bom':
        bom()
