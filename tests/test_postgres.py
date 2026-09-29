"""Real PostgreSQL integration checks. CI supplies an isolated database."""
import os
import secrets
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.store import Conflict

@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'),'Requires an isolated PostgreSQL test database')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        from app.postgres import PostgresStore
        self.store=PostgresStore(os.environ['TEST_DATABASE_URL'])
        self.token=secrets.token_hex(32)
        self.service=self.store.workspace(self.token)
    def test_concurrent_stock_and_retry(self):
        def submit(i):
            try:
                self.service.create_order('Buyer',[{'sku':'HEAD-01','quantity':1}],str(i));return 1
            except Conflict:return 0
        with ThreadPoolExecutor(max_workers=8) as pool:accepted=sum(pool.map(submit,range(50)))
        self.assertEqual(accepted,8)
        snap=self.service.snapshot();self.assertTrue(snap['metrics']['inventory_balanced'])
        self.assertEqual(next(p for p in snap['products'] if p['sku']=='HEAD-01')['available'],0)
        first=self.service.create_order('Retry',[{'sku':'LAMP-01','quantity':1}],'retry')
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids=list(pool.map(lambda _:self.service.create_order('Retry',[{'sku':'LAMP-01','quantity':1}],'retry')['id'],range(16)))
        self.assertEqual(set(ids),{first['id']})
    def test_rollback_isolation_and_cancel(self):
        before=self.service.snapshot()
        with self.assertRaises(Conflict):
            self.service.create_order('Buyer',[{'sku':'BAG-01','quantity':1},{'sku':'HEAD-01','quantity':99}],'fail')
        self.assertEqual(self.service.snapshot()['products'],before['products'])
        oid=self.service.create_order('Buyer',[{'sku':'BAG-01','quantity':1}],'ok')['id']
        other=self.store.workspace(secrets.token_hex(32))
        with self.assertRaises(KeyError):other.transition(oid,'confirm')
        self.service.transition(oid,'cancel');self.service.transition(oid,'cancel')
        self.assertEqual(self.service.snapshot()['products'],before['products'])
    def test_expiry_commits_on_rejected_late_confirm(self):
        self.service.clock=lambda:100
        oid=self.service.create_order('Buyer',[{'sku':'HEAD-01','quantity':1}],'short',5)['id']
        self.service.clock=lambda:105
        with self.assertRaises(Conflict):self.service.transition(oid,'confirm')
        snap=self.service.snapshot()
        self.assertEqual(next(o for o in snap['orders'] if o['id']==oid)['state'],'expired')
        self.assertEqual(next(p for p in snap['products'] if p['sku']=='HEAD-01')['available'],8)
    def test_outbox_crash_dedup_and_fencing(self):
        # Seeded events are already sent.
        self.service.clock=lambda:100
        self.service.create_order('Buyer',[{'sku':'HEAD-01','quantity':1}],'crash')
        first=self.service.claim();self.assertTrue(self.service.deliver(first))
        self.service.clock=lambda:116
        replacement=self.service.claim();self.assertEqual(first['id'],replacement['id'])
        self.assertFalse(self.service.acknowledge(first))
        self.assertTrue(self.service.deliver(replacement));self.assertTrue(self.service.acknowledge(replacement))
        self.assertEqual(sum(e['event_id']==first['id'] for e in self.service.snapshot()['inbox']),1)
    def test_fresh_app_retains_cookie_and_worker_processes(self):
        from app.main import create_app
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'PUBLIC_DEMO':'1','DATABASE_URL':os.environ['TEST_DATABASE_URL'],'DEMO_WORKSPACES':tmp}):
            with TestClient(create_app(),base_url='https://testserver') as a:
                a.get('/api/snapshot')
                body={'customer':'Persistent','items':[{'sku':'HEAD-01','quantity':1}],'request_key':'persist','ttl':300}
                oid=a.post('/api/orders',json=body,headers={'Origin':'https://testserver'}).json()['id']
                cookies=a.cookies
            # New app has no authoritative files or in-process state.
            with TestClient(create_app(),base_url='https://testserver',cookies=cookies) as b:
                self.assertTrue(any(o['id']==oid for o in b.get('/api/snapshot').json()['orders']))
                self.store.work()
                self.assertTrue(any(e['order_id']==oid and e['state']=='sent' for e in b.get('/api/snapshot').json()['events']))
    def test_quota_atomic_under_concurrency(self):
        def consume(_):
            from app.postgres import QuotaError
            try:self.store.consume_quota(self.token);return 1
            except QuotaError:return 0
        with patch('app.postgres.time.time',return_value=1000),ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(consume,range(80))),60)
