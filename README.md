# Dead Cells web port

Experimental HashLink → WebAssembly port with a fully online static launcher.

**[Play online](https://wheresrace.github.io/deadcellsport/)**

## Play

Open the site in desktop Chrome or Edge. The game starts loading immediately.
The supported base game loads entirely online. No file selection or installation
is required. Use a keyboard or gamepad. Click the game to capture the mouse.
F11 toggles fullscreen; rapid mouse clicks do not change fullscreen. Append `?log`
for diagnostics. This port does not provide touch controls.

The primary launcher is hosted on GitHub Pages. Its deployment uses GitHub Actions.
An existing ChatGPT Sites deployment is kept compatible and loads the same runtime
and bytecode from the versioned GitHub asset host.
The 2.07 GB archive is streamed
on demand from immutable 16 MiB files in this repository using GitHub's raw asset
host, which supports CORS and byte ranges. The generated Pages bundle itself is
about 73 MB, within its 1 GB site limit. Only requested ranges are downloaded,
with a bounded in-memory cache. GitHub's bandwidth and rate limits still apply;
for heavy traffic, move these chunks to object storage and change `--asset-base`.
Saves stay in this browser's IndexedDB. Clearing site data removes those saves.

## Build and deploy

The existing local toolchain and generated C files are required to rebuild:

```powershell
python runtime/build.py web
python tools/package_assets.py
python tools/package_pages.py
```

Commit and push `web-assets/`, then tag that asset commit as `assets-v1` and push
the tag. The default launcher configuration pins its archive URLs to that tag.
For a changed archive, use a new tag and pass the corresponding URL prefix to
`python tools/package_pages.py --asset-base <URL>`.

The packager writes an allowlisted static site to `docs/`. Commit `docs/` after
rebuilding. The Pages workflow publishes only `docs/` and uses a partial checkout
to avoid downloading the 2 GB asset folder during deployment. The local page
and runtime URLs are relative, so repository subpaths work. The public site
needs no application server and does not upload client logs.

For other static hosts, the launcher also accepts `wasmUrl` and `bootUrl` in
`runtime.json`. Point them to `docs/deadcells.wasm` and `docs/hlboot.bin` under the
same immutable asset tag, and host only `index.html`, `launcher.js`, `deadcells.js`
and `runtime.json`. This is the primary Site's configuration.

For local testing: `python -m http.server 8643 --directory docs`, then visit
`http://localhost:8643/`. The original developer server remains available via
`node runtime/web/serve.js` for automatic loading from `run/gog`.

See `NOTES.md` for the translator, native libraries, build steps and known issues.

Unofficial experimental project, not affiliated with Motion Twin or Evil Empire.
Dead Cells belongs to its respective owners.
