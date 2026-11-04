import struct

HVOID, HUI8, HUI16, HI32, HI64, HF32, HF64, HBOOL, HBYTES, HDYN, HFUN, HOBJ, HARRAY, HTYPE, HREF, HVIRTUAL, HDYNOBJ, HABSTRACT, HENUM, HNULL, HMETHOD, HSTRUCT, HPACKED, HGUID = range(24)

KIND_NAMES = ['void', 'u8', 'u16', 'i32', 'i64', 'f32', 'f64', 'bool', 'bytes', 'dyn', 'fun', 'obj', 'array', 'type', 'ref', 'virtual', 'dynobj', 'abstract', 'enum', 'null', 'method', 'struct', 'packed', 'guid']

OPCODES = [
    ('Mov', 2), ('Int', 2), ('Float', 2), ('Bool', 2), ('Bytes', 2), ('String', 2), ('Null', 1),
    ('Add', 3), ('Sub', 3), ('Mul', 3), ('SDiv', 3), ('UDiv', 3), ('SMod', 3), ('UMod', 3),
    ('Shl', 3), ('SShr', 3), ('UShr', 3), ('And', 3), ('Or', 3), ('Xor', 3),
    ('Neg', 2), ('Not', 2), ('Incr', 1), ('Decr', 1),
    ('Call0', 2), ('Call1', 3), ('Call2', 4), ('Call3', 5), ('Call4', 6),
    ('CallN', -1), ('CallMethod', -1), ('CallThis', -1), ('CallClosure', -1),
    ('StaticClosure', 2), ('InstanceClosure', 3), ('VirtualClosure', 3),
    ('GetGlobal', 2), ('SetGlobal', 2), ('Field', 3), ('SetField', 3), ('GetThis', 2), ('SetThis', 2),
    ('DynGet', 3), ('DynSet', 3),
    ('JTrue', 2), ('JFalse', 2), ('JNull', 2), ('JNotNull', 2),
    ('JSLt', 3), ('JSGte', 3), ('JSGt', 3), ('JSLte', 3), ('JULt', 3), ('JUGte', 3),
    ('JNotLt', 3), ('JNotGte', 3), ('JEq', 3), ('JNotEq', 3), ('JAlways', 1),
    ('ToDyn', 2), ('ToSFloat', 2), ('ToUFloat', 2), ('ToInt', 2), ('SafeCast', 2), ('UnsafeCast', 2), ('ToVirtual', 2),
    ('Label', 0), ('Ret', 1), ('Throw', 1), ('Rethrow', 1), ('Switch', -1), ('NullCheck', 1), ('Trap', 2), ('EndTrap', 1),
    ('GetI8', 3), ('GetI16', 3), ('GetMem', 3), ('GetArray', 3), ('SetI8', 3), ('SetI16', 3), ('SetMem', 3), ('SetArray', 3),
    ('New', 1), ('ArraySize', 2), ('Type', 2), ('GetType', 2), ('GetTID', 2), ('Ref', 2), ('Unref', 2), ('Setref', 2),
    ('MakeEnum', -1), ('EnumAlloc', 2), ('EnumIndex', 2), ('EnumField', 4), ('SetEnumField', 3),
    ('Assert', 0), ('RefData', 2), ('RefOffset', 3), ('Nop', 0), ('Prefetch', 3), ('Asm', 3),
]
VARARG_CALLS = {'CallN', 'CallMethod', 'CallThis', 'CallClosure', 'MakeEnum'}


class Type:
    __slots__ = ('kind', 'name', 'args', 'ret', 'super', 'global_', 'fields', 'protos', 'bindings', 'tparam', 'constructs')

    def __init__(self, kind):
        self.kind = kind
        self.name = None
        self.args = self.fields = self.protos = self.bindings = self.constructs = None
        self.ret = self.super = self.global_ = self.tparam = None


class Function:
    __slots__ = ('type', 'findex', 'regs', 'ops', 'debug', 'assigns')


class Code:
    pass


class Reader:
    def __init__(self, data):
        self.d = data
        self.p = 0

    def byte(self):
        b = self.d[self.p]
        self.p += 1
        return b

    def i32(self):
        v = struct.unpack_from('<i', self.d, self.p)[0]
        self.p += 4
        return v

    def f64(self):
        v = struct.unpack_from('<d', self.d, self.p)[0]
        self.p += 8
        return v

    def index(self):
        d = self.d
        p = self.p
        b = d[p]
        if not b & 0x80:
            self.p = p + 1
            return b & 0x7f
        if not b & 0x40:
            v = d[p + 1] | ((b & 31) << 8)
            self.p = p + 2
            return -v if b & 0x20 else v
        v = ((b & 31) << 24) | (d[p + 1] << 16) | (d[p + 2] << 8) | d[p + 3]
        self.p = p + 4
        return -v if b & 0x20 else v

    def uindex(self):
        v = self.index()
        if v < 0:
            raise ValueError('negative uindex at %d' % self.p)
        return v

    def strings(self, n):
        size = self.i32()
        blob = self.d[self.p:self.p + size]
        self.p += size
        out = []
        pos = 0
        for _ in range(n):
            sz = self.uindex()
            out.append(blob[pos:pos + sz].decode('utf-8', 'replace'))
            pos += sz + 1
        return out


def read(data):
    r = Reader(data)
    if data[:3] != b'HLB':
        raise ValueError('not HLB')
    r.p = 3
    c = Code()
    c.version = r.byte()
    c.flags = r.uindex()
    nints = r.uindex()
    nfloats = r.uindex()
    nstrings = r.uindex()
    nbytes = r.uindex() if c.version >= 5 else 0
    ntypes = r.uindex()
    nglobals = r.uindex()
    nnatives = r.uindex()
    nfunctions = r.uindex()
    nconstants = r.uindex() if c.version >= 4 else 0
    c.entrypoint = r.uindex()
    c.ints = [r.i32() for _ in range(nints)]
    c.floats = [r.f64() for _ in range(nfloats)]
    c.strings = r.strings(nstrings)
    c.bytes = None
    if c.version >= 5:
        size = r.i32()
        c.bytes = r.d[r.p:r.p + size]
        r.p += size
        c.bytes_pos = [r.uindex() for _ in range(nbytes)]
    c.debug_files = []
    if c.flags & 1:
        c.debug_files = r.strings(r.uindex())

    c.types = [Type(0) for _ in range(ntypes)]
    gettype = lambda: c.types[r.index()]
    ustr = lambda: c.strings[r.uindex()]
    for t in c.types:
        k = r.byte()
        t.kind = k
        if k in (HFUN, HMETHOD):
            t.args = [gettype() for _ in range(r.byte())]
            t.ret = gettype()
        elif k in (HOBJ, HSTRUCT):
            t.name = ustr()
            sup = r.index()
            t.super = c.types[sup] if sup >= 0 else None
            t.global_ = r.uindex()
            nf, np_, nb = r.uindex(), r.uindex(), r.uindex()
            t.fields = [(ustr(), gettype()) for _ in range(nf)]
            t.protos = [(ustr(), r.uindex(), r.index()) for _ in range(np_)]
            t.bindings = [(r.uindex(), r.uindex()) for _ in range(nb)]
        elif k in (HREF, HNULL, HPACKED):
            t.tparam = gettype()
        elif k == HVIRTUAL:
            t.fields = [(ustr(), gettype()) for _ in range(r.uindex())]
        elif k == HABSTRACT:
            t.name = ustr()
        elif k == HENUM:
            t.name = ustr()
            t.global_ = r.uindex()
            t.constructs = []
            for _ in range(r.uindex()):
                cname = ustr()
                t.constructs.append((cname, [gettype() for _ in range(r.uindex())]))
        elif k >= len(KIND_NAMES):
            raise ValueError('bad type kind %d at %d' % (k, r.p))

    c.globals = [gettype() for _ in range(nglobals)]
    c.natives = [(ustr(), ustr(), gettype(), r.uindex()) for _ in range(nnatives)]

    c.functions = []
    for _ in range(nfunctions):
        f = Function()
        f.type = gettype()
        f.findex = r.uindex()
        nregs = r.uindex()
        nops = r.uindex()
        f.regs = [gettype() for _ in range(nregs)]
        ops = []
        for _ in range(nops):
            op = r.uindex()
            name, n = OPCODES[op]
            if n >= 0:
                ops.append((op, tuple(r.index() for _ in range(n))))
            elif name in VARARG_CALLS:
                a, b = r.index(), r.index()
                cnt = r.byte()
                ops.append((op, (a, b, tuple(r.index() for _ in range(cnt)))))
            else:
                a, cnt = r.uindex(), r.uindex()
                offs = tuple(r.uindex() for _ in range(cnt))
                ops.append((op, (a, offs, r.uindex())))
        f.ops = ops
        f.debug = read_debug(r, nops, len(c.debug_files)) if c.flags & 1 else None
        f.assigns = None
        if c.version >= 3:
            f.assigns = [(r.uindex(), r.index()) for _ in range(r.uindex())]
        c.functions.append(f)

    c.constants = []
    for _ in range(nconstants):
        g = r.uindex()
        c.constants.append((g, [r.uindex() for _ in range(r.uindex())]))
    c.end = r.p
    return c


def read_debug(r, nops, nfiles):
    out = [0] * (nops * 2)
    curfile, curline, i = -1, 0, 0
    while i < nops:
        c = r.byte()
        if c & 1:
            curfile = ((c >> 1) << 8) | r.byte()
            if curfile >= nfiles:
                raise ValueError('bad debug file')
        elif c & 2:
            delta = c >> 6
            count = (c >> 2) & 15
            for _ in range(count):
                out[i * 2] = curfile
                out[i * 2 + 1] = curline
                i += 1
            curline += delta
        elif c & 4:
            curline += c >> 3
            out[i * 2] = curfile
            out[i * 2 + 1] = curline
            i += 1
        else:
            b2, b3 = r.byte(), r.byte()
            curline = (c >> 3) | (b2 << 5) | (b3 << 13)
            out[i * 2] = curfile
            out[i * 2 + 1] = curline
            i += 1
    return out


def type_name(t, depth=0):
    k = t.kind
    if t.name:
        return t.name
    if k in (HFUN, HMETHOD):
        if depth > 3:
            return 'fun'
        return '(%s) -> %s' % (', '.join(type_name(a, depth + 1) for a in t.args), type_name(t.ret, depth + 1))
    if k in (HREF, HNULL, HPACKED):
        return '%s<%s>' % (KIND_NAMES[k], type_name(t.tparam, depth + 1))
    if k == HVIRTUAL:
        return 'virtual<%s>' % ','.join(n for n, _ in t.fields)
    return KIND_NAMES[k]
