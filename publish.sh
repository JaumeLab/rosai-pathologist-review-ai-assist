#!/usr/bin/env bash
# Push JaumeLab/rosai-pathologist-review-ai-assist to GitHub (GitHub Pages).
set -euo pipefail

REPO="JaumeLab/rosai-pathologist-review-ai-assist"
REMOTE="git@github.com:${REPO}.git"
GH="${GH:-gh}"

cd "$(dirname "$0")"

git remote set-url origin "$REMOTE" 2>/dev/null || git remote add origin "$REMOTE"

if curl -fsS "https://api.github.com/repos/${REPO}" >/dev/null 2>&1; then
  echo "Repository exists. Pushing…"
  git push -u origin main
  echo "Pages: https://jaumelab.github.io/rosai-pathologist-review-ai-assist/"
  exit 0
fi

if "$GH" auth status >/dev/null 2>&1; then
  "$GH" repo create "$REPO" --public --source=. --remote=origin --push \
    --description "Pathologist WSI review with SlideSeek AI assist (correct predictions only)"
  echo "Pages: https://jaumelab.github.io/rosai-pathologist-review-ai-assist/"
  exit 0
fi

echo "Create https://github.com/${REPO} then: git push -u origin main"
exit 1
