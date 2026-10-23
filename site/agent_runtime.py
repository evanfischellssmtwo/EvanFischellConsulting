"""Runs the embedded agent through the Antigravity CLI on Gemini 3.8 Flash.

One chat turn is one ``agy`` process: the visitor's conversation goes in as a
single stream-json frame on standard input, and the CLI's stream-json output is
translated into the small event vocabulary the chat drawer renders (``text``,
``tool``, ``done``, ``error``). The site keeps no conversation state on the
server; the drawer sends the whole (short) conversation with every message.

Lockdown, because anyone on the internet can talk to this agent:

- The agent profile (``efc-concierge``) declares ``tools: []`` and
  ``commandExecutionPolicy: off``. Measured with the CLI: the model is then
  offered no terminal, file, browser or web tool at all, not merely told to
  avoid them.
- Its only reach outside the conversation is the site's own MCP server
  (``agent_tools_mcp.py``), which validates every call and records the action
  for this process to carry out.
- The process gets a scrubbed environment (PATH, HOME, locale, the Gemini key
  and the CLI's own switches), an empty working directory and a private HOME
  under /tmp. Feedback keys, bucket names and every other variable of the web
  process stay out of it.

Authentication is the Gemini API key the service already holds
(``GEMINI_API_KEY``); the CLI has a dedicated API-key mode, so no Google Cloud
role is needed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from site_actions import normalize

AGENT_NAME = "efc-concierge"
MCP_SERVER_NAME = "efc-site"
AGY_BIN = os.getenv("EFC_AGY_BIN", "agy")
AGY_MODEL = os.getenv("EFC_AGY_MODEL", "gemini-3.8-flash")
AGY_EFFORT = os.getenv("EFC_AGY_EFFORT", "low")
TURN_TIMEOUT_SECONDS = int(os.getenv("EFC_AGY_TIMEOUT", "75"))
STATE_ROOT = Path(os.getenv("EFC_AGY_STATE", os.path.join(tempfile.gettempdir(), "efc-agy")))

# Shown on tool rows in the drawer while the step runs and after it ends.
TOOL_LABELS = {
    "save_feedback": ("Saving your note for Evan", "Saved for Evan", "Could not save the note"),
    "create_page": ("Starting your page", "Page started", "Could not start the page"),
}

# Windows names are only for running the agent on a workstation during
# development; on Cloud Run they are absent.
_PASSTHROUGH_ENV = ("PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT", "TEMP", "TMP",
                    "APPDATA", "LOCALAPPDATA", "USERNAME")

# The CLI's own permission policy, a second lock behind the profile's empty tool
# list: every built-in action is denied and only this site's MCP server is
# allowed to run without asking. Deny outranks allow. (Measured: the "strict"
# toolPermission mode denies even allowed MCP calls in a headless run, so the
# CLI's default review mode is kept and the rules below decide.)
PERMISSIONS = {
    "permissions": {
        "deny": ["command(*)", "read_file(*)", "write_file(*)", "read_url(*)", "execute_url(*)"],
        "allow": [f"mcp({MCP_SERVER_NAME}/*)"],
    },
}

EMPTY_REPLY = ("I didn't manage a proper answer to that. Could you try again, or "
               "write to Evan at evan@evanfischellconsulting.com?")

# Tool steps that are part of the CLI's own bookkeeping rather than an action.
_HARMLESS_TOOLS = {"manage_task"}


class ForbiddenTool(RuntimeError):
    """The model reached a tool outside the site's MCP server; the turn is killed."""

_setup_lock = threading.Lock()
_prepared_for = None


def available():
    """True when the CLI is installed and has a key to run with."""
    return bool(os.environ.get("GEMINI_API_KEY")) and shutil.which(AGY_BIN) is not None


def _home():
    return STATE_ROOT / "home"


def _workspace():
    return STATE_ROOT / "workspace"


def _profile_text(instructions):
    header = "\n".join([
        "---",
        f"name: {AGENT_NAME}",
        "description: Public concierge for the Evan Fischell Consulting website.",
        "tools: []",
        "mainAgent: true",
        "subagent: false",
        "model: inherit",
        "inheritCustomizations: false",
        "inheritMcp: true",
        "commandExecutionPolicy: off",
        "skills: []",
        "---",
        "",
    ])
    return header + instructions.strip() + "\n"


def prepare(instructions):
    """Write the private HOME (agent profile + MCP config) once per instruction text."""
    global _prepared_for
    with _setup_lock:
        if _prepared_for == instructions:
            return
        config = _home() / ".gemini" / "config"
        agent_dir = config / "agents" / AGENT_NAME
        agent_dir.mkdir(parents=True, exist_ok=True)
        _workspace().mkdir(parents=True, exist_ok=True)
        (agent_dir / "agent.md").write_text(_profile_text(instructions), encoding="utf-8")
        server = Path(__file__).with_name("agent_tools_mcp.py")
        mcp = {"mcpServers": {MCP_SERVER_NAME: {
            "command": sys.executable,
            # -E and -s keep the tool server off the web process's Python
            # settings; the script directory stays importable for site_actions.
            "args": ["-E", "-s", str(server)],
        }}}
        (config / "mcp_config.json").write_text(json.dumps(mcp, indent=2), encoding="utf-8")
        cli = _home() / ".gemini" / "antigravity-cli"
        cli.mkdir(parents=True, exist_ok=True)
        (cli / "settings.json").write_text(json.dumps(PERMISSIONS, indent=2), encoding="utf-8")
        _prepared_for = instructions


def _environment(actions_file):
    env = {key: os.environ[key] for key in _PASSTHROUGH_ENV if key in os.environ}
    home = str(_home())
    env.update({
        "HOME": home,
        "USERPROFILE": home,

        "AGY_CLI_DISABLE_AUTO_UPDATE": "true",
        "NO_COLOR": "1",
        "EFC_ACTIONS_FILE": actions_file,
    })
    if os.environ.get("GEMINI_API_KEY"):
        env["GEMINI_API_KEY"] = os.environ["GEMINI_API_KEY"]
    return env


def render_prompt(contents):
    """Flatten the conversation into the one user frame the CLI receives."""
    *earlier, latest = contents
    lines = []
    if earlier:
        lines.append("Conversation so far:")
        for message in earlier:
            who = "Visitor" if message["role"] == "user" else "You"
            lines.append(f"{who}: {message['parts'][0]['text']}")
        lines.append("")
        lines.append("The visitor's new message:")
    lines.append(latest["parts"][0]["text"])
    return "\n".join(lines)


def _tool_event(step, state):
    info = step.get("tool_info") or {}
    params = info.get("parameters") or {}
    name = params.get("ToolName") if info.get("name") == "call_mcp_tool" else info.get("name")
    running, finished, failed = TOOL_LABELS.get(name, ("Working", "Done", "Step failed"))
    status = {"ACTIVE": "running", "DONE": "done"}.get(state, "failed")
    output = str(info.get("output") or "")
    if status == "done" and (info.get("error") or output.startswith(("Not ", "Unknown tool"))):
        status = "failed"
    label = {"running": running, "done": finished, "failed": failed}[status]
    return {"type": "tool", "id": str(step.get("step_index")), "tool": name or "tool",
            "status": status, "label": label}


def _read_actions(path, seen):
    """Return actions the tool server recorded since the last read."""
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except FileNotFoundError:
        return []
    fresh = []
    for line in lines[seen[0]:]:
        try:
            action = json.loads(line)
        except json.JSONDecodeError:
            continue
        action = normalize(action.get("type"), action) if isinstance(action, dict) else None
        if action:
            fresh.append(action)
    seen[0] = len(lines)
    return fresh


def _cleanup_conversation(conversation_id):
    if not conversation_id or not conversation_id.replace("-", "").isalnum():
        return
    cli = _home() / ".gemini" / "antigravity-cli"
    for folder in (cli / "brain" / conversation_id, cli / "conversations" / conversation_id):
        shutil.rmtree(folder, ignore_errors=True)


def stream_turn(contents, instructions):
    """Run one turn and yield drawer events. Raises ``RuntimeError`` before any
    output if the CLI could not start, so the caller can fall back."""
    prepare(instructions)
    actions_file = str(STATE_ROOT / f"actions-{uuid.uuid4().hex}.jsonl")
    command = [
        AGY_BIN, "--agent", AGENT_NAME, "--model", AGY_MODEL, "--effort", AGY_EFFORT,
        "--disable-slash-commands",
        "--print-timeout", f"{TURN_TIMEOUT_SECONDS}s",
        "--output-format", "stream-json", "--input-format", "stream-json", "--print", "",
    ]
    frame = {"event": "user", "type": "user", "message": {
        "role": "user", "content": [{"type": "text", "text": render_prompt(contents)}]}}
    try:
        process = subprocess.Popen(
            command, cwd=str(_workspace()), env=_environment(actions_file),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except OSError as exc:
        raise RuntimeError(f"agy did not start: {exc}") from exc

    stderr_tail = []
    threading.Thread(target=lambda: stderr_tail.extend(process.stderr.readlines()[-20:]),
                     daemon=True).start()
    timer = threading.Timer(TURN_TIMEOUT_SECONDS + 10, process.kill)
    timer.start()
    process.stdin.write(json.dumps(frame) + "\n")
    process.stdin.close()

    seen, text, conversation_id, last_text_step = [0], [], None, None
    started = time.monotonic()
    finished = False
    try:
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = event.get("event")
            if kind == "init":
                conversation_id = event.get("conversation_id")
            elif kind == "step_update":
                step = event.get("step_update") or {}
                step_type, state = step.get("step_type"), step.get("state")
                if step_type == "agent_response" and step.get("text_delta"):
                    delta = step["text_delta"]
                    if last_text_step is not None and step.get("step_index") != last_text_step and text:
                        delta = "\n\n" + delta.lstrip()
                    last_text_step = step.get("step_index")
                    text.append(delta)
                    yield {"type": "text", "delta": delta}
                elif step_type == "tool":
                    info = step.get("tool_info") or {}
                    if info.get("name") in _HARMLESS_TOOLS:
                        continue
                    params = info.get("parameters") or {}
                    if info.get("name") != "call_mcp_tool" or params.get("ServerName") != MCP_SERVER_NAME:
                        process.kill()
                        raise ForbiddenTool(f"forbidden tool step: {info.get('name')} "
                                            f"{json.dumps(params)[:200]}")
                    yield _tool_event(step, state)
                    if state != "ACTIVE":
                        for action in _read_actions(actions_file, seen):
                            yield {"type": "action", "action": action}
            elif kind == "result":
                result = event.get("result") or {}
                finished = True
                for action in _read_actions(actions_file, seen):
                    yield {"type": "action", "action": action}
                if result.get("status") != "SUCCESS" and not text:
                    raise RuntimeError(f"agy turn ended {result.get('status')}")
                reply = "".join(text).strip() or str(result.get("response") or "").strip()
                if not reply:
                    reply = EMPTY_REPLY
                    yield {"type": "text", "delta": reply}
                yield {"type": "done", "reply": reply,
                       "seconds": round(time.monotonic() - started, 2)}
        process.wait(timeout=10)
        if not finished:
            raise RuntimeError("agy exited without a result: " + "".join(stderr_tail)[-500:])
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        try:
            os.remove(actions_file)
        except OSError:
            pass
        _cleanup_conversation(conversation_id)
