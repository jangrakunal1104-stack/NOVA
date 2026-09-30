# =============================
# NOVA - MainWindow (Stabilized Version)
# =============================
import os
import json

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QListWidget, QListWidgetItem, QLineEdit, QPushButton, QLabel,
    QVBoxLayout, QHBoxLayout, QSizePolicy, QMessageBox, QFileDialog,
    QInputDialog, QTextEdit
)
from PySide6.QtCore import Qt, Slot, QUrl, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

# FIXED IMPORTS - Clean Structure
from core.chat_manager import ChatManager
from ui.llm_worker import LLMWorker
from ui.task_worker import TaskWorker
from ui.agent_worker import AgentWorker
from core.image_engine import ImageEngine
from core.brain import Brain
from core.vector_memory import VectorMemory
from core.backend_router import BackendRouter
from core.tavily_search import TavilySearch

from ui.renderer import Renderer
from ui.jsbridge import JSBridge
from ui.chat_manager_ui import ChatManagerUI
from config.config import SETTINGS_PATH, BASE_DIR

from ui.attachment_handler import AttachmentHandler

os.environ["TOKENIZERS_PARALLELISM"] = "false"


class ChatPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() == "nova-image":
            # path comes as query: nova-image://open?path=/home/...
            path = url.query().replace("path=", "", 1)
            # also handle if it was put in the path part
            if not path or path == url.query():
                path = url.path().lstrip("/")
            path = path.replace("%20", " ")
            if os.path.exists(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                print(f"[IMAGE] Opened: {path}")
            else:
                print(f"[IMAGE] File not found: {path}")
            return False  # block actual navigation
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("NOVA")
        self.resize(1200, 800)

        # Core Components
        self.chat_db = ChatManager()
        self.current_chat_id = None
        self.settings = self.load_settings()

        self.renderer = Renderer()
        self.brain = Brain()
        self.active_worker = None
        self._bg_on_success = None
        self._bg_on_error = None
        # Agent Mode: off by default. When on, send_message() routes the
        # turn through AgentWorker (tool-using loop) instead of Brain's
        # normal chat/search/vision/diffusion routing. See
        # core/agent_engine.py for the loop and core/agent_tools.py for
        # what it's allowed to touch.
        self.agent_mode = False
        self.image_engine = ImageEngine()
        self.attachment_handler = AttachmentHandler(self)
        self.chat_ui = ChatManagerUI(self)
        self.router = BackendRouter(self.image_engine)
        self.tavily = TavilySearch()
        self.vector_memory = VectorMemory(persist_dir=os.path.join(BASE_DIR, "nova_memory_db"))

        # State
        self._js_ready = False
        self.web_ready = False
        self._last_prompt = ""

        # Streaming State
        self.stream = {
            "active": False,
            "full_response": "",
            "buffer": "",
            "last_token": "",
            "finalized": False,
        }
        

        # Build UI
        self._build_ui()
        self._load_chats_from_db()
        self._build_attach_controls()

        # Status bar
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

        # LEFT - Chats
        self.chat_list = QListWidget()
        self.chat_list.itemClicked.connect(self._on_chat_selected)
        

        left = QVBoxLayout()
        left.addWidget(QLabel("Chats"))
        left.addWidget(self.chat_list, stretch=1)
        left.addStretch()

        left_container = QWidget()
        left_container.setLayout(left)
        left_container.setFixedWidth(200)

        # CENTER - Chat + Input
        self.chat_view = QWebEngineView(self)
        self.chat_view.setPage(ChatPage(self.chat_view))
        self.chat_view.setHtml(self.renderer.base_html())
        self.chat_view.loadFinished.connect(self._on_webview_ready)

        # WebChannel Setup
        self.channel = QWebChannel(self.chat_view.page())
        self.jsbridge = JSBridge(self)
        self.channel.registerObject("qt", self.jsbridge)
        self.chat_view.page().setWebChannel(self.channel)

        self.chat_view.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        self.chat_view.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        self.chat_view.settings().setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)

        self.chat_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Input Bar
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

        input_container = QWidget()
        input_container.setLayout(input_bar)
        input_container.setFixedHeight(42)
        input_container.setAttribute(Qt.WA_StyledBackground, True)

        center = QVBoxLayout()
        center.addWidget(self.chat_view, stretch=1)
        center.addWidget(input_container, stretch=0)

        center_container = QWidget()
        center_container.setLayout(center)

        # RIGHT - Options + Logs
        right = QVBoxLayout()
        right.addWidget(QLabel("Chat Options"))

        # Agent Mode: lets NOVA read/write files and run shell commands
        # (approval-gated -- see core/agent_engine.py) instead of only
        # chatting. Off by default; the button's own label always shows
        # the current state so it's never ambiguous whether it's live.
        self.agent_mode_btn = QPushButton("🤖 Agent Mode: OFF")
        self.agent_mode_btn.setCheckable(True)
        self.agent_mode_btn.setToolTip(
            "When ON, NOVA can read/write files and run shell commands in your "
            "home directory. Writes and risky commands still need your approval."
        )
        self.agent_mode_btn.clicked.connect(self.on_toggle_agent_mode)
        right.addWidget(self.agent_mode_btn)

        self.suggest_improvements_btn = QPushButton("🛠️ Suggest Improvements")
        self.suggest_improvements_btn.setToolTip(
            "Ask NOVA to review its own codebase and write proposed improvements "
            "into self_improvement_proposals/ for you to review -- it will not "
            "edit its own live source directly."
        )
        self.suggest_improvements_btn.clicked.connect(self.on_suggest_improvements)
        right.addWidget(self.suggest_improvements_btn)

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

        # Chat Buttons
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

        # Assemble everything
        root_layout.addWidget(left_container)
        root_layout.addWidget(center_container)
        root_layout.addWidget(right_container)
        # ===================================================================
        # NEW: Centralized JavaScript Communication
        # ===================================================================

    def _build_attach_controls(self):
        """Build attach buttons in menu bar"""
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

    def _on_webview_ready(self, ok: bool):
            """Called when the chat WebView finishes loading"""
            if ok:
                self._js_ready = True
                self.web_ready = True
                self.log("[UI] WebView + JavaScript bridge is READY")
        
    def run_js(self, js_code: str):
            """Safely run JavaScript in the chat view"""
            if not self._js_ready:
                # Retry after a short delay if not ready yet
                QTimer.singleShot(300, lambda: self.run_js(js_code))
                return
            
            self.chat_view.page().runJavaScript(js_code)

    

    # =============================
    # PLACEHOLDER BUTTON HANDLERS
    # =============================
    def on_delete_chat(self):
        """Delete current chat"""
        if not self.current_chat_id:
            return
        self.chat_ui.delete_chat()

    def on_new_chat(self):
        self.chat_ui.new_chat()

    def on_clear_chat(self):
        self.chat_ui.clear_chat()

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

    def on_toggle_agent_mode(self, checked: bool):
        self.agent_mode = checked
        self.agent_mode_btn.setText("🤖 Agent Mode: ON" if checked else "🤖 Agent Mode: OFF")
        if checked:
            self.log(
                "[AGENT] Agent Mode enabled — NOVA can now read/write files and run "
                "shell commands in your home directory. Writes and anything beyond "
                "a small read-only command allowlist still need your approval."
            )
        else:
            self.log("[AGENT] Agent Mode disabled.")

    def on_suggest_improvements(self):
        if self.current_chat_id is None:
            return

        if not self.agent_mode:
            self.agent_mode_btn.setChecked(True)
            self.on_toggle_agent_mode(True)

        prompt = (
            "Review NOVA's own codebase for possible improvements -- bugs, unclear "
            "code, missing error handling, performance, or design issues. Use "
            "list_dir and read_file to look through core/ and ui/ as needed (you "
            "don't need to read every file -- prioritize based on what you find). "
            "When you're done, WRITE your findings into self_improvement_proposals/ "
            "using write_file: one .md file per suggestion explaining the issue and "
            "the proposed fix, plus the full proposed replacement file content in a "
            "second file if it's a concrete rewrite. Do not just describe the "
            "changes in chat -- the proposals must actually be written to that "
            "folder so Mr. Black can review them."
        )
        self.prompt_input.setText(prompt)
        self.send_message()

    def _clear_attachments(self):
        if not self.current_chat_id:
            return
        self.attachment_handler.clear_attachments(self.current_chat_id)

    def on_attach_clicked(self):
        self.log("[ATTACH] button clicked")
        dialog = QFileDialog(self, "Attach file")
        # ... keep dialog setup ...
        if dialog.exec() != QFileDialog.Accepted:
            return
        path = dialog.selectedFiles()[0]
        self.attachment_handler.attach_file(self.current_chat_id, path)

    def _attach_file(self, path: str):
        if not self.current_chat_id:
            return
        self.attachment_handler.attach_file(self.current_chat_id, path)

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
        self.run_js(
            f'document.getElementById("chat").insertAdjacentHTML("beforeend", {json.dumps(html)});'
        )

    def _build_attachment_context(self):
        return self.attachment_handler.get_attachment_context(self.current_chat_id)

    def _load_chats_from_db(self):
        self.chat_list.clear()
        chats = self.chat_db.get_all_chats()

        if not chats:
            return

        for c in chats:
            # Display only the chat's actual title -- the id used to be
            # baked into the visible text as "id::title" (e.g. "5::New
            # Chat"), which showed as an unwanted leading number on every
            # chat. The id is still needed to route clicks, so it's stored
            # as item data instead of being rendered into the label.
            item = QListWidgetItem(c["title"])
            item.setData(Qt.UserRole, c["id"])
            self.chat_list.addItem(item)

    def _load_chat_from_db(self, chat_id):

        self.current_chat_id = chat_id

        self.run_js("document.getElementById('chat').innerHTML = '';")
        self.run_js(Renderer.js_clear_stream())

        messages = self.chat_db.get_chat(chat_id)

        for m in messages:
            if m["role"] == "system":
                continue

            if m["role"] == "user":
                html = Renderer.render_user_message(m["content"])
            else:
                html = Renderer.render_nova_message(m["content"])

            self.run_js(
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
        """User clicked Stop button"""
        self.log("[UI] Stop requested")
        self._stop_active_worker()
        
        final = self.stream["full_response"].strip()
        
        if final:
            self.run_js(Renderer.js_clear_stream())
            self.run_js(
                Renderer.js_finalize(
                    Renderer.render_nova_message(final)
                )
            )
            self.chat_db.add_message(self.current_chat_id, "assistant", final)

        self._reset_stream_state()
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.prompt_input.setEnabled(True)

    def _on_chat_selected(self, item):
        chat_id = item.data(Qt.UserRole)
        self.chat_ui.load_chat(chat_id)

    

    

    @Slot(str)
    def openImage(self, path: str):
        """Open image in system default viewer"""
        if not path or not os.path.exists(path):
            self.log(f"[IMAGE] File not found: {path}")
            return
        
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # =============================
    # SEND MESSAGE (STABILIZED)
    # =============================
    def send_message(self):
        prompt = self.prompt_input.text().strip()
        if not prompt or self.current_chat_id is None:
            return

        if self.agent_mode:
            # Skips Brain routing entirely -- Agent Mode is an explicit,
            # user-toggled mode, not something a keyword match should be
            # able to trigger silently, since it can run shell commands.
            self._prepare_ui(prompt)
            self._run_agent_turn()
            return

        # Special greeting handling
        if prompt.lower().strip() in ["hi", "hello", "hey"]:
            self._prepare_ui(prompt)
            response = "Hello Sir! How can I help you today, Mr. Black?"
            self.run_js(Renderer.js_finalize(Renderer.render_nova_message(response)))
            self.chat_db.add_message(self.current_chat_id, "assistant", response)
            self.prompt_input.clear()
            return

        self._last_prompt = prompt

        # === VERY STRONG MEMORY INJECTION ===
        memory_context = self.vector_memory.get_strong_context(prompt) or ""
        if memory_context:
            full_prompt = f"[USER PROFILE]\n{memory_context}\n\nCurrent message: {prompt}"
        else:
            full_prompt = prompt

        # Prepare UI
        self._prepare_ui(prompt)

        # Check for image attachment
        attachments = self.attachment_handler.attachments.get(self.current_chat_id, [])
        image_path = next(
            (att["path"] for att in reversed(attachments) if att.get("type") == "image"),
            None
        )

        if image_path and os.path.exists(image_path):
            print(f"[VISION] ✅ Using attached image: {image_path}")
            decision = {
                "model": "vision",
                "input": {"image_path": image_path, "prompt": full_prompt}
            }
            self.attachment_handler.clear_attachments(self.current_chat_id)
        else:
            # 🔥 IMPORTANT: Pass ORIGINAL prompt to Brain for better detection
            decision = self.brain.decide(
                [{"role": "user", "content": prompt}],   # ← Use raw prompt here
                attachments
            )
            print(f"[DEBUG] Final Decision: {decision.get('model')}")

        self._execute_decision(decision)
    
    def _execute_decision(self, decision):
        """Decision executor: LLM, search, vision, diffusion"""
        model = decision.get("model")
        data = decision.get("input", {})

        if model == "llm":
            mode = decision.get("mode", "normal")
            llm_type = decision.get("llm_type", "chat")
            # Always rebuild full history (Brain only has the current turn)
            messages = self._build_messages(
                data.get("prompt", self._last_prompt),
                mode
            )
            self._start_worker(messages, llm_type)

        elif model == "search":
            # Live web search via Tavily, then answer with LLM.
            # Runs on a background thread (_run_background) so the UI stays
            # responsive during the network call instead of freezing.
            query = data.get("prompt", self._last_prompt)
            self.log(f"[TAVILY] Searching: {query[:80]}...")
            self.send_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.prompt_input.setEnabled(False)

            def _do_search():
                results = self.tavily.search(query, max_results=5)
                return self.tavily.format_for_prompt(results), len(results)

            def _on_search_done(result):
                search_block, n_results = result
                print(f"[TAVILY] Got {n_results} result(s)")

                messages = self._build_messages(query)
                search_msg = {
                    "role": "system",
                    "content": (
                        search_block
                        + "\n\nAnswer the user's question using the search results above. "
                        "Be factual and concise. Mention sources when useful. "
                        "If results are weak, say so honestly."
                    )
                }
                if messages and messages[0].get("role") == "system":
                    messages.insert(1, search_msg)
                else:
                    messages.insert(0, search_msg)

                # Hands off to the normal LLM worker/thread for the actual
                # streamed answer.
                self._start_worker(messages, "chat")

            self._run_background(
                _do_search,
                _on_search_done,
                lambda err: self.on_llm_error(f"Search failed: {err}"),
            )

        elif model == "vision":
            image_path = data.get("image_path")
            user_prompt = data.get("prompt", self._last_prompt)
            if image_path and os.path.exists(image_path):
                self.send_btn.setEnabled(False)
                self.stop_btn.setEnabled(False)
                self.prompt_input.setEnabled(False)
                self.log("[VISION] Analyzing image...")

                self._run_background(
                    lambda: self.router.run_vision(image_path, user_prompt),
                    self._handle_vision_result,
                    lambda err: self.on_llm_error(f"Vision error: {err}"),
                )
            else:
                self._start_worker(self._build_messages(user_prompt))

        elif model == "diffusion":
            self.send_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.prompt_input.setEnabled(False)
            self.log("[DIFFUSION] Generating image...")

            def _on_diffusion_done(result):
                if isinstance(result, dict) and result.get("status") == "ok":
                    self.on_image_ready(result.get("file"), result.get("thumbnail"))
                else:
                    err = result.get("error", "Failed to generate image") if isinstance(result, dict) else "Failed to generate image"
                    self.on_llm_error(err)

            self._run_background(
                lambda: self.router.run_diffusion(data),
                _on_diffusion_done,
                lambda err: self.on_llm_error(f"Diffusion error: {err}"),
            )

        else:
            self.on_llm_error(f"Unknown decision model: {model}")

    def _run_background(self, fn, on_success, on_error=None):
        """
        Run a blocking callable (Tavily search / Vision / Diffusion) on a
        background QThread (TaskWorker) so the GUI thread never blocks.

        IMPORTANT: on_success/on_error are plain closures, not bound methods
        of this QObject, so Qt has no way to know they belong to the GUI
        thread if connected directly to the worker's signals — it would run
        them on the worker thread instead, which isn't safe for code that
        touches Qt widgets, sqlite, or self.chat_db. Instead we connect the
        worker's signals to _on_bg_result/_on_bg_error, which ARE bound
        methods of this QObject, so Qt correctly queues them onto the GUI
        thread; those two then simply call the stashed closures, which by
        that point are already executing on the right thread.
        """
        self._stop_active_worker()

        self._bg_on_success = on_success
        self._bg_on_error = on_error or self.on_llm_error

        worker = TaskWorker(fn)
        worker.result_ready.connect(self._on_bg_result)
        worker.error.connect(self._on_bg_error)
        self.active_worker = worker
        worker.start()

    @Slot(object)
    def _on_bg_result(self, result):
        cb, self._bg_on_success, self._bg_on_error = self._bg_on_success, None, None
        if cb:
            cb(result)

    @Slot(str)
    def _on_bg_error(self, msg):
        cb, self._bg_on_success, self._bg_on_error = self._bg_on_error, None, None
        if cb:
            cb(msg)

    # =============================
    # AGENT MODE (tool-using loop)
    # =============================
    def _run_agent_turn(self):
        """
        Kicks off one Agent Mode turn on a background thread (AgentWorker).
        _prepare_ui() has already rendered the user's message and saved it
        to chat_db/vector_memory by the time this runs (see send_message).
        """
        self._stop_active_worker()

        history = self.chat_db.get_messages_for_llm(self.current_chat_id)
        history = [m for m in history if (m.get("content") or "").strip()]

        self.log("[AGENT] Starting agent turn...")

        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.prompt_input.setEnabled(False)

        worker = AgentWorker(self.router, history)
        worker.step.connect(self._on_agent_step)
        worker.approval_requested.connect(self._on_agent_approval_requested)
        worker.finished.connect(self._on_agent_finished)
        worker.error.connect(self._on_agent_error)
        self.active_worker = worker
        worker.start()

    @Slot(str, str)
    def _on_agent_step(self, kind: str, text: str):
        """Renders each step of the agent loop into the chat as it
        happens, so tool calls and their results are visible, not just
        the final answer -- this is meant to be legible, not a hidden
        black box running commands on the user's machine."""
        if kind == "tool_call":
            self.log(f"[AGENT] 🔧 {text}")
            self.run_js(Renderer.js_finalize(
                Renderer.render_nova_message(f"🔧 **Running:** `{text}`")
            ))
        elif kind == "tool_result":
            preview = text if len(text) <= 800 else text[:800] + "\n…[truncated for display; the model saw the full result]"
            self.run_js(Renderer.js_finalize(
                Renderer.render_nova_message(f"```\n{preview}\n```")
            ))
        elif kind == "final":
            self.run_js(Renderer.js_finalize(Renderer.render_nova_message(text)))
            if self.current_chat_id is not None:
                self.chat_db.add_message(self.current_chat_id, "assistant", text)

    @Slot(str, str, object)
    def _on_agent_approval_requested(self, kind: str, summary: str, box_event):
        """
        Runs on the GUI thread (queued there by Qt because this slot is a
        bound method of a QObject living on that thread -- see
        ui/agent_worker.py's module docstring for the full mechanism).
        Shows a real confirmation dialog and unblocks the worker thread,
        which has been waiting on `event` since it emitted this signal.
        """
        box, event = box_event
        try:
            reply = QMessageBox.question(
                self,
                "NOVA Agent — Approval Needed",
                f"NOVA wants to:\n\n{summary}\n\nAllow this?",
                QMessageBox.Yes | QMessageBox.No,
            )
            box["approved"] = (reply == QMessageBox.Yes)
        finally:
            event.set()

    @Slot()
    def _on_agent_finished(self):
        self.log("[AGENT] Agent turn finished")
        self._stop_active_worker()
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.prompt_input.setEnabled(True)

    @Slot(str)
    def _on_agent_error(self, msg: str):
        # finished is always emitted right after this (AgentWorker.run()'s
        # finally block), which does the actual cleanup/button re-enable --
        # same two-signal pattern on_llm_error/on_llm_finished already use.
        self.log(f"[AGENT ERROR] {msg}")
        self.run_js(Renderer.js_finalize(
            Renderer.render_nova_message(f"❌ Agent Mode error: {msg}")
        ))



    # =============================
    # YOUR ORIGINAL METHODS (Kept 100% intact)
    # =============================
    def _prepare_ui(self, prompt: str):
        self.prompt_input.clear()
        self.run_js(Renderer.js_clear_stream())
        
        self.stream = {  
            "active": True,
            "full_response": "",
            "buffer": "",
            "last_token": "",
            "finalized": False,
        }

        # Add to memory FIRST
        self.vector_memory.add(
            text=prompt,
            metadata={"role": "user", "chat_id": str(self.current_chat_id)}
        )

        self.chat_db.add_message(self.current_chat_id, "user", prompt)
        self.chat_db.auto_rename_if_needed(self.current_chat_id, prompt)

        user_html = Renderer.render_user_message(prompt)
        self.run_js(Renderer.js_finalize(user_html))

    def switch_chat(self, chat_id: int):
        if chat_id == self.current_chat_id:
            return

        self.current_chat_id = chat_id

        # Update selection in left panel
        for i in range(self.chat_list.count()):
            item = self.chat_list.item(i)
            if item and item.data(Qt.UserRole) == chat_id:
                self.chat_list.setCurrentRow(i)
                break

        # Load messages
        messages = self.chat_db.list_messages(chat_id)

        # Safe rendering
        if hasattr(Renderer, 'render_chat_history'):
            html = Renderer.render_chat_history(messages)
        elif hasattr(Renderer, 'render_messages'):
            html = Renderer.render_messages(messages)
        else:
            html = "<br>".join([f"<b>{m.get('role', 'user')}:</b> {m.get('content','')[:200]}" 
                              for m in messages])

        self.run_js(f"document.getElementById('chat').innerHTML = {json.dumps(html)};")
        self.log(f"Switched to chat {chat_id}")

    def _start_worker(self, messages, llm_type: str = "chat"):
        """Simplified for single fine-tuned model"""
        if not self._js_ready:
            self.log("[UI] WebView not ready yet")
            return

        self._stop_active_worker()

        # No more model switching needed
        print(f"[WORKER] Starting generation with single fine-tuned model")

        self.active_worker = LLMWorker(
            router=self.router,
            messages=messages,
            llm_type="chat"          # Always use "chat" now
        )

        self.active_worker.token_received.connect(self.append_stream_token)
        self.active_worker.image_ready.connect(self.on_image_ready)
        self.active_worker.finished.connect(self.on_llm_finished)
        self.active_worker.error.connect(self.on_llm_error)

        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.prompt_input.setEnabled(False)
        self.active_worker.start()

    def _stop_active_worker(self):
        if self.active_worker:
            try:
                self.active_worker.stop()
                self.active_worker.wait()
            except:
                pass
            self.active_worker = None

    

    def closeEvent(self, event):
        self._stop_active_worker()
        try:
            if hasattr(self.image_engine, "unload"):
                self.image_engine.unload()
        except Exception as e:
            print(f"[CLEANUP] {e}")
        event.accept()
    
    def _handle_vision_result(self, result):
        """Handle result from Vision model"""
        if isinstance(result, dict) and "ocr" in result:
            text = result.get("ocr", "").strip()
        else:
            text = str(result).strip()

        if not text:
            text = "No text could be extracted from the image."

        print(f"[VISION] Final result length: {len(text)} chars")

        self.run_js(
            Renderer.js_finalize(
                Renderer.render_nova_message(text)
            )
        )
        self.chat_db.add_message(self.current_chat_id, "assistant", text)
        self._reset_stream_state()
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.prompt_input.setEnabled(True)

    def _reset_stream_state(self):
        """Reset streaming state"""
        self.stream = {
            "active": False,
            "full_response": "",
            "buffer": "",
            "last_token": "",
            "finalized": False,
        }

    # =============================
    # MISSING STREAMING METHODS
    # =============================

    def on_image_ready(self, full_path: str, thumb_path: str):
        """Handle generated image - Stabilized"""
        self.log(f"[IMAGE] Generation complete: {os.path.basename(full_path)}")
        
        if not full_path or not os.path.exists(full_path):
            self.log("[IMAGE ERROR] Output file missing")
            self.on_llm_error("Image generation failed - file not found")
            return

        self._stop_active_worker()
        thumb = thumb_path if thumb_path and os.path.exists(thumb_path) else full_path

        try:
            html = self.renderer.render_image(
                full_path,
                thumb,
                thumb_width=self.settings.get("image", {}).get("thumbnail_width", 256),
            )
            self.run_js(Renderer.js_finalize(html))
            self.chat_db.add_message(self.current_chat_id, "assistant", f"__IMAGE__::{full_path}::{thumb}")
            self.log("[IMAGE] Successfully displayed")
            # NOTE: this used to be missing on the success path, which left
            # Send permanently disabled after a direct (non-LLM-triggered)
            # diffusion generation succeeded.
            self._reset_stream_state()
            self.send_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.prompt_input.setEnabled(True)
        except Exception as e:
            self.log(f"[IMAGE RENDER ERROR] {e}")
            self.on_llm_error("Failed to display generated image")

    def append_stream_token(self, token: str):
        """Append token during streaming"""
        if not token or not self._js_ready:
            return
        if not self.active_worker:
            return

        # Avoid duplicate tokens
        if token == self.stream["last_token"]:
            return
        self.stream["last_token"] = token

        self.stream["full_response"] += token
        self.stream["buffer"] += token

        # Flush buffer
        if len(self.stream["buffer"]) >= 20 or token.endswith(("\n", ".", "!", "?", " ")):
            self.run_js(
                Renderer.js_append_token(self.stream["buffer"])
            )
            self.stream["buffer"] = ""

    def on_llm_finished(self):
        """Called when LLM generation completes"""
        self.log("[LLM] Generation finished")

        final = self.stream["full_response"].strip()
        self._stop_active_worker()

        if not final:
            self._reset_stream_state()
            self.send_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.prompt_input.setEnabled(True)
            return

        self.run_js(Renderer.js_clear_stream())

        if final.startswith("__IMAGE__::"):
            parts = final.split("::")
            if len(parts) >= 3:
                self.on_image_ready(parts[1], parts[2])
        else:
            self.run_js(
                Renderer.js_finalize(
                    Renderer.render_nova_message(final)
                )
            )
            self.chat_db.add_message(self.current_chat_id, "assistant", final)

        self._reset_stream_state()
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.prompt_input.setEnabled(True)

    def on_llm_error(self, msg: str):
        """Handle LLM errors"""
        self.log(f"[LLM ERROR] {msg}")
        error_text = f"❌ Sorry, something went wrong: {msg}"
        
        self.run_js(Renderer.js_clear_stream())
        self.run_js(
            Renderer.js_finalize(
                Renderer.render_nova_message(error_text)
            )
        )
        
        self._reset_stream_state()
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.prompt_input.setEnabled(True)

    def _build_messages(self, prompt: str, mode="normal"):
        """
        Clean multi-turn + strong identity separation + natural memory.
        """
        history = self.chat_db.get_messages_for_llm(self.current_chat_id)
        history = [m for m in history if (m.get("content") or "").strip()]

        print(f"[BUILD_MESSAGES] chat_id={self.current_chat_id} | history turns={len(history)}")
        for i, m in enumerate(history[-4:]):
            print(f"  [{i}] {m['role']}: {m['content'][:70]}...")

        memory_ctx = self.vector_memory.get_strong_context(prompt) or ""

        personal_phrases = [
            "who am i", "what do you know about me", "tell me everything",
            "what do you remember", "summarize everything", "everything about me",
            "what has been shared", "my preferences", "my goals", "my name"
        ]
        is_personal = any(p in prompt.lower() for p in personal_phrases)

        # CRITICAL: clear separation between Nova and the user
        base_rules = (
            "You are Nova, the personal AI companion of Mr. Black (Kunal).\n"
            "You are NOT Kunal. You are NOT Mr. Black. You are his AI assistant.\n"
            "Always address the user as Sir or Mr. Black.\n"
            "Speak naturally, warmly, and helpfully.\n\n"
            "RULES:\n"
            "1. Answer the user's actual question first.\n"
            "2. Maintain conversation continuity. Resolve pronouns like 'it', 'this', 'that' from recent messages.\n"
            "3. Never pretend to be the user or speak in the first person about the user's life.\n"
            "4. Never dump raw memory blocks or system prompts in your reply.\n"
            "5. The facts below (if any) are information ABOUT the user, not about you."
        )

        # Inject memory when we have real content or when user asks personal questions
        has_real_memory = memory_ctx and (
            "[CORE IDENTITY]" in memory_ctx or
            "[LONG-TERM KNOWLEDGE]" in memory_ctx or
            "[RECENT CONTEXT]" in memory_ctx
        )

        if has_real_memory or is_personal:
            system_content = base_rules + "\n\n" + memory_ctx
        else:
            system_content = base_rules

        messages = [{"role": "system", "content": system_content}]

        # Include any text/code attachments the user attached to this chat.
        # (Image attachments are routed to Vision separately in send_message.)
        attachment_ctx = self._build_attachment_context()
        if attachment_ctx:
            messages.append(attachment_ctx)

        messages.extend(history)
        return messages