from PySide6.QtCore import QThread, Signal


class TaskWorker(QThread):
    """
    Generic background-thread runner for a single blocking call — Tavily
    search, Vision (Qwen2-VL), or Diffusion (Stable Diffusion). These used
    to run directly on the Qt/GUI thread inside MainWindow, which froze the
    whole window (no repaint, no Stop button, looked "hung") for the entire
    duration of the network call / model load / inference. Running them on
    a QThread keeps the UI responsive.

    Unlike LLMWorker, the wrapped callable has no cooperative cancellation
    hook — a Tavily request, a Vision pass, or a Diffusion generation runs
    to completion once started, there's no way to interrupt it partway.
    stop() is therefore a no-op, provided only so this class matches the
    stop()/wait() interface MainWindow's _stop_active_worker() expects.
    """

    result_ready = Signal(object)
    error = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def stop(self):
        # No cooperative cancellation is possible for the wrapped calls.
        pass

    def run(self):
        try:
            result = self.fn()
        except Exception as e:
            self.error.emit(str(e))
            return
        self.result_ready.emit(result)
