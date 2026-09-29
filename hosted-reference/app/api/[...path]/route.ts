import {initialize,transact,exists} from '../../../lib/persistence';
import {experiment,DomainError} from '../../../lib/domain.mjs';
const cookieName='orderops_demo';
const uuid=/^[a-f0-9]{32}$/;
function session(request:Request){const value=(request.headers.get('cookie')||'').split(';').map(x=>x.trim()).find(x=>x.startsWith(cookieName+'='))?.slice(cookieName.length+1);return value&&uuid.test(value)?value:null;}
function reply(result:unknown,status=200,cookie?:string){const headers:Record<string,string>={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin'};if(cookie)headers['Set-Cookie']=cookie;return Response.json(result,{status,headers});}
async function handle(request:Request){let cookie:string|undefined;
 try{
  const url=new URL(request.url),path=url.pathname.replace(/^\/api\//,''),write=request.method==='POST';
  if(write&&request.headers.get('origin')!==url.origin)return reply({detail:'Same-origin requests only.'},403);
  if(request.method!=='GET'&&!write)return reply({detail:'Method not allowed.'},405);
  if(!write&&path!=='snapshot')return reply({detail:'Route not found.'},404);
  let id=session(request),body:Record<string,unknown>={};
  if(write){if(!request.headers.get('content-type')?.includes('application/json'))return reply({detail:'JSON request required.'},415);const raw=await request.text();if(raw.length>12000)return reply({detail:'Request is too large.'},413);try{body=JSON.parse(raw);}catch{return reply({detail:'Invalid JSON.'},400);}if(!body||Array.isArray(body)||typeof body!=='object')return reply({detail:'JSON object required.'},422);}
  if(!id||!(await exists(id))||path==='new-demo'){
   if(write&&path!=='new-demo')return reply({detail:'Refresh the page before submitting an order.'},401);
   id=crypto.randomUUID().replaceAll('-','');await initialize(id);
   cookie=`${cookieName}=${id}; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800${url.protocol==='https:'?'; Secure':''}`;
  }
  if(path==='new-demo')return reply({started:true},200,cookie);
  if(path.startsWith('experiments/'))return reply(experiment(path.split('/')[1]),200,cookie);
  const result=await transact(id,path,body);return reply(result,200,cookie);
 }catch(error){if(error instanceof DomainError)return reply({detail:error.message},error.status,cookie);console.error('OrderOps request failed',error instanceof Error?error.name:'Error');return reply({detail:'The store is temporarily unavailable. Your form is preserved; please retry.'},503,cookie);}
}
export const GET=handle;export const POST=handle;
