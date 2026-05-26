#!/usr/bin/env python3
"""Export all pathologist reviews to CSV or JSON."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import get_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export pathologist reviews")
    parser.add_argument("--study-id", default=os.environ.get("STUDY_ID", "rosai-selected-100-v3"))
    parser.add_argument("--format", choices=("csv", "json"), default="csv")
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()

    rows = get_store().export_study(study_id=args.study_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.format == "json":
        args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    else:
        fields = [
            "study_id",
            "reviewer_id",
            "reviewer_name",
            "case_id",
            "dx",
            "differential1",
            "differential2",
            "comments",
            "ai_helpfulness_score",
            "created_at",
            "updated_at",
        ]
        with args.output.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    print(f"Wrote {len(rows)} reviews to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
