import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            ts REAL NOT NULL,
            used INTEGER,
            total INTEGER,
            balance REAL
        )
    """)
    conn.commit()
    return conn


def save_snapshot(platform: str, used: int = 0, total: int = 0, balance: float = 0.0):
    conn = get_conn()
    conn.execute(
        "INSERT INTO usage_history (platform, ts, used, total, balance) VALUES (?, ?, ?, ?, ?)",
        (platform, time.time(), used, total, balance),
    )
    conn.commit()
    conn.close()


def get_history(platform: str, days: int = 7) -> list:
    conn = get_conn()
    cutoff = time.time() - days * 86400
    rows = conn.execute(
        "SELECT ts, used, total, balance FROM usage_history WHERE platform=? AND ts>=? ORDER BY ts",
        (platform, cutoff),
    ).fetchall()
    conn.close()
    return rows
