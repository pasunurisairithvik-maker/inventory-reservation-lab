"""Isolated experiments never mutate the dashboard's inventory."""
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from app.orders import Orders
from app.store import Conflict

def contention():
    with tempfile.TemporaryDirectory() as folder:
        service=Orders(Path(folder)/'experiment.db',clock=lambda:0)
        service.add_product('LAST-10','Limited batch',10000,10)
        def order(i):
            try:
                service.create_order('Buyer '+str(i),[{'sku':'LAST-10','quantity':1}],str(i))
                return 1
            except Conflict: return 0
        with ThreadPoolExecutor(max_workers=8) as pool: accepted=sum(pool.map(order,range(50)))
        snapshot=service.snapshot()
        return {'experiment':'50 requests / 10 units','requests':50,'workers':8,'accepted':accepted,'rejected':50-accepted,
                'remaining':snapshot['products'][0]['available'],'balanced':snapshot['metrics']['inventory_balanced'],
                'scope':'Local single-host SQLite correctness experiment; not a throughput benchmark.'}

def crash_recovery():
    with tempfile.TemporaryDirectory() as folder:
        clock=[0]
        service=Orders(Path(folder)/'experiment.db',clock=lambda:clock[0])
        service.add_product('A','Example',100,1)
        service.create_order('Demo',[{'sku':'A','quantity':1}],'crash')
        first=service.claim()
        service.deliver(first)
        # Simulate process loss after inbox commit and before acknowledgement.
        before=service.snapshot()
        clock[0]=16
        second=service.claim()
        stale_ack=service.acknowledge(first)
        service.deliver(second);service.acknowledge(second)
        after=service.snapshot()
        return {'experiment':'Crash after delivery / before acknowledgement','deliveries_attempted':2,
                'inbox_rows_before':before['metrics']['received_events'],'inbox_rows_after':after['metrics']['received_events'],
                'stale_ack_rejected':not stale_ack,'event_state':after['events'][0]['state'],
                'scope':'At-least-once delivery to a local inbox, deduplicated by event ID; no external payment or email.'}
