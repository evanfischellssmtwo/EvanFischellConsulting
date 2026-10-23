"""The two things the embedded agent can do besides talk.

Both the chat endpoint and the agent's MCP tool server (``agent_tools_mcp.py``)
validate actions here, so a tool call the model makes and an action the server
carries out can never disagree about what is allowed.

The Antigravity CLI hands MCP tools to the model through a generic wrapper
without their schemas, so the model sometimes guesses argument names
(``feedback`` for ``note``, ``request`` for ``brief``). The aliases below accept
those guesses instead of failing the visitor's turn.
"""

MAX_BRIEF_CHARS = 2000
MAX_FEEDBACK_CHARS = 2000
MAX_ABOUT_CHARS = 200

_ALIASES = {
    "note": ("note", "feedback", "text", "comment", "message", "content"),
    "about": ("about", "section", "topic", "subject", "element"),
    "brief": ("brief", "description", "request", "prompt", "topic", "text"),
}


def _first_text(arguments, field):
    for key in _ALIASES[field]:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize(kind, arguments):
    """Return a validated action dict, or ``None`` when the call is unusable."""
    if not isinstance(arguments, dict):
        return None
    if kind in ("create_page", "build_page"):
        brief = _first_text(arguments, "brief")
        if brief:
            return {"type": "create_page", "brief": brief[:MAX_BRIEF_CHARS]}
    elif kind == "save_feedback":
        note = _first_text(arguments, "note")
        if note:
            return {
                "type": "save_feedback",
                "note": note[:MAX_FEEDBACK_CHARS],
                "about": _first_text(arguments, "about")[:MAX_ABOUT_CHARS],
            }
    return None


def describe_missing(kind):
    """The tool error text the model sees when a call lacks its main argument."""
    if kind == "save_feedback":
        return 'Not saved: pass the visitor\'s point as "note" (and optionally "about").'
    if kind in ("create_page", "build_page"):
        return 'Not started: pass a one-paragraph description of the page as "brief".'
    return "Unknown tool."
