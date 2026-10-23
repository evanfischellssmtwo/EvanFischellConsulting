"""Small scripted stand-in for the Antigravity CLI used by test_agent.py."""

import json
import os
import sys
from pathlib import Path


def emit(event):
    print(json.dumps(event), flush=True)


def tool_step(state, tool_name="call_mcp_tool", *, name="save_feedback", arguments=None,
              output=None):
    info = {"name": tool_name}
    if tool_name == "call_mcp_tool":
        info["parameters"] = {
            "Arguments": arguments or {}, "ServerName": "efc-site", "ToolName": name,
        }
        if output is not None:
            info["output"] = output
    return {"event": "step_update", "step_update": {
        "conversation_id": "stub-conversation", "step_index": 1, "state": state,
        "step_type": "tool", "tool_name": tool_name, "tool_info": info,
    }}


def main():
    request = json.loads(sys.stdin.readline())
    prompt = request["message"]["content"][0]["text"]
    actions_path = Path(os.environ["EFC_ACTIONS_FILE"])
    # Store names only, so the parent can verify environment scrubbing without
    # ever copying values from the child's environment.
    actions_path.with_suffix(".envkeys").write_text(
        "\n".join(sorted(os.environ)), encoding="utf-8"
    )
    emit({"event": "init", "conversation_id": "stub-conversation", "init": {
        "model": "gemini-3.8-flash", "tools": [], "permission_mode": "request-review",
    }})

    if "SCENARIO: forbidden" in prompt:
        emit(tool_step("ACTIVE", "run_command", name="run_command"))
        return
    if "SCENARIO: feedback" in prompt:
        action = {"type": "save_feedback", "note": "Make the headline clearer", "about": "home page"}
        with actions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(action) + "\n")
        emit(tool_step("ACTIVE", arguments={"note": action["note"], "about": action["about"]}))
        emit(tool_step("DONE", arguments={"note": action["note"], "about": action["about"]},
                       output="Saved. Evan will read it."))
        emit({"event": "result", "result": {"conversation_id": "stub-conversation",
              "status": "SUCCESS", "response": "I saved that feedback.", "num_turns": 1}})
        return
    if "SCENARIO: page" in prompt:
        action = {"type": "create_page", "brief": "A page about sustainable gardens"}
        with actions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(action) + "\n")
        emit(tool_step("ACTIVE", name="create_page", arguments={"brief": action["brief"]}))
        emit(tool_step("DONE", name="create_page", arguments={"brief": action["brief"]},
                       output="The page is being built."))
        emit({"event": "result", "result": {"conversation_id": "stub-conversation",
              "status": "SUCCESS", "response": "I'll start that page.", "num_turns": 1}})
        return
    if "SCENARIO: failed result" in prompt:
        emit({"event": "result", "result": {"conversation_id": "stub-conversation",
              "status": "ERROR", "response": "", "num_turns": 1}})
        return
    if "SCENARIO: no result" in prompt:
        return

    for delta in ("Hello ", "there"):
        emit({"event": "step_update", "step_update": {
            "conversation_id": "stub-conversation", "step_index": 1,
            "state": "ACTIVE", "step_type": "agent_response", "text_delta": delta,
        }})
    emit({"event": "result", "result": {"conversation_id": "stub-conversation",
          "status": "SUCCESS", "response": "Hello there", "num_turns": 1}})


if __name__ == "__main__":
    main()
