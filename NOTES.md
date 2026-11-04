# Dead Cells → Web port

Game Port. Game files come from the user's own Steam install and are never committed or published
(`extracted/`, `*.pak`, `*.dat` are gitignored). `game-permissions.json` in the install folder is a verified
Motion Twin document.

## What the game is

- Haxe + Heaps on the HashLink VM (JIT build). `deadcells.exe` / `deadcells_gl.exe` are HashLink hosts with the
  bytecode embedded as PE resource `RCDATA/HLBOOT.DAT` (17.7 MB). Use the `_gl` one — it targets the OpenGL driver.
- Bytecode: HLB v4, debug info on (1964 source files with line numbers), 37,499 functions, 3.7M ops,
  25,144 types, 20,439 globals, 517 natives. Built from `dc-mp2c/client_20260616_101646`.
- No custom natives. Everything maps to stock open-source HashLink libs:

| lib | count | web plan |
|---|---|---|
| std | 164 | libhl compiled with emscripten; sockets/sys_command stubbed |
| openal | 126 | emscripten OpenAL (EFX calls stubbed) |
| sdl | 109 | hlsdl's GL path against WebGL2; window/gamepad via emscripten SDL2 |
| steam | 55 | stub |
| ssl | 20 | stub |
| fmt | 14 | compile as-is (zlib, png, jpg, ogg) |
| ui | 12 | stub (Win32 dialogs / sentinel) |
| chroma, discord, uv | 17 | stub |

- **32-bit (x86)**: exe, libhl.dll and all .hdll are x86. Official HashLink releases are x64-only, so stock `hl.exe`
  can't host it (0xC000007B). 32-bit pointers match wasm32, which helps the port.
- Single-threaded: no thread-creation natives.
- Main loop: `hxd.System.runMainLoop` (#30574) is `while (mainLoop())`; patch it to register
  `hxd.System.mainLoop` (#6568) with `emscripten_set_main_loop` instead.
- `res.pak`: Heaps PAK v1 with a 64-byte stamp after the header sizes. 7,055 files, 2.07 GB
  (atlas PNGs 1.0 GB, music OGG 0.88 GB, sfx WAV 37 MB, 2,197 TMX rooms, `data.cdb`, shader caches `*.gl/*.dx/*.ps5`).
  Entry checksum is Adler-32 of the file data (verified); data offset = header size + entry pos.
  Room `.tmx` files are a binary format (`BTMX` magic), not Tiled XML.

## Tools (`tools/`)

- `carve_hlboot.py <exe> <out>` — extract HLBOOT.DAT from the exe's resources.
- `hlb.py` — HashLink bytecode reader (types, natives, functions, ops, debug info). Verified: consumes the blob
  byte-for-byte.
- `hlb_stats.py <hlboot> <summary.json>` — counts, natives per lib, packages.
- `hlb_dump.py <hlboot> <out_dir>` — typed disassembly, one `.hlasm` per original source file, plus `INDEX.tsv`
  (findex → name → file).
- `pak.py <res.pak> [extract <out_dir> [substring]]` — list / extract pak contents.

## Port route

Translate bytecode → C (same shape as Haxe's `hl2c` / HL/C output), compile with emscripten against libhl and the
libs above, ship as wasm + WebGL2 + WebAudio. Keeps the original game logic; no source reconstruction needed.

Known hard parts:
1. GC root scanning — HashLink scans the native stack; in wasm locals aren't in linear memory. Use binaryen
   `--spill-pointers` or a shadow stack in the generated C.
2. Assets — 2 GB can't be preloaded. Serve `res.pak` from a local server and back Heaps' pak FileSystem with HTTP
   range reads (sync XHR in a worker) or OPFS after a one-time import.
3. GL → WebGL2 — Heaps' GL driver mostly fits GLES3; shaders are generated from HXSL at runtime, so force the
   GLSL ES 300 path and drop `polygon_mode` / `bind_frag_data_location`.
4. Size — 3.7M ops will produce a very large C translation unit; split per source file.

## Status (2026-11-03)

- `tools/hl2c/hl2c.py` translates all 37,499 functions to C; libhl's own loader builds types/globals/natives at
  runtime (`runtime/aot_main.c`, patched `module.c` from `runtime/build.py`). Field/enum offsets come from a startup
  table filled by libhl, so layouts can't drift.
- `python runtime/build.py node` → `build/deadcells_node.js/.wasm` (35 MB). Run from `run/game_libs` with
  `HLAOT_NOGC=1 node build/deadcells_node.js hlboot_gl.dat`: boots, loads res.pak, stops at the Steam check in
  `Boot.initPlatform` (exits unless `steam.Api.init` succeeds).
- Functions containing try/catch (setjmp) blow up at -O1 under wasm SjLj (one 4k-op ctor → 8.8 MB, over the
  engine's 7.6 MB per-function cap), so they go to `trap_*.c` and build at -O0.
- GC: binaryen `--spill-pointers` fails ("failed to find the stack pointer") on this emscripten; GC is disabled for
  boot tests until pointer roots are handled (shadow-stack roots emitted by the translator is the fallback).
- Steam build needs Steam to start; not bypassed. A DRM-free (GOG) bytecode goes through the same pipeline.

## Web status (GOG build, 2026-11-03)

- Source: GOG 1.26.0 installed to `run/gog`; bytecode carved to `extracted/hlboot_gog_gl.dat` (HLB v5, 36,967 functions,
  `gog` natives instead of `steam`). Steam bytecode still works through the same pipeline but stops at `steam.Api.init`.
- Regenerate: `HLAOT_SKIP_OVERRIDES=f6252 HLAOT_REAL_LIBS=std,fmt,sdl,openal,gog python tools/hl2c/hl2c.py extracted/hlboot_gog_gl.dat build/c`,
  then `python runtime/build.py web`, `node runtime/web/serve.js` → http://127.0.0.1:8642/ (serves `run/gog`, override with `GAME_DIR`).
- Overrides in `runtime/overrides/` match `f<findex>.c` or the function name without `$` (`hxd.System.runMainLoop.c`);
  name-based files use `@F(name)`, `@N(lib.name)`, `@SC(k)`, `@T(r)` placeholders so they survive bytecode changes.
- Browser: boots, WebGL2 + 1,291 shaders, splash → title screen → Play loads the Prisoners' Quarters intro.
- Web natives: sockets never connect (`runtime/web/net.c`), EFX source params dropped (`platform.c`), Win32 dialogs
  print to the log, `ErrorHandler.sendReport` is a no-op. GOG Galaxy is offline (`gog.c`: not signed in, language
  "English", no DLC — only the base game is installed in `run/gog`). Missing gog natives returned NULL, and the crash
  handler's `String.fromUTF8(NULL)` hid level-load errors and left `Game.level` null ("Null access" every frame).
- Screen: the SDL lib reports the canvas' CSS size as the display, fullscreen/borderless modes just fit the window to
  the page, and `hlaot_frame_begin` refits it when the page resizes. Browser fullscreen: double-click; Esc goes to
  the game while fullscreen (Keyboard Lock).
- GC: `HLAOT_GC=frame` (default on the web; `?nogc` turns it off) disables automatic collection and runs a major GC
  at frame start once allocation passes max(25% of heap, 64 MB) — no Haxe locals are live there.
- Saves: `/game/save` is IDBFS, loaded before start and flushed every 5 s and on `pagehide`. The `FATAL : Could not
  read save file` line on a first run is normal (`Save.tryLoad` handles the missing file).
- Debugging: `?profile` starts the JS Self-Profiling API (`await __profile(30)` in the console; server sends
  `Document-Policy: js-profiling`); link with `EXTRA_LINK=--profiling-funcs` to get `fN` names in stacks, map them
  with `extracted/disasm_gog/INDEX.tsv`. Null accesses log a C stack.
- Open: ~10 s of shader links at boot (ANGLE D3D11), EFX reverb/filters silent, frames throttle in hidden tabs.

## Milestones

1. ✅ Carve bytecode, parse it exactly, typed disassembly, pak index.
2. bytecode → C translator (`tools/hl2c/`), compiled natively first against stock HashLink on Windows to prove the
   translation boots the game before any web work.
3. emscripten build of libhl + fmt + stubs; headless boot to first frame in the browser.
4. WebGL2 rendering, input, audio, pak streaming.
5. Mod hooks: function-level overrides in the translator (replace any findex with hand-written Haxe/C).
