"""Guards for the landing page copy and the chat drawer's indicators.

The copy rules keep the page in the brand voice (executive-plain, no "AI", none
of the phrasing people now read as machine-written). The indicator checks are
this repository's contract test for the workspace rule that every status
indicator explains itself on hover (`ui-indicator-contract`).
"""

import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parents[1] / "site"
DRAWER_PAGES = ["index.html", "resume.html"]

BANNED = [
    "delve", "leverage", "seamless", "robust", "unlock", "empower", "elevate",
    "game-changer", "cutting-edge", "holistic", "synergy", "tapestry",
    "revolutionary", "ai-powered", "the honest answer", "not just",
]


class _VisibleText(HTMLParser):
    """Collects text a visitor can read (no script, style or SVG contents)."""

    SKIP = {"script", "style", "svg", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth and data.strip():
            self.parts.append(data.strip())


def _landing_text():
    parser = _VisibleText()
    parser.feed((SITE / "index.html").read_text(encoding="utf-8"))
    return " ".join(parser.parts)


def _script(page):
    html = (SITE / page).read_text(encoding="utf-8")
    match = re.search(r'<script id="efc-agent-script">(.*?)</script>', html, re.S)
    assert match, f"{page} has no chat drawer script"
    return match.group(1)


def test_landing_copy_never_says_ai():
    assert not re.search(r"\bAI\b", _landing_text())


def test_landing_copy_has_no_em_or_en_dashes():
    text = _landing_text()
    assert "—" not in text and "–" not in text


@pytest.mark.parametrize("phrase", BANNED)
def test_landing_copy_avoids_stock_phrases(phrase):
    assert phrase not in _landing_text().lower()


def test_landing_keeps_tagline_and_contact():
    text = _landing_text()
    assert "It shouldn't be hard" in text
    assert "evan@evanfischellconsulting.com" in text


@pytest.mark.parametrize("page", DRAWER_PAGES)
def test_drawer_uses_streaming_endpoint_and_valid_history_role(page):
    script = _script(page)
    assert "/api/agent/stream" in script
    assert "role:'agent'" not in script  # the server only accepts user/model


@pytest.mark.parametrize("page", DRAWER_PAGES)
def test_indicator_vocabulary_has_state_meaning_shape(page):
    script = _script(page)
    # Entries read 'Running: '+l+'. <meaning>' or 'Waiting: <meaning>'.
    texts = re.findall(r"return '([A-Z][a-z]+): (?:'\+l\+')?([^']+)'", script)
    states = {state for state, _ in texts}
    assert {"Running", "Done", "Failed", "Waiting"} <= states
    for state, meaning in texts:
        assert len(meaning) > 10, f"{state} explanation is too thin"


@pytest.mark.parametrize("page", DRAWER_PAGES)
def test_every_indicator_gets_title_and_aria_label_from_one_place(page):
    script = _script(page)
    # data-indicator is only ever set inside indicate(), which also sets the
    # native title and the aria-label from the same vocabulary entry.
    assert script.count("data-indicator") == 1
    body = re.search(r"function indicate\(([^)]*)\)\{(.*?)\n  \}", script, re.S).group(2)
    for attribute in ("'data-indicator'", "'title'", "'aria-label'"):
        assert attribute in body
    assert re.search(r"indicate\(row\.firstChild,'tool-step'", script)
    assert re.search(r"indicate\(w,'agent-reply','waiting'\)", script)


@pytest.mark.parametrize("page", DRAWER_PAGES)
def test_keyframes_belong_to_an_indicator(page):
    html = (SITE / page).read_text(encoding="utf-8")
    style = re.search(r'<style id="efc-agent-style">(.*?)</style>', html, re.S).group(1)
    # efc-pulse animates the tool-step dot and the waiting period, both of
    # which carry data-indicator through indicate().
    assert re.findall(r"@keyframes\s+([\w-]+)", style) == ["efc-pulse"]
    assert "prefers-reduced-motion" in style


@pytest.mark.parametrize("page", DRAWER_PAGES)
def test_inline_scripts_parse(page, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    html = (SITE / page).read_text(encoding="utf-8")
    scripts = re.findall(r"<script(?: id=\"[^\"]+\")?>(.*?)</script>", html, re.S)
    assert scripts
    for index, body in enumerate(scripts):
        path = tmp_path / f"script{index}.js"
        path.write_text(body, encoding="utf-8")
        result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, f"{page} script {index}: {result.stderr[-400:]}"