import nodePath from 'node:path';
import {readCodexStats} from './codex-stats.mjs';
import { request } from 'node:http';
import { readFile } from 'node:fs/promises';

export const inject = ['webServer', 'connection'];

export function apply(ctx, connection = {url: process.env.LINKMIND_STUDIO_URL, token: process.env.LINKMIND_STUDIO_TOKEN}) {
  const backend = new URL(connection.url);
  if (ctx.webServer.host !== '127.0.0.1') throw new Error('visual RSI studio currently requires a loopback dsh listener');
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
      if (req.method === 'GET' && req.url.split('?')[0] === '/linkmind/api/codex-stats') {
        const sessionId=new URL(req.url,origin).searchParams.get('session_id');
        if(!sessionId||sessionId.length>200){res.writeHead(400,{'Content-Type':'application/json'}).end(JSON.stringify({error:'Invalid session identity'}));return;}
        try{
          const stats=connection.state?await readCodexStats(nodePath.join(connection.state,'codex-conversations'),sessionId):null;
          res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'}).end(JSON.stringify(stats));
        }catch{res.writeHead(503,{'Content-Type':'application/json'}).end(JSON.stringify({error:'统计暂时不可用'}));}
        return;
      }
      if (req.method === 'GET' && ['workbench.mjs','studio-shell.mjs','studio-dock.mjs','studio-overview.mjs'].some(name => req.url.split('?')[0] === '/linkmind/'+name)) {
        const source = await readFile(new URL('./'+req.url.split('?')[0].slice('/linkmind/'.length), import.meta.url));
        res.writeHead(200, {'Content-Type':'text/javascript; charset=utf-8','Cache-Control':'no-cache','X-Content-Type-Options':'nosniff'});
        res.end(source); return;
      }
      // Electron forwards Fetch bodies as streams, which may arrive chunked.
      // The local JSON service needs a bounded body with an explicit length.
      let body;
      if (req.method === 'POST') {
        const chunks = [];
        let size = 0;
        try {
          for await (const chunk of req) {
            size += chunk.length;
            if (size > 1024 * 1024) { res.writeHead(413).end('Request body too large'); return; }
            chunks.push(chunk);
          }
        } catch {
          if (!res.destroyed) res.writeHead(400).end('Incomplete request body');
          return;
        }
        body = Buffer.concat(chunks);
      }
      const path = req.url.slice('/linkmind'.length) || '/';
      const upstream = request({hostname: backend.hostname, port: backend.port, path,
        method: req.method, headers: {'Authorization': `Bearer ${connection.token}`,
          'Content-Type': 'application/json', ...(body ? {'Content-Length': body.length} : {})}}, reply => {
        res.writeHead(reply.statusCode, {...reply.headers, 'X-Frame-Options': 'SAMEORIGIN',
          'Content-Security-Policy': "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'self'; base-uri 'none'"});
        reply.pipe(res);
      });
      upstream.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end('Studio service unavailable'); });
      req.on('aborted', () => upstream.destroy());
      res.on('close', () => upstream.destroy());
      if (body) upstream.end(body);
      else req.pipe(upstream);
    },
  }), 'visual RSI studio route');
}
