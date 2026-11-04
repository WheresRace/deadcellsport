const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const PORT = Number(process.env.PORT || 8642);
const ROOTS = [path.join(ROOT, 'runtime', 'web'), path.join(ROOT, 'build', 'web'), path.join(ROOT, 'run', 'game_libs')];
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

http.createServer((req, res) => {
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
