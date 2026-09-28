import os
import sqlite3
from datetime import datetime, timezone
from flask import g, current_app

def get_default_db_path():
    if os.environ.get('VERCEL'):
        return os.path.join('/tmp', 'payflow.db')
    return os.path.join(os.path.dirname(__file__), 'instance', 'payflow.db')

DEFAULT_DB_PATH = get_default_db_path()

def get_db(db_path=None):
    if 'db' not in g:
        target_path = db_path or (
            current_app.config.get('DATABASE') if current_app else get_default_db_path()
        )
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        g.db = sqlite3.connect(target_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON;')
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(db_path=None):
    target_path = db_path or get_default_db_path()
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    conn = sqlite3.connect(target_path)
    conn.execute('PRAGMA foreign_keys = ON;')
    with conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS payments (
                id TEXT PRIMARY KEY,
                amount_paise INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'INR',
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS refunds (
                id TEXT PRIMARY KEY,
                payment_id TEXT UNIQUE NOT NULL,
                amount_paise INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (payment_id) REFERENCES payments (id)
            );

            CREATE TABLE IF NOT EXISTS status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                note TEXT,
                FOREIGN KEY (payment_id) REFERENCES payments (id)
            );

            CREATE INDEX IF NOT EXISTS idx_payments_status ON payments (status);
            CREATE INDEX IF NOT EXISTS idx_payments_created ON payments (created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_payments_key ON payments (idempotency_key);
            CREATE INDEX IF NOT EXISTS idx_status_history_pid ON status_history (payment_id);
        ''')
    conn.close()

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()
