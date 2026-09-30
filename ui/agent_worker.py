"""
ui/agent_worker.py

QThread wrapper around core.agent_engine.AgentEngine, so Agent Mode runs
off the GUI thread -- same reasoning as ui/task_worker.py: tool calls
(especially shell commands and file I/O) can take a while and must not
freeze the window.

Approval is the tricky part: a tool call that needs the user's OK has to
pop a real dialog on the GUI thread and then BLOCK the worker thread until
they answer, without blocking the GUI thread itself. That's done here with
a Qt queued signal plus a threading.Event:

  1. The worker (background thread) calls _request_approval(), which
     builds a small mutable box + a threading.Event, and emits
     approval_requested(kind, summary, (box, event)).
  2. Because approval_requested is connected to a bound slot on a
     QObject that lives on the GUI thread (MainWindow), Qt auto-queues
     the delivery onto the GUI thread instead of running it on the
     worker thread -- the same signal/slot thread-affinity rule
     ui/task_worker.py relies on.
  3. MainWindow's slot shows a real QMessageBox (GUI thread, no freeze),
     writes the answer into `box`, and calls event.set().
  4. The worker thread, which has been sitting in event.wait() the whole
     time, wakes up and reads `box["approved"]`.

The window stays fully responsive while a dialog is up (it's a modal
QMessageBox, which is the expected UX for "an action needs your OK"
anyway); only the agent's own background thread is paused.
"""
import threading

from PySide6.QtCore import QThread, Signal

from core.agent_engine import AgentEngine


class AgentWorker(QThread):
    step = Signal(str, str)                        # kind, text
    approval_requested = Signal(str, str, object)   # kind, summary, (box, event)
    finished = Signal()
    error = Signal(str)

    def __init__(self, router, messages):
        """
        router: core.backend_router.BackendRouter -- used (not ModelLoader
            directly) so every model call this loop makes still goes
            through GPUArbiter's arbitration with Vision/Diffusion.
        messages: chat history so far, [{"role", "content"}, ...]; the
            agent's own system prompt is added internally by AgentEngine.
        """
        super().__init__()
        self.router = router
        self.messages = messages
        self._stop_requested = False

    def stop(self):
        # There's no clean mid-generation cancel for the underlying
        # llama.cpp call today (same limitation ui/task_worker.py's
        # TaskWorker has) -- this flag stops the loop from starting
        # another tool-call round after the current one finishes, and
        # unblocks anyone waiting on an approval so the thread can exit.
        self._stop_requested = True

    def _request_approval(self, kind: str, summary: str) -> bool:
        if self._stop_requested:
            return False
        box = {"approved": False}
        event = threading.Event()
        self.approval_requested.emit(kind, summary, (box, event))
        event.wait()
        return box["approved"]

    def _generate(self, messages) -> str:
        return "".join(self.router.run_llm(messages, "chat"))

    def run(self):
        try:
            engine = AgentEngine(self._generate, self._request_approval)

            def _emit(step):
                if not self._stop_requested:
                    self.step.emit(step.kind, step.text)

            engine.run(self.messages, _emit)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()
