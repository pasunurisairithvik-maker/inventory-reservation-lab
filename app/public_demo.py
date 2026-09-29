"""Bounded anonymous Python demo. Each browser has its own SQLite workspace."""
import os
import re
import secrets
import sqlite3
import time
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from app.bootstrap import seed
from app.orders import Orders

COOKIE = 'orderops_workspace'

class SessionDispatch:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def prepare(self, token, mutation):
        path = self.directory / (token + '.db')
        with sqlite3.connect(self.directory/'_allocation.sqlite',timeout=10) as allocation:
            allocation.execute('BEGIN IMMEDIATE')
            if not path.exists():
                if len(list(self.directory.glob('*.db'))) >= 250:
                    return None, 503, 'Demo workspace capacity reached.'
                # Serialize allocation so concurrent first visits cannot bypass capacity.
                seed(Orders(path))
        with sqlite3.connect(path, timeout=10) as db:
            db.execute('CREATE TABLE IF NOT EXISTS demo_quota (id INTEGER PRIMARY KEY CHECK(id=1), window INTEGER, count INTEGER, total INTEGER)')
            db.execute('INSERT OR IGNORE INTO demo_quota VALUES(1,0,0,0)')
            if mutation:
                db.execute('BEGIN IMMEDIATE') if not db.in_transaction else None
                window, count, total = db.execute('SELECT window,count,total FROM demo_quota WHERE id=1').fetchone()
                minute = int(time.time() // 60)
                count = count if window == minute else 0
                if count >= 60 or total >= 1000:
                    return None, 429, 'Demo request limit reached. Start a fresh browser workspace for the lifetime limit.'
                db.execute('UPDATE demo_quota SET window=?,count=?,total=? WHERE id=1', (minute,count+1,total+1))
        from app.main import create_app
        return create_app(path, max_orders=100), None, None

    def resolve(self,token):
        if not re.fullmatch(r'[a-f0-9]{64}',token) or not (self.directory/(token+'.db')).exists():
            return secrets.token_hex(32)
        return token

    def prepare_session(self,token,mutation):
        token=self.resolve(token)
        return token,*self.prepare(token,mutation)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return
        headers = dict(scope['headers'])
        mutation = scope['method'] != 'GET'
        async def reject(code, message):
            await JSONResponse({'detail':message}, status_code=code)(scope,receive,send)
        if scope['method'] not in ('GET','POST'):
            return await reject(405,'Unsupported method')
        if scope['path'] != '/' and not scope['path'].startswith('/api/'):
            return await reject(404,'Not found')
        if mutation:
            origin = headers.get(b'origin',b'').decode('latin1')
            expected = scope['scheme'] + '://' + headers.get(b'host',b'').decode('latin1')
            if origin != expected:
                return await reject(403,'Use the form on this site to make changes')
            if b'application/json' not in headers.get(b'content-type',b'').lower():
                return await reject(415,'JSON request required')
        # Enforce actual bytes, not an untrusted Content-Length header.
        body = b''
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect': return
            body += message.get('body',b'')
            if len(body) > 12000: return await reject(413,'Request too large')
            if not message.get('more_body',False): break
        cookie = SimpleCookie()
        try: cookie.load(headers.get(b'cookie',b'').decode('latin1'))
        except CookieError: pass
        token = cookie[COOKIE].value if COOKIE in cookie else ''
        token,app,code,detail = await run_in_threadpool(self.prepare_session,token,mutation)
        if code: return await reject(code,detail)
        async def replay():
            return {'type':'http.request','body':body,'more_body':False}
        async def secure_send(message):
            if message['type'] == 'http.response.start':
                flags = '; Secure' if scope['scheme'] == 'https' else ''
                value = f'{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800{flags}'
                message['headers'] += [(b'set-cookie',value.encode()),(b'cache-control',b'no-store'),(b'x-content-type-options',b'nosniff'),(b'x-frame-options',b'DENY')]
            await send(message)
        await app(scope,replay,secure_send)

class PostgresDispatch(SessionDispatch):
    def __init__(self,url):
        from app.postgres import PostgresStore
        import psycopg
        try:self.store=PostgresStore(url)
        except psycopg.Error:raise RuntimeError('Database initialization failed; check secure configuration') from None
    def resolve(self,token):
        if re.fullmatch(r'[a-f0-9]{64}',token) and self.store.exists(token):return token
        return secrets.token_hex(32)
    def prepare(self,token,mutation):
        from app.postgres import CapacityError,QuotaError
        from app.ops_api import mount
        try:
            service=self.store.workspace(token)
            if mutation:self.store.consume_quota(token)
            app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
            import psycopg
            @app.exception_handler(psycopg.Error)
            async def database_unavailable(request,exc):
                return JSONResponse({'detail':'Database unavailable. Retry shortly.'},status_code=503)
            mount(app,max_orders=100,service=service)
            return app,None,None
        except CapacityError:return None,503,'Demo workspace capacity reached.'
        except QuotaError:return None,429,'Demo request limit reached.'
    def prepare_session(self,token,mutation):
        import psycopg
        try:return super().prepare_session(token,mutation)
        except psycopg.Error:return token,None,503,'Database unavailable. Retry shortly.'

def public_app():
    if os.environ.get('REQUIRE_DATABASE')=='1' and not os.environ.get('DATABASE_URL'):
        raise RuntimeError('DATABASE_URL is required for persistent free hosting')
    directory = Path(os.environ.get('DEMO_WORKSPACES','workspaces'))
    app = FastAPI(title='OrderOps',docs_url=None,redoc_url=None,openapi_url=None)
    @app.get('/healthz')
    def health():
        heartbeat = directory / 'worker-heartbeat'
        healthy = heartbeat.exists() and time.time()-heartbeat.stat().st_mtime < 120
        return JSONResponse({'status':'ok' if healthy else 'worker_unavailable'},status_code=200 if healthy else 503)
    dispatch=PostgresDispatch(os.environ['DATABASE_URL']) if os.environ.get('DATABASE_URL') else SessionDispatch(directory)
    app.mount('/',dispatch)
    return app
