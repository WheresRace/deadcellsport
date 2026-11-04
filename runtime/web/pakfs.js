var HLAOT_CHUNK = 1 << 20;
var HLAOT_MAX_CHUNKS = 256;

function hlaotRangeFile(url, size) {
  var cache = new Map();

  function fetchRange(from, to) {
    var xhr = new XMLHttpRequest();
    // Blob slices keep multi-gigabyte local archives out of the wasm heap.
    var local = typeof url !== 'string';
    var requestUrl = local ? URL.createObjectURL(url.slice(from, to)) : url;
    xhr.open('GET', requestUrl, false);
    if (!local) xhr.setRequestHeader('Range', 'bytes=' + from + '-' + (to - 1));
    xhr.overrideMimeType('text/plain; charset=x-user-defined');
    try { xhr.send(null); }
    finally { if (local) URL.revokeObjectURL(requestUrl); }
    if (xhr.status !== 206 && xhr.status !== 200) throw new Error('range read failed ' + url + ' ' + xhr.status);
    var s = xhr.responseText;
    if (!local && xhr.status === 200 && s.length === size) s = s.slice(from, to);
    if (s.length !== to - from) throw new Error('Incomplete archive read');
    var out = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) out[i] = s.charCodeAt(i) & 0xff;
    return out;
  }

  function load(first, last) {
    var start = -1;
    for (var c = first; c <= last + 1; c++) {
      var missing = c <= last && !cache.has(c);
      if (missing && start < 0) start = c;
      if (!missing && start >= 0) {
        var from = start * HLAOT_CHUNK;
        var to = Math.min(c * HLAOT_CHUNK, size);
        var data = fetchRange(from, to);
        for (var k = start; k < c; k++) {
          var off = (k - start) * HLAOT_CHUNK;
          cache.set(k, data.slice(off, Math.min(off + HLAOT_CHUNK, data.length)));
        }
        start = -1;
      }
    }
  }

  return function read(buffer, offset, length, position) {
    if (length <= 0 || position >= size) return 0;
    length = Math.min(length, size - position);
    var first = Math.floor(position / HLAOT_CHUNK);
    var last = Math.floor((position + length - 1) / HLAOT_CHUNK);
    load(first, last);
    var done = 0;
    for (var c = first; c <= last; c++) {
      var chunk = cache.get(c);
      cache.delete(c);
      cache.set(c, chunk);
      var base = c * HLAOT_CHUNK;
      var from = Math.max(position, base) - base;
      var to = Math.min(position + length, base + chunk.length) - base;
      buffer.set(chunk.subarray(from, to), offset + done);
      done += to - from;
    }
    while (cache.size > HLAOT_MAX_CHUNKS) cache.delete(cache.keys().next().value);
    return done;
  };
}

function hlaotMountRange(dir, name, url, size) {
  var node = FS.createFile(dir, name, {}, true, false);
  var read = hlaotRangeFile(url, size);
  node.contents = null;
  Object.defineProperty(node, 'usedBytes', { get: function() { return size; } });
  var ops = {};
  for (var k in node.stream_ops) ops[k] = node.stream_ops[k];
  ops.read = function(stream, buffer, offset, length, position) {
    return read(buffer, offset, length, position);
  };
  ops.mmap = function() { throw new FS.ErrnoError(19); };
  node.stream_ops = ops;
}

Module.arguments = Module.arguments || [Module.hlaotBoot || 'hlboot_gl.dat'];
Module.preRun = Module.preRun || [];
Module.preRun.push(function() {
  var dir = '/game';
  // Normal HashLink GC by default; ?gcframe collects only between frames, ?nogc never.
  ENV.HLAOT_GC = /[?&]nogc/.test(location.search) ? 'off' : /[?&]gcframe/.test(location.search) ? 'frame' : 'auto';
  if (ENV.HLAOT_GC === 'off') ENV.HLAOT_NOGC = '1';
  FS.mkdir(dir);
  FS.chdir(dir);
  FS.mkdir(dir + '/save');
  FS.mount(IDBFS, {}, dir + '/save');
  addRunDependency('hlaot-save');
  FS.syncfs(true, function(error) {
    if (error) Module.printErr('Browser saves unavailable: ' + error);
    removeRunDependency('hlaot-save');
  });
  var saving = false;
  var persist = function() {
    if (saving) return;
    saving = true;
    FS.syncfs(false, function() { saving = false; });
  };
  setInterval(persist, 5000);
  addEventListener('pagehide', persist);
  var base = Module.hlaotBase || '';
  var boot = Module.hlaotBoot || 'hlboot_gl.dat';
  if (Module.hlaotFiles) {
    FS.writeFile(dir + '/' + boot, Module.hlaotBootData);
    Object.keys(Module.hlaotFiles).forEach(function(name) {
      var file = Module.hlaotFiles[name];
      hlaotMountRange(dir, name, file, file.size);
    });
    return;
  }
  addRunDependency('hlaot-boot');
  fetch(base + boot).then(function(r) {
    if (!r.ok) throw new Error(boot + ' ' + r.status);
    return r.arrayBuffer();
  }).then(function(b) {
    FS.writeFile(dir + '/' + boot, new Uint8Array(b));
    removeRunDependency('hlaot-boot');
  }).catch(function(error) { abort(error.message); });
  (Module.hlaotPaks || ['res.pak']).forEach(function(pak) {
    var id = 'hlaot-' + pak;
    addRunDependency(id);
    fetch(base + pak, { method: 'HEAD' }).then(function(r) {
      if (!r.ok) throw new Error(pak + ' ' + r.status);
      hlaotMountRange(dir, pak, base + pak, Number(r.headers.get('Content-Length')));
      removeRunDependency(id);
    }).catch(function(error) { abort(error.message); });
  });
});
