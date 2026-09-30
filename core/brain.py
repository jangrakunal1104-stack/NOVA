import re


class Brain:
    """
    Decides which subsystem handles a message: live web search, image
    generation, vision (image attached), a code-flavored chat turn, or a
    normal chat turn.

    Matching is done with word-boundary regex (`_matches`) rather than
    naive substring `in` checks, e.g. so the keyword "class" doesn't
    false-positive inside "classical", and "script" doesn't false-positive
    inside "subscription" -- both of which the old substring check did.

    Order matters: SEARCH is checked before IMAGE GENERATION because a
    search query can legitimately contain image-ish nouns ("search for a
    picture of the eiffel tower" should search, not generate an image).
    VISION (an attached image) is checked first of all, since an actually
    attached file is a stronger, more concrete signal than any keyword in
    the text.
    """

    IMAGE_KEYWORDS = [
        "generate image", "create image", "draw me", "make image", "picture of",
        "image of", "photo of", "visualize", "diffusion", "generate an image",
    ]

    SEARCH_PHRASES = [
        "current situation", "latest news", "what is happening", "what's happening",
        "what happened", "right now", "breaking news", "news about", "look up",
        "search for", "find out about", "what is the status", "latest on",
        "update on", "who won", "stock price", "weather in", "today's",
        "current status", "live update", "recent developments", "as of today",
        "strait of", "hormuz", "war in", "election results",
    ]

    CODE_KEYWORDS = [
        "write a", "python function", "python code", "code for", "function to",
        "algorithm", "script", "class", "def", "fix this code", "debug",
        "implement", "exploit", "binary", "sort the", "reverse a",
    ]

    @staticmethod
    def _matches(text: str, phrases) -> bool:
        """Word-boundary phrase matching (case-insensitive; `text` is
        expected already-lowercased). Avoids matching a keyword that's
        only a substring of a longer, unrelated word."""
        for phrase in phrases:
            pattern = r"\b" + r"\s+".join(re.escape(w) for w in phrase.split()) + r"\b"
            if re.search(pattern, text):
                return True
        return False

    def decide(self, messages, attachments=None):
        if not messages:
            return {"model": "llm", "llm_type": "chat", "input": {"messages": messages}}

        last_user_msg = messages[-1]["content"].lower()
        original_prompt = messages[-1]["content"]

        # === VISION (image attached) — most concrete signal, checked first ===
        if attachments and any(a.get("type") == "image" for a in attachments):
            print("[BRAIN] → VISION")
            return {
                "model": "vision",
                "input": {
                    "image_path": attachments[-1]["path"],
                    "prompt": original_prompt
                }
            }

        # === WEB SEARCH (current events, news, live facts) ===
        if self._matches(last_user_msg, self.SEARCH_PHRASES) or last_user_msg.startswith("search "):
            print("[BRAIN] → WEB SEARCH")
            return {
                "model": "search",
                "input": {"prompt": original_prompt}
            }

        # === IMAGE GENERATION ===
        if self._matches(last_user_msg, self.IMAGE_KEYWORDS):
            print("[BRAIN] → DIFFUSION")
            return {"model": "diffusion", "input": {"prompt": original_prompt}}

        # === CODE REQUEST ===
        if self._matches(last_user_msg, self.CODE_KEYWORDS):
            print("[BRAIN] → CODE REQUEST")
            return {"model": "llm", "llm_type": "chat", "input": {"messages": messages}}

        # Default
        print("[BRAIN] → NORMAL CHAT")
        return {"model": "llm", "llm_type": "chat", "input": {"messages": messages}}
