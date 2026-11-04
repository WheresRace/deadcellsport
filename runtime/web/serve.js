const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const PORT = Number(process.env.PORT || 8642);
const ROOTS = [path.join(ROOT, 'runtime', 'web'), path.join(ROOT, 'build', 'web'), path.resolve(ROOT, process.env.GAME_DIR || path.join('run', 'gog'))];
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.wasm': 'application/wasm' };

function resolve(url) {
  const name = decodeURIComponent(url.split('?')[0]).replace(/^\/+/, '') || 'index.html';
  if (name.includes('..')) return null;
  for (const r of ROOTS) {
    const p = path.join(r, name);
    if (fs.existsSync(p) && fs.statSync(p).isFile()) return p;
  }
  return null;
}

const CLIENT_LOG = path.join(ROOT, 'build', 'web_client.log');

// PASSWORD=... locks the server behind HTTP basic auth (any user name), for reaching it through a tunnel.
const PASSWORD = process.env.PASSWORD || '';

http.createServer((req, res) => {
  if (PASSWORD) {
    const m = /^Basic (.+)$/.exec(req.headers.authorization || '');
    const pass = m ? Buffer.from(m[1], 'base64').toString().replace(/^[^:]*:/, '') : '';
    if (pass !== PASSWORD) {
      res.writeHead(401, { 'WWW-Authenticate': 'Basic realm="deadcells", charset="UTF-8"' });
      res.end('password required');
      return;
    }
  }
  if (req.method === 'POST' && req.url.startsWith('/log')) {
    // Pages post to /log?<tab id>; tag each line so several open tabs can share the log.
    const tag = req.url.slice(5).replace(/[^a-z0-9]/g, '');
    let body = '';
    req.on('data', d => { body += d; });
    req.on('end', () => {
      fs.appendFileSync(CLIENT_LOG, tag ? body.split('\n').map(l => `[${tag}] ${l}`).join('\n') + '\n' : body + '\n');
      res.end();
    });
    return;
  }
  const file = resolve(req.url);
  if (!file) {
    res.writeHead(404);
    res.end();
    return;
  }
  const size = fs.statSync(file).size;
  const headers = {
    'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream',
    'Accept-Ranges': 'bytes',
    'Cache-Control': 'no-cache',
    'Document-Policy': 'js-profiling',
  };
  const m = /^bytes=(\d+)-(\d*)$/.exec(req.headers.range || '');
  if (m) {
    const start = Number(m[1]);
    const end = Math.min(m[2] ? Number(m[2]) : size - 1, size - 1);
    res.writeHead(206, { ...headers, 'Content-Range': `bytes ${start}-${end}/${size}`, 'Content-Length': end - start + 1 });
    if (req.method === 'HEAD') return res.end();
    fs.createReadStream(file, { start, end }).pipe(res);
    return;
  }
  res.writeHead(200, { ...headers, 'Content-Length': size });
  if (req.method === 'HEAD') return res.end();
  fs.createReadStream(file).pipe(res);
}).listen(PORT, '127.0.0.1', () => console.log(`serving on http://127.0.0.1:${PORT}/`));
