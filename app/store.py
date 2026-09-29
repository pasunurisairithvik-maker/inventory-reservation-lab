import sqlite3
import uuid
from contextlib import contextmanager

class Conflict(ValueError):
    pass

class Store:
    """Single-host SQLite reservations with serialized writers and explicit states."""
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS stock(sku TEXT PRIMARY KEY, available INTEGER NOT NULL CHECK(available >= 0));
            CREATE TABLE IF NOT EXISTS reservations(
              id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
              sku TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity > 0),
              state TEXT NOT NULL CHECK(state IN ('held','confirmed','released','expired')),
              expires_at REAL NOT NULL);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
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
    def expire(db, now):
        rows = db.execute("SELECT sku,quantity FROM reservations WHERE state='held' AND expires_at<=?", (now,)).fetchall()
        for row in rows:
            db.execute('UPDATE stock SET available=available+? WHERE sku=?', (row['quantity'], row['sku']))
        db.execute("UPDATE reservations SET state='expired' WHERE state='held' AND expires_at<=?", (now,))

    def seed(self, sku, quantity):
        if not isinstance(sku, str) or not sku.strip() or len(sku)>64 or type(quantity) is not int or quantity<0:
            raise ValueError('Invalid SKU or stock count')
        with self.transaction() as db:
            db.execute('INSERT INTO stock VALUES (?,?)', (sku,quantity))

    def reserve(self, sku, quantity, request_key, now, ttl=60):
        if (not isinstance(sku,str) or not sku.strip() or len(sku)>64 or type(quantity) is not int or quantity<1
            or not isinstance(request_key,str) or not request_key.strip() or len(request_key)>128
            or type(ttl) not in (int,float) or not 1<=ttl<=3600):
            raise ValueError('Invalid reservation request')
        with self.transaction() as db:
            self.expire(db, now)
            old = db.execute('SELECT * FROM reservations WHERE request_key=?', (request_key,)).fetchone()
            if old:
                if (old['sku'],old['quantity']) != (sku,quantity):
                    raise Conflict('Request key was already used with a different payload')
                return dict(old)
            changed = db.execute('UPDATE stock SET available=available-? WHERE sku=? AND available>=?', (quantity,sku,quantity)).rowcount
            if not changed:
                raise Conflict('Unknown SKU or insufficient stock')
            rid = str(uuid.uuid4())
            db.execute('INSERT INTO reservations VALUES (?,?,?,?,?,?)', (rid,request_key,sku,quantity,'held',now+ttl))
            return dict(db.execute('SELECT * FROM reservations WHERE id=?', (rid,)).fetchone())

    def transition(self, rid, action, now):
        if action not in ('confirm','release'):
            raise ValueError('Invalid action')
        target = 'confirmed' if action=='confirm' else 'released'
        with self.transaction() as db:
            self.expire(db, now)
            row = db.execute('SELECT * FROM reservations WHERE id=?', (rid,)).fetchone()
            if row is None:
                raise KeyError(rid)
            if row['state']==target:
                return dict(row)
            if row['state']!='held':
                raise Conflict('Reservation is already '+row['state'])
            if action=='release':
                db.execute('UPDATE stock SET available=available+? WHERE sku=?', (row['quantity'],row['sku']))
            db.execute('UPDATE reservations SET state=? WHERE id=?', (target,rid))
            return dict(db.execute('SELECT * FROM reservations WHERE id=?', (rid,)).fetchone())

    def snapshot(self, now):
        with self.transaction() as db:
            self.expire(db, now)
            return {'stock':[dict(r) for r in db.execute('SELECT * FROM stock ORDER BY sku')],
                    'reservations':[dict(r) for r in db.execute('SELECT * FROM reservations ORDER BY request_key')]}
