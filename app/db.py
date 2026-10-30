"""Accès à la base de données SQLite (couche d'accès aux données)."""
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "database", "prisme.db")
SCHEMA_PATH = os.path.join(ROOT, "database", "schema.sql")

_lock = threading.RLock()


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def row(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


def scalar(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return r[0] if r else None


def write(fn):
    """Sérialise les écritures (SQLite n'accepte qu'un écrivain à la fois)."""
    def wrapper(*a, **kw):
        with _lock:
            return fn(*a, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper


# --- Dates ---------------------------------------------------------------
FMT = "%Y-%m-%d %H:%M:%S"


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now_str():
    return now().strftime(FMT)


def to_str(dt):
    return dt.strftime(FMT) if dt else None


def parse(s):
    if not s:
        return None
    try:
        return datetime.strptime(s[:19], FMT)
    except ValueError:
        return None


def ago(**kw):
    return to_str(now() - timedelta(**kw))
