#!/usr/bin/env python3
"""Generate one random passcode per reviewer for Cloud Run."""

from __future__ import annotations

import secrets
from pathlib import Path

REVIEWERS = [f"reviewer_{i}" for i in range(1, 6)]


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    env_path = script_dir / "reviewer_passcodes.env"
    txt_path = script_dir / "reviewer_passcodes.txt"

    pairs = [(rid, secrets.token_urlsafe(12)) for rid in REVIEWERS]
    env_value = "|".join(f"{rid}:{code}" for rid, code in pairs)

    env_path.write_text(f'REVIEWER_PASSCODES="{env_value}"\n', encoding="utf-8")

    lines = [
        "RosAI AI-assist pathologist review — reviewer passcodes",
        "Keep private. Re-deploy with: ./deploy.sh",
        "",
    ]
    for rid, code in pairs:
        lines.append(f"{rid}\t{code}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {env_path}")
    print(f"Wrote {txt_path}")
    print("")
    for rid, code in pairs:
        print(f"  {rid}: {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
