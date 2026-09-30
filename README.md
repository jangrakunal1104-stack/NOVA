# NOVA 🔥

**Local-first multi-model AI companion (LLM + Vision + Diffusion + live web search + memory)**

---

## 🚀 Overview

NOVA is a personal AI runtime built around a locally-hosted fine-tuned GGUF model, with vision and image
generation add-ons, persistent vector memory, and live internet access via Tavily. It runs as a desktop
app (PySide6) with a streaming chat UI.

---

## ⚡ Features

* ✅ Token-by-token streaming responses
* ✅ Local GGUF chat model (llama.cpp / llama-cpp-python)
* ✅ Vision — image understanding via Qwen2-VL
* ✅ Image generation (Stable Diffusion 1.5)
* ✅ Live internet/web search via Tavily, injected into the model's context
* ✅ Long-term vector memory (Chroma + sentence-transformers), hierarchical: core identity / long-term
  facts / recent context
* ✅ File attachments (text + code files are read into context; images are routed to Vision)
* ✅ Chat history (SQLite), multi-chat, auto-rename, export, delete
* ✅ GPU-aware execution (loads/unloads models to stay within VRAM)

---

## 🧠 Architecture

### 1. Brain (`core/brain.py`)
Looks at the latest user message (and any attachments) and decides where it should go:
LLM chat, Vision, Diffusion, or live web Search.

### 2. Backend Router (`core/backend_router.py`)
Central execution controller for the LLM, Vision, and Diffusion engines. Coordinates with the GPU
arbiter so only one heavy model is resident at a time.

### 3. Model Loader (`core/model_loader.py`)
Loads the fine-tuned GGUF model via `llama-cpp-python`, with GPU offloading and streaming generation.

### 4. Tavily Search (`core/tavily_search.py`)
Live internet access. When the Brain detects a query about current events, news, prices, or anything
time-sensitive, results are fetched from Tavily and injected into the model's system prompt before it
answers — see **Live internet access** below for setup.

### 5. Vector Memory (`core/vector_memory.py`)
Chroma-backed hierarchical memory (core identity / long-term / episodic), queried on every turn and
injected into the system prompt when relevant.

### 6. Vision (`core/vision_qwen.py`)
Qwen2-VL image understanding — used automatically when an image is attached.

### 7. Diffusion (`core/image_engine.py`)
Stable Diffusion 1.5 pipeline with prompt enhancement and thumbnail generation.

### 8. UI (`ui/`)
PySide6 desktop app: streaming chat view (HTML renderer with syntax highlighting), chat sidebar,
attachments, VRAM monitor. Background generation runs in `ui/llm_worker.py` so the UI never blocks.

### 9. Chat storage (`core/chat_manager.py`)
SQLite-backed chat history: multi-chat support, auto rename, export, delete.

---

## 🔁 Execution Flow

```
User Input
   ↓
Brain (intent detection)
   ↓
[ LLM | Vision | Diffusion | Tavily Search → LLM ]
   ↓
LLM Worker (streaming, background thread)
   ↓
Renderer (HTML UI)
   ↓
ChatManager (SQLite)
```

---

## 📁 Project Structure

```
NOVA/
│
├── core/
│   ├── brain.py            # intent routing
│   ├── backend_router.py   # LLM/vision/diffusion execution
│   ├── model_loader.py     # GGUF model (llama.cpp)
│   ├── gpu_manager.py
│   ├── gpu_arbiter.py
│   ├── image_engine.py     # Stable Diffusion
│   ├── vision_qwen.py      # Qwen2-VL vision
│   ├── vector_memory.py    # Chroma vector memory
│   ├── tavily_search.py    # live web search
│   └── chat_manager.py     # SQLite chat storage
│
├── ui/
│   ├── main_window.py
│   ├── llm_worker.py
│   ├── renderer.py
│   ├── jsbridge.py
│   ├── chat_manager_ui.py
│   ├── attachment_handler.py
│   └── static/
│
├── config/
│   ├── config.py
│   └── settings.json
│
├── models/                 # local model weights (gitignored)
├── outputs/                # generated images (gitignored)
├── datasets/                # training data (gitignored, large)
│
├── desktop.py               # entry point
├── requirements.txt
├── .env.example
└── README.md
```

---

## ⚙️ Installation

```bash
git clone https://github.com/jangrakunal1104-stack/NOVA.git
cd NOVA

python3 -m venv genv
source genv/bin/activate

pip install -r requirements.txt
```

### Live internet access (Tavily)

NOVA uses [Tavily](https://tavily.com) for live web search (news, prices, current events, anything the
Brain decides is time-sensitive). Get a free API key from the Tavily dashboard, then:

```bash
cp .env.example .env
# edit .env and set TAVILY_API_KEY=your_key_here
```

`desktop.py` loads `.env` automatically on startup via `python-dotenv`. Without a key, search-triggered
queries still work, but the model is told search is unavailable instead of getting live results.

### Local models

Place your models under `models/`:

* `models/gguf/nova_mrblack_q8_0.gguf` — the chat/code model
* `models/vision/Qwen2-VL-2B-Instruct/` — vision model
* `models/diffusion/sd15/` — Stable Diffusion 1.5 pipeline

---

## ▶️ Run

```bash
python desktop.py
```

---

## ⚠️ Requirements

* Python 3.10+
* NVIDIA GPU (recommended; the app runs on CPU but generation will be slow)
* CUDA (for GPU offloading in llama.cpp / torch)
* Local models placed as described above
* A Tavily API key for live search (optional but recommended)

---

## 🧹 Housekeeping

`datasets/`, `models/`, and the various `nova_*` memory/vector-store directories at the repo root hold
large, machine-generated or personal data — they're excluded via `.gitignore` and should never be
committed. If any of these were committed to git history before, they should be purged from history
(e.g. with `git filter-repo`) rather than just removed going forward, since `.gitignore` only affects
future commits.

---

## 🧭 Roadmap

* [ ] Voice (STT + TTS)
* [ ] Tool execution layer
* [ ] Multi-agent system
* [ ] Plugin architecture

---

## 📜 License

MIT License

---

## 👨‍💻 Author

Kunal Jangra
