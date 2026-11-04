#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#endif

static void *hlaot_loop_error;
void hlaot_frame_begin( void );

static void hlaot_loop_body(void) {
	void *exc = 0;
	void *r0 = hlaot_loop_error;
	bool alive;
	hl_trap_ctx trap0;
	hlaot_frame_begin();
	hl_trap(trap0,exc,Lcatch);
	((void(*)(void*))@N(std.set_error_handler))(r0);
	@F(haxe.$MainLoop.tick)();
	alive = (bool)@F(hxd.$System.mainLoop)();
	hl_endtrap(trap0);
	if( !alive ) {
#ifdef __EMSCRIPTEN__
		emscripten_cancel_main_loop();
#endif
		((void(*)(int))@N(std.sys_exit))(0);
	}
	return;
Lcatch:;
	((void(*)(void*))@N(std.set_error_handler))(0);
	((vclosure*)r0)->hasValue ? ((void(*)(void*,void*))((vclosure*)r0)->fun)((vdynamic*)((vclosure*)r0)->value,exc) : ((void(*)(void*))((vclosure*)r0)->fun)(exc);
}

void hlaot_mark_stack_top( void );

// Called from JS each frame. emscripten_set_main_loop unwinds out of main without restoring the stack
// pointer, so the boot frames stay allocated above it, dead; tell the GC its stack starts here instead.
// No locals live in memory here, so the stack pointer is still the one JS called in with.
static void hlaot_loop_frame(void) {
	hlaot_mark_stack_top();
	hlaot_loop_body();
}

void @F(hxd.$System.runMainLoop)(void) {
	static vclosure cl = {0};
	if( !cl.fun ) { cl.t = T(@T(0)); cl.fun = (void*)@SC(0); }
	hlaot_loop_error = &cl;
#ifdef __EMSCRIPTEN__
	emscripten_set_main_loop(hlaot_loop_frame,0,1);
#else
	for(;;) hlaot_loop_frame();
#endif
}
