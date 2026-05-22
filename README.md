# RosAI Pathologist Review — AI Assist (Correct Cases)

GitHub Pages app for pathologist review with **SlideSeek AI assist**, limited to cases where SlideSeek’s **top-1 prediction exactly matched** ground truth (`exact_top1`).

Distinct from the blinded study without AI assist: [rosai-pathologist-review](https://github.com/JaumeLab/rosai-pathologist-review).

## Live site

**https://jaumelab.github.io/rosai-pathologist-review-ai-assist/**

Pathologists use their personal link: `?reviewer=reviewer_1` … `reviewer_5`.

Each pathologist signs in with a personal link plus a **reviewer password** (same gate as the no-AI study).

Generate reviewer passwords once (creates `backend/reviewer_passcodes.env`, gitignored):

```bash
cd backend
python3 generate_passcodes.py
./deploy.sh
```

## Case pool

- **61 cases** (SlideSeek exact top-1 match on the RosAI 100 benchmark)
- **All 61 cases for every reviewer** (same pool; reviewer links only track who saved responses)

## Reviewer links

| Reviewer | URL |
|----------|-----|
| 1 | https://jaumelab.github.io/rosai-pathologist-review-ai-assist/?reviewer=reviewer_1 |
| 2 | https://jaumelab.github.io/rosai-pathologist-review-ai-assist/?reviewer=reviewer_2 |
| 3 | https://jaumelab.github.io/rosai-pathologist-review-ai-assist/?reviewer=reviewer_3 |
| 4 | https://jaumelab.github.io/rosai-pathologist-review-ai-assist/?reviewer=reviewer_4 |
| 5 | https://jaumelab.github.io/rosai-pathologist-review-ai-assist/?reviewer=reviewer_5 |

## Rebuild study data

```bash
python3 scripts/build_study.py
```

Regenerates `assignments.json`, `ai-assist/`, and copies `index.html` from `rosai-pathologist-review-slideseek`.

## Deploy

```bash
python3 scripts/build_study.py
git add -A && git commit -m "..." && ./publish.sh
```

Enable GitHub Pages once: [Settings → Pages](https://github.com/JaumeLab/rosai-pathologist-review-ai-assist/settings/pages) → branch **`main`**, folder **`/`** → Save.

### Review API (Cloud Run)

```bash
cd backend
chmod +x deploy.sh
./deploy.sh
```

Update `config.json` `api_base_url` with the Cloud Run URL, then push.

Study ID: `rosai-ai-assist-correct-v1` (separate Firestore namespace from the main study).
