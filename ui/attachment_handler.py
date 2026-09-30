from pathlib import Path
import os
from PIL import Image
import json
from ui.renderer import Renderer

class AttachmentHandler:
    def __init__(self, main_window):
        self.main_window = main_window
        self.attachments = {}  # chat_id -> list of dicts

    def attach_file(self, chat_id: int, path: str):
        if not chat_id:
            return

        MAX_SIZE = 5_000_000
        name = os.path.basename(path)
        ext = Path(path).suffix.lower()

        self.attachments.setdefault(chat_id, [])

        # Prevent duplicates
        if any(a["path"] == path for a in self.attachments[chat_id]):
            self.main_window.log(f"[ATTACH] {name} already attached")
            return

        try:
            size = os.path.getsize(path)
        except OSError as e:
            self.main_window.log(f"[ATTACH ERROR] {e}")
            return

        if size > MAX_SIZE:
            self.main_window.log(f"[ATTACH ERROR] {name} too large")
            return

        # Image
        if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            try:
                Image.open(path)
                content = f"IMAGE FILE: {name}\nAssistant will analyze this image."
                attachment = {"name": name, "path": path, "type": "image", "size": size, "content": content}
            except Exception as e:
                self.main_window.log(f"[ATTACH ERROR] image parse failed: {e}")
                return

        # Text/Code
        elif ext in {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".log"}:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                attachment = {"name": name, "path": path, "type": "text", "size": size, "content": content}
            except Exception as e:
                self.main_window.log(f"[ATTACH ERROR] {e}")
                return
        else:
            self.main_window.log(f"[ATTACH ERROR] Unsupported file type: {ext}")
            return

        self.attachments[chat_id].append(attachment)
        self.main_window.log(f"[ATTACH] {name} attached ({attachment['type']})")
        self.render_badge(name)

    def clear_attachments(self, chat_id: int):
        if chat_id in self.attachments:
            self.attachments[chat_id] = []
            self.main_window.log("[ATTACH] Cleared attachments")
            # Remove visual badges
            self.main_window.run_js(
                'document.querySelectorAll(".attachment").forEach(el => el.remove());'
            )

    def render_badge(self, name: str):
        html = f"""
        <div class="attachment" style="border: 1px dashed #555; padding: 6px; margin: 4px 0; font-size: 12px; color: #ccc;">
            📎 Attached: <b>{name}</b>
        </div>
        """
        self.main_window.run_js(
            f'document.getElementById("chat").insertAdjacentHTML("beforeend", {json.dumps(html)});'
        )

    def get_attachment_context(self, chat_id: int):
        atts = self.attachments.get(chat_id, [])
        if not atts:
            return None
        parts = [f"--- FILE: {a['name']} ---\n{a['content']}\n" for a in atts]
        return {
            "role": "system",
            "content": "The following files are attached:\n\n" + "\n".join(parts)
        }