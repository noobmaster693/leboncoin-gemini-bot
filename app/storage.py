from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

from .models import DealRecord


class DealStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS deals (
                    listing_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL
                )
                """
            )
            con.commit()

    def exists(self, listing_id: str) -> bool:
        with self._connect() as con:
            cur = con.execute("SELECT 1 FROM deals WHERE listing_id = ?", (listing_id,))
            return cur.fetchone() is not None

    def save(self, record: DealRecord) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO deals(listing_id, url, record_json, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.listing.listing_id,
                    record.listing.url,
                    record.model_dump_json(),
                    record.status,
                    record.created_at.isoformat(),
                ),
            )
            con.commit()

    def get(self, listing_id: str) -> Optional[DealRecord]:
        with self._connect() as con:
            cur = con.execute("SELECT record_json FROM deals WHERE listing_id = ?", (listing_id,))
            row = cur.fetchone()
        if not row:
            return None
        return DealRecord.model_validate_json(row[0])

    def list_recent(self, limit: int = 50) -> List[DealRecord]:
        with self._connect() as con:
            cur = con.execute("SELECT record_json FROM deals ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
        return [DealRecord.model_validate_json(row[0]) for row in rows]

    def update_status(self, listing_id: str, status: str) -> None:
        record = self.get(listing_id)
        if record:
            record.status = status
            self.save(record)
