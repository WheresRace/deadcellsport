import os, sys, math, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import hlb
from hlb import *

OPS = {name: i for i, (name, _) in enumerate(hlb.OPCODES)}
NON_PTR = {HVOID, HUI8, HUI16, HI32, HI64, HF32, HF64, HBOOL, HGUID}
INT_KINDS = {HUI8, HUI16, HI32, HI64, HBOOL}
FLOAT_KINDS = {HF32, HF64}
CTYPE = {HVOID: 'void', HUI8: 'unsigned char', HUI16: 'unsigned short', HI32: 'int', HI64: 'int64', HF32: 'float',
         HF64: 'double', HBOOL: 'bool', HBYTES: 'vbyte*', HTYPE: 'hl_type*', HGUID: 'int64'}
DYN_FIELD = {HUI8: 'ui8', HUI16: 'ui16', HI32: 'i', HI64: 'i64', HGUID: 'i64', HF32: 'f', HF64: 'd', HBOOL: 'b'}
CLASS_CHAR = {HVOID: 'v', HUI8: 'c', HUI16: 's', HI32: 'i', HI64: 'l', HGUID: 'l', HF32: 'f', HF64: 'd', HBOOL: 'b'}


def is_ptr(t):
    return t.kind not in NON_PTR


def ctype(t):
    return CTYPE.get(t.kind, 'void*')


def cls(t):
    return CLASS_CHAR.get(t.kind, 'p')


def dyn_prefix(t):
    k = t.kind
    if k in (HUI8, HUI16, HI32, HBOOL):
        return 'i'
    if k in (HI64, HGUID):
        return 'i64'
    if k == HF32:
        return 'f'
    if k == HF64:
        return 'd'
    return 'p'


def cfloat(v, f32=False):
    if math.isnan(v):
        return '(float)NAN' if f32 else 'NAN'
    if math.isinf(v):
        s = 'INFINITY' if v > 0 else '(-INFINITY)'
        return s
    s = repr(float(v))
    if 'e' not in s and '.' not in s:
        s += '.'
    return s + ('f' if f32 else '')


def cstr(s):
    out = []
    for ch in s.encode('utf-8'):
        if ch in (0x22, 0x5c):
            out.append('\\' + chr(ch))
        elif 32 <= ch < 127 and ch != 0x3f:
            out.append(chr(ch))
        else:
            out.append('\\%03o' % ch)
    return '"' + ''.join(out) + '"'


class Gen:
    def __init__(self, code):
        self.c = code
        self.tid = {id(t): i for i, t in enumerate(code.types)}
        self.ftypes = {}
        self.is_native = set()
        for f in code.functions:
            self.ftypes[f.findex] = f.type
        for lib, name, t, findex in code.natives:
            self.ftypes[findex] = t
            self.is_native.add(findex)
        self.offsets = []
        self.offset_ids = {}
        self.sigs = {}
        for f in code.functions:
            self.add_sig(f.type)
        for t in code.types:
            if t.kind in (HFUN, HMETHOD):
                self.add_sig(t)
        self.compare_fun = {}

    def ti(self, t):
        return self.tid[id(t)]

    def T(self, t):
        return 'T(%d)' % self.ti(t)

    def add_sig(self, t):
        key = ''.join(cls(a) for a in t.args) + '_' + cls(t.ret)
        if key not in self.sigs:
            self.sigs[key] = (t.args, t.ret)
        return key

    def off(self, kind, t, a, b=0):
        key = (kind, self.ti(t), a, b)
        i = self.offset_ids.get(key)
        if i is None:
            i = len(self.offsets)
            self.offsets.append(key)
            self.offset_ids[key] = i
        return 'O(%d)' % i

    def obj_fields(self, t):
        chain = []
        s = t
        while s:
            chain.append(s)
            s = s.super
        out = []
        for s in reversed(chain):
            out.extend(s.fields)
        return out

    def obj_compare(self, t):
        k = self.ti(t)
        if k in self.compare_fun:
            return self.compare_fun[k]
        found = None
        s = t
        while s and found is None:
            for name, findex, _ in s.protos:
                if name == '__compare':
                    found = findex
                    break
            s = s.super
        self.compare_fun[k] = found
        return found

    def proto_findex(self, t, pindex):
        s = t
        while s:
            for name, findex, pi in s.protos:
                if pi == pindex:
                    return findex
            s = s.super
        return None

    def fsig_cast(self, args, ret, expr):
        a = ','.join(ctype(x) if x.kind != HVOID else 'void*' for x in args) or 'void'
        return '((%s(*)(%s))%s)' % (ctype(ret), a, expr)

    def fdecl(self, findex):
        t = self.ftypes[findex]
        a = ','.join(ctype(x) for x in t.args) or 'void'
        return '%s f%d(%s);' % (ctype(t.ret), findex, a)

    def callee(self, findex, needed):
        if findex in self.is_native:
            t = self.ftypes[findex]
            return self.fsig_cast(t.args, t.ret, 'F(%d)' % findex)
        needed.add(findex)
        return 'f%d' % findex

    def function(self, f, needed):
        c = self.c
        regs = f.regs
        ft = f.type
        nargs = len(ft.args)
        out = []
        w = out.append
        args = ','.join('%s r%d' % (ctype(regs[i]), i) for i in range(nargs)) or 'void'
        w('%s f%d(%s) {' % (ctype(ft.ret), f.findex, args))
        decls = collections.defaultdict(list)
        for i in range(nargs, len(regs)):
            if regs[i].kind != HVOID:
                decls[ctype(regs[i])].append('r%d = 0' % i)
        for ty, names in decls.items():
            for nm in names:
                w('\t%s %s;' % (ty, nm))
        ops = f.ops
        targets = set()
        trap_depth = 0
        max_trap = 0
        for i, (op, a) in enumerate(ops):
            name = hlb.OPCODES[op][0]
            if name.startswith('J') or name == 'Trap':
                targets.add(i + 1 + a[-1])
            elif name == 'Switch':
                for o in a[1]:
                    targets.add(i + 1 + o)
                targets.add(i + 1 + a[2])
            if name == 'Trap':
                trap_depth += 1
                max_trap = max(max_trap, trap_depth)
            elif name == 'EndTrap' and a[0]:
                trap_depth -= 1
        for i in range(max_trap):
            w('\thl_trap_ctx trap%d;' % i)
        trap_depth = 0
        rt = lambda r: regs[r]
        R = lambda r: 'r%d' % r

        def label(i, d):
            return 'L%d' % (i + 1 + d)

        def assign(r, t):
            if rt(r).kind == HVOID or t.kind == HVOID:
                return ''
            return 'r%d = (%s)' % (r, ctype(rt(r)))

        def call(r, findex, argregs):
            t = self.ftypes[findex]
            fn = self.callee(findex, needed)
            cargs = ','.join(R(x) if rt(x).kind != HVOID else '0' for x in argregs)
            return '%s%s(%s);' % (assign(r, t.ret), fn, cargs)

        def field_get(r, o, fid):
            ot = rt(o)
            if ot.kind in (HOBJ, HSTRUCT):
                fname, ftyp = self.obj_fields(ot)[fid]
                return '%s*(%s*)((char*)%s + %s);' % (assign(r, ftyp), ctype(ftyp), R(o), self.off('o', ot, fid))
            if ot.kind == HVIRTUAL:
                fname, ftyp = ot.fields[fid]
                tv = (',' + self.T(ftyp)) if dyn_prefix(ftyp) in ('i', 'p') else ''
                return '%s(hl_vfields(%s)[%d] ? *(%s*)hl_vfields(%s)[%d] : (%s)hl_dyn_get%s((vdynamic*)((vvirtual*)%s)->value,%s->virt->fields[%d].hashed_name%s));' % (
                    assign(r, ftyp), R(o), fid, ctype(ftyp), R(o), fid, ctype(ftyp), dyn_prefix(ftyp), R(o), self.T(ot), fid, tv)
            raise ValueError('field on %s' % hlb.type_name(ot))

        def field_set(o, fid, v):
            ot = rt(o)
            if ot.kind in (HOBJ, HSTRUCT):
                fname, ftyp = self.obj_fields(ot)[fid]
                return '*(%s*)((char*)%s + %s) = (%s)%s;' % (ctype(ftyp), R(o), self.off('o', ot, fid), ctype(ftyp), R(v))
            if ot.kind == HVIRTUAL:
                fname, ftyp = ot.fields[fid]
                tv = (',' + self.T(rt(v))) if dyn_prefix(ftyp) in ('i', 'p') else ''
                return 'if( hl_vfields(%s)[%d] ) *(%s*)hl_vfields(%s)[%d] = (%s)%s; else hl_dyn_set%s((vdynamic*)((vvirtual*)%s)->value,%s->virt->fields[%d].hashed_name%s,%s);' % (
                    R(o), fid, ctype(ftyp), R(o), fid, ctype(ftyp), R(v), dyn_prefix(ftyp), R(o), self.T(ot), fid, tv, R(v))
            raise ValueError('setfield on %s' % hlb.type_name(ot))

        def method_call(r, fid, argregs):
            o = argregs[0]
            ot = rt(o)
            rest = argregs[1:]
            if ot.kind in (HOBJ, HSTRUCT):
                fn = self.fsig_cast([ot] + [rt(x) for x in rest], rt(r), '((vdynamic*)%s)->t->vobj_proto[%d]' % (R(o), fid))
                return '%s%s(%s);' % (assign(r, rt(r)), fn, ','.join(R(x) for x in argregs))
            if ot.kind == HVIRTUAL:
                fname, ftyp = ot.fields[fid]
                ret = rt(r)
                fn = self.fsig_cast([c.types[9]] + [rt(x) for x in rest], ret, 'hl_vfields(%s)[%d]' % (R(o), fid))
                direct = '%s%s(%s);' % (assign(r, ret), fn, ','.join(['((vvirtual*)%s)->value' % R(o)] + [R(x) for x in rest]))
                vargs = ','.join(R(x) if is_ptr(rt(x)) else '&' + R(x) for x in rest)
                s = 'if( hl_vfields(%s)[%d] ) %s else { ' % (R(o), fid, direct)
                if rest:
                    s += 'void *args[] = {%s}; ' % vargs
                aa = 'args' if rest else 'NULL'
                if ret.kind == HVOID:
                    s += 'hl_dyn_call_obj(((vvirtual*)%s)->value,%s,%s->virt->fields[%d].hashed_name,%s,NULL); }' % (R(o), self.T(ftyp), self.T(ot), fid, aa)
                elif is_ptr(ret):
                    s += '%s = (%s)hl_dyn_call_obj(((vvirtual*)%s)->value,%s,%s->virt->fields[%d].hashed_name,%s,NULL); }' % (R(r), ctype(ret), R(o), self.T(ftyp), self.T(ot), fid, aa)
                else:
                    s += 'vdynamic ret; hl_dyn_call_obj(((vvirtual*)%s)->value,%s,%s->virt->fields[%d].hashed_name,%s,&ret); %s = (%s)ret.v.%s; }' % (
                        R(o), self.T(ftyp), self.T(ot), fid, aa, R(r), ctype(ret), DYN_FIELD[ret.kind])
                return s
            raise ValueError('method on %s' % hlb.type_name(ot))

        def compare(i, opname, a, b, d):
            ta, tb = rt(a), rt(b)
            cmp = {'JSLt': '<', 'JSGte': '>=', 'JSGt': '>', 'JSLte': '<=', 'JEq': '==', 'JNotEq': '!='}[opname]
            L = label(i, d)
            ka, kb = ta.kind, tb.kind
            num = INT_KINDS | FLOAT_KINDS
            if (ka in num and kb in num) or (ka == kb == HBYTES) or (ka == kb == HARRAY) or ka in (HENUM, HDYNOBJ, HABSTRACT, HSTRUCT, HREF, HMETHOD, HPACKED) and ka == kb:
                return 'if( %s %s (%s)%s ) goto %s;' % (R(a), cmp, ctype(ta), R(b), L)
            if ka == kb == HTYPE:
                return 'if( hl_same_type(%s,%s) %s 0 ) {} else goto %s;' % (R(a), R(b), cmp, L)
            if ka == HNULL and kb == HNULL:
                fld = 'v.' + DYN_FIELD.get(ta.tparam.kind, 'ptr')
                pc = '(((vdynamic*)%s)->%s %s ((vdynamic*)%s)->%s)' % (R(a), fld, cmp, R(b), fld)
                if cmp == '==':
                    return 'if( %s == %s || (%s && %s && %s) ) goto %s;' % (R(a), R(b), R(a), R(b), pc, L)
                if cmp == '!=':
                    return 'if( %s != %s && (!%s || !%s || %s) ) goto %s;' % (R(a), R(b), R(a), R(b), pc, L)
                return 'if( %s && %s && %s ) goto %s;' % (R(a), R(b), pc, L)
            if ka in (HDYN, HFUN) or kb in (HDYN, HFUN):
                inv = '&& i != hl_invalid_comparison ' if cmp in ('>', '>=') else ''
                return '{ int i = hl_dyn_compare((vdynamic*)%s,(vdynamic*)%s); if( i %s 0 %s) goto %s; }' % (R(a), R(b), cmp, inv, L)
            if ka == HOBJ and kb == HOBJ:
                cf = self.obj_compare(ta)
                if cf is None:
                    return 'if( %s %s %s ) goto %s;' % (R(a), cmp, R(b), L)
                fn = self.callee(cf, needed)
                call_ = '%s(%s,(vdynamic*)%s)' % (fn, R(a), R(b))
                if cmp == '==':
                    return 'if( %s == %s || (%s && %s && %s == 0) ) goto %s;' % (R(a), R(b), R(a), R(b), call_, L)
                if cmp == '!=':
                    return 'if( %s != %s && (!%s || !%s || %s != 0) ) goto %s;' % (R(a), R(b), R(a), R(b), call_, L)
                return 'if( %s && %s && %s %s 0 ) goto %s;' % (R(a), R(b), call_, cmp, L)
            if ka == kb == HVIRTUAL:
                va, vb = '((vvirtual*)%s)->value' % R(a), '((vvirtual*)%s)->value' % R(b)
                if cmp == '==':
                    return 'if( %s == %s || (%s && %s && %s && %s && %s == %s) ) goto %s;' % (R(a), R(b), R(a), R(b), va, vb, va, vb, L)
                return 'if( %s != %s && (!%s || !%s || !%s || !%s || %s != %s) ) goto %s;' % (R(a), R(b), R(a), R(b), va, vb, va, vb, L)
            if ka == HVIRTUAL and kb == HOBJ:
                va = '((vvirtual*)%s)->value' % R(a)
                if cmp == '==':
                    return 'if( %s ? (%s && %s == (vdynamic*)%s) : (%s == NULL) ) goto %s;' % (R(a), R(b), va, R(b), R(b), L)
                return 'if( %s ? (%s == NULL || %s != (vdynamic*)%s) : (%s != NULL) ) goto %s;' % (R(a), R(b), va, R(b), R(b), L)
            if ka == HOBJ and kb == HVIRTUAL:
                return compare(i, opname, b, a, d)
            return 'if( (void*)%s %s (void*)%s ) goto %s;' % (R(a), cmp, R(b), L)

        for i, (op, a) in enumerate(ops):
            if i in targets:
                w('L%d:;' % i)
            name = hlb.OPCODES[op][0]
            s = None
            if name == 'Mov':
                if rt(a[0]).kind != HVOID:
                    s = '%s = (%s)%s;' % (R(a[0]), ctype(rt(a[0])), R(a[1]))
            elif name == 'Int':
                v = c.ints[a[1]]
                s = '%s = %s;' % (R(a[0]), '(int)0x80000000' if v == -0x80000000 else str(v))
            elif name == 'Float':
                s = '%s = %s;' % (R(a[0]), cfloat(c.floats[a[1]], rt(a[0]).kind == HF32))
            elif name == 'Bool':
                s = '%s = %s;' % (R(a[0]), 'true' if a[1] else 'false')
            elif name == 'String':
                s = '%s = S(%d);' % (R(a[0]), a[1])
            elif name == 'Null':
                s = '%s = 0;' % R(a[0])
            elif name in ('Add', 'Sub', 'Mul', 'And', 'Or', 'Xor'):
                o = {'Add': '+', 'Sub': '-', 'Mul': '*', 'And': '&', 'Or': '|', 'Xor': '^'}[name]
                s = '%s = %s %s %s;' % (R(a[0]), R(a[1]), o, R(a[2]))
            elif name == 'SDiv':
                if rt(a[0]).kind in INT_KINDS:
                    s = '%s = (%s == 0 || %s == -1) ? %s * %s : %s / %s;' % (R(a[0]), R(a[2]), R(a[2]), R(a[1]), R(a[2]), R(a[1]), R(a[2]))
                else:
                    s = '%s = %s / %s;' % (R(a[0]), R(a[1]), R(a[2]))
            elif name == 'UDiv':
                s = '%s = %s == 0 ? 0 : ((unsigned)%s) / ((unsigned)%s);' % (R(a[0]), R(a[2]), R(a[1]), R(a[2]))
            elif name == 'SMod':
                k = rt(a[0]).kind
                if k in INT_KINDS:
                    s = '%s = (%s == 0 || %s == -1) ? 0 : %s %% %s;' % (R(a[0]), R(a[2]), R(a[2]), R(a[1]), R(a[2]))
                else:
                    s = '%s = %s(%s,%s);' % (R(a[0]), 'fmodf' if k == HF32 else 'fmod', R(a[1]), R(a[2]))
            elif name == 'UMod':
                s = '%s = %s == 0 ? 0 : ((unsigned)%s) %% ((unsigned)%s);' % (R(a[0]), R(a[2]), R(a[1]), R(a[2]))
            elif name in ('Shl', 'SShr', 'UShr'):
                k = rt(a[0]).kind
                bits = {HUI8: 8, HUI16: 16, HI32: 32, HI64: 64}.get(k, 32)
                if name == 'Shl':
                    s = '%s = %s << (%s %% %d);' % (R(a[0]), R(a[1]), R(a[2]), bits)
                elif name == 'SShr':
                    s = '%s = %s >> (%s %% %d);' % (R(a[0]), R(a[1]), R(a[2]), bits)
                else:
                    s = '%s = ((%s)%s) >> (%s %% %d);' % (R(a[0]), 'uint64' if bits == 64 else 'unsigned', R(a[1]), R(a[2]), bits)
            elif name == 'Neg':
                s = '%s = -%s;' % (R(a[0]), R(a[1]))
            elif name == 'Not':
                s = '%s = !%s;' % (R(a[0]), R(a[1]))
            elif name == 'Incr':
                s = '++%s;' % R(a[0])
            elif name == 'Decr':
                s = '--%s;' % R(a[0])
            elif name.startswith('Call') and name[4:].isdigit():
                s = call(a[0], a[1], a[2:])
            elif name == 'CallN':
                s = call(a[0], a[1], a[2])
            elif name == 'CallMethod':
                s = method_call(a[0], a[1], a[2])
            elif name == 'CallThis':
                s = method_call(a[0], a[1], (0,) + a[2])
            elif name == 'CallClosure':
                r, cl, pl = a
                ct = rt(cl)
                if ct.kind == HDYN:
                    parts = []
                    for p in pl:
                        pt = rt(p)
                        if pt.kind == HDYN or is_ptr(pt) and pt.kind not in (HBYTES, HTYPE, HREF, HMETHOD, HPACKED, HABSTRACT):
                            parts.append('(vdynamic*)%s' % R(p))
                        else:
                            parts.append('hl_make_dyn(&%s,%s)' % (R(p), self.T(pt)))
                    s = '{ '
                    if pl:
                        s += 'vdynamic *args[] = {%s}; ' % ','.join(parts)
                    ret = rt(r)
                    call_ = 'hl_dyn_call((vclosure*)%s,%s,%d)' % (R(cl), 'args' if pl else 'NULL', len(pl))
                    if ret.kind == HVOID:
                        s += call_ + '; }'
                    elif is_ptr(ret) and ret.kind not in (HBYTES, HTYPE, HREF, HMETHOD, HPACKED, HABSTRACT):
                        s += '%s = (%s)%s; }' % (R(r), ctype(ret), call_)
                    else:
                        tv = (',' + self.T(ret)) if dyn_prefix(ret) in ('i', 'p') else ''
                        s += 'vdynamic *ret = %s; %s = (%s)hl_dyn_cast%s(&ret,&hlt_dyn%s); }' % (call_, R(r), ctype(ret), dyn_prefix(ret), tv)
                else:
                    sargs = ','.join(R(p) for p in pl)
                    with_v = self.fsig_cast([c.types[9]] + list(ct.args), ct.ret, '((vclosure*)%s)->fun' % R(cl))
                    no_v = self.fsig_cast(list(ct.args), ct.ret, '((vclosure*)%s)->fun' % R(cl))
                    s = '%s(((vclosure*)%s)->hasValue ? %s((vdynamic*)((vclosure*)%s)->value%s) : %s(%s));' % (
                        assign(r, ct.ret), R(cl), with_v, R(cl), (',' + sargs) if sargs else '', no_v, sargs)
                    if assign(r, ct.ret) == '':
                        s = '((vclosure*)%s)->hasValue ? %s((vdynamic*)((vclosure*)%s)->value%s) : %s(%s);' % (
                            R(cl), with_v, R(cl), (',' + sargs) if sargs else '', no_v, sargs)
            elif name == 'StaticClosure':
                r, fid = a
                fn = self.callee(fid, needed)
                s = '{ static vclosure cl = {0}; if( !cl.fun ) { cl.t = %s; cl.fun = (void*)%s; } %s = &cl; }' % (self.T(self.ftypes[fid]), fn, R(r))
            elif name == 'InstanceClosure':
                r, fid, o = a
                fn = self.callee(fid, needed)
                s = '%s = hl_alloc_closure_ptr(%s,(void*)%s,%s);' % (R(r), self.T(self.ftypes[fid]), fn, R(o))
            elif name == 'VirtualClosure':
                r, o, m = a
                fidx = self.proto_findex(rt(o), m)
                tt = self.T(self.ftypes[fidx]) if fidx is not None else self.T(rt(r))
                s = '%s = hl_alloc_closure_ptr(%s,((vdynamic*)%s)->t->vobj_proto[%d],%s);' % (R(r), tt, R(o), m, R(o))
            elif name == 'GetGlobal':
                r, g = a
                s = '%s = (%s)*(%s*)G(%d);' % (R(r), ctype(rt(r)), ctype(c.globals[g]), g)
            elif name == 'SetGlobal':
                g, r = a
                s = '*(%s*)G(%d) = (%s)%s;' % (ctype(c.globals[g]), g, ctype(c.globals[g]), R(r))
            elif name == 'Field':
                s = field_get(a[0], a[1], a[2])
            elif name == 'SetField':
                s = field_set(a[0], a[1], a[2])
            elif name == 'GetThis':
                s = field_get(a[0], 0, a[1])
            elif name == 'SetThis':
                s = field_set(0, a[0], a[1])
            elif name == 'DynGet':
                r, o, sid = a
                t = rt(r)
                tv = (',' + self.T(t)) if dyn_prefix(t) in ('i', 'p') else ''
                s = '%s = (%s)hl_dyn_get%s((vdynamic*)%s,H(%d)%s);' % (R(r), ctype(t), dyn_prefix(t), R(o), sid, tv)
            elif name == 'DynSet':
                o, sid, v = a
                t = rt(v)
                tv = (',' + self.T(t)) if dyn_prefix(t) in ('i', 'p') else ''
                s = 'hl_dyn_set%s((vdynamic*)%s,H(%d)%s,%s);' % (dyn_prefix(t), R(o), sid, tv, R(v))
            elif name in ('JTrue', 'JNotNull'):
                s = 'if( %s ) goto %s;' % (R(a[0]), label(i, a[1]))
            elif name in ('JFalse', 'JNull'):
                s = 'if( !%s ) goto %s;' % (R(a[0]), label(i, a[1]))
            elif name in ('JSLt', 'JSGte', 'JSGt', 'JSLte', 'JEq', 'JNotEq'):
                s = compare(i, name, a[0], a[1], a[2])
            elif name == 'JULt':
                s = 'if( ((unsigned)%s) < ((unsigned)%s) ) goto %s;' % (R(a[0]), R(a[1]), label(i, a[2]))
            elif name == 'JUGte':
                s = 'if( ((unsigned)%s) >= ((unsigned)%s) ) goto %s;' % (R(a[0]), R(a[1]), label(i, a[2]))
            elif name == 'JNotLt':
                s = 'if( !(%s < %s) ) goto %s;' % (R(a[0]), R(a[1]), label(i, a[2]))
            elif name == 'JNotGte':
                s = 'if( !(%s >= %s) ) goto %s;' % (R(a[0]), R(a[1]), label(i, a[2]))
            elif name == 'JAlways':
                s = 'goto %s;' % label(i, a[0])
            elif name in ('Label', 'Nop', 'Assert', 'Prefetch'):
                s = None
            elif name == 'ToDyn':
                r, v = a
                vt = rt(v)
                if vt.kind == HBOOL:
                    s = '%s = hl_alloc_dynbool(%s);' % (R(r), R(v))
                else:
                    body = '%s = hl_alloc_dynamic(%s); ((vdynamic*)%s)->v.%s = %s;' % (R(r), self.T(vt), R(r), DYN_FIELD.get(vt.kind, 'ptr'), R(v))
                    s = ('if( %s == NULL ) %s = NULL; else { %s }' % (R(v), R(r), body)) if is_ptr(vt) else body
            elif name == 'ToSFloat':
                s = '%s = (%s)%s;' % (R(a[0]), ctype(rt(a[0])), R(a[1]))
            elif name == 'ToUFloat':
                s = '%s = (%s)(unsigned)%s;' % (R(a[0]), ctype(rt(a[0])), R(a[1]))
            elif name == 'ToInt':
                s = '%s = (%s)%s;' % (R(a[0]), ctype(rt(a[0])), R(a[1]))
            elif name == 'SafeCast':
                r, v = a
                t, tsrc = rt(r), rt(v)
                if tsrc.kind == HNULL and tsrc.tparam is t:
                    s = '%s = %s ? ((vdynamic*)%s)->v.%s : 0;' % (R(r), R(v), R(v), DYN_FIELD.get(t.kind, 'ptr'))
                else:
                    tv = (',' + self.T(t)) if dyn_prefix(t) in ('i', 'p') else ''
                    s = '%s = (%s)hl_dyn_cast%s(&%s,%s%s);' % (R(r), ctype(t), dyn_prefix(t), R(v), self.T(tsrc), tv)
            elif name == 'UnsafeCast':
                s = '%s = (%s)%s;' % (R(a[0]), ctype(rt(a[0])), R(a[1]))
            elif name == 'ToVirtual':
                s = '%s = hl_to_virtual(%s,(vdynamic*)%s);' % (R(a[0]), self.T(rt(a[0])), R(a[1]))
            elif name == 'Ret':
                if ft.ret.kind == HVOID:
                    s = 'return;'
                else:
                    s = 'return (%s)%s;' % (ctype(ft.ret), R(a[0]))
            elif name == 'Throw':
                s = 'hl_throw((vdynamic*)%s);' % R(a[0])
            elif name == 'Rethrow':
                s = 'hl_rethrow((vdynamic*)%s);' % R(a[0])
            elif name == 'Switch':
                r, offs, end = a
                cases = ' '.join('case %d: goto %s;' % (k, label(i, o)) for k, o in enumerate(offs))
                s = 'switch( %s ) { %s }' % (R(r), cases)
            elif name == 'NullCheck':
                s = 'if( !%s ) hl_null_access();' % R(a[0])
            elif name == 'Trap':
                r, d = a
                s = 'hl_trap(trap%d,%s,%s);' % (trap_depth, R(r), label(i, d))
                trap_depth += 1
            elif name == 'EndTrap':
                if a[0]:
                    trap_depth -= 1
                    s = 'hl_endtrap(trap%d);' % trap_depth
                else:
                    s = 'hl_endtrap(trap%d);' % (trap_depth - 1)
            elif name in ('GetI8', 'GetI16', 'GetMem'):
                r, b, idx = a
                ty = {'GetI8': 'unsigned char', 'GetI16': 'unsigned short'}.get(name, ctype(rt(r)))
                s = '{ %s _v; memcpy(&_v, %s + %s, sizeof(_v)); %s = _v; }' % (ty, R(b), R(idx), R(r))
            elif name in ('SetI8', 'SetI16', 'SetMem'):
                b, idx, v = a
                ty = {'SetI8': 'unsigned char', 'SetI16': 'unsigned short'}.get(name, ctype(rt(v)))
                s = '{ %s _v = (%s)%s; memcpy(%s + %s, &_v, sizeof(_v)); }' % (ty, ty, R(v), R(b), R(idx))
            elif name == 'GetArray':
                r, arr, idx = a
                if rt(arr).kind == HABSTRACT:
                    if rt(r).kind in (HSTRUCT, HOBJ):
                        s = '%s = (char*)%s + %s * hl_get_obj_rt(%s)->size;' % (R(r), R(arr), R(idx), self.T(rt(r)))
                    else:
                        s = '%s = ((%s*)%s)[%s];' % (R(r), ctype(rt(r)), R(arr), R(idx))
                else:
                    s = '%s = hl_aptr(%s,%s)[%s];' % (R(r), R(arr), ctype(rt(r)), R(idx))
            elif name == 'SetArray':
                arr, idx, v = a
                if rt(arr).kind == HABSTRACT:
                    s = 'memcpy((char*)%s + %s * hl_get_obj_rt(%s)->size, %s, hl_get_obj_rt(%s)->size);' % (R(arr), R(idx), self.T(rt(v)), R(v), self.T(rt(v)))
                else:
                    s = 'hl_aptr(%s,%s)[%s] = %s;' % (R(arr), ctype(rt(v)), R(idx), R(v))
            elif name == 'New':
                t = rt(a[0])
                if t.kind in (HOBJ, HSTRUCT):
                    s = '%s = hl_alloc_obj(%s);' % (R(a[0]), self.T(t))
                elif t.kind == HDYNOBJ:
                    s = '%s = hl_alloc_dynobj();' % R(a[0])
                elif t.kind == HVIRTUAL:
                    s = '%s = hl_alloc_virtual(%s);' % (R(a[0]), self.T(t))
                else:
                    raise ValueError('new %s' % hlb.type_name(t))
            elif name == 'ArraySize':
                s = '%s = ((varray*)%s)->size;' % (R(a[0]), R(a[1]))
            elif name == 'Type':
                s = '%s = T(%d);' % (R(a[0]), a[1])
            elif name == 'GetType':
                s = '%s = %s ? ((vdynamic*)%s)->t : &hlt_void;' % (R(a[0]), R(a[1]), R(a[1]))
            elif name == 'GetTID':
                s = '%s = ((hl_type*)%s)->kind;' % (R(a[0]), R(a[1]))
            elif name == 'Ref':
                s = '%s = (void*)&%s;' % (R(a[0]), R(a[1]))
            elif name == 'Unref':
                s = '%s = *(%s*)%s;' % (R(a[0]), ctype(rt(a[0])), R(a[1]))
            elif name == 'Setref':
                s = '*(%s*)%s = %s;' % (ctype(rt(a[1])), R(a[0]), R(a[1]))
            elif name == 'RefData':
                s = '%s = (void*)hl_aptr(%s,char);' % (R(a[0]), R(a[1]))
            elif name == 'RefOffset':
                s = '%s = (char*)%s + %s * %d;' % (R(a[0]), R(a[1]), R(a[2]), 4)
            elif name == 'MakeEnum':
                r, cid, pl = a
                et = rt(r)
                params = et.constructs[cid][1]
                parts = ['venum *tmp = hl_alloc_enum(%s,%d);' % (self.T(et), cid)]
                for k, p in enumerate(pl):
                    parts.append('*(%s*)((char*)tmp + %s) = (%s)%s;' % (ctype(params[k]), self.off('e', et, cid, k), ctype(params[k]), R(p)))
                parts.append('%s = tmp;' % R(r))
                s = '{ %s }' % ' '.join(parts)
            elif name == 'EnumAlloc':
                s = '%s = hl_alloc_enum(%s,%d);' % (R(a[0]), self.T(rt(a[0])), a[1])
            elif name == 'EnumIndex':
                s = '%s = ((venum*)%s)->index;' % (R(a[0]), R(a[1]))
            elif name == 'EnumField':
                r, e, cid, pid = a
                et = rt(e)
                pt = et.constructs[cid][1][pid]
                s = '%s*(%s*)((char*)%s + %s);' % (assign(r, pt), ctype(pt), R(e), self.off('e', et, cid, pid))
            elif name == 'SetEnumField':
                e, pid, v = a
                et = rt(e)
                pt = et.constructs[0][1][pid]
                s = '*(%s*)((char*)%s + %s) = (%s)%s;' % (ctype(pt), R(e), self.off('e', et, 0, pid), ctype(pt), R(v))
            else:
                s = 'hl_fatal("unsupported op %s");' % name
            if s:
                w('\t' + s)
        if len(ops) in targets:
            w('L%d:;' % len(ops))
        if ft.ret.kind != HVOID:
            w('\treturn 0;')
        w('}')
        return '\n'.join(out)


HEADER = r'''#include <hl.h>
#include <math.h>
#include <string.h>
extern hl_type *hlaot_types;
extern void **hlaot_globals;
extern int *hlaot_offsets;
extern vbyte **hlaot_strings;
extern int *hlaot_hashes;
extern void **hlaot_fptrs;
#define T(i) (hlaot_types + (i))
#define G(i) (hlaot_globals[i])
#define O(i) (hlaot_offsets[i])
#define S(i) ((void*)hlaot_strings[i])
#define H(i) (hlaot_hashes[i])
#define F(i) (hlaot_fptrs[i])
'''


def reflect(gen):
    out = [HEADER]
    w = out.append
    keys = sorted(gen.sigs)
    for n, key in enumerate(keys):
        args, ret = gen.sigs[key]
        ca = [ctype(x) if x.kind != HVOID else 'void*' for x in args]
        fn = '((%s(*)(%s))fun)' % (ctype(ret), ','.join(ca) or 'void')
        vargs = []
        for k, x in enumerate(args):
            if x.kind == HVOID:
                vargs.append('0')
            elif is_ptr(x):
                vargs.append('(%s)args[%d]' % (ca[k], k))
            else:
                vargs.append('*(%s*)args[%d]' % (ca[k], k))
        callx = '%s(%s)' % (fn, ','.join(vargs))
        w('static void *sc%d(void *fun, void **args, vdynamic *out) {' % n)
        if ret.kind == HVOID:
            w('\t%s; return NULL;' % callx)
        elif is_ptr(ret):
            w('\treturn (void*)%s;' % callx)
        else:
            w('\tout->v.%s = %s; return &out->v.%s;' % (DYN_FIELD[ret.kind], callx, DYN_FIELD[ret.kind]))
        w('}')
        params = ''.join(',%s p%d' % (ca[k], k) for k in range(len(args)))
        w('static %s wr%d(void *value%s) {' % (ctype(ret), n, params))
        if args:
            w('\tvoid *args[] = {%s};' % ','.join('p%d' % k if is_ptr(x) or x.kind == HVOID else '&p%d' % k for k, x in enumerate(args)))
        aa = 'args' if args else 'NULL'
        if ret.kind == HVOID:
            w('\thl_wrapper_call(value,%s,NULL);' % aa)
        elif is_ptr(ret):
            w('\treturn (%s)hl_wrapper_call(value,%s,NULL);' % (ctype(ret), aa))
        else:
            w('\tvdynamic ret; hl_wrapper_call(value,%s,&ret); return ret.v.%s;' % (aa, DYN_FIELD[ret.kind]))
        w('}')
    w('typedef struct { const char *key; void *call; void *wrap; } hlaot_sig;')
    w('static const hlaot_sig SIGS[] = {')
    for n, key in enumerate(keys):
        w('\t{"%s",(void*)sc%d,(void*)wr%d},' % (key, n, n))
    w('};')
    w('''static char kind_char( hl_type *t ) {
	switch( t->kind ) {
	case HVOID: return 'v'; case HUI8: return 'c'; case HUI16: return 's'; case HI32: return 'i';
	case HI64: case HGUID: return 'l'; case HF32: return 'f'; case HF64: return 'd'; case HBOOL: return 'b';
	default: return 'p';
	}
}
static const hlaot_sig *find_sig( hl_type *t ) {
	char key[64];
	int i, n = 0, lo = 0, hi = (int)(sizeof(SIGS)/sizeof(SIGS[0])) - 1;
	for(i=0;i<t->fun->nargs && n < 60;i++) key[n++] = kind_char(t->fun->args[i]);
	key[n++] = '_';
	key[n++] = kind_char(t->fun->ret);
	key[n] = 0;
	while( lo <= hi ) {
		int mid = (lo + hi) >> 1;
		int c = strcmp(SIGS[mid].key, key);
		if( c == 0 ) return SIGS + mid;
		if( c < 0 ) lo = mid + 1; else hi = mid - 1;
	}
	return NULL;
}
void *hlaot_static_call( void *fun, hl_type *t, void **args, vdynamic *out ) {
	const hlaot_sig *s = find_sig(t);
	if( !s ) hl_fatal("Unsupported dynamic call signature");
	return ((void*(*)(void*,void**,vdynamic*))s->call)(fun,args,out);
}
void *hlaot_get_wrapper( hl_type *t ) {
	const hlaot_sig *s = find_sig(t);
	return s ? s->wrap : NULL;
}''')
    return '\n'.join(out) + '\n'


def tables(gen):
    c = gen.c
    out = [HEADER]
    w = out.append
    for f in c.functions:
        w(gen.fdecl(f.findex))
    w('const int hlaot_nfunctions = %d;' % len(c.functions))
    w('void *hlaot_functions[] = {')
    for f in c.functions:
        w('\t(void*)f%d,' % f.findex)
    w('};')
    w('const int hlaot_noffsets = %d;' % len(gen.offsets))
    w('const int hlaot_offset_spec[] = {')
    for kind, t, x, y in gen.offsets:
        w('\t%d,%d,%d,%d,' % (0 if kind == 'o' else 1, t, x, y))
    w('0};')
    w('const int hlaot_bytecode_size = %d;' % c.end)
    return '\n'.join(out) + '\n'


def main(path, out_dir, per_file_ops=60000):
    data = open(path, 'rb').read()
    code = hlb.read(data)
    gen = Gen(code)
    os.makedirs(out_dir, exist_ok=True)
    files = []
    chunk, size, needed, n = [], 0, set(), 0

    def flush():
        nonlocal chunk, size, needed, n
        if not chunk:
            return
        own = {f for f, _ in chunk}
        decls = [gen.fdecl(x) for x in sorted(needed | own)]
        name = 'fun_%03d.c' % n
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8', newline='\n') as o:
            o.write(HEADER)
            o.write('\n'.join(decls) + '\n\n')
            o.write('\n\n'.join(body for _, body in chunk) + '\n')
        files.append(name)
        n += 1
        chunk, size, needed = [], 0, set()

    for f in code.functions:
        body = gen.function(f, needed)
        chunk.append((f.findex, body))
        size += len(f.ops)
        if size >= per_file_ops:
            flush()
    flush()
    with open(os.path.join(out_dir, 'reflect.c'), 'w', encoding='utf-8', newline='\n') as o:
        o.write(reflect(gen))
    with open(os.path.join(out_dir, 'tables.c'), 'w', encoding='utf-8', newline='\n') as o:
        o.write(tables(gen))
    print('functions', len(code.functions), 'files', len(files), 'signatures', len(gen.sigs), 'offsets', len(gen.offsets))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
