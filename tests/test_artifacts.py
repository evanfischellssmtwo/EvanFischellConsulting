from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_deploy_artifacts_match_canonical_sources():
    assert (ROOT / "brand/PITCH-DECK.html").read_bytes() == (ROOT / "site/deck.html").read_bytes()
    assert (ROOT / "brand/KNOWLEDGE-BASE.md").read_bytes() == (ROOT / "site/kb.md").read_bytes()


def test_procfile_uses_one_worker_for_process_local_state():
    assert "-w 1" in (ROOT / "site/Procfile").read_text(encoding="utf-8")
