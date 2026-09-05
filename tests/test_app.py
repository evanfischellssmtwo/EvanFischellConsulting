import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SITE = Path(__file__).parents[1] / "site"
sys.path.insert(0, str(SITE))
spec = importlib.util.spec_from_file_location("efc_app", SITE / "app.py")
efc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(efc)


@pytest.fixture(autouse=True)
def reset_state():
    efc._usage.update(day=None, chat=0, page=0, feedback=0)
    efc._pages.clear()
    efc._feedback_mem.clear()
    efc.FEEDBACK_KEY = ""
    efc.FEEDBACK_BUCKET = ""


@pytest.fixture
def client():
    efc.app.config.update(TESTING=True)
    return efc.app.test_client()


def test_evergreen_serves_and_rewrites_content(client, monkeypatch):
    import io
    content = io.BytesIO(b'<link href="/brand/efc.css"><a href="/downloads/evergreen-scope.pdf">PDF</a>')
    content.headers = {"Content-Type": "text/html; charset=utf-8"}
    monkeypatch.setattr(efc, "urlopen", lambda url, timeout: content)
    response = client.get("/evergreen?url=https://example.com")
    assert response.status_code == 200
    assert "Location" not in response.headers
    assert b'/evergreen/brand/efc.css' in response.data
    assert b'/evergreen/scope.pdf' in response.data


def test_evergreen_source_failure_is_not_a_redirect(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise efc.URLError("unavailable")
    monkeypatch.setattr(efc, "urlopen", unavailable)
    assert client.get("/evergreen").status_code == 502
    assert client.get("/evergreen/unknown").status_code == 404


def test_evergreen_guide_redirect(client):
    response = client.get("/evergreen/guide")
    assert response.status_code == 302
    assert response.headers["Location"] == "/evergreen/guide/start"


def test_evergreen_guide_content_and_assets(client, monkeypatch):
    import io
    content = io.BytesIO(b'<link rel="stylesheet" href="/guide/assets/guide.css"><a href="/guide/models">Models</a><img src="/brand/logos/efc-wordmark-light.svg">')
    content.headers = {"Content-Type": "text/html; charset=utf-8"}
    monkeypatch.setattr(efc, "urlopen", lambda url, timeout: content)
    response = client.get("/evergreen/guide/start")
    assert response.status_code == 200
    assert b'/evergreen/guide/assets/guide.css' in response.data
    assert b'/evergreen/guide/models' in response.data
    assert b'/evergreen/brand/logos/efc-wordmark-light.svg' in response.data


def test_utmb_serves_and_rewrites_content(client, monkeypatch):
    import io
    content = io.BytesIO(b'<a href="/vendor-ai-review">Scorecard</a><a href="/panel-biographies">Dossier</a>')
    content.headers = {"Content-Type": "text/html; charset=utf-8"}
    monkeypatch.setattr(efc, "urlopen", lambda url, timeout: content)
    response = client.get("/utmb")
    assert response.status_code == 200
    assert b'/utmb/vendor-ai-review' in response.data
    assert b'/utmb/panel-biographies' in response.data


def test_utmb_routes_and_error_handling(client, monkeypatch):
    assert client.get("/utmb/unknown").status_code == 404
    def unavailable(*args, **kwargs):
        raise efc.URLError("unavailable")
    monkeypatch.setattr(efc, "urlopen", unavailable)
    assert client.get("/utmb").status_code == 502


def test_invalid_chat_does_not_consume_quota(client):
    response = client.post("/api/agent/chat", json={"messages": []})
    assert response.status_code == 400
    assert efc._usage["chat"] == 0


@pytest.mark.parametrize("message", ["bad", {"role": "system", "text": "x"}, {"role": "user"}])
def test_chat_rejects_invalid_messages(client, message):
    response = client.post("/api/agent/chat", json={"messages": [message]})
    assert response.status_code == 400


def test_chat_parser_repairs_truncated_object():
    assert efc._parse_chat_response('{"reply":"hello"') == {"reply": "hello", "action": None}


def test_chat_parser_normalizes_action():
    result = efc._parse_chat_response('{"reply":"ok","action":{"type":"create_page","brief":"brief"}}')
    assert result["action"] == {"type": "create_page", "brief": "brief"}


def test_chat_parser_normalizes_feedback_action():
    result = efc._parse_chat_response(
        '{"reply":"saved","action":{"type":"save_feedback","note":"tighten the bullets","about":"resume"}}')
    assert result["action"] == {"type": "save_feedback", "note": "tighten the bullets", "about": "resume"}


@pytest.mark.parametrize("action", [
    '{"type":"save_feedback","note":"   "}',
    '{"type":"save_feedback"}',
    '{"type":"delete_everything","note":"x"}',
])
def test_chat_parser_rejects_bad_actions(action):
    assert efc._parse_chat_response('{"reply":"ok","action":%s}' % action)["action"] is None


def test_feedback_requires_note_before_quota(client):
    response = client.post("/api/agent/feedback", json={"note": "  "})
    assert response.status_code == 400
    assert efc._usage["feedback"] == 0


def test_feedback_saves_and_review_requires_key(client):
    saved = client.post("/api/agent/feedback", json={"note": "headshot is too big", "about": "resume: hero"})
    assert saved.status_code == 200
    assert len(efc._feedback_mem) == 1

    assert client.get("/feedback").status_code == 404
    assert client.get("/feedback?key=wrong").status_code == 404

    efc.FEEDBACK_KEY = "secret-key"
    page = client.get("/feedback?key=secret-key")
    assert page.status_code == 200
    assert "headshot is too big" in page.get_data(as_text=True)


def test_feedback_review_escapes_entries(client):
    client.post("/api/agent/feedback", json={"note": "<script>alert(1)</script>", "about": "x"})
    efc.FEEDBACK_KEY = "secret-key"
    body = client.get("/feedback?key=secret-key").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


@pytest.mark.parametrize("html", [
    "<html><head><meta name='robots' content='noindex'><script>x</script></head></html>",
    "<html><head><meta name='robots' content='noindex'></head><body onclick='x()'></body></html>",
    "<html><head><meta name='robots' content='noindex'></head><body><a href='https://example.com'>x</a></body></html>",
    "<html><body>missing noindex</body></html>",
])
def test_generated_html_rejects_unsafe_content(html):
    with pytest.raises(ValueError):
        efc._validate_generated_html(html)


def test_generated_page_has_security_headers(client):
    efc._pages["safe"] = {"html": "<html></html>", "ts": 0}
    response = client.get("/p/safe")
    assert response.status_code == 200
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]


def test_page_generation_validates_before_quota(client):
    response = client.post("/api/agent/page", json={"brief": ""})
    assert response.status_code == 400
    assert efc._usage["page"] == 0


def test_health_does_not_expose_usage(client):
    assert client.get("/api/health").json == {"ok": True, "service": "efc-site", "agent": True}


@pytest.mark.parametrize(
    "path",
    ["/", "/deck", "/pilot-tco", "/vendor-ai-review", "/vendor-ai-questionnaire",
     "/missing", "/api/health"],
)
def test_site_responses_prevent_search_indexing(client, path):
    response = client.get(path)
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"



def assert_self_contained(body):
    """No CDN, no remote font, no third-party fetch.

    Checks fetching constructs rather than the bare string "https://": the
    injected brand token files legitimately carry source URLs in comments.
    """
    pattern = r"""(?:url\(|@import\s+|src=|href=)["']?\s*(?:https?:)?//[^"')\s>]+"""
    remote = [r for r in re.findall(pattern, body) if "w3.org" not in r]
    assert not remote, f"remote references found: {remote[:3]}"


@pytest.fixture
def served_client(client, monkeypatch):
    """Client whose static pages actually resolve.

    Loading app.py by file location leaves Flask's root_path at the process cwd
    rather than site/, so every send_from_directory page 404s under the plain
    ``client`` fixture. Pin it for tests that assert on served bytes.
    """
    monkeypatch.setattr(efc.app, "root_path", str(SITE))
    return client


def test_vendor_ai_review_is_served_and_undiscoverable(served_client):
    """Unlisted: served on request, noindex in the page, and linked from nowhere."""
    response = served_client.get("/vendor-ai-review")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'name="robots" content="noindex, nofollow, noarchive"' in body
    assert "Vendor AI Evaluation" in body
    assert_self_contained(body)

    landing = served_client.get("/").get_data(as_text=True)
    assert "vendor-ai-review" not in landing


def test_vendor_ai_questionnaire_is_served_and_undiscoverable(served_client):
    """Unlisted vendor-facing questionnaire: served on request, linked from nowhere."""
    response = served_client.get("/vendor-ai-questionnaire")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'name="robots" content="noindex, nofollow, noarchive"' in body
    assert "Tell us how your AI actually works" in body
    assert_self_contained(body)

    landing = served_client.get("/").get_data(as_text=True)
    assert "vendor-ai-questionnaire" not in landing


def test_robots_allows_crawlers_to_observe_noindex(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.content_type == "text/plain; charset=utf-8"
    assert response.get_data(as_text=True) == "User-agent: *\nAllow: /\n"
    assert "Disallow: /" not in response.get_data(as_text=True)


def test_canonical_redirect_preserves_query(client):
    response = client.get("/x?a=1", headers={"Host": "www.evanfischellconsulting.com"})
    assert response.status_code == 301
    assert response.location == "https://evanfischellconsulting.com/x?a=1"
