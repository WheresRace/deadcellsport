# Dead Cells web port

Experimental HashLink → WebAssembly port with a static GitHub Pages launcher.

**[Open the web port](https://wheresrace.github.io/deadcellsport/)**

## Play

Open the Pages site in desktop Chrome or Edge, then select your **GOG 1.26.0**
game folder. Alternatively select `res.pak` and `deadcells_gl.exe` individually;
an extracted `hlboot_gl.dat` also works. The executable's bytecode must match
the exact build used to compile the runtime. Other game versions and DLC are
unsupported.

Files are read locally in chunks and are never uploaded. The site contains the
launcher and compiled runtime; the original game archive and bytecode are excluded.
Saves stay in this browser's IndexedDB. Clearing site data removes those saves.
Use a keyboard or gamepad. Double-click for fullscreen; append `?log` for diagnostics.
This port does not provide touch controls.

## Build and deploy

The existing local toolchain and generated C files are required to rebuild:

```powershell
python runtime/build.py web
python tools/package_pages.py
```

The packager writes an allowlisted static site to `docs/`, including a version
fingerprint derived from local game files, without copying those files. Commit
`docs/` after rebuilding. GitHub Pages serves the `docs/` folder on `master`.
All asset URLs are relative, so repository subpaths work. There is no server
dependency, range-request requirement, or client-log upload on the public site.

For local testing: `python -m http.server 8643 --directory docs`, then visit
`http://localhost:8643/`. The original developer server remains available via
`node runtime/web/serve.js` for automatic loading from `run/gog`.

See `NOTES.md` for the translator, native libraries, build steps and known issues.

Unofficial experimental project, not affiliated with Motion Twin or Evil Empire.
Dead Cells belongs to its respective owners. Original game files are not included.
