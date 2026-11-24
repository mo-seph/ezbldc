"""Export everything in output/ from the board as it stands: STEP, three
renders, the copper map, and the draft JLCPCB set in output/fab/ (Gerbers,
drill, their zip, placement file, the two BOM files). It reads the board
and changes nothing in it.

    python3 tools/export_outputs.py

The BOM is ../bom_jlcpcb.csv, kept by hand. It is checked here against
design_spec.py (every fitted part with an LCSC number must be in it, and
nothing else), copied to output/fab/, and a second copy is written without
the through-hole parts for an order where those are fitted by hand.
"""
import csv
import json
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
sys.path.insert(0, PRJ)
import design_spec as spec      # noqa: E402

CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
KPY = ('/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/'
       'Versions/Current/bin/python3')
PCB = os.path.join(PRJ, 'bldc_driver_board.kicad_pcb')
OUT = os.path.join(PRJ, 'output')
FAB = os.path.join(OUT, 'fab')
GERB = os.path.join(FAB, 'gerbers')
BOM = os.path.join(os.path.dirname(PRJ), 'bom_jlcpcb.csv')
LAYERS = ('F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,'
          'F.Mask,B.Mask,Edge.Cuts')


def run(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f'FAILED: {" ".join(args[:4])} ...\n{r.stdout}{r.stderr}')
    return r.stdout


def boms():
    fitted = {c['ref']: c for c in spec.COMPONENTS
              if c['lcsc'] and not c['dnp'] and not c['nobom']}
    rows = list(csv.reader(open(BOM)))
    listed = {}
    for row in rows[1:]:
        for ref in row[1].split(','):
            listed[ref] = row[3]
    problems = [f'{r} is fitted but not in the BOM' for r in fitted if r not in listed]
    problems += [f'{r} is in the BOM but not a fitted part' for r in listed
                 if r not in fitted]
    problems += [f'{r}: BOM says {listed[r]}, spec says {fitted[r]["lcsc"]}'
                 for r in fitted if r in listed and listed[r] != fitted[r]['lcsc']]
    if problems:
        sys.exit('bom_jlcpcb.csv does not match design_spec.py:\n  '
                 + '\n  '.join(problems))
    shutil.copy(BOM, os.path.join(FAB, 'bom_jlcpcb.csv'))
    tht = {r for r, c in fitted.items() if c['tht']}
    smd_rows = [rows[0]] + [row for row in rows[1:]
                            if not set(row[1].split(',')) & tht]
    with open(os.path.join(FAB, 'bom_jlcpcb_smd_only.csv'), 'w', newline='') as f:
        csv.writer(f).writerows(smd_rows)
    return len(rows) - 1, len(smd_rows) - 1


# Rotation. JLCPCB turns a part from the way its own (EasyEDA) footprint for
# that LCSC number is drawn; KiCad turns it from the way KiCad's footprint
# is drawn. Where the two drawings differ, the angle in the placement file
# has to be KiCad's plus the difference. The difference belongs to the LCSC
# PART, not to the package family: the community rotation tables are keyed
# by KiCad footprint name and were wrong for two parts here (they would
# have turned the five electrolytics back to front).
#
# Each offset below was worked out from the EasyEDA footprint of that exact
# LCSC number (easyeda.com/api/products/<C-number>/components, read
# 2026-11-11) against the KiCad footprint on the board, by where pin 1 and
# the next pin lie. Every polarised part on the board was checked; a part
# that is not listed needs no offset:
#   C2836443 100 uF can: + pad on the left in both           -> 0
#   C22452 / C2480 / C86819 SMA diodes, C84256 LED: cathode
#     on the left in both                                    -> 0
#   C160404 Qwiic, C381116 jack, C111887 TO-220              -> 0
# JLCPCB's placement preview is still the final check.
ROTATION_OFFSETS = {        # LCSC number: degrees added to KiCad's angle
    'C92482': 270,      # DRV8313 HTSSOP-28: EasyEDA has pin 1 bottom-left
    'C5603': 270,       # 74HC139 SOIC-16: the same
    'C2843785': 270,    # WS2812B: EasyEDA has pin 1 bottom-left
    'C157991': 180,     # JST B5B-XH-A: EasyEDA has pin 1 on the right
    'C2937625': 270,    # 1x3 header: EasyEDA draws the row left to right
    'C492401': 270,     # 1x2 header: the same
}

_THT_CENTRES = '''
import json, sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
out = {}
for fp in b.GetFootprints():
    if fp.GetAttributes() & pcbnew.FP_THROUGH_HOLE:
        xs = [p.GetPosition().x for p in fp.Pads()]
        ys = [p.GetPosition().y for p in fp.Pads()]
        out[fp.GetReference()] = [(min(xs) + max(xs)) / 2e6,
                                  -(min(ys) + max(ys)) / 2e6]
print('CENTRES ' + json.dumps(out))
'''


def placement():
    """JLCPCB placement file from KiCad's position export, with the
    rotation offsets above, and with each through-hole part placed at the
    middle of its pins (KiCad reports pin 1; JLCPCB expects the centre)."""
    tmp = os.path.join(PRJ, 'build', 'pos.csv')
    run(CLI, 'pcb', 'export', 'pos', '--format', 'csv', '--units', 'mm',
        '--side', 'front', '--exclude-dnp', '-o', tmp, PCB)
    rows = list(csv.reader(open(tmp)))
    lcsc = {c['ref']: c['lcsc'] for c in spec.COMPONENTS}
    out = run(KPY, '-c', _THT_CENTRES, PCB)
    centres = json.loads([ln for ln in out.splitlines()
                          if ln.startswith('CENTRES ')][0][8:])
    turned = []
    with open(os.path.join(FAB, 'cpl_jlcpcb.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Designator', 'Val', 'Package', 'Mid X', 'Mid Y',
                    'Rotation', 'Layer'])
        for ref, val, package, x, y, rot, side in rows[1:]:
            rot = float(rot) % 360
            offset = ROTATION_OFFSETS.get(lcsc.get(ref, ''), 0)
            if offset:
                rot = (rot + offset) % 360
                turned.append(ref)
            if ref in centres:
                x, y = (f'{v:.6f}' for v in centres[ref])
            w.writerow([ref, val, package, x, y, f'{rot:.1f}', side.capitalize()])
    return len(rows) - 1, turned


def main():
    os.makedirs(GERB, exist_ok=True)
    n_bom, n_smd = boms()
    run(CLI, 'pcb', 'export', 'step', '--subst-models', '--force', '--no-dnp',
        '-o', os.path.join(OUT, 'bldc_driver_board.step'), PCB)
    for name, extra in (('top', ['--side', 'top']),
                        ('bottom', ['--side', 'bottom']),
                        ('iso', ['--side', 'top', '--rotate', '-40,0,25',
                                 '--perspective'])):
        run(CLI, 'pcb', 'render', '-w', '2200', '-h', '1750', '--quality',
            'high', '--background', 'opaque', *extra,
            '-o', os.path.join(OUT, f'render_{name}.png'), PCB)
    run(KPY, os.path.join(HERE, 'signal_map.py'))
    run('rsvg-convert', '-w', '2100', os.path.join(OUT, 'signal_map.svg'),
        '-o', os.path.join(OUT, 'signal_map.png'))
    # the board carries no designators (too dense), so: a drawing that does
    run(KPY, os.path.join(HERE, 'assembly_map.py'))
    asm = os.path.join(OUT, 'assembly_top.svg')
    run('rsvg-convert', '-w', '3200', asm,
        '-o', os.path.join(OUT, 'assembly_top.png'))
    run('rsvg-convert', '-f', 'pdf', asm,
        '-o', os.path.join(OUT, 'assembly_top.pdf'))
    for f in os.listdir(GERB):
        os.remove(os.path.join(GERB, f))
    run(CLI, 'pcb', 'export', 'gerbers', '--layers', LAYERS, '--check-zones',
        '--subtract-soldermask', '-o', GERB + os.sep, PCB)
    # drill files as JLCPCB's KiCad guide asks: Excellon, millimetres,
    # decimal, absolute origin, "alternate" mode for the jacks' slots;
    # plated and unplated holes in separate files
    run(CLI, 'pcb', 'export', 'drill', '--format', 'excellon',
        '--excellon-separate-th', '-o', GERB + os.sep, PCB)
    with zipfile.ZipFile(os.path.join(FAB, 'bldc_driver_board_gerbers.zip'),
                         'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(GERB)):
            z.write(os.path.join(GERB, f), f)
    n_pos, turned = placement()
    print(f'exported: STEP, 3 renders, signal map, assembly drawing, '
          f'{len(os.listdir(GERB))} Gerber/drill files, placement file '
          f'({n_pos} parts; rotation offsets applied to '
          f'{", ".join(sorted(turned))}), BOM ({n_bom} lines; {n_smd} '
          f'without the through-hole parts)')


if __name__ == '__main__':
    main()
