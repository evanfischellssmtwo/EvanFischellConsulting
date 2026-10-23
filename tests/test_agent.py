import importlib.util
import json
import os
import shlex
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).parents[1]
SITE = ROOT / "site"
sys.path.insert(0, str(SITE))
import agent_runtime
import agent_tools_mcp

spec = importlib.util.spec_from_file_location("efc_agent_test_app", SITE / "app.py")
efc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(efc)


@pytest.fixture
def client():
    efc.app.config.update(TESTING=True)
    return efc.app.test_client()


@pytest.fixture(autouse=True)
def reset_app_state():
    # Loading app.py by file location leaves Flask's root at the repository;
    # the app's knowledge file and other assets live beside app.py in site/.
    efc.app.root_path = str(SITE)
    efc._kb_cache = None
    efc._usage.update(day=None, chat=0, page=0, feedback=0)
    efc._pages.clear()
    efc._feedback_mem.clear()
    efc.FEEDBACK_BUCKET = ""


@pytest.fixture
def stub_agy(tmp_path, monkeypatch):
    stub = Path(__file__).with_name("stub_agy.py")
    launcher = tmp_path / ("agy.cmd" if os.name == "nt" else "agy")
    if os.name == "nt":
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{stub}" %*\r\n', encoding="utf-8"
        )
    else:
        launcher.write_text(
            "#!/bin/sh\nexec " + shlex.quote(sys.executable) + " " + shlex.quote(str(stub)) + " \"$@\"\n",
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    monkeypatch.setattr(agent_runtime, "AGY_BIN", str(launcher))
    monkeypatch.setattr(agent_runtime, "STATE_ROOT", tmp_path / "runtime")
    monkeypatch.setattr(agent_runtime, "_prepared_for", None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("FEEDBACK_KEY", raising=False)
    return launcher


def contents(text, *, role="user"):
    return [{"role": role, "parts": [{"text": text}]}]


def test_stream_turn_yields_text_deltas_and_joined_reply(stub_agy):
    events = list(agent_runtime.stream_turn(contents("SCENARIO: plain"), "test instructions"))
    assert [event["delta"] for event in events if event["type"] == "text"] == ["Hello ", "there"]
    assert events[-1]["type"] == "done"
    assert events[-1]["reply"] == "Hello there"


def test_stream_turn_reports_feedback_tool_and_action(stub_agy):
    events = list(agent_runtime.stream_turn(contents("SCENARIO: feedback"), "test instructions"))
    tool_events = [event for event in events if event["type"] == "tool"]
    assert [(event["status"], event["label"]) for event in tool_events] == [
        ("running", "Saving your note for Evan"), ("done", "Saved for Evan"),
    ]
    assert {"type": "action", "action": {
        "type": "save_feedback", "note": "Make the headline clearer", "about": "home page",
    }} in events


def test_stream_turn_rejects_forbidden_tool(stub_agy):
    with pytest.raises(agent_runtime.ForbiddenTool):
        list(agent_runtime.stream_turn(contents("SCENARIO: forbidden"), "test instructions"))


def test_prepare_writes_lockdown_profile_and_mcp_config(stub_agy):
    agent_runtime.prepare("Private test rules")
    home = agent_runtime.STATE_ROOT / "home" / ".gemini"
    profile = home / "config" / "agents" / "efc-concierge" / "agent.md"
    config = home / "config" / "mcp_config.json"
    settings = home / "antigravity-cli" / "settings.json"
    assert "tools: []" in profile.read_text(encoding="utf-8")
    assert "commandExecutionPolicy: off" in profile.read_text(encoding="utf-8")
    assert "efc-site" in json.loads(config.read_text(encoding="utf-8"))["mcpServers"]
    assert "command(*)" in json.loads(settings.read_text(encoding="utf-8"))["permissions"]["deny"]


def test_child_environment_does_not_include_unrelated_secret(stub_agy, monkeypatch):
    monkeypatch.setenv("FEEDBACK_KEY", "secret-that-must-not-cross-process-boundary")
    list(agent_runtime.stream_turn(contents("SCENARIO: plain"), "test instructions"))
    snapshots = list((agent_runtime.STATE_ROOT).glob("*.envkeys"))
    assert len(snapshots) == 1
    child_keys = snapshots[0].read_text(encoding="utf-8").splitlines()
    assert "GEMINI_API_KEY" in child_keys
    assert "EFC_ACTIONS_FILE" in child_keys
    assert "FEEDBACK_KEY" not in child_keys


def test_stream_endpoint_emits_ndjson_and_saves_feedback(client, stub_agy):
    response = client.post("/api/agent/stream", json={
        "messages": [{"role": "user", "text": "SCENARIO: feedback"}],
    })
    lines = [json.loads(line) for line in response.get_data(as_text=True).splitlines()]
    assert response.status_code == 200
    assert response.mimetype == "application/x-ndjson"
    assert lines[-1]["type"] == "done"
    saved = efc._list_feedback()
    assert len(saved) == 1
    assert saved[0]["note"] == "Make the headline clearer"


def test_chat_endpoint_returns_create_page_action(client, stub_agy):
    response = client.post("/api/agent/chat", json={
        "messages": [{"role": "user", "text": "SCENARIO: page"}],
    })
    assert response.status_code == 200
    assert response.json == {
        "reply": "I'll start that page.",
        "action": {"type": "create_page", "brief": "A page about sustainable gardens"},
    }


def test_unavailable_agy_uses_fallback_events(client, tmp_path, monkeypatch):
    monkeypatch.setattr(agent_runtime, "AGY_BIN", str(tmp_path / "missing-agy"))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class FakeModels:
        @staticmethod
        def generate_content(**kwargs):
            return SimpleNamespace(text='{"reply":"fallback ok","action":null}')

    monkeypatch.setattr(efc, "_client", lambda: SimpleNamespace(models=FakeModels()))
    response = client.post("/api/agent/chat", json={
        "messages": [{"role": "user", "text": "Hello"}],
    })
    assert response.status_code == 200
    assert response.json == {"reply": "fallback ok", "action": None}


def test_prior_agent_role_is_accepted(client, stub_agy):
    response = client.post("/api/agent/chat", json={"messages": [
        {"role": "user", "text": "Earlier question"},
        {"role": "agent", "text": "Earlier answer"},
        {"role": "user", "text": "SCENARIO: plain"},
    ]})
    assert response.status_code == 200
    assert response.json["reply"] == "Hello there"


def test_mcp_handle_call_accepts_alias_and_records_action(tmp_path, monkeypatch):
    actions = tmp_path / "actions.jsonl"
    monkeypatch.setenv("EFC_ACTIONS_FILE", str(actions))
    result = agent_tools_mcp.handle_call({
        "name": "save_feedback", "arguments": {"feedback": "Please simplify this", "about": "resume"},
    })
    assert result["isError"] is False
    assert json.loads(actions.read_text(encoding="utf-8")) == {
        "type": "save_feedback", "note": "Please simplify this", "about": "resume",
    }


def test_mcp_handle_call_rejects_missing_note(tmp_path, monkeypatch):
    monkeypatch.setenv("EFC_ACTIONS_FILE", str(tmp_path / "actions.jsonl"))
    result = agent_tools_mcp.handle_call({"name": "save_feedback", "arguments": {"about": "resume"}})
    assert result["isError"] is True
    assert not (tmp_path / "actions.jsonl").exists()


def test_failed_result_without_text_raises(stub_agy):
    with pytest.raises(RuntimeError, match="agy turn ended ERROR"):
        list(agent_runtime.stream_turn(contents("SCENARIO: failed result"), "test instructions"))


def test_exit_without_result_raises(stub_agy):
    with pytest.raises(RuntimeError, match="agy exited without a result"):
        list(agent_runtime.stream_turn(contents("SCENARIO: no result"), "test instructions"))


def test_invalid_stream_request_does_not_consume_quota(client, stub_agy):
    response = client.post("/api/agent/stream", json={"messages": []})
    assert response.status_code == 400
    assert efc._usage["chat"] == 0
