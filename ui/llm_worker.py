from PySide6.QtCore import QThread, Signal

class LLMWorker(QThread):
    token_received = Signal(str)
    image_ready = Signal(str, str)
    finished = Signal()
    error = Signal(str)
    

    def __init__(self, router, messages, llm_type="chat"):
        super().__init__()
        self.router = router
        self.messages = messages
        self.llm_type = llm_type
        self._running = True
        self._completed = False

    def stop(self):
        self._running = False

    def run(self):
        try:
            for token in self.router.run_llm(self.messages, self.llm_type):
                if not self._running:
                    break
                
                if isinstance(token, str):

                    # 🔥 IMAGE HANDLING (IMPORTANT)
                    if token.startswith("__IMAGE__::"):
                        try:
                            _, file, thumb = token.split("::")
                            self.image_ready.emit(file, thumb)
                        except Exception as e:
                            self.error.emit(f"[IMAGE PARSE ERROR] {e}")
                        continue

                    # NORMAL TEXT
                    self.token_received.emit(token)

            self._completed = True

        except Exception as e:
            self.error.emit(str(e))

        finally:
            
            self.finished.emit()
