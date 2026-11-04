'use strict';
var Module;
(function() {
  var errorEl = document.getElementById('error');
  var canvas = document.getElementById('canvas');
  var logEl = document.getElementById('log');
  if (new URLSearchParams(location.search).has('log')) logEl.hidden = false;

  function log(message) {
    console.log(message);
    if (!logEl.hidden) {
      logEl.textContent = (logEl.textContent + message + '\n').slice(-60000);
      logEl.scrollTop = logEl.scrollHeight;
    }
  }
  function fail(error) {
    document.body.classList.remove('playing');
    errorEl.textContent = error.message || String(error);
    errorEl.hidden = false;
    log(errorEl.textContent);
  }
  async function start() {
    try {
      if (!window.WebAssembly || !canvas.getContext('webgl2')) throw new Error('This browser needs WebAssembly and WebGL 2 enabled.');
      var response = await fetch('runtime.json');
      if (!response.ok) throw new Error('The game could not be reached. Reload to try again.');
      var config = await response.json();
      var wasmBinary;
      if (config.wasmUrl) {
        var wasmResponse = await fetch(config.wasmUrl);
        if (!wasmResponse.ok) throw new Error('Runtime download failed. Reload to try again.');
        wasmBinary = await wasmResponse.arrayBuffer();
      }
      Module = {
        canvas: canvas,
        instantiateWasm: wasmBinary ? function(imports, success) {
          WebAssembly.instantiate(wasmBinary, imports).then(function(result) {
            success(result.instance);
          }).catch(fail);
          return {};
        } : undefined,
        hlaotBootUrl: config.bootUrl,
        hlaotPakManifest: { 'res.pak': config.pak },
        print: log,
        printErr: log,
        setStatus: function() {},
        onAbort: function(reason) { fail(new Error('Game stopped: ' + reason + '. Reload to try again.')); },
      };
      document.body.classList.add('playing');
      var script = document.createElement('script');
      script.src = 'deadcells.js';
      script.onerror = function() { fail(new Error('Runtime download failed. Reload to try again.')); };
      document.body.appendChild(script);
      canvas.focus();
    } catch (error) {
      fail(error);
    }
  }
  async function fullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen({ navigationUI: 'hide' });
    } catch (error) { log(error.message); }
  }
  // Attack clicks must never toggle fullscreen or release mouse capture.
  var pointerLockPending = false;
  canvas.addEventListener('pointerdown', function() { canvas.focus({ preventScroll: true }); });
  canvas.addEventListener('click', function(event) {
    if (event.button !== 0 || typeof runtimeInitialized === 'undefined' || !runtimeInitialized) return;
    canvas.focus({ preventScroll: true });
    if (!canvas.requestPointerLock || pointerLockPending || document.pointerLockElement === canvas) return;
    pointerLockPending = true;
    try {
      var request = canvas.requestPointerLock();
      if (request && typeof request.catch === 'function') request.catch(function(error) {
        pointerLockPending = false;
        log('[mouse] ' + error.message);
      });
    } catch (error) {
      pointerLockPending = false;
      log('[mouse] ' + error.message);
    }
  });
  document.addEventListener('pointerlockchange', function() {
    pointerLockPending = false;
    if (document.pointerLockElement === canvas) canvas.focus({ preventScroll: true });
  });
  document.addEventListener('pointerlockerror', function() { pointerLockPending = false; });
  addEventListener('keydown', function(event) {
    if (event.key === 'Escape' && document.pointerLockElement === canvas) {
      document.exitPointerLock();
      return;
    }
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
  start();
})();
