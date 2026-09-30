"""
core/agent_engine.py

"Agent Mode" for NOVA -- lets the model call tools (core/agent_tools.py)
in a loop instead of only answering in one shot: read files, list
directories, run shell commands, and write files (gated by approval),
scoped to the user's home directory.

This is a PROMPTED tool-call loop, not llama.cpp's native function-calling
grammar. nova_mrblack is a custom fine-tune and wasn't necessarily trained
on a specific tool-calling format, so this asks it, in plain system-prompt
instructions, to emit a `<tool_call>{...}</tool_call>` JSON block when it
wants to use a tool, and to just answer normally otherwise. How reliably
that's followed depends on the underlying model's instruction-following --
it is NOT guaranteed the way a model trained for tool use would be. Treat
early runs as a signal of whether the base model is strong enough for this
pattern, not as a finished, bulletproof feature. If the model frequently
ignores the format, drifts into chatting instead of calling a tool, or
hallucinates tool results instead of waiting for the real one, that's the
model, not a bug in this loop -- see AGENT_MODE section in README.md.
"""
import json
import re
from dataclasses import dataclass
from typing import Callable, List, Optional

from core import agent_tools

# Safety valve against a runaway loop (a confused model calling tools
# forever). Each call is a full model round-trip, so this also bounds how
# long one user turn can take.
MAX_TOOL_CALLS_PER_TURN = 8

_TOOL_CALL_START_RE = re.compile(r"<tool_call>\s*", re.DOTALL)

AGENT_SYSTEM_PROMPT = """You are Nova, running in AGENT MODE. In this mode you can use tools to \
read files, list directories, run shell commands, and write files on Mr. Black's computer, \
instead of only answering from what you already know.

Available tools:
{tool_list}

To use a tool, reply with EXACTLY this and nothing else:
<tool_call>
{{"name": "<tool name>", "arguments": {{...}}}}
</tool_call>

Rules:
- Call at most one tool per reply.
- After a tool runs, you will be shown its result as a new message. Use it to decide your next step.
- When you have enough information to fully answer, reply normally in plain text with NO \
<tool_call> block -- that is how the loop knows you are done. Do not describe a tool call in \
prose; either emit the block exactly, or give your final answer.
- Some actions need Mr. Black's approval before they run: writing any file, and most shell \
commands beyond a small read-only allowlist (ls, cat, grep, git status/diff/log, pytest, etc). \
If a tool result says approval was denied, do not repeat the same call -- adjust your plan or \
explain to Mr. Black what you needed and why.
- You may NEVER write directly into NOVA's own source code. If asked to improve NOVA itself, \
write your proposal into the self_improvement_proposals/ folder instead (a .md file explaining \
the issue and the fix, plus the proposed file content if it's a full rewrite) -- never edit \
NOVA's live files. write_file will refuse anyway if you try, but do not attempt it.
- Be concrete and efficient. Do not call a tool just to double-check something you were already told.
"""


def _format_tool_list() -> str:
    lines = []
    for name, spec in agent_tools.TOOL_SPECS.items():
        args = ", ".join(f"{k}: {v}" for k, v in spec["args"].items())
        lines.append(f"- {name}({args}): {spec['description']}")
    return "\n".join(lines)


@dataclass
class AgentStep:
    kind: str            # "tool_call" | "tool_result" | "final" | "info"
    text: str


class AgentEngine:
    """
    Drives the read -> decide -> (maybe call a tool) -> observe loop for
    one user turn. Knows nothing about Qt -- ui/agent_worker.py adapts
    this to a QThread + signals so it can pause for approval without
    freezing the GUI.
    """

    def __init__(self, generate_fn: Callable[[List[dict]], str], request_approval: Callable[[str, str], bool]):
        """
        generate_fn(messages) -> str: runs one full (non-streaming, from
            this loop's point of view) model turn and returns the
            complete reply text. Callers should route this through
            core.backend_router.BackendRouter.run_llm rather than calling
            ModelLoader directly, so GPU arbitration with Vision/Diffusion
            (core.gpu_arbiter.GPUArbiter) still applies -- Agent Mode can
            make several model calls per user turn, and each one needs to
            play by the same GPU-sharing rules a normal chat turn does.
        request_approval(action_kind, summary) -> bool: called (from
            whatever thread AgentEngine.run() executes on) whenever a tool
            call needs the user's OK. Must block until answered.
        """
        self.generate_fn = generate_fn
        self.request_approval = request_approval

    def run(self, user_messages: List[dict], emit: Callable[["AgentStep"], None]):
        """
        user_messages: normal chat-style [{"role": "user"/"assistant", "content": ...}, ...],
            same shape ChatManager already produces.
        emit: called with each AgentStep as the loop progresses, so the UI
            can show tool calls/results as they happen rather than only at
            the very end.
        """
        system = {"role": "system", "content": AGENT_SYSTEM_PROMPT.format(tool_list=_format_tool_list())}
        messages = [system] + list(user_messages)

        for _ in range(MAX_TOOL_CALLS_PER_TURN):
            reply = self.generate_fn(messages)
            tool_call = self._extract_tool_call(reply)

            if tool_call is None:
                emit(AgentStep("final", reply.strip()))
                return

            name = tool_call.get("name")
            args = tool_call.get("arguments") or {}
            emit(AgentStep("tool_call", f"{name}({json.dumps(args)})"))

            result_text = self._execute(name, args)
            emit(AgentStep("tool_result", result_text))

            # Feed the tool result back as the next turn rather than
            # trying to keep streaming the same reply -- the model needs
            # to see it before it can decide what to do next.
            messages.append({"role": "assistant", "content": reply.strip()})
            messages.append({"role": "user", "content": f"[TOOL RESULT for {name}]\n{result_text}"})

        emit(AgentStep(
            "final",
            f"(Stopped after {MAX_TOOL_CALLS_PER_TURN} tool calls in one turn -- this is a "
            f"safety cap against a runaway loop, not an error. Ask a follow-up to continue.)",
        ))

    @staticmethod
    def _extract_tool_call(reply: str) -> Optional[dict]:
        """
        Find a <tool_call>{...}</tool_call> block and parse the JSON
        inside it. Deliberately NOT a single non-greedy regex like
        r"\\{.*?\\}" -- the JSON here is nested (the top-level object has
        its own "arguments": {...} object inside it), and a non-greedy
        match stops at the FIRST closing brace it finds, which is the
        inner object's, producing truncated/invalid JSON for every call
        that has more than zero arguments. Brace-balancing instead.
        """
        start_match = _TOOL_CALL_START_RE.search(reply.strip())
        if not start_match:
            return None

        remainder = reply.strip()[start_match.end():]
        end_tag = remainder.find("</tool_call>")
        if end_tag != -1:
            remainder = remainder[:end_tag]

        start = remainder.find("{")
        if start == -1:
            return None

        depth = 0
        end = None
        for i, ch in enumerate(remainder[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            return None

        try:
            return json.loads(remainder[start:end])
        except json.JSONDecodeError:
            return None

    def _execute(self, name: str, args: dict) -> str:
        if name not in agent_tools.TOOL_SPECS:
            return f"Unknown tool '{name}'. Available tools: {', '.join(agent_tools.TOOL_SPECS)}"

        try:
            if name == "read_file":
                result = agent_tools.read_file(**args)
            elif name == "list_dir":
                result = agent_tools.list_dir(**args)
            elif name == "write_file":
                summary = f"Write to {args.get('path')} ({len(str(args.get('content', '')))} chars)"
                if not self.request_approval("write_file", summary):
                    return "Denied by user: write_file was not approved."
                result = agent_tools.write_file(**args)
            elif name == "run_shell":
                command = args.get("command", "")
                safe, reason = agent_tools.is_safe_command(command)
                if not safe:
                    summary = f"Run: {command}\n(needs approval: {reason})"
                    if not self.request_approval("run_shell", summary):
                        return f"Denied by user: run_shell was not approved ({reason})."
                result = agent_tools.run_shell(**args)
            else:
                return f"Tool '{name}' is declared but has no handler wired up."
        except agent_tools.ToolError as e:
            return str(e)
        except TypeError as e:
            return f"Bad arguments for {name}: {e}"

        return result.output
