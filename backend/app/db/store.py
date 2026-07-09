"""SQLite persistence: runs + trace events (replayable for SSE reconnect and demo replay)."""
import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.config import settings
from app.events import TraceEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    coverage REAL,
    unsupported_rate REAL,
    iterations INTEGER,
    token_usage INTEGER,
    report_md TEXT,
    report_dir TEXT,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    ts TEXT NOT NULL,
    node TEXT NOT NULL,
    event TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
"""

_db: aiosqlite.Connection | None = None


async def init_db() -> None:
    global _db
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(settings.db_path)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(_SCHEMA)
    await _db.commit()


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_run(run_id: str, question: str) -> None:
    await _db.execute(
        "INSERT INTO runs (id, question, status, created_at) VALUES (?, ?, 'running', ?)",
        (run_id, question, _now()))
    await _db.commit()


async def finish_run(run_id: str, *, coverage: float | None, unsupported_rate: float | None,
                     iterations: int, token_usage: int, report_md: str | None,
                     report_dir: str | None, result: dict[str, Any]) -> None:
    await _db.execute(
        """UPDATE runs SET status='done', coverage=?, unsupported_rate=?, iterations=?,
           token_usage=?, report_md=?, report_dir=?, result_json=?, finished_at=? WHERE id=?""",
        (coverage, unsupported_rate, iterations, token_usage, report_md, report_dir,
         json.dumps(result, default=str), _now(), run_id))
    await _db.commit()


async def fail_run(run_id: str, error: str) -> None:
    await _db.execute("UPDATE runs SET status='failed', error=?, finished_at=? WHERE id=?",
                      (error[:1000], _now(), run_id))
    await _db.commit()


async def insert_event(ev: TraceEvent) -> None:
    await _db.execute(
        "INSERT OR IGNORE INTO events (run_id, seq, ts, node, event, payload) VALUES (?, ?, ?, ?, ?, ?)",
        (ev.run_id, ev.seq, ev.ts.isoformat(), ev.node, ev.event, json.dumps(ev.payload, default=str)))
    await _db.commit()


async def get_run(run_id: str) -> dict | None:
    cur = await _db.execute("SELECT * FROM runs WHERE id=?", (run_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def list_runs(limit: int = 50) -> list[dict]:
    cur = await _db.execute(
        """SELECT id, question, status, coverage, iterations, token_usage, created_at, finished_at
           FROM runs ORDER BY created_at DESC LIMIT ?""", (limit,))
    return [dict(r) for r in await cur.fetchall()]


async def get_events(run_id: str, after_seq: int = 0) -> list[dict]:
    cur = await _db.execute(
        "SELECT seq, ts, node, event, payload FROM events WHERE run_id=? AND seq>? ORDER BY seq",
        (run_id, after_seq))
    return [{**dict(r), "payload": json.loads(r["payload"])} for r in await cur.fetchall()]
