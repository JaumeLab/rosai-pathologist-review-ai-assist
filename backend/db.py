"""Database layer: SQLite (local) or Firestore (production on GCP)."""

from __future__ import annotations

import os
import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ReviewStore(ABC):
    @abstractmethod
    def upsert_review(
        self,
        *,
        study_id: str,
        reviewer_id: str,
        reviewer_name: str,
        case_id: str,
        dx: str,
        differential1: str,
        differential2: str,
        comments: str,
        ai_helpfulness_score: int | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def list_reviews(self, *, study_id: str, reviewer_id: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def export_study(self, *, study_id: str) -> list[dict[str, Any]]: ...


class SQLiteReviewStore(ReviewStore):
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    study_id TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    reviewer_name TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    dx TEXT NOT NULL DEFAULT '',
                    differential1 TEXT NOT NULL DEFAULT '',
                    differential2 TEXT NOT NULL DEFAULT '',
                    comments TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(study_id, reviewer_id, case_id)
                );

                CREATE TABLE IF NOT EXISTS review_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    study_id TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    reviewer_name TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    dx TEXT NOT NULL DEFAULT '',
                    differential1 TEXT NOT NULL DEFAULT '',
                    differential2 TEXT NOT NULL DEFAULT '',
                    comments TEXT NOT NULL DEFAULT '',
                    recorded_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_reviews_study_reviewer
                    ON reviews(study_id, reviewer_id);
                CREATE INDEX IF NOT EXISTS idx_events_study
                    ON review_events(study_id, recorded_at);
                """
            )
            self._ensure_columns(conn)

    def _ensure_columns(self, conn: sqlite3.Connection) -> None:
        for table in ("reviews", "review_events"):
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if "ai_helpfulness_score" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN ai_helpfulness_score INTEGER")

    def upsert_review(
        self,
        *,
        study_id: str,
        reviewer_id: str,
        reviewer_name: str,
        case_id: str,
        dx: str,
        differential1: str,
        differential2: str,
        comments: str,
        ai_helpfulness_score: int | None = None,
    ) -> dict[str, Any]:
        now = _now_iso()
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT created_at FROM reviews
                WHERE study_id = ? AND reviewer_id = ? AND case_id = ?
                """,
                (study_id, reviewer_id, case_id),
            ).fetchone()
            created_at = row["created_at"] if row else now
            conn.execute(
                """
                INSERT INTO reviews (
                    study_id, reviewer_id, reviewer_name, case_id,
                    dx, differential1, differential2, comments,
                    ai_helpfulness_score, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(study_id, reviewer_id, case_id) DO UPDATE SET
                    reviewer_name = excluded.reviewer_name,
                    dx = excluded.dx,
                    differential1 = excluded.differential1,
                    differential2 = excluded.differential2,
                    comments = excluded.comments,
                    ai_helpfulness_score = excluded.ai_helpfulness_score,
                    updated_at = excluded.updated_at
                """,
                (
                    study_id,
                    reviewer_id,
                    reviewer_name,
                    case_id,
                    dx,
                    differential1,
                    differential2,
                    comments,
                    ai_helpfulness_score,
                    created_at,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO review_events (
                    study_id, reviewer_id, reviewer_name, case_id,
                    dx, differential1, differential2, comments,
                    ai_helpfulness_score, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    study_id,
                    reviewer_id,
                    reviewer_name,
                    case_id,
                    dx,
                    differential1,
                    differential2,
                    comments,
                    ai_helpfulness_score,
                    now,
                ),
            )
        return {
            "study_id": study_id,
            "reviewer_id": reviewer_id,
            "reviewer_name": reviewer_name,
            "case_id": case_id,
            "dx": dx,
            "differential1": differential1,
            "differential2": differential2,
            "comments": comments,
            "ai_helpfulness_score": ai_helpfulness_score,
            "created_at": created_at,
            "updated_at": now,
        }

    def list_reviews(self, *, study_id: str, reviewer_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reviews
                WHERE study_id = ? AND reviewer_id = ?
                ORDER BY case_id
                """,
                (study_id, reviewer_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def export_study(self, *, study_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reviews
                WHERE study_id = ?
                ORDER BY reviewer_id, case_id
                """,
                (study_id,),
            ).fetchall()
        return [dict(row) for row in rows]


class FirestoreReviewStore(ReviewStore):
    def __init__(self) -> None:
        from google.cloud import firestore

        self.client = firestore.Client()

    @staticmethod
    def _doc_id(study_id: str, reviewer_id: str, case_id: str) -> str:
        return f"{study_id}__{reviewer_id}__{case_id}"

    def upsert_review(
        self,
        *,
        study_id: str,
        reviewer_id: str,
        reviewer_name: str,
        case_id: str,
        dx: str,
        differential1: str,
        differential2: str,
        comments: str,
        ai_helpfulness_score: int | None = None,
    ) -> dict[str, Any]:
        now = _now_iso()
        doc_id = self._doc_id(study_id, reviewer_id, case_id)
        ref = self.client.collection("reviews").document(doc_id)
        existing = ref.get()
        if existing.exists:
            created_at = (existing.to_dict() or {}).get("created_at", now)
        else:
            created_at = now
        payload = {
            "study_id": study_id,
            "reviewer_id": reviewer_id,
            "reviewer_name": reviewer_name,
            "case_id": case_id,
            "dx": dx,
            "differential1": differential1,
            "differential2": differential2,
            "comments": comments,
            "ai_helpfulness_score": ai_helpfulness_score,
            "created_at": created_at,
            "updated_at": now,
        }
        ref.set(payload, merge=True)
        self.client.collection("review_events").add(
            {**payload, "recorded_at": now},
        )
        return payload

    def list_reviews(self, *, study_id: str, reviewer_id: str) -> list[dict[str, Any]]:
        query = (
            self.client.collection("reviews")
            .where("study_id", "==", study_id)
            .where("reviewer_id", "==", reviewer_id)
        )
        return [doc.to_dict() for doc in query.stream()]

    def export_study(self, *, study_id: str) -> list[dict[str, Any]]:
        query = self.client.collection("reviews").where("study_id", "==", study_id)
        rows = [doc.to_dict() for doc in query.stream()]
        rows.sort(key=lambda r: (r.get("reviewer_id", ""), r.get("case_id", "")))
        return rows


def get_store() -> ReviewStore:
    backend = os.environ.get("REVIEW_DB_BACKEND", "sqlite").strip().lower()
    if backend == "firestore":
        return FirestoreReviewStore()
    db_path = Path(os.environ.get("SQLITE_PATH", "data/reviews.db"))
    return SQLiteReviewStore(db_path)
