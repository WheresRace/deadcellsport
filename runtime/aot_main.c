#include <hl.h>
#include <hlmodule.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
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

hl_type *hlaot_types;
void **hlaot_globals;
int *hlaot_offsets;
vbyte **hlaot_strings;
int *hlaot_hashes;
void **hlaot_fptrs;

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
	hlaot_types = c->types;
	hlaot_fptrs = m->functions_ptrs;
	hlaot_globals = (void**)malloc(sizeof(void*) * c->nglobals);
	for(i=0;i<c->nglobals;i++)
		hlaot_globals[i] = m->globals_data + m->globals_indexes[i];
	hlaot_strings = (vbyte**)malloc(sizeof(void*) * c->nstrings);
	hlaot_hashes = (int*)malloc(sizeof(int) * c->nstrings);
	for(i=0;i<c->nstrings;i++) {
		hlaot_strings[i] = (vbyte*)hl_get_ustring(c,i);
		hlaot_hashes[i] = hl_hash_utf8(c->strings[i]);
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
	hl_register_thread(&ret);
	if( getenv("HLAOT_NOGC") ) hl_gc_enable(false);
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
