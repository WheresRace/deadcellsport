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

## Milestones

1. ✅ Carve bytecode, parse it exactly, typed disassembly, pak index.
2. bytecode → C translator (`tools/hl2c/`), compiled natively first against stock HashLink on Windows to prove the
   translation boots the game before any web work.
3. emscripten build of libhl + fmt + stubs; headless boot to first frame in the browser.
4. WebGL2 rendering, input, audio, pak streaming.
5. Mod hooks: function-level overrides in the translator (replace any findex with hand-written Haxe/C).
