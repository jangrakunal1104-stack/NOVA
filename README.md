# NOVA 🔥

**Local AI Runtime (LLM + Vision + Diffusion + Desktop UI)**

---

## 🚀 Overview

NOVA is a **fully local multi-modal AI system** that runs entirely offline.

It integrates:

* 🧠 LLM (chat + code)
* 👁️ Vision (OCR + captioning)
* 🎨 Image generation (Stable Diffusion)
* ⚡ Smart routing (intent-based execution)
* 🖥️ Desktop UI (PySide6 with streaming)

Designed as a **modular AI runtime**, not just a chatbot.

---

## ⚡ Features

* ✅ Token-by-token streaming responses
* ✅ Multi-model routing (chat / code / vision / diffusion)
* ✅ OCR → clean code reconstruction
* ✅ Image generation with prompt enhancement
* ✅ File attachments (text + images)
* ✅ Chat history (SQLite)
* ✅ GPU-aware execution + VRAM monitoring
* ✅ Fully offline (no API dependency)

---

## 🧠 Architecture

### 1. Brain (Decision Engine)

* Detects intent from user input
* Routes to:

  * LLM
  * Vision
  * Diffusion
  * Search

---

### 2. Backend Router

* Central execution controller
* Handles:

  * Model switching
  * Streaming generation
  * Vision pipeline
  * Diffusion execution

---

### 3. Model Loader

Supports:

* GGUF (llama.cpp)
* Transformers
* ONNX

Features:

* Streaming tokens
* GPU offloading
* Dynamic load/unload

---

### 4. Vision System

* BLIP → image captioning
* Tesseract → OCR
* OpenCV → preprocessing
* SmartLayer → fixes OCR code

---

### 5. Diffusion Engine

* Stable Diffusion pipeline
* Prompt enhancement + style detection
* Auto thumbnail + base64 rendering

---

### 6. UI System (PySide6)

* Streaming chat interface
* HTML renderer (highlight.js + Dracula theme)
* Sidebar + chat management
* Attachment system
* VRAM monitor

---

### 7. Threading (LLM Worker)

* Runs generation in background
* Streams tokens to UI
* Prevents UI freeze

---

### 8. Chat System

* SQLite database
* Multi-chat support
* Auto rename
* Export / delete

---

## 🔁 Execution Flow

```
User Input
   ↓
Brain (intent detection)
   ↓
Backend Router
   ↓
[LLM | Vision | Diffusion]
   ↓
LLM Worker (streaming)
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
│   ├── brain.py
│   ├── backend_router.py
│   ├── model_loader.py
│   ├── gpu_manager.py
│   ├── gpu_arbiter.py
│   ├── image_engine.py
│   ├── vision_pipeline.py
│   ├── vision_engine.py
│   ├── smart_layer.py
│   ├── context_memory.py
│   ├── chat_manager.py
│   └── ...
│
├── ui/
│   ├── main_window.py
│   ├── llm_worker.py
│   ├── renderer.py
│   └── static/
│
├── models/
├── outputs/
├── attachments/
│
├── nova_desktop.py
├── requirements.txt
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

---

## ▶️ Run

```bash
python nova_desktop.py
```

---

## ⚠️ Requirements

* Python 3.10+
* NVIDIA GPU (recommended)
* CUDA (optional but improves performance)
* Local models (GGUF / diffusion)

---

## 🧭 Roadmap

* [ ] Voice (STT + TTS)
* [ ] Tool execution layer
* [ ] Multi-agent system
* [ ] Vector memory (RAG)
* [ ] Plugin architecture

---

## 📜 License

MIT License

---

## 👨‍💻 Author

Kunal Jangra
