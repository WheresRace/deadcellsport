#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

/* The packaged GL cache uses desktop GLSL 150. Its in/out syntax maps to
 * GLSL ES 300; fragment output locations must be declared in the source.
 */
static const GLchar *hlaot_web_shader_source(GLuint shader, const GLchar *source) {
	if( strncmp(source, "#version 150", 12) != 0 ) return source;
	const char *rest = strchr(source, '\n');
	if( !rest ) return source;
	rest++;
	size_t lines = 1;
	for( const char *p = rest; *p; p++ ) if( *p == '\n' ) lines++;
	char *out = (char*)hl_gc_alloc_noptr(strlen(rest) * 2 + lines * 48 + 32);
	char *cursor = out;
	const char *version = "#version 300 es\n";
	memcpy(cursor, version, strlen(version));
	cursor += strlen(version);
	GLint type = 0;
	glGetShaderiv(shader, GL_SHADER_TYPE, &type);
	int location = 0;
	while( *rest ) {
		const char *end = strchr(rest, '\n');
		if( !end ) end = rest + strlen(rest);
		const char *token = rest;
		while( token < end && (*token == ' ' || *token == '\t') ) token++;
		if( type == GL_FRAGMENT_SHADER && end - token >= 4 && strncmp(token, "out ", 4) == 0 ) {
			cursor += sprintf(cursor, "layout(location = %d) ", location++);
			const char *array = memchr(token, '[', (size_t)(end - token));
			if( array ) {
				long count = strtol(array + 1, NULL, 10);
				if( count > 1 && count < 32 ) location += (int)count - 1;
			}
		}
		/* 'sample' is legal in the desktop cache but reserved by GLSL ES. */
		for( const char *p = rest; p < end; ) {
			if( isalpha((unsigned char)*p) || *p == '_' ) {
				const char *word = p++;
				while( p < end && (isalnum((unsigned char)*p) || *p == '_') ) p++;
				if( p - word == 6 && memcmp(word, "sample", 6) == 0 ) {
					memcpy(cursor, "web_sample", 10);
					cursor += 10;
				} else {
					memcpy(cursor, word, (size_t)(p - word));
					cursor += p - word;
				}
			} else *cursor++ = *p++;
		}
		if( *end ) *cursor++ = '\n';
		rest = *end ? end + 1 : end;
	}
	*cursor = 0;
	return (const GLchar*)out;
}
