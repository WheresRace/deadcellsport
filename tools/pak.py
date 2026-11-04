import struct, sys, collections


def read_index(path):
    f = open(path, 'rb')
    head = f.read(16)
    if head[:3] != b'PAK':
        raise ValueError('not a pak')
    version = head[3]
    header_size, data_size = struct.unpack_from('<iI', head, 4)
    f.seek(0)
    h = f.read(header_size)
    p = 12 + (64 if version >= 1 else 0)
    entries = []

    def entry(prefix):
        nonlocal p
        n = h[p]
        name = h[p + 1:p + 1 + n].decode('utf-8')
        p += 1 + n
        flags = h[p]
        p += 1
        full = prefix + name
        if flags & 1:
            count = struct.unpack_from('<i', h, p)[0]
            p += 4
            for _ in range(count):
                entry(full + '/' if full else '')
        else:
            if flags & 2:
                pos = int(struct.unpack_from('<d', h, p)[0])
                p += 8
            else:
                pos = struct.unpack_from('<I', h, p)[0]
                p += 4
            size, crc = struct.unpack_from('<Ii', h, p)
            p += 8
            entries.append((full, header_size + pos, size, crc))

    entry('')
    return version, header_size, data_size, entries


def extract(path, entries, out_dir, match=''):
    import os
    with open(path, 'rb') as f:
        for name, pos, size, _ in entries:
            if match not in name:
                continue
            dst = os.path.join(out_dir, name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            f.seek(pos)
            open(dst, 'wb').write(f.read(size))


if __name__ == '__main__':
    version, hs, ds, entries = read_index(sys.argv[1])
    print('pak v%d header %d data %d files %d' % (version, hs, ds, len(entries)))
    if len(sys.argv) > 2 and sys.argv[2] == 'extract':
        extract(sys.argv[1], entries, sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else '')
        sys.exit()
    by_ext = collections.defaultdict(lambda: [0, 0])
    by_dir = collections.defaultdict(lambda: [0, 0])
    for name, pos, size, _ in entries:
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name.rsplit('/', 1)[-1] else '(none)'
        by_ext[ext][0] += 1
        by_ext[ext][1] += size
        top = name.split('/')[0] if '/' in name else '(root)'
        by_dir[top][0] += 1
        by_dir[top][1] += size
    for title, d in (('by extension', by_ext), ('by top dir', by_dir)):
        print(title)
        for k, (n, s) in sorted(d.items(), key=lambda kv: -kv[1][1])[:20]:
            print('  %-14s %6d files %8.1f MB' % (k, n, s / 1e6))
    big = sorted(entries, key=lambda e: -e[2])[:8]
    print('largest:', [(e[0], round(e[2] / 1e6, 1)) for e in big])
