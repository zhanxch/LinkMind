import { request } from 'node:http';

export const inject = ['webServer', 'connection'];

export function apply(ctx, connection = {url: process.env.LINKMIND_STUDIO_URL, token: process.env.LINKMIND_STUDIO_TOKEN}) {
  const backend = new URL(connection.url);
  if (ctx.webServer.host !== '127.0.0.1') throw new Error('LinkMind Studio currently requires a loopback dsh listener');
  ctx.effect(() => ctx.webServer.register({
    kind: 'prefix', path: '/linkmind',
    handler: async (req, res) => {
      const origin = ctx.webServer.getOrigin();
      if (req.headers.host !== new URL(origin).host ||
          (req.headers.origin && req.headers.origin !== origin) ||
          req.headers['sec-fetch-site'] === 'cross-site' ||
          (req.method === 'POST' && req.headers.origin !== origin && req.headers['x-linkmind-request'] !== '1')) {
        res.writeHead(403).end('Forbidden'); return;
      }
      if (!ctx.connection.authorizeIndex(req, res)) return;
      const path = req.url.slice('/linkmind'.length) || '/';
      const upstream = request({hostname: backend.hostname, port: backend.port, path,
        method: req.method, headers: {'Authorization': `Bearer ${connection.token}`,
          'Content-Type': 'application/json', ...(req.headers['content-length'] ? {'Content-Length': req.headers['content-length']} : {})}}, reply => {
        res.writeHead(reply.statusCode, {...reply.headers, 'X-Frame-Options': 'SAMEORIGIN',
          'Content-Security-Policy': "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'self'; base-uri 'none'"});
        reply.pipe(res);
      });
      upstream.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end('Studio service unavailable'); });
      req.on('aborted', () => upstream.destroy());
      res.on('close', () => upstream.destroy());
      req.pipe(upstream);
    },
  }), 'LinkMind Studio route');
}
