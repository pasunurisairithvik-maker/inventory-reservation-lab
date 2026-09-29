import {env} from 'cloudflare:workers';
import {operation,seed,DomainError} from './domain.mjs';
function db(){if(!env.DB)throw new Error('Storage unavailable');return env.DB;}
export async function initialize(id:string){const state=seed(Date.now()/1000);await db().prepare('INSERT INTO demo_workspaces(id,state,version,updated) VALUES (?,?,0,?)').bind(id,JSON.stringify(state),Date.now()).run();}
export async function transact(id:string,path:string,body:Record<string,unknown>){
 for(let attempt=0;attempt<10;attempt++){
  const row=await db().prepare('SELECT state,version FROM demo_workspaces WHERE id=?').bind(id).first<{state:string;version:number}>();
  if(!row)throw new DomainError('This demo workspace is unavailable. Start a fresh demo.',404);
  const {state,result}=operation(JSON.parse(row.state),path,body,Date.now()/1000);
  const updated=await db().prepare('UPDATE demo_workspaces SET state=?,version=version+1,updated=? WHERE id=? AND version=?').bind(JSON.stringify(state),Date.now(),id,row.version).run();
  if(updated.meta.changes===1)return result;
 }
 throw new DomainError('The store is busy. Retry with the same request key.',409);
}
export async function exists(id:string){return !!await db().prepare('SELECT id FROM demo_workspaces WHERE id=?').bind(id).first();}
