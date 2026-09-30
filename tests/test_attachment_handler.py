"""
Tests for ui.attachment_handler.AttachmentHandler -- attaching files and
building the context block that (as of the main_window.py fix) actually
gets sent to the LLM. Only depends on Pillow, no Qt import needed for the
logic under test (a fake main_window stand-in is used for the log/run_js
calls AttachmentHandler makes back into MainWindow).
"""
import pytest
from PIL import Image

from ui.attachment_handler import AttachmentHandler


class FakeMainWindow:
    def __init__(self):
        self.logs = []
        self.js_calls = []

    def log(self, msg):
        self.logs.append(msg)

    def run_js(self, js):
        self.js_calls.append(js)


@pytest.fixture
def handler():
    return AttachmentHandler(FakeMainWindow())


def test_attach_text_file_builds_context(handler, tmp_path):
    f = tmp_path / "notes.py"
    f.write_text("print('hello from attached file')\n")

    handler.attach_file(1, str(f))
    ctx = handler.get_attachment_context(1)

    assert ctx is not None
    assert ctx["role"] == "system"
    assert "hello from attached file" in ctx["content"]
    assert "notes.py" in ctx["content"]


def test_attach_image_file_records_metadata_not_content(handler, tmp_path):
    img_path = tmp_path / "pic.png"
    Image.new("RGB", (10, 10)).save(img_path)

    handler.attach_file(1, str(img_path))
    atts = handler.attachments[1]
    assert len(atts) == 1
    assert atts[0]["type"] == "image"


def test_no_attachments_returns_none(handler):
    assert handler.get_attachment_context(1) is None


def test_duplicate_attach_is_ignored(handler, tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("hello")
    handler.attach_file(1, str(f))
    handler.attach_file(1, str(f))
    assert len(handler.attachments[1]) == 1


def test_clear_attachments(handler, tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("hello")
    handler.attach_file(1, str(f))
    handler.clear_attachments(1)
    assert handler.get_attachment_context(1) is None


def test_unsupported_extension_is_rejected(handler, tmp_path):
    f = tmp_path / "archive.zip"
    f.write_bytes(b"not really a zip")
    handler.attach_file(1, str(f))
    assert handler.attachments.get(1, []) == []
