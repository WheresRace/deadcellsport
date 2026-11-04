#include <hl.h>
#include <hlmodule.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#include <emscripten/stack.h>
#endif

extern void *hlaot_functions[];
extern const int hlaot_nfunctions;
extern const int hlaot_offset_spec[];
extern const int hlaot_noffsets;
extern const int hlaot_bytecode_size;
extern void *hlaot_natives[];
void *hlaot_static_call( void *fun, hl_type *t, void **args, vdynamic *out );
void *hlaot_get_wrapper( hl_type *t );
HL_API void hl_gc_enable( bool b );
HL_API void hl_gc_stats( double *total_allocated, double *allocation_count, double *current_memory );

void __real_hl_null_access( void );

// Linked with --wrap=hl_null_access so libhl's own null errors are traced too.
void __wrap_hl_null_access( void ) {
	static int traced;
	if( traced++ < 4 ) {
		static char stack[8192];
		emscripten_get_callstack(EM_LOG_C_STACK, stack, sizeof(stack));
		fprintf(stderr,"[null access]\n%s\n",stack);
	}
	__real_hl_null_access();
}

// Linked with --wrap=hl_alloc_bytes: trace big buffers with their stack.
vbyte *__real_hl_alloc_bytes( int size );
vbyte *__wrap_hl_alloc_bytes( int size ) {
	static int traced;
	if( (size >= (4 << 20) || size < 0) && traced++ < 80 ) {
		static char stack[4096];
		emscripten_get_callstack(EM_LOG_C_STACK, stack, sizeof(stack));
		fprintf(stderr,"[bigalloc] %d KB\n%s\n",size >> 10,stack);
	}
	return __real_hl_alloc_bytes(size);
}

void __real_hl_throw( vdynamic *v );

// Linked with --wrap=hl_throw: trace the first exceptions with their C stack.
void __wrap_hl_throw( vdynamic *v ) {
	static int traced;
	const char *msg = v ? hl_to_utf8(hl_to_string(v)) : "null";
	// Eof ends every stream read and the first-run save read fails by design; don't spend the budget on them.
	// New runs throw (and catch) "Item X was not revealed first" for every locked item.
	if( strcmp(msg,"Eof") != 0 && strstr(msg,"Can't read save") == NULL && strstr(msg,"was not revealed first") == NULL && traced++ < 60 ) {
		static char stack[8192];
		emscripten_get_callstack(EM_LOG_C_STACK, stack, sizeof(stack));
		fprintf(stderr,"[throw] %s\n%s\n",msg,stack);
	}
	__real_hl_throw(v);
}

// Linked with --wrap=hl_sys_sleep: sleeping on the page's main thread only freezes it, so return at once.
void __wrap_hl_sys_sleep( double f ) {
	static int traced;
	if( traced++ < 3 ) {
		static char stack[8192];
		emscripten_get_callstack(EM_LOG_C_STACK, stack, sizeof(stack));
		fprintf(stderr,"[sleep] %g\n%s\n",f,stack);
	}
}

void hlaot_null_access( void ) {
	hl_null_access();
}

void hlaot_null_site( int f, int site ) {
	fprintf(stderr,"[null access] f%d site %d\n",f,site);
	hlaot_null_access();
}

static bool hlaot_force_nogc;
static bool hlaot_frame_gc;
static bool hlaot_gc_requested;
static double hlaot_gc_last_mark;

void hlaot_gc_enable( bool enabled ) {
	if( hlaot_frame_gc ) return;
	hl_gc_enable(enabled && !hlaot_force_nogc);
}

void hlaot_gc_major( void ) {
	if( hlaot_frame_gc ) { hlaot_gc_requested = true; return; }
	if( !hlaot_force_nogc ) hl_gc_major();
}

__attribute__((weak)) void hlaot_sdl_fit( void );

// Loop heads in translated code tick hlaot_ticks; every 1M ticks we check whether the current frame has run too long.
unsigned hlaot_ticks;
static double hlaot_frame_start, hlaot_hang_next;

void hlaot_loop_check( int findex ) {
	static int reports;
	double now = emscripten_get_now();
	if( hlaot_frame_start == 0 || now < hlaot_hang_next || reports >= 6 ) return;
	hlaot_hang_next = now + 8000;
	if( now - hlaot_frame_start < 8000 ) return;
	static char stack[8192];
	reports++;
	emscripten_get_callstack(EM_LOG_C_STACK, stack, sizeof(stack));
	fprintf(stderr,"[hang] frame running %.0f s, in f%d\n%s\n",(now - hlaot_frame_start) / 1000,findex,stack);
}

// The GC scans the shadow stack conservatively and accepts pointers into the middle of a block. Frames of
// returned calls leave old values below the stack pointer; new frames that do not overwrite every slot
// (C library locals, padding) then expose them to the scan, so a decoded texture or upload buffer seen once on
// the stack can stay pinned for good. Clear the dead part of the stack while the stack is shallow: walk down
// from the stack pointer, zeroing every non-zero 4 KB block, until 256 KB in a row were already clear.
__attribute__((noinline)) static void hlaot_clear_dead_stack( void ) {
	uintptr_t end = emscripten_stack_get_end();
	uintptr_t p = (emscripten_stack_get_current() - 256) & ~(uintptr_t)4095;
	int clean = 0;
	while( p > end + 4096 && clean < 64 ) {
		unsigned int *w = (unsigned int*)(p - 4096);
		unsigned int acc = 0;
		int i;
		for(i=0;i<1024;i++) acc |= w[i];
		if( acc ) {
			for(i=0;i<1024;i++) w[i] = 0;
			clean = 0;
		} else
			clean++;
		p -= 4096;
	}
}

// Called first thing in each main-loop frame, with the stack pointer JS entered with: everything above it is
// the dead boot call chain (see runMainLoop), which must not be scanned. Has no frame of its own.
__attribute__((noinline)) void hlaot_mark_stack_top( void ) {
	hl_get_thread()->stack_top = (void*)emscripten_stack_get_current();
}

void hlaot_frame_begin( void ) {
	double total, count, mem, budget;
	hlaot_clear_dead_stack();
	hlaot_frame_start = emscripten_get_now();
	hlaot_hang_next = hlaot_frame_start + 8000;
	if( hlaot_sdl_fit ) hlaot_sdl_fit();
	if( !hlaot_frame_gc ) return;
	hl_gc_stats(&total,&count,&mem);
	// Fixed budget: a budget that grows with the heap lets garbage pile up toward the 4 GB wasm limit.
	budget = 128.0 * 1024 * 1024;
	if( hlaot_gc_requested || total - hlaot_gc_last_mark > budget ) {
		hlaot_gc_requested = false;
		hl_gc_major();
		hl_gc_stats(&hlaot_gc_last_mark,&count,&mem);
	}
}

hl_type *hlaot_types;
void **hlaot_globals;
int *hlaot_offsets;
vbyte **hlaot_strings;
int *hlaot_hashes;
void **hlaot_fptrs;
static hl_code *hlaot_code;

char *hlaot_bytes( int i ) {
	return hlaot_code->version >= 5 ? hlaot_code->bytes + hlaot_code->bytes_pos[i] : (char*)hlaot_code->strings[i];
}

jit_ctx *hl_jit_alloc() { return NULL; }
void hl_jit_free( jit_ctx *ctx, h_bool can_reset ) {}
void hl_jit_reset( jit_ctx *ctx, hl_module *m ) {}
void hl_jit_init( jit_ctx *ctx, hl_module *m ) {}
int hl_jit_function( jit_ctx *ctx, hl_module *m, hl_function *f ) { return -1; }
void *hl_jit_code( jit_ctx *ctx, hl_module *m, int *codesize, hl_debug_infos **debug, hl_module *previous ) { return NULL; }
void hl_jit_patch_method( void *old_fun, void **new_fun_table ) {}

static void aot_setup( hl_module *m ) {
	hl_code *c = m->code;
	int i;
	hlaot_code = c;
	hlaot_types = c->types;
	hlaot_fptrs = m->functions_ptrs;
	hlaot_globals = (void**)malloc(sizeof(void*) * c->nglobals);
	for(i=0;i<c->nglobals;i++)
		hlaot_globals[i] = m->globals_data + m->globals_indexes[i];
	hlaot_strings = (vbyte**)malloc(sizeof(void*) * c->nstrings);
	hlaot_hashes = (int*)malloc(sizeof(int) * c->nstrings);
	for(i=0;i<c->nstrings;i++) {
		hlaot_strings[i] = (vbyte*)hl_get_ustring(c,i);
		// Cache the name like the JIT does, so Reflect.fields / hl_field_name can map hashes back.
		hlaot_hashes[i] = hl_hash_gen((uchar*)hlaot_strings[i],true);
	}
	hlaot_offsets = (int*)malloc(sizeof(int) * (hlaot_noffsets + 1));
	for(i=0;i<hlaot_noffsets;i++) {
		const int *s = hlaot_offset_spec + i * 4;
		hl_type *t = c->types + s[1];
		if( s[0] == 0 )
			hlaot_offsets[i] = hl_get_obj_rt(t)->fields_indexes[s[2]];
		else
			hlaot_offsets[i] = t->tenum->constructs[s[2]].offsets[s[3]];
	}
	hl_setup.static_call = hlaot_static_call;
	hl_setup.get_wrapper = hlaot_get_wrapper;
	hl_setup.static_call_ref = false;
}

void hlaot_install_functions( hl_module *m ) {
	int i;
	if( m->code->nfunctions != hlaot_nfunctions ) hl_fatal("bytecode does not match generated code");
	for(i=0;i<m->code->nfunctions;i++)
		m->functions_ptrs[m->code->functions[i].findex] = hlaot_functions[i];
}

void *hlaot_native( int i ) {
	return hlaot_natives[i];
}

static hl_code *load_code( const char *file ) {
	FILE *f = fopen(file,"rb");
	char *err = NULL;
	int size, pos = 0;
	char *data;
	hl_code *code;
	if( !f ) { fprintf(stderr,"cannot open %s\n",file); return NULL; }
	fseek(f,0,SEEK_END);
	size = (int)ftell(f);
	fseek(f,0,SEEK_SET);
	data = (char*)malloc(size);
	while( pos < size ) {
		int r = (int)fread(data + pos,1,size-pos,f);
		if( r <= 0 ) break;
		pos += r;
	}
	fclose(f);
	if( size != hlaot_bytecode_size ) fprintf(stderr,"warning: bytecode size %d, generated for %d\n",size,hlaot_bytecode_size);
	code = hl_code_read((unsigned char*)data,size,&err);
	free(data);
	if( !code ) fprintf(stderr,"%s\n",err ? err : "invalid bytecode");
	return code;
}

// Translated functions pass their pointer-register frame here. Being opaque to the compiler, it forces those
// registers into linear memory across calls, where the GC's stack scan finds them.
__attribute__((noinline)) void hlaot_roots( void *frame ) {
}

// Live GC memory in MB, for the page's memory readout.
EMSCRIPTEN_KEEPALIVE int hlaot_gc_live_mb( void ) {
	double total, count, mem;
	hl_gc_stats(&total,&count,&mem);
	return (int)(mem / (1024 * 1024));
}

// Debug: Module._hlaot_gc_report() runs two collections with GC_PROFILE_MEM (16) set; the second one
// prints "GC-PROFILE-MEM <total> MB, <free>% free", i.e. how much of the page memory is garbage or holes.
HL_API int hl_gc_get_flags( void );
HL_API void hl_gc_set_flags( int f );
void hlaot_gc_breakdown( void );
void hlaot_gc_retainers( void );
EMSCRIPTEN_KEEPALIVE void hlaot_gc_report( void ) {
	int f = hl_gc_get_flags();
	hlaot_clear_dead_stack();
	printf("RETAIN sp=%p base=%p gctop=%p\n",(void*)emscripten_stack_get_current(),(void*)emscripten_stack_get_base(),hl_get_thread()->stack_top);
	hl_gc_major();
	hl_gc_set_flags(f | 16);
	hl_gc_major();
	hl_gc_set_flags(f);
	hlaot_gc_breakdown();
	if( getenv("HLAOT_RETAIN") || 1 ) hlaot_gc_retainers();
}

// Debug: memory in MB: [0] malloc in use, [1] malloc holes, [2] GC page memory, [3] GC page pool, [4] free in pool.
#include <malloc.h>
int hlaot_page_stats( int which );
EMSCRIPTEN_KEEPALIVE int *hlaot_malloc_stats( void ) {
	static int out[5];
	out[3] = hlaot_page_stats(0);
	out[4] = hlaot_page_stats(1);
	struct mallinfo mi = mallinfo();
	double total, count, mem;
	hl_gc_stats(&total,&count,&mem);
	out[0] = (int)((unsigned)mi.uordblks >> 20);
	out[1] = (int)((unsigned)mi.fordblks >> 20);
	out[2] = (int)(mem / (1024 * 1024));
	return out;
}

// TEMP debug: Module._hlaot_debug_kill_hero() runs en.Hero.kill (#2066) on pr.Game.ME (global 429), GOG bytecode.
void f2066( void *hero );
EMSCRIPTEN_KEEPALIVE void hlaot_debug_kill_hero( void ) {
	hl_trap_ctx ctx;
	vdynamic *exc;
	vdynamic *cl = *(vdynamic**)hlaot_globals[429];
	vdynamic *game = cl ? (vdynamic*)hl_dyn_getp(cl,hl_hash_utf8("ME"),&hlt_dyn) : NULL;
	vdynamic *hero = game ? (vdynamic*)hl_dyn_getp(game,hl_hash_utf8("hero"),&hlt_dyn) : NULL;
	if( !hero ) { fprintf(stderr,"[debug] no hero\n"); return; }
	hl_trap(ctx,exc,on_exc);
	f2066(hero);
	hl_endtrap(ctx);
	fprintf(stderr,"[debug] hero killed\n");
	return;
on_exc:
	fprintf(stderr,"[debug] kill threw %s\n",hl_to_utf8(hl_to_string(exc)));
}

// TEMP debug: write a level id into hlaot_debug_goto_buf(), then hlaot_debug_goto() runs
// cine.LevelTransition.goto (#9734, GOG bytecode), the same transition an exit door starts.
void *f9734( void *id );
void *f16( vbyte *bytes, int len );
static char hlaot_goto_id[64];
EMSCRIPTEN_KEEPALIVE char *hlaot_debug_goto_buf( void ) { return hlaot_goto_id; }
EMSCRIPTEN_KEEPALIVE void hlaot_debug_goto( void ) {
	hl_trap_ctx ctx;
	vdynamic *exc;
	uchar *id = (uchar*)hl_gc_alloc_noptr(64 * sizeof(uchar));
	int i;
	for(i=0;i<63 && hlaot_goto_id[i];i++) id[i] = (uchar)hlaot_goto_id[i];
	id[i] = 0;
	hl_trap(ctx,exc,on_exc);
	f9734(f16((vbyte*)id,i)); // String.__alloc__ (#16)
	hl_endtrap(ctx);
	fprintf(stderr,"[debug] goto %s\n",hlaot_goto_id);
	return;
on_exc:
	fprintf(stderr,"[debug] goto %s threw %s\n",hlaot_goto_id,hl_to_utf8(hl_to_string(exc)));
}

int main( int argc, char *argv[] ) {
	static vclosure cl;
	vdynamic *ret;
	bool isExc = false;
	const char *file = argc > 1 ? argv[1] : "hlboot.dat";
	hl_code *code;
	hl_module *m;
	hl_global_init();
	hl_setup.file_path = (pchar*)file;
	hl_setup.sys_args = (pchar**)(argv + 2);
	hl_setup.sys_nargs = argc > 2 ? argc - 2 : 0;
	hl_sys_init();
	// main unwinds once the browser main loop starts and later frames begin at the stack base, so scan from there.
	hl_register_thread((void*)emscripten_stack_get_base());
	hlaot_force_nogc = getenv("HLAOT_NOGC") != NULL;
	hlaot_frame_gc = !hlaot_force_nogc && getenv("HLAOT_GC") && strcmp(getenv("HLAOT_GC"),"frame") == 0;
	if( hlaot_force_nogc || hlaot_frame_gc ) hl_gc_enable(false);
	code = load_code(file);
	if( !code ) return 1;
	m = hl_module_alloc(code);
	if( !m ) return 2;
	if( !hl_module_init(m,false) ) return 3;
	aot_setup(m);
	fprintf(stderr,"[aot] module ready: %d functions, %d natives, %d offsets\n",code->nfunctions,code->nnatives,hlaot_noffsets);
	cl.t = code->functions[m->functions_indexes[code->entrypoint]].type;
	cl.fun = m->functions_ptrs[code->entrypoint];
	cl.hasValue = 0;
	ret = hl_dyn_call_safe(&cl,NULL,0,&isExc);
	if( isExc ) {
		hl_print_uncaught_exception(ret);
		return 1;
	}
	fprintf(stderr,"[aot] entrypoint returned\n");
	return 0;
}
