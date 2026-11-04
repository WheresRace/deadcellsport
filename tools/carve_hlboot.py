import struct, sys, hashlib

def resources(d):
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    optsz = struct.unpack_from('<H', d, pe + 20)[0]
    sec = pe + 24 + optsz
    for i in range(nsec):
        name, vsize, va, rsize, raw = struct.unpack_from('<8sIIII', d, sec + 40 * i)
        if name.rstrip(b'\0') == b'.rsrc':
            base_va, base_raw = va, raw
    def name_of(entry_name):
        if entry_name & 0x80000000:
            o = base_raw + (entry_name & 0x7fffffff)
            n = struct.unpack_from('<H', d, o)[0]
            return d[o + 2:o + 2 + n * 2].decode('utf-16le')
        return entry_name
    def walk(off, path):
        named, ids = struct.unpack_from('<HH', d, base_raw + off + 12)
        for i in range(named + ids):
            en, eo = struct.unpack_from('<II', d, base_raw + off + 16 + 8 * i)
            p = path + [name_of(en)]
            if eo & 0x80000000:
                yield from walk(eo & 0x7fffffff, p)
            else:
                rva, size = struct.unpack_from('<II', d, base_raw + eo)
                yield p, rva - base_va + base_raw, size
    yield from walk(0, [])

src, out = sys.argv[1], sys.argv[2]
d = open(src, 'rb').read()
for path, off, size in resources(d):
    tag = d[off:off + 3]
    print(path, hex(off), size, tag)
    if tag == b'HLB':
        blob = d[off:off + size]
        open(out, 'wb').write(blob)
        print('wrote', out, size, hashlib.sha1(blob).hexdigest())
