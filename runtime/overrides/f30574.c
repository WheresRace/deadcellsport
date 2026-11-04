#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#endif

static void *hlaot_loop_error;

static void hlaot_loop_frame(void) {
	void *exc = 0;
	void *r0 = hlaot_loop_error;
	bool alive;
	hl_trap_ctx trap0;
	hl_trap(trap0,exc,Lcatch);
	((void(*)(void*))F(31080))(r0);
	f30939();
	alive = (bool)f6568();
	hl_endtrap(trap0);
	if( !alive ) {
#ifdef __EMSCRIPTEN__
		emscripten_cancel_main_loop();
#endif
		((void(*)(int))F(6449))(0);
	}
	return;
Lcatch:;
	((void(*)(void*))F(31080))(0);
	((vclosure*)r0)->hasValue ? ((void(*)(void*,void*))((vclosure*)r0)->fun)((vdynamic*)((vclosure*)r0)->value,exc) : ((void(*)(void*))((vclosure*)r0)->fun)(exc);
}

void f30574(void) {
	static vclosure cl = {0};
	if( !cl.fun ) { cl.t = T(1292); cl.fun = (void*)f31227; }
	hlaot_loop_error = &cl;
#ifdef __EMSCRIPTEN__
	emscripten_set_main_loop(hlaot_loop_frame,0,1);
#else
	for(;;) hlaot_loop_frame();
#endif
}
