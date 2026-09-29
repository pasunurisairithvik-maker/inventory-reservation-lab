import os
from app.store import Store
if __name__=='__main__':
    Store(os.environ.get('INVENTORY_DB','inventory.db')).seed('BOOK-001',10)
    print('Added BOOK-001 with 10 units. Run once per fresh database.')
