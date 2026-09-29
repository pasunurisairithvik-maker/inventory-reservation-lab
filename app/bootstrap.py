import argparse
import os
from app.orders import Orders
from app.store import Conflict

def seed(service):
    products=[('BAG-01','Everyday backpack',149900,18),('BOTTLE-01','Steel water bottle',69900,30),
              ('HEAD-01','Wireless headphones',249900,8),('NOTE-01','Dotted notebook',24900,50),('LAMP-01','Desk lamp',129900,12)]
    for product in products:
        try: service.add_product(*product)
        except Conflict: pass
    service.create_order('Campus store',[{'sku':'BAG-01','quantity':2},{'sku':'NOTE-01','quantity':3}],'sample-campus',3600)
    confirmed=service.create_order('Demo buyer',[{'sku':'BOTTLE-01','quantity':1}],'sample-buyer',3600)
    if confirmed['state']=='held': service.transition(confirmed['id'],'confirm')
    for _ in range(3): service.process_one()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Add fictional demo products and two sample orders; preserves existing data.')
    parser.add_argument('--db',default=os.environ.get('INVENTORY_DB','inventory.db'))
    args=parser.parse_args();seed(Orders(args.db));print('OrderOps demo data ready. No real customer data or payments.')
