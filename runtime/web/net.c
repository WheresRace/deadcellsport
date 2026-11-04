#include <hl.h>

bool hlaot_socket_set_timeout( void *s, double t ) {
	return true;
}

bool hlaot_socket_set_fast_send( void *s, bool b ) {
	return true;
}

bool hlaot_socket_connect( void *s, int host, int port ) {
	return false;
}
