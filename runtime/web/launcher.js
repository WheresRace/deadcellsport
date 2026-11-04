'use strict';
var Module;
(function() {
  var status = document.getElementById('status');
  var canvas = document.getElementById('canvas');
  var gameStatus = document.getElementById('game-status');
  var logEl = document.getElementById('log');
  var busy = false;
  if (new URLSearchParams(location.search).has('log')) logEl.style.display = 'block';

  function log(message) {
    console.log(message);
    if (logEl.style.display === 'block') {
      logEl.textContent = (logEl.textContent + message + '\n').slice(-60000);
      logEl.scrollTop = logEl.scrollHeight;
    }
  }
  function fail(error) {
    document.body.classList.remove('playing');
    gameStatus.textContent = '';
    status.className = 'error';
    status.textContent = error.message || String(error);
    log(status.textContent);
  }

  // Read the PE resource tree; only the small bytecode resource enters memory.
  function extractBoot(buffer) {
    var bytes = new Uint8Array(buffer);
    if (bytes[0] === 72 && bytes[1] === 76 && bytes[2] === 66) return bytes;
    var view = new DataView(buffer);
    if (view.getUint16(0, true) !== 0x5a4d) throw new Error('Select deadcells_gl.exe or hlboot_gl.dat.');
    var pe = view.getUint32(0x3c, true);
    if (view.getUint32(pe, true) !== 0x4550) throw new Error('Invalid game executable.');
    var sections = view.getUint16(pe + 6, true);
    var sectionTable = pe + 24 + view.getUint16(pe + 20, true);
    var raw, va;
    for (var i = 0; i < sections; i++) {
      var section = sectionTable + 40 * i;
      var name = new TextDecoder().decode(bytes.subarray(section, section + 8)).replace(/\0/g, '');
      if (name === '.rsrc') {
        va = view.getUint32(section + 12, true);
        raw = view.getUint32(section + 20, true);
        break;
      }
    }
    if (raw === undefined) throw new Error('No game bytecode in this executable.');
    function walk(offset, depth) {
      if (depth > 4) throw new Error('Invalid executable resources.');
      var count = view.getUint16(raw + offset + 12, true) + view.getUint16(raw + offset + 14, true);
      for (var n = 0; n < count; n++) {
        var entry = view.getUint32(raw + offset + 20 + n * 8, true);
        if (entry & 0x80000000) {
          var found = walk(entry & 0x7fffffff, depth + 1);
          if (found) return found;
        } else {
          var start = view.getUint32(raw + entry, true) - va + raw;
          var length = view.getUint32(raw + entry + 4, true);
          if (bytes[start] === 72 && bytes[start + 1] === 76 && bytes[start + 2] === 66) {
            if (start < 0 || start + length > bytes.length) throw new Error('Incomplete game executable.');
            return bytes.slice(start, start + length);
          }
        }
      }
    }
    var boot = walk(0, 0);
    if (!boot) throw new Error('No HashLink bytecode found. Select the OpenGL executable.');
    return boot;
  }

  async function start(pak, bootFile) {
    if (busy) return;
    if (!pak || !bootFile) { fail(new Error('Select res.pak and deadcells_gl.exe (or hlboot_gl.dat).')); return; }
    busy = true;
    document.querySelectorAll('button').forEach(function(button) { button.disabled = true; });
    status.className = '';
    status.textContent = 'Checking your game files locally…';
    try {
      if (!window.WebAssembly || !canvas.getContext('webgl2')) throw new Error('This browser needs WebAssembly and WebGL 2 enabled.');
      var response = await fetch('runtime.json');
      if (!response.ok) throw new Error('Runtime manifest could not be loaded. Reload the page.');
      var config = await response.json();
      if (bootFile.size > 64 * 1024 * 1024) throw new Error('The selected executable is too large. Select deadcells_gl.exe.');
      var boot = extractBoot(await bootFile.arrayBuffer());
      var digest = new Uint8Array(await crypto.subtle.digest('SHA-256', boot));
      var hash = Array.from(digest, function(b) { return b.toString(16).padStart(2, '0'); }).join('');
      if (hash !== config.bootSha256) throw new Error('This game version does not match the runtime. Select GOG 1.26.0 OpenGL game files.');
      var magic = new Uint8Array(await pak.slice(0, 3).arrayBuffer());
      if (pak.size !== config.pakSize || String.fromCharCode.apply(null, magic) !== 'PAK') throw new Error('The archive does not match the supported GOG 1.26.0 base game.');
      Module = {
        canvas: canvas,
        hlaotFiles: { 'res.pak': pak },
        hlaotBootData: boot,
        print: log,
        printErr: log,
        setStatus: function(message) { gameStatus.textContent = message; },
        onAbort: function(reason) { fail(new Error('Game stopped: ' + reason + '. Reload to try again.')); },
        onRuntimeInitialized: function() {
          gameStatus.textContent = 'Starting game and compiling shaders…';
          requestAnimationFrame(function() { gameStatus.textContent = ''; });
        }
      };
      document.body.classList.add('playing');
      gameStatus.textContent = 'Loading game runtime…';
      var script = document.createElement('script');
      script.src = 'deadcells.js';
      script.onerror = function() { fail(new Error('Runtime download failed. Reload to try again.')); };
      document.body.appendChild(script);
      canvas.focus();
    } catch (error) {
      busy = false;
      document.querySelectorAll('button').forEach(function(button) { button.disabled = false; });
      fail(error);
    }
  }

  document.getElementById('choose').addEventListener('click', function() { document.getElementById('folder').click(); });
  document.getElementById('folder').addEventListener('change', function(event) {
    var files = Array.from(event.target.files);
    var find = function(name) { return files.find(function(file) { return file.name.toLowerCase() === name; }); };
    start(find('res.pak'), find('hlboot_gl.dat') || find('deadcells_gl.exe'));
  });
  document.getElementById('start').addEventListener('click', function() {
    start(document.getElementById('pak').files[0], document.getElementById('boot').files[0]);
  });
  async function fullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen({ navigationUI: 'hide' });
    } catch (error) { log(error.message); }
  }
  canvas.addEventListener('dblclick', fullscreen);
  addEventListener('keydown', function(event) {
    if (event.key === 'F11' && document.body.classList.contains('playing')) {
      event.preventDefault(); event.stopImmediatePropagation(); fullscreen();
    }
  }, true);
  document.addEventListener('fullscreenchange', async function() {
    if (!navigator.keyboard || !navigator.keyboard.lock) return;
    try {
      if (document.fullscreenElement) await navigator.keyboard.lock(['Escape']);
      else navigator.keyboard.unlock();
    } catch (error) { log(error.message); }
  });
  ['keydown', 'pointerdown', 'touchstart'].forEach(function(type) {
    addEventListener(type, function(event) {
      if (!event.isTrusted || typeof AL === 'undefined' || !AL.contexts) return;
      Object.values(AL.contexts).forEach(function(context) {
        if (context && context.audioCtx && context.audioCtx.state !== 'running') context.audioCtx.resume().catch(log);
      });
    }, true);
  });
})();
