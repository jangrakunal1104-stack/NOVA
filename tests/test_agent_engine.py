"""
Tests for core.agent_engine.AgentEngine -- the tool-call loop that powers
Agent Mode. Uses a scripted fake generate_fn (no real model needed) and
monkeypatches core.agent_tools' actual read_file/write_file/run_shell so
nothing here touches a real filesystem or shell.
"""
import json

import pytest

from core import agent_tools
from core.agent_engine import AgentEngine, MAX_TOOL_CALLS_PER_TURN


def _tool_call_text(name, **arguments):
    return f'<tool_call>\n{json.dumps({"name": name, "arguments": arguments})}\n</tool_call>'


def test_no_tool_call_returns_final_immediately():
    replies = iter(["Just a normal answer, no tools needed."])
    engine = AgentEngine(lambda messages: next(replies), lambda kind, summary: True)

    steps = []
    engine.run([{"role": "user", "content": "hi"}], steps.append)

    assert len(steps) == 1
    assert steps[0].kind == "final"
    assert "normal answer" in steps[0].text


def test_read_only_tool_call_does_not_need_approval(monkeypatch):
    monkeypatch.setattr(
        agent_tools, "list_dir",
        lambda path=".": agent_tools.ToolResult(True, "file: a.txt"),
    )

    replies = iter([_tool_call_text("list_dir", path="."), "Found a.txt in there."])
    approvals_asked = []
    engine = AgentEngine(
        lambda m: next(replies),
        lambda kind, summary: approvals_asked.append(kind) or True,
    )

    steps = []
    engine.run([{"role": "user", "content": "what's in my folder?"}], steps.append)

    assert approvals_asked == []
    assert [s.kind for s in steps] == ["tool_call", "tool_result", "final"]
    assert "a.txt" in steps[1].text


def test_write_file_requires_approval_and_is_denied(monkeypatch):
    write_calls = []
    monkeypatch.setattr(
        agent_tools, "write_file",
        lambda path, content: write_calls.append(path) or agent_tools.ToolResult(True, "wrote it"),
    )

    replies = iter([_tool_call_text("write_file", path="notes.txt", content="hi"), "Done."])
    engine = AgentEngine(lambda m: next(replies), lambda kind, summary: False)  # always deny

    steps = []
    engine.run([{"role": "user", "content": "save a note"}], steps.append)

    assert write_calls == [], "write_file must not actually run once approval is denied"
    tool_result = [s for s in steps if s.kind == "tool_result"][0]
    assert "Denied by user" in tool_result.text


def test_write_file_approved_actually_runs(monkeypatch):
    write_calls = []
    monkeypatch.setattr(
        agent_tools, "write_file",
        lambda path, content: write_calls.append((path, content)) or agent_tools.ToolResult(True, "wrote it"),
    )

    replies = iter([_tool_call_text("write_file", path="notes.txt", content="hi"), "Saved it."])
    engine = AgentEngine(lambda m: next(replies), lambda kind, summary: True)  # always approve

    steps = []
    engine.run([{"role": "user", "content": "save a note"}], steps.append)

    assert write_calls == [("notes.txt", "hi")]


def test_unsafe_shell_command_requires_approval(monkeypatch):
    monkeypatch.setattr(
        agent_tools, "run_shell",
        lambda command, cwd=None: agent_tools.ToolResult(True, "done"),
    )

    replies = iter([_tool_call_text("run_shell", command="rm -rf ~/junk"), "ok"])
    asked = []
    engine = AgentEngine(
        lambda m: next(replies),
        lambda kind, summary: asked.append((kind, summary)) or True,
    )

    steps = []
    engine.run([{"role": "user", "content": "clean up"}], steps.append)

    assert len(asked) == 1
    assert asked[0][0] == "run_shell"


def test_safe_shell_command_skips_approval(monkeypatch):
    monkeypatch.setattr(
        agent_tools, "run_shell",
        lambda command, cwd=None: agent_tools.ToolResult(True, "total 0"),
    )

    replies = iter([_tool_call_text("run_shell", command="ls -la"), "Listed it."])
    asked = []
    engine = AgentEngine(lambda m: next(replies), lambda kind, summary: asked.append(kind) or True)

    steps = []
    engine.run([{"role": "user", "content": "list my files"}], steps.append)

    assert asked == []


def test_loop_stops_at_max_tool_calls_to_prevent_runaway(monkeypatch):
    monkeypatch.setattr(
        agent_tools, "list_dir",
        lambda path=".": agent_tools.ToolResult(True, "..."),
    )

    def always_tool_call(messages):
        return _tool_call_text("list_dir", path=".")

    steps = []
    engine = AgentEngine(always_tool_call, lambda kind, summary: True)
    engine.run([{"role": "user", "content": "loop forever"}], steps.append)

    tool_calls = [s for s in steps if s.kind == "tool_call"]
    assert len(tool_calls) == MAX_TOOL_CALLS_PER_TURN
    assert steps[-1].kind == "final"
    assert "Stopped after" in steps[-1].text


def test_unknown_tool_name_reports_error_without_crashing():
    replies = iter([_tool_call_text("delete_everything", path="/"), "oops"])
    engine = AgentEngine(lambda m: next(replies), lambda kind, summary: True)

    steps = []
    engine.run([{"role": "user", "content": "do something"}], steps.append)

    tool_result = [s for s in steps if s.kind == "tool_result"][0]
    assert "Unknown tool" in tool_result.text


def test_malformed_tool_call_json_is_treated_as_final_answer():
    # A broken/incomplete <tool_call> block must not crash the loop --
    # treat it as a (garbled) final answer rather than retrying forever.
    replies = iter(["<tool_call>\nnot valid json at all\n</tool_call>"])
    engine = AgentEngine(lambda m: next(replies), lambda kind, summary: True)

    steps = []
    engine.run([{"role": "user", "content": "hi"}], steps.append)

    assert len(steps) == 1
    assert steps[0].kind == "final"


def test_nested_json_arguments_are_parsed_correctly(monkeypatch):
    # Regression: the tool-call extractor used to use a non-greedy regex
    # that stopped at the FIRST closing brace, which is the inner
    # "arguments" object's brace, not the outer one -- producing
    # truncated/invalid JSON for every call with more than zero
    # arguments. Brace-balancing fixed it; this locks the fix in.
    seen_args = []
    monkeypatch.setattr(
        agent_tools, "write_file",
        lambda path, content: seen_args.append((path, content)) or agent_tools.ToolResult(True, "ok"),
    )

    replies = iter([
        _tool_call_text("write_file", path="a.txt", content='has {curly braces} and "quotes" inside'),
        "done",
    ])
    engine = AgentEngine(lambda m: next(replies), lambda kind, summary: True)

    steps = []
    engine.run([{"role": "user", "content": "write something with braces in it"}], steps.append)

    assert seen_args == [("a.txt", 'has {curly braces} and "quotes" inside')]
