"""Accès à la base de données SQLite (couche d'accès aux données)."""
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("PRISME_DB") or os.path.join(ROOT, "database", "prisme.db")
SCHEMA_PATH = os.path.join(ROOT, "database", "schema.sql")

_lock = threading.RLock()
_local = threading.local()


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


class ThreadConn:
    """Une connexion par fil d'exécution : en WAL, les lectures ne bloquent jamais pendant une écriture."""

    def _get(self):
        c = getattr(_local, "conn", None)
        if c is None:
            c = _local.conn = connect()
        return c

    def __getattr__(self, name):
        return getattr(self._get(), name)

    def release(self):
        c = getattr(_local, "conn", None)
        if c is not None:
            try:
                c.rollback()
            finally:
                c.close()
                _local.conn = None


def init_schema(conn):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    migrate(conn)
    conn.commit()


def migrate(conn):
    """Évolutions de schéma sur une base existante (idempotent, aucune donnée supprimée)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)")}
    if "status_reason" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN status_reason TEXT")
    if "email_verified" not in {r[1] for r in conn.execute("PRAGMA table_info(users)")}:
        conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
    if not conn.execute("SELECT 1 FROM meta WHERE key='neutral_sources'").fetchone():
        # Plus de note ni de badge « certifiée » attribués à de vrais médias.
        conn.execute("UPDATE sources SET reliability=70, certified=0, reliability_note=NULL WHERE is_demo=0")
        conn.execute("INSERT INTO meta(key, value) VALUES ('neutral_sources', '1')")


def log_change(conn, actor, entity, entity_id, action, detail=""):
    """Journal de traçabilité des modifications éditoriales."""
    conn.execute("INSERT INTO change_log(actor, entity, entity_id, action, detail) VALUES (?,?,?,?,?)",
                 (actor, entity, entity_id, action, str(detail)[:500]))


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
