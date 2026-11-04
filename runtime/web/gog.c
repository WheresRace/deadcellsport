#include <hl.h>
#include <string.h>

// GOG Galaxy is offline in the browser: no sign-in, no achievements, only the base game installed.

static vbyte *gog_string( const char *s ) {
	int len = (int)strlen(s) + 1;
	vbyte *b = hl_gc_alloc_noptr(len);
	memcpy(b,s,len);
	return b;
}

void gog_init( vbyte *client_id, vbyte *client_secret, void *on_event ) {
}

void gog_process_data( void ) {
}

bool gog_signed_in( void ) {
	return false;
}

bool gog_is_logged_on( void ) {
	return false;
}

vbyte *gog_get_galaxy_id( void ) {
	vbyte *id = hl_gc_alloc_noptr(8);
	memset(id,0,8);
	return id;
}

vbyte *gog_get_persona_name( void ) {
	return gog_string("Player");
}

vbyte *gog_get_current_game_language( void ) {
	return gog_string("English");
}

bool gog_is_dlc_installed( vbyte *id ) {
	return false;
}

void gog_request_encrypted_app_ticket( vbyte *data, int size ) {
}

void gog_show_overlay_with_web_page( vbyte *url ) {
}

void gog_request_stats_and_achievements( void ) {
}

void gog_store_stats_and_achievements( void ) {
}

bool gog_has_achievement( vbyte *name ) {
	return false;
}

void gog_set_achievement( vbyte *name ) {
}
