import sys, os, collections
sys.path.insert(0, os.path.dirname(__file__))
import hlb


def function_names(c):
    names = {}
    for t in c.types:
        if t.kind != hlb.HOBJ:
            continue
        for name, findex, _ in t.protos:
            names.setdefault(findex, '%s.%s' % (t.name, name))
        for fid, findex in t.bindings:
            fields = []
            s = t
            chain = []
            while s:
                chain.append(s)
                s = s.super
            for s in reversed(chain):
                fields.extend(s.fields)
            fname = fields[fid][0] if fid < len(fields) else '#%d' % fid
            owner = t.name[1:] if t.name.startswith('$') else t.name
            names.setdefault(findex, '%s.%s' % (owner, fname))
    for lib, name, _, findex in c.natives:
        names[findex] = '@%s.%s' % (lib, name)
    return names


def fmt_op(c, names, op, args):
    name, n = hlb.OPCODES[op]
    if name in hlb.VARARG_CALLS:
        a, b, rest = args
        if name == 'CallN':
            return '%s r%d = %s(%s)' % (name, a, names.get(b, 'f%d' % b), ', '.join('r%d' % x for x in rest))
        return '%s r%d %d (%s)' % (name, a, b, ', '.join('r%d' % x for x in rest))
    if name == 'Switch':
        a, offs, end = args
        return 'Switch r%d [%s] end %d' % (a, ','.join(map(str, offs)), end)
    if name == 'String':
        return 'String r%d = %r' % (args[0], c.strings[args[1]][:80])
    if name == 'Int':
        return 'Int r%d = %d' % (args[0], c.ints[args[1]])
    if name == 'Float':
        return 'Float r%d = %r' % (args[0], c.floats[args[1]])
    if name.startswith('Call') and name[4:].isdigit():
        return '%s r%d = %s(%s)' % (name, args[0], names.get(args[1], 'f%d' % args[1]), ', '.join('r%d' % x for x in args[2:]))
    if name in ('StaticClosure',):
        return '%s r%d = %s' % (name, args[0], names.get(args[1], 'f%d' % args[1]))
    if name in ('GetGlobal', 'SetGlobal'):
        g = c.globals[args[1]] if name == 'GetGlobal' else c.globals[args[0]]
        return '%s %s  ; %s' % (name, ' '.join(map(str, args)), hlb.type_name(g))
    return '%s %s' % (name, ' '.join(str(x) for x in args))


def main(path, out_dir):
    c = hlb.read(open(path, 'rb').read())
    names = function_names(c)
    groups = collections.defaultdict(list)
    for f in c.functions:
        fid = f.debug[0] if f.debug else -1
        groups[fid].append(f)
    os.makedirs(out_dir, exist_ok=True)
    index = []
    for fid, funcs in groups.items():
        src = c.debug_files[fid] if fid >= 0 else 'unknown.hx'
        rel = src.replace(chr(92), '/')
        if ':' in rel:
            rel = 'std/' + rel.split('/std/', 1)[-1] if '/std/' in rel else 'abs/' + rel.split('/')[-1]
        rel = ''.join(ch if ch.isalnum() or ch in '/._-' else '_' for ch in rel)
        dst = os.path.join(out_dir, rel + '.hlasm')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'w', encoding='utf-8') as o:
            for f in sorted(funcs, key=lambda f: f.debug[1] if f.debug else 0):
                fname = names.get(f.findex, 'f%d' % f.findex)
                index.append('%d\t%s\t%s' % (f.findex, fname, rel))
                o.write('fn %s  #%d  %s\n' % (fname, f.findex, hlb.type_name(f.type)))
                for i, t in enumerate(f.regs):
                    o.write('  reg r%d: %s\n' % (i, hlb.type_name(t)))
                for i, (op, args) in enumerate(f.ops):
                    line = f.debug[i * 2 + 1] if f.debug else 0
                    o.write('  %5d L%-5d %s\n' % (i, line, fmt_op(c, names, op, args)))
                o.write('\n')
    open(os.path.join(out_dir, 'INDEX.tsv'), 'w', encoding='utf-8').write('\n'.join(sorted(index, key=lambda l: int(l.split('\t')[0]))))
    print('files', len(groups), 'functions', len(index), 'named', sum(1 for l in index if not l.split('\t')[1].startswith('f')))


main(sys.argv[1], sys.argv[2])
