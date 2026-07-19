# Artifact ownership

This repository intentionally contains self-contained HTML outputs. Their size
is a deployment and offline-review requirement, not an invitation to maintain
parallel sources.

| Artifact | Role | Source of truth |
| --- | --- | --- |
| `brand/PITCH-DECK.html` | Canonical pitch deck | This file |
| `site/deck.html` | Cloud Run deploy copy | `brand/PITCH-DECK.html` |
| `brand/KNOWLEDGE-BASE.md` | Canonical agent knowledge base | This file |
| `site/kb.md` | Cloud Run deploy copy | `brand/KNOWLEDGE-BASE.md` |
| `brand/ONE-PAGER.html` | Canonical one-pager | This file |
| `brand/ONE-PAGER-INTERACTIVE.html` | Supported interactive variant | This file |
| `brand/ONE-PAGER.backup-2026-07-02.html` | Historical snapshot | Do not deploy or edit as canonical |
| `brand/previews/` and other exploration HTML | Design previews | Individual files; not deploy artifacts |
| `reviews/` | Evaluation output | Historical review evidence |

Run `python -m pytest tests/test_artifacts.py` before deployment. CI rejects a
deck or knowledge-base deploy copy that differs from its canonical source.
