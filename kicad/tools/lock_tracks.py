"""Lock every existing track and via, ready for autorouting.

    KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $KPY tools/lock_tracks.py

Locked copper is exported to the autorouter as fixed, and KiCad keeps it
when the routed session is imported (the import replaces only unlocked
tracks). Run once, on the board as build_board.py left it; the board is
first copied to build/pre_autoroute.kicad_pcb.
"""
import json
import os
import shutil

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
PCB = os.path.join(PRJ, 'bldc_driver_board.kicad_pcb')
BACKUP = os.path.join(PRJ, 'build', 'pre_autoroute.kicad_pcb')


def main():
    shutil.copyfile(PCB, BACKUP)
    # pcbnew may rewrite the project files when it saves a board: keep ours
    keep = {}
    for ext in ('.kicad_pro', '.kicad_prl'):
        p = PCB.replace('.kicad_pcb', ext)
        if os.path.exists(p):
            keep[p] = open(p).read()
    board = pcbnew.LoadBoard(PCB)
    # The first time this runs on a freshly built board, every track on it
    # is build_board.py's own. Remember which, so that autoroute.py's
    # clean-up steps can tell them from autorouted copper later (all of it
    # ends up locked). build_board.py deletes this file on each rebuild.
    hand = os.path.join(PRJ, 'build', 'handrouted.json')
    if not os.path.exists(hand):
        json.dump([t.m_Uuid.AsString() for t in board.GetTracks()],
                  open(hand, 'w'))
    n = 0
    for t in board.GetTracks():
        t.SetLocked(True)
        n += 1
    # For the autorouter only (KiCad's rules allow these places): the strip
    # between the two pads of every two-pad surface-mount part, as rectangles
    # in KiCad page millimetres. autoroute.py turns them into keep-outs in
    # the file it gives Freerouting.
    rects = []
    for fp in board.GetFootprints():
        pads = [p for p in fp.Pads() if p.GetNumber()]
        if len(pads) != 2 or any(p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                                 for p in pads):
            continue
        a, b = (p.GetBoundingBox() for p in pads)
        if a.GetRight() < b.GetLeft() or b.GetRight() < a.GetLeft():
            x0, x1 = sorted((min(a.GetRight(), b.GetRight()),
                             max(a.GetLeft(), b.GetLeft())))
            y0, y1 = min(a.GetTop(), b.GetTop()), max(a.GetBottom(), b.GetBottom())
        else:
            y0, y1 = sorted((min(a.GetBottom(), b.GetBottom()),
                             max(a.GetTop(), b.GetTop())))
            x0, x1 = min(a.GetLeft(), b.GetLeft()), max(a.GetRight(), b.GetRight())
        rects.append([pcbnew.ToMM(v) for v in (x0, y0, x1, y1)])
    # ... and the clear area round each fiducial (its 0.6 mm pad clearance
    # is not something the router is told)
    for fp in board.GetFootprints():
        if fp.GetReference().startswith('FID'):
            p, r = fp.GetPosition(), pcbnew.FromMM(1.8)
            rects.append([pcbnew.ToMM(v)
                          for v in (p.x - r, p.y - r, p.x + r, p.y + r)])
    json.dump(rects, open(os.path.join(PRJ, 'build', 'router_keepouts.json'), 'w'))
    pcbnew.SaveBoard(PCB, board)
    for p, text in keep.items():
        open(p, 'w').write(text)
    print(f'locked {n} tracks and vias; backup at {BACKUP}')


if __name__ == '__main__':
    main()
