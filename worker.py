"""Continuous local inbox delivery and hold expiry, including public workspaces."""
import argparse
import logging
import os
import sqlite3
import time
from pathlib import Path
from app.orders import Orders

def cycle(paths):
    for path in paths:
        try:
            result=Orders(path).process_one()
            if result['processed']:print({'event_id':result['event_id'],'processed':True},flush=True)
        except sqlite3.OperationalError:
            # Keep serving other workspaces; never log aliases or message contents.
            logging.warning('Workspace database busy; retrying on next cycle')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=os.environ.get('INVENTORY_DB','inventory.db'))
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    directory=Path(os.environ.get('DEMO_WORKSPACES','workspaces')) if os.environ.get('PUBLIC_DEMO')=='1' else None
    if directory: directory.mkdir(parents=True,exist_ok=True)
    try:
        while True:
            cycle(sorted(directory.glob('*.db')) if directory else [args.db])
            if directory:(directory/'worker-heartbeat').touch()
            if args.once:break
            time.sleep(0.5)
    except KeyboardInterrupt:pass
