class ContextMemory:
    def __init__(self):
        self.topic = None
        self.intent = None

    def update(self, prompt: str):
        p = prompt.lower().strip()

        # =========================
        # RESET CONDITION
        # =========================
        if len(p.split()) <= 2:
            return

        # =========================
        # TOPIC DETECTION (STICKY)
        # =========================
        new_topic = None

        if any(x in p for x in ["tcp", "dns", "network", "ip", "packet"]):
            new_topic = "networking"

        elif any(x in p for x in ["hack", "exploit", "scan", "nmap"]):
            new_topic = "cybersecurity"

        elif any(x in p for x in ["python", "code", "script", "program"]):
            new_topic = "programming"

        if new_topic:
            self.topic = new_topic

        # =========================
        # INTENT DETECTION
        # =========================
        if any(x in p for x in ["fix", "error", "bug", "traceback"]):
            self.intent = "debugging"

        elif any(x in p for x in ["how", "why", "explain", "steps"]):
            self.intent = "learning"

        else:
            self.intent = "general"

    def get(self):
        return {
            "topic": self.topic,
            "intent": self.intent
        }

    def reset(self):
        self.topic = None
        self.intent = None