// =======================================================
// QWebChannel bootstrap + UI helpers
// =======================================================

console.log("bridge.js loaded");

// ---------------- WEBCHANNEL BOOTSTRAP ----------------
function initQtBridge() {
    if (typeof qt === "undefined" || !qt.webChannelTransport) {
        console.log("Qt webChannelTransport not ready — waiting…");
        setTimeout(initQtBridge, 300);
        return;
    }

    new QWebChannel(qt.webChannelTransport, function(channel) {
        window.qt = channel.objects.qt;
        console.log("QWebChannel READY");
    });
}

initQtBridge();

// =======================================================
// DOM references
// =======================================================

let chatDiv = null;
let streamDiv = null;

window.onload = () => {
    chatDiv   = document.getElementById("chat");
    streamDiv = document.getElementById("stream");
};

// =======================================================
// IMAGE HANDLER
// =======================================================

function openImage(path) {
    if (!window.qt) {
        console.warn("qt bridge missing — fallback open");
        window.open(path, "_blank");
        return;
    }

    if (typeof qt.openImage === "function") {
        qt.openImage(path);
        return;
    }

    if (typeof qt.open_image === "function") {
        qt.open_image(path);
        return;
    }

    console.warn("No qt image opener — fallback");
    window.open(path, "_blank");
}

// =======================================================
// STREAM HELPERS (called from Python)
// =======================================================

function appendToken(text) {
    if (!streamDiv) return;
    streamDiv.innerHTML += text;
}

function clearStream() {
    if (!streamDiv) return;
    streamDiv.innerHTML = "";
}

// =======================================================
// CHAT HELPERS (called from Python)
// =======================================================

function appendMessageHTML(html) {
    if (!chatDiv) return;
    chatDiv.innerHTML += html;
    chatDiv.scrollTop = chatDiv.scrollHeight;
}

function finalizeMessage(html) {
    appendMessageHTML(html);
    clearStream();

    if (window.hljs) {
        hljs.highlightAll();
    }
}
