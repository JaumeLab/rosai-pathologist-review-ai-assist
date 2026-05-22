#!/usr/bin/env python3
"""Build AI-assist study bundle: SlideSeek exact-top-1 cases only."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLIDESEEK = ROOT.parent / "rosai-pathologist-review-slideseek"
CASES_JSONL = (
    ROOT.parent
    / "rosai-bench/out/slide-seek/slideseek_rosai100_v2_share/cases.jsonl"
)
SOURCE_AI = SLIDESEEK / "ai-assist"
SOURCE_INDEX = SOURCE_AI / "index.json"


def load_correct_case_ids(cases_jsonl: Path) -> list[str]:
    correct: list[str] = []
    with cases_jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            case_id = (case.get("case_id") or "").strip()
            if not case_id:
                continue
            exact = case.get("exact_top1")
            if exact is None:
                exact = case.get("first_exact_rank") == 1
            if exact in (1, True):
                correct.append(case_id)
    return sorted(correct)


def build_assignments(case_ids: list[str], *, reviewers: int) -> dict:
    """Every reviewer gets the full exact-top-1 pool (same case list)."""
    reviewer_ids = [f"reviewer_{i}" for i in range(1, reviewers + 1)]
    pool = list(case_ids)
    assignments = {rid: pool for rid in reviewer_ids}
    return {
        "study_id": "rosai-ai-assist-correct-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assignment_mode": "full_pool_per_reviewer",
        "cases_per_reviewer": len(pool),
        "total_cases_in_pool": len(case_ids),
        "filter": "slideseek_exact_top1",
        "reviewers": [
            {"id": f"reviewer_{i}", "name": f"Pathologist {i}"} for i in range(1, reviewers + 1)
        ],
        "assignments": assignments,
    }


def copy_ai_assist(case_ids: list[str], out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    source_index = json.loads(SOURCE_INDEX.read_text(encoding="utf-8"))
    cases_map: dict[str, str] = {}
    for case_id in case_ids:
        src = SOURCE_AI / f"{case_id}.json"
        if not src.is_file():
            raise FileNotFoundError(f"Missing ai-assist bundle: {src}")
        dst = out_dir / f"{case_id}.json"
        shutil.copy2(src, dst)
        cases_map[case_id] = f"{case_id}.json"
    index = {
        "source": source_index.get("source", "slideseek-ai-assist"),
        "model": source_index.get("model", "gpt-5.4"),
        "generated_from": str(CASES_JSONL),
        "filter": "slideseek_exact_top1",
        "case_count": len(cases_map),
        "cases": cases_map,
    }
    (out_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-jsonl", type=Path, default=CASES_JSONL)
    parser.add_argument("--reviewers", type=int, default=5)
    args = parser.parse_args()

    if not args.cases_jsonl.is_file():
        raise SystemExit(f"cases.jsonl not found: {args.cases_jsonl}")
    if not SOURCE_INDEX.is_file():
        raise SystemExit(f"source ai-assist index not found: {SOURCE_INDEX}")

    case_ids = load_correct_case_ids(args.cases_jsonl)
    if not case_ids:
        raise SystemExit("No exact-top-1 cases found")

    assignments = build_assignments(case_ids, reviewers=args.reviewers)
    (ROOT / "assignments.json").write_text(
        json.dumps(assignments, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    copy_ai_assist(case_ids, ROOT / "ai-assist")

    src_index = SLIDESEEK / "index.html"
    if src_index.is_file():
        shutil.copy2(src_index, ROOT / "index.html")

    print(f"Built study with {len(case_ids)} exact-top-1 cases")
    for rid, ids in assignments["assignments"].items():
        print(f"  {rid}: {len(ids)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
