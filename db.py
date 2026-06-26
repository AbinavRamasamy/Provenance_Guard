import os
import sqlite3
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "provenance_guard.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                content_id              TEXT PRIMARY KEY,
                creator_id              TEXT NOT NULL,
                text_hash               TEXT NOT NULL,
                groq_score              REAL,
                stylo_score             REAL NOT NULL,
                confidence_score        REAL NOT NULL,
                attribution             TEXT NOT NULL,
                label_headline          TEXT NOT NULL,
                label_body              TEXT NOT NULL,
                label_confidence_display TEXT NOT NULL,
                status                  TEXT NOT NULL DEFAULT 'decided',
                timestamp               TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS appeals (
                appeal_id           TEXT PRIMARY KEY,
                content_id          TEXT NOT NULL,
                creator_reasoning   TEXT NOT NULL,
                contact             TEXT,
                timestamp           TEXT NOT NULL,
                FOREIGN KEY (content_id) REFERENCES audit_log(content_id)
            )
        """)


def insert_log_entry(
    content_id: str,
    creator_id: str,
    text_hash: str,
    groq_score: Optional[float],
    stylo_score: float,
    confidence_score: float,
    attribution: str,
    label: dict,
    timestamp: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO audit_log
               (content_id, creator_id, text_hash, groq_score, stylo_score,
                confidence_score, attribution, label_headline, label_body,
                label_confidence_display, status, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'decided', ?)""",
            (
                content_id, creator_id, text_hash, groq_score, stylo_score,
                confidence_score, attribution,
                label["headline"], label["body"], label["confidence_display"],
                timestamp,
            ),
        )


def get_entry(content_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM audit_log WHERE content_id = ?", (content_id,)
        ).fetchone()
    return dict(row) if row else None


def insert_appeal(
    appeal_id: str,
    content_id: str,
    creator_reasoning: str,
    contact: Optional[str],
    timestamp: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO appeals (appeal_id, content_id, creator_reasoning, contact, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (appeal_id, content_id, creator_reasoning, contact, timestamp),
        )


def update_status(content_id: str, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE audit_log SET status = ? WHERE content_id = ?",
            (status, content_id),
        )


def get_log_entries(limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        rows = conn.execute(
            """SELECT a.*, ap.appeal_id, ap.creator_reasoning, ap.contact,
                      ap.timestamp AS appeal_timestamp
               FROM audit_log a
               LEFT JOIN appeals ap ON a.content_id = ap.content_id
               ORDER BY a.timestamp DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()

    entries = []
    for row in rows:
        r = dict(row)
        appeal = None
        if r.get("appeal_id"):
            appeal = {
                "appeal_id": r["appeal_id"],
                "creator_reasoning": r["creator_reasoning"],
                "contact": r["contact"],
                "timestamp": r["appeal_timestamp"],
            }
        entries.append({
            "content_id": r["content_id"],
            "creator_id": r["creator_id"],
            "timestamp": r["timestamp"],
            "attribution": r["attribution"],
            "confidence": r["confidence_score"],
            "llm_score": r["groq_score"],
            "signals": {
                "groq": r["groq_score"],
                "stylometric": r["stylo_score"],
            },
            "status": r["status"],
            "label": {
                "headline": r["label_headline"],
                "body": r["label_body"],
                "confidence_display": r["label_confidence_display"],
            },
            "appeal": appeal,
        })

    return entries, total
