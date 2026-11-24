"""Send commands to the KiCAD MCP server's Python worker from the shell.

The MCP tools take their arguments inline; for the big schematic payloads
(80 parts, 300 pin connections) this feeds the same worker the same
commands from JSON files instead, so nothing is retyped.

    python3 kicad_cmd.py <command> <params.json | inline-json> [more pairs...]

Uses the paths from the desktop app's MCP config for the "kicad" server.
"""
import json
import os
import subprocess
import sys

CFG = os.path.expanduser(
    '~/Library/Application Support/Claude/claude_desktop_config.json')


def worker_env_and_script():
    k = json.load(open(CFG))['mcpServers']['kicad']
    env = dict(os.environ)
    env.update(k.get('env', {}))
    server_js = k['args'][0]
    script = os.path.join(os.path.dirname(os.path.dirname(server_js)),
                          'python', 'kicad_interface.py')
    return env, env['KICAD_PYTHON'], script


def run(commands):
    env, py, script = worker_env_and_script()
    p = subprocess.Popen([py, script], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         env=env, text=True, cwd=os.path.dirname(script))
    ready = p.stdout.readline()
    out = []
    for name, params in commands:
        p.stdin.write(json.dumps({'command': name, 'params': params}) + '\n')
        p.stdin.flush()
        line = p.stdout.readline()
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({'raw': line})
    p.stdin.close()
    p.wait(timeout=30)
    return ready, out


if __name__ == '__main__':
    args = sys.argv[1:]
    cmds = []
    for name, src in zip(args[0::2], args[1::2]):
        params = json.load(open(src)) if os.path.exists(src) else json.loads(src)
        cmds.append((name, params))
    ready, res = run(cmds)
    for (name, _), r in zip(cmds, res):
        s = json.dumps(r)
        print(f'--- {name}: {s[:1500]}{" ..." if len(s) > 1500 else ""}')
