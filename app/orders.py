"""OrderOps transactional domain model. All money is integer paise."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager, closing
from app.store import Conflict

class Orders:
    def __init__(self,path,clock=time.time):
        self.path=str(path)
        self.clock=clock
        with closing(self.connection()) as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS ops_products(
              sku TEXT PRIMARY KEY,name TEXT NOT NULL,price INTEGER NOT NULL CHECK(price>=0),
              available INTEGER NOT NULL CHECK(available>=0),received INTEGER NOT NULL CHECK(received>=0));
            CREATE TABLE IF NOT EXISTS ops_orders(
              id TEXT PRIMARY KEY,request_key TEXT UNIQUE NOT NULL,fingerprint TEXT NOT NULL,
              customer TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('held','confirmed','cancelled','expired')),
              total INTEGER NOT NULL CHECK(total>=0),created REAL NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS ops_lines(
              order_id TEXT NOT NULL REFERENCES ops_orders(id),sku TEXT NOT NULL REFERENCES ops_products(sku),
              quantity INTEGER NOT NULL CHECK(quantity>0),unit_price INTEGER NOT NULL,
              PRIMARY KEY(order_id,sku));
            CREATE TABLE IF NOT EXISTS ops_audit(
              id INTEGER PRIMARY KEY AUTOINCREMENT,order_id TEXT,action TEXT NOT NULL,at REAL NOT NULL,detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ops_outbox(
              id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES ops_orders(id),kind TEXT NOT NULL,payload TEXT NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('pending','processing','sent','dead')),
              attempts INTEGER NOT NULL DEFAULT 0,due REAL NOT NULL,lease REAL,token TEXT,error TEXT);
            CREATE TABLE IF NOT EXISTS ops_inbox(
              event_id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,received REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS ops_orders_expiry ON ops_orders(state,expires);
            CREATE INDEX IF NOT EXISTS ops_outbox_ready ON ops_outbox(state,due);
            """)

    def connection(self):
        db=sqlite3.connect(self.path,timeout=10)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @contextmanager
    def transaction(self):
        db=self.connection()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def text(value,label,limit):
        if not isinstance(value,str) or not value.strip() or len(value)>limit:
            raise ValueError(f'{label} must be nonempty and at most {limit} characters')
        return value.strip()

    @staticmethod
    def integer(value,label,low,high):
        if type(value) is not int or not low<=value<=high:
            raise ValueError(f'{label} must be an integer between {low} and {high}')
        return value

    @staticmethod
    def event(db,order_id,kind,now,detail):
        db.execute('INSERT INTO ops_audit(order_id,action,at,detail) VALUES (?,?,?,?)',
                   (order_id,kind,now,json.dumps(detail,sort_keys=True)))
        if order_id:
            eid=str(uuid.uuid4())
            payload=json.dumps({'event_id':eid,'order_id':order_id,'kind':kind,'detail':detail},sort_keys=True)
            db.execute("INSERT INTO ops_outbox(id,order_id,kind,payload,state,due) VALUES (?,?,?,?,'pending',?)",
                       (eid,order_id,kind,payload,now))

    def add_product(self,sku,name,price,quantity):
        sku=self.text(sku,'SKU',64);name=self.text(name,'Name',80)
        self.integer(price,'Price in paise',0,100000000)
        self.integer(quantity,'Quantity',0,1000000)
        with self.transaction() as db:
            if db.execute('SELECT 1 FROM ops_products WHERE sku=?',(sku,)).fetchone():
                raise Conflict('SKU already exists')
            db.execute('INSERT INTO ops_products VALUES (?,?,?,?,?)',(sku,name,price,quantity,quantity))
            self.event(db,None,'product.created',self.clock(),{'sku':sku,'quantity':quantity})

    def restock(self,sku,quantity):
        self.integer(quantity,'Quantity',1,1000000)
        with self.transaction() as db:
            if not db.execute('UPDATE ops_products SET available=available+?,received=received+? WHERE sku=?',(quantity,quantity,sku)).rowcount:
                raise KeyError(sku)
            self.event(db,None,'stock.received',self.clock(),{'sku':sku,'quantity':quantity})

    @classmethod
    def lines(cls,items):
        if not isinstance(items,list) or not 1<=len(items)<=20:
            raise ValueError('An order needs 1 to 20 distinct items')
        result=[];seen=set()
        for item in items:
            if not isinstance(item,dict) or set(item)!={'sku','quantity'}:
                raise ValueError('Each line needs SKU and quantity only')
            sku=cls.text(item['sku'],'SKU',64)
            quantity=cls.integer(item['quantity'],'Quantity',1,1000)
            if sku in seen: raise ValueError('Duplicate SKU: combine quantities into one line')
            seen.add(sku);result.append({'sku':sku,'quantity':quantity})
        return sorted(result,key=lambda row:row['sku'])

    @staticmethod
    def get_order(db,oid):
        row=db.execute('SELECT * FROM ops_orders WHERE id=?',(oid,)).fetchone()
        if row is None: raise KeyError(oid)
        result=dict(row);result.pop('fingerprint')
        result['items']=[dict(x) for x in db.execute('SELECT l.sku,p.name,l.quantity,l.unit_price FROM ops_lines l JOIN ops_products p ON p.sku=l.sku WHERE order_id=? ORDER BY l.sku',(oid,))]
        return result

    @classmethod
    def expire(cls,db,now):
        rows=db.execute("SELECT id FROM ops_orders WHERE state='held' AND expires<=?",(now,)).fetchall()
        for row in rows:
            oid=row['id']
            for item in db.execute('SELECT sku,quantity FROM ops_lines WHERE order_id=?',(oid,)).fetchall():
                db.execute('UPDATE ops_products SET available=available+? WHERE sku=?',(item['quantity'],item['sku']))
            db.execute("UPDATE ops_orders SET state='expired' WHERE id=?",(oid,))
            cls.event(db,oid,'order.expired',now,{})
        return len(rows)

    def cleanup(self):
        with self.transaction() as db: return self.expire(db,self.clock())

    def create_order(self,customer,items,request_key,ttl=300):
        customer=self.text(customer,'Customer alias',60)
        request_key=self.text(request_key,'Request key',128)
        self.integer(ttl,'TTL',5,3600)
        items=self.lines(items)
        fingerprint=json.dumps({'customer':customer,'items':items,'ttl':ttl},sort_keys=True,separators=(',',':'))
        now=self.clock()
        with self.transaction() as db:
            self.expire(db,now)
            old=db.execute('SELECT id,fingerprint FROM ops_orders WHERE request_key=?',(request_key,)).fetchone()
            if old:
                if old['fingerprint']!=fingerprint: raise Conflict('Request key already belongs to a different order')
                return self.get_order(db,old['id'])
            rows=[];total=0
            for item in items:
                product=db.execute('SELECT * FROM ops_products WHERE sku=?',(item['sku'],)).fetchone()
                if product is None: raise Conflict('Unknown SKU: '+item['sku'])
                if not db.execute('UPDATE ops_products SET available=available-? WHERE sku=? AND available>=?',(item['quantity'],item['sku'],item['quantity'])).rowcount:
                    raise Conflict('Insufficient stock: '+item['sku']+'; no items were reserved')
                rows.append((item['sku'],item['quantity'],product['price']))
                total+=item['quantity']*product['price']
            oid=str(uuid.uuid4())
            db.execute("INSERT INTO ops_orders VALUES (?,?,?,?,'held',?,?,?)",(oid,request_key,fingerprint,customer,total,now,now+ttl))
            db.executemany('INSERT INTO ops_lines VALUES (?,?,?,?)',[(oid,*row) for row in rows])
            self.event(db,oid,'order.held',now,{'total_paise':total,'items':items})
            return self.get_order(db,oid)

    def transition(self,oid,action):
        if action not in ('confirm','cancel'): raise ValueError('Choose confirm or cancel')
        target='confirmed' if action=='confirm' else 'cancelled'
        now=self.clock()
        # Cleanup is its own committed transaction, so rejected late operations still retain expiry.
        self.cleanup()
        with self.transaction() as db:
            self.expire(db,now)
            row=self.get_order(db,oid)
            if row['state']==target: return row
            if row['state']!='held': raise Conflict('Order is already '+row['state'])
            if target=='cancelled':
                for item in row['items']:
                    db.execute('UPDATE ops_products SET available=available+? WHERE sku=?',(item['quantity'],item['sku']))
            db.execute('UPDATE ops_orders SET state=? WHERE id=?',(target,oid))
            self.event(db,oid,'order.'+target,now,{})
            return self.get_order(db,oid)

    def recover(self,db,now):
        db.execute("UPDATE ops_outbox SET state=CASE WHEN attempts>=3 THEN 'dead' ELSE 'pending' END,token=NULL,lease=NULL,due=?,error='Worker lease expired' WHERE state='processing' AND lease<=?",(now,now))

    def claim(self):
        now=self.clock()
        with self.transaction() as db:
            self.recover(db,now)
            row=db.execute("SELECT * FROM ops_outbox WHERE state='pending' AND due<=? ORDER BY due,id LIMIT 1",(now,)).fetchone()
            if row is None: return None
            token=str(uuid.uuid4())
            db.execute("UPDATE ops_outbox SET state='processing',attempts=attempts+1,token=?,lease=? WHERE id=?",(token,now+15,row['id']))
            return dict(db.execute('SELECT * FROM ops_outbox WHERE id=?',(row['id'],)).fetchone())

    def deliver(self,event):
        """Local inbox commits independently from acknowledgement; unique IDs deduplicate retries."""
        with self.transaction() as db:
            row=db.execute("SELECT 1 FROM ops_outbox WHERE id=? AND token=? AND state='processing' AND lease>?",(event['id'],event['token'],self.clock())).fetchone()
            if row is None: return False
            db.execute('INSERT OR IGNORE INTO ops_inbox VALUES (?,?,?,?)',(event['id'],event['kind'],event['payload'],self.clock()))
            return True

    def acknowledge(self,event):
        with self.transaction() as db:
            return bool(db.execute("UPDATE ops_outbox SET state='sent',token=NULL,lease=NULL,error=NULL WHERE id=? AND token=? AND state='processing' AND lease>?",(event['id'],event['token'],self.clock())).rowcount)

    def fail(self,event):
        with self.transaction() as db:
            return bool(db.execute("UPDATE ops_outbox SET state=CASE WHEN attempts>=3 THEN 'dead' ELSE 'pending' END,due=?,token=NULL,lease=NULL,error='Simulated delivery failure' WHERE id=? AND token=? AND state='processing' AND lease>?",(self.clock()+2**event['attempts'],event['id'],event['token'],self.clock())).rowcount)

    def replay(self,eid):
        with self.transaction() as db:
            row=db.execute('SELECT state FROM ops_outbox WHERE id=?',(eid,)).fetchone()
            if row is None: raise KeyError(eid)
            if row['state']!='dead': raise Conflict('Only dead-letter events can be replayed')
            db.execute("UPDATE ops_outbox SET state='pending',attempts=0,due=?,error=NULL WHERE id=?",(self.clock(),eid))
            self.event(db,None,'event.replayed',self.clock(),{'event_id':eid})

    def process_one(self,fail=False):
        self.cleanup()
        event=self.claim()
        if event is None: return {'processed':False,'reason':'No event ready'}
        if fail:
            self.fail(event)
            return {'processed':True,'event_id':event['id'],'delivered':False}
        delivered=self.deliver(event)
        acknowledged=self.acknowledge(event) if delivered else False
        return {'processed':True,'event_id':event['id'],'delivered':delivered,'acknowledged':acknowledged}

    def snapshot(self):
        now=self.clock()
        with self.transaction() as db:
            self.expire(db,now);self.recover(db,now)
            products=[dict(r) for r in db.execute('SELECT * FROM ops_products ORDER BY sku')]
            for p in products:
                p['held']=db.execute("SELECT COALESCE(SUM(l.quantity),0) FROM ops_lines l JOIN ops_orders o ON o.id=l.order_id WHERE l.sku=? AND o.state='held'",(p['sku'],)).fetchone()[0]
                p['sold']=db.execute("SELECT COALESCE(SUM(l.quantity),0) FROM ops_lines l JOIN ops_orders o ON o.id=l.order_id WHERE l.sku=? AND o.state='confirmed'",(p['sku'],)).fetchone()[0]
                p['balanced']=p['received']==p['available']+p['held']+p['sold']
            ids=[r['id'] for r in db.execute('SELECT id FROM ops_orders ORDER BY created DESC,id LIMIT 100')]
            orders=[self.get_order(db,oid) for oid in ids]
            events=[dict(r) for r in db.execute('SELECT id,order_id,kind,state,attempts,due,lease,error FROM ops_outbox ORDER BY rowid DESC LIMIT 100')]
            audit=[dict(r) for r in db.execute('SELECT * FROM ops_audit ORDER BY id DESC LIMIT 100')]
            inbox=[dict(r) for r in db.execute('SELECT event_id,kind,received FROM ops_inbox ORDER BY received DESC LIMIT 100')]
            counts={r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) AS n FROM ops_orders GROUP BY state')}
            event_counts={r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) AS n FROM ops_outbox GROUP BY state')}
            confirmed_value=db.execute("SELECT COALESCE(SUM(total),0) FROM ops_orders WHERE state='confirmed'").fetchone()[0]
            return {'products':products,'orders':orders,'events':events,'audit':audit,'inbox':inbox,
                    'metrics':{'order_counts':counts,'event_counts':event_counts,'confirmed_value_paise':confirmed_value,
                               'inventory_balanced':all(p['balanced'] for p in products),'received_events':db.execute('SELECT COUNT(*) FROM ops_inbox').fetchone()[0]},
                    'now':now,'list_limit':100}
