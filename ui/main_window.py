# =============================
# PySide6 (grouped properly)
# =============================
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QListWidget,
    QLineEdit, QPushButton, QLabel, QVBoxLayout,
    QHBoxLayout, QSizePolicy, QDialog, 
    QMessageBox, QFileDialog, QInputDialog, QTextEdit
)
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, Slot, QUrl, QTimer
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
# =============================
# Standard library
# =============================
import os
import json
from pathlib import Path
# =============================
# Third-party
# =============================
from PIL import Image

# =============================
# Project imports
# =============================
from core.chat_manager import ChatManager
from ui.llm_worker import LLMWorker
from core.image_engine import ImageEngine
from core.brain import Brain

from core.backend_router import BackendRouter

from ui.renderer import Renderer
from .jsbridge import JSBridge

from config.config import SETTINGS_PATH

from core.context_memory import ContextMemory

os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Reserved for future CSP / file interception

#class ImageInterceptor(QWebEngineUrlRequestInterceptor):
#    def __init__(self, window):
#        super().__init__()
#        self.window = window

#    def interceptRequest(self, info):
#        # Placeholder — extend later
#        pass

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self._full_response = ""
        self._last_token = ""
        self.setWindowTitle("NOVA")
        self.resize(1200, 800)
        self.chat_db = ChatManager()
        self.current_chat_id = None
        self.web_ready = False

        self.context_memories = {}
        self.chat_summaries = {}
        self.semantic_memory = {}
        # ---- state / core init ----


        self.settings = self.load_settings()
        self.ctx_size = self.settings["global"]["ctx_size"]
        self.active_model = None
        self.attachments = {}

        self.renderer = Renderer()
        self.brain = Brain()
        self.active_worker = None
        self._stream_buffer = ""
        self._final_rendered = False
        self.image_engine = ImageEngine()
        
        self.router = BackendRouter(
            self.image_engine
        )

        
        # ---- build UI ----
        self._build_ui()
        self._load_chats_from_db()

        # ---- build MENUS FIRST ----
        self._build_menu()

        # =============================
        # ATTACH CONTROLS (MENU BAR)
        # =============================
        self.attach_widget = QWidget(self)
        self.attach_layout = QHBoxLayout(self.attach_widget)
        self.attach_layout.setContentsMargins(6, 0, 6, 0)
        self.attach_layout.setSpacing(6)

        self.attach_btn = QPushButton("📎 Attach")
        self.attach_btn.setFixedHeight(26)
        self.attach_btn.clicked.connect(self.on_attach_clicked)

        self.clear_btn = QPushButton("🧹 Clear")
        self.clear_btn.setFixedHeight(26)
        self.clear_btn.clicked.connect(self._clear_attachments)

        self.attach_layout.addWidget(self.attach_btn)
        self.attach_layout.addWidget(self.clear_btn)

        self.menuBar().setCornerWidget(
            self.attach_widget,
            Qt.TopLeftCorner
        )

        # ---- status bar, timers, rest ----
        self.vram_label = QLabel("VRAM: --")
        self.statusBar().addPermanentWidget(self.vram_label)

        self._vram_timer = QTimer(self)
        self._vram_timer.timeout.connect(self._update_vram_status)
        self._vram_timer.start(1000)

        # =============================
        # UI LAYOUT
        # =============================
    def _build_ui(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)
        self.setCentralWidget(root)

        # ----------------------------------
            # LEFT — Chats + STT / TTS
            # ----------------------------------
        self.chat_list = QListWidget()
        self.chat_list.clear()
        self.chat_list.itemClicked.connect(self._on_chat_selected)

        left = QVBoxLayout()
        left.addWidget(QLabel("Chats"))
        left.addWidget(self.chat_list, stretch=1)
        left.addStretch()




        left_container = QWidget()
        left_container.setLayout(left)
        left_container.setFixedWidth(200)

            # ----------------------------------
            # CENTER — Chat + Input Bar
            # ----------------------------------
        self.chat_view = QWebEngineView(self)
        self.chat_view.setAttribute(Qt.WA_NativeWindow, False)


        self.chat_view.setHtml(self.renderer.base_html())

        def _wire_webchannel():
            if getattr(self, "channel", None):
                return

            self.channel = QWebChannel(self.chat_view.page())
            self.jsbridge = JSBridge(self)
            self.channel.registerObject("qt", self.jsbridge)
            self.chat_view.page().setWebChannel(self.channel)
            self.web_ready = True
            self.log("[UI] WebView ready")

        self.chat_view.loadFinished.connect(lambda ok: _wire_webchannel())

        self.chat_view.settings().setAttribute(
            QWebEngineSettings.LocalContentCanAccessFileUrls, True
        )
        self.chat_view.settings().setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, True
        )
        self.chat_view.settings().setAttribute(
            QWebEngineSettings.JavascriptCanOpenWindows, True
        )

        self.chat_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            # --- Input Bar ---
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("Type a message…")
        self.prompt_input.returnPressed.connect(self.send_message)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_message)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)

        self.stop_btn.clicked.connect(self.on_stop_clicked)

        input_bar = QHBoxLayout()

        input_bar.addWidget(self.prompt_input)
        input_bar.addWidget(self.send_btn)
        input_bar.addWidget(self.stop_btn)

        self.prompt_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        input_container = QWidget()
        input_container.setLayout(input_bar)
        input_container.setFixedHeight(42)
        input_container.setAttribute(Qt.WA_StyledBackground, True)

        center = QVBoxLayout()
        center.addWidget(self.chat_view, stretch=1)
        center.addWidget(input_container, stretch=0)

        center_container = QWidget()
        center_container.setLayout(center)

        # ----------------------------------
        # RIGHT — Chat Options + Model (display-only)
        # ----------------------------------
        right = QVBoxLayout()
        right.addWidget(QLabel("Chat Options"))



        # ---- Logs ----
        right.addSpacing(8)
        right.addWidget(QLabel("Logs"))

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFixedHeight(220)
        self.log_console.setStyleSheet("""
            QTextEdit {
                background-color: #0e0e0e;
                color: #9cdcfe;
                font-family: Consolas, monospace;
                font-size: 11px;
                border: 1px solid #222;
            }
        """)

        right.addWidget(self.log_console)

        self.new_chat_btn = QPushButton("New Chat")
        self.clear_chat_btn = QPushButton("Clear Chat")
        self.rename_chat_btn = QPushButton("Rename Chat")
        self.export_chat_btn = QPushButton("Export Chat")
        self.delete_chat_btn = QPushButton("Delete Chat")
        self.new_chat_btn.clicked.connect(self.on_new_chat)
        self.clear_chat_btn.clicked.connect(self.on_clear_chat)
        self.rename_chat_btn.clicked.connect(self.on_rename_chat)
        self.export_chat_btn.clicked.connect(self.on_export_chat)
        self.delete_chat_btn.clicked.connect(self.on_delete_chat)

        right.addWidget(self.new_chat_btn)
        right.addWidget(self.clear_chat_btn)
        right.addWidget(self.rename_chat_btn)
        right.addWidget(self.export_chat_btn)
        right.addWidget(self.delete_chat_btn)

        right.addStretch()

        right_container = QWidget()
        right_container.setLayout(right)
        right_container.setFixedWidth(260)

        # Assemble layout
        root_layout.addWidget(left_container)
        root_layout.addWidget(center_container)
        root_layout.addWidget(right_container)

    def _build_menu(self):
        pass

    # =============================
    # PLACEHOLDER BUTTON HANDLERS
    # =============================
    def _run_js(self, js: str):
        if not self.web_ready:
            return
        self.chat_view.page().runJavaScript(js)

    def on_new_chat(self):
        chat_id = self.chat_db.create_chat()
        self._load_chats_from_db()
        self._load_chat_from_db(chat_id)
        self.log(f"[CHAT] New chat created ({chat_id})")

    def on_clear_chat(self):
        if not self.current_chat_id:
            return

        old_id = self.current_chat_id
        self.chat_db.delete_chat(old_id)
        self.log(f"[CHAT] Deleted chat {old_id}")

        # Create a brand-new empty chat
        new_id = self.chat_db.create_chat()
        self.log(f"[CHAT] Created new chat {new_id}")

        # Update list WITHOUT auto-loading messages
        self.chat_list.clear()
        chats = self.chat_db.get_all_chats()
        for c in chats:
            self.chat_list.addItem(f"{c['id']}::{c['title']}")

        self.current_chat_id = new_id

        # Clear UI explicitly
        self._run_js("document.getElementById('chat').innerHTML = '';")
        self._run_js(Renderer.js_clear_stream())

    def on_rename_chat(self):
        if not self.current_chat_id:
            return

        title, ok = QInputDialog.getText(
            self,
            "Rename Chat",
            "New chat title:"
        )
        if not ok or not title.strip():
            return

        self.chat_db.rename_chat(self.current_chat_id, title.strip())
        self._load_chats_from_db()
        self.log(f"[CHAT] Renamed to: {title}")

    def on_export_chat(self):
        if not self.current_chat_id:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Chat",
            f"chat_{self.current_chat_id}.txt",
            "Text Files (*.txt)"
        )
        if not path:
            return

        messages = self.chat_db.get_chat(self.current_chat_id)

        with open(path, "w", encoding="utf-8") as f:
            for m in messages:
                f.write(f"{m['role'].upper()}:\n{m['content']}\n\n")

        self.log(f"[CHAT] Exported to {path}")

    def _clear_attachments(self):
        if not self.current_chat_id:
            return

        self.attachments[self.current_chat_id] = []

        
        self.log("[ATTACH] Cleared attachments")

        self._run_js(
            Renderer.js_finalize(
                '<div style="color:#888; font-size:12px;">🧹 Attachments cleared</div>'
            )
        )

    def on_attach_clicked(self):
        
        self.log("[ATTACH] button clicked")

        dialog = QFileDialog(self, "Attach file")
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setNameFilter(
            "Documents (*.txt *.md *.py *.json *.log *.yaml *.yml);;"
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;"
            "All files (*)"
        )
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        if dialog.exec() != QFileDialog.Accepted:
            self.log("[ATTACH] cancelled")
            return

        path = dialog.selectedFiles()[0]
        self.log(f"[ATTACH] selected: {path}")
        self._attach_file(path)

    def _attach_file(self, path: str):
        
        MAX_SIZE = 5_000_000  # 5 MB

        name = os.path.basename(path)
        ext = Path(path).suffix.lower()

        # ---------------------------------
        # Ensure chat attachment bucket
        # ---------------------------------
        self.attachments.setdefault(self.current_chat_id, [])

        # ---------------------------------
        # Prevent duplicate attachments
        # ---------------------------------
        for a in self.attachments[self.current_chat_id]:
            if a["path"] == path:
                self.log(f"[ATTACH] {name} already attached")
                return

        # ---------------------------------
        # File size check
        # ---------------------------------
        try:
            size = os.path.getsize(path)
        except OSError as e:
            self.log(f"[ATTACH ERROR] {e}")
            return

        if size > MAX_SIZE:
            self.log(f"[ATTACH ERROR] {name} too large ({size} bytes)")
            return

        # ---------------------------------
        # IMAGE FILES
        # ---------------------------------
        if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:

            try:
                img = Image.open(path)

                content = f"IMAGE FILE: {name}\nThe assistant will analyze this image directly."
    
                attachment = {
                    "name": name,
                    "path": path,
                    "type": "image",
                    "size": size,
                    "content": content,
                }

            except Exception as e:
                self.log(f"[ATTACH ERROR] image parse failed: {e}")
                return

        # ---------------------------------
        # TEXT / CODE FILES
        # ---------------------------------
        elif ext in {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".log"}:

            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()

                attachment = {
                    "name": name,
                    "path": path,
                    "type": "text",
                    "size": size,
                    "content": content,
                }

            except UnicodeDecodeError:
                self.log(f"[ATTACH ERROR] {name} is not valid UTF-8 text")
                return
            except Exception as e:
                self.log(f"[ATTACH ERROR] {e}")
                return

        # ---------------------------------
        # UNSUPPORTED FILE TYPES
        # ---------------------------------
        else:
            self.log(f"[ATTACH ERROR] Unsupported file type: {ext}")
            return

        # ---------------------------------
        # Store attachment
        # ---------------------------------
        self.attachments[self.current_chat_id].append(attachment)

        self.log(f"[ATTACH] {name} attached ({attachment['type']})")

        # Render badge in UI
        self._render_attachment_badge(name)

    def _render_attachment_badge(self, name: str):
        self.log(f"[ATTACH] Active: {name}")

        html = f"""
        <div class="attachment" style="
            border: 1px dashed #555;
            padding: 6px;
            margin: 4px 0;
            font-size: 12px;
            color: #ccc;
        ">
            📎 Attached: <b>{name}</b>
        </div>
        """
        self._run_js(
            f'document.getElementById("chat").insertAdjacentHTML("beforeend", {json.dumps(html)});'
        )

    def _build_attachment_context(self):
        atts = self.attachments.get(self.current_chat_id, [])
        if not atts:
            return None

        parts = []
        for att in atts:
            parts.append(
                f"--- FILE: {att['name']} ---\n{att['content']}\n"
            )

        return {
            "role": "system",
            "content": (
                    "The following files are attached to this conversation.\n\n"
                    + "\n".join(parts)
            )
        }

    def _load_chats_from_db(self):
        self.chat_list.clear()
        chats = self.chat_db.get_all_chats()

        if not chats:
            return

        for c in chats:
            self.chat_list.addItem(f"{c['id']}::{c['title']}")

    def _load_chat_from_db(self, chat_id):

        self.current_chat_id = chat_id

        # CLEAR UI completely
        self._run_js("document.getElementById('chat').innerHTML = '';")
        self._run_js(Renderer.js_clear_stream())

        messages = self.chat_db.get_chat(chat_id)

        for m in messages:
            if m["role"] == "system":
                continue

            if m["role"] == "user":
                html = Renderer.render_user_message(m["content"])
            else:
                html = Renderer.render_nova_message(m["content"])

            self._run_js(
                f'document.getElementById("chat").insertAdjacentHTML("beforeend", {json.dumps(html)});'
            )

    def _update_vram_status(self):
        try:
            import subprocess

            result = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                stderr=subprocess.DEVNULL,
                timeout=1,
            )

            used, total = result.decode().strip().split(",")
            used = int(used)
            total = int(total)
            pct = (used / total) * 100 if total else 0

            self.vram_label.setText(
                f"VRAM: {used} / {total} MB ({pct:.0f}%)"
            )

        except FileNotFoundError:
            self.vram_label.setText("VRAM: nvidia-smi not found")

        except Exception:
            self.vram_label.setText("VRAM: ?")

    def log(self, message: str):
        self.log_console.append(message)
        self.log_console.verticalScrollBar().setValue(
            self.log_console.verticalScrollBar().maximum()
        )

    def load_settings(self):
        if not os.path.exists(SETTINGS_PATH):
            settings = {}
        else:
            with open(SETTINGS_PATH, "r") as f:
                settings = json.load(f)

        settings.setdefault("global", {}).setdefault("ctx_size", 4096)
        settings.setdefault("image", {})
        settings["image"].setdefault("thumbnail_width", 256)
        settings["image"].setdefault("width", 768)
        settings["image"].setdefault("height", 768)
        settings.setdefault("models", {}).setdefault("last_used", None)

        return settings


    def save_settings(self, settings=None):
        if settings is None:
            settings = self.settings
        with open(SETTINGS_PATH, "w") as f:
            json.dump(settings, f, indent=2)

    def on_stop_clicked(self):
        self._last_token = ""
        self.log("[UI] Stop requested")

        if self.active_worker:
            self.active_worker.stop()
            self.active_worker.wait()
            self.active_worker = None

        # 🔥 finalize partial response instead of deleting it
        final = self._full_response.strip()

        if final:
            self._run_js(Renderer.js_clear_stream())

            self._run_js(
                Renderer.js_finalize(
                    Renderer.render_nova_message(final)
                )
            )

            self.chat_db.add_message(self.current_chat_id, "assistant", final)

        # 🔥 reset buffers AFTER saving
        self._full_response = ""
        self._stream_buffer = ""

        self.stop_btn.setEnabled(False)
        self.send_btn.setEnabled(True)

    def _on_chat_selected(self, item):
        chat_id = int(item.text().split("::")[0])
        self._load_chat_from_db(chat_id)

    def append_assistant_placeholder(self):
        self._run_js(
            Renderer.js_clear_stream()
        )

    def _open_full_image(self, path: str):
        

        dlg = QDialog(self)
        dlg.setWindowTitle("Image Viewer")

        pix = QPixmap(path)
        lbl = QLabel()
        lbl.setPixmap(pix)
        lbl.setScaledContents(True)

        layout = QVBoxLayout(dlg)
        layout.addWidget(lbl)

        dlg.resize(800, 600)
        dlg.exec()

    @Slot(str)
    def openImage(self, path: str):
        if not path or not os.path.exists(path):
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # =============================
    # Send message (STREAMING)
    # =============================
    def send_message(self):
        self._last_token = ""
        prompt = self.prompt_input.text().strip()
        self._final_rendered = False
        # =============================
        # GREETING HARD OVERRIDE (FINAL FIX)
        # =============================
        p = prompt.lower().strip()

        if p in ["hi", "hello", "hey"]:
            self._prepare_ui(prompt)

            response = "Hello! How can I help you?"

            html = Renderer.render_nova_message(response)
            self._run_js(Renderer.js_finalize(html))

            self.chat_db.add_message(self.current_chat_id, "assistant", response)

            return
        
        

        # keep original prompt for memory
        self._last_prompt = prompt
        # 🔥 RESET CONTEXT (IMPORTANT)
        if prompt.lower().strip() in ["hi", "hello", "hey"]:
            
            ctx_mem = self._get_context_memory()
            ctx_mem.reset()
        
        # always update memory
        ctx_mem = self._get_context_memory()
        ctx_mem.update(prompt)
        
        
        if not prompt or self.current_chat_id is None:
            return
        
        self._stop_active_worker()
        self._prepare_ui(prompt)
        # =============================
        # SEMANTIC MEMORY EXTRACTION
        # =============================
        fact = self._extract_facts(prompt)

        if fact:
            self.semantic_memory.setdefault(self.current_chat_id, [])

            if fact not in self.semantic_memory[self.current_chat_id]:
                self.semantic_memory[self.current_chat_id].append(fact)
        attachments = self.attachments.get(self.current_chat_id, [])
        # =============================
        # AUTO SUMMARY (LEVEL 2 MEMORY)
        # =============================
        messages = self.chat_db.get_messages_for_llm(self.current_chat_id)

        if len(messages) > 20 and len(messages) % 10 == 0:
            summary = self._summarize_chat(messages[:-10])
            self.chat_summaries[self.current_chat_id] = summary
        

# 🔥 FORCE VISION FIRST (CRITICAL)
        if attachments:
            image_path = next(
                (att["path"] for att in reversed(attachments) if att.get("type") == "image"),
                None
            )

            if image_path:
                decision = {
                    "model": "vision",
                    "mode": "normal",
                    "input": {
                        "image_path": image_path,
                        "prompt": prompt
                    }
                }
            else:
                decision = self.brain.decide(
                    [{"role": "user", "content": prompt}],
                    attachments
                )
        else:
            decision = self.brain.decide(
                [{"role": "user", "content": prompt}],
                attachments
            )

        # 🔥 ONLY BUILD MESSAGES FOR LLM
        if decision["model"] == "llm":
            mode = decision.get("mode", "normal")
            messages = self._build_messages(prompt, mode)
            decision["input"]["messages"] = messages

        self._execute_decision(decision)

        
        #self.intent_engine.update("text", prompt)

    def _stop_active_worker(self):
        if self.active_worker:
            self.active_worker.stop()
            self.active_worker.wait()
            self.active_worker = None
    
    def _prepare_ui(self, prompt: str):
        
        self.prompt_input.clear()
        self._run_js(Renderer.js_clear_stream())
        self._stream_buffer = ""

        self.chat_db.add_message(self.current_chat_id, "user", prompt)
        self.chat_db.auto_rename_if_needed(self.current_chat_id, prompt)

        user_html = Renderer.render_user_message(prompt)
        self._run_js(Renderer.js_finalize(user_html))

    def _build_messages(self, prompt: str, mode: str):
        p = prompt.lower().strip()

        # =============================
        # 1. CONTEXT MEMORY
        # =============================
        ctx = self._get_context_memory().get()
        topic = ctx.get("topic")
        intent = ctx.get("intent")

        # =============================
        # 2. SYSTEM PROMPT (DEFINE FIRST ❗)
        # =============================
        system_content = (
            "You are NOVA, an advanced local AI assistant.\n"
            "You must:\n"
            "- Use memory when answering questions about past context or user\n"
            "- If user provides new information → acknowledge it naturally\n"
            "- NEVER say you don't know if the answer exists in memory\n"
            "- If user asks about themselves → use stored facts\n"
            "- Do NOT assume memory for new statements\n"
            "- Stay consistent with conversation history\n"
            "- Continue previous context unless user changes topic\n"
            "- Be precise, structured, and useful\n"
            "- Do NOT hallucinate\n"
        )

        # Inject context memory
        if topic or intent:
            system_content += f"""
        Conversation Context:
        - Topic: {topic or "unknown"}
        - Intent: {intent or "general"}

        Rules:
        - Maintain topic continuity
        - Do not restart explanation unless asked
        - Adapt answer based on intent
        - Keep answers concise when question is simple

        Behavior:
        - If user provides new personal info → acknowledge naturally
        - If user asks about themselves → use stored facts
        - Do NOT mention memory, storage, or internal system
        - Respond naturally like a human assistant
        """

        # =============================
        # 3. HISTORY CONTROL (SMART)
        # =============================
        MAX_HISTORY = 10

        if p in ["hi", "hello", "hey"]:
            history = []
        else:
            history = self.chat_db.get_messages_for_llm(self.current_chat_id)[-MAX_HISTORY:]

        # =============================
        # 4. ATTACHMENTS
        # =============================
        attachment_ctx = self._build_attachment_context()

        # =============================
        # 5. FINAL MESSAGE BUILD
        # =============================
        messages = []

        # SYSTEM FIRST
        messages.append({
            "role": "system",
            "content": system_content
        })

        # =============================
        # SUMMARY MEMORY
        # =============================
        summary = self.chat_summaries.get(self.current_chat_id)

        if summary:
            messages.append({
                "role": "system",
                "content": f"IMPORTANT CONTEXT (conversation summary):\n{summary}"
            })

        # =============================
        # SEMANTIC MEMORY
        # =============================
        facts = self.semantic_memory.get(self.current_chat_id)

        if facts:
            memory_text = "\n".join(facts[-5:])

            messages.append({
                "role": "system",
                "content": (
                    "User context (informational, safe to use):\n"
                    f"{memory_text}"
                )
            })

            

        # HISTORY
        messages.extend(history)

        # ATTACHMENTS (if any)
        if attachment_ctx:
            messages.append(attachment_ctx)

        # USER LAST
        if len(prompt.split()) > 5:
            prompt += "\n\nAnswer clearly."

        messages.append({
            "role": "user",
            "content": prompt
        })

        return messages
    
    
    
    def _self_reflect(self, draft_answer: str):
        critique_messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict AI editor.\n"
                    "Improve the answer below.\n\n"

                    
                    "RULES:\n"
                    "- Do NOT shorten the answer\n"
                    "- Do NOT remove any sections\n"
                    "- Do NOT convert lists into paragraphs\n"
                    "- Preserve numbering, bullet points, and formatting EXACTLY\n"
                    "- Only fix clarity and correctness\n"
                    "- Do NOT add new information\n"
                    "- Do NOT reference previous conversation\n"
                    "- Do NOT add commentary\n"
                    "- Do NOT say 'Improved answer'\n\n"
                    "Return ONLY the improved answer.\n"
                )
            },
            {
                "role": "user",
                "content": draft_answer
            }
        ]

        

        #refined = self.router.generate_sync(critique_messages)

        # 🔥 CLEAN OUTPUT
        #refined = refined.replace("Improved answer:", "").strip()

        #return refined
    
    # TEMPORARTY PLACEHOLDER — REPLACE WITH BRAIN DECISION
    def should_reflect(self, prompt: str, answer: str) -> bool:
        return False
    #def should_reflect(self, prompt: str, answer: str) -> bool:
        p = prompt.lower()

    # Trigger reflection for complex reasoning
        if any(x in p for x in ["how", "why", "explain", "steps", "analyze"]):
            return True

    # reflect only when complex AND long
        if len(answer) > 500 and any(x in p for x in ["how", "why", "explain"]):
            return True
        

    # Skip for simple factual queries
        if len(answer) < 200:
            return False

        return False

    def _start_worker(self, messages, llm_type="chat"):
        if not self.web_ready:
            self.log("[BLOCK] WebView not ready — delaying generation")
            return
        self.active_worker = LLMWorker(
            router=self.router,
            messages=messages,
            llm_type=llm_type
        )

        self.active_worker.token_received.connect(self.append_stream_token)
        self.active_worker.image_ready.connect(self.on_image_ready)
        self.active_worker.finished.connect(self.on_llm_finished)
        self.active_worker.error.connect(self.on_llm_error)

        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.active_worker.start()

    # =============================
    # LLM (streaming)
    # =============================

    def append_stream_token(self, token: str):
        if not token or not self.web_ready:
            return

        if not self.active_worker:
            return

        # 🔥 REMOVE DUPLICATE TOKENS
        if token == self._last_token:
            return
        self._last_token = token

        self._full_response += token
        self._stream_buffer += token

        if len(self._stream_buffer) >= 20 or token.endswith(("\n", ".", " ")):
            self._run_js(
                Renderer.js_append_token(self._stream_buffer)
            )
            self._stream_buffer = ""

    def on_llm_finished(self):
        self._last_token = ""
        if not self._full_response:
            return

        # 🔥 get full response FIRST
        final = self._full_response.strip()
        self._full_response = ""

        if not final:
            self.log("[LLM] generation stopped")
            self.active_worker = None
            self.send_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            return

        # 🔥 prevent duplicate finalize EARLY
        if self._final_rendered:
            return
        self._final_rendered = True

        self.log("[LLM] generation finished")

        # Ensure worker is stopped
        if self.active_worker:
            self.active_worker.stop()
            self.active_worker.wait()
            self.active_worker = None

        # =============================
        # SMART REFLECTION (DISABLED SAFE)
        # =============================
        if self.should_reflect(self._last_prompt, final):
            self.log("[AI] Running self-reflection...")
            refined = self._self_reflect(final)

            if len(refined) >= len(final) * 0.6:
                if not (("\n1." in final or "\n- " in final) and ("\n1." not in refined and "\n- " not in refined)):
                    final = refined.strip()

        # =============================
        # IMAGE RESPONSE HANDLER
        # =============================
        if final.startswith("__IMAGE__::"):
            parts = final.split("::")

            if len(parts) >= 3:
                full_path = parts[1]
                thumb_path = parts[2]

                self.on_image_ready(full_path, thumb_path)

                self.chat_db.add_message(self.current_chat_id, "assistant", final)

                self.send_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)
                return

        # =============================
        # 🔥 CLEAN STREAM FIRST (IMPORTANT)
        # =============================
        self._stream_buffer = ""
        self._run_js(Renderer.js_clear_stream())

        # =============================
        # RENDER FINAL ANSWER
        # =============================
        self._run_js(
            Renderer.js_finalize(
                Renderer.render_nova_message(final)
            )
        )

        self.chat_db.add_message(self.current_chat_id, "assistant", final)

        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def on_llm_error(self, msg: str):
        self._full_response = ""
        self._stream_buffer = ""
        self._final_rendered = False

        self.log(f"[LLM ERROR] {msg}")
        try:
            html = Renderer.render_nova_message(f"[LLM error] {msg}")
            self._run_js(
                Renderer.js_finalize(html)
            )

        except Exception as e:
            self.log(f"[FATAL UI ERROR] {e}")

    @Slot(str, str)
    def on_image_ready(self, full_path: str, thumb_path: str):
        self.log("[IMAGE] generation complete")
        self.log(f"[IMAGE] file = {full_path}")

        if not full_path or not os.path.exists(full_path):
            self.log("[IMAGE ERROR] Output file missing")
            return

        self.log(f"[IMAGE] Ready: {os.path.basename(full_path)}")

        # stop any active streaming worker
        self._stream_buffer = ""

        if self.active_worker:
            self.active_worker.stop()
            self.active_worker.wait()
            self.active_worker = None



        thumb = thumb_path if thumb_path else full_path

        html = self.renderer.render_image(
            full_path,
            thumb,
            thumb_width=self.settings.get("image", {}).get("thumbnail_width", 256),
        )

        self._run_js(
            Renderer.js_finalize(html)
        )

    def on_delete_chat(self):

        if not self.current_chat_id:
            return

        reply = QMessageBox.question(
            self,
            "Delete Chat",
            "Are you sure you want to delete this chat?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return
        chat_id = self.current_chat_id

            # delete from database
        self.chat_db.delete_chat(chat_id)

        self.log(f"[CHAT] Deleted chat {chat_id}")

            # refresh sidebar
        self._load_chats_from_db()

            # clear UI
        self._run_js("document.getElementById('chat').innerHTML = '';")
        self._run_js(Renderer.js_clear_stream())

            # create new chat automatically
        new_id = self.chat_db.create_chat()
        self._load_chats_from_db()
        self._load_chat_from_db(new_id)

    
    def _execute_decision(self, decision):

        model = decision["model"]
        data = decision["input"]

        if model == "llm":
            messages = data["messages"]

            # Inject mode into system prompt
            if decision["mode"] == "reason":
                messages[0]["content"] += "\nExplain step-by-step."

            elif decision["mode"] == "search":
                messages[0]["content"] += "\nUse web search results."

            llm_type = decision.get("llm_type", "chat")
            self._start_worker(messages, llm_type)

        elif model == "vision":
            image_path = data.get("image_path")
            user_prompt = data.get("prompt", "")

            if not image_path or not os.path.exists(image_path):
                self.log("[VISION BLOCKED] No valid image → fallback to LLM")

                messages = self._build_messages(user_prompt, "normal")
                self._start_worker(messages)
                return

            # 🔥 RUN PIPELINE + LLM DIRECTLY
            result = self.router.run_vision(image_path, user_prompt)

            vision_data = result

            self.log(f"[VISION RAW] {vision_data}")

            # 🔥 DIRECT OUTPUT (NO LLM)
            if isinstance(vision_data, dict):
                from core.smart_layer import SmartLayer

                smart = SmartLayer(self.router)

                ocr_text = vision_data.get("ocr", "")

                

                ocr_text = smart.refine_ocr(ocr_text)

                
            else:
                ocr_text = str(vision_data)

            if not ocr_text.strip():
                ocr_text = vision_data.get("ocr", "[NO TEXT DETECTED]")

            # render directly
            self._run_js(
                Renderer.js_finalize(
                    Renderer.render_nova_message(ocr_text)
                )
            )

            self.chat_db.add_message(
                self.current_chat_id,
                "assistant",
                ocr_text
            )

            # 🔥 CLEAR ATTACHMENT
            self.attachments[self.current_chat_id] = []
            

            

        elif model == "diffusion":
            

            result = self.router.run_diffusion(data)

            full = None
            thumb = None

            if isinstance(result, dict):
                if result.get("status") != "ok":
                    self.log(f"[IMAGE ERROR] {result}")
                    return

                full = (
                    result.get("file") or
                    result.get("full") or
                    result.get("image") or
                    result.get("path")
                )

                thumb = (
                    result.get("thumbnail") or
                    result.get("thumb") or
                    full
                )
                

            elif result:
                full, thumb = result

            if not full:
                self.log("[IMAGE ERROR] No image returned")
                return

            self.on_image_ready(full, thumb)
            self.chat_db.add_message(self.current_chat_id, "assistant", full)

    def _get_context_memory(self):
        if self.current_chat_id not in self.context_memories:
            self.context_memories[self.current_chat_id] = ContextMemory()
        return self.context_memories[self.current_chat_id]

    def _summarize_chat(self, messages):
        text = "\n".join([m["content"] for m in messages])

        summary_prompt = [
            {
                "role": "system",
                "content": "Summarize this conversation.\n"
                            "Focus on:\n"
                            "- main topic\n"
                            "- key concepts discussed\n"
                            "- important user context\n"
                            "Be concise and structured.\n"
                            "Do NOT add unrelated information."
            },
            {
                "role": "user",
                "content": text
            }
        ]

        summary = ""
        for chunk in self.router.run_llm(summary_prompt):
            summary += chunk

        return summary.strip()

    def _extract_facts(self, prompt: str):
        extraction_prompt = [
            {
                "role": "system",
                "content": (
                    "Extract key facts in natural language.\n"
                    "Examples:\n"
                    "- User's name is Kunal\n"
                    "- User uses RTX 3060\n"
                    "- User is learning cybersecurity\n"
                    "\nRules:\n"
                    "- No labels like 'name:'\n"
                    "- No structured keys\n"
                    "- Just short natural sentences\n"
                    "- If nothing important, return NONE."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        result = ""
        for chunk in self.router.run_llm(extraction_prompt):
            result += chunk

        result = result.strip()

        if result and result != "NONE":
            return result

        return None

    def closeEvent(self, event):
        try:
            if self.router:
                if hasattr(self.router.llm_engine, "unload"):
                    self.router.llm_engine.unload()

                if hasattr(self.router.vision_engine, "stop"):
                    self.router.vision_engine.stop()
        except Exception as e:
            print("[CLEANUP ERROR]", e)

        event.accept()