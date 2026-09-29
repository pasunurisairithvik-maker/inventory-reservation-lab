import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi.testclient import TestClient
from app.store import Store, Conflict
from app.main import create_app

class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'test.db'
        self.store=Store(self.path)
        self.store.seed('book',10)
    def reserve(self,key='key',quantity=2):
        return self.store.reserve('book',quantity,key,0,60)
    def test_concurrent_no_oversell(self):
        def order(i):
            try:
                self.reserve(str(i),1)
                return 1
            except Conflict:
                return 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(order,range(50))),10)
        self.assertEqual(self.store.snapshot(1)['stock'][0]['available'],0)
    def test_concurrent_same_key(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows=list(pool.map(lambda _:self.reserve(),range(20)))
        self.assertEqual(len({r['id'] for r in rows}),1)
        self.assertEqual(self.store.snapshot(1)['stock'][0]['available'],8)
    def test_key_conflict(self):
        self.reserve()
        with self.assertRaises(Conflict): self.reserve(quantity=3)
        self.assertEqual(self.store.snapshot(1)['stock'][0]['available'],8)
    def test_release_once(self):
        r=self.reserve()
        self.store.transition(r['id'],'release',1)
        self.store.transition(r['id'],'release',2)
        self.assertEqual(self.store.snapshot(2)['stock'][0]['available'],10)
    def test_confirm_is_final(self):
        r=self.reserve()
        self.store.transition(r['id'],'confirm',1)
        self.store.transition(r['id'],'confirm',2)
        with self.assertRaises(Conflict): self.store.transition(r['id'],'release',3)
        self.assertEqual(self.store.snapshot(100)['stock'][0]['available'],8)
    def test_expiry_boundary(self):
        r=self.reserve()
        with self.assertRaises(Conflict): self.store.transition(r['id'],'confirm',60)
        self.assertEqual(self.store.snapshot(61)['stock'][0]['available'],10)
        self.assertEqual(self.store.snapshot(62)['stock'][0]['available'],10)
        self.assertEqual(self.store.reserve('book',2,'key',63)['state'],'expired')
    def test_restart_persistence(self):
        r=self.reserve()
        self.assertEqual(Store(self.path).snapshot(1)['reservations'][0]['id'],r['id'])
    def test_invalid_does_not_change_stock(self):
        for quantity in [0,-1,True,1.5]:
            with self.assertRaises(ValueError): self.reserve(quantity=quantity)
        self.assertEqual(self.store.snapshot(1)['stock'][0]['available'],10)
    def test_unknown_and_insufficient(self):
        with self.assertRaises(Conflict): self.reserve(quantity=11)
        with self.assertRaises(Conflict): self.store.reserve('missing',1,'missing',0)
        self.assertEqual(self.store.snapshot(1)['reservations'],[])
    def test_api(self):
        with TestClient(create_app(self.path)) as client:
            body={'sku':'book','quantity':2,'request_key':'api'}
            response=client.post('/reservations',json=body)
            self.assertEqual(response.status_code,200)
            rid=response.json()['id']
            self.assertEqual(client.post('/reservations',json=body).json()['id'],rid)
            self.assertEqual(client.post('/reservations',json={**body,'quantity':3}).status_code,409)
            self.assertEqual(client.post(f'/reservations/{rid}/release').status_code,200)
            self.assertEqual(client.post('/reservations/unknown/confirm').status_code,404)
            self.assertEqual(client.post('/reservations',json={**body,'quantity':True}).status_code,422)
