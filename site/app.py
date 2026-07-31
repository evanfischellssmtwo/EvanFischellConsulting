"""Evan Fischell Consulting — public landing site + embedded agent (efc-site)."""
import json
import logging
import os
import re
import secrets as pysecrets
import threading
import time
from html.parser import HTMLParser
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory

app = Flask(__name__)

CANONICAL_HOST = "evanfischellconsulting.com"
REDIRECT_HOSTS = {
    "evanfischell.com",
    "www.evanfischell.com",
    "www.evanfischellconsulting.com",
}

MODEL = os.getenv("EFC_MODEL", "gemini-3.1-pro-preview")
CHAT_DAILY_CAP = int(os.getenv("CHAT_DAILY_CAP", "200"))
PAGE_DAILY_CAP = int(os.getenv("PAGE_DAILY_CAP", "15"))
MAX_TURNS = 16
MAX_MSG_CHARS = 2000
MAX_PAGES_STORED = 100

_usage = {"day": None, "chat": 0, "page": 0}
_usage_lock = threading.Lock()
_pages = {}  # id -> {"html": str, "ts": float}
_pages_lock = threading.Lock()
_kb_cache = None
logger = logging.getLogger(__name__)


def _kb():
    global _kb_cache
    if _kb_cache is None:
        _kb_cache = (Path(app.root_path) / "kb.md").read_text(encoding="utf-8")
    return _kb_cache


def _spend(kind, cap):
    with _usage_lock:
        today = time.strftime("%Y-%m-%d")
        if _usage["day"] != today:
            _usage.update(day=today, chat=0, page=0)
        if _usage[kind] >= cap:
            return False
        _usage[kind] += 1
        return True


def _normalize_messages(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages required")
    contents = []
    for message in messages[-MAX_TURNS:]:
        if not isinstance(message, dict):
            raise ValueError("each message must be an object")
        role = message.get("role")
        if role not in {"user", "model"}:
            raise ValueError("message role must be user or model")
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("message text required")
        contents.append({"role": role, "parts": [{"text": text[:MAX_MSG_CHARS]}]})
    return contents


def _parse_chat_response(raw):
    raw = (raw or "").strip()
    out = None
    for candidate in (raw, raw + "}", raw + "}}"):
        try:
            out = json.loads(candidate)
            break
        except json.JSONDecodeError:
            continue
    if out is None:
        match = re.search(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.S)
        if match:
            out = {"reply": json.loads('"' + match.group(1) + '"'), "action": None}
        else:
            match = re.search(r"\{.*\}", raw, re.S)
            try:
                out = json.loads(match.group(0)) if match else {"reply": raw, "action": None}
            except json.JSONDecodeError:
                out = {"reply": raw, "action": None}
    if isinstance(out, list):
        out = next((item for item in out if isinstance(item, dict)), None) or {"reply": raw}
    if not isinstance(out, dict):
        out = {"reply": str(out)}
    reply = str(out.get("reply") or "").strip() or "Sorry — I lost my train of thought. Try again?"
    action = out.get("action") if isinstance(out.get("action"), dict) else None
    if action:
        brief = action.get("brief")
        if action.get("type") != "create_page" or not isinstance(brief, str) or not brief.strip():
            action = None
        else:
            action = {"type": "create_page", "brief": brief[:2000]}
    return {"reply": reply, "action": action}


class _GeneratedPageValidator(HTMLParser):
    BLOCKED_TAGS = {"script", "iframe", "embed", "object", "form", "base"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.errors = []
        self.has_html = False
        self.has_noindex = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attributes = {name.lower(): (value or "") for name, value in attrs}
        self.has_html |= tag == "html"
        if tag in self.BLOCKED_TAGS:
            self.errors.append(f"blocked tag: {tag}")
        if any(name.startswith("on") for name in attributes):
            self.errors.append("event handler attributes are blocked")
        for name in ("href", "src", "action", "formaction"):
            value = attributes.get(name, "").strip().lower()
            if value.startswith(("http:", "https:", "//", "javascript:", "data:")):
                self.errors.append(f"external or active {name} is blocked")
        if tag == "meta" and attributes.get("name", "").lower() == "robots":
            content = attributes.get("content", "").lower()
            self.has_noindex |= "noindex" in content


def _validate_generated_html(html):
    parser = _GeneratedPageValidator()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        raise ValueError("malformed generated HTML") from exc
    if not parser.has_html:
        parser.errors.append("html element required")
    if not parser.has_noindex:
        parser.errors.append("noindex metadata required")
    if parser.errors:
        raise ValueError("; ".join(parser.errors))


def _client():
    from google import genai
    return genai.Client()  # reads GEMINI_API_KEY from env


CHAT_PROTOCOL = """

## Response protocol (strict)
Respond with ONLY a JSON object: {"reply": "<your message to the visitor>",
"action": null}. When the visitor explicitly asks you to create a page or
website (an explicit request counts as agreement), or has clearly agreed to
your offer of one, set "action" to {"type": "create_page", "brief": "<one
paragraph describing what the page should be — the visitor's request, their
role/situation if relevant, and what it should cover>"} and keep "reply"
short (tell them the page is being prepared). Keep replies under 160 words.
Plain text only in reply — no markdown headings, no bullets unless brief.
"""

PAGE_SYS = """You generate a single, complete, self-contained HTML page for a
visitor, on behalf of the Evan Fischell Consulting embedded agent. The visitor
brief tells you what they want. Two modes:

1. **Professional brief** (the visitor's role/situation and the firm): 2–4
   short sections grounded ONLY in the company facts below — no pricing, no
   client names, no certifications, no guarantees.
2. **Anything-else page** (the visitor asked for a page on some topic — a
   hobby, an interest, something playful): make it genuinely good and
   delightful. Accurate, tasteful, family-friendly. It is a demonstration of
   craft, so make it charming.

Hard rules for both: one file, no external resources (no fonts, images,
scripts, trackers); inline CSS only. Never: offensive content, impersonation
of real people or companies, medical/legal/financial advice, anything
involving patient data. Include <meta name="robots" content="noindex,
nofollow">. Output ONLY the HTML document, no code fences.

Brand chrome (both modes): ink #0F2233 header band with the wordmark
"Evan Fischell Consulting." (Consulting font-weight 300, the period in amber
#E8912A) and a headline ending in an amber period; paper #F4F7F9 background,
slate #34505F body text, amber used sparingly (a 44px×2px rule, accents);
font stack: 'IBM Plex Sans','Segoe UI',system-ui,sans-serif. Ink footer:
"Prepared by the Evan Fischell Consulting embedded agent ·
evan@evanfischellconsulting.com". Inside the chrome, mode 2 pages may play
with layout freely.

## Company facts
"""


@app.before_request
def canonicalize():
    host = (request.host or "").split(":")[0].lower()
    if host in REDIRECT_HOSTS:
        path = request.full_path if request.query_string else request.path
        return redirect(f"https://{CANONICAL_HOST}{path}", code=301)
    return None


@app.after_request
def prevent_search_indexing(response):
    # Crawlers must be able to fetch pages to observe this directive. Keep
    # robots.txt crawlable; blocking the site there can preserve known URLs in
    # search results because the crawler cannot see the noindex response.
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


@app.get("/robots.txt")
def robots():
    return "User-agent: *\nAllow: /\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.get("/")
def index():
    return send_from_directory(app.root_path, "index.html")


@app.get("/deck")
def deck():
    # Unlisted: nothing links here; the page carries noindex. Deployed copy of
    # brand/PITCH-DECK.html (canonical) — re-copy on each deploy.
    return send_from_directory(app.root_path, "deck.html")


@app.get("/resume")
def resume():
    # Unlisted, like /deck: nothing links here; the page carries noindex.
    # Interactive resume that prints as a two-page document.
    return send_from_directory(app.root_path, "resume.html")


@app.post("/api/agent/chat")
def agent_chat():
    try:
        contents = _normalize_messages(request.get_json(silent=True))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not _spend("chat", CHAT_DAILY_CAP):
        return jsonify({"reply": "I've hit my conversation limit for today — "
                        "please reach Evan directly at evan@evanfischellconsulting.com.",
                        "action": None}), 429
    try:
        from google.genai import types
        resp = _client().models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=_kb() + CHAT_PROTOCOL,
                response_mime_type="application/json",
                max_output_tokens=8192,
                thinking_config=types.ThinkingConfig(thinking_budget=2048),
            ),
        )
        return jsonify(_parse_chat_response(resp.text))
    except Exception:
        logger.exception("chat generation failed")
        return jsonify({"reply": "Something went wrong on my end. You can always "
                        "reach Evan at evan@evanfischellconsulting.com.",
                        "action": None}), 502


@app.post("/api/agent/page")
def agent_page():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400
    brief = str(data.get("brief") or "").strip()[:2000]
    if not brief:
        return jsonify({"error": "brief required"}), 400
    if not _spend("page", PAGE_DAILY_CAP):
        return jsonify({"error": "page limit reached for today"}), 429
    try:
        from google.genai import types
        resp = _client().models.generate_content(
            model=MODEL,
            contents=f"Visitor brief: {brief}",
            config=types.GenerateContentConfig(
                system_instruction=PAGE_SYS + _kb(),
                max_output_tokens=24576,
                thinking_config=types.ThinkingConfig(thinking_budget=4096),
            ),
        )
        html = (resp.text or "").strip()
        html = re.sub(r"^```(?:html)?\s*|\s*```$", "", html)
        _validate_generated_html(html)
        pid = pysecrets.token_urlsafe(8)
        with _pages_lock:
            if len(_pages) >= MAX_PAGES_STORED:
                oldest = min(_pages, key=lambda k: _pages[k]["ts"])
                _pages.pop(oldest, None)
            _pages[pid] = {"html": html, "ts": time.time()}
        return jsonify({"id": pid, "url": f"/p/{pid}"})
    except Exception:
        logger.exception("page generation failed")
        return jsonify({"error": "generation failed"}), 502


@app.get("/p/<pid>")
def page(pid):
    with _pages_lock:
        entry = _pages.get(pid)
    if not entry:
        return ("This page has expired. Ask the agent on the home page to "
                "make you a fresh one."), 404
    return entry["html"], 200, {"Content-Type": "text/html; charset=utf-8",
                                "X-Robots-Tag": "noindex, nofollow",
                                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"}


FAVICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
               '<rect width="64" height="64" rx="14" fill="#0F2233"/>'
               '<text x="27" y="42" font-family="Segoe UI,system-ui,sans-serif" '
               'font-size="26" font-weight="600" fill="#F4F7F9" text-anchor="middle">EF</text>'
               '<circle cx="48" cy="40" r="5" fill="#E8912A"/></svg>')


@app.get("/favicon.ico")
@app.get("/favicon.svg")
def favicon():
    return FAVICON_SVG, 200, {"Content-Type": "image/svg+xml",
                              "Cache-Control": "public, max-age=86400"}


@app.errorhandler(404)
def not_found(e):
    return ("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Evan Fischell Consulting</title></head>
<body style="margin:0;background:#F4F7F9;color:#0F2233;font-family:'IBM Plex Sans','Segoe UI',system-ui,sans-serif">
<div style="max-width:560px;margin:18vh auto 0;padding:0 24px">
<div style="font-size:15px;margin-bottom:28px"><b style="font-weight:600">Evan Fischell</b>
<span style="font-weight:300">Consulting</span><span style="color:#E8912A;font-weight:600">.</span></div>
<div style="height:2px;width:44px;background:#E8912A;margin-bottom:16px"></div>
<h1 style="font-size:26px;font-weight:600;margin:0 0 12px">That page doesn't exist.</h1>
<p style="color:#34505F;font-size:15.5px;line-height:1.6">But the agent on the
<a href="/" style="color:#C1731A;font-weight:600;text-decoration:none;border-bottom:1px solid #E8912A">home page</a>
is good at finding what you actually needed.</p>
</div></body></html>""", 404, {"Content-Type": "text/html; charset=utf-8"})


@app.get("/api/health")
def health():
    return {"ok": True, "service": "efc-site", "agent": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
