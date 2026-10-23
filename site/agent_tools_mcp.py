"""Stdio MCP server that gives the embedded agent its two site tools.

The Antigravity CLI starts this process for each chat turn (see
``agent_runtime.py``). It does not carry out the actions itself: it validates
the call, appends the accepted action as one JSON line to the file named by
``EFC_ACTIONS_FILE``, and tells the model what happened. The web process reads
that file and does the real work (saving feedback, building the page), so
this server needs no credentials and no network.

Only the JSON-RPC methods the CLI uses are implemented: ``initialize``,
``tools/list``, ``tools/call`` and the notifications, which need no reply.
"""

import json
import os
import sys

from site_actions import describe_missing, normalize

PROTOCOL_VERSION = "2025-06-18"

TOOLS = [
    {
        "name": "save_feedback",
        "description": "Record a visitor's feedback, critique or correction about the site or the resume so Evan can read it later.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "The visitor's point, in their own words."},
                "about": {"type": "string", "description": "The part of the site it concerns."},
            },
            "required": ["note"],
        },
    },
    {
        "name": "create_page",
        "description": "Start building a one-page web page for the visitor. The page appears in the chat when it is ready.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "brief": {"type": "string", "description": "One paragraph describing what the page should be and cover."},
            },
            "required": ["brief"],
        },
    },
]
TOOL_NAMES = {tool["name"] for tool in TOOLS}


def _reply(message_id, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": message_id}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result if result is not None else {}
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _text_result(text, is_error=False):
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _record(action):
    path = os.environ.get("EFC_ACTIONS_FILE")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(action) + "\n")


def handle_call(params):
    """Validate one ``tools/call`` and return its MCP result."""
    name = params.get("name")
    if name not in TOOL_NAMES:
        return _text_result("Unknown tool.", is_error=True)
    action = normalize(name, params.get("arguments") or {})
    if action is None:
        return _text_result(describe_missing(name), is_error=True)
    _record(action)
    if action["type"] == "save_feedback":
        return _text_result("Saved. Evan will read it.")
    return _text_result("The page is being built. It will appear in the chat in about half a minute.")


def main():
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        message_id, method = message.get("id"), message.get("method")
        if message_id is None:
            continue  # notifications need no answer
        if method == "initialize":
            requested = (message.get("params") or {}).get("protocolVersion")
            _reply(message_id, {
                "protocolVersion": requested or PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "efc-site", "version": "1.0"},
            })
        elif method == "tools/list":
            _reply(message_id, {"tools": TOOLS})
        elif method == "tools/call":
            _reply(message_id, handle_call(message.get("params") or {}))
        elif method == "ping":
            _reply(message_id, {})
        else:
            _reply(message_id, error={"code": -32601, "message": "Method not found"})


if __name__ == "__main__":
    main()
