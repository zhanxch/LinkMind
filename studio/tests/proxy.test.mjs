import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {apply} from '../plugin/index.mjs';

test('Studio proxy requires dsh authentication and same-origin writes', async () => {
  const backend=http.createServer((req,res)=>{
    assert.equal(req.headers.authorization,'Bearer local-test-token');
    if(req.method==='POST')assert.equal(req.headers['content-length'],'2');
    res.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify({path:req.url}));
  });
  await new Promise(resolve=>backend.listen(0,'127.0.0.1',resolve));
  process.env.LINKMIND_STUDIO_URL=`http://127.0.0.1:${backend.address().port}`;
  process.env.LINKMIND_STUDIO_TOKEN='local-test-token';
  let route;
  const frontend=http.createServer((req,res)=>route.handler(req,res));
  await new Promise(resolve=>frontend.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${frontend.address().port}`;
  apply({effect:fn=>fn(),webServer:{host:'127.0.0.1',getOrigin:()=>origin,tapIndex:()=>()=>{},register:r=>{route=r;return ()=>{};}},
    connection:{authorizeIndex(req,res){if(req.headers.cookie==='dsh=test')return true;res.writeHead(401).end();return false;}}});
  try {
    assert.equal((await fetch(origin+'/linkmind/api/state')).status,401);
    assert.equal((await fetch(origin+'/linkmind/api/tasks',{method:'POST',headers:{cookie:'dsh=test',origin:'https://other.example'},body:'{}'})).status,403);
    assert.equal((await fetch(origin+'/linkmind/api/tasks',{method:'POST',headers:{cookie:'dsh=test'},body:'{}'})).status,403);
    const accepted=await fetch(origin+'/linkmind/api/tasks',{method:'POST',headers:{cookie:'dsh=test',origin},body:'{}'});
    assert.equal(accepted.status,200);
    assert.deepEqual(await accepted.json(),{path:'/api/tasks'});
    assert.equal(accepted.headers.get('x-frame-options'),'SAMEORIGIN');
    // Desktop's authenticated protocol strips Origin but preserves this header.
    const native={method:'POST',headers:{cookie:'dsh=test','X-LinkMind-Request':'1'},body:'{}'};
    assert.equal((await fetch(origin+'/linkmind/api/tasks',native)).status,200);
    const chunked=new ReadableStream({start(controller){controller.enqueue(new TextEncoder().encode('{'));controller.enqueue(new TextEncoder().encode('}'));controller.close();}});
    assert.equal((await fetch(origin+'/linkmind/api/tasks',{...native,body:chunked,duplex:'half'})).status,200);
    assert.equal((await fetch(origin+'/linkmind/api/tasks',{...native,body:'x'.repeat(1024*1024+1)})).status,413);
    assert.equal((await fetch(origin+'/linkmind/api/tasks',{...native,headers:{'X-LinkMind-Request':'1'}})).status,401);
    assert.equal((await fetch(origin+'/linkmind/api/tasks',{...native,headers:{...native.headers,origin:'https://other.example'}})).status,403);
  } finally {
    frontend.closeAllConnections(); backend.closeAllConnections();
    await Promise.all([new Promise(r=>frontend.close(r)),new Promise(r=>backend.close(r))]);
    delete process.env.LINKMIND_STUDIO_URL;delete process.env.LINKMIND_STUDIO_TOKEN;
  }
});
