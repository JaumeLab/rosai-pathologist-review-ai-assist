"""RosAI pathologist review API."""

from __future__ import annotations

import json
import os
import secrets
import urllib.request
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import get_store

STUDY_ID = os.environ.get("STUDY_ID", "rosai-selected-100-v3")
ASSIGNMENTS_URL = os.environ.get(
    "ASSIGNMENTS_URL",
    "https://raw.githubusercontent.com/JaumeLab/rosai-pathologist-review/main/assignments.json",
)
ADMIN_EXPORT_KEY = os.environ.get("ADMIN_EXPORT_KEY", "")

DEFAULT_CORS_ORIGINS = (
    "https://jaumelab.github.io",
    "http://127.0.0.1:8770",
    "http://127.0.0.1:8771",
    "http://127.0.0.1:8780",
    "http://localhost:8770",
    "http://localhost:8771",
    "http://localhost:8780",
)


def _cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw == "*":
        return ["*"]
    parsed = [o.strip() for o in raw.replace("|", ",").split(",") if o.strip()]
    return list(dict.fromkeys([*DEFAULT_CORS_ORIGINS, *parsed]))


CORS_ORIGINS = _cors_origins()


def _load_passcodes() -> dict[str, str]:
    raw = os.environ.get("REVIEWER_PASSCODES", "").strip()
    if not raw:
        return {}
    out: dict[str, str] = {}
    for entry in raw.replace(",", "|").split("|"):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        reviewer_id, code = entry.split(":", 1)
        reviewer_id = reviewer_id.strip()
        code = code.strip()
        if reviewer_id and code:
            out[reviewer_id] = code
    return out


PASSCODES = _load_passcodes()

IS_LOCAL_SQLITE = os.environ.get("REVIEW_DB_BACKEND", "").lower() == "sqlite"

app = FastAPI(title="RosAI Pathologist Review API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    # Local exploration: allow any localhost port (frontend may use 8772+).
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost)(:\d+)?" if IS_LOCAL_SQLITE else None,
    allow_credentials=False,
    allow_methods=["GET", "PUT", "OPTIONS"],
    allow_headers=["*"],
)

_assignments_cache: dict[str, Any] | None = None


def load_assignments() -> dict[str, Any]:
    global _assignments_cache
    if _assignments_cache is not None:
        return _assignments_cache
    with urllib.request.urlopen(ASSIGNMENTS_URL, timeout=20) as resp:
        _assignments_cache = json.load(resp)
    return _assignments_cache


def validate_reviewer(reviewer_id: str) -> dict[str, str]:
    data = load_assignments()
    for rev in data.get("reviewers", []):
        if rev.get("id") == reviewer_id:
            return rev
    raise HTTPException(status_code=403, detail=f"Unknown reviewer: {reviewer_id}")


def validate_case_for_reviewer(reviewer_id: str, case_id: str) -> None:
    data = load_assignments()
    allowed = set(data.get("assignments", {}).get(reviewer_id, []))
    if case_id not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Case {case_id} is not assigned to {reviewer_id}",
        )


def require_passcode(reviewer_id: str, passcode: str) -> None:
    if not PASSCODES:
        return
    expected = PASSCODES.get(reviewer_id)
    if not expected or not passcode or not secrets.compare_digest(passcode, expected):
        raise HTTPException(status_code=401, detail="Invalid passcode")


class ReviewPayload(BaseModel):
    reviewer_name: str = Field(min_length=1, max_length=200)
    dx: str = Field(default="", max_length=2000)
    differential1: str = Field(default="", max_length=2000)
    differential2: str = Field(default="", max_length=2000)
    comments: str = Field(default="", max_length=8000)


@app.get("/health")
def health() -> dict[str, Any]:
    backend = os.environ.get("REVIEW_DB_BACKEND", "sqlite")
    return {
        "status": "ok",
        "study_id": STUDY_ID,
        "backend": backend,
        "cors_origins": CORS_ORIGINS,
        "passcodes_required": bool(PASSCODES),
    }


@app.get("/api/reviews/{study_id}/{reviewer_id}")
def list_reviewer_reviews(
    study_id: str,
    reviewer_id: str,
    x_reviewer_passcode: str = Header(default=""),
) -> dict[str, Any]:
    if study_id != STUDY_ID:
        raise HTTPException(status_code=404, detail="Unknown study")
    validate_reviewer(reviewer_id)
    require_passcode(reviewer_id, x_reviewer_passcode)
    rows = get_store().list_reviews(study_id=study_id, reviewer_id=reviewer_id)
    cases = {
        row["case_id"]: {
            "dx": row.get("dx", ""),
            "differential1": row.get("differential1", ""),
            "differential2": row.get("differential2", ""),
            "comments": row.get("comments", ""),
            "updated_at": row.get("updated_at"),
            "created_at": row.get("created_at"),
        }
        for row in rows
    }
    return {
        "study_id": study_id,
        "reviewer_id": reviewer_id,
        "case_count": len(cases),
        "cases": cases,
    }


@app.put("/api/reviews/{study_id}/{reviewer_id}/{case_id}")
def upsert_review(
    study_id: str,
    reviewer_id: str,
    case_id: str,
    payload: ReviewPayload,
    x_reviewer_passcode: str = Header(default=""),
) -> dict[str, Any]:
    if study_id != STUDY_ID:
        raise HTTPException(status_code=404, detail="Unknown study")
    rev = validate_reviewer(reviewer_id)
    require_passcode(reviewer_id, x_reviewer_passcode)
    validate_case_for_reviewer(reviewer_id, case_id)
    saved = get_store().upsert_review(
        study_id=study_id,
        reviewer_id=reviewer_id,
        reviewer_name=payload.reviewer_name or rev.get("name", reviewer_id),
        case_id=case_id,
        dx=payload.dx.strip(),
        differential1=payload.differential1.strip(),
        differential2=payload.differential2.strip(),
        comments=payload.comments.strip(),
    )
    return {"ok": True, "review": saved}


@app.get("/api/export/{study_id}")
def export_study(study_id: str, key: str = "") -> dict[str, Any]:
    if study_id != STUDY_ID:
        raise HTTPException(status_code=404, detail="Unknown study")
    if not ADMIN_EXPORT_KEY or key != ADMIN_EXPORT_KEY:
        raise HTTPException(status_code=401, detail="Invalid export key")
    rows = get_store().export_study(study_id=study_id)
    return {"study_id": study_id, "count": len(rows), "reviews": rows}
