import asyncio,base64,hashlib,json,tempfile,sys
from pathlib import Path
from mcp import Client
from roborag.rag_mcp import EpisodeMemory,create_server
from roborag.rag_tasks import TASKS,prompt_for
ROOT=Path.cwd()
def sha(v):return hashlib.sha256(v).hexdigest()
async def main():
 result={'prompts':{},'tools':{},'references':{},'retrieval':{}}
 for task in sorted(TASKS):
  result['prompts'][task]=sha(prompt_for(ROOT,task,'delta').encode())
  with tempfile.TemporaryDirectory() as tmp:
   m=EpisodeMemory(tmp,tmp,tmp,tmp,task,controller='delta')
   async with Client(create_server(m)) as c:
    result['tools'][task]={t.name:t.model_dump(mode='json',exclude_none=True) for t in (await c.list_tools()).tools}
 bank=Path(sys.argv[1]).resolve(); data=Path(sys.argv[2]).resolve()
 with tempfile.TemporaryDirectory() as tmp:
  m=EpisodeMemory(bank,data,tmp,tmp,'push_T',controller='delta')
  async with Client(create_server(m)) as c:
   for g in m.bank.retriever().index['graphs']:
    query={'goal':g['instruction'],'observation':g['initial_cue'],'mode':'plan'}
    response=await c.call_tool('retrieve_evidence',query)
    assert not response.is_error
    result['retrieval'][g['id']]=json.loads(response.content[0].text)
   for p in m.bank.retriever().index['phases']:
    m.references.add(p['id'])
    for section in ('start','close','open','end'):
     response=await c.call_tool('read_action_reference',{'source':p['id'],'section':section,'images':True})
     assert not response.is_error
     content=[]
     for block in response.content:
      if block.type=='image':content.append({'type':'image','sha256':sha(base64.b64decode(block.data))})
      else:content.append({'type':'text','text':block.text})
     result['references'][p['id']+'/'+section]=content
 Path(sys.argv[3]).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'tasks':len(result['tools']),'reference_expansions':len(result['references']),'output':sys.argv[3]}))
asyncio.run(main())
