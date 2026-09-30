"""
ui.main_window.MainWindow can't be instantiated in a unit test without a
running QApplication, a display, and (worse) it would try to actually
load the GGUF/vision/diffusion models via BackendRouter/ImageEngine in
__init__. These are static source checks instead, guarding specific
regressions found and fixed during development. They don't require
PySide6 to be installed, so they run anywhere.
"""
from pathlib import Path

SRC = Path(__file__).parent.parent.joinpath("ui", "main_window.py").read_text()


def test_no_duplicate_qtwebenginecore_import():
    # main_window.py used to import QWebEngineSettings/QWebEnginePage from
    # PySide6.QtWebEngineCore twice (once at the top, once again mid-file).
    assert SRC.count("from PySide6.QtWebEngineCore import") == 1


def test_single_chatpage_class_definition():
    assert SRC.count("class ChatPage") == 1


def test_attachment_context_is_wired_into_build_messages():
    # Attached text/code files used to be displayed as a badge only --
    # AttachmentHandler.get_attachment_context() existed but nothing ever
    # called it, so attached file content never reached the model.
    idx = SRC.index("def _build_messages")
    body = SRC[idx: idx + 3000]
    assert "_build_attachment_context(" in body


def test_search_vision_diffusion_run_on_background_thread():
    # These used to call self.tavily.search(...) / self.router.run_vision(...)
    # / self.router.run_diffusion(...) directly on the GUI thread, freezing
    # the window for the duration. They should now route through
    # _run_background (backed by ui.task_worker.TaskWorker).
    idx_search = SRC.index('elif model == "search"')
    idx_vision = SRC.index('elif model == "vision"')
    idx_diffusion = SRC.index('elif model == "diffusion"')
    idx_end = SRC.index("def _run_background")

    assert "_run_background(" in SRC[idx_search:idx_vision]
    assert "_run_background(" in SRC[idx_vision:idx_diffusion]
    assert "_run_background(" in SRC[idx_diffusion:idx_end]


def test_prompt_input_guarded_during_background_work():
    # Send button being disabled didn't stop Enter/returnPressed from
    # re-triggering send_message() while a worker was already running.
    # prompt_input itself must be disabled/re-enabled around every
    # worker/background-task lifecycle.
    assert SRC.count("prompt_input.setEnabled(False)") == 4
    assert SRC.count("prompt_input.setEnabled(True)") == 6


def test_on_image_ready_reenables_send_button_on_success_path():
    # Direct diffusion generation used to leave Send permanently disabled
    # after a successful image, because only the error path re-enabled it.
    idx = SRC.index("def on_image_ready")
    idx_next_def = SRC.index("\n    def ", idx + 10)
    body = SRC[idx:idx_next_def]
    assert "Successfully displayed" in body
    # the re-enable lines must appear AFTER the success log line
    success_pos = body.index("Successfully displayed")
    enable_pos = body.index('send_btn.setEnabled(True)')
    assert enable_pos > success_pos


def test_settings_and_memory_paths_anchored_to_base_dir():
    # These used to be a bare relative path / a path pointing at the wrong
    # directory (see config/config.py and tests around it) -- both
    # regressions traced back to main_window.py not anchoring to BASE_DIR.
    assert "from config.config import SETTINGS_PATH, BASE_DIR" in SRC
    assert 'os.path.join(BASE_DIR, "nova_memory_db")' in SRC


def test_chat_list_does_not_bake_id_into_displayed_title():
    # The sidebar used to build each row as f"{c['id']}::{c['title']}" and
    # display that whole string, so every chat showed an unwanted leading
    # number (e.g. "5::New Chat") regardless of what the user named it.
    # The id must now travel as item data (Qt.UserRole), not as visible
    # text, so a number only ever appears if the user actually renamed a
    # chat to one.
    assert "QListWidgetItem" in SRC
    assert "item.setData(Qt.UserRole, c[\"id\"])" in SRC
    assert 'f"{c[\'id\']}::{c[\'title\']}"' not in SRC
    assert 'item.text().split("::")[0]' not in SRC
