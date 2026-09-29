import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.orders import Orders

class PublicDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'PUBLIC_DEMO':'1','DEMO_WORKSPACES':self.tmp.name})
        self.env.start();self.app=create_app()
        self.a=TestClient(self.app,base_url='https://testserver')
        self.b=TestClient(self.app,base_url='https://testserver')
    def tearDown(self):
        self.a.close();self.b.close();self.env.stop();self.tmp.cleanup()
    def post(self,client,path,body):return client.post(path,json=body,headers={'Origin':'https://testserver'})
    def test_isolation_retry_restart_and_cookie_flags(self):
        response=self.a.get('/api/snapshot');self.b.get('/api/snapshot')
        for flag in ('HttpOnly','Secure','SameSite=Strict'):self.assertIn(flag,response.headers['set-cookie'])
        body={'customer':'Test','items':[{'sku':'HEAD-01','quantity':1}],'request_key':'same','ttl':300}
        first=self.post(self.a,'/api/orders',body).json()
        self.assertEqual(self.post(self.a,'/api/orders',body).json()['id'],first['id'])
        self.assertEqual(self.post(self.b,'/api/orders/'+first['id']+'/confirm',{}).status_code,404)
        with TestClient(create_app(),base_url='https://testserver',cookies=self.a.cookies) as restarted:
            self.assertTrue(any(o['id']==first['id'] for o in restarted.get('/api/snapshot').json()['orders']))
    def test_cross_origin_and_legacy_routes_blocked(self):
        self.a.get('/api/snapshot')
        self.assertEqual(self.a.post('/api/cleanup',json={},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.a.post('/api/cleanup',json={}).status_code,403)
        self.assertEqual(self.a.get('/inventory').status_code,404)
        self.assertEqual(self.a.get('/docs').status_code,404)
    def test_size_limit_and_cookie_path_traversal(self):
        response=self.a.post('/api/orders',content='a'*12001,headers={'Origin':'https://testserver','Content-Type':'application/json'})
        self.assertEqual(response.status_code,413)
        self.a.cookies.set('orderops_workspace','../../not-a-workspace')
        self.assertEqual(self.a.get('/api/snapshot').status_code,200)
        self.assertEqual(len(list(Path(self.tmp.name).glob('*.db'))),1)
    def test_rate_limit_and_background_delivery(self):
        self.a.get('/api/snapshot')
        body={'customer':'Test','items':[{'sku':'HEAD-01','quantity':1}],'request_key':'worker','ttl':300}
        oid=self.post(self.a,'/api/orders',body).json()['id']
        subprocess.run([sys.executable,'worker.py','--once'],check=True,capture_output=True)
        events=self.a.get('/api/snapshot').json()['events']
        self.assertTrue(any(e['order_id']==oid and e['state']=='sent' for e in events))
        self.assertEqual(self.a.get('/healthz').status_code,200)
        for _ in range(59):self.assertEqual(self.post(self.a,'/api/cleanup',{}).status_code,200)
        self.assertEqual(self.post(self.a,'/api/cleanup',{}).status_code,429)
    def test_order_cap_preserves_safe_retry(self):
        path=Path(self.tmp.name)/'domain.db';service=Orders(path,max_orders=1)
        service.add_product('A','Demo',100,2)
        one=service.create_order('Test',[{'sku':'A','quantity':1}],'one')
        self.assertEqual(service.create_order('Test',[{'sku':'A','quantity':1}],'one')['id'],one['id'])
        from app.store import Conflict
        with self.assertRaises(Conflict):service.create_order('Test',[{'sku':'A','quantity':1}],'two')
    def test_health_fails_without_worker(self):
        self.assertEqual(self.a.get('/healthz').status_code,503)

class SupervisorTests(unittest.TestCase):
    def test_worker_exit_stops_api(self):
        import serve
        started=time.monotonic()
        result=serve.supervise([sys.executable,'-c','import time;time.sleep(30)'],[sys.executable,'-c','raise SystemExit(7)'],Path.cwd())
        self.assertEqual(result,7)
        self.assertLess(time.monotonic()-started,5)
