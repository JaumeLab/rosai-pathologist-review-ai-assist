# Deploy checklist

## 1. GitHub repository (one-time)

Create an empty public repo: **JaumeLab/rosai-pathologist-review-ai-assist**  
(no README — the local repo already has the initial commit)

```bash
cd rosai-pathologist-review-ai-assist
git push -u origin main
```

## 2. GitHub Pages (done)

Live URL: **https://jaumelab.github.io/rosai-pathologist-review-ai-assist/**

Reviewer links: `?reviewer=reviewer_1` … `reviewer_5`

## 3. Review API (done)

Cloud Run: `rosai-review-api-ai-assist`  
URL: `https://rosai-review-api-ai-assist-gkm46r7lpa-uc.a.run.app`

- Study ID: `rosai-ai-assist-correct-v1`
- No passcodes (`require_passcode: false` in `config.json`)
- Assignments served from GitHub (`assignments.json` on `main`)

## 4. Rebuild study (when AI bundles change)

```bash
python3 scripts/build_study.py
./scripts/push_assignments_to_gcs.sh
git add -A && git commit -m "Rebuild study" && git push
```
