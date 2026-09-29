import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi.testclient import TestClient
from app.orders import Orders
from app.store import Conflict
from app.main import create_app
from app.experiments import contention,crash_recovery

class OrderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'orders.db';self.now=100
        self.service=Orders(self.path,clock=lambda:self.now)
        self.service.add_product('A','Backpack',12345,10)
        self.service.add_product('B','Notebook',5000,3)
    def order(self,key='key',items=None,ttl=300):
        return self.service.create_order('Demo',items or [{'sku':'A','quantity':1}],key,ttl)
    def stock(self,sku='A'):
        return next(p for p in self.service.snapshot()['products'] if p['sku']==sku)
    def test_atomic_multi_item_and_money(self):
        row=self.order(items=[{'sku':'A','quantity':2},{'sku':'B','quantity':3}])
        self.assertEqual(row['total'],39690)
        self.assertEqual(self.stock()['available'],8)
        self.assertEqual(self.stock('B')['available'],0)
        self.assertTrue(self.service.snapshot()['metrics']['inventory_balanced'])
    def test_second_item_failure_rolls_back_everything(self):
        before=self.service.snapshot()
        with self.assertRaises(Conflict): self.order(items=[{'sku':'A','quantity':2},{'sku':'B','quantity':4}])
        after=self.service.snapshot()
        self.assertEqual(before['products'],after['products'])
        self.assertEqual(before['orders'],after['orders'])
        self.assertEqual(before['audit'],after['audit'])
        self.assertEqual(after['events'],[])
    def test_unknown_second_item_rolls_back(self):
        with self.assertRaises(Conflict): self.order(items=[{'sku':'A','quantity':1},{'sku':'Z','quantity':1}])
        self.assertEqual(self.stock()['available'],10)
    def test_concurrent_multi_item_no_oversell(self):
        def submit(i):
            try:
                self.order(str(i),[{'sku':'A','quantity':1},{'sku':'B','quantity':1}]);return 1
            except Conflict: return 0
        with ThreadPoolExecutor(max_workers=8) as pool: accepted=sum(pool.map(submit,range(30)))
        self.assertEqual(accepted,3)
        self.assertEqual(self.stock()['available'],7)
        self.assertEqual(self.stock('B')['available'],0)
        self.assertEqual(len(self.service.snapshot()['events']),3)
    def test_concurrent_duplicate_request(self):
        with ThreadPoolExecutor(max_workers=8) as pool: rows=list(pool.map(lambda _:self.order(),range(20)))
        self.assertEqual(len({r['id'] for r in rows}),1)
        self.assertEqual(self.stock()['available'],9)
        self.assertEqual(len(self.service.snapshot()['audit']),3)
    def test_reordered_items_retry_same_order(self):
        items=[{'sku':'B','quantity':1},{'sku':'A','quantity':1}]
        one=self.order(items=items);two=self.order(items=list(reversed(items)))
        self.assertEqual(one['id'],two['id'])
    def test_changed_payload_key_conflict(self):
        self.order()
        with self.assertRaises(Conflict): self.order(ttl=60)
        with self.assertRaises(Conflict): self.service.create_order('Other',[{'sku':'A','quantity':1}],'key')
    def test_terminal_confirm_idempotent(self):
        row=self.order();oid=row['id']
        self.service.transition(oid,'confirm');self.service.transition(oid,'confirm')
        with self.assertRaises(Conflict): self.service.transition(oid,'cancel')
        self.now+=400
        self.assertEqual(self.stock()['sold'],1)
        self.assertEqual(self.stock()['available'],9)
        self.assertEqual(len(self.service.snapshot()['events']),2)
    def test_cancel_returns_every_item_once(self):
        row=self.order(items=[{'sku':'A','quantity':2},{'sku':'B','quantity':1}])
        self.service.transition(row['id'],'cancel');self.service.transition(row['id'],'cancel')
        self.assertEqual(self.stock()['available'],10)
        self.assertEqual(self.stock('B')['available'],3)
    def test_expiry_boundary_is_committed_on_rejection(self):
        row=self.order(ttl=5);self.now+=5
        with self.assertRaises(Conflict): self.service.transition(row['id'],'confirm')
        with self.service.connection() as db:
            self.assertEqual(db.execute('SELECT state FROM ops_orders').fetchone()[0],'expired')
        self.assertEqual(self.service.cleanup(),0)
        self.assertEqual(self.stock()['available'],10)
        self.assertEqual(self.order(ttl=5)['state'],'expired')
        self.assertEqual(len(self.service.snapshot()['events']),2)
    def test_invalid_lines_and_bool(self):
        for items in [[],[{'sku':'A','quantity':True}],[{'sku':'A','quantity':1.2}],
                      [{'sku':'A','quantity':1},{'sku':'A','quantity':2}]]:
            with self.assertRaises(ValueError): self.service.create_order('Demo',items,'key')
        self.assertEqual(self.stock()['available'],10)
    def test_restart_preserves_order(self):
        row=self.order()
        self.assertEqual(Orders(self.path,clock=lambda:self.now).snapshot()['orders'][0]['id'],row['id'])
    def test_restock_balances_ledger(self):
        self.order();self.service.restock('A',5)
        self.assertEqual(self.stock()['received'],15)
        self.assertEqual(self.stock()['available'],14)
        self.assertTrue(self.stock()['balanced'])
    def test_outbox_and_order_commit_together(self):
        row=self.order();snapshot=self.service.snapshot()
        self.assertEqual(snapshot['events'][0]['order_id'],row['id'])
        self.assertEqual(snapshot['audit'][0]['action'],'order.held')
    def test_crash_duplicate_delivery_and_stale_ack(self):
        self.order();first=self.service.claim()
        self.assertTrue(self.service.deliver(first))
        self.now+=16;second=self.service.claim()
        self.assertFalse(self.service.acknowledge(first))
        self.assertFalse(self.service.deliver(first))
        self.assertTrue(self.service.deliver(second))
        self.assertTrue(self.service.acknowledge(second))
        snapshot=self.service.snapshot()
        self.assertEqual(snapshot['metrics']['received_events'],1)
        self.assertEqual(snapshot['events'][0]['state'],'sent')
    def test_retry_backoff_dead_letter_and_replay(self):
        self.order()
        for attempt in range(1,4):
            event=self.service.claim();self.assertEqual(event['attempts'],attempt)
            self.assertTrue(self.service.fail(event));self.assertIsNone(self.service.claim())
            self.now+=2**attempt
        snapshot=self.service.snapshot();self.assertEqual(snapshot['events'][0]['state'],'dead')
        self.service.replay(snapshot['events'][0]['id'])
        self.assertTrue(self.service.process_one()['acknowledged'])
        self.assertEqual(self.service.snapshot()['metrics']['received_events'],1)
        with self.assertRaises(Conflict): self.service.replay(event['id'])
    def test_repeated_worker_crashes_eventually_dead_letter(self):
        self.order()
        for _ in range(3):
            self.assertIsNotNone(self.service.claim());self.now+=16
        self.assertIsNone(self.service.claim())
        self.assertEqual(self.service.snapshot()['events'][0]['state'],'dead')
    def test_concurrent_workers_do_not_duplicate_effects(self):
        for i in range(8): self.order(str(i))
        with ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(lambda _:self.service.process_one(),range(12)))
        self.assertEqual(sum(r['processed'] for r in results),8)
        snapshot=self.service.snapshot()
        self.assertEqual(snapshot['metrics']['received_events'],8)
        self.assertEqual(snapshot['metrics']['event_counts'],{'sent':8})
    def test_live_api_order_actions_and_validation(self):
        with TestClient(create_app(self.path)) as client:
            self.assertEqual(client.get('/').status_code,200)
            self.assertIn('OrderOps',client.get('/').text)
            body={'customer':'Demo','items':[{'sku':'A','quantity':2}],'request_key':'http','ttl':300}
            row=client.post('/api/orders',json=body);self.assertEqual(row.status_code,200)
            self.assertEqual(client.post('/api/orders',json=body).json()['id'],row.json()['id'])
            self.assertEqual(client.post('/api/orders',json={**body,'ttl':60}).status_code,409)
            self.assertEqual(client.post('/api/orders',json={**body,'items':[{'sku':'A','quantity':True}]}).status_code,422)
            self.assertEqual(client.post('/api/orders/'+row.json()['id']+'/cancel',json={}).status_code,200)
            self.assertEqual(client.post('/api/products/A/restock',json={'quantity':3}).status_code,200)
            self.assertEqual(client.post('/api/events/process',json={}).status_code,200)
            self.assertEqual(client.get('/api/snapshot').status_code,200)
            self.assertEqual(client.post('/api/orders/missing/confirm',json={}).status_code,404)
    def test_experiment_evidence(self):
        result=contention();self.assertEqual(result['accepted'],10);self.assertTrue(result['balanced'])
        result=crash_recovery();self.assertEqual(result['inbox_rows_after'],1)
        self.assertTrue(result['stale_ack_rejected']);self.assertEqual(result['event_state'],'sent')
