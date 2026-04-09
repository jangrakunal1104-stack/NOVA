from pathlib import Path
import json
from string import Template
import re
import html
import base64
from matplotlib.pylab import full

CODE_BLOCK_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)

INLINE_CODE_FIX_RE = re.compile(
    r"```(\w+)\s+(.*?)```",
    re.DOTALL
)


class Renderer:
    ROOT = Path(__file__).resolve().parent

    STATIC = ROOT / "static"
    DRACULA_CSS = STATIC / "dracula.css"
    HLJS_JS = STATIC / "highlight.min.js"
    QWEBCHANNEL_JS = STATIC / "qwebchannel.js"

    @staticmethod
    def _file_url(path: Path) -> str:
        return f"file://{path.resolve()}"

    # ------------------------------------------------------------------
    # BASE HTML
    # ------------------------------------------------------------------
    @staticmethod
    def base_html() -> str:
        dracula = Renderer._file_url(Renderer.DRACULA_CSS)
        hljs = Renderer._file_url(Renderer.HLJS_JS)
        qweb = "qrc:///qtwebchannel/qwebchannel.js"
        bridge = Renderer._file_url(Renderer.STATIC / "bridge.js")

        tpl = Template("""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">

            <link rel="stylesheet" href="$dracula">
            <script src="$hljs"></script>
            <script src="$qweb"></script>
            <script src="$bridge"></script>

            <script>
            /* ===============================
            QT WEBCHANNEL INIT
            =============================== */
            function initQtBridge() {
                if (typeof qt === "undefined" || !qt.webChannelTransport) {
                    setTimeout(initQtBridge, 300);
                    return;
                }

                new QWebChannel(qt.webChannelTransport, function(channel) {
                    window.qt = channel.objects.qt;
                    console.log("QWebChannel READY");
                });
            }
            initQtBridge();

            /* ===============================
            DOM HELPERS
            =============================== */
            function getChatDiv() {
                return document.getElementById("chat");
            }

            function getStreamDiv() {
                return document.getElementById("stream");
            }

            /* ===============================
            IMAGE HANDLER
            =============================== */
            function openImage(path) {
                if (window.qt && typeof qt.openImage === "function") {
                    qt.openImage(path);
                } else {
                    window.open(path, "_blank");
                }
            }

            /* ===============================
            STREAMING (GLOBAL SAFE)
            =============================== */
            window.appendToken = function(text) {
                const streamDiv = getStreamDiv();
                const chatDiv = getChatDiv();

                if (!streamDiv || !text) return;

                const escaped = text
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .split(String.fromCharCode(10)).join("<br>");

                streamDiv.insertAdjacentHTML("beforeend", escaped);

                if (chatDiv) {
                    chatDiv.scrollTop = chatDiv.scrollHeight;
                }
            };

            window.clearStream = function() {
                const streamDiv = getStreamDiv();
                if (streamDiv) streamDiv.innerHTML = "";
            };

            /* ===============================
            FINALIZE
            =============================== */
            window.finalizeMessage = function(html) {
                const chatDiv = getChatDiv();
                if (!chatDiv) return;

                chatDiv.innerHTML += html;
                chatDiv.scrollTop = chatDiv.scrollHeight;

                window.clearStream();

                if (window.hljs) {
                    hljs.highlightAll();
                }
            };
            </script>

            <style>
            body {
                background: #0c0c0c;
                color: #e6e6e6;
                font-family: "Fira Code", monospace;
                margin: 0;
                padding: 12px;
            }

            .msg {
                margin: 10px 0;
                line-height: 1.5;
            }

            .nova-image {
                margin: 6px 0;
            }

            .nova-thumb {
                border-radius: 8px;
                border: 1px solid #444;
                cursor: pointer;
            }
            </style>
        </head>

        <body>
            <div id="chat"></div>
            <div id="stream"></div>
        </body>
        </html>
        """)

        return tpl.substitute(
            dracula=dracula,
            hljs=hljs,
            qweb=qweb,
            bridge=bridge,
        )

    # ------------------------------------------------------------------
    # MESSAGE RENDERERS
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_code_blocks(text: str) -> str:
        return INLINE_CODE_FIX_RE.sub(
            lambda m: f"```{m.group(1)}\n{m.group(2)}\n```",
            text
        )

    @staticmethod
    def render_markdown_code(text: str) -> str:
        text = Renderer.normalize_code_blocks(text)

        def repl(m):
            lang = m.group(1) or ""
            code = html.escape(m.group(2))
            return f'<pre><code class="language-{lang}">{code}</code></pre>'

        parts = []
        last = 0

        for m in CODE_BLOCK_RE.finditer(text):
            # escape text before code block
            parts.append(html.escape(text[last:m.start()]))

            lang = m.group(1) or ""
            code = html.escape(m.group(2))
            parts.append(f'<pre><code class="language-{lang}">{code}</code></pre>')

            last = m.end()

        # escape remaining text
        parts.append(html.escape(text[last:]))

        rendered = "".join(parts)
        return rendered.replace("\n", "<br>")

    @staticmethod
    def render_user_message(text: str) -> str:
        return f"""
        <div class="msg">
          <div style="color:#8be9fd;font-size:0.85em;">You</div>
          <div>{text}</div>
        </div>
        """

    @staticmethod
    def render_nova_message(text: str) -> str:

        # =============================
        # IMAGE MESSAGE HANDLING
        # =============================
        if text.startswith("__IMAGE__::"):
            parts = text.split("::")

            if len(parts) == 3:
                full_path = parts[1]
                thumb_path = parts[2]

                image_html = Renderer.render_image(full_path, thumb_path)

                return f"""
                <div class="msg">
                <div style="color:#50fa7b;font-size:0.85em;">Nova</div>
                <div>{image_html}</div>
                </div>
                """

        # -----------------------------
        # NORMAL TEXT
        # -----------------------------
        content = Renderer.render_markdown_code(text)

        return f"""
        <div class="msg">
        <div style="color:#50fa7b;font-size:0.85em;">Nova</div>
        <div>{content}</div>
        </div>
        """

    # ------------------------------------------------------------------
    # IMAGE RENDERER (FINAL)
    # ------------------------------------------------------------------
    @staticmethod
    def render_image(full_path: str, thumb_path: str | None, thumb_width: int = 256) -> str:
        full = Path(full_path)
        thumb = Path(thumb_path) if thumb_path else full

        # 🔥 Convert image to base64
        with open(thumb, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        img_src = f"data:image/png;base64,{encoded}"

        return f"""
        <div class="msg nova-image">
            <img
                src="{img_src}"
                style="
                    width: {thumb_width}px;
                    height: auto;
                    display: block;
                    cursor: pointer;
                    border-radius: 8px;
                "
                onclick="openImage('{full.resolve()}')"
            />
        </div>
        """

    # ------------------------------------------------------------------
    # STREAM HELPERS
    # ------------------------------------------------------------------
    @staticmethod
    def js_clear_stream() -> str:
        return "if (window.clearStream) clearStream();"

    @staticmethod
    def js_append_token(text: str) -> str:
        return f"""
        if (window.appendToken) {{
            appendToken({json.dumps(text)});
        }}
        """

    @staticmethod
    def js_finalize(html: str) -> str:
        return f"""
        if (window.finalizeMessage) {{
            finalizeMessage({json.dumps(html)});
        }}
        """
