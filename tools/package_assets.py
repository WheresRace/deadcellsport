"""Split the game archive into immutable, range-readable web assets."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNK_SIZE = 16 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pak', type=Path, default=ROOT / 'run/gog/res.pak')
    parser.add_argument('--out', type=Path, default=ROOT / 'web-assets/res')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    chunks = []
    with args.pak.open('rb') as source:
        while data := source.read(CHUNK_SIZE):
            name = f'{len(chunks):04}.bin'
            (args.out / name).write_bytes(data)
            chunks.append({'file': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    manifest = {'size': args.pak.stat().st_size, 'chunkSize': CHUNK_SIZE, 'chunks': chunks}
    (args.out.parent / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Wrote {len(chunks)} chunks, {manifest["size"]:,} bytes to {args.out}')


if __name__ == '__main__':
    main()
