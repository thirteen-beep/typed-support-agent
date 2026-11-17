from __future__ import annotations
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
import uuid


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS orders(tenant TEXT,customer TEXT,order_id TEXT,status TEXT,
              amount_cents INTEGER,refundable INTEGER,PRIMARY KEY(tenant,order_id));
            CREATE TABLE IF NOT EXISTS documents(tenant TEXT,doc_id TEXT,title TEXT,body TEXT,
              PRIMARY KEY(tenant,doc_id));
            CREATE VIRTUAL TABLE IF NOT EXISTS doc_search USING fts5(tenant UNINDEXED,doc_id UNINDEXED,title,body);
            CREATE TABLE IF NOT EXISTS sessions(tenant TEXT,customer TEXT,session_id TEXT,history BLOB,
              PRIMARY KEY(tenant,customer,session_id));
            CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY,tenant TEXT,customer TEXT,
              session_id TEXT,question TEXT,outcome TEXT,result TEXT,elapsed_ms REAL,usage TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS spans(run_id TEXT,seq INTEGER,name TEXT,duration_ms REAL,
              args TEXT,result TEXT,status TEXT,PRIMARY KEY(run_id,seq));
            CREATE TABLE IF NOT EXISTS approvals(approval_id TEXT PRIMARY KEY,tenant TEXT,customer TEXT,
              order_id TEXT,amount_cents INTEGER,state TEXT,UNIQUE(tenant,customer,order_id));
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def seed_demo(self):
        with self.connect() as db:
            db.executemany('INSERT OR IGNORE INTO orders VALUES (?,?,?,?,?,?)', [
                ('acme', 'alice', 'A100', 'delivered', 12900, 1),
                ('acme', 'alice', 'A101', 'shipped', 5900, 0),
                ('acme', 'bob', 'B900', 'delivered', 99900, 1),
                ('beta', 'alice', 'Z800', 'processing', 88800, 1)])
            docs = [
                ('acme','refund-7d','Refund policy','Delivered items can be proposed for refund within the eligible window. A human must approve every refund request. No payment is executed by this demo.'),
                ('acme','shipping','Shipping policy','Shipped orders are in transit. Do not promise an arrival date unless tracking provides one. Ask support staff when tracking is unavailable.'),
                ('beta','private-policy','Private beta policy','BETA_INTERNAL_CANARY_7621: beta tenant internal document; must never be visible to acme.')]
            for row in docs:
                db.execute('INSERT OR IGNORE INTO documents VALUES (?,?,?,?)', row)
            db.execute('DELETE FROM doc_search')
            db.execute('INSERT INTO doc_search SELECT tenant,doc_id,title,body FROM documents')

    def order(self, tenant: str, customer: str, order_id: str):
        with self.connect() as db:
            row = db.execute('SELECT order_id,status,amount_cents,refundable FROM orders WHERE tenant=? AND customer=? AND order_id=?',
                             (tenant,customer,order_id)).fetchone()
            return dict(row) if row else None

    def search(self, tenant: str, query: str):
        import re
        words = re.findall(r'[a-zA-Z0-9_]+', query.lower())[:8]
        if not words:
            return []
        match = ' OR '.join('"'+w+'"' for w in words)
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT doc_id,title,body FROM doc_search WHERE doc_search MATCH ? AND tenant=? ORDER BY bm25(doc_search) LIMIT 3',
                (match,tenant))]

    def propose_refund(self, tenant, customer, order_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM orders WHERE tenant=? AND customer=? AND order_id=?',
                             (tenant,customer,order_id)).fetchone()
            if not row or not row['refundable']:
                return None
            db.execute('INSERT OR IGNORE INTO approvals VALUES (?,?,?,?,?,?)',
                       ('apr-'+uuid.uuid4().hex[:12],tenant,customer,order_id,row['amount_cents'],'pending'))
            return dict(db.execute('SELECT approval_id,order_id,amount_cents,state FROM approvals WHERE tenant=? AND customer=? AND order_id=?',
                                   (tenant,customer,order_id)).fetchone())

    def review(self, tenant, customer, approval_id, approve: bool):
        if type(approve) is not bool:
            raise ValueError('Approval must be boolean')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM approvals WHERE tenant=? AND customer=? AND approval_id=?',
                             (tenant,customer,approval_id)).fetchone()
            if not row:
                raise ValueError('Approval not found in this scope')
            desired = 'approved' if approve else 'rejected'
            if row['state'] != 'pending' and row['state'] != desired:
                raise ValueError('A completed decision cannot be reversed')
            db.execute('UPDATE approvals SET state=? WHERE approval_id=?', (desired,approval_id))
            return {'approval_id':approval_id,'state':desired,'payment_executed':False}

    def pending(self, tenant, customer):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT approval_id,order_id,amount_cents,state FROM approvals WHERE tenant=? AND customer=? ORDER BY approval_id',
                                               (tenant,customer))]

    def history(self, tenant, customer, session):
        with self.connect() as db:
            row = db.execute('SELECT history FROM sessions WHERE tenant=? AND customer=? AND session_id=?',
                             (tenant,customer,session)).fetchone()
            return row[0] if row else None

    def record(self, record, spans, history=None):
        with self.connect() as db:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (record['run_id'],record['tenant'],record['customer'],record['session_id'],record['question'],
                        record['outcome'],json.dumps(record['decision'],ensure_ascii=False),record['elapsed_ms'],
                        json.dumps(record.get('usage',{})),time.time()))
            for seq, span in enumerate(spans):
                db.execute('INSERT INTO spans VALUES (?,?,?,?,?,?,?)',
                           (record['run_id'],seq,span['name'],span['duration_ms'],json.dumps(span['args']),
                            json.dumps(span['result'],ensure_ascii=False),span['status']))
            if history is not None:
                db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?,?)',
                           (record['tenant'],record['customer'],record['session_id'],history))

    def runs(self, tenant, customer, limit=20):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT run_id,session_id,question,outcome,result,elapsed_ms,usage FROM runs WHERE tenant=? AND customer=? ORDER BY created DESC LIMIT ?',
                                               (tenant,customer,min(limit,100)))]

    def traces(self, tenant, customer, run_id):
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM runs WHERE run_id=? AND tenant=? AND customer=?',(run_id,tenant,customer)).fetchone():
                return []
            return [dict(r) for r in db.execute('SELECT seq,name,duration_ms,args,result,status FROM spans WHERE run_id=? ORDER BY seq',(run_id,))]
