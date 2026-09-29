import os
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from app.store import Store, Conflict

class Reservation(BaseModel):
    sku: str = Field(min_length=1,max_length=64)
    quantity: int = Field(strict=True,gt=0)
    request_key: str = Field(min_length=1,max_length=128)
    ttl: int = Field(strict=True,ge=1,le=3600,default=60)

def create_app(path=None, max_orders=None):
    if path is None and os.environ.get("PUBLIC_DEMO") == "1":
        from app.public_demo import public_app
        return public_app()
    store = Store(path or os.environ.get('INVENTORY_DB','inventory.db'))
    api = FastAPI(title='OrderOps — Order Reliability Lab')
    from app.ops_api import mount
    mount(api,store.path,max_orders=max_orders)
    @api.get('/inventory')
    def inventory():
        return store.snapshot(time.time())
    @api.post('/reservations')
    def reserve(body: Reservation):
        try:
            return store.reserve(**body.model_dump(),now=time.time())
        except Conflict as exc:
            raise HTTPException(409,str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
    @api.post('/reservations/{rid}/{action}')
    def transition(rid: str,action: str):
        try:
            return store.transition(rid,action,time.time())
        except KeyError as exc:
            raise HTTPException(404,'Unknown reservation') from exc
        except Conflict as exc:
            raise HTTPException(409,str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
    return api
