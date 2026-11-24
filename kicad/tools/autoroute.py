"""Autoroute the logic nets with Freerouting, keeping everything
build_board.py routed exactly as it is.

    python3 tools/autoroute.py          (after tools/build_board.py)

Steps:
  1. lock every existing track and via (tools/lock_tracks.py, which also
     copies the board to build/pre_autoroute.kicad_pcb);
  2. export a Specctra DSN through the KiCad MCP server's worker (it adds
     the project's net classes and the edge clearance to the file);
  3. run Freerouting on it;
  4. keep from Freerouting's session only the nets KiCad said were open
     before routing. It also "tidies" nets that are already connected,
     leaving stubs; those are dropped;
  5. import the session (KiCad keeps locked copper, adds the new routes);
  6. refill the planes and run DRC with schematic parity.

Freerouting: ~/.kicad-mcp/freerouting.jar must be a release built for the
Java on this machine. 2.1.0 is the last one for Java 21; 2.2.0 and later
need Java 25. 2.1.0 ignores the "-mp" pass limit the MCP's own autoroute
command passes (it never stops), hence the explicit --router.* settings
here. Analytics and telemetry are switched off on the command line.
"""
import collections
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import kicad_cmd    # noqa: E402

PCB = os.path.join(PRJ, 'bldc_driver_board.kicad_pcb')
PRO = os.path.join(PRJ, 'bldc_driver_board.kicad_pro')
BUILD = os.path.join(PRJ, 'build')
DSN = os.path.join(BUILD, 'board.dsn')
SES = os.path.join(BUILD, 'board.ses')
SES_LOGIC = os.path.join(BUILD, 'board_logic.ses')
JAR = os.path.expanduser('~/.kicad-mcp/freerouting.jar')
KPY = ('/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/'
       'Versions/Current/bin/python3')
KCLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'

def drc(parity=False):
    report = os.path.join(BUILD, 'drc.json')
    cmd = [KCLI, 'pcb', 'drc', '--format', 'json', '--severity-all',
           '--refill-zones', '--save-board', '-o', report, PCB]
    if parity:
        cmd.insert(5, '--schematic-parity')
    subprocess.run(cmd, check=True, capture_output=True)
    return json.load(open(report))


def open_nets():
    """Nets KiCad reports as not fully connected: the ones to autoroute."""
    nets = set()
    for v in drc().get('unconnected_items', []):
        for item in v['items']:
            m = re.search(r'\[([^\]]+)\]', item['description'])
            if m:
                nets.add(m.group(1))
    return nets


def worker(*commands):
    _ready, results = kicad_cmd.run(
        [('open_project', {'filename': PRO})] + list(commands))
    for (name, _), r in zip(commands, results[1:]):
        if not r.get('success'):
            sys.exit(f'{name} failed: {json.dumps(r)[:600]}')
        print(f'{name}: {r.get("message", "")[:120]}')
    return results[1:]


def block_end(s, i):
    depth = 0
    for j in range(i, len(s)):
        if s[j] == '(':
            depth += 1
        elif s[j] == ')':
            depth -= 1
            if depth == 0:
                return j + 1
    raise ValueError('unbalanced session file')


def wanted_only(src, dst, wanted):
    t = open(src).read()
    start = t.index('(network_out')
    end = block_end(t, start)
    body = t[start:end]
    pieces, kept, i = [], [], len('(network_out')
    pieces.append(body[:i])
    net = re.compile(r'\(net\s+("?[^\s")]+"?)')
    while True:
        m = net.search(body, i)
        if not m:
            break
        e = block_end(body, m.start())
        if m.group(1).strip('"') in wanted:
            pieces.append('\n      ' + body[m.start():e])
            kept.append(m.group(1).strip('"'))
        i = e
    pieces.append(body[i:])
    open(dst, 'w').write(t[:start] + ''.join(pieces) + t[end:])
    print(f'session: kept {len(kept)} of the {len(wanted)} nets that were open')


GROW = 600          # um added to every through-hole pad's size (0.3 mm a side)
OX, OY = 100.0, 162.05      # board frame -> KiCad page, as in build_board.py
# under the barrel jacks, board frame (x0, y0, x1, y1): the barrel, and the
# strip between the two pins on the axis
JACK_AREAS = [(0.3, 41.3, 6.2, 50.2), (8.9, 43.2, 12.2, 50.2),
              (73.8, 41.3, 79.7, 50.2), (67.8, 41.3, 71.1, 49.1)]


def tune_dsn():
    """Constraints for Freerouting that KiCad's rules do not carry.
    1. Through-hole pads are described 0.3 mm larger all round, so signal
       tracks keep 0.5 mm from hand-soldered joints instead of 0.2.
    2. Keep-outs on the top layer between the pads of two-pad parts and
       under the jacks.
    Only the copy handed to Freerouting is changed; the board is not."""
    lines = open(DSN).read().split('\n')
    out, i, dims = [], 0, None
    while i < len(lines):
        ln = lines[i]
        m = re.match(r'\s*\(padstack "?\w+\[A\]Pad_([\d.]+)(?:x([\d.]+))?', ln)
        if m:
            w = float(m.group(1))
            h = float(m.group(2) or m.group(1))
            dims = (w, h) if min(w, h) >= 1400 else None
        elif ln.strip() == ')':
            dims = None
        if dims and '(shape (circle' in ln:
            ln = re.sub(r'(\(circle \S+ )([\d.]+)',
                        lambda k: k.group(1) + str(float(k.group(2)) + GROW), ln)
        elif dims and '(shape (path' in ln:
            ln = re.sub(r'(\(path \S+ )([\d.]+)',
                        lambda k: k.group(1) + str(float(k.group(2)) + GROW), ln)
        elif dims and '(shape (rect' in ln:
            k = re.match(r'(\s*\(shape \(rect \S+) (\S+) (\S+) (\S+) (\S+)\)\)', ln)
            x0, y0, x1, y1 = (float(v) for v in k.groups()[1:])
            g = GROW / 2
            ln = f'{k.group(1)} {x0 - g} {y0 - g} {x1 + g} {y1 + g}))'
        elif dims and '(shape (polygon' in ln:
            block = [ln]
            while not block[-1].rstrip().endswith('))'):
                i += 1
                block.append(lines[i])
            text = ' '.join(block)
            k = re.match(r'(\s*\(shape \(polygon \S+ \S+)(.*)\)\)\s*$', text)
            nums = [float(v) for v in k.group(2).split()]
            sx, sy = (dims[0] + GROW) / dims[0], (dims[1] + GROW) / dims[1]
            nums = [v * (sx if j % 2 == 0 else sy) for j, v in enumerate(nums)]
            ln = k.group(1) + ' ' + ' '.join(f'{v:.3f}' for v in nums) + '))'
        out.append(ln)
        i += 1
    rects = json.load(open(os.path.join(BUILD, 'router_keepouts.json')))
    rects += [(OX + x0, OY - y1, OX + x1, OY - y0) for x0, y0, x1, y1 in JACK_AREAS]
    extra = []
    for x0, y0, x1, y1 in rects:
        if x1 - x0 < 0.05 or y1 - y0 < 0.05:
            continue
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        extra.append('    (keepout "" (polygon F.Cu 0  ' + '  '.join(
            f'{round(x * 1000)} {round(-y * 1000)}' for x, y in pts) + '))')
    at = next(j for j, ln in enumerate(out) if ln.lstrip().startswith('(keepout'))
    out[at:at] = extra
    open(DSN, 'w').write('\n'.join(out))
    print(f'router constraints: {len(extra)} extra keep-outs, through-hole pads '
          f'grown by {GROW / 2000:.1f} mm a side')


def _remove(ids):
    """Delete autorouted tracks / vias by uuid. build_board.py's own copper
    (listed in build/handrouted.json by lock_tracks.py) is never touched.
    The board file is edited as text because pcbnew's Python API cannot
    safely remove items."""
    hand = set(json.load(open(os.path.join(BUILD, 'handrouted.json'))))
    t = open(PCB).read()
    n = 0
    for uid in set(ids) - hand:
        k = t.find(f'(uuid "{uid}")')
        if k < 0:
            continue
        start = max(t.rfind('\n\t(segment', 0, k), t.rfind('\n\t(via', 0, k),
                    t.rfind('\n\t(arc', 0, k))
        if start < 0:
            continue
        end = block_end(t, start + 2)
        if end < k:             # the uuid belongs to something else (a pad)
            continue
        t = t[:start] + t[end:]
        n += 1
    if n:
        open(PCB, 'w').write(t)
    return n


def _offenders(types):
    ids = set()
    for v in drc().get('violations', []):
        if v['type'] in types:
            ids.update(i['uuid'] for i in v['items'] if i.get('uuid'))
    return ids


def prune_dangling():
    """Remove autorouted track ends and vias that lead nowhere, repeating
    until none are left."""
    removed = 0
    for _ in range(6):
        n = _remove(_offenders(('track_dangling', 'via_dangling')))
        if not n:
            break
        removed += n
    return removed


def remove_violators():
    """Remove autorouted copper that KiCad's DRC rejects (the router is not
    told everything KiCad knows); the next round routes those nets again."""
    return _remove(_offenders(('clearance', 'hole_clearance', 'shorting_items',
                               'solder_mask_bridge', 'tracks_crossing',
                               'items_not_allowed', 'copper_edge_clearance')))


def route_once(strict=True):
    """One lock / export / route / import round. Returns nets still open.
    strict=False leaves out tune_dsn()'s extra constraints (KiCad's own
    rules still apply), for nets the router cannot place under them."""
    subprocess.run([KPY, os.path.join(HERE, 'lock_tracks.py')], check=True,
                   stderr=subprocess.DEVNULL)
    for f in (DSN, SES, SES_LOGIC):
        if os.path.exists(f):
            os.remove(f)
    wanted = open_nets()
    if not wanted:
        return wanted
    print(f'{len(wanted)} nets to route')
    worker(('export_dsn', {'boardPath': PCB, 'outputPath': DSN}))
    if strict:
        tune_dsn()
    else:
        print('RELAXED round (no extra router constraints) for: '
              + ', '.join(sorted(wanted)))
    cmd = ['/usr/bin/java', '-jar', JAR, '-de', DSN, '-do', SES,
           '--gui.enabled=false', '-mt', '1', '-da',
           '--usage_and_diagnostic_data.disable_analytics=true',
           '--profile.allow_telemetry=false',
           '--router.max_passes=40', '--router.optimizer.max_passes=2',
           '--router.job_timeout=00:05:00']
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=420, cwd=BUILD)
    except subprocess.TimeoutExpired:
        sys.exit('Freerouting did not finish in 420 s')
    if not os.path.exists(SES):
        sys.exit('Freerouting wrote no session file')
    wanted_only(SES, SES_LOGIC, wanted)
    worker(('import_ses', {'sesPath': SES_LOGIC}))
    # before the next round locks this round's copper
    n = prune_dangling()
    if n:
        print(f'removed {n} dangling autorouted stubs')
    return open_nets()


def main():
    # Freerouting sometimes leaves a few nets; a second round, with the
    # first round's routes fixed, usually finishes them.
    # Three rounds under the extra constraints, then up to two without them
    # for whatever is still open. `--relaxed` starts with the relaxed rounds
    # (to finish a board whose strict rounds have already run).
    first_relaxed = 0 if '--relaxed' in sys.argv else 3
    for attempt in range(first_relaxed + 2):
        left = route_once(strict=attempt < first_relaxed)
        bad = remove_violators()
        if bad:
            print(f'round {attempt + 1}: removed {bad} autorouted items '
                  f'that failed DRC, to be routed again')
        elif not left:
            break
        if left:
            print(f'round {attempt + 1}: still open: {sorted(left)}')
    d = drc(parity='--parity' in sys.argv)
    for key in ('violations', 'unconnected_items', 'schematic_parity'):
        items = d.get(key, [])
        print(f'DRC {key}: {len(items)}',
              dict(collections.Counter(v['type'] for v in items)))


if __name__ == '__main__':
    main()
