"""
Tests for ui.renderer.Renderer -- pure string/HTML generation, no Qt
dependency (renderer.py itself doesn't import PySide6).
"""
from ui.renderer import Renderer


def test_base_html_renders_without_error():
    html = Renderer.base_html()
    assert "<html>" in html
    assert "<div id=\"chat\">" in html


def test_user_message_is_html_escaped():
    # XSS-safety check: a user message containing HTML must come back escaped.
    out = Renderer.render_user_message("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_nova_message_renders_headings_bold_and_code_blocks():
    text = "### Heading\n**bold text**\n```python\nprint(1)\n```"
    out = Renderer.render_nova_message(text)
    assert "<h2>Heading</h2>" in out
    assert "<strong>bold text</strong>" in out
    assert "language-python" in out
    assert "copy-btn" in out


def test_nova_message_with_no_markdown_still_renders():
    out = Renderer.render_nova_message("just a plain reply")
    assert "just a plain reply" in out


def test_js_helpers_produce_valid_looking_snippets():
    assert Renderer.js_clear_stream() == "window.clearStream();"
    assert "appendToken" in Renderer.js_append_token("hi")
    assert "finalizeMessage" in Renderer.js_finalize("<div>x</div>")
