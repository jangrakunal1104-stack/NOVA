from pathlib import Path
import json
from string import Template
import re
import html
import base64

CODE_BLOCK_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)

class Renderer:
    ROOT = Path(__file__).resolve().parent
    STATIC = ROOT / "static"
    DRACULA_CSS = STATIC / "dracula.css"
    HLJS_JS = STATIC / "highlight.min.js"
    QWEBCHANNEL_JS = STATIC / "qwebchannel.js"

    @staticmethod
    def _file_url(path: Path) -> str:
        return f"file://{path.resolve()}"

    @staticmethod
    def base_html() -> str:
        dracula = Renderer._file_url(Renderer.DRACULA_CSS)
        hljs = Renderer._file_url(Renderer.HLJS_JS)
        qweb = "qrc:///qtwebchannel/qwebchannel.js"
        bridge = Renderer._file_url(Renderer.STATIC / "bridge.js")

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>NOVA • Mr. Black</title>
            <link rel="stylesheet" href="{dracula}">
            <script src="{hljs}"></script>
            <script src="{qweb}"></script>
            <script src="{bridge}"></script>

            <style>
                body {{
                    background: #050505;
                    color: #e0e0e0;
                    font-family: system-ui, sans-serif;
                    margin:0; padding:12px;
                    line-height: 1.75;
                }}
                .msg {{
                    margin: 18px 0;
                    padding: 16px 20px;
                    border-radius: 12px;
                    max-width: 92%;
                }}
                .user-msg {{ background: #1e40af; margin-left: auto; border-bottom-right-radius: 4px; }}
                .nova-msg {{ background: #1f2937; margin-right: auto; border-bottom-left-radius: 4px; }}

                h2 {{
                    color: #67e8f9;
                    font-size: 1.55em;
                    margin: 1.8em 0 0.8em 0;
                    border-bottom: 2px solid #334155;
                    padding-bottom: 10px;
                }}

                strong {{ color: #93c5fd; font-weight: 600; }}

                ol {{ padding-left: 1.6em; margin: 14px 0; }}
                ol li {{ margin: 10px 0; }}

                pre {{
                    background: #0f172a;
                    padding: 16px;
                    border-radius: 10px;
                    overflow-x: auto;
                    position: relative;
                    border: 1px solid #334155;
                }}
                code {{
                    font-family: 'Fira Code', Consolas, monospace;
                    font-size: 0.95em;
                }}
                .copy-btn {{
                    position: absolute; top: 12px; right: 12px;
                    background: #1e2937; color: #94a3b8;
                    border: none; padding: 6px 14px; border-radius: 6px;
                    cursor: pointer; font-size: 0.82em;
                }}
                .copy-btn:hover {{ background: #334155; color: white; }}
            </style>
        </head>
        <body>
            <div id="chat"></div>
            <div id="stream"></div>

            <script>
            function copyCode(btn) {{
                const code = btn.parentElement.querySelector('code').innerText;
                navigator.clipboard.writeText(code);
                const orig = btn.textContent;
                btn.textContent = 'Copied!';
                setTimeout(() => btn.textContent = orig, 1800);
            }}

            window.appendToken = function(text) {{
                const stream = document.getElementById("stream");
                if (stream && text) {{
                    stream.innerHTML += text.replace(/\\n/g, "<br>");
                    document.getElementById("chat").scrollTop = document.getElementById("chat").scrollHeight;
                }}
            }};

            window.clearStream = function() {{
                const stream = document.getElementById("stream");
                if (stream) stream.innerHTML = "";
            }};

            window.finalizeMessage = function(html) {{
                const chat = document.getElementById("chat");
                if (chat) {{
                    chat.innerHTML += html;
                    chat.scrollTop = chat.scrollHeight;
                }}
                window.clearStream();
                if (typeof hljs !== 'undefined') {{
                    setTimeout(() => hljs.highlightAll(), 100);
                }}
            }};

            window.openImage = function(path) {{
                path = (path || "").toString().replace(/^["']|["']$/g, "");

                function tryOpen() {{
                    if (window.qt) {{
                        if (typeof window.qt.openImage === "function") {{
                            window.qt.openImage(path);
                            return true;
                        }}
                        if (typeof window.qt.open_image === "function") {{
                            window.qt.open_image(path);
                            return true;
                        }}
                    }}
                    return false;
                }}

                if (tryOpen()) return;

                var attempts = 0;
                var timer = setInterval(function() {{
                    attempts = attempts + 1;
                    if (tryOpen() || attempts >= 10) {{
                        clearInterval(timer);
                        if (attempts >= 10) {{
                            console.warn("openImage: Qt bridge never became ready", path);
                            window.open("file://" + path, "_blank");
                        }}
                    }}
                }}, 200);
            }};
            </script>
        </body>
        </html>
        """
        return html

    @staticmethod
    def render_user_message(text: str) -> str:
        return f'<div class="msg user-msg"><strong style="color:#93c5fd;">You</strong><br>{html.escape(text)}</div>'

    @staticmethod
    def render_nova_message(text: str) -> str:
        if text.startswith("__IMAGE__::"):
            parts = text.split("::")
            if len(parts) == 3:
                return Renderer.render_image(parts[1], parts[2])

        content = Renderer.render_markdown_code(text)
        return f'<div class="msg nova-msg"><strong style="color:#67e8f9;">Nova</strong><br>{content}</div>'

    @staticmethod
    def render_markdown_code(text: str) -> str:
        # Convert all ### headings to beautiful h2
        text = re.sub(r'^###\s+(.+?)(:)?$', 
                     r'<h2>\1</h2>', 
                     text, flags=re.MULTILINE)

        # Support for #### sub-headings if any
        text = re.sub(r'^####\s+(.+?)(:)?$', 
                     r'<h3 style="color:#93c5fd; font-size:1.35em;">\1</h3>', 
                     text, flags=re.MULTILINE)

        # Bold numbered points like "1. **Cleaning the String**:"
        text = re.sub(r'(\d+)\.\s+\*\*(.+?)\*\*:?', 
                     r'<strong>\1. \2:</strong>', text)

        # General bold text
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

        # Code blocks with copy button
        def repl(m):
            lang = (m.group(1) or "python").strip()
            code = html.escape(m.group(2))
            return f'<pre><code class="language-{lang}">{code}</code><button class="copy-btn" onclick="copyCode(this)">Copy</button></pre>'

        text = CODE_BLOCK_RE.sub(repl, text)
        return text.replace("\n", "<br>")

    @staticmethod
    def render_image(full_path: str, thumb_path: str | None, thumb_width: int = 512) -> str:
        full = Path(full_path)
        thumb = Path(thumb_path) if thumb_path else full

        try:
            with open(thumb, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            img_src = f"data:image/png;base64,{encoded}"
        except Exception:
            img_src = f"file://{full.resolve()}"

        # Custom scheme that Python will intercept
        open_url = f"nova-image://open?path={full.resolve()}"

        return (
            f'<div class="nova-image">'
            f'<a href="{open_url}" title="Click to open">'
            f'<img src="{img_src}" '
            f'style="max-width:{thumb_width}px;height:auto;border-radius:10px;'
            f'border:1px solid #475569;cursor:pointer;">'
            f'</a></div>'
        )
    @staticmethod
    def js_clear_stream() -> str: return "window.clearStream();"
    @staticmethod
    def js_append_token(text: str) -> str: return f"window.appendToken({json.dumps(text)});"
    @staticmethod
    def js_finalize(html: str) -> str: return f"window.finalizeMessage({json.dumps(html)});"