import os, sys, subprocess, concurrent.futures, re, glob

ROOT = r"C:\Users\NKTRa\deadcellsport"
EMCC = os.path.join(ROOT, r"toolchain\emsdk\upstream\emscripten\emcc.exe")
HL = os.path.join(ROOT, r"third_party\hashlink")
HL14 = os.path.join(ROOT, r"third_party\hashlink-1.14")
OUT = os.path.join(ROOT, 'build')
OBJ = os.path.join(OUT, 'obj')
OPT = os.environ.get('OPT', '-O1')
TARGET = sys.argv[1] if len(sys.argv) > 1 else 'node'

PCRE = ['auto_possess', 'chartables', 'compile', 'config', 'context', 'convert', 'dfa_match', 'error', 'extuni',
        'find_bracket', 'jit_compile', 'maketables', 'match_data', 'match', 'newline', 'ord2utf', 'pattern_info',
        'script_run', 'serialize', 'string_utils', 'study', 'substitute', 'substring', 'tables', 'ucd', 'valid_utf', 'xclass']
STD = ['array', 'buffer', 'bytes', 'cast', 'date', 'error', 'debug', 'file', 'fun', 'maps', 'math', 'obj', 'random',
       'regexp', 'socket', 'string', 'sys', 'types', 'ucs2', 'thread', 'process', 'track']

COMMON = ['-fwrapv', '-w', '-mnontrapping-fptoint', '-DHL_NO_THREADS', '-sSUPPORT_LONGJMP=wasm']
PORTS = ['-sUSE_SDL=2']


def patched_gl():
    src = open(os.path.join(HL14, 'libs', 'sdl', 'gl.c'), encoding='utf-8').read()
    a = src.index('#if defined(HL_IOS) || defined (HL_TVOS)')
    b = src.index('#ifdef HL_GLES', a)
    src = src[:a] + '#include <SDL2/SDL.h>\n#include <GLES3/gl3.h>\n#define HL_GLES\n#define glColorMaski(...) ES_NOT_SUPPORTED\n#define glGetQueryObjectui64v(...) ES_NOT_SUPPORTED\n#define glQueryCounter(...) ES_NOT_SUPPORTED\n\n' + src[b:]
    dst = os.path.join(OUT, 'runtime', 'gl_web.c')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'w', encoding='utf-8', newline='\n').write(src)
    return dst


def fmt_sources():
    cm = open(os.path.join(HL14, 'libs', 'fmt', 'CMakeLists.txt'), encoding='utf-8').read()
    seen, out = set(), []
    for rel in re.findall(r'\$\{INCLUDES_BASE_DIR\}/([\w/.-]+\.c)', cm):
        rel = rel.replace('turbojpeg/jsimd.c', 'turbojpeg/jsimd_none.c')
        if rel not in seen:
            seen.add(rel)
            out.append(os.path.join(HL14, 'include', *rel.split('/')))
    return out


def patched_module():
    src = open(os.path.join(HL, 'src', 'module.c'), encoding='utf-8').read()
    a = src.index('\t\tstrcpy(p,"hlp_");')
    b = src.index('\t\t\thl_fatal4("Invalid signature', a)
    b = src.index('\n', b) + 1
    src = src[:a] + '\t\tm->functions_ptrs[n->findex] = hlaot_native(i);\n\t\t(void)sign; (void)f; (void)p;\n' + src[b:]
    src = src.replace('\t\t\tlibHandler = resolve_library(lib, is_opt);', '\t\t\tlibHandler = NULL;')
    a = src.index('\t// JIT\n\tctx = hl_jit_alloc();')
    b = src.index('\t// INIT constants', a)
    src = src[:a] + '\tctx = NULL;\n\thlaot_install_functions(m);\n' + src[b:]
    src = src.replace('#include <hlmodule.h>', '#include <hlmodule.h>\nvoid *hlaot_native( int i );\nvoid hlaot_install_functions( hl_module *m );', 1)
    dst = os.path.join(OUT, 'runtime', 'module_aot.c')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'w', encoding='utf-8', newline='\n').write(src)
    return dst


def units():
    u = []
    inc = ['-I', os.path.join(HL, 'src')]
    pcre = inc + ['-I', os.path.join(HL, 'include', 'pcre'), '-DHAVE_CONFIG_H', '-DPCRE2_STATIC', '-DPCRE2_CODE_UNIT_WIDTH=16']
    for n in PCRE:
        p = os.path.join(HL, 'include', 'pcre', 'pcre2_%s.c' % n)
        if os.path.exists(p):
            u.append((p, pcre + ['-O2']))
    rt = inc + ['-DLIBHL_EXPORTS', '-O2'] + pcre[2:]
    u.append((os.path.join(HL, 'src', 'gc.c'), rt))
    u.append((os.path.join(HL, 'src', 'code.c'), rt))
    u.append((patched_module(), rt))
    for n in STD:
        u.append((os.path.join(HL, 'src', 'std', n + '.c'), rt))
    u.append((os.path.join(ROOT, 'runtime', 'aot_main.c'), inc + ['-O2']))
    hinc = lambda *d: ['-I', os.path.join(HL14, 'include', *d)]
    web = os.path.join(ROOT, 'runtime', 'web')
    fmt = inc + ['-I', web] + hinc('png') + hinc('zlib') + hinc('vorbis') + hinc('turbojpeg') + hinc('minimp3') + hinc('mikktspace') + ['-DSIZEOF_SIZE_T=4', '-O2']
    for p in fmt_sources():
        u.append((p, fmt))
    for n in ['fmt.c', 'sha1.c']:
        u.append((os.path.join(HL14, 'libs', 'fmt', n), fmt))
    u.append((os.path.join(HL14, 'libs', 'sdl', 'sdl.c'), inc + PORTS + ['-O2']))
    u.append((patched_gl(), inc + PORTS + ['-I', os.path.join(HL14, 'libs', 'sdl'), '-O2']))
    u.append((os.path.join(HL14, 'libs', 'openal', 'openal.c'), inc + ['-I', os.path.join(HL14, 'libs', 'openal'), '-include', os.path.join(web, 'al_compat.h'), '-O2']))
    for p in sorted(glob.glob(os.path.join(OUT, 'c', '*.c'))):
        u.append((p, inc + (['-O0'] if os.path.basename(p).startswith(('big_', 'trap_')) else [OPT])))
    return u


def compile_unit(job):
    src, flags = job
    rel = os.path.relpath(src, ROOT).replace('\\', '_').replace('/', '_')
    obj = os.path.join(OBJ, rel[:-2] + '.o')
    if os.path.exists(obj) and os.path.getmtime(obj) > os.path.getmtime(src) and os.path.getmtime(obj) > os.path.getmtime(__file__):
        return obj, 0, ''
    p = subprocess.run([EMCC, '-c', src, '-o', obj] + COMMON + flags, capture_output=True, text=True, errors='replace')
    return obj, p.returncode, p.stderr


def main():
    os.makedirs(OBJ, exist_ok=True)
    jobs = units()
    objs, failed = [], 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as ex:
        for obj, rc, err in ex.map(compile_unit, jobs):
            objs.append(obj)
            if rc:
                failed += 1
                print('FAIL', obj)
                print('\n'.join(l for l in err.splitlines() if 'error' in l)[:3000])
    if failed:
        sys.exit(1)
    print('compiled', len(objs), 'units')
    link = PORTS + ['-lopenal', '-sMIN_WEBGL_VERSION=2', '-sMAX_WEBGL_VERSION=2', '-sALLOW_MEMORY_GROWTH=1', '-sINITIAL_MEMORY=268435456', '-sMAXIMUM_MEMORY=4294967296', '-sSTACK_SIZE=16777216',
            '-sSUPPORT_LONGJMP=wasm', '-mnontrapping-fptoint', OPT] + os.environ.get('EXTRA_LINK', '').split()
    if TARGET == 'node':
        link += ['-sNODERAWFS=1', '-sEXIT_RUNTIME=1', '-o', os.path.join(OUT, 'deadcells_node.js')]
    else:
        os.makedirs(os.path.join(OUT, 'web'), exist_ok=True)
        link += ['-sEXIT_RUNTIME=0', '-sFORCE_FILESYSTEM=1', '-sEXPORTED_RUNTIME_METHODS=FS',
                 '--pre-js', os.path.join(ROOT, 'runtime', 'web', 'pakfs.js'), '-o', os.path.join(OUT, 'web', 'deadcells.js')]
    rsp = os.path.join(OUT, 'link.rsp')
    open(rsp, 'w').write('\n'.join('"%s"' % o.replace('\\', '/') for o in objs))
    p = subprocess.run([EMCC, '@' + rsp] + link, capture_output=True, text=True, errors='replace')
    print(p.stdout[-3000:], p.stderr[-6000:])
    print('link exit', p.returncode)
    sys.exit(p.returncode)


main()
