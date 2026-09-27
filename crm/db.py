import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("CRM_DB_PATH", Path(__file__).parent / "crm.db"))


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS companies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                industry TEXT,
                website TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id TEXT PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                phone TEXT,
                company_id TEXT REFERENCES companies(id) ON DELETE SET NULL,
                company_name TEXT,
                tags TEXT DEFAULT '[]',
                source TEXT,
                status TEXT DEFAULT 'active',
                assigned_to TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pipelines (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pipeline_stages (
                id TEXT PRIMARY KEY,
                pipeline_id TEXT NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                color TEXT DEFAULT '#6B7280',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS opportunities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                contact_id TEXT REFERENCES contacts(id) ON DELETE SET NULL,
                contact_name TEXT,
                company_id TEXT REFERENCES companies(id) ON DELETE SET NULL,
                company_name TEXT,
                pipeline_id TEXT NOT NULL REFERENCES pipelines(id),
                pipeline_name TEXT,
                stage_id TEXT NOT NULL REFERENCES pipeline_stages(id),
                stage_name TEXT,
                status TEXT DEFAULT 'open',
                monetary_value REAL DEFAULT 0,
                close_date TEXT,
                assigned_to TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                body TEXT,
                contact_id TEXT REFERENCES contacts(id) ON DELETE SET NULL,
                contact_name TEXT,
                opportunity_id TEXT REFERENCES opportunities(id) ON DELETE SET NULL,
                opportunity_name TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                due_date TEXT,
                status TEXT DEFAULT 'open',
                contact_id TEXT REFERENCES contacts(id) ON DELETE SET NULL,
                contact_name TEXT,
                opportunity_id TEXT REFERENCES opportunities(id) ON DELETE SET NULL,
                opportunity_name TEXT,
                assigned_to TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS saved_views (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                entity TEXT NOT NULL,
                filters TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
        """)
