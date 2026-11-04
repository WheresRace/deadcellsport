#include <hl.h>
#include <string.h>
#include <mbedtls/md5.h>
#include <mbedtls/sha1.h>
#include <mbedtls/sha256.h>
#include <mbedtls/sha512.h>

/* HashLink's asset stamps use the digest native independently of TLS. */
vbyte *hlaot_dgst_make(vbyte *data, int len, vbyte *algorithm, int *size) {
	unsigned char digest[64];
	int length = 0;
	int result = -1;
	if( !size || !algorithm || len < 0 || (!data && len) ) {
		hl_error("Invalid digest arguments");
		return NULL;
	}
	*size = 0;
	if( strcmp((char*)algorithm, "SHA256") == 0 ) {
		length = 32;
		result = mbedtls_sha256_ret(data, (size_t)len, digest, 0);
	} else if( strcmp((char*)algorithm, "SHA224") == 0 ) {
		length = 28;
		result = mbedtls_sha256_ret(data, (size_t)len, digest, 1);
	} else if( strcmp((char*)algorithm, "SHA1") == 0 || strcmp((char*)algorithm, "SHA") == 0 ) {
		length = 20;
		result = mbedtls_sha1_ret(data, (size_t)len, digest);
	} else if( strcmp((char*)algorithm, "SHA512") == 0 ) {
		length = 64;
		result = mbedtls_sha512_ret(data, (size_t)len, digest, 0);
	} else if( strcmp((char*)algorithm, "SHA384") == 0 ) {
		length = 48;
		result = mbedtls_sha512_ret(data, (size_t)len, digest, 1);
	} else if( strcmp((char*)algorithm, "MD5") == 0 ) {
		length = 16;
		result = mbedtls_md5_ret(data, (size_t)len, digest);
	} else {
		hl_error("Unsupported hash algorithm: %s", hl_to_utf16((char*)algorithm));
		return NULL;
	}
	if( result != 0 ) {
		hl_error("Digest computation failed");
		return NULL;
	}
	vbyte *out = hl_gc_alloc_noptr(length);
	memcpy(out, digest, length);
	*size = length;
	return out;
}
