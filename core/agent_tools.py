"""
core/agent_tools.py

Tools NOVA's Agent Mode can call: shell execution and file read/write/list,
scoped to the user's home directory. This is the sharp-edged part of the
codebase -- read the safety notes on each function before changing them.

Design decisions (from the user, 2026-09-30):
  - Scope: anywhere under the user's home directory, not the whole
    filesystem. A path that resolves outside it is refused.
  - Approval: read-only / clearly-safe actions run immediately. Anything
    that writes a file, or runs a shell command outside a small read-only
    allowlist, requires the user's explicit approval before it executes.
    That gating is enforced by core/agent_engine.py (which calls
    is_safe_command() and only invokes the approval callback when needed);
    the functions here execute unconditionally once called.
  - Self-modification: NOVA is never allowed to write directly into its
    own live source tree. When asked to improve itself, it must write
    proposals (new files, not edits to existing ones) into
    self_improvement_proposals/ for a human to review and apply by hand.
    This is enforced here in write_file(), not just requested in a
    prompt, so it holds even if the model ignores its instructions.
"""
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from config.config import BASE_DIR

HOME_DIR = Path(os.path.expanduser("~")).resolve()

# NOVA's own source tree -- write_file() refuses to touch anything in here
# except PROPOSALS_DIR. Keeps a bad self-review from corrupting the app
# it's reviewing while it's still running.
NOVA_SOURCE_DIR = Path(BASE_DIR).resolve()
PROPOSALS_DIR = NOVA_SOURCE_DIR / "self_improvement_proposals"

MAX_READ_BYTES = 200_000       # ~200KB -- plenty for source files, guards
                                # against accidentally reading a huge binary/log
MAX_SHELL_OUTPUT = 20_000       # chars of combined stdout/stderr kept
SHELL_TIMEOUT_SECONDS = 30


class ToolError(Exception):
    """Raised for a call that must not run at all (e.g. a path outside
    HOME_DIR). Distinct from a normal ToolResult(ok=False, ...), which
    means "ran, but failed" -- a ToolError means "refused to run"."""


@dataclass
class ToolResult:
    ok: bool
    output: str


def _resolve_in_home(path: str) -> Path:
    """
    Resolve a path the model gave us and make sure it lands inside the
    user's home directory. .resolve() collapses ".." before the
    containment check runs, so "~/Documents/../../etc/passwd" is caught,
    not just a literal leading "..".
    """
    raw = os.path.expanduser(str(path or "").strip())
    if not raw:
        raise ToolError("Refused: empty path.")

    candidate = Path(raw).resolve() if os.path.isabs(raw) else (HOME_DIR / raw).resolve()

    try:
        candidate.relative_to(HOME_DIR)
    except ValueError:
        raise ToolError(
            f"Refused: '{path}' resolves to {candidate}, which is outside your "
            f"home directory ({HOME_DIR}). NOVA's file tools are scoped to your "
            f"home directory only."
        )
    return candidate


def _is_blocked_self_write(path: Path) -> bool:
    """True if `path` is inside NOVA's own source tree and NOT inside the
    proposals folder -- i.e. a write that write_file() must refuse."""
    try:
        path.relative_to(NOVA_SOURCE_DIR)
    except ValueError:
        return False
    try:
        path.relative_to(PROPOSALS_DIR)
        return False  # inside the proposals dir -- allowed
    except ValueError:
        return True  # inside NOVA_SOURCE_DIR but not under proposals -- blocked


def read_file(path: str, max_bytes: int = MAX_READ_BYTES) -> ToolResult:
    p = _resolve_in_home(path)
    if not p.exists():
        return ToolResult(ok=False, output=f"No such file: {p}")
    if p.is_dir():
        return ToolResult(ok=False, output=f"{p} is a directory, not a file. Use list_dir instead.")

    try:
        data = p.read_bytes()
    except Exception as e:
        return ToolResult(ok=False, output=f"Could not read {p}: {e}")

    truncated = len(data) > max_bytes
    text = data[:max_bytes].decode("utf-8", errors="replace")
    if truncated:
        text += f"\n\n...[truncated, file is {len(data)} bytes, showing first {max_bytes}]"
    return ToolResult(ok=True, output=text)


def list_dir(path: str = ".") -> ToolResult:
    p = _resolve_in_home(path)
    if not p.exists():
        return ToolResult(ok=False, output=f"No such path: {p}")
    if not p.is_dir():
        return ToolResult(ok=False, output=f"{p} is a file, not a directory. Use read_file instead.")

    try:
        entries = sorted(os.listdir(p))
    except Exception as e:
        return ToolResult(ok=False, output=f"Could not list {p}: {e}")

    if not entries:
        return ToolResult(ok=True, output="(empty directory)")

    lines = []
    for name in entries:
        full = p / name
        kind = "dir" if full.is_dir() else "file"
        lines.append(f"{kind:4}  {name}")
    return ToolResult(ok=True, output="\n".join(lines))


def write_file(path: str, content: str) -> ToolResult:
    """
    Create or overwrite a text file. The caller (agent_engine) is
    responsible for gating this behind the user's approval before ever
    invoking it -- but the self-source-write block below is re-checked
    here too, so that specific rule holds even if a caller forgets to.
    """
    p = _resolve_in_home(path)

    if _is_blocked_self_write(p):
        rel = p.relative_to(NOVA_SOURCE_DIR)
        return ToolResult(
            ok=False,
            output=(
                f"Refused: '{rel}' is inside NOVA's own source tree. NOVA is not "
                f"allowed to modify its own live code directly. Instead, write your "
                f"proposed change to self_improvement_proposals/<short-name>.md "
                f"(explain the issue and the fix), and if it's a full file rewrite, "
                f"also write self_improvement_proposals/<original filename> with the "
                f"proposed replacement content, for the user to review and apply by hand."
            ),
        )

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except Exception as e:
        return ToolResult(ok=False, output=f"Could not write {p}: {e}")

    return ToolResult(ok=True, output=f"Wrote {len(content)} characters to {p}")


# Command names considered safe to auto-run without approval: read-only /
# informational, none of them can delete, overwrite, install, or send
# data anywhere on their own. Matched against the first word of the
# command only -- see is_safe_command() for the rest of the check.
_SAFE_COMMANDS = {
    "ls", "pwd", "cat", "head", "tail", "wc", "find", "grep", "echo",
    "whoami", "date", "uname", "which", "pytest", "df", "du", "ps",
    "nvidia-smi", "free", "id", "hostname", "file", "stat", "tree",
    "git", "pip", "npm", "node", "python", "python3",
}

# A "safe" command name is refused anyway if the invocation contains any
# of these -- they let a harmless-looking command smuggle in a write, a
# chain, or a shell escape (e.g. "echo hi > ~/.bashrc", "git status; rm -rf ~").
_DANGEROUS_TOKENS = ("|", ">", "<", "&", ";", "`", "$(", "sudo")

# Sub-commands of an otherwise-safe tool that are NOT safe: git can rewrite
# or discard history, pip/npm can install and run arbitrary code, and bare
# python/node with a script argument can do anything a shell can.
_UNSAFE_GIT_SUBCOMMANDS = {
    "push", "commit", "checkout", "reset", "clean", "rm", "stash",
    "filter-branch", "filter-repo", "gc", "merge", "rebase", "add",
}
_UNSAFE_PIP_SUBCOMMANDS = {"install", "uninstall", "download"}
_UNSAFE_NPM_SUBCOMMANDS = {"install", "i", "uninstall", "run", "exec", "start"}
_SCRIPT_RUNNERS = {"python", "python3", "node"}


def is_safe_command(command: str) -> Tuple[bool, str]:
    """
    Returns (is_safe, reason). A command is only auto-approved if it's a
    single, simple invocation of an allowlisted read-only tool, with no
    shell metacharacters and no unsafe subcommand. Everything else needs
    the user's explicit approval -- the default is "ask", not "allow".
    """
    stripped = (command or "").strip()
    if not stripped:
        return False, "empty command"

    for tok in _DANGEROUS_TOKENS:
        if tok in stripped:
            return False, f"contains '{tok}', which can chain, redirect, or escalate a command"

    try:
        parts = shlex.split(stripped)
    except ValueError as e:
        return False, f"could not parse command safely: {e}"

    if not parts:
        return False, "empty command"

    head = parts[0]
    if head not in _SAFE_COMMANDS:
        return False, f"'{head}' is not on the safe/read-only allowlist"

    if head == "git":
        sub = parts[1] if len(parts) > 1 else ""
        if sub in _UNSAFE_GIT_SUBCOMMANDS:
            return False, f"'git {sub}' can modify history, the working tree, or the remote"
    elif head == "pip":
        sub = parts[1] if len(parts) > 1 else ""
        if sub in _UNSAFE_PIP_SUBCOMMANDS:
            return False, f"'pip {sub}' can install or remove arbitrary code"
    elif head == "npm":
        sub = parts[1] if len(parts) > 1 else ""
        if sub in _UNSAFE_NPM_SUBCOMMANDS:
            return False, f"'npm {sub}' can install and execute arbitrary code"
    elif head in _SCRIPT_RUNNERS and len(parts) > 1:
        return False, f"'{head}' with arguments can execute an arbitrary script"

    return True, "read-only/informational command on the safe allowlist"


def run_shell(command: str, cwd: Optional[str] = None) -> ToolResult:
    """
    Actually execute `command`. Callers (agent_engine) must have already
    gated this behind approval if is_safe_command() said no -- this
    function executes unconditionally once called; it does not re-check
    safety, because by the time it's invoked the decision (auto-approved,
    or approved by the user) has already been made.
    """
    workdir = _resolve_in_home(cwd) if cwd else HOME_DIR
    if not workdir.is_dir():
        return ToolResult(ok=False, output=f"Working directory does not exist: {workdir}")

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(ok=False, output=f"Command timed out after {SHELL_TIMEOUT_SECONDS}s")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to run command: {e}")

    out = (proc.stdout or "")
    if proc.stderr:
        out += ("\n[stderr]\n" + proc.stderr)
    if len(out) > MAX_SHELL_OUTPUT:
        out = out[:MAX_SHELL_OUTPUT] + f"\n...[truncated, {len(out)} chars total]"

    ok = proc.returncode == 0
    prefix = "" if ok else f"[exit code {proc.returncode}]\n"
    return ToolResult(ok=ok, output=prefix + out)


TOOL_SPECS = {
    "read_file": {
        "description": "Read a text file. Path is relative to your home directory unless absolute (must still resolve inside it).",
        "args": {"path": "string"},
    },
    "list_dir": {
        "description": "List a directory's contents.",
        "args": {"path": "string (default: '.')"},
    },
    "write_file": {
        "description": (
            "Write (create or overwrite) a text file. Requires the user's approval, "
            "unless the path is inside self_improvement_proposals/. Always refused "
            "for any other path inside NOVA's own source tree."
        ),
        "args": {"path": "string", "content": "string"},
    },
    "run_shell": {
        "description": (
            "Run a shell command in your home directory (or a given cwd inside it). "
            "Read-only commands on a small allowlist (ls, cat, grep, git status/diff/log, "
            "pytest, etc.) run immediately; anything else needs the user's approval."
        ),
        "args": {"command": "string", "cwd": "string (optional)"},
    },
}
