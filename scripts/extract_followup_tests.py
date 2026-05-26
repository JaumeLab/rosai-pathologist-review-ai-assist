#!/usr/bin/env python3
"""Extract structured recommended follow-up tests from SlideSeek reports into ai-assist bundles."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = ROOT.parent / "rosai-bench"
DEFAULT_SOURCE = BENCH_ROOT / "out/slide-seek/slideseek_rosai100_v2_share/cases.jsonl"
DEFAULT_TRACES = BENCH_ROOT / "out/slide-seek/slideseek_rosai100_v2_share/traces"
DEFAULT_BUNDLES = ROOT / "ai-assist"
DEFAULT_ENV = BENCH_ROOT / ".env"

ROI_NAV_RE = re.compile(
    r"\bfollow\s+up\b.*\b(at|on|region|area|tile|mag|power|survey|scan)\b",
    re.I,
)
ANCILLARY_HINT_RE = re.compile(
    r"\b("
    r"ihc|immunohist|immunophenotyp|immunostain|special stain|molecular|sequencing|"
    r"fish|pcr|flow cytometry| cytogenetic|ancillary|confirmatory|"
    r"e-cadherin|p120|cd117|kit|dog1|s100|melan-a|hmb-45|p63|calponin|smmhc|"
    r"desmin|synaptophysin|chromogranin|ck7|ck20|pax8|gata3|er\b|pr\b|her2|"
    r"beta-catenin|bcl-2|cd34|cd31|ki-67|p53|ini1|brca|msi|mmr|"
    r"pas\b|gms\b|afb\b|iron stain|trichrome|congo red|"
    r"would (?:be )?(?:confirmed|appropriate)|confirmation by|recommend(?:ed|ation)?"
    r")\b",
    re.I,
)

SYSTEM_PROMPT = """You extract recommended clinical ancillary tests from SlideSeek pathology output.

Return ONLY valid JSON:
{"followup_tests": [{"test": "...", "rationale": "..."}]}

Include ONLY tests a pathologist might order to refine or confirm the diagnosis:
- immunohistochemistry / special stains
- molecular / FISH / cytogenetics
- flow cytometry when explicitly suggested

Exclude:
- requests to re-examine another ROI, higher magnification, or additional slide areas
- generic clinical follow-up, imaging, or management without a named test
- restating the diagnosis without a test recommendation

Rules:
- Max 6 items. Deduplicate overlapping panels.
- test: short label (≤120 chars), e.g. "E-cadherin and p120 IHC"
- rationale: one sentence on why (≤180 chars)
- If no ancillary tests are recommended, return {"followup_tests": []}"""


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_cases(source: Path) -> dict[str, dict]:
    cases: dict[str, dict] = {}
    with source.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            case_id = (case.get("case_id") or "").strip()
            if case_id:
                cases[case_id] = case
    return cases


def load_trace_excerpt(trace_dir: Path, case_id: str) -> str:
    trace_path = trace_dir / case_id / "trace.json"
    if not trace_path.is_file():
        return ""
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    chunks: list[str] = []
    report = (trace.get("final_report") or "").strip()
    if report:
        chunks.append(report)
    for step in trace.get("steps") or []:
        for tool in step.get("tool_executions") or []:
            for key in ("result", "output", "summary", "content"):
                val = tool.get(key)
                if isinstance(val, str) and ANCILLARY_HINT_RE.search(val):
                    chunks.append(val.strip())
    return "\n\n---\n\n".join(chunks[:4])


def tile_caption_hints(case: dict) -> str:
    lines: list[str] = []
    for tile in case.get("tile_descriptions") or case.get("tiles") or []:
        caption = (tile.get("caption") or tile.get("description") or "").strip()
        rationale = (tile.get("rationale") or "").strip()
        if caption and ANCILLARY_HINT_RE.search(caption) and not ROI_NAV_RE.search(caption):
            lines.append(f"Tile caption: {caption}")
        if rationale and ANCILLARY_HINT_RE.search(rationale) and not ROI_NAV_RE.search(rationale):
            lines.append(f"Tile note: {rationale}")
    return "\n".join(lines[:8])


def build_user_prompt(case: dict, *, trace_excerpt: str) -> str:
    report = (case.get("final_report") or case.get("report") or "").strip()
    diffs = case.get("differential_diagnosis") or []
    diff_text = "; ".join(str(d).strip() for d in diffs[:5] if str(d).strip())
    hints = tile_caption_hints(case)
    parts = [
        f"Case: {case.get('case_id', '')} | Organ: {case.get('organ') or '—'}",
        f"Primary prediction: {(case.get('prediction') or '').strip() or '—'}",
        f"Differentials: {diff_text or '—'}",
        "",
        "Final report:",
        report or "(none)",
    ]
    if trace_excerpt and trace_excerpt != report:
        parts.extend(["", "Additional trace excerpts:", trace_excerpt])
    if hints:
        parts.extend(["", "Possible ancillary mentions from tile text:", hints])
    return "\n".join(parts)


def normalize_tests(payload: dict) -> list[dict]:
    raw = payload.get("followup_tests") or payload.get("tests") or []
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            test = item.strip()
            rationale = ""
        else:
            test = str(item.get("test") or item.get("name") or "").strip()
            rationale = str(item.get("rationale") or item.get("purpose") or "").strip()
        if not test:
            continue
        key = re.sub(r"\s+", " ", test.lower())
        if key in seen:
            continue
        seen.add(key)
        if len(test) > 120:
            test = test[:117].rstrip() + "…"
        if len(rationale) > 180:
            rationale = rationale[:177].rstrip() + "…"
        out.append({"test": test, "rationale": rationale})
        if len(out) >= 6:
            break
    return out


def call_gpt(client, *, prompt: str, model: str) -> list[dict]:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=800,
    )
    content = response.choices[0].message.content or "{}"
    return normalize_tests(json.loads(content))


def enrich_bundle(bundle_path: Path, tests: list[dict]) -> None:
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["followup_tests"] = tests
    bundle["followup_tests_generated_at"] = datetime.now(timezone.utc).isoformat()
    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract follow-up tests into ai-assist bundles")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--traces", type=Path, default=DEFAULT_TRACES)
    parser.add_argument("--bundles-dir", type=Path, default=DEFAULT_BUNDLES)
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--case", action="append", default=[], help="Only process these case_ids")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env(args.env)
    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set (expected in rosai-bench/.env)", file=sys.stderr)
        return 1
    if not args.source.is_file():
        print(f"Source not found: {args.source}", file=sys.stderr)
        return 1
    if not args.bundles_dir.is_dir():
        print(f"Bundles dir not found: {args.bundles_dir}", file=sys.stderr)
        return 1

    cases = load_cases(args.source)
    bundle_paths = sorted(args.bundles_dir.glob("*.json"))
    bundle_paths = [p for p in bundle_paths if p.name != "index.json"]
    if args.case:
        wanted = set(args.case)
        bundle_paths = [p for p in bundle_paths if p.stem in wanted]
    if args.limit:
        bundle_paths = bundle_paths[: args.limit]

    from openai import OpenAI

    client = OpenAI()
    updated = 0
    for i, bundle_path in enumerate(bundle_paths, start=1):
        case_id = bundle_path.stem
        case = cases.get(case_id)
        if not case:
            print(f"[{i}/{len(bundle_paths)}] skip {case_id}: not in cases.jsonl", file=sys.stderr)
            continue
        if args.skip_existing:
            existing = json.loads(bundle_path.read_text(encoding="utf-8"))
            if existing.get("followup_tests") is not None:
                continue

        prompt = build_user_prompt(case, trace_excerpt=load_trace_excerpt(args.traces, case_id))
        print(f"[{i}/{len(bundle_paths)}] {case_id} …", flush=True)
        if args.dry_run:
            continue

        try:
            tests = call_gpt(client, prompt=prompt, model=args.model)
            enrich_bundle(bundle_path, tests)
            updated += 1
            print(f"  -> {len(tests)} test(s)")
        except Exception as exc:
            print(f"  FAILED {case_id}: {exc}", file=sys.stderr)
        time.sleep(0.25)

    print(f"Updated {updated} bundle(s) in {args.bundles_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
