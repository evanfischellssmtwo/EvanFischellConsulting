"""Evan Fischell Consulting — public landing site + embedded agent (efc-site)."""
import json
import re
import secrets as pysecrets
import time
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory

app = Flask(__name__)

CANONICAL_HOST = "evanfischellconsulting.com"
REDIRECT_HOSTS = {
    "evanfischell.com",
    "www.evanfischell.com",
    "www.evanfischellconsulting.com",
}

MODEL = "gemini-3.1-pro-preview"
CHAT_DAILY_CAP = 200
PAGE_DAILY_CAP = 15
MAX_TURNS = 16
MAX_MSG_CHARS = 2000
MAX_PAGES_STORED = 100

_usage = {"day": None, "chat": 0, "page": 0}
_pages = {}  # id -> {"html": str, "ts": float}
_kb_cache = None


def _kb():
    global _kb_cache
    if _kb_cache is None:
        _kb_cache = (Path(app.root_path) / "kb.md").read_text(encoding="utf-8")
    return _kb_cache


def _spend(kind, cap):
    today = time.strftime("%Y-%m-%d")
    if _usage["day"] != today:
        _usage.update(day=today, chat=0, page=0)
    if _usage[kind] >= cap:
        return False
    _usage[kind] += 1
    return True


def _client():
    from google import genai
    return genai.Client()  # reads GEMINI_API_KEY from env


CHAT_PROTOCOL = """

## Response protocol (strict)
Respond with ONLY a JSON object: {"reply": "<your message to the visitor>",
"action": null}. When — and only when — the visitor has clearly agreed to have
a custom one-page brief created, set "action" to {"type": "create_page",
"brief": "<one paragraph describing the visitor's role, situation, and what
the page should cover>"} and keep "reply" short (tell them the page is being
prepared). Keep replies under 160 words. Plain text only in reply — no markdown
headings, no bullets unless brief.
"""

PAGE_SYS = """You generate a single, complete, self-contained HTML page — a
custom one-page brief from Evan Fischell Consulting, tailored to the visitor
brief you are given. Rules: one file, no external resources (no fonts, images,
scripts); inline CSS only. Brand: ink #0F2233 (header/footer bands, headline
text), slate #34505F body text, paper #F4F7F9 background, amber #E8912A used
sparingly (a 44px×2px rule, key numbers, the period after headlines); font
stack: 'IBM Plex Sans','Segoe UI',system-ui,sans-serif. Structure: ink header
band with the wordmark "Evan Fischell Consulting." (Consulting in font-weight
300, the period in amber) and a tailored headline ending in an amber period;
2–4 short sections grounded ONLY in the company facts below; an ink footer with
contact evan@evanfischellconsulting.com. Include <meta name="robots"
content="noindex, nofollow">. Stay strictly within the company facts — no
pricing, no client names, no certifications, no guarantees. Output ONLY the
HTML document, no code fences.

## Company facts
""" + ""


@app.before_request
def canonicalize():
    host = (request.host or "").split(":")[0].lower()
    if host in REDIRECT_HOSTS:
        path = request.full_path if request.query_string else request.path
        return redirect(f"https://{CANONICAL_HOST}{path}", code=301)
    return None


@app.get("/")
def index():
    return send_from_directory(app.root_path, "index.html")


@app.get("/deck")
def deck():
    # Unlisted: nothing links here; the page carries noindex. Deployed copy of
    # brand/PITCH-DECK.html (canonical) — re-copy on each deploy.
    return send_from_directory(app.root_path, "deck.html")


@app.post("/api/agent/chat")
def agent_chat():
    if not _spend("chat", CHAT_DAILY_CAP):
        return jsonify({"reply": "I've hit my conversation limit for today — "
                        "please reach Evan directly at evan@evanfischellconsulting.com.",
                        "action": None})
    data = request.get_json(silent=True) or {}
    msgs = data.get("messages") or []
    if not isinstance(msgs, list) or not msgs:
        return jsonify({"error": "messages required"}), 400
    contents = []
    for m in msgs[-MAX_TURNS:]:
        role = "user" if m.get("role") == "user" else "model"
        text = str(m.get("text") or "")[:MAX_MSG_CHARS]
        contents.append({"role": role, "parts": [{"text": text}]})
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
        raw = (resp.text or "").strip()
        out = None
        for candidate in (raw, raw + "}", raw + "}}"):
            try:
                out = json.loads(candidate)
                break
            except Exception:
                continue
        if out is None:
            m = re.search(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.S)
            if m:
                out = {"reply": json.loads('"' + m.group(1) + '"'), "action": None}
            else:
                m = re.search(r"\{.*\}", raw, re.S)
                out = json.loads(m.group(0)) if m else {"reply": raw, "action": None}
        reply = str(out.get("reply") or "").strip() or (
            "Sorry — I lost my train of thought. Try again?")
        action = out.get("action") if isinstance(out.get("action"), dict) else None
        if action and action.get("type") != "create_page":
            action = None
        return jsonify({"reply": reply, "action": action})
    except Exception:
        return jsonify({"reply": "Something went wrong on my end. You can always "
                        "reach Evan at evan@evanfischellconsulting.com.",
                        "action": None})


@app.post("/api/agent/page")
def agent_page():
    if not _spend("page", PAGE_DAILY_CAP):
        return jsonify({"error": "page limit reached for today"}), 429
    data = request.get_json(silent=True) or {}
    brief = str(data.get("brief") or "").strip()[:2000]
    if not brief:
        return jsonify({"error": "brief required"}), 400
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
        if "<html" not in html.lower():
            return jsonify({"error": "generation failed"}), 502
        pid = pysecrets.token_urlsafe(8)
        if len(_pages) >= MAX_PAGES_STORED:
            oldest = min(_pages, key=lambda k: _pages[k]["ts"])
            _pages.pop(oldest, None)
        _pages[pid] = {"html": html, "ts": time.time()}
        return jsonify({"id": pid, "url": f"/p/{pid}"})
    except Exception:
        return jsonify({"error": "generation failed"}), 502


@app.get("/p/<pid>")
def page(pid):
    entry = _pages.get(pid)
    if not entry:
        return ("This page has expired. Ask the agent on the home page to "
                "make you a fresh one."), 404
    return entry["html"], 200, {"Content-Type": "text/html; charset=utf-8",
                                "X-Robots-Tag": "noindex, nofollow"}


@app.get("/api/health")
def health():
    return {"ok": True, "service": "efc-site", "agent": True,
            "usage": {k: _usage[k] for k in ("day", "chat", "page")}}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
