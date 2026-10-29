# Evan Fischell Consulting

Brand sources and the public site for Evan Fischell Consulting
(`https://evanfischellconsulting.com`).

- `brand/` holds the brand strategy, knowledge base, pitch deck and one-pager
  (canonical sources).
- `site/` is the Flask + gunicorn Cloud Run application: landing page, unlisted
  pages (`/deck`, `/resume`, vendor-AI pages), the embedded agent
  (`site/agent_runtime.py`) and `/api/health`.
- `ARTIFACTS.md` names the canonical source for every deploy copy under `site/`.
- `reviews/` is historical evaluation output.

## Local tests

```powershell
python -m pip install -r site/requirements.txt pytest
python -m pytest
```

The authoritative contract is `.efisch/dev-push-tests.json`; PR CI
(`.github/workflows/ci.yml`) also builds `site/Dockerfile` and checks that the
image and the Antigravity CLI start.

## Delivery

Lifecycle comes from CI Control's
[branching policy](https://github.com/Evan-Fischell/efisch-ci-control/blob/main/config/branching-policy.json)
(`evan-fischell-consulting`, slot-qa): lease with `cicd_start_work` and land a
gated PR on `main` with `cicd_land_candidate`.

## Deployment

This site is a Google Cloud Run service, not a Nomad application, so the
[Nomad deployment stack](https://github.com/Evan-Fischell/efisch-runner-platform/blob/main/docs/nomadStack.md)
does not apply. A landing on `main` runs `.github/workflows/deploy-prod.yml` on
a GitHub-hosted runner with Workload Identity Federation: tests, `gcloud run
deploy --source site`, a traffic check and a smoke test of the live hostname.

- **Artifact profile:** Cloud Run source build of `site/` (`site/Dockerfile`).
- **Health:** `GET /api/health` returns `{"ok": true, "service": "efc-site", "agent": true}`.
- **State:** none on disk; feedback goes to a private Cloud Storage bucket,
  generated pages are in memory.
- **Port:** 8080 in the container.
- **QA composition binding:** not in the isolated AgentSpace QA composition.

No agent deploys by hand; a manual deploy is an emergency bypass that needs
Evan's explicit authorization.
