def send_message(self):
        prompt = self.prompt_input.text().strip()
        if not prompt:
            return

        # -----------------------------
        # 1) STOP any active generation
        # -----------------------------
        if self.active_worker:
            self.active_worker.stop()
            self.active_worker.wait()
            self.active_worker = None

        # -----------------------------
        # 2) ROUTE MODEL (before UI)
        # -----------------------------
        if MainWindow.is_code_prompt(prompt):
            target_model = MODEL_MAP["coder"]
            self.log("[ROUTER] Code prompt → CODER model")
        else:
            target_model = MODEL_MAP["chat"]
            self.log("[ROUTER] Chat prompt → CHAT model")

        loaded = self.model_loader.get_loaded_model_name()
        if loaded != target_model:
            self.log(f"[MODEL] Loading {target_model}")
            model_path = os.path.join("models", "gguf", target_model)
            self.model_loader.load(path=model_path, device="cpu")

        # -----------------------------
        # 3) UI PREP
        # -----------------------------
        self.prompt_input.clear()
        self._run_js(Renderer.js_clear_stream())
        self._stream_buffer = ""

        # Render + store user message ONCE
        self.chat_db.add_message(self.current_chat_id, "user", prompt)
        self.chat_db.auto_rename_if_needed(self.current_chat_id, prompt)
        # Render user message immediately
        user_html = Renderer.render_user_message(prompt)
        self._run_js(Renderer.js_finalize(user_html))

        # -----------------------------
        # 4) BUILD CONTEXT
        # -----------------------------
        messages = self.chat_db.get_messages_for_llm(self.current_chat_id)

        attachment_ctx = self._build_attachment_context()
        if attachment_ctx:
            messages.insert(0, attachment_ctx)

        

        # -----------------------------
        # 5) START STREAMING WORKER
        # -----------------------------
        self.active_worker = LLMWorker(
            router=self.router,
            messages=messages
        )

        self.active_worker.token_received.connect(self.append_stream_token)
        self.active_worker.image_ready.connect(self.on_image_ready)
        self.active_worker.finished.connect(self.on_llm_finished)
        self.active_worker.error.connect(self.on_llm_error)
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.active_worker.start()