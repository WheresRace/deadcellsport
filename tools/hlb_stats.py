import sys, time, json, collections
sys.path.insert(0, __import__('os').path.dirname(__file__))
import hlb

path = sys.argv[1]
data = open(path, 'rb').read()
t0 = time.time()
c = hlb.read(data)
print('parsed in %.1fs, consumed %d / %d bytes' % (time.time() - t0, c.end, len(data)))
print('version', c.version, 'flags', c.flags, 'entry', c.entrypoint)
print('ints', len(c.ints), 'floats', len(c.floats), 'strings', len(c.strings), 'debugfiles', len(c.debug_files))
print('types', len(c.types), 'globals', len(c.globals), 'natives', len(c.natives), 'functions', len(c.functions), 'constants', len(c.constants))
print('total ops', sum(len(f.ops) for f in c.functions))
kinds = collections.Counter(hlb.KIND_NAMES[t.kind] for t in c.types)
print('type kinds', dict(kinds))
libs = collections.defaultdict(list)
for lib, name, t, fi in c.natives:
    libs[lib].append(name)
print('native libs:')
for lib in sorted(libs, key=lambda l: -len(libs[l])):
    print('  %-12s %d' % (lib, len(libs[lib])))
pkgs = collections.Counter()
for t in c.types:
    if t.kind == hlb.HOBJ and t.name:
        pkgs[t.name.split('.')[0] if '.' in t.name else '(root)'] += 1
print('top-level packages:', pkgs.most_common(40))
out = sys.argv[2]
json.dump({'natives': {l: sorted(n) for l, n in libs.items()},
           'debug_files': c.debug_files}, open(out, 'w'), indent=1)
print('wrote', out)
