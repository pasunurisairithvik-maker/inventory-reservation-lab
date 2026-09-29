from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.orders import Orders
from app.store import Conflict
from app.experiments import contention, crash_recovery

class Line(BaseModel):
    sku: str = Field(min_length=1,max_length=64)
    quantity: int = Field(strict=True,ge=1,le=1000)
class OrderBody(BaseModel):
    customer: str = Field(min_length=1,max_length=60)
    items: list[Line] = Field(min_length=1,max_length=20)
    request_key: str = Field(min_length=1,max_length=128)
    ttl: int = Field(strict=True,ge=5,le=3600,default=300)
class StockBody(BaseModel):
    quantity: int = Field(strict=True,ge=1,le=1000000)
class WorkBody(BaseModel):
    simulate_failure: bool = False

def mount(api,path):
    service=Orders(path)
    router=APIRouter(prefix='/api')
    def invoke(fn,*args,**kwargs):
        try: return fn(*args,**kwargs)
        except Conflict as exc: raise HTTPException(409,str(exc)) from exc
        except KeyError as exc: raise HTTPException(404,'Record not found') from exc
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    @api.get('/',include_in_schema=False)
    def dashboard(): return FileResponse(Path(__file__).parent/'static'/'index.html')
    @router.get('/snapshot')
    def snapshot(): return service.snapshot()
    @router.post('/orders')
    def create(body:OrderBody): return invoke(service.create_order,**body.model_dump())
    @router.post('/orders/{oid}/{action}')
    def transition(oid:str,action:str): return invoke(service.transition,oid,action)
    @router.post('/products/{sku}/restock')
    def restock(sku:str,body:StockBody):
        invoke(service.restock,sku,body.quantity);return {'restocked':True}
    @router.post('/events/process')
    def process(body:WorkBody): return service.process_one(fail=body.simulate_failure)
    @router.post('/events/{eid}/replay')
    def replay(eid:str):
        invoke(service.replay,eid);return {'replayed':True}
    @router.post('/cleanup')
    def cleanup(): return {'expired':service.cleanup()}
    @router.post('/experiments/{kind}')
    def experiment(kind:str):
        if kind=='contention': return contention()
        if kind=='crash': return crash_recovery()
        raise HTTPException(404,'Unknown experiment')
    api.include_router(router)
