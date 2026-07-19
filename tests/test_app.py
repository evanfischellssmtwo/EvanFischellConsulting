import importlib.util
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
    efc._usage.update(day=None, chat=0, page=0)
    efc._pages.clear()


@pytest.fixture
def client():
    efc.app.config.update(TESTING=True)
    return efc.app.test_client()


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


@pytest.mark.parametrize("path", ["/", "/deck", "/missing", "/api/health"])
def test_site_responses_prevent_search_indexing(client, path):
    response = client.get(path)
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"


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
