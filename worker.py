"""Run local event delivery and expired-hold cleanup in a separate process."""
import argparse
import os
import time
from app.orders import Orders
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=os.environ.get('INVENTORY_DB','inventory.db'))
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args();service=Orders(args.db)
    try:
        while True:
            result=service.process_one()
            if result['processed']: print(result,flush=True)
            if args.once: break
            time.sleep(0.5)
    except KeyboardInterrupt: pass
