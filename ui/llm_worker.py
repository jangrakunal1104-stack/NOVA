from PySide6.QtCore import QThread, Signal


class LLMWorker(QThread):
    """Stable LLM Worker - Runs in background thread"""
    
    token_received = Signal(str)
    image_ready = Signal(str, str)   # full_path, thumb_path
    finished = Signal()
    error = Signal(str)

    def __init__(self, router, messages, llm_type="chat"):
        super().__init__()
        self.router = router
        self.messages = messages
        self.llm_type = llm_type
        self._running = True

    def stop(self):
        """Safely stop generation"""
        self._running = False

    def run(self):
        """Main execution in thread"""
        try:
            print(f"[LLMWorker] Starting generation with llm_type={self.llm_type}")

            # Call router (which now respects Brain decision)
            token_stream = self.router.run_llm(self.messages, self.llm_type)

            for token in token_stream:
                if not self._running:
                    print("[LLMWorker] Stop requested by user")
                    break

                if not isinstance(token, str):
                    continue

                # 🔥 Special handling for image generation signal
                if token.startswith("__IMAGE__::"):
                    try:
                        _, file, thumb = token.split("::", 2)
                        self.image_ready.emit(file, thumb)
                    except Exception as e:
                        self.error.emit(f"[IMAGE PARSE ERROR] {e}")
                    continue

                # Normal text token
                self.token_received.emit(token)

            print("[LLMWorker] Generation completed successfully")

        except Exception as e:
            print(f"[LLMWorker] ERROR: {e}")
            self.error.emit(str(e))

        finally:
            self.finished.emit()