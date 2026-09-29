"""Reproducible contention experiment; only the supplied workload is measured."""
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from app.store import Store, Conflict

def run():
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Path(directory)/'stock.db')
        store.seed('BOOK-001',10)
        def order(i):
            try:
                store.reserve('BOOK-001',1,f'order-{i}',now=0,ttl=60)
                return True
            except Conflict:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted=sum(pool.map(order,range(50)))
        state=store.snapshot(1)
        available=state['stock'][0]['available']
        report={'requests':50,'worker_threads':8,'initial_stock':10,'accepted':accepted,
                'rejected':50-accepted,'available_stock':available,'held_quantity':sum(r['quantity'] for r in state['reservations'] if r['state']=='held'),
                'scope':'One local SQLite database; not a distributed load benchmark.'}
        assert accepted==10 and available==0
        return report
if __name__=='__main__':
    report=run()
    Path('results').mkdir(exist_ok=True)
    Path('results/contention.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
