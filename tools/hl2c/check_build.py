import os, sys, subprocess, concurrent.futures, re

EMCC = r"C:\Users\NKTRa\deadcellsport\toolchain\emsdk\upstream\emscripten\emcc.exe"
ROOT = r"C:\Users\NKTRa\deadcellsport"
SRC = os.path.join(ROOT, 'build', 'c')
OBJ = os.path.join(ROOT, 'build', 'obj')
INC = os.path.join(ROOT, 'third_party', 'hashlink', 'src')
FLAGS = sys.argv[1:] or ['-O0']


def build(name):
    out = os.path.join(OBJ, name[:-2] + '.o')
    p = subprocess.run([EMCC, '-c', os.path.join(SRC, name), '-o', out, '-I', INC, '-fwrapv', '-w', '-ferror-limit=0'] + FLAGS,
                       capture_output=True, text=True, errors='replace')
    return name, p.returncode, p.stderr


os.makedirs(OBJ, exist_ok=True)
files = sorted(f for f in os.listdir(SRC) if f.endswith('.c'))
errors = []
with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as ex:
    for name, rc, err in ex.map(build, files):
        msgs = [l for l in err.splitlines() if ': error:' in l]
        if rc:
            errors.extend((name, m) for m in msgs)
        print('%-14s %s %d errors' % (name, 'ok ' if rc == 0 else 'ERR', len(msgs)), flush=True)
kinds = {}
for name, m in errors:
    k = re.sub(r'.*error: ', '', m)
    k = re.sub(r"'[^']*'", "'_'", k)
    kinds.setdefault(k, []).append(m)
print('\nfailed files:', len({n for n, _ in errors}), 'total errors:', len(errors))
for k, v in sorted(kinds.items(), key=lambda kv: -len(kv[1]))[:25]:
    print('%6d  %s\n        e.g. %s' % (len(v), k, v[0][-200:]))
