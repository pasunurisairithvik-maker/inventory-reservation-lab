"""Local supervised-preview checks. Never prints session cookies."""
import concurrent.futures,json,urllib.request,urllib.error,http.cookiejar,time
from pathlib import Path
ORIGIN='http://127.0.0.1:4173'
def client():
 jar=http.cookiejar.CookieJar();return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)),jar
def call(opener,path,body=None,origin=ORIGIN):
 headers={}
 if body is not None:headers={'Content-Type':'application/json','Origin':origin}
 request=urllib.request.Request(ORIGIN+'/api/'+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
 try:
  with opener.open(request,timeout=30) as response:return response.status,json.load(response)
 except urllib.error.HTTPError as response:
  raw=response.read()
  try:data=json.loads(raw)
  except json.JSONDecodeError:data={'detail':'Non-JSON rejection'}
  return response.code,data
a,jar=client();assert call(a,'snapshot')[0]==200
cookies=list(jar);assert len(cookies)==1 and cookies[0].has_nonstandard_attr('HttpOnly')
assert call(a,'automation',{'enabled':False})[0]==200
b,_=client();assert call(b,'snapshot')[0]==200
cookie='; '.join(f'{c.name}={c.value}' for c in jar)
def order(i):
 body={'customer':'Integration '+str(i),'request_key':'integration-'+str(i),'ttl':300,'items':[{'sku':'HEAD-01','quantity':1}]}
 for _ in range(4):
  req=urllib.request.Request(ORIGIN+'/api/orders',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':ORIGIN,'Cookie':cookie})
  try:
   with urllib.request.urlopen(req,timeout=30) as response:return response.status,json.load(response)
  except urllib.error.HTTPError as response:
   data=json.load(response)
   if response.code==409 and 'busy' in data.get('detail',''):continue
   return response.code,data
 raise AssertionError('Concurrent request remained busy')
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(order,range(50)))
accepted=[r for status,r in results if status==200]
assert len(accepted)==8,(len(accepted),results)
assert sum(status==409 for status,_ in results)==42
_,snapshot=call(a,'snapshot')
head=next(p for p in snapshot['products'] if p['sku']=='HEAD-01')
assert head['available']==0 and snapshot['metrics']['inventory_balanced']
_,other=call(b,'snapshot');assert next(p for p in other['products'] if p['sku']=='HEAD-01')['available']==8
assert call(b,'orders/'+accepted[0]['id']+'/confirm',{})[0]==404
assert call(a,'automation',{'enabled':True},origin='https://untrusted.invalid')[0]==403
body={'customer':'Integration '+str(next(i for i,(status,_) in enumerate(results) if status==200)),'request_key':accepted[0]['request_key'],'ttl':300,'items':[{'sku':'HEAD-01','quantity':1}]}
assert call(a,'orders',body)[1]['id']==accepted[0]['id']
assert call(a,'orders',{'customer':'invalid','request_key':'invalid','items':[{'sku':'HEAD-01','quantity':True}]})[0]==422
assert call(a,'orders/'+accepted[0]['id']+'/cancel',{})[0]==200
assert call(a,'products/HEAD-01/restock',{'quantity':2})[0]==200
assert call(a,'snapshot')[1]['metrics']['inventory_balanced']
report={'preview_api':{'requests':50,'concurrent_http_clients':8,'initial_stock':8,'accepted':8,'stock_conflicts':42,'remaining':0},'checks':{'workspace_isolation':True,'cross_workspace_order_blocked':True,'same_origin_mutations_enforced':True,'http_only_session_cookie':True,'retry_idempotency':True,'bool_quantity_rejected':True,'cancel_and_restock_balanced':True},'scope':'Actual HTTP API against supervised-preview D1 database. Not a production load or latency benchmark.'}
Path('results').mkdir(exist_ok=True);Path('results/hosted-integration.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
