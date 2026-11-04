var HLAOT_CHUNK = 1 << 20;
var HLAOT_MAX_CHUNKS = 256;

function hlaotRangeFile(url, size) {
  var cache = new Map();

  function fetchRange(from, to) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, false);
    xhr.setRequestHeader('Range', 'bytes=' + from + '-' + (to - 1));
    xhr.overrideMimeType('text/plain; charset=x-user-defined');
    xhr.send(null);
    if (xhr.status !== 206 && xhr.status !== 200) throw new Error('range read failed ' + url + ' ' + xhr.status);
    var s = xhr.responseText;
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
          cache.set(k, data.subarray(off, Math.min(off + HLAOT_CHUNK, data.length)));
        }
        start = -1;
      }
    }
    while (cache.size > HLAOT_MAX_CHUNKS) cache.delete(cache.keys().next().value);
  }

  return function read(buffer, offset, length, position) {
    if (position >= size) return 0;
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
  ENV.HLAOT_NOGC = '1';
  FS.mkdir(dir);
  FS.chdir(dir);
  var base = Module.hlaotBase || '';
  var boot = Module.hlaotBoot || 'hlboot_gl.dat';
  addRunDependency('hlaot-boot');
  fetch(base + boot).then(function(r) {
    if (!r.ok) throw new Error(boot + ' ' + r.status);
    return r.arrayBuffer();
  }).then(function(b) {
    FS.writeFile(dir + '/' + boot, new Uint8Array(b));
    removeRunDependency('hlaot-boot');
  });
  (Module.hlaotPaks || ['res.pak']).forEach(function(pak) {
    var id = 'hlaot-' + pak;
    addRunDependency(id);
    fetch(base + pak, { method: 'HEAD' }).then(function(r) {
      if (!r.ok) throw new Error(pak + ' ' + r.status);
      hlaotMountRange(dir, pak, base + pak, Number(r.headers.get('Content-Length')));
      removeRunDependency(id);
    });
  });
});
