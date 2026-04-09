class Brain:

    def __init__(self):
        pass

    def decide(self, messages, attachments=None):
        text = messages[-1]["content"].lower().strip()

        # =========================
        # 1. ATTACHMENTS (HIGHEST PRIORITY)
        # =========================
        if attachments:
            for att in attachments:
                if att.get("type") == "image":
                    return {
                        "intent": "vision",
                        "model": "vision",
                        "mode": "normal",
                        "input": {
                            "image_path": att["path"],
                            "prompt": text
                        }
                    }

        # =========================
        # 2. IMAGE GENERATION
        # =========================
        if self._is_image_generation(text):
            return {
                "intent": "diffusion",
                "model": "diffusion",
                "mode": "normal",
                "input": {"prompt": text}
            }

        # =========================
        # 3. SEARCH MODE
        # =========================
        if self._needs_search(text):
            return {
                "intent": "search",
                "model": "llm",
                "mode": "search",
                "input": {"messages": messages}
            }

        # =========================
        # 4. CODE / DEBUG
        # =========================
        if self._is_code_request(text):
            return {
                "intent": "code",
                "model": "llm",
                "llm_type": "code",
                "mode": "reason",
                "input": {"messages": messages}
            }

        # =========================
        # 5. REASONING MODE (NEW)
        # =========================
        if self._needs_reasoning(text):
            return {
                "intent": "reason",
                "model": "llm",
                "mode": "reason",
                "input": {"messages": messages}
            }

        # =========================
        # 6. DEFAULT CHAT
        # =========================
        return {
            "intent": "chat",
            "model": "llm",
            "mode": "normal",
            "input": {"messages": messages}
        }

    # =========================
    # HELPERS
    # =========================

    def _is_image_generation(self, text):
        return any(x in text for x in [
            "generate image", "create image", "draw", "image of", "make image"
        ])

    def _needs_search(self, text):
        return any(x in text for x in [
            "latest", "current", "today", "news", "recent",
            "price", "stock", "weather"
        ])
        

    def _is_code_request(self, text):
        return any(x in text for x in [
            "code", "python", "script", "bug", "error", "fix", "debug", "traceback"
        ])

    def _needs_reasoning(self, text):
        return any(x in text for x in [
            "how", "why", "explain", "steps", "analyze", "difference", "compare"
        ])