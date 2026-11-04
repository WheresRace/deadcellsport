// GC page pool for the wasm build.
// HashLink takes every GC page from emscripten_builtin_memalign(64 KB). dlmalloc serves an aligned request by
// over-allocating and trimming, so the hole a freed page leaves can never hold the next aligned page: freed pages
// pile up as dead holes until the 4 GB heap is full. Here pages come from 16 MB chunks that are never returned
// to malloc; a per-chunk bitmap tracks free 64 KB pages, so freed pages are reused exactly.
#include <stdlib.h>
#include <string.h>

void *emscripten_builtin_memalign( size_t align, size_t size );

#define PG_BITS 16
#define PG (1 << PG_BITS)
#define CHUNK_PAGES 256

typedef struct {
	unsigned char *base;
	int npages;
	int nfree;
	int large; // serves blocks over LARGE_PAGES
	unsigned int *bits; // 1 = page in use
} pool_chunk;

static pool_chunk *chunks;
static int nchunks, maxchunks;

static int find_run( pool_chunk *c, int n ) {
	int i, run = 0;
	if( c->nfree < n ) return -1;
	for(i=0;i<c->npages;i++) {
		if( (i & 31) == 0 && c->bits[i >> 5] == 0xFFFFFFFFu ) {
			run = 0;
			i += 31;
			continue;
		}
		if( c->bits[i >> 5] & (1u << (i & 31)) )
			run = 0;
		else if( ++run == n )
			return i - n + 1;
	}
	return -1;
}

static void mark( pool_chunk *c, int start, int n, int used ) {
	int i;
	for(i=start;i<start+n;i++) {
		if( used ) c->bits[i >> 5] |= 1u << (i & 31);
		else c->bits[i >> 5] &= ~(1u << (i & 31));
	}
	c->nfree += used ? -n : n;
}

static pool_chunk *new_chunk( int npages, int large ) {
	unsigned char *base = (unsigned char*)emscripten_builtin_memalign(PG, (size_t)npages << PG_BITS);
	pool_chunk *c;
	if( !base ) return NULL;
	if( nchunks == maxchunks ) {
		int nmax = maxchunks ? maxchunks * 2 : 64;
		pool_chunk *nc = (pool_chunk*)realloc(chunks, sizeof(pool_chunk) * nmax);
		if( !nc ) { free(base); return NULL; }
		chunks = nc;
		maxchunks = nmax;
	}
	c = &chunks[nchunks++];
	c->base = base;
	c->npages = npages;
	c->nfree = npages;
	c->large = large;
	c->bits = (unsigned int*)calloc((npages + 31) >> 5, sizeof(unsigned int));
	return c;
}

// Smallest free run of at least n pages in c (best fit), or -1.
static int find_best( pool_chunk *c, int n, int *best_len ) {
	int i, run = 0, best = -1;
	if( c->nfree < n ) return -1;
	for(i=0;i<=c->npages;i++) {
		int used = i == c->npages || (c->bits[i >> 5] & (1u << (i & 31)));
		if( !used ) { run++; continue; }
		if( run >= n && (best < 0 || run < *best_len) ) {
			best = i - run;
			*best_len = run;
		}
		run = 0;
	}
	return best;
}

static void *take( pool_chunk *c, int start, int n ) {
	mark(c, start, n, 1);
	return c->base + ((size_t)start << PG_BITS);
}

// Blocks over LARGE_PAGES pages (1 MB: decoded textures, upload buffers) live in their own chunks so that
// single pages cannot break up the runs they need; they are reused best-fit.
#define LARGE_PAGES 16

void *hlaot_page_alloc( int size ) {
	int n = (int)(((unsigned)size + PG - 1) >> PG_BITS);
	int large = n > LARGE_PAGES;
	int i, start;
	pool_chunk *c;
	if( large ) {
		int best = -1, best_len = 0, best_chunk = -1;
		for(i=0;i<nchunks;i++) {
			int len = 0;
			if( !chunks[i].large ) continue;
			start = find_best(&chunks[i], n, &len);
			if( start >= 0 && (best < 0 || len < best_len) ) { best = start; best_len = len; best_chunk = i; }
		}
		if( best >= 0 ) return take(&chunks[best_chunk], best, n);
		c = new_chunk((n + LARGE_PAGES - 1) & ~(LARGE_PAGES - 1), 1);
	} else {
		for(i=0;i<nchunks;i++) {
			if( chunks[i].large ) continue;
			start = find_run(&chunks[i], n);
			if( start >= 0 ) return take(&chunks[i], start, n);
		}
		c = new_chunk(CHUNK_PAGES, 0);
		// Near the memory limit a full chunk may not fit any more; try the exact size.
		if( !c ) c = new_chunk(n, 0);
	}
	if( c ) return take(c, 0, n);
	// Out of fresh memory: take any free run, whatever class its chunk serves.
	for(i=0;i<nchunks;i++) {
		start = find_run(&chunks[i], n);
		if( start >= 0 ) return take(&chunks[i], start, n);
	}
	return NULL;
}

void hlaot_page_free( void *ptr, int size ) {
	unsigned char *p = (unsigned char*)ptr;
	int n = (int)(((unsigned)size + PG - 1) >> PG_BITS);
	int i;
	if( !p ) return; // the GC releases its initial NULL mark buffer
	for(i=0;i<nchunks;i++) {
		pool_chunk *c = &chunks[i];
		if( p >= c->base && p < c->base + ((size_t)c->npages << PG_BITS) ) {
			mark(c, (int)((p - c->base) >> PG_BITS), n, 0);
			return;
		}
	}
	abort();
}

// Pool totals in MB, for the page's memory readout: [0] reserved by the pool, [1] free inside it.
int hlaot_page_stats( int which ) {
	long long tot = 0, fr = 0;
	int i;
	for(i=0;i<nchunks;i++) {
		tot += chunks[i].npages;
		fr += chunks[i].nfree;
	}
	return (int)(((which ? fr : tot) << PG_BITS) >> 20);
}
