"""Assemble a static Pages site without copying local game files."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'docs')
    parser.add_argument('--game-dir', type=Path, default=ROOT / 'run' / 'gog')
    args = parser.parse_args()
    sources = {
        'index.html': ROOT / 'runtime/web/pages.html',
        'launcher.js': ROOT / 'runtime/web/launcher.js',
        'deadcells.js': ROOT / 'build/web/deadcells.js',
        'deadcells.wasm': ROOT / 'build/web/deadcells.wasm',
    }
    for source in sources.values():
        if not source.is_file():
            parser.error(f'Missing {source}; build the web runtime first.')
    if 'Module.hlaotFiles' not in sources['deadcells.js'].read_text(encoding='utf-8'):
        parser.error('Web runtime is stale; run python runtime/build.py web first.')
    boot = args.game_dir / 'hlboot_gl.dat'
    pak = args.game_dir / 'res.pak'
    config = {
        'gameVersion': 'GOG 1.26.0',
        'bootSha256': hashlib.sha256(boot.read_bytes()).hexdigest(),
        'pakSize': pak.stat().st_size,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    allowed = set(sources) | {'.nojekyll', 'runtime.json'}
    unexpected = [p.name for p in args.out.iterdir() if p.name not in allowed]
    if unexpected:
        parser.error(f'Refusing to publish unexpected output files: {unexpected}')
    for name, source in sources.items():
        shutil.copyfile(source, args.out / name)
    (args.out / 'runtime.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    (args.out / '.nojekyll').touch()
    print(f'Pages site: {args.out} ({sum(p.stat().st_size for p in args.out.iterdir()):,} bytes)')
    print('Only the launcher and compiled runtime are included. No game archive or bytecode is copied.')


if __name__ == '__main__':
    main()
