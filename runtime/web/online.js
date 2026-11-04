'use strict';
var Module;
(function() {
  var status = document.getElementById('status');
  var canvas = document.getElementById('canvas');
  var gameStatus = document.getElementById('game-status');
  var logEl = document.getElementById('log');
  var button = document.getElementById('start');
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
  button.addEventListener('click', async function() {
    if (busy) return;
    busy = true;
    button.disabled = true;
    status.className = '';
    status.textContent = 'Connecting to the game…';
    try {
      if (!window.WebAssembly || !canvas.getContext('webgl2')) throw new Error('This browser needs WebAssembly and WebGL 2 enabled.');
      var response = await fetch('runtime.json');
      if (!response.ok) throw new Error('The game could not be reached. Reload to try again.');
      var config = await response.json();
      var wasmBinary;
      if (config.wasmUrl) {
        status.textContent = 'Downloading game runtime…';
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
        setStatus: function(message) { gameStatus.textContent = message; },
        onAbort: function(reason) { fail(new Error('Game stopped: ' + reason + '. Reload to try again.')); },
        onRuntimeInitialized: function() {
          gameStatus.textContent = 'Loading game and compiling shaders…';
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
      button.disabled = false;
      fail(error);
    }
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
