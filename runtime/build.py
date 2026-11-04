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
    src = src.replace('return (vbyte*)glGetString(name);',
                      'if( !SDL_GL_GetCurrentContext() ) return NULL;\n\treturn (vbyte*)glGetString(name);')
    src = src.replace('// globals', '#include "gl_shader_compat.h"\n\n// globals', 1)
    src = src.replace('glShaderSource(s->v.i, 1, &c, NULL);',
                      'c = hlaot_web_shader_source(s->v.i, c);\n\tglShaderSource(s->v.i, 1, &c, NULL);')
    src = src.replace('#\tdefine glBindFragDataLocation(...) ES_NOT_SUPPORTED',
                      '#\tdefine glBindFragDataLocation(...) ((void)0)')
    dst = os.path.join(OUT, 'runtime', 'gl_web.c')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'w', encoding='utf-8', newline='\n').write(src)
    return dst


def patched_sdl():
    src = open(os.path.join(HL14, 'libs', 'sdl', 'sdl.c'), encoding='utf-8').read()
    src = src.replace('SDL_Init(SDL_INIT_EVERYTHING)',
                      'SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_EVENTS | SDL_INIT_TIMER | SDL_INIT_JOYSTICK | SDL_INIT_GAMECONTROLLER)')
    # Desktop bytecode requests core OpenGL; the browser exposes GLES 3 / WebGL2.
    src = src.replace('#ifdef HL_MOBILE', '#if defined(HL_MOBILE) || defined(__EMSCRIPTEN__)')
    src = src.replace('SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, major);',
                      'major = 3; minor = 0; flags = (flags & ~6) | 8;\n\tSDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, major);')
    src = src.replace('return SDL_GL_CreateContext(win);',
                      'SDL_GLContext context = SDL_GL_CreateContext(win);\n'
                      '\tif( !context ) fprintf(stderr, "[webgl] Context creation failed: %s\\n", SDL_GetError());\n'
                      '\treturn context;')
    # The game renders at a fixed 1920x1080 on the web; the page letterboxes the canvas to 16:9.
    src = src.replace('HL_PRIM int HL_NAME(get_screen_width)() {',
                      'static void web_screen_size( int *w, int *h ) {\n'
                      '\t*w = 1920; *h = 1080;\n'
                      '}\n'
                      'void hlaot_sdl_fit( void ) {\n'
                      '\tSDL_Window *win = SDL_GL_GetCurrentWindow();\n'
                      '\tint w, h, cw, ch;\n'
                      '\tif( !win ) return;\n'
                      '\tweb_screen_size(&w, &h);\n'
                      '\tSDL_GetWindowSize(win, &cw, &ch);\n'
                      '\tif( w > 0 && h > 0 && (w != cw || h != ch) ) SDL_SetWindowSize(win, w, h);\n'
                      '}\n'
                      'HL_PRIM int HL_NAME(get_screen_width)() {\n'
                      '\tint w, h; web_screen_size(&w, &h); return w;\n'
                      '}\n'
                      'static int unused_screen_width() {')
    src = src.replace('HL_PRIM int HL_NAME(get_screen_height)() {',
                      'HL_PRIM int HL_NAME(get_screen_height)() {\n'
                      '\tint w, h; web_screen_size(&w, &h); return h;\n'
                      '}\n'
                      'static int unused_screen_height() {')
    src = src.replace('HL_PRIM int HL_NAME(get_screen_width_of_window)(SDL_Window* win) {',
                      'HL_PRIM int HL_NAME(get_screen_width_of_window)(SDL_Window* win) {\n'
                      '\treturn HL_NAME(get_screen_width)();\n'
                      '}\n'
                      'static int unused_screen_width_of_window(SDL_Window* win) {')
    src = src.replace('HL_PRIM int HL_NAME(get_screen_height_of_window)(SDL_Window* win) {',
                      'HL_PRIM int HL_NAME(get_screen_height_of_window)(SDL_Window* win) {\n'
                      '\treturn HL_NAME(get_screen_height)();\n'
                      '}\n'
                      'static int unused_screen_height_of_window(SDL_Window* win) {')
    src = src.replace('\tswitch( mode ) {\n\tcase 0: // WINDOWED',
                      '\tif( mode != 0 ) { SDL_SetWindowFullscreen(win, 0); hlaot_sdl_fit(); return true; }\n'
                      '\tswitch( mode ) {\n\tcase 0: // WINDOWED')
    dst = os.path.join(OUT, 'runtime', 'sdl_web.c')
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


# Debug: after a collection, walk back from every live large block (part 8) to what keeps it alive.
# Each level is one pass over the marked heap; prints referrer types up to a root or the stack.
GC_RETAINERS = r'''
#define RT_MAX 512
typedef struct { void *p; int size; void *ref; int refkind; int nrefs; } rt_ent;
static rt_ent rt_cur[RT_MAX];
static int rt_ncur;
static int rt_find( void *p ) {
	int i;
	for(i=0;i<rt_ncur;i++)
		if( (unsigned char*)p >= (unsigned char*)rt_cur[i].p && (unsigned char*)p < (unsigned char*)rt_cur[i].p + rt_cur[i].size ) return i;
	return -1;
}
static const char *rt_type( void *block, gc_pheader *page ) {
	static char buf[128];
	if( page->page_kind != MEM_KIND_DYNAMIC ) {
		sprintf(buf,"<kind%d>",page->page_kind);
		return buf;
	}
	hl_type *t = *(hl_type**)block;
	if( !t || GC_GET_PAGE(t) || (int)t->kind < 0 || t->kind > HLAST ) return "<raw>";
	char *s = hl_to_utf8(hl_type_str(t));
	snprintf(buf,sizeof(buf),"%s",s);
	return buf;
}
static void rt_note( int i, void *ref, int kind ) {
	if( rt_cur[i].nrefs++ == 0 ) { rt_cur[i].ref = ref; rt_cur[i].refkind = kind; }
}
static void rt_scan_range( void **a, void **b, int kind, int exact ) {
	while( a < b ) {
		void *p = *a;
		if( p ) {
			int i = rt_find(p);
			if( i >= 0 && (!exact || p == rt_cur[i].p) ) rt_note(i, a, kind);
		}
		a++;
	}
}
void hlaot_gc_retainers( void ) {
	int pid, i, level;
	rt_ncur = 0;
	for(pid=GC_LARGE_PART << PAGE_KIND_BITS;pid<GC_ALL_PAGES;pid++) {
		gc_pheader *ph = gc_pages[pid];
		for(;ph;ph=ph->next_page)
			if( rt_ncur < RT_MAX ) { rt_cur[rt_ncur].p = ph->base; rt_cur[rt_ncur].size = ph->page_size; rt_ncur++; }
	}
	printf("RETAIN start %d large blocks\n", rt_ncur);
	for(level=0;level<8 && rt_ncur;level++) {
		for(i=0;i<rt_ncur;i++) { rt_cur[i].nrefs = 0; rt_cur[i].ref = NULL; }
		for(i=0;i<gc_roots_count;i++) {
			void *p = *gc_roots[i];
			int k = p ? rt_find(p) : -1;
			if( k >= 0 && p == rt_cur[k].p ) rt_note(k, gc_roots[i], 1);
		}
		for(i=0;i<gc_threads.count;i++) {
			hl_thread_info *t = gc_threads.threads[i];
			rt_scan_range((void**)t->stack_cur, (void**)t->stack_top, 2, 0);
		}
		for(pid=0;pid<GC_ALL_PAGES;pid++) {
			gc_pheader *ph = gc_pages[pid];
			if( !MEM_HAS_PTR(ph ? ph->page_kind : 0) ) continue;
			for(;ph;ph=ph->next_page) {
				gc_allocator_page_data *p = &ph->alloc;
				int bid;
				for(bid=p->first_block;bid<p->max_blocks;bid++) {
					if( p->sizes && !p->sizes[bid] ) continue;
					if( (ph->bmp[bid>>3] & (1<<(bid&7))) == 0 ) continue;
					int size = p->sizes ? p->sizes[bid] * p->block_size : p->block_size;
					void **blk = (void**)(ph->base + bid * p->block_size);
					rt_scan_range(blk, blk + size / sizeof(void*), 0, 1);
					if( p->sizes ) bid += p->sizes[bid] - 1;
				}
			}
		}
		// report and step up to the referrers
		rt_ent next[RT_MAX];
		int nnext = 0;
		for(i=0;i<rt_ncur;i++) {
			rt_ent *e = &rt_cur[i];
			gc_pheader *pp = GC_GET_PAGE(e->p);
			const char *ty = pp ? rt_type(e->p, pp) : "?";
			if( !e->nrefs ) { printf("RETAIN L%d %p %dKB %s <- NOTHING\n",level,e->p,e->size>>10,ty); continue; }
			if( e->refkind == 1 ) { printf("RETAIN L%d %p %dKB %s <- ROOT %p\n",level,e->p,e->size>>10,ty,e->ref); continue; }
			if( e->refkind == 2 ) { printf("RETAIN L%d %p %dKB %s <- STACK %p =%p (%d refs) cur=%p top=%p\n",level,e->p,e->size>>10,ty,e->ref,*(void**)e->ref,e->nrefs,gc_threads.threads[0]->stack_cur,gc_threads.threads[0]->stack_top); continue; }
			// find the block holding the reference
			gc_pheader *rp = GC_GET_PAGE(e->ref);
			void *rb = e->ref;
			int bid = rp ? gc_allocator_get_block_interior(rp, &rb) : -1;
			if( bid < 0 ) { printf("RETAIN L%d %p %s <- ? %p\n",level,e->p,ty,e->ref); continue; }
			int rsize = rp->alloc.sizes ? rp->alloc.sizes[bid] * rp->alloc.block_size : rp->alloc.block_size;
			printf("RETAIN L%d %p %dKB %s <- %s @+%d (%d refs)\n",level,e->p,e->size>>10,ty,rt_type(rb,rp),(int)((char*)e->ref-(char*)rb),e->nrefs);
			int j, dup = 0;
			for(j=0;j<nnext;j++) if( next[j].p == rb ) dup = 1;
			if( !dup && nnext < RT_MAX ) { next[nnext].p = rb; next[nnext].size = rsize; nnext++; }
		}
		memcpy(rt_cur, next, sizeof(rt_ent) * nnext);
		rt_ncur = nnext;
	}
	fflush(stdout);
}
'''


def patched_gc():
    # The GC grows small-object pages up to ~2.5 MB once a size class has many pages. In the 4 GB wasm heap
    # one surviving object then pins the whole page, and the mixed page sizes fragment malloc until large
    # blocks (8 MB textures) no longer fit. Keep every small-object page at 64 KB.
    alloc = open(os.path.join(HL, 'src', 'allocator.c'), encoding='utf-8').read()
    old = '\t// increase size based on previously allocated pages\n\tif( block < 256 ) {'
    if old not in alloc:
        raise SystemExit('allocator.c: page growth code not found')
    alloc = alloc.replace(old, '\t// increase size based on previously allocated pages (disabled for wasm)\n\tif( block < 256 && 0 ) {')
    # Debug: per size class page memory and free space, valid right after a collection.
    alloc += '''
void hlaot_gc_breakdown() {
	int pid;
	for(pid=0;pid<GC_ALL_PAGES;pid++) {
		gc_pheader *ph = gc_pages[pid];
		double total = 0, fr = 0;
		int count = 0;
		while( ph ) {
			count++;
			total += ph->page_size;
			fr += gc_free_memory(ph);
			ph = ph->next_page;
		}
		if( total >= (4 << 20) )
			printf("GC-PART part=%d kind=%d pages=%d total=%.0fMB free=%.0fMB\\n", pid >> PAGE_KIND_BITS, pid & ((1 << PAGE_KIND_BITS) - 1), count, total / 1048576, fr / 1048576);
	}
}
'''
    gc = open(os.path.join(HL, 'src', 'gc.c'), encoding='utf-8').read()
    gc = gc.replace('#include "allocator.c"', '#include "allocator_aot.c"', 1)
    # Pages come from runtime/gc_pages.c, a pool that reuses freed pages (see the note there).
    for old, new in (('\treturn emscripten_builtin_memalign(GC_PAGE_SIZE, size);', '\treturn hlaot_page_alloc(size);'),
                     ('\temscripten_builtin_free(ptr);', '\thlaot_page_free(ptr, size);'),
                     ('static void *gc_alloc_page_memory( int size );', 'static void *gc_alloc_page_memory( int size );\nvoid *hlaot_page_alloc( int size );\nvoid hlaot_page_free( void *ptr, int size );')):
        if old not in gc:
            raise SystemExit('gc.c: %r not found' % old)
        gc = gc.replace(old, new, 1)
    gc += GC_RETAINERS
    d = os.path.join(OUT, 'runtime')
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'allocator_aot.c'), 'w', encoding='utf-8', newline='\n').write(alloc)
    dst = os.path.join(d, 'gc_aot.c')
    open(dst, 'w', encoding='utf-8', newline='\n').write(gc)
    return dst


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
    u.append((patched_gc(), rt))
    u.append((os.path.join(ROOT, 'runtime', 'gc_pages.c'), ['-O2']))
    u.append((os.path.join(HL, 'src', 'code.c'), rt))
    u.append((patched_module(), rt))
    for n in STD:
        u.append((os.path.join(HL, 'src', 'std', n + '.c'), rt))
    u.append((os.path.join(ROOT, 'runtime', 'aot_main.c'), inc + ['-O2']))
    hinc = lambda *d: ['-I', os.path.join(HL14, 'include', *d)]
    web = os.path.join(ROOT, 'runtime', 'web')
    crypto = inc + hinc('mbedtls', 'include') + ['-O2']
    for n in ['md5', 'sha1', 'sha256', 'sha512']:
        u.append((os.path.join(HL14, 'include', 'mbedtls', 'library', n + '.c'), crypto))
    u.append((os.path.join(web, 'digest.c'), crypto))
    u.append((os.path.join(web, 'net.c'), inc + ['-O2']))
    u.append((os.path.join(web, 'platform.c'), inc + ['-O2']))
    u.append((os.path.join(web, 'gog.c'), inc + ['-O2']))
    fmt = inc + ['-I', web] + hinc('png') + hinc('zlib') + hinc('vorbis') + hinc('turbojpeg') + hinc('minimp3') + hinc('mikktspace') + ['-DSIZEOF_SIZE_T=4', '-O2']
    for p in fmt_sources():
        u.append((p, fmt))
    for n in ['fmt.c', 'sha1.c']:
        u.append((os.path.join(HL14, 'libs', 'fmt', n), fmt))
    u.append((patched_sdl(), inc + PORTS + ['-I', os.path.join(HL14, 'libs', 'sdl'), '-O2']))
    u.append((patched_gl(), inc + PORTS + ['-I', web, '-I', os.path.join(HL14, 'libs', 'sdl'), '-O2']))
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
            '-sSUPPORT_LONGJMP=wasm', '-mnontrapping-fptoint', '-Wl,--wrap=hl_null_access', '-Wl,--wrap=hl_throw', '-Wl,--wrap=hl_sys_sleep', '-Wl,--wrap=hl_alloc_bytes', OPT] + os.environ.get('EXTRA_LINK', '').split()
    if TARGET == 'node':
        link += ['-sNODERAWFS=1', '-sEXIT_RUNTIME=1', '-o', os.path.join(OUT, 'deadcells_node.js')]
    else:
        os.makedirs(os.path.join(OUT, 'web'), exist_ok=True)
        link += ['-sEXIT_RUNTIME=0', '-sFORCE_FILESYSTEM=1', '-lidbfs.js', '-sEXPORTED_RUNTIME_METHODS=FS',
                 '--pre-js', os.path.join(ROOT, 'runtime', 'web', 'pakfs.js'), '-o', os.path.join(OUT, 'web', 'deadcells.js')]
    rsp = os.path.join(OUT, 'link.rsp')
    open(rsp, 'w').write('\n'.join('"%s"' % o.replace('\\', '/') for o in objs))
    p = subprocess.run([EMCC, '@' + rsp] + link, capture_output=True, text=True, errors='replace')
    print(p.stdout[-3000:], p.stderr[-6000:])
    print('link exit', p.returncode)
    sys.exit(p.returncode)


if __name__ == '__main__':
    main()
