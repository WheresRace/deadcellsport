#include <stdio.h>

/* Boot.initPlatform: the web port has no Steam desktop client.
 * Leave the Steam API uninitialized so optional services remain unavailable.
 */
void f6252(void* args) {
	(void)args;
	fprintf(stderr, "[platform] Web startup: Steam desktop initialization skipped\n");
}
