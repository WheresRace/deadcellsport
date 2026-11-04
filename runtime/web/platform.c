#include <hl.h>
#include <stdio.h>
#include <AL/al.h>

#define AL_EFX_FIRST 0x20005
#define AL_EFX_LAST 0x2000D

void hlaot_ui_winlog_set_text( void *w, vbyte *txt, bool autoScroll ) {
	if( txt ) fprintf(stderr,"[winlog] %s\n",hl_to_utf8((uchar*)txt));
}

int hlaot_ui_dialog( vbyte *title, vbyte *message, int flags ) {
	fprintf(stderr,"[dialog] %s: %s\n",title ? hl_to_utf8((uchar*)title) : "",message ? hl_to_utf8((uchar*)message) : "");
	return 0;
}

void hlaot_al_sourcei( int source, int param, int value ) {
	if( param >= AL_EFX_FIRST && param <= AL_EFX_LAST ) return;
	alSourcei(source,param,value);
}

void hlaot_al_source3i( int source, int param, int v1, int v2, int v3 ) {
	if( param >= AL_EFX_FIRST && param <= AL_EFX_LAST ) return;
	alSource3i(source,param,v1,v2,v3);
}

void hlaot_al_sourcef( int source, int param, float value ) {
	if( param >= AL_EFX_FIRST && param <= AL_EFX_LAST ) return;
	alSourcef(source,param,value);
}
