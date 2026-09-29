"""Relational PostgreSQL backend; per-workspace schemas and serialized mutations.

The small demo deliberately uses a schema per visitor, capped at 50 visitors.
SQLite remains the independent local backend. No database URLs are logged.
"""
import hashlib
import os
import time
from contextlib import contextmanager
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from app.orders import Orders
from app.bootstrap import seed

REGISTRY = 'public.orderops_workspaces'
DDL = Orders.SCHEMA.replace('PRAGMA journal_mode=WAL;','').replace('INTEGER PRIMARY KEY AUTOINCREMENT','BIGSERIAL PRIMARY KEY').replace('INTEGER','BIGINT').replace('REAL','DOUBLE PRECISION').replace('CREATE TABLE IF NOT EXISTS ops_outbox(', 'CREATE TABLE IF NOT EXISTS ops_outbox(seq BIGSERIAL UNIQUE,')

class CapacityError(Exception):pass
class QuotaError(Exception):pass

class Row(dict):
    def __getitem__(self,key):
        if isinstance(key,int):return tuple(self.values())[key]
        return super().__getitem__(key)

class Cursor:
    def __init__(self,cursor):self.cursor=cursor
    @property
    def rowcount(self):return self.cursor.rowcount
    def convert(self,row):
        return None if row is None else Row(zip([c.name for c in self.cursor.description],row))
    def fetchone(self):return self.convert(self.cursor.fetchone())
    def fetchall(self):return [self.convert(row) for row in self.cursor.fetchall()]
    def __iter__(self):
        for row in self.cursor:yield self.convert(row)

class Connection:
    def __init__(self,raw):self.raw=raw
    def execute(self,query,args=()):
        query=query.replace('?', '%s').replace('ORDER BY rowid','ORDER BY seq')
        if 'INSERT OR IGNORE' in query:
            query=query.replace('INSERT OR IGNORE','INSERT')+' ON CONFLICT DO NOTHING'
        return Cursor(self.raw.execute(query,args))
    def executemany(self,query,args):
        cursor=self.raw.cursor();cursor.executemany(query.replace('?','%s'),args);return Cursor(cursor)
    def close(self):self.raw.close()

class PostgresOrders(Orders):
    backend="postgres"
    def __init__(self,store,workspace_id,schema,clock=time.time,max_orders=100):
        self.store=store;self.workspace_id=workspace_id;self.schema=schema
        self.clock=clock;self.max_orders=max_orders;self.path=schema
    def connection(self):
        raw=self.store.connect()
        raw.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))
        return Connection(raw)
    @contextmanager
    def transaction(self):
        connection=self.connection();raw=connection.raw
        try:
            with raw.transaction():
                # Serialize all operations in one workspace, including expiry and claims.
                raw.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(self.workspace_id,))
                yield connection
                due=raw.execute("SELECT MIN(at) FROM (SELECT expires AS at FROM ops_orders WHERE state='held' UNION ALL SELECT CASE WHEN state='processing' THEN lease ELSE due END AS at FROM ops_outbox WHERE state IN ('pending','processing')) AS ready").fetchone()[0]
                raw.execute(f'UPDATE {REGISTRY} SET next_due=%s WHERE id=%s',(due,self.workspace_id))
        finally:raw.close()

class PostgresStore:
    def __init__(self,url=None):
        self.url=url or os.environ['DATABASE_URL']
        with self.connect() as db, db.transaction():
            db.execute('SELECT pg_advisory_xact_lock(819027153)')
            db.execute(f'''CREATE TABLE IF NOT EXISTS {REGISTRY} (
                id TEXT PRIMARY KEY, schema_name TEXT UNIQUE NOT NULL, ready BOOLEAN NOT NULL DEFAULT FALSE,
                minute BIGINT NOT NULL DEFAULT 0, request_count BIGINT NOT NULL DEFAULT 0,
                request_total BIGINT NOT NULL DEFAULT 0, next_due DOUBLE PRECISION)''')
            db.execute(f'CREATE INDEX IF NOT EXISTS orderops_workspace_due ON {REGISTRY}(next_due) WHERE ready')
    def connect(self):
        host=conninfo_to_dict(self.url).get('host','')
        tls={} if host in ('127.0.0.1','localhost','') or host.startswith('/') else {'sslmode':'require'}
        return psycopg.connect(self.url,autocommit=True,connect_timeout=10,options='-c statement_timeout=15000 -c lock_timeout=10000',**tls)
    @staticmethod
    def identity(token):return hashlib.sha256(token.encode()).hexdigest()
    def exists(self,token):
        with self.connect() as db:
            return db.execute(f'SELECT 1 FROM {REGISTRY} WHERE id=%s',(self.identity(token),)).fetchone() is not None
    def workspace(self,token):
        identity=self.identity(token);schema='w_'+identity[:40]
        with self.connect() as db:
            with db.transaction():
                db.execute('SELECT pg_advisory_xact_lock(819027154)')
                row=db.execute(f'SELECT ready FROM {REGISTRY} WHERE id=%s',(identity,)).fetchone()
                if row is None:
                    if db.execute(f'SELECT count(*) FROM {REGISTRY}').fetchone()[0]>=50:raise CapacityError()
                    db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
                    db.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))
                    for statement in DDL.split(';'):
                        if statement.strip():db.execute(statement)
                    db.execute(f'INSERT INTO {REGISTRY}(id,schema_name) VALUES(%s,%s)',(identity,schema))
        service=PostgresOrders(self,identity,schema)
        if row is None or not row[0]:
            seed(service)
            with self.connect() as db:db.execute(f'UPDATE {REGISTRY} SET ready=TRUE WHERE id=%s',(identity,))
        return service
    def consume_quota(self,token):
        identity=self.identity(token);minute=int(time.time()//60)
        with self.connect() as db:
            with db.transaction():
                row=db.execute(f'SELECT minute,request_count,request_total FROM {REGISTRY} WHERE id=%s FOR UPDATE',(identity,)).fetchone()
                count=row[1] if row[0]==minute else 0
                if count>=60 or row[2]>=1000:raise QuotaError()
                db.execute(f'UPDATE {REGISTRY} SET minute=%s,request_count=%s,request_total=request_total+1 WHERE id=%s',(minute,count+1,identity))
    def work(self):
        # Metadata only when idle: do not scan all schemas or poll every 0.5 seconds.
        with self.connect() as db:
            rows=db.execute(f'SELECT id,schema_name FROM {REGISTRY} WHERE ready AND next_due<=%s ORDER BY next_due LIMIT 10',(time.time(),)).fetchall()
        for identity,schema in rows:
            service=PostgresOrders(self,identity,schema)
            for _ in range(4):
                if not service.process_one()['processed']:break
